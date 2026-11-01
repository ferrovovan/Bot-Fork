"""
VKAdapter implementation for Bot Fork.
Handles vkbottle / VK Bot API event translation, keyboard mapping, and mock testing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional
from bot_fork.adapters.base import EventHandler, PlatformAdapter
from bot_fork.exceptions import PlatformError, PlatformOperationNotSupported
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


# F-13: peer_id групповой беседы в VK = 2000000000 + id беседы
VK_CHAT_PEER_BASE = 2000000000

# F-13: message_new.action.type → нормализованный system_kind
_VK_ACTION_KINDS = {
    "chat_invite_user": "member_joined",
    "chat_kick_user": "member_left",
    "chat_title_update": "chat_title_changed",
    "chat_pin_message": "pinned",
    "chat_unpin_message": "other",
}


def detect_chat_type(peer_id: Any) -> Optional[str]:
    """F-13: беседа (peer >= 2e9) или личка."""
    try:
        return "group" if int(peer_id) >= VK_CHAT_PEER_BASE else "private"
    except (TypeError, ValueError):
        return None


def detect_action(raw_message: Any) -> Optional[tuple]:
    """F-13: служебное действие беседы → (system_kind, member_id) либо None."""
    if isinstance(raw_message, dict):
        action = raw_message.get("action")
    else:
        action = getattr(raw_message, "action", None)
    if not action:
        return None
    atype = action.get("type") if isinstance(action, dict) else getattr(action, "type", None)
    if not atype:
        return None
    member = action.get("member_id") if isinstance(action, dict) else getattr(action, "member_id", None)
    return (_VK_ACTION_KINDS.get(str(atype), "other"), str(member) if member else None)


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
        # F-13/F-19: журнал групповых операций (мок-режим и отладка реального)
        self.chat_ops: List[Dict[str, Any]] = []
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

            # F-13: действие в беседе (пригласили/исключили/переименовали) — system-событие
            action = detect_action(msg)
            if action is not None:
                kind, member_id = action
                return IncomingEvent(
                    platform="vk",
                    user_id=member_id or from_id,
                    chat_id=peer_id,
                    event_type="system",
                    system_kind=kind,
                    chat_type=detect_chat_type(peer_id),
                )
            text = msg.get("text")
            return IncomingEvent(
                platform="vk",
                user_id=from_id,
                chat_id=peer_id,
                text=text,
                payload=payload_str,
                event_id=str(raw_event.get("event_id", msg.get("id", ""))),
                content_type=detect_content_type(msg) or ("text" if text else None),
                chat_type=detect_chat_type(peer_id),
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

        action = detect_action(raw_event)
        if action is not None:
            kind, member_id = action
            return IncomingEvent(
                platform="vk",
                user_id=member_id or from_id,
                chat_id=peer_id,
                event_type="system",
                system_kind=kind,
                chat_type=detect_chat_type(peer_id),
            )
        return IncomingEvent(
            platform="vk",
            user_id=from_id,
            chat_id=peer_id,
            text=text,
            payload=payload_str,
            event_id=str(getattr(raw_event, "id", "")),
            content_type=detect_content_type(raw_event) or ("text" if text else None),
            chat_type=detect_chat_type(peer_id),
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
        await self._dispatch_outgoing(message)

    # --- F-13/F-19: групповые операции. VK умеет их все ключом сообщества ---

    def _mock_mode(self) -> bool:
        return not self.token

    @staticmethod
    def _peer_to_chat_id(chat_id: str) -> int:
        """Единый chat_id (для беседы = peer_id) → локальный chat_id для методов messages.*Chat*."""
        cid = int(chat_id)
        return cid - VK_CHAT_PEER_BASE if cid >= VK_CHAT_PEER_BASE else cid

    async def create_chat(self, user_ids, title: str) -> str:
        """
        F-13: messages.createChat. Возвращает единый chat_id (peer_id беседы).
        Нюанс VK (проверено по dev.vk.com): с токеном сообщества чат не виден в интерфейсе
        сообщества, а участников при создании пригласить нельзя — только позже через
        add_member()/get_invite_link().
        """
        if self._mock_mode():
            self.chat_ops.append({"op": "create_chat", "user_ids": list(user_ids), "title": title})
            return str(VK_CHAT_PEER_BASE + 1)
        try:
            api = await self._ensure_api()
            chat_id = await api.messages.create_chat(user_ids=",".join(str(u) for u in user_ids), title=title)
            return str(VK_CHAT_PEER_BASE + int(chat_id))
        except Exception as e:
            raise PlatformError(f"VK API messages.createChat failed: {e}") from e

    async def add_member(self, chat_id: str, user_id: str) -> None:
        """F-13: messages.addChatUser (бот должен быть админом беседы, ошибка 925)."""
        if self._mock_mode():
            self.chat_ops.append({"op": "add_member", "chat_id": chat_id, "user_id": user_id})
            return
        try:
            api = await self._ensure_api()
            await api.messages.add_chat_user(chat_id=self._peer_to_chat_id(chat_id), user_id=int(user_id))
        except Exception as e:
            raise PlatformError(f"VK API messages.addChatUser failed: {e}") from e

    async def remove_member(self, chat_id: str, user_id: str) -> None:
        """F-13: messages.removeChatUser (бот-админ беседы)."""
        if self._mock_mode():
            self.chat_ops.append({"op": "remove_member", "chat_id": chat_id, "user_id": user_id})
            return
        try:
            api = await self._ensure_api()
            await api.messages.remove_chat_user(chat_id=self._peer_to_chat_id(chat_id), member_id=int(user_id))
        except Exception as e:
            raise PlatformError(f"VK API messages.removeChatUser failed: {e}") from e

    async def rename_chat(self, chat_id: str, title: str) -> None:
        """F-24: messages.editChat(chat_id, title)."""
        if self._mock_mode():
            self.chat_ops.append({"op": "rename_chat", "chat_id": chat_id, "title": title})
            return
        api = await self._ensure_api()
        try:
            await api.messages.edit_chat(chat_id=self._peer_to_chat_id(chat_id), title=title)
        except Exception as e:
            raise PlatformError(f"VK API messages.editChat failed: {e}") from e

    async def get_invite_link(self, chat_id: str) -> str:
        """F-13: messages.getInviteLink(peer_id)."""
        if self._mock_mode():
            self.chat_ops.append({"op": "get_invite_link", "chat_id": chat_id})
            return f"https://vk.me/join/mock-{chat_id}"
        try:
            api = await self._ensure_api()
            result = await api.messages.get_invite_link(peer_id=int(chat_id))
            return str(result.get("link") if isinstance(result, dict) else result)
        except Exception as e:
            raise PlatformError(f"VK API messages.getInviteLink failed: {e}") from e

    async def edit_message(self, chat_id: str, message_id: str, message: OutgoingMessage) -> None:
        """F-19: messages.edit — обновляет текст/клавиатуру отправленного сообщения."""
        if message.attachment is not None:
            raise PlatformOperationNotSupported(
                "VK: редактировать сообщение с вложением нельзя — отправьте новое."
            )
        if self._mock_mode():
            self.chat_ops.append({
                "op": "edit_message", "chat_id": chat_id, "message_id": message_id,
                "payload": self.format_outgoing(message),
            })
            return
        formatted = self.format_outgoing(message)
        try:
            api = await self._ensure_api()
            await api.messages.edit(
                peer_id=int(chat_id),
                message_id=int(message_id),
                message=message.text,
                keyboard=formatted.get("keyboard"),
                random_id=0,
            )
        except Exception as e:
            raise PlatformError(f"VK API messages.edit failed: {e}") from e

    async def send_ex(self, message: OutgoingMessage) -> Optional[str]:
        """F-19: отправка с возвратом message_id. Мок возвращает синтетический id."""
        message_id = await self._dispatch_outgoing(message)
        if self._mock_mode():
            return f"vk-mock-{len(self.sent_messages)}"
        return message_id

    async def _dispatch_outgoing(self, message: OutgoingMessage) -> Optional[str]:
        """Общая отправка; возвращает platform message_id, если он известен."""
        formatted = self.format_outgoing(message)
        self.sent_messages.append(formatted)

        if self.mock_sender is not None:
            res = self.mock_sender(formatted)
            if hasattr(res, "__await__"):
                await res
            return None

        if self.token:
            try:
                api = await self._ensure_api()

                attachment_ref = None
                if message.attachment is not None:
                    # F-01: медиа сначала загружается в VK, потом шлётся ссылкой-вложением
                    attachment_ref = await self._vk_upload_attachment(api, message)

                result = await api.messages.send(
                    peer_id=int(message.chat_id) if str(message.chat_id).isdigit() else message.chat_id,
                    message=message.text,
                    random_id=0,
                    keyboard=formatted.get("keyboard"),
                    attachment=attachment_ref,
                )
                return str(result) if result is not None else None
            except ImportError:
                logger.info(
                    "vkbottle not installed; message formatted and logged in standalone mode: %s",
                    formatted.get("message")[:60],
                )
            except Exception as e:
                raise PlatformError(f"VK API send failed: {e}") from e
        return None

    async def _ensure_api(self):
        if self._api is None:
            try:
                from vkbottle import API
            except ImportError as e:
                raise PlatformError("vkbottle must be installed for live VK chat operations") from e
            self._api = API(token=self.token)
        return self._api

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
