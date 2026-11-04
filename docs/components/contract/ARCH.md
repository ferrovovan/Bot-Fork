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

Где инварианты живут (файл и строки) — [INTERNAL.md](INTERNAL.md).

## Запреты

- Платформенные классы и сырые строки API внутри типов: сцены перестают
  переноситься TG↔VK.
- Молчаливое сглаживание значений вне лимитов: нарушение вскрывается на
  построении, а не при отправке.
- Хранение в `UserSession.data` чего-либо кроме строк без решения комнаты
  (F-03 открыт).

## Чем проверяется

`tests/test_models.py` — типы и лимиты; `tests/test_media.py` — валидация
`Attachment`; `tests/test_actions.py` — `Reject`. Число тестов — [INTERNAL.md](INTERNAL.md).
