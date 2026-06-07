from __future__ import annotations

DOMAIN = "hommyn_local_mqtt"

CONF_MAC = "mac"
CONF_SCAN_TIMEOUT = "scan_timeout"
CONF_TOPIC_PREFIX = "topic_prefix"
CONF_DEVICE_NAME = "device_name"

PLATFORMS = ["binary_sensor", "sensor", "number", "switch", "select", "climate"]

MODE_OPTIONS = [
    "0",  # Off
    "1",  # Auto
    "2",  # Cooling
    "3",  # Dry
    "4",  # Heating
    "5",  # Fan
]

POWER_OPTIONS = [
    "0",  # Auto
    "1",  # Low
    "2",  # "Medium
    "3",  # High
    "4",  # Turbo
]

POWER_MODE_OPTIONS = [
    "0",  # Manual
    "1",  # Auto
]

ERROR_OPTIONS = {
    "0": "OK",
    "1": "E1",
    "2": "E2",
    "3": "E3",
    "4": "E4",
}

STATE_SUFFIXES = [
    "mode/out",
    "timer/out",
    "child_lock/out",
    "backlight/out",
    "sound/out",
    "open_window/out",
    "open_window_detect/out",
    "sensor/temperature/out",
    "power/out",
    "power_mode/out",
    "temperature_comfort/out",
    "temperature_eco/out",
    "temperature_antifrost/out",
    "error/out",
    "backlight_auto/out",
    "half_power/out",
]
