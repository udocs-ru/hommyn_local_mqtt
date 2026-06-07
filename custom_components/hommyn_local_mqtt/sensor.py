from __future__ import annotations

from typing import TYPE_CHECKING, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature

from .const import ERROR_OPTIONS
from .entity import HommynMqttEntity, HommynTopic, float_payload, int_payload

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

SPECS: list[HommynTopic] = [
    HommynTopic(key="current_temperature", out_suffix="sensor/temperature/out"),
    HommynTopic(key="error", translation_key="error", out_suffix="error/out"),
]


async def async_setup_entry(
    _hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([HommynSensor(entry, spec) for spec in SPECS])


class HommynSensor(HommynMqttEntity, SensorEntity):
    def __init__(self, entry: ConfigEntry, spec: HommynTopic) -> None:
        super().__init__(entry, spec)
        self._attr_native_value = None

        if spec.key == "current_temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif spec.key == "error":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(ERROR_OPTIONS.values())

    @override
    def _handle_payload(self, _payload: str) -> None:
        # Сенсор ошибки
        if self._spec.key == "error":
            code = int_payload(_payload)
            if code is not None:
                self._attr_native_value = ERROR_OPTIONS.get(str(code), _payload)
            else:
                self._attr_native_value = _payload
            return

        # Сенсор температуры (числовые значения)
        value = float_payload(_payload)
        if value is not None:
            self._attr_native_value = round(value, 6)
        else:
            # Если не число, возможно строка "off" или подобное
            self._attr_native_value = _payload.strip()
