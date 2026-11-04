# storage/ARCH.md — Code Arch: каким должно быть хранилище состояний

**Компонент:** `bot_fork/storage.py`, `bot_fork/sql_storage.py` ·
**Серия контракта:** `1.12.x` · **Правит:** совет архитекторов (метка `ARCH-CHANGE: RfI-NN`)

## Назначение

Держит: активные сессии диалогов по ключу `SessionKey(platform, user_id, chat_id,
lane)`; порт `StateStorage` и две реализации — `MemoryStateStorage` (процесс,
тесты) и `SqlStateStorage` (stdlib `sqlite3` или произвольный DBAPI через
`connection_factory`); снимок сессий сцены (`list_scene`, F-34).
Не держит: логику диалога, TTL-очистку (это работа продукта), миграции продуктовых
таблиц.

## Границы

| Можно импортировать | Нельзя импортировать |
|---|---|
| stdlib (`asyncio`, `json`, `sqlite3`, `abc`); `models`, `exceptions` | `router`, `fsm`, `app`, адаптеры, ORM |

SQL собирается только из констант и параметров; разбор DSN — собственная логика,
сторонние URL-парсеры не нужны.

## Публичный контракт

- **`StateStorage`** (ABC): `get(key)`, `set(session)`, `clear(key)`;
  факультативно (не абстрактный): `list_scene(scene_id)` — база отдаёт пустой список.
- **`MemoryStateStorage`**: `count()`; **`SqlStateStorage(dsn, connection_factory?)`**:
  `count()`, `close()` — вне порта, факт, а не контракт (см. INTERNAL).
- Все методы async; синхронный DBAPI прячется в поток.

## Инварианты

1. Ключ составной, с дорожкой: разные платформы, чаты и дорожки — разные сессии;
   ≥100 параллельных сессий изолированы (NFR-01). Проверяется:
   `tests/test_storage.py`, `tests/test_sql_storage.py`, `tests/test_stress_100_sessions.py`.
2. `clear` идемпотентен; чужой тип ключа — `StorageError` — `tests/test_storage.py`.
3. Sql: round-trip, upsert по повторному ключу, переживание переподключения,
   конкурентные записи — `tests/test_sql_storage.py`.
4. Схема v2: PK `(platform, user_id, chat_id, lane)`; таблица v1 мигрируется
   автоматически, строки получают `lane='user'` (F-06) — `tests/test_lanes.py`.
5. Формы DSN (`sqlite:///…`, `sqlite+aiosqlite://…`, голый путь, `:memory:`)
   равносильны — `tests/test_sql_storage.py`.
6. `list_scene`: базовый порт — пустой список (возможность, не обязанность);
   Memory и Sql отдают снимок сессий, ключ из снимка пригоден для `clear` (F-34) —
   `tests/test_storage.py`, `tests/test_sql_storage.py`.
7. Значения `data` переживают round-trip как строки; битый JSON в хранимой строке —
   `StorageError`, а не половина сессии.

Где это лежит — [INTERNAL.md](INTERNAL.md).

## Запреты

- Синхронные вызовы DBAPI в событийном цикле — только поток под лока.
- Хранение чего-либо, кроме сессий (продуктовые таблицы — продукт).
- Молчаливое игнорирование испорченных данных.

## Чем проверяется

`tests/test_storage.py` (4), `tests/test_sql_storage.py` (13),
`tests/test_lanes.py` (миграция схемы и дорожки), `tests/test_stress_100_sessions.py` (1).
Число — [INTERNAL.md](INTERNAL.md).
