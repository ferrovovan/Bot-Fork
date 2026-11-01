# Bot Fork (Версия 1.0)

**Встраиваемая Python-библиотека прототипирования диалоговых сцен для Telegram и ВКонтакте.**

Разработчик описывает диалоговую логику (сцены, шаги, валидаторы, ветвления и кнопки) один раз на чистом Python без платформенных зависимостей, и запускает бота в **Telegram** или **ВКонтакте**, меняя только конфигурацию окружения.

---

## ⚡ Особенности архитектуры v1.0

- **Единый диалоговый FSM-контракт**: `Scene`, `Step`, `Button`, `DialogRouter`, `FSMEngine`.
- **Изоляция ядра (NFR-03)**: Ядро не зависит от `aiogram` и `vkbottle`. Платформенные классы не попадают в сценарии.
- **Одноплатформенный запуск на процесс**: За один запуск активен ровно один адаптер (`ENABLED_PLATFORMS=telegram` или `ENABLED_PLATFORMS=vk`). Попытка одновременного запуска вызывает `ConfigError`.
- **Чистый вывод без проприетарных подписей**: Сообщения доставляются в чистом виде от имени вашего бота без навязчивых водяных знаков, с валидацией лимита 4096 символов.
- **In-Memory хранилище состояний**: `MemoryStateStorage` изолирует до 100+ параллельных сессий по составному ключу `SessionKey(platform, user_id, chat_id)`.
- **Высокая производительность (NFR-01)**: Среднее время обработки входящего события < 0.1 мс (бенчмарк 100 сессий проходит за ~6 мс при лимите 1.0 с).
- **Свободная лицензия**: Apache-2.0.

### Хроника расширений (fork roadmap)

- **v1.1** — прикладной рантайм: `app.send` (F-11), async-валидаторы и `Step.action` (F-04),
  `SqlStateStorage` (F-02/03), дедупликация событий (F-18), хук `on_error` (F-20), брендинг-флаг (F-16).
- **v1.2** — вложения `Attachment` в `OutgoingMessage` (F-01, TG photo/doc, VK upload), `content_type`
  события (F-21).
- **v1.3** — запуск сцены из кнопки: payload `scene:<id>` (F-23); контекст сессии в `action(value, data, session)` (F-04).
- **v1.4** — групповые чаты (WP3): `chat_type` и `event_type/system_kind` в `IncomingEvent` (F-13),
  хук `on_system_event` (служебные события не будят диалог), операции адаптеров
  `create_chat`/`add_member`/`remove_member`/`get_invite_link` (F-13) и `send_ex`/`edit_message` (F-19).
  VK умеет всё; Telegram — план Б: `create_chat`/`add_member` бросают `PlatformOperationNotSupported`
  (чат создаёт админ, бот раздаёт `get_invite_link`).
- **v1.5** — полосы диалога и программный вход (WP4, готовим Фазу 2): `SessionKey.lane`
  («user»|«system»), `SceneDefinition.lane` — подтверждение слота перехватывает чат, анкета
  ждёт в своём слоте и продолжается с того же шага (F-06); `app.start_scene(scene_id,
  user_id, chat_id, data)` — запуск сцены из кода для jobs/outbox (F-22); схема
  `SqlStateStorage` v2 (PK с lane) с авто-миграцией старых баз.

