#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import socket
import subprocess
import time
from typing import Any, Iterable

from hommyn_hotspot_provision import (
    default_gateway,
    hotspot_handshake,
    read_frames,
    request_wifi_list,
    select_bssid,
    send_cmd,
    send_time_sync,
)
from hommyn_proto import (
    CMD_HANDSHAKE,
    CMD_WIFI_CONFIG,
    FRAME_ACK,
    FRAME_CMD,
    FRAME_NAK,
    aes_cbc_encrypt,
    decrypt_frame_payload,
    discover_mdns,
    encrypted_ack_frame,
    frame,
    make_x25519_keys,
    wifi_config_payload,
)


DEFAULT_HOTSPOT_GATEWAY = "192.168.4.1"
DEFAULT_PORT = 41122
MAC_RE = re.compile(r"(?i)([0-9a-f]{2}[:-]){5}[0-9a-f]{2}")


def yes_no(prompt: str, default: bool | None = None) -> bool:
    """Ask a yes/no question."""
    suffix = " [y/n]"
    if default is True:
        suffix = " [Y/n]"
    elif default is False:
        suffix = " [y/N]"
    while True:
        raw = input(f"{prompt}{suffix}: ").strip().lower()
        if not raw and default is not None:
            return default
        if raw in {"y", "yes", "д", "да"}:
            return True
        if raw in {"n", "no", "н", "нет"}:
            return False
        print("Введите y/yes/да или n/no/нет.")


def ask(prompt: str, default: str | None = None, *, secret: bool = False) -> str:
    """Ask for a value."""
    import getpass

    shown = f"{prompt}"
    if default:
        shown += f" [{default}]"
    shown += ": "
    raw = getpass.getpass(shown) if secret else input(shown)
    value = raw.strip()
    return value if value else (default or "")


def normalize_mac(value: str | None) -> str:
    """Normalize MAC to aa:bb:cc:dd:ee:ff when possible."""
    if not value:
        return ""
    raw = re.sub(r"[^0-9a-fA-F]", "", value)
    if len(raw) != 12:
        return value.strip().lower()
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2)).lower()


def mac_to_int(value: str | None) -> int | None:
    """Convert MAC to integer."""
    mac = normalize_mac(value)
    raw = mac.replace(":", "")
    if len(raw) != 12:
        return None
    try:
        return int(raw, 16)
    except ValueError:
        return None


def is_neighbor_mac(left: str | None, right: str | None, distance: int = 1) -> bool:
    """Return whether two MAC addresses are close enough to be ESP32 AP/STA pair."""
    left_int = mac_to_int(left)
    right_int = mac_to_int(right)
    if left_int is None or right_int is None:
        return False
    return abs(left_int - right_int) <= distance


def extract_mac(value: str) -> str:
    """Extract first MAC address from command output."""
    match = MAC_RE.search(value)
    return normalize_mac(match.group(0)) if match else ""


