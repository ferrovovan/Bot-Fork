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
    Unique composite session key isolating user, chat, and platform.
    Prevents session collision between Telegram and VK.
    """
    platform: str
    user_id: str
    chat_id: str

    def __post_init__(self) -> None:
        if self.platform not in ("telegram", "vk"):
            raise ValueError(f"Invalid platform: {self.platform}. Allowed: 'telegram', 'vk'")
        if not self.user_id:
            raise ValueError("user_id cannot be empty")
        if not self.chat_id:
            raise ValueError("chat_id cannot be empty")

    def to_dict(self) -> Dict[str, str]:
        return {
            "platform": self.platform,
            "user_id": str(self.user_id),
            "chat_id": str(self.chat_id),
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

    def __post_init__(self) -> None:
        if self.platform not in ("telegram", "vk"):
            raise ValueError(f"Invalid platform '{self.platform}'. Allowed: 'telegram', 'vk'")
        if not self.user_id:
            raise ValueError("user_id cannot be empty")
        if not self.chat_id:
            raise ValueError("chat_id cannot be empty")
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
        }


@dataclass
class OutgoingMessage:
    """
    Universal outgoing message contract. Text and up to 4 text buttons.
    """
    chat_id: str
    text: str
    buttons: Tuple[Button, ...] = ()

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
