"""
Base platform adapter interface for Bot Fork.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, List, Optional, Sequence
from bot_fork.exceptions import PlatformOperationNotSupported
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

    # --- F-13/F-19: необязательные операции. Не абстрактные — совместимость со сторонними
    # адаптерами (web-симулятор) сохранена: кто не реализует, тот получает явный
    # PlatformOperationNotSupported, а не TypeError при инстанцировании. ---

    async def send_ex(self, message: OutgoingMessage) -> Optional[str]:
        """
        F-19: как send(), но возвращает platform message_id (нужен для edit_message).
        Дефолт: обычный send без идентификатора; реальные адаптеры переопределяют.
        """
        await self.send(message)
        return None

    async def edit_message(self, chat_id: str, message_id: str, message: OutgoingMessage) -> None:
        """F-19: обновление ранее отправленного сообщения (текст + кнопки). Вложение — нельзя."""
        raise PlatformOperationNotSupported(
            f"{self.platform_name}: редактирование сообщений не реализовано в этом адаптере"
        )

    async def create_chat(self, user_ids: Sequence[str], title: str) -> str:
        """
        F-13: создать групповой чат, вернуть единый chat_id (для событий/сессий).
        Telegram Bot API не умеет вовсе — там исключение (план Б: чат заводит админ).
        """
        raise PlatformOperationNotSupported(f"{self.platform_name}: создание чатов недоступно боту")

    async def add_member(self, chat_id: str, user_id: str) -> None:
        """F-13: добавить участника в чат (бот должен быть админом чата)."""
        raise PlatformOperationNotSupported(f"{self.platform_name}: добавление участников недоступно боту")

    async def remove_member(self, chat_id: str, user_id: str) -> None:
        """F-13: исключить участника из чата (бот должен быть админом чата)."""
        raise PlatformOperationNotSupported(f"{self.platform_name}: исключение участников не реализовано")

    async def get_invite_link(self, chat_id: str) -> str:
        """F-13: ссылка-приглашение в чат (бот должен быть админом с правом invite)."""
        raise PlatformOperationNotSupported(f"{self.platform_name}: ссылка-приглашение недоступна боту")
