#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from typing import Iterable

from hommyn_proto import (
    choose,
    discover_mdns,
    load_device_record,
    send_udp_secure_open_mqtt,
)


def normalize_mac(value: str) -> str:
    raw = re.sub(r"[^0-9a-fA-F]", "", value)
    if len(raw) != 12:
        return value.lower()
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2)).lower()


def render_device(dev) -> str:
    txt = dev.txt
    return (
        f"{dev.addresses[0]}:{dev.port} mac={dev.mac or '-'} "
        f"protocol={dev.protocol} firmware={txt.get('firmware', '-')} "
        f"devtype={txt.get('devtype', '-')} name={dev.name}"
    )


def select_device(devices, mac: str | None):
    if mac:
        wanted = normalize_mac(mac)
        matches = [dev for dev in devices if normalize_mac(dev.mac) == wanted]
        if not matches:
            raise SystemExit(f"No mDNS device with macaddr={wanted}")
        return matches[0]
    if len(devices) == 1:
        print(f"Using only discovered device: {render_device(devices[0])}")
        return devices[0]
    print("Discovered Hommyn devices:")
    return choose(devices, render_device)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Set custom MQTT on a protocol v3 Hommyn device using saved token."
    )
    parser.add_argument(
        "--keys",
        default="hommyn_device.json",
        help="JSON saved by hommyn_ble_provision.py",
    )
    parser.add_argument("--host", required=True, help="MQTT broker hostname or IP")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--user", default="", help="MQTT username")
    parser.add_argument("--password", default="", help="MQTT password")
    parser.add_argument(
        "--secure", action="store_true", help="Set SSL/TLS flag; usually use port 8883"
    )
    parser.add_argument(
        "--mac",
        help="Device MAC to select from mDNS; defaults to macaddr from --keys if present",
    )
    parser.add_argument(
        "--discover-timeout",
        type=float,
        default=5.0,
        help="mDNS discovery time in seconds",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=4.0,
        help="UDP handshake/ACK timeout in seconds",
    )
    args = parser.parse_args(argv)

    record = load_device_record(args.keys)
    token = str(record.get("token", ""))
    if not token:
        raise SystemExit(f"No token field in {args.keys}")

    devices = discover_mdns(args.discover_timeout)
    if not devices:
        raise SystemExit("No Hommyn devices found via mDNS _syncleo._udp.")

    mac = args.mac or record.get("macaddr")
    device = select_device(devices, str(mac) if mac else None)
    if not device.public:
        raise SystemExit("Selected device does not advertise public key in mDNS TXT.")

    send_udp_secure_open_mqtt(
        address=device.addresses[0],
        port=device.port,
        public_hex=device.public,
        token_hex=token,
        mqtt_host=args.host,
        mqtt_port=args.port,
        username=args.user,
        password=args.password,
        secure=args.secure,
        timeout=args.timeout,
    )
    print(
        f"MQTT settings sent to {device.addresses[0]}:{device.port} mac={device.mac or '-'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