def run_text_command(args: list[str], timeout: float = 2.0) -> str:
    """Run a local command and return stdout/stderr text."""
    try:
        return subprocess.check_output(args, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except Exception:
        return ""


def ping_gateway(gateway: str, timeout: float) -> bool:
    """Check whether hotspot gateway is reachable."""
    deadline = max(1, int(timeout))
    out = run_text_command(["ping", "-c", "1", "-W", str(deadline), gateway], timeout=timeout + 1)
    return " 0% packet loss" in out or "bytes from" in out


def hotspot_gateway_mac(gateway: str) -> str:
    """Read hotspot gateway MAC from Linux neighbor/ARP tables."""
    out = run_text_command(["ip", "neigh", "show", gateway])
    mac = extract_mac(out)
    if mac:
        return mac
    out = run_text_command(["arp", "-n", gateway])
    return extract_mac(out)


def token_is_zero(token_hex: str) -> bool:
    """Return whether token is empty/zero."""
    try:
        token = bytes.fromhex(token_hex)
    except ValueError:
        return True
    return not token or all(byte == 0 for byte in token)


def render_mdns_device(device: Any) -> str:
    """Render one mDNS device line."""
    txt = device.txt
    return (
        f"{device.addresses[0]}:{device.port} "
        f"mac={device.mac or '-'} protocol={device.protocol} firmware={txt.get('firmware', '-')} "
        f"basetype={txt.get('basetype', '-')} devtype={txt.get('devtype', '-')} "
        f"name={device.name}"
    )


def get_hotspot_token(gateway: str, port: int, timeout: float, retries: int) -> dict[str, Any]:
    """Read a non-zero token from the device hotspot."""
    target = (gateway, port)
    print(f"\nПодключаюсь к устройству: {gateway}:{port}")
    if not ping_gateway(gateway, timeout):
        raise SystemExit(
            f"Gateway {gateway} недоступен. Проверьте, что компьютер подключен к Wi-Fi устройства "
            "WFN-02-01 и получил адрес из сети устройства."
        )
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        last_handshake: dict[str, Any] | None = None
        for attempt in range(1, retries + 1):
            print(f"Запрос токена, попытка {attempt}/{retries}...")
            try:
                handshake = hotspot_handshake(sock, target, timeout)
            except TimeoutError:
                print("Нет ответа на UDP handshake. Устройство может быть не в режиме сопряжения или порт недоступен.")
                time.sleep(1)
                continue
            except OSError as exc:
                raise SystemExit(f"Ошибка UDP при обращении к {gateway}:{port}: {exc}") from exc
            last_handshake = handshake
            if not token_is_zero(str(handshake.get("token", ""))):
                return handshake
            print("Устройство вернуло нулевой токен, повторяю запрос.")
            time.sleep(1)
    raise SystemExit(f"Не удалось получить ненулевой токен. Последний ответ: {last_handshake}")


def configure_wifi_interactive(gateway: str, port: int, timeout: float, retries: int) -> None:
    """Ask for Wi-Fi/MQTT settings and send CmdWifiConfiguration."""
    ssid = ask("SSID домашней Wi-Fi сети")
    if not ssid:
        raise SystemExit("SSID не задан.")
    password = ask("Пароль Wi-Fi", secret=True)
    mqtt_host = ask("MQTT host для записи в устройство, можно оставить пустым", "")
    explicit_bssid = ask("BSSID точки доступа, можно оставить пустым", "")

    target = (gateway, port)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        print("\nПовторяю handshake перед отправкой Wi-Fi настроек...")
        try:
            hotspot_handshake(sock, target, timeout)
        except TimeoutError as exc:
            raise SystemExit("Не удалось повторить hotspot-handshake перед отправкой Wi-Fi настроек.") from exc
        send_time_sync(sock, target, 1, timeout)

        print("Запрашиваю список Wi-Fi сетей у устройства...")
        aps = request_wifi_list(sock, target, timeout)
        bssid = select_bssid(aps, ssid, explicit_bssid or None)
        payload = wifi_config_payload(ssid, password, mqtt_host or None, bssid)

        seq = 3
        for attempt in range(1, retries + 1):
            print(f"Отправляю Wi-Fi настройки, попытка {attempt}/{retries}...")
            send_cmd(sock, target, seq, CMD_WIFI_CONFIG, payload)
            for _addr, (resp_seq, frame_type, resp_payload) in read_frames(sock, timeout):
                if frame_type == FRAME_ACK and resp_seq == seq:
                    print("Устройство подтвердило прием Wi-Fi настроек.")
                    return
                if frame_type == FRAME_NAK:
                    raise SystemExit("Устройство вернуло NAK на Wi-Fi настройки.")
                if frame_type == FRAME_CMD and resp_payload and resp_payload[0] == CMD_WIFI_CONFIG:
                    status = resp_payload[1] if len(resp_payload) > 1 else None
                    result = resp_payload[2] if len(resp_payload) > 2 else None
                    print(f"Статус Wi-Fi настройки: status={status} result={result} raw={resp_payload[1:].hex()}")
                    if status == 1:
                        return
            seq = (seq + 1) & 0xFF
    raise SystemExit("Устройство не подтвердило Wi-Fi настройки.")


def secure_handshake_probe(device: Any, token_hex: str, timeout: float) -> bool:
    """Return whether token works for this mDNS device."""
    if not device.public:
        return False
    token = bytes.fromhex(token_hex)
    if len(token) != 16:
        return False

    phone_public, keys = make_x25519_keys(device.public)
    encrypted_token = aes_cbc_encrypt(keys.tx_key_base, keys.tx_iv_base, token, pad=False)
    payload = bytes([CMD_HANDSHAKE]) + phone_public + encrypted_token
    target = (device.addresses[0], device.port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(frame(0, FRAME_CMD, payload), target)
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, _addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            parsed = None
            try:
                from hommyn_proto import parse_frame

                parsed = parse_frame(data)
            except Exception:
                parsed = None
            if not parsed:
                continue
            seq, frame_type, frame_payload = parsed
            if frame_type == FRAME_NAK:
                return False
            if frame_type != FRAME_CMD:
                continue
            try:
                plain = decrypt_frame_payload(seq, frame_payload, keys)
            except Exception:
                return False
            if plain and plain[0] == CMD_HANDSHAKE:
                sock.sendto(encrypted_ack_frame(seq, keys), target)
                return True
    return False


def discover_target_device(
    token_hex: str,
    mac: str,
    hotspot_mac: str,
    discover_timeout: float,
    udp_timeout: float,
    attempts: int,
):
    """Find the configured device in mDNS."""
    wanted_mac = normalize_mac(mac)
    hotspot_mac = normalize_mac(hotspot_mac)
    for attempt in range(1, attempts + 1):
        print(f"\nИщу Hommyn устройства в mDNS, попытка {attempt}/{attempts}...")
        devices = discover_mdns(discover_timeout)
        if not devices:
            print("mDNS пока ничего не нашел.")
            continue

        print("Найденные устройства:")
        for idx, device in enumerate(devices, 1):
            print(f" {idx}. {render_mdns_device(device)}")

        if wanted_mac:
            matches = [device for device in devices if normalize_mac(device.mac) == wanted_mac]
            if matches:
                print(f"Устройство найдено по точному MAC: {wanted_mac}")
                return matches[0]
            near_matches = [device for device in devices if is_neighbor_mac(device.mac, wanted_mac)]
            if len(near_matches) == 1:
                print(f"Устройство найдено по соседнему MAC: задан {wanted_mac}, mDNS {near_matches[0].mac}")
                return near_matches[0]
            print(f"Устройство с macaddr={wanted_mac} пока не найдено.")

        if hotspot_mac:
            matches = [device for device in devices if normalize_mac(device.mac) == hotspot_mac]
            if matches:
                print(f"Устройство найдено по MAC hotspot gateway: {hotspot_mac}")
                return matches[0]
            near_matches = [device for device in devices if is_neighbor_mac(device.mac, hotspot_mac)]
            if len(near_matches) == 1:
                print(f"Устройство найдено по соседнему MAC hotspot: hotspot {hotspot_mac}, mDNS {near_matches[0].mac}")
                return near_matches[0]
            if len(near_matches) > 1:
                print("По соседнему MAC найдено несколько устройств, дополнительно проверяю токен.")
                token_matches = [device for device in near_matches if secure_handshake_probe(device, token_hex, udp_timeout)]
                if len(token_matches) == 1:
                    return token_matches[0]
                raise SystemExit("Не удалось однозначно сопоставить hotspot MAC с mDNS устройством.")

        print("MAC не задан, пробую определить нужное устройство по полученному токену...")
        matches = []
        for device in devices:
            if secure_handshake_probe(device, token_hex, udp_timeout):
                matches.append(device)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SystemExit(
                "Токен неожиданно прошел проверку на нескольких mDNS устройствах. "
                "Это не должно происходить; запустите скрипт с --mac для точного выбора."
            )

        if len(devices) == 1:
            print("Токеном подтвердить не удалось, но найдено только одно устройство.")
            if yes_no("Использовать единственное найденное устройство?", False):
                return devices[0]

        print("Нужное устройство пока не определено.")
    return None


def build_ha_record(device: Any, token_hex: str, hotspot_handshake_data: dict[str, Any], hotspot_mac: str) -> dict[str, Any]:
    """Build a JSON record with fields needed by Home Assistant."""
    txt = device.txt
    return {
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "name": device.name,
        "host": device.addresses[0],
        "port": device.port,
        "token": token_hex,
        "macaddr": device.mac,
        "hotspot_mac": hotspot_mac or None,
        "public": device.public,
        "curve": txt.get("curve"),
        "protocol": txt.get("protocol") or hotspot_handshake_data.get("protocol"),
        "firmware": txt.get("firmware") or hotspot_handshake_data.get("firmware"),
        "basetype": txt.get("basetype"),
        "devtype": txt.get("devtype"),
        "vendor": txt.get("vendor"),
        "mdns_host": device.host,
        "mdns_txt": txt,
    }


def print_ha_summary(record: dict[str, Any]) -> None:
    """Print values needed for the HA config flow."""
    print("\nДанные для настройки Home Assistant / Hommyn UDP:")
    for key in ("host", "port", "token", "macaddr", "public", "curve", "protocol", "firmware", "basetype", "devtype", "vendor"):
        print(f"  {key}: {record.get(key) or '-'}")
    print("\nJSON:")
    print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare Hommyn UDP Home Assistant settings from pairing mode.")
    parser.add_argument("--gateway", help="IP шлюза hotspot устройства, по умолчанию default gateway или 192.168.4.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP порт устройства, default: 41122")
    parser.add_argument("--timeout", type=float, default=4.0, help="UDP timeout")
    parser.add_argument("--token-retries", type=int, default=5, help="Сколько раз запрашивать ненулевой токен")
    parser.add_argument("--discover-timeout", type=float, default=8.0, help="mDNS scan timeout")
    parser.add_argument("--discover-attempts", type=int, default=6, help="Количество mDNS попыток после подключения к домашней сети")
    parser.add_argument("--mac", help="MAC устройства, если известен; иначе скрипт попробует найти устройство по токену")
    parser.add_argument("--skip-wifi-question", action="store_true", help="Не спрашивать про Wi-Fi настройки, только получить токен")
    args = parser.parse_args(argv)

    print(
        "Шаг 1. Переведите устройство в режим сопряжения.\n"
        "Обычно нужно удерживать кнопку на устройстве около 5 секунд, пока индикатор не начнет мигать.\n"
        "Затем подключите компьютер к Wi-Fi сети устройства: WFN-02-01.\n"
    )
    input("Когда компьютер подключен к WFN-02-01, нажмите Enter...")

    gateway = args.gateway or default_gateway() or DEFAULT_HOTSPOT_GATEWAY
    handshake = get_hotspot_token(gateway, args.port, args.timeout, args.token_retries)
    token_hex = str(handshake["token"])
    print(f"\nПолучен ненулевой токен: {token_hex}")
    hotspot_mac = hotspot_gateway_mac(gateway)
    if hotspot_mac:
        print(f"MAC устройства в hotspot/ARP: {hotspot_mac}")
    else:
        print("Не удалось определить MAC hotspot gateway через ARP/ip neigh; продолжу поиск по токену.")

    print(
        "\nШаг 2. Подключите компьютер обратно к вашей домашней Wi-Fi/LAN сети.\n"
        "Устройство тоже должно подключиться к этой сети и начать вещать mDNS _syncleo._udp.\n"
    )
    input("Когда компьютер снова в домашней сети, нажмите Enter...")

    device = discover_target_device(
        token_hex,
        args.mac or "",
        hotspot_mac,
        args.discover_timeout,
        args.timeout,
        args.discover_attempts,
    )
    if device is None:
        raise SystemExit(
            "Не удалось найти устройство в mDNS. Проверьте, что устройство подключилось к домашней сети, "
            "а mDNS/UDP multicast не заблокирован роутером."
        )

    record = build_ha_record(device, token_hex, handshake, hotspot_mac)
    print_ha_summary(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
