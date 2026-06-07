from __future__ import annotations

from typing import TYPE_CHECKING, override

from homeassistant.components.select import SelectEntity

from .const import BACKLIGHT_OPTIONS, MODE_OPTIONS, POWER_MODE_OPTIONS
from .entity import HommynMqttEntity, HommynTopic, int_payload

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

SPECS = [
    (
        HommynTopic(
            key="mode",
            translation_key="mode",
            out_suffix="mode/out",
            in_suffix="mode/in",
        ),
        MODE_OPTIONS,
    ),
    (
        HommynTopic(
            key="power_mode",
            translation_key="power_mode",
            out_suffix="power_mode/out",
            in_suffix="power_mode/in",
        ),
        POWER_MODE_OPTIONS,
    ),
    (
        HommynTopic(
            key="backlight",
            translation_key="backlight",
            out_suffix="backlight/out",
            in_suffix="backlight/in",
        ),
        BACKLIGHT_OPTIONS,
    ),
]


async def async_setup_entry(
    _hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([HommynSelect(entry, spec, options) for spec, options in SPECS])


class HommynSelect(HommynMqttEntity, SelectEntity):
    def __init__(
        self, entry: ConfigEntry, spec: HommynTopic, value_map: list[str]
    ) -> None:
        super().__init__(entry, spec)
        # self._value_map = value_map
        # self._reverse_map = {label: value for value, label in value_map.items()}
        self._attr_options = value_map
        self._attr_current_option = None

    @override
    def _handle_payload(self, payload: str) -> None:
        value = int_payload(payload)
        if value is not None:
            self._attr_current_option = str(value)

    @override
    async def async_select_option(self, option: str) -> None:
        # value = self._reverse_map[option]
        self._attr_current_option = option
        await self._publish(option)
        self.async_write_ha_state()
