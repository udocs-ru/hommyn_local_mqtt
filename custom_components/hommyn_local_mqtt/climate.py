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

from .entity import (
    HommynMqttEntity,
    HommynTopic,
    UnsubscribeType,
    float_payload,
    int_payload,
)

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

# Описание топиков для климата
CLIMATE_TOPICS = {
    "mode": HommynTopic(
        key="mode",
        out_suffix="mode/out",
        in_suffix="mode/in",
        translation_key="mode",
    ),
    "temperature_comfort": HommynTopic(
        key="temperature_comfort",
        out_suffix="temperature_comfort/out",
        in_suffix="temperature_comfort/in",
        translation_key="temperature_comfort",
    ),
    "current_temperature": HommynTopic(
        key="current_temperature",
        out_suffix="sensor/temperature/out",
        translation_key="current_temperature",
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
    _attr_max_temp = 30.0

    _attr_hvac_modes = list(HVAC_TO_CODE.keys())
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    _unsub_current_temp: UnsubscribeType | None
    _unsub_target_temp: UnsubscribeType | None

    def __init__(self, entry: ConfigEntry) -> None:
        """Инициализация климат-сущности."""
        # Используем mode топик как основной для родительского класса
        super().__init__(entry, CLIMATE_TOPICS["mode"])

        # Состояния
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._attr_hvac_mode = HVACMode.OFF

        # Подписки на дополнительные топики
        self._unsub_current_temp = None
        self._unsub_target_temp = None

    @override
    async def async_added_to_hass(self) -> None:
        """Подписка на все MQTT топики."""
        # Подписка родителя (на mode топик)
        await super().async_added_to_hass()

        # Подписка на текущую температуру
        topic_current = (
            f"{self._prefix}/{CLIMATE_TOPICS['current_temperature'].out_suffix}"
        )
        self._unsub_current_temp = await mqtt.async_subscribe(
            self.hass, topic_current, self._on_current_temperature, 1
        )

        # Подписк на целевую температуру
        topic_target = (
            f"{self._prefix}/{CLIMATE_TOPICS['temperature_comfort'].out_suffix}"
        )
        self._unsub_target_temp = await mqtt.async_subscribe(
            self.hass, topic_target, self._on_target_temperature, 1
        )

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Отписка от всех топиков"""
        for unsub in [self._unsub_current_temp, self._unsub_target_temp]:
            if unsub:
                unsub()
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
            topic = f"{self._prefix}/{CLIMATE_TOPICS['temperature_comfort'].in_suffix}"
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
