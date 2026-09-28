"""
Base platform adapter interface for Bot Fork.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Optional
from bot_fork.models import HandlerResult, IncomingEvent, OutgoingMessage

EventHandler = Callable[[IncomingEvent], Awaitable[HandlerResult]]


class PlatformAdapter(ABC):
    """Abstract base class for platform adapters (Telegram and VK)."""

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Returns 'telegram' or 'vk'."""
        pass

    @abstractmethod
    def normalize_event(self, raw_event: Any) -> IncomingEvent:
        """Converts platform-specific update/event to universal IncomingEvent."""
        pass

    @abstractmethod
    def format_outgoing(self, message: OutgoingMessage) -> Any:
        """Converts OutgoingMessage to platform-specific payload."""
        pass

    @abstractmethod
    async def send(self, message: OutgoingMessage) -> None:
        """Sends an outgoing message via platform API or mock."""
        pass

    @abstractmethod
    async def start_polling(self, handler: EventHandler) -> None:
        """Starts receiving events and dispatches them to handler."""
        pass