[![Build Wheel & CI](https://github.com/ferrovovan/Bot-Fork/actions/workflows/build-wheel.yml/badge.svg)](https://github.com/ferrovovan/Bot-Fork/actions/workflows/build-wheel.yml)
[![Release](https://img.shields.io/github/v/release/ferrovovan/Bot-Fork?include_prereleases&label=release)](https://github.com/ferrovovan/Bot-Fork/releases)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

---

## 📦 Установка

```bash
# Базовая установка (ядро и mock-режим) напрямую с GitHub:
pip install 'bot-fork @ git+https://github.com/ferrovovan/Bot-Fork'

# С поддержкой Telegram (aiogram 3):
pip install 'bot-fork[telegram] @ git+https://github.com/ferrovovan/Bot-Fork'

# С поддержкой ВКонтакте (vkbottle 4):
pip install 'bot-fork[vk] @ git+https://github.com/ferrovovan/Bot-Fork'

# С поддержкой обеих платформ (Telegram и VK):
pip install 'bot-fork[all] @ git+https://github.com/ferrovovan/Bot-Fork'

# Для разработки и запуска pytest:
pip install 'bot-fork[all,dev] @ git+https://github.com/ferrovovan/Bot-Fork'
```

Нужен **Python 3.10+**. Единственная обязательная зависимость — `python-dotenv`.

### Установка готового `.whl` пакета

Готовые сборки `.whl` публикуются в [Releases](https://github.com/ferrovovan/Bot-Fork/releases):

```bash
# Установка прямо по ссылке на последний релиз:
pip install https://github.com/ferrovovan/Bot-Fork/releases/latest/download/bot_fork-1.0.0-py3-none-any.whl

# Или установка предварительно скачанного файла .whl:
pip install bot_fork-1.0.0-py3-none-any.whl

# Установка скачанного .whl вместе с поддержкой Telegram:
pip install "bot_fork-1.0.0-py3-none-any.whl[telegram]"
```

---

## 🚀 Быстрый старт: Демонстрационная анкета `/info`

Создайте файл `app.py`:

```python
from bot_fork import BotForkApp, Scene, Step, Button

# Описание универсального сценария
info = Scene(
    id="info",
    entry_commands=("/info",),
    steps=(
        Step.text(
            id="name",
            prompt="Как к вам обращаться?",
            validator=lambda t: (1 <= len(t.strip()) <= 80, "Имя должно быть от 1 до 80 символов."),
            next="role",
        ),
        Step.choice(
            id="role",
            prompt="Выберите вашу роль:",
            buttons=(
                Button("Разработчик", "developer"),
                Button("Фрилансер", "freelancer"),
                Button("Другое", "other"),
            ),
            next="goal",
        ),
        Step.text(
            id="goal",
            prompt="Кратко опишите цель проекта.",
            validator=lambda t: (1 <= len(t.strip()) <= 500, "Цель должна быть от 1 до 500 символов."),
            complete=True,
        ),
    ),
)

# Запуск приложения
app = BotForkApp.from_env()
app.register_scene(info)

if __name__ == "__main__":
    app.run()
```

Или запустите готовую демку из репозитория:
```bash
python -m examples.demo_info
```

---

## 🖥 Интерактивная демка (`web/`)

Чат-мок Telegram и ВКонтакте в браузере: показывает диалог, состояние `MemoryStateStorage`
и JSON-контракты `IncomingEvent` / `HandlerResult` на каждом шаге. Сообщения исполняет
настоящее ядро — оболочка лишь вызывает `scripts/handle_event.py`.

```bash
pip install -e .
cd web && npm install && npm run dev     # http://localhost:3000
```

Токены мессенджеров не нужны: симулятор работает с ядром напрямую, минуя API мессенджеров.
Подробности — в [web/README.md](web/README.md).

---

## ⚙️ Переменные окружения (`.env`)

Шаблон — в файле [.env.example](.env.example).

### Запуск для Telegram:
```env
ENABLED_PLATFORMS=telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
LOG_LEVEL=INFO
```

### Запуск для ВКонтакте:
```env
ENABLED_PLATFORMS=vk
VK_BOT_TOKEN=vk1.a.abcdefghijklmnopqrstuvwxyz1234567890
LOG_LEVEL=INFO
```

#### Настройка сообщества ВКонтакте (важно для исключения VK API Error 15):
1. **Ключ доступа:** В группе перейдите в *Управление -> Работа с API -> Ключи доступа*. Создайте ключ и отметьте галочки:
   - *«Разрешить приложению доступ к сообщениям сообщества»* (`messages`);
   - *«Разрешить приложению доступ к управлению сообществом»* (`manage`).
2. **Включение Long Poll:** Во вкладке *Управление -> Работа с API -> Long Poll API*:
   - Установите статус **«Включен»**, выберите версию API **5.199**;
   - Во вкладке *«Типы событий»* включите **«Входящие сообщения»** (`message_new`).
3. **Включение сообщений:** В меню *Управление -> Сообщения*: включите **«Сообщения сообщества»**, а в *«Настройки для бота»* включите **«Возможности ботов»**.

*Примечание*: Одновременное указание `ENABLED_PLATFORMS=telegram,vk` вызовет `ConfigError` до начала polling.

---

## 🧪 Тестирование

Запуск полного набора unit- и интеграционных тестов (T1–T15, FR-01–FR-07, NFR-01–NFR-06):

```bash
python3 tests/test_all.py
```

Тесты выполняются автономно с mock-адаптерами и не требуют реальных токенов API.

---

## ⚙️ Сборка `.whl` пакета и CI/CD

В проекте настроен автоматический CI/CD pipeline в GitHub Actions (`.github/workflows/build-wheel.yml`):
- **Тестирование:** прогон 46 unit- и интеграционных тестов на версиях Python 3.10, 3.11, 3.12, 3.13.
- **Сборка:** компиляция чистого `.whl` (Wheel) и архива исходников `.tar.gz` (`python -m build`).
- **Верификация:** проверка метаданных пакета утилитой `twine check --strict` и тестовая установка.
- **Публикация:** при создании тега `v*` (например, `v1.0.0`) готовый `.whl` файл автоматически прикрепляется к GitHub Releases.

### Локальная сборка wheel:

```bash
# 1. Установите инструмент сборки
pip install build twine

# 2. Соберите wheel и sdist
python3 -m build

# 3. Готовые файлы появятся в директории dist/:
#    dist/bot_fork-1.0.0-py3-none-any.whl
#    dist/bot_fork-1.0.0.tar.gz

# Проверка корректности пакета:
twine check dist/*
```

---

## 📄 Лицензия

Apache License 2.0 (Apache-2.0). Подробнее см. в файле [LICENSE](LICENSE).

