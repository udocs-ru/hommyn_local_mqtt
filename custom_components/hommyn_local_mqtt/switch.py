from __future__ import annotations

from typing import TYPE_CHECKING, override

from homeassistant.components.switch import SwitchEntity

from .const import (
    TOPIC_BACKLIGHT,
    TOPIC_BACKLIGHT_AUTO,
    TOPIC_CHILD_LOCK,
    TOPIC_HALF_POWER,
    TOPIC_OPEN_WINDOW,
    TOPIC_SOUND,
    TOPIC_TIMER,
)
from .entity import HommynMqttEntity, HommynTopic
from .helpers import int_payload

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


SPECS = [
    HommynTopic(
        key="swing",
        out_suffix=TOPIC_BACKLIGHT_AUTO,
        in_suffix=TOPIC_BACKLIGHT_AUTO,
    ),
    HommynTopic(
        key="timer",
        out_suffix=TOPIC_TIMER,
        in_suffix=TOPIC_TIMER,
        is_enabled=False,
    ),
    HommynTopic(
        key="child_lock",
        out_suffix=TOPIC_CHILD_LOCK,
        in_suffix=TOPIC_CHILD_LOCK,
        is_enabled=False,
    ),
    HommynTopic(
        key="sound",
        out_suffix=TOPIC_SOUND,
        in_suffix=TOPIC_SOUND,
        is_enabled=False,
    ),
    HommynTopic(
        key="backlight",
        out_suffix=TOPIC_BACKLIGHT,
        in_suffix=TOPIC_BACKLIGHT,
    ),
    HommynTopic(
        key="open_window",
        out_suffix=TOPIC_OPEN_WINDOW,
        in_suffix=TOPIC_OPEN_WINDOW,
        is_enabled=False,
    ),
    HommynTopic(
        key="half_power",
        out_suffix=TOPIC_HALF_POWER,
        in_suffix=TOPIC_HALF_POWER,
        is_enabled=False,
    ),
]


async def async_setup_entry(
    _hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([HommynSwitch(entry, spec) for spec in SPECS])


class HommynSwitch(HommynMqttEntity, SwitchEntity):
    def __init__(self, entry: ConfigEntry, spec: HommynTopic) -> None:
        super().__init__(entry, spec)
        self._attr_is_on = None

    @override
    def _handle_payload(self, payload: str) -> None:
        value = int_payload(payload)
        if value is not None:
            self._attr_is_on = value == 1

    @override
    async def async_turn_on(self, **kwargs: dict[str, object]) -> None:
        await self._publish("1")

    @override
    async def async_turn_off(self, **kwargs: dict[str, object]) -> None:
        await self._publish("0")
