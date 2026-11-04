# contract/ARCH.md — Code Arch: каким должен быть контракт типов

**Компонент:** `bot_fork/models.py`, `bot_fork/exceptions.py` ·
**Серия контракта:** `1.12.x` · **Правит:** совет архитекторов (метка `ARCH-CHANGE: RfI-NN`)

## Назначение

Держит: платформо-независимые типы диалога — `SessionKey` (с дорожками), `Button`,
`Reject`, `IncomingEvent`, `Attachment`, `OutgoingMessage`, `UserSession`,
`ErrorInfo`, `HandlerResult` — и иерархию исключений; отклоняет неправильные
значения при построении объекта.
Не держит: исполнение диалога, сцены, роутинг, хранение; не знает платформ. Типы
единственны до и после роутера — ядро не зависит от `aiogram`/`vkbottle` (NFR-03).

## Границы

| Можно импортировать | Нельзя импортировать |
|---|---|
| stdlib (`dataclasses`, `datetime`, `typing`) | любой модуль `bot_fork` и всё платформенное |

## Публичный контракт

- Типы: перечислены в «Назначении»; `SessionKey` хешируем, неизменяем, имеет
  `with_lane()`; `UserSession` имеет `clone()`; у всех есть `to_dict()` —
  JSON-контракт песочницы `web/` и логов.
- Исключения: корень `BotForkError`; `ConfigError`, `InvalidInputError`,
  `StorageError`, `PlatformError`/`PlatformTimeoutError`,
  `PlatformOperationNotSupported` («платформа не умеет» — не авария).
- Числа и счётчики — только в [INTERNAL.md](INTERNAL.md); контракт меняется
  только через RfI совета.

## Инварианты

1. `SessionKey`: `platform ∈ {telegram, vk}`, непустые `user_id`/`chat_id`,
   `lane ∈ {user, system}` — иначе исключение при построении.
   Проверяется: `tests/test_models.py`.
2. `Button`: label 1–40 символов, value 1–64 — `tests/test_models.py`.
3. `OutgoingMessage`: не более 4 кнопок, текст не длиннее платформенного лимита —
   `tests/test_models.py`.
4. `IncomingEvent`: текст стрижётся и ограничен лимитом;
   `event_type ∈ {message, system}`; `session_key` события всегда в дорожке
   `user` — `tests/test_models.py`.
5. `Attachment`: `kind ∈ {photo, document}`, непустые байты, имя файла
   ограничено; `to_dict()` не содержит байтов — `tests/test_media.py`.
6. `Reject`: текст обязателен непустым, кнопки факультативны (F-28) —
   `tests/test_actions.py`.
7. `HandlerResult` — атомарный ответ рантайма: сообщения, сессия после шага,
   флаг очистки, ошибка; пустой результат = молчание — `tests/test_models.py`.
8. `UserSession.data` (F-03, закрыт решением комнаты `D-18`): значения
   JSON-совместимые — `str | int | float (конечный) | bool | None | list | dict`
   (вложенно, ключи только `str`); запись иного типа — `ConfigError` при
   построении, до любого хранилища. Старый `Dict[str, str]` — валидное
   подмножество; хранилище сериализует составные значения в TEXT (JSON) и читает
   без переинтерпретации: строка-обёртка ряда v1.12 возвращается строкой
   (совместимость) — `tests/test_session_data_json.py`.
   `ARCH-CHANGE: RfI-05-1`.

Где инварианты живут (файл и строки) — [INTERNAL.md](INTERNAL.md).

## Запреты

- Платформенные классы и сырые строки API внутри типов: сцены перестают
  переноситься TG↔VK.
- Молчаливое сглаживание значений вне лимитов: нарушение вскрывается на
  построении, а не при отправке.
- Значения `UserSession.data` вне JSON-домена инварианта 8 (`set`, `datetime`,
  кортежи, произвольные объекты, NaN/Infinity): `ConfigError` на построении,
  а не сюрприз при сериализации в хранилище. Составные данные — настоящие
  `list`/`dict`, а не JSON-обёртки в строке (обёртки продукта снимает пакет D2.4).

## Чем проверяется

`tests/test_models.py` — типы и лимиты; `tests/test_media.py` — валидация
`Attachment`; `tests/test_actions.py` — `Reject`; `tests/test_session_data_json.py`
— домен значений `UserSession.data` (F-03, Memory+Sql round-trip). Число тестов —
[INTERNAL.md](INTERNAL.md).
