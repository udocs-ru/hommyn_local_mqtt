[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/udocs-ru/hommyn_local_mqtt)](https://github.com/udocs-ru/hommyn_local_mqtt/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-compatible-blue.svg)](https://www.home-assistant.io/)
[![License](https://img.shields.io/github/license/udocs-ru/hommyn_local_mqtt.svg)](https://github.com/udocs-ru/hommyn_local_mqtt/blob/main/LICENSE)

# Hommyn local MQTT

Интеграция Home Assistant для управления устройствами с помощью стика Hommyn (Русклимат) через кастомный MQTT сервер.

> [!WARNING]
> Данная интеграция предназначена для работы с устройствами Hommyn в которых через настройки в официальном приложении указан кастомный MQTT сервер!
> Если вы перенаправляете трафик с `mqtt.cloud.rusklimat.ru` на свой MQTT сервер, то вам нужно использовать другую интеграцию: [polaris-mqtt](https://github.com/samoswall/polaris-mqtt)
>
> Структура топиков и сообщений в этих двух реализация совершенно разная!

## Установка

### Через HACS

[![Открыть в Home Assistant и установить Hommyn local MQTT через HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=udocs-ru&repository=hommyn_local_mqtt&category=integration)

Если кнопка не работает: добавьте репозиторий в HACS вручную (категория: Интеграция), установите "Hommyn local MQTT" и перезапустите Home Assistant.

### Вручную (без HACS)

1. Скопируйте папку `custom_components/hommyn_local_mqtt/` в директорию `config/custom_components/` вашего HA
2. Перезапустите Home Assistant

## Добавление устройства

Если на устройстве корректно указан MQTT сервер, то обычно в течении нескольких секунд после установки интеграции на странице **Настройка** / **Устройства и службы** оно будет обнаружено.
Для ручного добавления перейдите в **Настройка** / **Устройства и службы**, нажмите **Добавить интеграцию** и в поиске найдите и выберите **Hommyn local MQTT**.

Если не получается обнаружить устройство попробуйте с помощью пульта включить устройство, изменить температуру или режим работы и попробуйте снова.
