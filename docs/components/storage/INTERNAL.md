# storage/INTERNAL.md — Internal Arch: как хранилища устроены сейчас

**Компонент:** `bot_fork/storage.py`, `bot_fork/sql_storage.py` · **Снимок:**
2026-11-04, HEAD `c386469` (1.12.1) · **Правит:** координатор (пакеты движка)

## Карта файлов

| Файл | Что внутри | Строк |
|---|---|---|
| `bot_fork/storage.py` | `StateStorage` (ABC) с факультативным `list_scene`, `MemoryStateStorage` | 87 |
| `bot_fork/sql_storage.py` | `SqlStateStorage`: разбор DSN, схема v2 + миграция v1→v2, sync-операции в потоке | 258 |

Итого 2 файла, 345 строк.

## Ключевые решения (и почему так)

| Решение | Зачем | Где |
|---|---|---|
| Memory отдаёт `clone()` на get и на set | ни один вызывающий не мутирует состояние хранилища на месте | `storage.py:51-64`, `models.py:216-223` |
| Один `asyncio.Lock` на всё хранилище | проще per-key, а конфликт редок на масштабе сессий | `storage.py:49,57-64`, `sql_storage.py:59` |
| DBAPI через `asyncio.to_thread` | синхронный `sqlite3` не блокирует событийный цикл | `sql_storage.py:225-251` |
| Одно соединение на инстанс (`check_same_thread=False`) + лок; `connection_factory` — выбор продукта (PG) | sqlite не любит потоки; продукт уносит бэкенд без правки движка | `sql_storage.py:45-62` |
| Схема v2 с дорожкой; миграция пересозданием таблицы (SQLite не умеет менять PK) | F-06 без потери старых баз, строки v1 едут в `lane='user'` | `sql_storage.py:64-97` |
| `INSERT … ON CONFLICT DO UPDATE` — upsert | `set` идемпотентен, гонка на одном PK безопасна | `sql_storage.py:152-157` |
| Разбор DSN (`sqlite:///`, `sqlite+aiosqlite://`, 4-слэша, `:memory:`) | первый запуск продукта споткнулся о SQLAlchemy-стиль пути — фикс v1.8.1 | `sql_storage.py:25-34` |
| `data` — JSON-текст с `ensure_ascii=False`, значения принудительно `str()` | читаемый дамп; контракт `Dict[str, str]` соблюдён | `sql_storage.py:161-170` |
| Битый `updated_at` → текущее время; битый JSON `data` → `StorageError` | штамп времени не повод ронять диалог, данные — повод | `sql_storage.py:131-139` |

## Ограничения и долги

| `файл:строка` | Суть / как воспроизвести | Тяжесть | Решение | Метка |
|---|---|---|---|---|
| `storage.py:15-37` | `count()` есть у обеих реализаций, но не в порту; `close()` — только у Sql: продукт, принявший «любой StateStorage», спотыкается | низкая | расширить порт (прибавка API — патч) | — |
| `storage.py:74-87`, `sql_storage.py:195-221` | семантика clone-на-get прямого теста не имеет (`test_get_set_clear` её не проверяет); `list_scene` — полный обход без фильтра по дорожке | низкая | точечные тесты; индекс — за продуктом на PG | — |
| `sql_storage.py:118-146` | испорченный `data` одной сессии валит `get` именно её — диалог этого чата умирает честно, но жестко | низкая | признать контрактом | — |

## Как гонять тесты компонента

```bash
python3 -m pytest tests/test_storage.py tests/test_sql_storage.py \
    tests/test_lanes.py tests/test_stress_100_sessions.py -q
python3 -m pytest tests -q        # база: 158 passed
```

## Владелец и правила обновления

- Владелец — координатор; изменение схемы — только со строкой миграции и тестом;
  сдвиг PK — через RfI.
