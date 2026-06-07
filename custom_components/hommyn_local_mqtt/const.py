from __future__ import annotations

DOMAIN = "hommyn_local_mqtt"

CONF_TOPIC_PREFIX = "topic_prefix"

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
    "2",  # Medium
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

TOPIC_CURRENT_TEMPERATURE = "sensor/temperature"
TOPIC_ERROR = "error"
TOPIC_BACKLIGHT_AUTO = "backlight_auto"
TOPIC_TIMER = "timer"
TOPIC_CHILD_LOCK = "child_lock"
TOPIC_SOUND = "sound"
TOPIC_BACKLIGHT = "backlight"
TOPIC_OPEN_WINDOW = "open_window"
TOPIC_HALF_POWER = "half_power"
TOPIC_MODE = "mode"
TOPIC_POWER = "power"
TOPIC_POWER_MODE = "power_mode"
TOPIC_TEMPERATURE_COMFORT = "temperature_comfort"
TOPIC_TEMPERATURE_ECO = "temperature_eco"
TOPIC_TEMPERATURE_ANTIFROST = "temperature_antifrost"
TOPIC_OPEN_WINDOW_DETECT = "open_window_detect"

STATE_SUFFIXES = [
    f"{TOPIC_MODE}/out",
    f"{TOPIC_CURRENT_TEMPERATURE}/out",
    f"{TOPIC_TEMPERATURE_COMFORT}/out",
    f"{TOPIC_POWER}/out",
    f"{TOPIC_POWER_MODE}/out",
]
