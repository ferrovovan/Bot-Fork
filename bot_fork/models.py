"""
Core models for Bot Fork library.
Conforms to ScenoMost Bot Fork MVP 3.1 specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class SessionKey:
    """
    Unique composite session key isolating user, chat, lane, and platform.
    Prevents session collision between Telegram and VK.
    F-06: lane — именованный слот сессии в одном чате:
      "user"   — обычные диалоги (анкета, меню);
      "system" — приоритетные сцены (подтверждение слота), перехватывают события,
                 а после завершения пользовательская сессия продолжается с своего шага.
    """
    platform: str
    user_id: str
    chat_id: str
    lane: str = "user"

    def __post_init__(self) -> None:
        if self.platform not in ("telegram", "vk"):
            raise ValueError(f"Invalid platform: {self.platform}. Allowed: 'telegram', 'vk'")
        if not self.user_id:
            raise ValueError("user_id cannot be empty")
        if not self.chat_id:
            raise ValueError("chat_id cannot be empty")
        if self.lane not in ("user", "system"):
            raise ValueError(f"Invalid lane: {self.lane}. Allowed: 'user', 'system'")

    def with_lane(self, lane: str) -> "SessionKey":
        """Ключ того же чата в другом слоте (F-06)."""
        return SessionKey(platform=self.platform, user_id=self.user_id, chat_id=self.chat_id, lane=lane)

    def to_dict(self) -> Dict[str, str]:
        return {
            "platform": self.platform,
            "user_id": str(self.user_id),
            "chat_id": str(self.chat_id),
            "lane": self.lane,
        }


@dataclass(frozen=True)
class Button:
    """
    Universal text button representation independent of platform libraries.
    """
    label: str
    value: str

    def __post_init__(self) -> None:
        if not (1 <= len(self.label) <= 40):
            raise ValueError(f"Button label length must be 1-40 chars, got {len(self.label)}")
        if not (1 <= len(self.value) <= 64):
            raise ValueError(f"Button value length must be 1-64 chars, got {len(self.value)}")

    def to_dict(self) -> Dict[str, str]:
        return {"label": self.label, "value": self.value}


@dataclass(frozen=True)
class Reject:
    """F-28: отказ действия со своими кнопками (F-28).

    Действие шага отказывает двумя способами: строкой (печатается кнопки шага,
    как раньше) или Reject — тогда под текстом отказа кладём кнопки перехода,
    которых в самом шаге нет. Кнопка `scene:<id>` запускает сцену (F-23), так
    что отказ «команды нет» может предложить «📝 Анкета».
    """
    text: str
    buttons: Tuple[Button, ...] = ()

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Reject text must be non-empty")


@dataclass
class IncomingEvent:
    """
    Normalized incoming event from Telegram or VK adapter.
    """
    platform: str
    user_id: str
    chat_id: str
    text: Optional[str] = None
    payload: Optional[str] = None
    event_id: Optional[str] = None
    # F-21: тип контента входящего сообщения — text|photo|sticker|voice|video|document|other
    content_type: Optional[str] = None
    # F-13: тип чата — private|group|supergroup|channel (None — неизвестно, напр. в старых моках)
    chat_type: Optional[str] = None
    # F-13: "message" — обычный диалог; "system" — служебное событие группы.
    # Роутер гасит system-события (бот не отвечает на «игрок присоединился»);
    # охотники за событиями подписываются на BotForkApp(on_system_event=...).
    event_type: str = "message"
    # F-13: вид служебного события: member_joined|member_left|bot_added|bot_removed|
    # chat_title_changed|pinned|other
    system_kind: Optional[str] = None

    def __post_init__(self) -> None:
        if self.platform not in ("telegram", "vk"):
            raise ValueError(f"Invalid platform '{self.platform}'. Allowed: 'telegram', 'vk'")
        if not self.user_id:
            raise ValueError("user_id cannot be empty")
        if not self.chat_id:
            raise ValueError("chat_id cannot be empty")
        if self.event_type not in ("message", "system"):
            raise ValueError(f"Invalid event_type '{self.event_type}'. Allowed: 'message', 'system'")
        # Normalize text: strip outer whitespace
        if self.text is not None:
            self.text = self.text.strip()
            if len(self.text) > 4096:
                raise ValueError("Text exceeds maximum length of 4096 characters")

    @property
    def session_key(self) -> SessionKey:
        return SessionKey(
            platform=self.platform,
            user_id=str(self.user_id),
            chat_id=str(self.chat_id),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "text": self.text,
            "payload": self.payload,
            "event_id": self.event_id,
            "content_type": self.content_type,
            "chat_type": self.chat_type,
            "event_type": self.event_type,
            "system_kind": self.system_kind,
        }


@dataclass
class Attachment:
    """
    F-01: вложение к исходящему сообщению (график botgraph — photo, выгрузка — document).
    Хранит байты в памяти; в to_dict/sent_messages попадает только описание, не байты.
    """
    kind: str  # "photo" | "document"
    data: bytes
    filename: str
    caption: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("photo", "document"):
            raise ValueError(f"Attachment kind must be 'photo' or 'document', got '{self.kind}'")
        if not self.data:
            raise ValueError("Attachment data is empty")
        if not self.filename:
            raise ValueError("Attachment filename is required")
        if len(self.filename) > 128:
            raise ValueError(f"Attachment filename too long ({len(self.filename)} > 128)")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "filename": self.filename,
            "caption": self.caption,
            "size": len(self.data),
        }


@dataclass
class OutgoingMessage:
    """
    Universal outgoing message contract. Text and up to 4 text buttons.
    F-01: optional attachment (photo/document) — уходит вместе с текстом.
    """
    chat_id: str
    text: str
    buttons: Tuple[Button, ...] = ()
    attachment: Optional[Attachment] = None

    def __post_init__(self) -> None:
        if len(self.buttons) > 4:
            raise ValueError(f"A maximum of 4 buttons is allowed, got {len(self.buttons)}")
        # Free tier branding check handled by BotForkApp / FSMEngine
        if len(self.text) > 4096:
            raise ValueError(f"Outgoing message exceeds 4096 characters limit (len={len(self.text)})")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "text": self.text,
            "buttons": [b.to_dict() for b in self.buttons],
            # F-01: мок-адаптер и web-симулятор рисуют вложение по описанию, без байтов
            "attachment": self.attachment.to_dict() if self.attachment else None,
        }


@dataclass
class UserSession:
    """
    Session state storing active scene, current step, and collected survey data.
    """
    session_key: SessionKey
    scene_id: str
    step_id: str
    data: Dict[str, str] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def clone(self) -> UserSession:
        return UserSession(
            session_key=self.session_key,
            scene_id=self.scene_id,
            step_id=self.step_id,
            data=dict(self.data),
            updated_at=datetime.now(timezone.utc),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_key": self.session_key.to_dict(),
            "scene_id": self.scene_id,
            "step_id": self.step_id,
            "data": dict(self.data),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class ErrorInfo:
    """
    Standard error representation for expected dialogue flow errors.
    """
    code: str
    message: str
    retryable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass
class HandlerResult:
    """
    Atomic result of event processing by FSMEngine / DialogRouter.
    """
    messages: Tuple[OutgoingMessage, ...] = ()
    session_after: Optional[UserSession] = None
    clear_session: bool = False
    error: Optional[ErrorInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages": [m.to_dict() for m in self.messages],
            "session_after": self.session_after.to_dict() if self.session_after else None,
            "clear_session": self.clear_session,
            "error": self.error.to_dict() if self.error else None,
        }
