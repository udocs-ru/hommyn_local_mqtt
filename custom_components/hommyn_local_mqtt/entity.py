"""Common entity helpers for Hommyn local MQTT."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast, override

from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
from .const import CONF_TOPIC_PREFIX, DOMAIN


@dataclass(frozen=True)
class HommynTopic:
    key: str
    out_suffix: str
    in_suffix: str | None = None
    is_enabled: bool = True
    name: str | None = None
    translation_key: str | None = None


# Тип для функции отписки от MQTT
type UnsubscribeType = Callable[[], None]


class HommynMqttEntity(Entity):
    _attr_has_entity_name: bool = True

    _entry: ConfigEntry
    _spec: HommynTopic
    _prefix: str
    _unsub: UnsubscribeType | None

    def __init__(self, entry: ConfigEntry, spec: HommynTopic) -> None:
        super().__init__()

        self._entry = entry
        self._spec = spec

        # Префикс топика устройства
        self._prefix = cast(str, entry.data[CONF_TOPIC_PREFIX]).strip("/")

        self._device_name: str = f"Hommyn {self._prefix}"
        self._attr_unique_id = f"{DOMAIN}_{self._prefix}_{spec.key}"
        self._attr_entity_registry_enabled_default = spec.is_enabled

        if spec.name is not None:
            self._attr_name = spec.name

        if spec.translation_key is not None:
            self.translation_key = spec.translation_key
        else:
            self.translation_key = spec.key

        # Информация об устройстве
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._prefix)},
            manufacturer="Hommyn",
            name=self._device_name,
        )

        self._unsub = None

    @property
    def out_topic(self) -> str:
        """Топик для получения состояния от устройства."""
        return f"{self._prefix}/{self._spec.out_suffix}/out"

    @property
    def in_topic(self) -> str | None:
        """Топик для отправки команд устройству."""
        if self._spec.in_suffix is None:
            return None
        return f"{self._prefix}/{self._spec.in_suffix}/in"

    @override
    async def async_added_to_hass(self) -> None:
        """Подписываемся на MQTT топик состояния."""
        self._unsub = await mqtt.async_subscribe(
            self.hass, self.out_topic, self._message_received, 1
        )

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Отписываемся от MQTT при удалении."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def _message_received(self, msg: mqtt.ReceiveMessage) -> None:
        """Обработчик входящих MQTT сообщений."""
        # Преобразуем payload в строку
        if isinstance(msg.payload, bytes):
            payload_str: str = msg.payload.decode()
        else:
            payload_str = str(msg.payload)
        self._handle_payload(payload_str)
        self.async_write_ha_state()

    def _handle_payload(self, _payload: str) -> None:
        """Обработка payload. Должен быть переопределён в дочернем классе."""
        raise NotImplementedError

    async def _publish(self, payload: str) -> None:
        """Публикация сообщения в топик."""
        topic = self.in_topic
        if topic is None:
            return
        await mqtt.async_publish(self.hass, topic, payload, 1, False)
