# docs/components — модульная документация 9 компонентов движка

> Три поля документации (норма — TEAMWINNING `structure/02-перенос-документации.md`,
> решение — `Room_for_Improvement/decisions/D-12.md`, заказ — D2):
> **ARCH.md** — норма «как должно быть» (правит совет архитекторов),
> **INTERNAL.md** — факт «как устроено сейчас» (обновляется в том же коммите, что код),
> **TODO-ARCH.md** — очередь местных долгов. Общая очередь движка —
> [docs/TODO-ARCH.md](../TODO-ARCH.md), хроника — [docs/History.md](../History.md).

**Снимок:** 2026-11-04, HEAD `c386469` (серия 1.12.x) · **Пакет:** п46 (D2.1)

## Порядок чтения

Корневой `README.md` → этот индекс → `ARCH.md` компонента → `TODO-ARCH.md` →
`INTERNAL.md`. ARCH читают до задачи, INTERNAL — во время задачи.

## Компоненты

| Компонент | Код | Держит |
|---|---|---|
| [contract](contract/ARCH.md) · [факт](contract/INTERNAL.md) · [очередь](contract/TODO-ARCH.md) | `bot_fork/models.py`, `exceptions.py` | Типы, лимиты, иерархия исключений |
| [scenes](scenes/ARCH.md) · [факт](scenes/INTERNAL.md) · [очередь](scenes/TODO-ARCH.md) | `bot_fork/scene.py`, `builder.py` | Шаги, сцены, валидация сборки сценария |
| [fsm](fsm/ARCH.md) · [факт](fsm/INTERNAL.md) · [очередь](fsm/TODO-ARCH.md) | `bot_fork/fsm.py` | Исполнение шага, действия, завершение сцены |
| [router](router/ARCH.md) · [факт](router/INTERNAL.md) · [очередь](router/TODO-ARCH.md) | `bot_fork/router.py` | Диспетч, реестр сцен, дорожки, отмена |
| [app](app/ARCH.md) · [факт](app/INTERNAL.md) · [очередь](app/TODO-ARCH.md) | `bot_fork/app.py`, `__init__.py` | Сборка приложения, рантайм, публичный API |
| [storage](storage/ARCH.md) · [факт](storage/INTERNAL.md) · [очередь](storage/TODO-ARCH.md) | `bot_fork/storage.py`, `sql_storage.py` | Состояние сессий: порт, Memory, Sql |
| [adapters](adapters/ARCH.md) · [факт](adapters/INTERNAL.md) · [очередь](adapters/TODO-ARCH.md) | `bot_fork/adapters/{base,telegram,vk}.py` | Граница платформ: Telegram и VK |
| [showcase](showcase/ARCH.md) · [факт](showcase/INTERNAL.md) · [очередь](showcase/TODO-ARCH.md) | `examples/`, `scripts/`, `site/`, `web/` | Демо, страница, песочница браузера |
| [docs](docs/ARCH.md) · [факт](docs/INTERNAL.md) · [очередь](docs/TODO-ARCH.md) | `README.md`, `docs/` | Сама документация, правила версионирования |

## Соглашения

- ARCH ≤70 строк; в инвариантах нет `файл:строка` и счётчиков — факты живут в
  INTERNAL; «чем проверяется» — тесты из `tests/`, а не «на глаз».
- INTERNAL ≤90 строк: карта файлов, решения с адресами, долги (тут `файл:строка` можно).
- TODO-ARCH ≤30 строк: только долги с адресом; статусы: `ждёт пакета/RFC →
  в работе → внедрено | отказ: <причина>`.
- База: `python3 -m pytest tests -q` → **189 passed + 7 subtests** (замер 2026-11-04, п49-4).
