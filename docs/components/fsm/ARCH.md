# fsm/ARCH.md — Code Arch: каким должен быть движок FSM

**Компонент:** `bot_fork/fsm.py` · **Серия контракта:** `1.12.x` ·
**Правит:** совет архитекторов (метка `ARCH-CHANGE: RfI-NN`)

## Назначение

Держит: исполнение одного события о шаг, на котором стоит сессия, — проверка
ввода, валидатор, действие, переходы и цепочки info-шагов, завершение сцены через
`on_complete`, брендинг исходящего текста.
Не держит: запуск сцен и запись в хранилище ([router](../router/ARCH.md)),
платформенную доставку ([adapters](../adapters/ARCH.md)).

## Границы

| Можно импортировать | Нельзя импортировать |
|---|---|
| stdlib; `models`, `exceptions`, `builder`, `scene` | `router`, `storage`, `app`, адаптеры |

## Публичный контракт

- **`FSMEngine.process_step(event, session, scene) → HandlerResult`** — async;
  валидаторы и действия могут быть корутинами (F-04).
- **`apply_branding(text)`** — лимит 4096 + факультативный водяной знак;
  константы `BRANDING_WATERMARK`, `MAX_MESSAGE_LENGTH`.
- Ошибочные коды результата — контракт продукта: `INVALID_INPUT`, `INVALID_BUTTON`,
  `NEED_BUTTON`, `ACTION_REJECTED`, `ACTION_ERROR`, `INTERNAL_ERROR`.

## Инварианты

1. Пустой текст — `INVALID_INPUT`, сессия остаётся на шаге.
   Проверяется: `tests/test_fsm.py`.
2. Валидатор возвращает `bool` или `(bool, сообщение)`, синхронно или асинхронно;
   исключение — `INVALID_INPUT` с текстом, шаг сохраняется — `tests/test_fsm.py`,
   `tests/test_actions.py`.
3. Payload кнопки на текстовом шаге — `INVALID_BUTTON`, а не «пустой ответ» (F-25) —
   `tests/test_info_step.py`.
4. Choice сверяется с живой клавиатурой (включая динамическую, F-29): устаревший
   payload — `INVALID_BUTTON` с кнопками; свободный текст — `NEED_BUTTON` с
   кнопками (F-30) — `tests/test_fsm.py`, `tests/test_dynamic_buttons.py`.
5. Действие: строка-ответ — отказ (`ACTION_REJECTED`), данные шага не сохраняются;
   `Reject` добавляет свои кнопки (F-28); исключение — `ACTION_ERROR`; действие с
   третьим аргументом получает сессию (F-04) — `tests/test_actions.py`.
6. Цепочка info-шагов показывает тексты, исполняет действия и идёт дальше до
   шага с вводом, завершения или конца сцены; зацикливание остановлено (F-25) —
   `tests/test_info_step.py`.
7. Завершение: `on_complete` принимает строку, список `OutgoingMessage` или `None`
   (молчание); исключение в нём — общий отчёт; без `on_complete` — общий отчёт (F-09) —
   `tests/test_on_complete.py`.
8. Каждый исходящий текст ≤4096; водяной знак включается только явным
   окружением, по умолчанию вывод чистый (F-16) — `tests/test_branding.py`,
   `tests/test_runtime_guard.py`.

Где это лежит — [INTERNAL.md](INTERNAL.md).

## Запреты

- Продуктовая лексика в движке: общий отчёт завершения — стопка для демо без
  `on_complete`, продукт обязан задавать свои тексты.
- Потеря ответа пользователя при отвергнутом действии: отказ = без записи в состояние.
- Молчаливое проглатывание исключений валидатора/действия: код ошибки обязан
  дойти до наблюдающего.

## Чем проверяется

`tests/test_fsm.py` (7), `tests/test_actions.py` (12), `tests/test_on_complete.py` (7),
`tests/test_info_step.py` (6, вместе со scenes/router), `tests/test_branding.py` (2),
брендинг-тесты из `tests/test_runtime_guard.py`. Число — [INTERNAL.md](INTERNAL.md).
