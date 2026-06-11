#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import socket
import struct
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

try:
    from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
except ImportError:
    ServiceBrowser = Zeroconf = None
    ServiceListener = object


SERVICE_TYPE = "_syncleo._udp.local."
BLE_SCAN_SERVICE = "264a38f8-0f60-41fd-9325-b6d3157c4584"

FRAME_ACK = 0
FRAME_CMD = 1
FRAME_NAK = 0xFF

CMD_HANDSHAKE = 0x00
CMD_MODE = 0x01
CMD_TARGET_TEMPERATURE = 0x02
CMD_TARGET_TIME = 0x03
CMD_ERROR = 0x07
CMD_VOLUME = 0x09
CMD_SPEED = 0x0F
CMD_CURRENT_TEMPERATURE = 0x14
CMD_IONIZATION = 0x18
CMD_BACKLIGHT = 0x1C
CMD_CHILD_LOCK = 0x1E
CMD_TANK = 0x1F
CMD_DAMPER = 0x26
CMD_SMART_MODE = 0x28
CMD_BSS = 0x29
CMD_TURBO = 0x31
CMD_NIGHT = 0x32
CMD_CURRENT_POWER = 0x34
CMD_PROGRAM_DATA = 0x42
CMD_TIME_SYNC = 0x80
CMD_WIFI_LIST = 0x81
CMD_WIFI_CONFIG = 0x82
CMD_OPEN_MQTT = 0x87

SECURITY_SERVICE = "d973f1e0-b19e-11e2-9e96-0800200c9a66"
SECURITY_PUBLIC = "d973f1e1-b19e-11e2-9e96-0800200c9a66"
SECURITY_AUTH = "d973f1e5-b19e-11e2-9e96-0800200c9a66"
SECURITY_CURVE = "d973f1e6-b19e-11e2-9e96-0800200c9a66"

WIFI_SERVICE = "305d8319-52e7-73c9-f7bb-18aad4eae5b6"
WIFI_LIST = "831e0e2c-2950-7563-34ff-4b9e045afbc8"
WIFI_STATUS = "b959e5ac-ada9-e16b-619a-3bbfa2b2f35c"
WIFI_CONFIG = "e01bed78-91fc-a247-763e-cb63cddd6e12"


def rev(data: bytes) -> bytes:
    return data[::-1]


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad = block_size - (len(data) % block_size)
    return data + bytes([pad]) * pad


def pkcs7_unpad(data: bytes, block_size: int = 16) -> bytes:
    if not data or len(data) % block_size:
        raise ValueError("invalid PKCS7 data length")
    pad = data[-1]
    if pad < 1 or pad > block_size or data[-pad:] != bytes([pad]) * pad:
        raise ValueError("invalid PKCS7 padding")
    return data[:-pad]


def aes_cbc_encrypt(key: bytes, iv: bytes, data: bytes, *, pad: bool) -> bytes:
    if pad:
        data = pkcs7_pad(data)
    elif len(data) % 16:
        raise ValueError("AES/CBC/NoPadding data length must be a multiple of 16")
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return enc.update(data) + enc.finalize()


def aes_cbc_decrypt(key: bytes, iv: bytes, data: bytes, *, unpad: bool) -> bytes:
    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    out = dec.update(data) + dec.finalize()
    return pkcs7_unpad(out) if unpad else out


def rotate_left(data: bytes, count: int) -> bytes:
    count %= len(data)
    return data[count:] + data[:count]


@dataclass
class SessionKeys:
    tx_iv_base: bytes
    tx_key_base: bytes

    @property
    def rx_key_base(self) -> bytes:
        return self.tx_iv_base

    @property
    def rx_iv_base(self) -> bytes:
        return self.tx_key_base

    def tx_key_iv(self, seq: int) -> tuple[bytes, bytes]:
        return rotate_left(self.tx_key_base, seq & 0x0F), rotate_left(self.tx_iv_base, (seq >> 4) & 0x0F)

    def rx_key_iv(self, seq: int) -> tuple[bytes, bytes]:
        return rotate_left(self.rx_key_base, seq & 0x0F), rotate_left(self.rx_iv_base, (seq >> 4) & 0x0F)


def make_x25519_keys(peer_public_reversed_hex: str) -> tuple[bytes, SessionKeys]:
    peer_public = rev(bytes.fromhex(peer_public_reversed_hex))
    private = x25519.X25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(peer_public))
    digest = hashlib.sha256(rev(shared)).digest()
    return rev(public), SessionKeys(tx_iv_base=digest[:16], tx_key_base=digest[16:])


