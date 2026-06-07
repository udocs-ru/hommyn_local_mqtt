from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorStateClass

from .entity import HommynMqttEntity, HommynTopic, float_payload


@dataclass(frozen=True)
class NumberSpec:
    topic: HommynTopic
    min: int
    max: int
    step: int


SPECS: list[NumberSpec] = [
    NumberSpec(
        topic=HommynTopic(
            key="temperature_comfort",
            translation_key="temperature_comfort",
            out_suffix="temperature_comfort/out",
            in_suffix="temperature_comfort/in",
        ),
        min=17,
        max=32,
        step=1,
    ),
    NumberSpec(
        topic=HommynTopic(
            key="temperature_eco",
            translation_key="temperature_eco",
            out_suffix="temperature_eco/out",
            in_suffix="temperature_eco/in",
            is_enabled=False,
        ),
        min=3,
        max=7,
        step=1,
    ),
    NumberSpec(
        topic=HommynTopic(
            key="temperature_antifrost",
            translation_key="temperature_antifrost",
            out_suffix="temperature_antifrost/out",
            in_suffix="temperature_antifrost/in",
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
