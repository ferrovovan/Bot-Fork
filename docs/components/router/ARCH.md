# router/ARCH.md — Code Arch: каким должен быть диспетчер и реестр сцен

**Компонент:** `bot_fork/router.py` · **Серия контракта:** `1.12.x` ·
**Правит:** совет архитекторов (метка `ARCH-CHANGE: RfI-NN`)

## Назначение

Держит: решение «какой диалог отвечает на это событие» в фиксированном порядке —
системные события → отмена → входная команда и кнопка `scene:<id>` → активная
сессия (сначала дорожка `system`) → FSM; реестр сцен с уникальными командами;
запуск и перезапуск сцены (`begin_scene`); сохранение результата исполнения в
хранилище.
Не держит: валидацию сцен (её делает построение), отправку платформам (возвращает
`HandlerResult`), семантику шагов ([fsm](../fsm/ARCH.md)).

## Границы

| Можно импортировать | Нельзя импортировать |
|---|---|
| stdlib; `models`, `exceptions`, `scene`, `fsm`, `storage` (порт) | `app`, адаптеры, платформенные библиотеки |

## Публичный контракт

- **`SceneRegistry`**: `register`, `get_scene`, `resolve_command`, `list_scenes()` —
  кортеж id зарегистрированных сцен по возрастанию (F-35; состояние сцен — в `StateStorage` (F-34), не здесь), `list_entry_commands`, `commands_for` (F-32).
- **`DialogRouter(registry, storage, fsm_engine?, on_system_event?, cancel_commands?, cancel_buttons?)`**;
  `route(event) → HandlerResult`.
- **`begin_scene(scene, lane_key, chat_id, had_session?, initial_data?)`** —
  единый путь запуска для команды, кнопки и программного старта (F-22).

## Инварианты

1. Порядок разбора фиксирован: системное событие → отмена → команда/кнопка →
   активная сессия → служебный ответ (`UNKNOWN_COMMAND`/`NO_ACTIVE_SCENE`).
   Проверяется: `tests/test_router.py`, `tests/test_groups.py`.
2. Реестр: id сцен и команды (в нижнем регистре) уникальны; команда сопоставляется
   по первому слову текста — `tests/test_router.py`.
3. Отмена снимает «верхний» диалог: сперва дорожка `system`, затем `user` (F-06);
   активной сессии нет — сообщение без очистки — `tests/test_cancel_commands.py`,
   `tests/test_lanes.py`.
4. Набор команд отмены задаёт продукт (F-31); сверка точная по первому слову,
   регистронезависимая — `tests/test_cancel_commands.py`.
5. Ответ отмены несёт подсказку живых команд (F-32) и кнопки продолжения из
   `cancel_buttons`, заданных продуктом (F-36, симметрия F-31; `ARCH-CHANGE: RfI-06-2`);
   пусто — текстовый ответ как раньше; движок не изобретает подписей — `tests/test_cancel_commands.py`, `tests/test_cancel_buttons.py`.
6. Payload `scene:<id>` запускает сцену как команда, в том числе без активной
   сессии; неизвестный `scene:` уходит общий путь (F-23) — `tests/test_scene_button.py`.
7. Системная сцена стартует в своей дорожке и не трогает пользовательскую сессию (F-06) —
   `tests/test_lanes.py`.
8. Перезапуск очищает данные прошлой сессии; префикс сообщения задаёт
   `restart_text` (`None` — общий, `""` — без префикса) (F-27) — `tests/test_router.py`.
9. Info-шаг стартовым шагом проходит цепочкой без зависания (F-33) —
   `tests/test_info_step.py`.
10. `list_scenes()` перечисляет id детерминированно (по возрастанию) и не меняет
    состояние реестра (F-35, `ARCH-CHANGE: RfI-06-1`) — `tests/test_registry.py`.

Где это лежит — [INTERNAL.md](INTERNAL.md).

## Запреты

- Лезть в приватные поля реестра из продукта: перечислитель публичен —
  `list_scenes()` (F-35); обход через `getattr` — симптом, а не решение.
- Продуктовая лексика в ответах: подсказки — из реестра, а не из головы (урок F-32).
- Запуск сцены не в её `lane`.

## Чем проверяется

`tests/test_router.py` (8), `tests/test_scene_button.py` (5),
`tests/test_cancel_commands.py` (5), `tests/test_lanes.py` (дорожки),
системные события `tests/test_groups.py`, `tests/test_registry.py` (F-35), `tests/test_cancel_buttons.py` (F-36). Число — [INTERNAL.md](INTERNAL.md).