def frame(seq: int, frame_type: int, payload: bytes) -> bytes:
    return bytes([seq & 0xFF, frame_type & 0xFF]) + struct.pack("<H", len(payload)) + payload


def parse_frame(data: bytes) -> tuple[int, int, bytes] | None:
    if len(data) < 4:
        return None
    seq = data[0]
    frame_type = data[1]
    size = struct.unpack("<H", data[2:4])[0]
    if len(data) != size + 4:
        return None
    return seq, frame_type, data[4:]


def encrypted_cmd_frame(seq: int, cmd: int, payload: bytes, keys: SessionKeys) -> bytes:
    plain = bytes([cmd & 0xFF]) + payload
    key, iv = keys.tx_key_iv(seq)
    encrypted = aes_cbc_encrypt(key, iv, bytes([seq & 0xFF]) + plain, pad=True)
    return frame(seq, FRAME_CMD, encrypted)


def plain_cmd_frame(seq: int, cmd: int, payload: bytes) -> bytes:
    return frame(seq, FRAME_CMD, bytes([cmd & 0xFF]) + payload)


def plain_ack_frame(seq: int) -> bytes:
    return frame(seq, FRAME_ACK, b"")


def encrypted_ack_frame(seq: int, keys: SessionKeys) -> bytes:
    key, iv = keys.tx_key_iv(seq)
    encrypted = aes_cbc_encrypt(key, iv, bytes([seq & 0xFF]), pad=True)
    return frame(seq, FRAME_ACK, encrypted)


def decrypt_frame_payload(seq: int, payload: bytes, keys: SessionKeys) -> bytes:
    key, iv = keys.rx_key_iv(seq)
    plain = aes_cbc_decrypt(key, iv, payload, unpad=True)
    if not plain or plain[0] != (seq & 0xFF):
        raise ValueError("decrypted frame sequence mismatch")
    return plain[1:]


def open_mqtt_payload(host: str, port: int, username: str = "", password: str = "", secure: bool = False) -> bytes:
    host_b = host.encode()
    user_b = username.encode()
    pass_b = password.encode()
    for label, data in (("host", host_b), ("username", user_b), ("password", pass_b)):
        if len(data) > 255:
            raise ValueError(f"{label} is too long")
    return (
        bytes([1 if secure else 0])
        + struct.pack("<H", port)
        + bytes([len(host_b)])
        + host_b
        + bytes([len(user_b)])
        + user_b
        + bytes([len(pass_b)])
        + pass_b
    )


def temperature_payload(value: float) -> bytes:
    integer = int(value)
    fraction = int(round(abs(value - integer) * 100)) & 0x7F
    if value < 0:
        fraction |= 0x80
    return bytes([abs(integer) & 0xFF, fraction])


def parse_temperature_payload(data: bytes) -> float | None:
    if len(data) < 2:
        return None
    sign = -1 if data[1] & 0x80 else 1
    return sign * (data[0] + ((data[1] & 0x7F) / 100.0))


def wifi_config_payload(ssid: str, password: str, mqtt_host: str | None, bssid: bytes) -> bytes:
    ssid_b = ssid.encode()
    pass_b = password.encode()
    mqtt_b = b"" if mqtt_host is None else mqtt_host.encode()
    if len(bssid) != 6:
        raise ValueError("bssid must be 6 bytes")
    for label, data in (("ssid", ssid_b), ("password", pass_b), ("mqtt_host", mqtt_b)):
        if len(data) > 255:
            raise ValueError(f"{label} is too long")
    payload = bssid + bytes([len(ssid_b)]) + ssid_b + bytes([len(pass_b)]) + pass_b
    if mqtt_host:
        payload += bytes([len(mqtt_b)]) + mqtt_b
    return payload


def parse_wifi_list(data: bytes) -> list[dict[str, object]]:
    if len(data) < 2:
        return []
    count = struct.unpack("<H", data[:2])[0]
    pos = 2
    aps: list[dict[str, object]] = []
    for _ in range(count):
        if pos + 7 > len(data):
            break
        bssid = data[pos : pos + 6]
        pos += 6
        ssid_len = data[pos]
        pos += 1
        if pos + ssid_len + 3 > len(data):
            break
        ssid = data[pos : pos + ssid_len].decode(errors="replace")
        pos += ssid_len
        channel = data[pos]
        rssi = struct.unpack("b", data[pos + 1 : pos + 2])[0]
        auth = data[pos + 2]
        pos += 3
        if ssid:
            aps.append({"bssid": bssid.hex(":"), "ssid": ssid, "channel": channel, "rssi": rssi, "auth": auth})
    return aps


