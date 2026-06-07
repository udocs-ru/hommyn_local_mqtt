from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature

from .const import (
    TOPIC_TEMPERATURE_ANTIFROST,
    TOPIC_TEMPERATURE_COMFORT,
    TOPIC_TEMPERATURE_ECO,
)
from .helpers import float_payload

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorStateClass

from .entity import HommynMqttEntity, HommynTopic


@dataclass(frozen=True)
class NumberSpec:
    topic: HommynTopic
    min: int
    max: int
    step: int


SPECS = [
    NumberSpec(
        topic=HommynTopic(
            key="temperature_comfort",
            out_suffix=TOPIC_TEMPERATURE_COMFORT,
            in_suffix=TOPIC_TEMPERATURE_COMFORT,
        ),
        min=16,
        max=32,
        step=1,
    ),
    NumberSpec(
        topic=HommynTopic(
            key="temperature_eco",
            out_suffix=TOPIC_TEMPERATURE_ECO,
            in_suffix=TOPIC_TEMPERATURE_ECO,
            is_enabled=False,
        ),
        min=3,
        max=7,
        step=1,
    ),
    NumberSpec(
        topic=HommynTopic(
            key="temperature_antifrost",
            out_suffix=TOPIC_TEMPERATURE_ANTIFROST,
            in_suffix=TOPIC_TEMPERATURE_ANTIFROST,
            is_enabled=False,
        ),
        min=3,
        max=7,
        step=1,
    ),
]


async def async_setup_entry(
    _hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            HommynNumber(entry, spec.topic, spec.min, spec.max, spec.step)
            for spec in SPECS
        ]
    )


class HommynNumber(HommynMqttEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        entry: ConfigEntry,
        spec: HommynTopic,
        min_value: float,
        max_value: float,
        step: float,
    ) -> None:
        super().__init__(entry, spec)
        if spec.key == "temperature_comfort":
            self._attr_device_class = NumberDeviceClass.TEMPERATURE
        else:
            self._attr_device_class = NumberDeviceClass.TEMPERATURE_DELTA

        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_native_value = None

    @override
    def _handle_payload(self, payload: str) -> None:
        value = float_payload(payload)
        if value is not None:
            self._attr_native_value = value

    @override
    async def async_set_native_value(self, value: float) -> None:
        if float(value).is_integer():
            payload = str(int(value))
        else:
            payload = str(value)
        self._attr_native_value = value
        await self._publish(payload)
        self.async_write_ha_state()
