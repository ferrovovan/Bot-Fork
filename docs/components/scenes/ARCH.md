# scenes/ARCH.md — Code Arch: какими должны быть сцены и шаги

**Компонент:** `bot_fork/scene.py`, `bot_fork/builder.py` ·
**Серия контракта:** `1.12.x` · **Правит:** совет архитекторов (метка `ARCH-CHANGE: RfI-NN`)

## Назначение

Держит: декларативное описание сцен и шагов и отлов ошибок конфигурации на
построении (висячие переходы, лишние кнопки, дубли id); фабрики `Step.text/info/choice`,
`Scene`, `ButtonBuilder`.
Не держит: переходы по шагам и хранение сессий — динамические тексты и клавиатуры
лишь получают `UserSession` аргументом; про исполнение — в [fsm](../fsm/ARCH.md).

## Границы

| Можно импортировать | Нельзя импортировать |
|---|---|
| stdlib; `models`, `exceptions`; `builder` | `fsm`, `router`, `storage`, адаптеры |

Сцена описывается без ядра исполнения: контракт описания первичен по отношению к FSM.

## Публичный контракт

- **`StepDefinition`**: `id`, `prompt` (строка или функция, синхронная/async),
  `input_type` (`text|choice|info`), `buttons` (кортеж или функция), `validator`,
  `transitions`, `next_step_id`, `complete`, `action`.
- **Фабрики**: `Step.text`, `Step.info` (показывает и идёт дальше без ввода),
  `Step.choice`; `ButtonBuilder.text/keyboard` — единая проверка кнопок.
- **`SceneDefinition` / фабрика `Scene(...)`**: `id`, `entry_commands`,
  `start_step_id` (по умолчанию первый шаг), `steps`, `lane` (`user|system`, F-06),
  `on_complete` (F-09), `restart_text` (F-27).

## Инварианты

1. Сцена: от 1 до 50 шагов; id шагов уникальны; `start_step_id` существует —
   `tests/test_scenes.py`.
2. `next_step_id` и каждая цель `transitions` указывают на существующий шаг —
   `tests/test_scenes.py`.
3. У `choice` есть кнопки; у `info` кнопок нет ни в статическом, ни в динамическом
   виде; не более 4 кнопок с уникальными value — `tests/test_scenes.py`,
   `tests/test_info_step.py`.
4. Статическая кнопка choice имеет переход либо `next`/завершение; payload
   `scene:<id>` — исключение: перехватывает роутер (F-23) — `tests/test_scenes.py`.
5. Динамический prompt возвращает непустую строку; исключение продукта
   оборачивается в `ConfigError` и не роняет рантайм (F-05/F-29) —
   `tests/test_dynamic_prompt.py`.
6. Динамическая клавиатура проходит ту же проверку, что статическая (≤4,
   уникальные value) — `tests/test_dynamic_buttons.py`.
7. `lane` сцены — только `user|system` — `tests/test_lanes.py`.

Где это лежит (файл и строки) — [INTERNAL.md](INTERNAL.md).

## Запреты

- Продуктовая лексика в фабриках и дефолтах (урок F-09: финальные тексты вынесены
  в `on_complete`/`restart_text`, ядро нейтрально).
- Перенос проверок, доступных на сборке, в рантайм: сцена с висячим переходом не
  должна доживать до диалога.
- Дублирование правил кнопок вне `ButtonBuilder`: правило должно быть одно.

## Чем проверяется

`tests/test_scenes.py` (7), `tests/test_dynamic_prompt.py` (6),
`tests/test_dynamic_buttons.py` (6), `tests/test_info_step.py` (6, вместе с
fsm/router), `tests/test_lanes.py` (проверка lane сцены). Число — [INTERNAL.md](INTERNAL.md).
