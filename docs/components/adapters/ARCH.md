# adapters/ARCH.md — Code Arch: какой должна быть граница платформ

**Компонент:** `bot_fork/adapters/{base,telegram,vk}.py` ·
**Серия контракта:** `1.12.x` · **Правит:** совет архитекторов (метка `ARCH-CHANGE: RfI-NN`)

## Назначение

Держит: перевод платформенных событий в `IncomingEvent` и обратно —
`OutgoingMessage` в клавиатуру Telegram / VK; отправку (мок и живую), поллинг;
групповые операции (F-13/F-24), отправку с id и редактирование (F-19), вложения
(F-01), распознавание контента входящего (F-21).
Не держит: решений, что отвечать (диалог — у fsm), состояния, токенов в payload и логах.

## Границы

| Можно импортировать | Нельзя импортировать |
|---|---|
| stdlib; `models`, `exceptions`, `base` | `fsm`, `router`, `app`; `aiogram`/`vkbottle` — только лениво, внутри методов (NFR-03) |

## Публичный контракт

- **`PlatformAdapter`** (ABC): `platform_name`, `normalize_event`, `format_outgoing`,
  `send`, `start_polling`; факультативные (по умолчанию —
  `PlatformOperationNotSupported`): `send_ex`, `edit_message`, `create_chat`,
  `add_member`, `remove_member`, `rename_chat`, `get_invite_link`.
- **`TelegramAdapter`/`VKAdapter(token?, mock_sender?)`**: журналы `sent_messages`,
  `chat_ops` для тестов и песочницы; нормализаторы `detect_content_type`,
  `detect_chat_type`, `detect_service_kind`/`detect_action`.

## Инварианты

1. Нормализация принимает dict и объекты библиотек (сообщение, callback,
   групповые события) обеих платформ. Проверяется: `tests/test_adapters.py`,
   `tests/test_groups.py`.
2. Клавиатура: TG — inline `callback_data` («одна кнопка в ряд»), VK — inline JSON
   `{"button": value}`; label/value проходят из `Button` без искажений —
   `tests/test_adapters.py`, `tests/test_scene_button.py`.
3. Групповые сервисные события — `event_type="system"` с `system_kind`, включая
   известие о самом боте (`my_chat_member`) (F-13) — `tests/test_groups.py`.
4. Telegram plan B: `create_chat`/`add_member` отказывают даже в мок-режиме —
   продукт видит план B на тестах, а не в бою (F-13) — `tests/test_groups.py`.
5. VK умеет групповые операции целиком; в моке операции пишутся в журнал `chat_ops` —
   `tests/test_groups.py`.
6. `edit_message` с вложением — `PlatformOperationNotSupported` на обеих
   платформах; `send_ex` возвращает id (в моке — синтетический) (F-19) —
   `tests/test_groups.py`.
7. Вложения: TG — медиа с подписью, VK — сначала загрузка, затем отправка ссылкой;
   байты в payload не попадают (F-01) — `tests/test_media.py`.
8. Без токена: отправка идёт в мок/журнал, `start_polling` — `PlatformError` —
   `tests/test_adapters.py` (отправка); поллинг прямого теста нет (долг, INTERNAL).

Где это лежит — [INTERNAL.md](INTERNAL.md).

## Запреты

- Мочить возможности, которых у платформы нет: зелёный тест не должен врать за прод.
- Ветвления диалога и названия сцен в адаптерах.
- Токен в payload, логах, текстах ошибок.

## Чем проверяется

`tests/test_adapters.py` (10), `tests/test_groups.py` (18), `tests/test_media.py` (9),
`tests/test_send.py` (3). Число — [INTERNAL.md](INTERNAL.md).
