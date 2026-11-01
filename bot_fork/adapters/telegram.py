"""
TelegramAdapter implementation for Bot Fork.
Handles aiogram event translation, inline keyboard mapping, and mock testing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional
from bot_fork.adapters.base import EventHandler, PlatformAdapter
from bot_fork.exceptions import PlatformError, PlatformOperationNotSupported
from bot_fork.models import Attachment, Button, IncomingEvent, OutgoingMessage

logger = logging.getLogger("bot_fork.adapters.telegram")

# F-21: маппинг полей Telegram-сообщения на нормализованный content_type
_TG_CONTENT_KINDS = ("photo", "sticker", "video", "voice", "audio", "document", "animation")

# F-13: статусы my_chat_member → системное событие о самом боте
_TG_BOT_REMOVED_STATUSES = ("left", "kicked")


def _tg_field(source: Any, name: str) -> Any:
    """Поле из dict или объекта (aiogram) единым способом."""
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def detect_chat_type(raw_chat: Any) -> Optional[str]:
    """F-13: chat.type у Telegram — private|group|supergroup|channel."""
    value = _tg_field(raw_chat, "type")
    return str(value) if value else None


def detect_service_kind(raw_message: Any) -> Optional[tuple]:
    """
    F-13: сервисное сообщение группы → (system_kind, user_id участника) либо None.
    new_chat_members/left_chat_member в супергруппах приходят только боту-админу — это
    ограничение Bot API, продукт на него закладывается планом Б (см. лог F-13).
    """
    members = _tg_field(raw_message, "new_chat_members")
    if members:
        first = members[0]
        uid = _tg_field(first, "id")
        return ("member_joined", str(uid) if uid else None)
    left = _tg_field(raw_message, "left_chat_member")
    if left:
        uid = _tg_field(left, "id")
        return ("member_left", str(uid) if uid else None)
    if _tg_field(raw_message, "new_chat_title") is not None:
        return ("chat_title_changed", None)
    if _tg_field(raw_message, "pinned_message"):
        return ("pinned", None)
    if _tg_field(raw_message, "new_chat_photo") or _tg_field(raw_message, "delete_chat_photo"):
        return ("other", None)
    return None


def detect_content_type(raw_message: Any) -> Optional[str]:
    """
    F-21: определяет тип контента входящего сообщения (text|photo|sticker|voice|video|document|other).
    Работает и с dict (raw update), и с объектом aiogram.types.Message.
    """
    def _present(name: str) -> bool:
        if isinstance(raw_message, dict):
            return bool(raw_message.get(name))
        return bool(getattr(raw_message, name, None))

    if _present("text"):
        return "text"
    for name in _TG_CONTENT_KINDS:
        if _present(name):
            return "video" if name == "animation" else name
    if _present("sticker"):
        return "sticker"
    return "other"


class TelegramAdapter(PlatformAdapter):
    """
    Adapter for Telegram Messenger.
    Converts Telegram Update / Message / CallbackQuery into IncomingEvent.
    Converts OutgoingMessage buttons into Telegram inline keyboards.
    """

    def __init__(self, token: Optional[str] = None, mock_sender: Optional[Callable[[Dict[str, Any]], Any]] = None) -> None:
        super().__init__(token)
        self.mock_sender = mock_sender
        self.sent_messages: List[Dict[str, Any]] = []
        # F-13/F-19: журнал групповых операций (мок-режим и отладка реального)
        self.chat_ops: List[Dict[str, Any]] = []
        self._bot = None

    @property
    def platform_name(self) -> str:
        return "telegram"

    def normalize_event(self, raw_event: Any) -> IncomingEvent:
        """
        Normalizes a Telegram dictionary or object into IncomingEvent.
        Supports text messages and inline callback queries from:
        - raw dicts (test mocks / webhooks)
        - aiogram Update
        - aiogram Message (e.g. from @dp.message())
        - aiogram CallbackQuery (e.g. from @dp.callback_query())
        """
        if isinstance(raw_event, dict):
            # F-13: изменение участника самого бота (bot_added/bot_removed)
            if "my_chat_member" in raw_event:
                mcm = raw_event["my_chat_member"]
                chat = mcm.get("chat", {})
                user = mcm.get("from", {})
                new_member = mcm.get("new_chat_member", {})
                status = str(new_member.get("status", ""))
                kind = "bot_removed" if status in _TG_BOT_REMOVED_STATUSES else "bot_added"
                uid = str(user.get("id", chat.get("id", "")))
                return IncomingEvent(
                    platform="telegram",
                    user_id=uid,
                    chat_id=str(chat.get("id", uid)),
                    text=None,
                    event_type="system",
                    system_kind=kind,
                    chat_type=detect_chat_type(chat),
                )

            # Check callback query
            if "callback_query" in raw_event:
                cb = raw_event["callback_query"]
                from_user = cb.get("from", {})
                msg = cb.get("message", {})
                chat = msg.get("chat", {})
                user_id = str(from_user.get("id", ""))
                chat_id = str(chat.get("id", user_id))
                payload = cb.get("data")
                return IncomingEvent(
                    platform="telegram",
                    user_id=user_id,
                    chat_id=chat_id,
                    text=None,
                    payload=payload,
                    event_id=str(cb.get("id", "")),
                    chat_type=detect_chat_type(chat),
                )

            # Check standard message
            msg = raw_event.get("message", raw_event)
            from_user = msg.get("from", {})
            chat = msg.get("chat", {})
            user_id = str(from_user.get("id", chat.get("id", "")))
            chat_id = str(chat.get("id", user_id))
            text = msg.get("text")
            # F-13: сервисные сообщения группы («X присоединился» и т.п.)
            service = detect_service_kind(msg)
            if service is not None:
                kind, member_uid = service
                return IncomingEvent(
                    platform="telegram",
                    user_id=member_uid or user_id,
                    chat_id=chat_id,
                    event_type="system",
                    system_kind=kind,
                    chat_type=detect_chat_type(chat),
                )
            return IncomingEvent(
                platform="telegram",
                user_id=user_id,
                chat_id=chat_id,
                text=text,
                payload=None,
                event_id=str(raw_event.get("update_id", "")),
                content_type=detect_content_type(msg),
                chat_type=detect_chat_type(chat),
            )

        # 1. Direct CallbackQuery object (e.g. from @dp.callback_query()) - has 'data'
        if hasattr(raw_event, "data") and getattr(raw_event, "data", None) is not None:
            from_user = getattr(raw_event, "from_user", None)
            msg = getattr(raw_event, "message", None)
            chat = getattr(msg, "chat", None) if msg else None
            user_id = str(from_user.id) if from_user else ""
            chat_id = str(chat.id) if chat else user_id
            return IncomingEvent(
                platform="telegram",
                user_id=user_id,
                chat_id=chat_id,
                text=None,
                payload=raw_event.data,
                event_id=str(getattr(raw_event, "id", "")),
                chat_type=detect_chat_type(chat),
            )

        # 2. Update object containing callback_query / my_chat_member / message
        mcm = getattr(raw_event, "my_chat_member", None)
        if mcm is not None:
            chat = getattr(mcm, "chat", None)
            user = getattr(mcm, "from_user", None)
            new_member = getattr(mcm, "new_chat_member", None)
            status = str(getattr(new_member, "status", ""))
            kind = "bot_removed" if status in _TG_BOT_REMOVED_STATUSES else "bot_added"
            uid = str(user.id) if user else str(getattr(chat, "id", ""))
            return IncomingEvent(
                platform="telegram",
                user_id=uid,
                chat_id=str(getattr(chat, "id", uid)),
                text=None,
                event_type="system",
                system_kind=kind,
                chat_type=detect_chat_type(chat),
            )

        if getattr(raw_event, "callback_query", None):
            cb = raw_event.callback_query
            user_id = str(cb.from_user.id) if getattr(cb, "from_user", None) else ""
            chat = getattr(cb.message, "chat", None) if getattr(cb, "message", None) else None
            chat_id = str(chat.id) if chat else user_id
            return IncomingEvent(
                platform="telegram",
                user_id=user_id,
                chat_id=chat_id,
                text=None,
                payload=getattr(cb, "data", None),
                event_id=str(getattr(cb, "id", "")),
                chat_type=detect_chat_type(chat),
            )

        # 3. Direct Message object (e.g. from @dp.message()) - has 'chat'
        if hasattr(raw_event, "chat") and raw_event.chat:
            chat = raw_event.chat
            from_user = getattr(raw_event, "from_user", None)
            user_id = str(from_user.id) if from_user else str(getattr(chat, "id", ""))
            chat_id = str(getattr(chat, "id", user_id))
            # F-13: объект ChatMemberUpdated из @dp.my_chat_member() — событие о боте
            if getattr(raw_event, "new_chat_member", None) is not None:
                status = str(getattr(raw_event.new_chat_member, "status", ""))
                kind = "bot_removed" if status in _TG_BOT_REMOVED_STATUSES else "bot_added"
                return IncomingEvent(
                    platform="telegram",
                    user_id=user_id,
                    chat_id=chat_id,
                    text=None,
                    event_type="system",
                    system_kind=kind,
                    chat_type=detect_chat_type(chat),
                )
            text = getattr(raw_event, "text", None)
            service = detect_service_kind(raw_event)
            if service is not None:
                kind, member_uid = service
                return IncomingEvent(
                    platform="telegram",
                    user_id=member_uid or user_id,
                    chat_id=chat_id,
                    event_type="system",
                    system_kind=kind,
                    chat_type=detect_chat_type(chat),
                )
            return IncomingEvent(
                platform="telegram",
                user_id=user_id,
                chat_id=chat_id,
                text=text,
                payload=None,
                event_id=str(getattr(raw_event, "message_id", "")),
                content_type=detect_content_type(raw_event),
                chat_type=detect_chat_type(chat),
            )

        # 4. Update object containing message
        if hasattr(raw_event, "message") and raw_event.message:
            msg = raw_event.message
            user_id = str(msg.from_user.id) if getattr(msg, "from_user", None) else str(getattr(msg.chat, "id", ""))
            chat_id = str(msg.chat.id) if getattr(msg, "chat", None) else user_id
            service = detect_service_kind(msg)
            if service is not None:
                kind, member_uid = service
                return IncomingEvent(
                    platform="telegram",
                    user_id=member_uid or user_id,
                    chat_id=chat_id,
                    event_type="system",
                    system_kind=kind,
                    chat_type=detect_chat_type(msg.chat),
                )
            return IncomingEvent(
                platform="telegram",
                user_id=user_id,
                chat_id=chat_id,
                text=getattr(msg, "text", None),
                payload=None,
                event_id=str(getattr(raw_event, "update_id", getattr(msg, "message_id", ""))),
                content_type=detect_content_type(msg),
                chat_type=detect_chat_type(msg.chat),
            )

        raise PlatformError(f"Unsupported Telegram event structure: {type(raw_event)}")

    def format_outgoing(self, message: OutgoingMessage) -> Dict[str, Any]:
        """
        Converts OutgoingMessage into Telegram API payload.
        Maps buttons to inline_keyboard rows.
        """
        payload: Dict[str, Any] = {
            "chat_id": message.chat_id,
            "text": message.text,
        }

        # F-01: вложение — описание в payload для мока/отладки, байты уходят отдельным вызовом API
        if message.attachment is not None:
            payload["attachment"] = message.attachment.to_dict()

        if message.buttons:
            # Inline keyboard: up to 4 buttons in a clean vertical or grid layout
            inline_keyboard = [
                [{"text": btn.label, "callback_data": btn.value}]
                for btn in message.buttons
            ]
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}

        return payload

    async def send(self, message: OutgoingMessage) -> None:
        """Sends OutgoingMessage via mock_sender or Telegram Bot API."""
        await self._dispatch_outgoing(message)

    async def _dispatch_outgoing(self, message: OutgoingMessage) -> Optional[str]:
        """Общая отправка; возвращает platform message_id, если он известен."""
        formatted = self.format_outgoing(message)
        self.sent_messages.append(formatted)

        if self.mock_sender is not None:
            res = self.mock_sender(formatted)
            if hasattr(res, "__await__"):
                await res
            return None

        # If real token provided and aiogram is available
        if self.token:
            try:
                from aiogram import Bot
                if self._bot is None:
                    self._bot = Bot(token=self.token)
                bot = self._bot
                reply_markup = None
                if message.buttons:
                    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
                    buttons_list = [
                        [InlineKeyboardButton(text=btn.label, callback_data=btn.value)]
                        for btn in message.buttons
                    ]
                    reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons_list)

                if message.attachment is not None:
                    # F-01: текст уходит подписью (caption) к медиа
                    import io

                    file_obj = io.BytesIO(message.attachment.data)
                    file_obj.name = message.attachment.filename
                    caption = message.attachment.caption or message.text
                    if message.attachment.kind == "photo":
                        result = await bot.send_photo(
                            chat_id=int(message.chat_id),
                            photo=file_obj,
                            caption=caption,
                            reply_markup=reply_markup,
                        )
                    else:
                        result = await bot.send_document(
                            chat_id=int(message.chat_id),
                            document=file_obj,
                            caption=caption,
                            reply_markup=reply_markup,
                        )
                else:
                    result = await bot.send_message(
                        chat_id=int(message.chat_id),
                        text=message.text,
                        reply_markup=reply_markup,
                    )
                return str(getattr(result, "message_id", "")) or None
            except ImportError:
                logger.info(
                    "aiogram not installed; message formatted and logged in standalone mode: %s",
                    formatted.get("text")[:60],
                )
            except Exception as e:
                raise PlatformError(f"Telegram API send failed: {e}") from e
        return None

    # --- F-13/F-19: групповые операции ---

    def _mock_mode(self) -> bool:
        return not self.token

    async def create_chat(self, user_ids, title: str) -> str:
        """
        F-13: Telegram Bot API не умеет создавать чаты (план Б — чат заводит админ,
        см. лог F-13). В мок-режиме возвращаем детерминированный id для тестов продукта.
        """
        # Бросаем и в мок-режиме: продукт обязан увидеть план Б уже на тестах,
        # иначе моки разрешат то, что на боевой платформе упадёт.
        raise PlatformOperationNotSupported(
            "Telegram Bot API: бот не может создавать чаты. План Б: чат создаёт админ руками "
            "и добавляет бота админом (см. Архитектура/07, риски WP3)."
        )

    async def add_member(self, chat_id: str, user_id: str) -> None:
        """F-13: Bot API не умеет принудительно добавлять участников — только ссылка-приглашение."""
        raise PlatformOperationNotSupported(
            "Telegram Bot API: бот не может добавлять участников в чат. Используйте "
            "get_invite_link() и отправьте ссылку игроку."
        )

    async def remove_member(self, chat_id: str, user_id: str) -> None:
        """F-13: banChatMember (бот-админ). Мок — запись в chat_ops."""
        if self._mock_mode():
            self.chat_ops.append({"op": "remove_member", "chat_id": chat_id, "user_id": user_id})
            return
        await self._real_api_call(
            lambda bot: bot.ban_chat_member(chat_id=int(chat_id), user_id=int(user_id)),
            "banChatMember",
        )

    async def rename_chat(self, chat_id: str, title: str) -> None:
        """F-24: setChatTitle (бот-админ с can_change_info; иначе PlatformError)."""
        if self._mock_mode():
            self.chat_ops.append({"op": "rename_chat", "chat_id": chat_id, "title": title})
            return
        bot = await self._ensure_bot()
        try:
            await bot.set_chat_title(chat_id=int(chat_id), title=title)
        except Exception as e:
            raise PlatformError(f"Telegram API setChatTitle failed: {e}") from e

    async def get_invite_link(self, chat_id: str) -> str:
        """F-13: createChatInviteLink (бот-админ с правом can_invite_users)."""
        if self._mock_mode():
            self.chat_ops.append({"op": "get_invite_link", "chat_id": chat_id})
            return f"https://t.me/+mock-{chat_id}"
        bot = await self._ensure_bot()
        try:
            link = await bot.create_chat_invite_link(chat_id=int(chat_id))
            return link.invite_link
        except Exception as e:
            raise PlatformError(f"Telegram API createChatInviteLink failed: {e}") from e

    async def edit_message(self, chat_id: str, message_id: str, message: OutgoingMessage) -> None:
        """F-19: editMessageText + новые кнопки. Вложение при редактировании TG не шлёт."""
        if message.attachment is not None:
            raise PlatformOperationNotSupported(
                "Telegram: отредактировать сообщение с вложением нельзя — отправьте новое."
            )
        if self._mock_mode():
            self.chat_ops.append({
                "op": "edit_message", "chat_id": chat_id, "message_id": message_id,
                "payload": self.format_outgoing(message),
            })
            return
        bot = await self._ensure_bot()
        reply_markup = None
        if message.buttons:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=btn.label, callback_data=btn.value)]
                for btn in message.buttons
            ])
        try:
            await bot.edit_message_text(
                chat_id=int(chat_id),
                message_id=int(message_id),
                text=message.text,
                reply_markup=reply_markup,
            )
        except Exception as e:
            # TG отвечает «message is not modified», если текст не изменился — это не ошибка
            if "message is not modified" in str(e).lower():
                logger.info("edit_message: содержимое не изменилось, пропускаю")
                return
            raise PlatformError(f"Telegram API editMessageText failed: {e}") from e

    async def send_ex(self, message: OutgoingMessage) -> Optional[str]:
        """F-19: отправка с возвратом message_id. Мок возвращает синтетический id."""
        message_id = await self._dispatch_outgoing(message)
        if self._mock_mode():
            return f"tg-mock-{len(self.sent_messages)}"
        return message_id

    async def _ensure_bot(self):
        if self._bot is None:
            try:
                from aiogram import Bot
            except ImportError as e:
                raise PlatformError("aiogram must be installed for live Telegram chat operations") from e
            self._bot = Bot(token=self.token)
        return self._bot

    async def _real_api_call(self, coro_factory, name: str):
        bot = await self._ensure_bot()
        try:
            return await coro_factory(bot)
        except Exception as e:
            raise PlatformError(f"Telegram API {name} failed: {e}") from e

    async def start_polling(self, handler: EventHandler) -> None:
        """Starts Telegram long polling using aiogram or test mock loop."""
        if not self.token:
            raise PlatformError("TELEGRAM_BOT_TOKEN is required to start Telegram polling")

        try:
            from aiogram import Bot, Dispatcher, types
            bot = Bot(token=self.token)
            self._bot = bot
            dp = Dispatcher()

            @dp.message()
            async def handle_message(message: types.Message):
                event = self.normalize_event(message)
                result = await handler(event)
                for out_msg in result.messages:
                    await self.send(out_msg)

            @dp.callback_query()
            async def handle_callback(cb: types.CallbackQuery):
                event = self.normalize_event(cb)
                result = await handler(event)
                for out_msg in result.messages:
                    await self.send(out_msg)
                await cb.answer()

            # F-13: добавление/удаление самого бота из чатов
            @dp.my_chat_member()
            async def handle_my_chat_member(update: types.ChatMemberUpdated):
                event = self.normalize_event(update)
                result = await handler(event)
                for out_msg in result.messages:
                    await self.send(out_msg)

            logger.info("Starting Telegram long polling...")
            await dp.start_polling(bot)
        except ImportError as e:
            raise PlatformError("aiogram must be installed to start live Telegram polling: pip install aiogram") from e