@dataclass
class MdnsDevice:
    name: str
    host: str
    port: int
    addresses: list[str]
    txt: dict[str, str]

    @property
    def mac(self) -> str:
        return self.txt.get("macaddr", "")

    @property
    def protocol(self) -> int:
        try:
            return int(self.txt.get("protocol", "1"))
        except ValueError:
            return 1

    @property
    def public(self) -> str:
        return self.txt.get("public", "")


class MdnsCollector(ServiceListener):
    def __init__(self) -> None:
        self.devices: dict[str, MdnsDevice] = {}

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name, timeout=2000)
        if not info:
            return
        addresses = [socket.inet_ntoa(addr) for addr in info.addresses]
        if not addresses:
            return
        txt = {
            (k.decode(errors="replace") if isinstance(k, bytes) else str(k)):
            (v.decode(errors="replace") if isinstance(v, bytes) else str(v))
            for k, v in info.properties.items()
        }
        self.devices[name] = MdnsDevice(name, info.server.rstrip(".") if info.server else name, info.port, addresses, txt)

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self.add_service(zc, type_, name)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self.devices.pop(name, None)


def discover_mdns(timeout: float = 5.0) -> list[MdnsDevice]:
    if Zeroconf is None or ServiceBrowser is None:
        raise SystemExit("Missing dependency: python3 -m pip install zeroconf")
    collector = MdnsCollector()
    zc = Zeroconf()
    try:
        # ServiceBrowser(zc, SERVICE_TYPE, handlers=[collector.add_service])
        ServiceBrowser(zc, SERVICE_TYPE, listener=collector)
        end = time.time() + timeout
        while time.time() < end:
            time.sleep(0.1)
        return sorted(collector.devices.values(), key=lambda d: (d.mac, d.name))
    finally:
        zc.close()


def save_device_record(path: str | Path, record: dict[str, object]) -> None:
    Path(path).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def load_device_record(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text())


def choose(items: list[object], render) -> object:
    for idx, item in enumerate(items, 1):
        print(f"{idx:2d}. {render(item)}")
    while True:
        raw = input("Select number: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            print("Enter a number.")
            continue
        if 1 <= idx <= len(items):
            return items[idx - 1]
        print("Number out of range.")


def send_udp_secure_open_mqtt(
    address: str,
    port: int,
    public_hex: str,
    token_hex: str,
    mqtt_host: str,
    mqtt_port: int,
    username: str = "",
    password: str = "",
    secure: bool = False,
    timeout: float = 3.0,
) -> None:
    token = bytes.fromhex(token_hex)
    if len(token) != 16:
        raise ValueError("token must be 16 bytes / 32 hex chars")
    phone_public, keys = make_x25519_keys(public_hex)
    encrypted_token = aes_cbc_encrypt(keys.tx_key_base, keys.tx_iv_base, token, pad=False)
    handshake_payload = bytes([CMD_HANDSHAKE]) + phone_public + encrypted_token

    target = (address, port)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(frame(0, FRAME_CMD, handshake_payload), target)

        ready = False
        end = time.time() + timeout
        while time.time() < end and not ready:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            parsed = parse_frame(data)
            if not parsed:
                continue
            seq, frame_type, payload = parsed
            if frame_type == FRAME_CMD:
                plain = decrypt_frame_payload(seq, payload, keys)
                if plain and plain[0] == CMD_HANDSHAKE:
                    sock.sendto(encrypted_ack_frame(seq, keys), target)
                    ready = True
            elif frame_type == FRAME_ACK:
                continue
            elif frame_type == FRAME_NAK:
                raise RuntimeError("device returned NAK during handshake")
        if not ready:
            raise TimeoutError("secure UDP handshake did not complete")

        payload = open_mqtt_payload(mqtt_host, mqtt_port, username, password, secure)
        sock.sendto(encrypted_cmd_frame(1, CMD_OPEN_MQTT, payload, keys), target)
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            parsed = parse_frame(data)
            if not parsed:
                continue
            seq, frame_type, _payload = parsed
            if frame_type == FRAME_ACK and seq == 1:
                return
            if frame_type == FRAME_NAK and seq == 1:
                raise RuntimeError("device returned NAK for CmdOpenMqtt")
        raise TimeoutError("no ACK for CmdOpenMqtt")
