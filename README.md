# СценоМост Bot Fork (MVP 1.0)

**Встраиваемая Python-библиотека прототипирования диалоговых сцен для Telegram и ВКонтакте.**

Разработчик описывает диалоговую логику (сцены, шаги, валидаторы, ветвления и кнопки) один раз на чистом Python без платформенных зависимостей, и запускает бота в **Telegram** или **ВКонтакте**, меняя только конфигурацию окружения.

---

## ⚡ Особенности архитектуры MVP

- **Единый диалоговый FSM-контракт**: `Scene`, `Step`, `Button`, `DialogRouter`, `FSMEngine`.
- **Изоляция ядра (NFR-03)**: Ядро не зависит от `aiogram` и `vkbottle`. Платформенные классы не попадают в сценарии.
- **Одноплатформенный запуск на процесс**: В бесплатной версии за один запуск активен ровно один адаптер (`ENABLED_PLATFORMS=telegram` или `ENABLED_PLATFORMS=vk`). Попытка одновременного запуска вызывает `ConfigError`.
- **Фиксированная подпись**: В бесплатной версии к каждому исходящему сообщению ровно один раз добавляется суффикс `Made with Bot Fork`.
- **In-Memory хранилище состояний**: `MemoryStateStorage` изолирует до 100+ параллельных сессий по составному ключу `SessionKey(platform, user_id, chat_id)`.
- **Высокая производительность (NFR-01)**: Среднее время обработки входящего события < 0.1 мс (бенчмарк 100 сессий проходит за ~6 мс при лимите 1.0 с).

---

## 📦 Варианты установки

Все зависимости сразу (Telegram + ВКонтакте + тесты):

```bash
pip install -r requirements.txt
```

Или через стандартный pip install пакета по профилям (из pyproject.toml):

```bash
# Базовая установка (ядро и mock-режим)
pip install bot-fork

# С поддержкой Telegram (aiogram)
pip install "bot-fork[telegram]"

# С поддержкой ВКонтакте (vkbottle)
pip install "bot-fork[vk]"

# Все адаптеры
pip install "bot-fork[all]"
```

---

## 🚀 Быстрый старт: Демонстрационная анкета `/info`

В корне проекта запустите:
```
python -m examples.demo_info
```

---

## ⚙️ Переменные окружения (`.env`)

### Запуск для Telegram:
```env
ENABLED_PLATFORMS=telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNO...
LOG_LEVEL=INFO
```

### Запуск для ВКонтакте:
```env
ENABLED_PLATFORMS=vk
VK_BOT_TOKEN=vk1.a.abcdefg...
LOG_LEVEL=INFO
```

*Примечание*: Одновременное указание `ENABLED_PLATFORMS=telegram,vk` вызовет `ConfigError` до начала polling.

---

## 🧪 Тестирование

Запуск полного набора unit- и интеграционных тестов (T1–T15, FR-01–FR-07, NFR-01–NFR-06):

```bash
python3 tests/test_all.py
```

Тесты выполняются автономно с mock-адаптерами и не требуют реальных токенов API.

---

## 📄 Лицензия

GNU Affero General Public License v3 (AGPL-3.0). Подробнее см. в файле [LICENSE](LICENSE).
