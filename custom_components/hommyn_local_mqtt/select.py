from __future__ import annotations

from typing import TYPE_CHECKING, override

from homeassistant.components.select import SelectEntity

from .const import (
    MODE_OPTIONS,
    POWER_MODE_OPTIONS,
    POWER_OPTIONS,
    TOPIC_MODE,
    TOPIC_POWER,
    TOPIC_POWER_MODE,
)
from .entity import HommynMqttEntity, HommynTopic
from .helpers import int_payload

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

SPECS = [
    (
        HommynTopic(
            key="mode",
            out_suffix=TOPIC_MODE,
            in_suffix=TOPIC_MODE,
        ),
        MODE_OPTIONS,
    ),
    (
        HommynTopic(
            key="power",
            out_suffix=TOPIC_POWER,
            in_suffix=TOPIC_POWER,
        ),
        POWER_OPTIONS,
    ),
    (
        HommynTopic(
            key="power_mode",
            out_suffix=TOPIC_POWER_MODE,
            in_suffix=TOPIC_POWER_MODE,
        ),
        POWER_MODE_OPTIONS,
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
        self._attr_options = value_map
        self._attr_current_option = None

    @override
    def _handle_payload(self, payload: str) -> None:
        value = int_payload(payload)
        if value is not None:
            self._attr_current_option = str(value)

    @override
    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        await self._publish(option)
        self.async_write_ha_state()
