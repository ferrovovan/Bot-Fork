"""
VKAdapter implementation for Bot Fork.
Handles vkbottle / VK Bot API event translation, keyboard mapping, and mock testing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional
from bot_fork.adapters.base import EventHandler, PlatformAdapter
from bot_fork.exceptions import PlatformError
from bot_fork.models import Button, IncomingEvent, OutgoingMessage

logger = logging.getLogger("bot_fork.adapters.vk")


class VKAdapter(PlatformAdapter):
    """
    Adapter for VKontakte (ВКонтакte).
    Converts VK MessageNew / callback events into IncomingEvent.
    Converts OutgoingMessage buttons into VK keyboard format.
    """

    def __init__(self, token: Optional[str] = None, mock_sender: Optional[Callable[[Dict[str, Any]], Any]] = None) -> None:
        super().__init__(token)
        self.mock_sender = mock_sender
        self.sent_messages: List[Dict[str, Any]] = []
        self._api = None

    @property
    def platform_name(self) -> str:
        return "vk"

    def normalize_event(self, raw_event: Any) -> IncomingEvent:
        """
        Normalizes a VK event dictionary or object into IncomingEvent.
        Handles text messages and callback button payloads.
        """
        if isinstance(raw_event, dict):
            # VK callback or message dict
            msg = raw_event.get("object", {}).get("message", raw_event.get("message", raw_event))
            from_id = str(msg.get("from_id", msg.get("user_id", "")))
            peer_id = str(msg.get("peer_id", from_id))

            payload_raw = msg.get("payload")
            payload_str = None
            if payload_raw:
                if isinstance(payload_raw, str):
                    try:
                        p_dict = json.loads(payload_raw)
                        payload_str = p_dict.get("button", p_dict.get("cmd", payload_raw))
                    except Exception:
                        payload_str = payload_raw
                elif isinstance(payload_raw, dict):
                    payload_str = payload_raw.get("button", payload_raw.get("cmd"))

            text = msg.get("text")
            return IncomingEvent(
                platform="vk",
                user_id=from_id,
                chat_id=peer_id,
                text=text,
                payload=payload_str,
                event_id=str(raw_event.get("event_id", msg.get("id", ""))),
            )

        # Object with attributes
        from_id = str(getattr(raw_event, "from_id", getattr(raw_event, "user_id", "")))
        peer_id = str(getattr(raw_event, "peer_id", from_id))
        text = getattr(raw_event, "text", None)
        payload_raw = getattr(raw_event, "payload", None)
        payload_str = None
        if payload_raw:
            if isinstance(payload_raw, str):
                try:
                    p_dict = json.loads(payload_raw)
                    payload_str = p_dict.get("button", payload_raw)
                except Exception:
                    payload_str = payload_raw
            elif isinstance(payload_raw, dict):
                payload_str = payload_raw.get("button")

        return IncomingEvent(
            platform="vk",
            user_id=from_id,
            chat_id=peer_id,
            text=text,
            payload=payload_str,
            event_id=str(getattr(raw_event, "id", "")),
        )

    def format_outgoing(self, message: OutgoingMessage) -> Dict[str, Any]:
        """
        Converts OutgoingMessage into VK messages.send payload.
        Maps buttons to inline VK keyboard.
        """
        payload: Dict[str, Any] = {
            "peer_id": int(message.chat_id) if message.chat_id.isdigit() else message.chat_id,
            "message": message.text,
            "random_id": 0,
        }

        if message.buttons:
            # Inline keyboard for VK
            buttons_grid = []
            for btn in message.buttons:
                btn_action = {
                    "type": "text",
                    "label": btn.label,
                    "payload": json.dumps({"button": btn.value}, ensure_ascii=False),
                }
                buttons_grid.append([{"action": btn_action, "color": "primary"}])

            payload["keyboard"] = json.dumps(
                {"inline": True, "buttons": buttons_grid},
                ensure_ascii=False,
            )

        return payload

    async def send(self, message: OutgoingMessage) -> None:
        """Sends OutgoingMessage via mock_sender or VK Bot API."""
        formatted = self.format_outgoing(message)
        self.sent_messages.append(formatted)

        if self.mock_sender is not None:
            res = self.mock_sender(formatted)
            if hasattr(res, "__await__"):
                await res
            return

        # If real token provided and vkbottle is available
        if self.token:
            try:
                from vkbottle import API
                if self._api is None:
                    self._api = API(token=self.token)
                await self._api.messages.send(
                    peer_id=int(message.chat_id) if str(message.chat_id).isdigit() else message.chat_id,
                    message=message.text,
                    random_id=0,
                    keyboard=formatted.get("keyboard"),
                )
            except ImportError:
                logger.info(
                    "vkbottle not installed; message formatted and logged in standalone mode: %s",
                    formatted.get("message")[:60],
                )
            except Exception as e:
                raise PlatformError(f"VK API send failed: {e}") from e

    async def start_polling(self, handler: EventHandler) -> None:
        """Starts VK long polling using vkbottle."""
        if not self.token:
            raise PlatformError("VK_BOT_TOKEN is required to start VK polling")

        try:
            from vkbottle.bot import Bot, Message
            from vkbottle.exception_factory import VKAPIError
            bot = Bot(token=self.token)
            self._api = bot.api

            @bot.on.message()
            async def handle_message(msg: Message):
                event = self.normalize_event(msg)
                result = await handler(event)
                for out_msg in result.messages:
                    await self.send(out_msg)

            logger.info("Starting VK long polling...")
            await bot.run_polling()
        except ImportError as e:
            raise PlatformError("vkbottle must be installed to start live VK polling: pip install vkbottle") from e
        except Exception as e:
            err_str = str(e)
            if "VKAPIError_15" in err_str or "Access denied" in err_str or "scopes" in err_str:
                logger.error(
                    "VK API Error 15 (Access denied): The Community Access Token lacks necessary scopes or Long Poll API is disabled. "
                    "Ensure in VK Community Settings: "
                    "1) 'Работа с API' -> 'Ключи доступа': token must have permissions for 'Сообщения' and 'Управление сообществом'. "
                    "2) 'Работа с API' -> 'Long Poll API': Status must be 'Включен', and in 'Типы событий' check 'Входящие сообщения'. "
                    "3) 'Сообщения': Community Messages must be 'Включены' and 'Возможности ботов' enabled."
                )
            raise PlatformError(f"VK polling error: {e}") from e
