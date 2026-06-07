"""Config flow for Hommyn local MQTT."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import cast, override

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant

from .const import CONF_TOPIC_PREFIX, DOMAIN, STATE_SUFFIXES

UnsubscribeType = Callable[[], None]
MessageHandlerType = Callable[[mqtt.ReceiveMessage], None]


async def discover_topic_prefixes(
    hass: HomeAssistant, timeout: float = 8.0
) -> list[str]:
    """
    Подписываем на топики из STATE_SUFFIXES и возвращает найденные префиксы.
    Для каждого суффикса создается wildcard подписка, например: '+/sensor/temperature/out'.
    Сам топик обычно выглядит так '983daeb6d468/sensor/temperature/out', если что-то пришло,
    то отрезаем префикс и записываем в discovered и спустя таймаут 8 сек возвращаем массив префиксов.
    """

    discovered: set[str] = set()
    unsubscribers: list[UnsubscribeType] = []

    def create_handler(suffix: str) -> MessageHandlerType:
        def message_handler(msg: mqtt.ReceiveMessage) -> None:
            topic: str = msg.topic
            expected: str = f"/{suffix}"
            if topic.endswith(expected):
                prefix: str = topic[: -len(expected)].strip("/")
                if prefix:
                    discovered.add(prefix)

        return message_handler

    try:
        for suffix in STATE_SUFFIXES:
            wildcard: str = f"+/{suffix}"
            qos: int = 1
            unsubscribe: UnsubscribeType = await mqtt.async_subscribe(
                hass, wildcard, create_handler(suffix), qos
            )
            unsubscribers.append(unsubscribe)
        await asyncio.sleep(timeout)
    finally:
        for unsubscribe in unsubscribers:
            unsubscribe()
    return sorted(discovered)


class HommynLocalMqttConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hommyn local MQTT."""

    VERSION: int = 1

    def __init__(self) -> None:
        super().__init__()
        self._discovered_prefixes: list[str] = []  # список найденных префиксов
        self._discovery_done: bool = False  # флаг о том что поиск уже был выполнен

    @override
    async def async_step_user(
        self, user_input: dict[str, object] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        # проверяем доступность mqtt. если недоступно, то показываем ошибку
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            return self.async_abort(reason="mqtt_not_configured")

        # запускаем поиск префиксов в mqtt
        if not self._discovery_done:
            self._discovered_prefixes = await discover_topic_prefixes(self.hass)
            self._discovery_done = True

        # список ранее настроенных записей
        existing_entries = self._async_current_entries()
        existing_prefixes: set[str] = set()  # Создаём пустое множество

        for entry in existing_entries:
            if CONF_TOPIC_PREFIX in entry.data:
                prefix = cast(str, entry.data.get(CONF_TOPIC_PREFIX, ""))
                existing_prefixes.add(prefix)

        # фльтр префиксов, которых нет в existing_prefixes
        available_prefixes: list[str] = [
            prefix
            for prefix in self._discovered_prefixes
            if prefix not in existing_prefixes
        ]

        ## обработка отправленной формы
        if user_input is not None:
            # проверяем есть ли выбранный префикс
            if CONF_TOPIC_PREFIX not in user_input:
                errors["base"] = "no_topic_selected"
                return self.async_show_form(
                    step_id="user", data_schema=vol.Schema({}), errors=errors
                )

            topic_prefix: str = cast(str, user_input[CONF_TOPIC_PREFIX])

            # сохраняем префикс
            _ = await self.async_set_unique_id(topic_prefix)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Hommyn {topic_prefix}", data={CONF_TOPIC_PREFIX: topic_prefix}
            )

        # показ формы
        ## нет новых префиксов
        if not available_prefixes and self._discovered_prefixes:
            return self.async_abort(reason="all_configured")

        ## ничего не нашли
        if not self._discovered_prefixes:
            return self.async_abort(reason="no_device_found")

        ## показываем список доступных префиксов
        schema = vol.Schema(
            {vol.Required(CONF_TOPIC_PREFIX): vol.In(available_prefixes)}
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
