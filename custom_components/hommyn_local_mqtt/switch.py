from __future__ import annotations

from typing import TYPE_CHECKING, override

from homeassistant.components.switch import SwitchEntity

from .entity import HommynMqttEntity, HommynTopic, int_payload

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


SPECS = [
    HommynTopic(
        key="swing",
        translation_key="swing",
        out_suffix="backlight_auto/out",
        in_suffix="backlight_auto/in",
    ),
    HommynTopic(
        key="timer",
        translation_key="timer",
        out_suffix="timer/out",
        in_suffix="timer/in",
        is_enabled=False,
    ),
    HommynTopic(
        key="child_lock",
        translation_key="child_lock",
        out_suffix="child_lock/out",
        in_suffix="child_lock/in",
        is_enabled=False,
    ),
    HommynTopic(
        key="sound",
        translation_key="sound",
        out_suffix="sound/out",
        in_suffix="sound/in",
        is_enabled=False,
    ),
    HommynTopic(
        key="backlight",
        translation_key="backlight",
        out_suffix="backlight/out",
        in_suffix="backlight/in",
    ),
    HommynTopic(
        key="open_window",
        translation_key="open_window",
        out_suffix="open_window/out",
        in_suffix="open_window/in",
        is_enabled=False,
    ),
    HommynTopic(
        key="half_power",
        translation_key="half_power",
        out_suffix="half_power/out",
        in_suffix="half_power/in",
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
