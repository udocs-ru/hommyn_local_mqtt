from __future__ import annotations

from typing import TYPE_CHECKING, override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant

from .entity import HommynMqttEntity, HommynTopic, int_payload

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

BINARY_SENSORS = [
    HommynTopic(
        key="open_window_detect",
        translation_key="open_window_detect",
        out_suffix="open_window_detect/out",
    ),
]


async def async_setup_entry(
    _hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([HommynBinarySensor(entry, spec) for spec in BINARY_SENSORS])


class HommynBinarySensor(HommynMqttEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.WINDOW

    def __init__(self, entry: ConfigEntry, spec: HommynTopic) -> None:
        super().__init__(entry, spec)
        self._attr_is_on = None

    @override
    def _handle_payload(self, payload: str) -> None:
        value = int_payload(payload)
        if value is not None:
            self._attr_is_on = value == 1
