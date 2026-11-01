# Симулятор диалога Bot Fork

Веб-оболочка над Python-ядром `bot_fork/`: чат-мок Telegram и ВКонтакте, показывающий
в реальном времени состояние конечного автомата и JSON-контракты `IncomingEvent` / `HandlerResult`.

## Как это работает

Браузер не эмулирует логику сценариев. Каждое сообщение уходит в `server.ts`,
тот запускает `scripts/handle_event.py`, и событие проходит через настоящее ядро:
`normalize_event()` → `DialogRouter` → `FSMEngine` → `format_outgoing()`.
Состояние сессии между вызовами лежит в файле внутри `tempfile.gettempdir()`.

## Запуск

Нужны Python 3.10+ и Node.js 22.6+ (`npm run dev` работает и на более старых — там сборку делает `tsx`).

```bash
# 1. ядро (из корня репозитория)
pip install -e .

# 2. оболочка (из web/)
npm install
npm run dev                  # http://localhost:3000
```

Токены мессенджеров не нужны: симулятор вызывает ядро напрямую, без Telegram и VK API.
`aiogram` и `vkbottle` для него тоже не требуются — адаптеры импортируют их лениво.

Только фронтенд с прокси на уже запущенный `npm run dev`:

```bash
npm run client               # http://localhost:5173
```

Продакшен-сборка:

```bash
npm run build
npm start                    # NODE_ENV=production, раздаёт web/dist
```

## Что где лежит

| Файл | Назначение |
| --- | --- |
| `src/App.tsx` | Экран: шапка, симулятор, блок «Как устроен один сценарий» |
| `src/components/ChatSimulator.tsx` | Чат-мок, переключение TG/VK, инспектор FSM и протокола |
| `src/components/HowItWorks.tsx` | Поток обработки события и состав модулей ядра |
| `server.ts` | Мост `/api/bot-fork/event` и `/api/bot-fork/reset` над `scripts/handle_event.py` |

## API

| Метод и путь | Тело запроса | Ответ |
| --- | --- | --- |
| `POST /api/bot-fork/event` | `{platform, user_id, chat_id, text, payload}` | `HandlerResult` из ядра |
| `POST /api/bot-fork/reset` | `{platform, user_id, chat_id}` | `{ok, cleared}` |
| `GET /api/health` | — | `{ok: true}` |

`platform` принимает только `telegram` и `vk`, `user_id` и `chat_id` — только `[A-Za-z0-9_-]{1,64}`;
остальное отклоняется с `400` до запуска Python-процесса.
