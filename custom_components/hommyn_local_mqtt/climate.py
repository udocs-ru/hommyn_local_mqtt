from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast, override

from homeassistant.components import mqtt
from homeassistant.components.climate import (
    ClimateEntity,
)
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import callback

from .const import (
    TOPIC_CURRENT_TEMPERATURE,
    TOPIC_MODE,
    TOPIC_POWER,
    TOPIC_TEMPERATURE_COMFORT,
)
from .entity import HommynMqttEntity, HommynTopic, UnsubscribeType
from .helpers import float_payload, int_payload

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


# Маппинг HVACMode -> код устройства
HVAC_TO_CODE = {
    HVACMode.OFF: "0",
    HVACMode.AUTO: "1",
    HVACMode.COOL: "2",
    HVACMode.DRY: "3",
    HVACMode.HEAT: "4",
    HVACMode.FAN_ONLY: "5",
}

# Маппинг кода устройства -> HVACMode
CODE_TO_HVAC = {v: k for k, v in HVAC_TO_CODE.items()}

SPECS = {
    "mode": HommynTopic(
        key="mode",
        out_suffix=TOPIC_MODE,
        in_suffix=TOPIC_MODE,
    ),
    "power": HommynTopic(
        key="power",
        out_suffix=TOPIC_POWER,
        in_suffix=TOPIC_POWER,
    ),
    "temperature_comfort": HommynTopic(
        key="temperature_comfort",
        out_suffix=TOPIC_TEMPERATURE_COMFORT,
        in_suffix=TOPIC_TEMPERATURE_COMFORT,
    ),
    "current_temperature": HommynTopic(
        key="current_temperature",
        out_suffix=TOPIC_CURRENT_TEMPERATURE,
    ),
}


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([HommynClimate(entry)])


class HommynClimate(HommynMqttEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1.0
    _attr_min_temp = 16.0
    _attr_max_temp = 32.0

    _attr_hvac_modes = list(HVAC_TO_CODE.keys())
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    _unsub_additional: list[UnsubscribeType]

    def __init__(self, entry: ConfigEntry) -> None:
        """Инициализация климат-сущности."""
        # Используем mode топик как основной для родительского класса
        super().__init__(entry, SPECS["mode"])

        self._attr_fan_modes = ["auto", "low", "medium", "high", "turbo"]
        self._attr_fan_mode = "auto"
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._attr_hvac_mode = HVACMode.OFF

        self._unsub_additional = list()

    @override
    async def async_added_to_hass(self) -> None:
        """Подписка на все MQTT топики."""
        # Подписка родителя (на mode топик)
        await super().async_added_to_hass()

        # подписки на дополнительные топики

        # скорость вентилятора
        self._unsub_additional.append(
            await mqtt.async_subscribe(
                self.hass,
                self.buildTopic(SPECS["power"].out_suffix, "out"),
                self._on_fan_message,
                1,
            )
        )

        # текущая температура
        self._unsub_additional.append(
            await mqtt.async_subscribe(
                self.hass,
                self.buildTopic(SPECS["current_temperature"].out_suffix, "out"),
                self._on_current_temperature,
                1,
            )
        )

        # целевая температура
        self._unsub_additional.append(
            await mqtt.async_subscribe(
                self.hass,
                self.buildTopic(SPECS["temperature_comfort"].out_suffix, "out"),
                self._on_target_temperature,
                1,
            )
        )

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Отписка от всех топиков"""
        for unsub in self._unsub_additional:
            unsub()

        self._unsub_additional.clear()
        await super().async_will_remove_from_hass()

    @override
    def _handle_payload(self, payload: str) -> None:
        """Обработка режима работы (из родительского класс)"""
        code = int_payload(payload)
        if code is not None:
            mode = CODE_TO_HVAC.get(str(code))
            if mode is not None:
                self._attr_hvac_mode = mode
                self.async_write_ha_state()

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:  # pyright: ignore[reportExplicitAny]
        """Установка целевой температуры."""
        temperature = cast(float | None, kwargs.get(ATTR_TEMPERATURE))
        if temperature is not None:
            topic = self.buildTopic(SPECS["temperature_comfort"].in_suffix, "in")
            await mqtt.async_publish(self.hass, topic, str(int(temperature)), 1, False)

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Установка режима работы."""
        code = HVAC_TO_CODE.get(hvac_mode)
        if code is None:
            return
        self._attr_hvac_mode = hvac_mode
        topic = self.in_topic  # from parent (mode/in)
        if topic:
            await mqtt.async_publish(self.hass, topic, code, 1, False)

    @override
    async def async_turn_on(self) -> None:
        """Включение."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    @override
    async def async_turn_off(self) -> None:
        """Выключение."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    @callback
    def _on_fan_message(self, msg: mqtt.ReceiveMessage) -> None:
        """Обработчик скорости вентилятора."""
        payload = (
            msg.payload.decode() if isinstance(msg.payload, bytes) else str(msg.payload)
        )

        # Маппинг кодов из POWER_OPTIONS в fan_modes
        fan_map = {
            "0": "auto",
            "1": "low",
            "2": "medium",
            "3": "high",
            "4": "turbo",
        }
        mode = fan_map.get(payload)
        if mode:
            self._attr_fan_mode = mode
            self.async_write_ha_state()

    @override
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Установка скорости вентилятора."""
        # Обратный маппинг
        fan_map = {
            "auto": "0",
            "low": "1",
            "medium": "2",
            "high": "3",
            "turbo": "4",
        }
        code = fan_map.get(fan_mode)
        if code:
            topic = self.buildTopic(SPECS["power"].in_suffix, "in")
            await mqtt.async_publish(self.hass, topic, code, 1, False)

    @callback
    def _on_current_temperature(self, msg: mqtt.ReceiveMessage) -> None:
        """Обработчик текущей температуры"""
        if isinstance(msg.payload, bytes):
            payload: str = msg.payload.decode("utf-8")
        else:
            payload = str(msg.payload)

        value = float_payload(payload)
        if value is not None:
            self._attr_current_temperature = round(value, 6)
            self.async_write_ha_state()

    @callback
    def _on_target_temperature(self, msg: mqtt.ReceiveMessage) -> None:
        """Обработчик целевой температуры"""
        if isinstance(msg.payload, bytes):
            payload: str = msg.payload.decode("utf-8")
        else:
            payload = str(msg.payload)

        value = float_payload(payload)
        if value is not None:
            self._attr_target_temperature = round(value, 6)
            self.async_write_ha_state()

    def buildTopic(self, entity: str | None, dir: str) -> str:
        """хелпер сборки топика"""
        return f"{self._prefix}/{entity}/{dir}"
