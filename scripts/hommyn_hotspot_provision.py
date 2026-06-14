#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import struct
import subprocess
import time
from pathlib import Path
from typing import Iterable

from hommyn_proto import (
    CMD_HANDSHAKE,
    FRAME_ACK,
    FRAME_CMD,
    FRAME_NAK,
    parse_frame,
    plain_ack_frame,
    plain_cmd_frame,
)


def mac_bytes(value: str) -> bytes:
    raw = "".join(ch for ch in value if ch.lower() in "0123456789abcdef")
    if len(raw) != 12:
        raise ValueError("BSSID must contain 12 hex digits")
    return bytes.fromhex(raw)


def default_gateway() -> str | None:
    try:
        out = subprocess.check_output(
            ["ip", "route", "show", "default"], text=True, timeout=2
        )
    except Exception:
        return None
    for line in out.splitlines():
        parts = line.split()
        if parts[:1] == ["default"] and "via" in parts:
            return parts[parts.index("via") + 1]
    return None


def send_cmd(
    sock: socket.socket, target: tuple[str, int], seq: int, cmd: int, payload: bytes
) -> None:
    sock.sendto(plain_cmd_frame(seq, cmd, payload), target)


def send_ack(sock: socket.socket, target: tuple[str, int], seq: int) -> None:
    sock.sendto(plain_ack_frame(seq), target)


def read_frames(sock: socket.socket, timeout: float):
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, addr = sock.recvfrom(8192)
        except socket.timeout:
            continue
        parsed = parse_frame(data)
        if not parsed:
            print(f"Malformed UDP frame from {addr}: {data.hex()}")
            continue
        yield addr, parsed


def read_until(
    sock: socket.socket,
    target: tuple[str, int],
    timeout: float,
    wanted_cmd: int | None = None,
):
    for _addr, (seq, frame_type, payload) in read_frames(sock, timeout):
        if frame_type == FRAME_CMD:
            if payload:
                send_ack(sock, target, seq)
                cmd = payload[0]
                body = payload[1:]
                if wanted_cmd is None or cmd == wanted_cmd:
                    return seq, cmd, body
            continue
        if frame_type == FRAME_ACK:
            if wanted_cmd is None:
                return seq, None, b""
            continue
        if frame_type == FRAME_NAK:
            raise RuntimeError("device returned NAK")
    return None


def hotspot_handshake(
    sock: socket.socket, target: tuple[str, int], timeout: float
) -> dict[str, object]:
    send_cmd(sock, target, 0, CMD_HANDSHAKE, b"\x00" * 16)
    result = read_until(sock, target, timeout, CMD_HANDSHAKE)
    if result is None:
        raise TimeoutError("no CmdHandshake response")
    _seq, _cmd, body = result
    if len(body) < 21:
        raise RuntimeError(f"short CmdHandshake response: {body.hex()}")
    protocol = struct.unpack("<H", body[:2])[0]
    firmware = f"{body[2]}.{body[3]}"
    mode = body[4]
    token = body[5:21]
    print(
        f"Handshake: protocol={protocol} firmware={firmware} mode={mode} token={token.hex()}"
    )
    return {
        "protocol": protocol,
        "firmware": firmware,
        "mode": mode,
        "token": token.hex(),
    }


def send_time_sync(
    sock: socket.socket, target: tuple[str, int], seq: int, timeout: float
) -> None:
    now = int(time.time())
    offset_min = -time.timezone // 60
    payload = struct.pack("<ih", now, offset_min)
    send_cmd(sock, target, seq, CMD_TIME_SYNC, payload)
    for _addr, (resp_seq, frame_type, _payload) in read_frames(sock, timeout):
        if frame_type == FRAME_ACK and resp_seq == seq:
            return


def configure(args: argparse.Namespace) -> None:
    gateway = args.gateway or default_gateway() or "192.168.4.1"
    target = (gateway, args.port)
    print(f"Target hotspot gateway: {target[0]}:{target[1]}")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(args.timeout)

        handshake = hotspot_handshake(sock, target, args.timeout)
        if args.out:
            record = {
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "gateway": gateway,
                "hotspot": True,
                "port": args.port,
                **handshake,
            }
            Path(args.out).write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n"
            )
            print(f"Saved token to {args.out}")

        send_time_sync(sock, target, 1, args.timeout)

        aps: list[dict[str, object]] = []
        if not args.no_scan:
            print("Requesting WiFi AP list from device...")
            aps = request_wifi_list(sock, target, args.timeout)

        bssid = select_bssid(aps, args.ssid, args.bssid)
        payload = wifi_config_payload(
            args.ssid, args.wifi_password, args.mqtt_host, bssid
        )

        seq = 3
        for attempt in range(1, args.retries + 1):
            print(f"Sending WiFi config attempt {attempt}/{args.retries}")
            send_cmd(sock, target, seq, CMD_WIFI_CONFIG, payload)
            for _addr, (resp_seq, frame_type, resp_payload) in read_frames(
                sock, args.timeout
            ):
                if frame_type == FRAME_ACK and resp_seq == seq:
                    print("ACK received.")
                    return
                if frame_type == FRAME_NAK:
                    raise SystemExit("Device returned NAK for WiFi config.")
                if (
                    frame_type == FRAME_CMD
                    and resp_payload
                    and resp_payload[0] == CMD_WIFI_CONFIG
                ):
                    send_ack(sock, target, resp_seq)
                    status = resp_payload[1] if len(resp_payload) > 1 else None
                    result = resp_payload[2] if len(resp_payload) > 2 else None
                    print(
                        f"WiFi status: status={status} result={result} raw={resp_payload[1:].hex()}"
                    )
                    if status == 1:
                        return
            seq = (seq + 1) & 0xFF

    raise SystemExit("No ACK/status from device.")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Configure Hommyn device through WFN-02/hotspot UDP mode."
    )
    parser.add_argument(
        "--ssid", required=True, help="Home WiFi SSID to send to the device"
    )
    parser.add_argument("--wifi-password", required=True, help="Home WiFi password")
    parser.add_argument(
        "--mqtt-host",
        help="Optional MQTT host to include in CmdWifiConfiguration payload",
    )
    parser.add_argument(
        "--bssid",
        help="Home WiFi BSSID; if omitted, ask device for WiFi list and select matching SSID",
    )
    parser.add_argument(
        "--gateway",
        help="Hotspot gateway IP; default: system default gateway, then 192.168.4.1",
    )
    parser.add_argument("--port", type=int, default=41122, help="Hotspot UDP port")
    parser.add_argument(
        "--timeout", type=float, default=4.0, help="UDP response timeout"
    )
    parser.add_argument("--retries", type=int, default=3, help="WiFi config retries")
    parser.add_argument(
        "--no-scan",
        action="store_true",
        help="Do not request WiFi AP list before configuration",
    )
    parser.add_argument(
        "--out",
        default="hommyn_hotspot_device.json",
        help="Output JSON for token returned by hotspot handshake",
    )
    args = parser.parse_args(argv)
    configure(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
