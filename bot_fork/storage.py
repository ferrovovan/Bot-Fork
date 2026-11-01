"""
State storage interfaces and MemoryStateStorage implementation for Bot Fork.
Maintains session state isolated by SessionKey in process memory.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Optional
from bot_fork.exceptions import StorageError
from bot_fork.models import SessionKey, UserSession


class StateStorage(ABC):
    """Abstract asynchronous state storage interface."""

    @abstractmethod
    async def get(self, key: SessionKey) -> Optional[UserSession]:
        """Retrieve active user session for given session key."""
        pass

    @abstractmethod
    async def set(self, session: UserSession) -> None:
        """Store or update user session."""
        pass

    @abstractmethod
    async def clear(self, key: SessionKey) -> None:
        """Clear active user session for key (idempotent)."""
        pass

    async def list_scene(self, scene_id: str) -> list:
        """F-34: снимок сессий, припаркованных на сцене scene_id (для фоновых
        саметчеров продукта — TTL брошенных анкет). Необязательная возможность:
        базовый класс отвечает пустым списком — «сканировать нечего»."""
        return []


class MemoryStateStorage(StateStorage):
    """
    In-memory state storage.
    Isolates sessions by composite SessionKey (platform, user_id, chat_id).
    Supports at least 100 concurrent active sessions as required by NFR-01.
    """

    def __init__(self) -> None:
        self._sessions: Dict[SessionKey, UserSession] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: SessionKey) -> Optional[UserSession]:
        if not isinstance(key, SessionKey):
            raise StorageError("Invalid session key type")
        async with self._lock:
            session = self._sessions.get(key)
            if session:
                return session.clone()
            return None

    async def set(self, session: UserSession) -> None:
        if not isinstance(session, UserSession) or not isinstance(session.session_key, SessionKey):
            raise StorageError("Invalid session or session key")
        async with self._lock:
            self._sessions[session.session_key] = session.clone()

    async def clear(self, key: SessionKey) -> None:
        if not isinstance(key, SessionKey):
            raise StorageError("Invalid session key type")
        async with self._lock:
            self._sessions.pop(key, None)

    async def count(self) -> int:
        """Return total active session count."""
        async with self._lock:
            return len(self._sessions)

    async def list_scene(self, scene_id: str) -> list:
        """F-34: сессии на сцене scene_id (снимки, updated_at сохраняется)."""
        async with self._lock:
            return [
                UserSession(
                    session_key=s.session_key, scene_id=s.scene_id,
                    step_id=s.step_id, data=dict(s.data), updated_at=s.updated_at,
                )
                for s in self._sessions.values()
                if s.scene_id == scene_id
            ]
