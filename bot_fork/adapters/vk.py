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
from bot_fork.models import Attachment, Button, IncomingEvent, OutgoingMessage

logger = logging.getLogger("bot_fork.adapters.vk")

# F-21: тип вложений VK → нормализованный content_type
_VK_ATTACHMENT_KINDS = {
    "photo": "photo",
    "video": "video",
    "audio_message": "voice",
    "doc": "document",
    "sticker": "sticker",
    "graffiti": "other",
}


def detect_content_type(raw_message: Any) -> Optional[str]:
    """
    F-21: content_type входящего сообщения VK по полю attachments / стикерам.
    Возвращает None, если это обычный текст (текст — значение по умолчанию в сцене).
    """
    if isinstance(raw_message, dict):
        attachments = raw_message.get("attachments") or []
        sticker = raw_message.get("sticker")
    else:
        attachments = getattr(raw_message, "attachments", None) or []
        sticker = getattr(raw_message, "sticker", None)

    if sticker:
        return "sticker"
    for att in attachments:
        kind = att.get("type") if isinstance(att, dict) else getattr(att, "type", None)
        if kind:
            return _VK_ATTACHMENT_KINDS.get(kind, "other")
    return None


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
                content_type=detect_content_type(msg) or ("text" if text else None),
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
            content_type=detect_content_type(raw_event) or ("text" if text else None),
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

        # F-01: описание вложения для мока/отладки; реальная отправка — после загрузки в VK
        if message.attachment is not None:
            payload["attachment"] = message.attachment.to_dict()

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

                attachment_ref = None
                if message.attachment is not None:
                    # F-01: медиа сначала загружается в VK, потом шлётся ссылкой-вложением
                    attachment_ref = await self._vk_upload_attachment(
                        self._api, message
                    )

                await self._api.messages.send(
                    peer_id=int(message.chat_id) if str(message.chat_id).isdigit() else message.chat_id,
                    message=message.text,
                    random_id=0,
                    keyboard=formatted.get("keyboard"),
                    attachment=attachment_ref,
                )
            except ImportError:
                logger.info(
                    "vkbottle not installed; message formatted and logged in standalone mode: %s",
                    formatted.get("message")[:60],
                )
            except Exception as e:
                raise PlatformError(f"VK API send failed: {e}") from e

    async def _vk_upload_attachment(self, api: Any, message: OutgoingMessage) -> str:
        """
        F-01: загрузка вложения (photo|document) в VK, возвращает 'photo{oid}_{pid}' | 'doc{oid}_{pid}'.
        """
        import aiohttp

        att = message.attachment
        peer_id = int(message.chat_id) if str(message.chat_id).isdigit() else message.chat_id
        if att.kind == "photo":
            server = await api.photos.get_messages_upload_server(peer_id=peer_id)
            upload_url = server["upload_url"]
            form_field = "photo"
            save = api.photos.save_messages_photo
        else:
            server = await api.docs.get_messages_upload_server(peer_id=peer_id, type="doc")
            upload_url = server["upload_url"]
            form_field = "file"
            save = api.docs.save_messages_photo if hasattr(api.docs, "save_messages_photo") else api.docs.save

        form = aiohttp.FormData()
        form.add_field(form_field, att.data, filename=att.filename)
        async with aiohttp.ClientSession() as session:
            async with session.post(upload_url, data=form) as resp:
                result = await resp.json()
        saved = await save(**{("file" if att.kind != "photo" else "photo"): result.get(form_field, result)}, peer_id=peer_id)
        if isinstance(saved, list):
            saved = saved[0]
        return f"{'photo' if att.kind == 'photo' else 'doc'}{saved['owner_id']}_{saved['id']}"

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
