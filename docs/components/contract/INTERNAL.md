# contract/INTERNAL.md — Internal Arch: как контракт типов устроен сейчас

**Компонент:** `bot_fork/models.py`, `bot_fork/exceptions.py` · **Снимок:**
2026-11-04, HEAD `c386469` (1.12.1) · **Правит:** координатор (пакеты движка)

## Карта файлов

| Файл | Что внутри | Строк |
|---|---|---|
| `bot_fork/models.py` | `SessionKey`, `Button`, `Reject`, `IncomingEvent`, `Attachment`, `OutgoingMessage`, `UserSession`, `ErrorInfo`, `HandlerResult` | 268 |
| `bot_fork/exceptions.py` | корень `BotForkError` + 5 потомков | 41 |

Итого 2 файла, 309 строк. Сюита компонента: `test_models.py` (6), `test_media.py`
(9, из них 3 про валидацию `Attachment`), `test_actions.py::test_reject_requires_text`.

## Ключевые решения (и почему так)

| Решение | Зачем | Где |
|---|---|---|
| `SessionKey` — frozen dataclass, хешируемый | ключ словаря хранилища используется как есть (`storage.py:48`); дорожка — часть ключа (F-06) | `models.py:13-48` |
| `lane` внутри ключа + `with_lane()` | системная сцена перехватывает чат, не затаптывая пользовательскую сессию | `models.py:18-26,38-40` |
| Проверки лимитов в `__post_init__` | битый объект невозможно построить; ошибка указывает на место создания | `models.py:28-36,59-63,109-122,158-166,188-193` |
| `IncomingEvent.text` стрижётся в `__post_init__` | пробельные хвосты не попадают ни в валидаторы, ни в проверку пустоты | `models.py:118-122` |
| `Attachment.to_dict()` отдаёт размер, не байты | логи и песочница `web/` не разрастаются | `models.py:168-174` |
| `UserSession.clone()` копирует словарь `data` | наружу всегда копия: вызывающий не мутирует состояние на месте | `models.py:216-223` |
| `Reject(text, buttons)` — отдельный тип (F-28) | отказ отличим от успеха с пустым ответом | `models.py:69-83` |
| `event_type`/`system_kind` (F-13) | сервисные события групп не будят диалог | `models.py:101-107` |
| `PlatformOperationNotSupported` — потомок `PlatformError` | «не умеет» отличается от «сломалось», но ловится одним except | `exceptions.py:26-36` |

## Ограничения и долги

| `файл:строка` | Суть / как воспроизвести | Тяжесть | Решение | Метка |
|---|---|---|---|---|
| `models.py:213` | `UserSession.data` — `Dict[str, str]`; продукт хранит JSON строкой (F-03) | высокая | типизация данных сессии — решение комнаты | `RfI-candidate` |
| `models.py:59-63` против `builder.py:23-30` | одни лимиты `Button`: `ValueError` при прямом построении, `ConfigError` из `ButtonBuilder` | низкая | согласовать классы исключений | — |
| `models.py:109-122` | `IncomingEvent` изменяем, `text` правится после построения (иначе стрижка невозможна) | низкая | frozen + фабрика — позже | — |

## Как гонять тесты компонента

```bash
python3 -m pytest tests/test_models.py tests/test_media.py -q
python3 -m pytest tests -q          # полная база: 158 passed
```

## Владелец и правила обновления

- Владелец — координатор; правка кода компонента без строки здесь — неполный пакет.
- Числа сверять перечитыванием кода и прогоном, а не «по памяти».
