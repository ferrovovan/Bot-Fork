"""
TelegramAdapter implementation for Bot Fork.
Handles aiogram event translation, inline keyboard mapping, and mock testing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional
from bot_fork.adapters.base import EventHandler, PlatformAdapter
from bot_fork.exceptions import PlatformError
from bot_fork.models import Button, IncomingEvent, OutgoingMessage

logger = logging.getLogger("bot_fork.adapters.telegram")


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
                )

            # Check standard message
            msg = raw_event.get("message", raw_event)
            from_user = msg.get("from", {})
            chat = msg.get("chat", {})
            user_id = str(from_user.get("id", chat.get("id", "")))
            chat_id = str(chat.get("id", user_id))
            text = msg.get("text")
            return IncomingEvent(
                platform="telegram",
                user_id=user_id,
                chat_id=chat_id,
                text=text,
                payload=None,
                event_id=str(raw_event.get("update_id", "")),
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
            )

        # 2. Update object containing callback_query
        if hasattr(raw_event, "callback_query") and raw_event.callback_query:
            cb = raw_event.callback_query
            user_id = str(cb.from_user.id) if getattr(cb, "from_user", None) else ""
            chat_id = str(cb.message.chat.id) if getattr(cb, "message", None) and getattr(cb.message, "chat", None) else user_id
            return IncomingEvent(
                platform="telegram",
                user_id=user_id,
                chat_id=chat_id,
                text=None,
                payload=getattr(cb, "data", None),
                event_id=str(getattr(cb, "id", "")),
            )

        # 3. Direct Message object (e.g. from @dp.message()) - has 'chat'
        if hasattr(raw_event, "chat") and raw_event.chat:
            chat = raw_event.chat
            from_user = getattr(raw_event, "from_user", None)
            user_id = str(from_user.id) if from_user else str(getattr(chat, "id", ""))
            chat_id = str(getattr(chat, "id", user_id))
            text = getattr(raw_event, "text", None)
            return IncomingEvent(
                platform="telegram",
                user_id=user_id,
                chat_id=chat_id,
                text=text,
                payload=None,
                event_id=str(getattr(raw_event, "message_id", "")),
            )

        # 4. Update object containing message
        if hasattr(raw_event, "message") and raw_event.message:
            msg = raw_event.message
            user_id = str(msg.from_user.id) if getattr(msg, "from_user", None) else str(getattr(msg.chat, "id", ""))
            chat_id = str(msg.chat.id) if getattr(msg, "chat", None) else user_id
            return IncomingEvent(
                platform="telegram",
                user_id=user_id,
                chat_id=chat_id,
                text=getattr(msg, "text", None),
                payload=None,
                event_id=str(getattr(raw_event, "update_id", getattr(msg, "message_id", ""))),
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
        formatted = self.format_outgoing(message)
        self.sent_messages.append(formatted)

        if self.mock_sender is not None:
            res = self.mock_sender(formatted)
            if hasattr(res, "__await__"):
                await res
            return

        # If real token provided and aiogram is available
        if self.token:
            try:
                import aiogram
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

                await bot.send_message(
                    chat_id=int(message.chat_id),
                    text=message.text,
                    reply_markup=reply_markup,
                )
            except ImportError:
                logger.info(
                    "aiogram not installed; message formatted and logged in standalone mode: %s",
                    formatted.get("text")[:60],
                )
            except Exception as e:
                raise PlatformError(f"Telegram API send failed: {e}") from e

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

            logger.info("Starting Telegram long polling...")
            await dp.start_polling(bot)
        except ImportError as e:
            raise PlatformError("aiogram must be installed to start live Telegram polling: pip install aiogram") from e
