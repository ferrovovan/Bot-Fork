"""
SqlStateStorage — персистентное хранилище сессий Bot Fork (F-02).

Хранит UserSession в SQL-таблице поверх stdlib sqlite3 (по умолчанию) или любой
другой DBAPI-совместимой библиотеки через connection_factory (PostgreSQL и т.п.).
Синхронные DBAPI-вызовы вынесены в поток через asyncio.to_thread, чтобы не
блокировать event loop.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from bot_fork.exceptions import StorageError
from bot_fork.models import SessionKey, UserSession
from bot_fork.storage import StateStorage

TABLE_NAME = "botfork_sessions"


class SqlStateStorage(StateStorage):
    """
    StateStorage поверх SQL. По умолчанию — sqlite3 (файл или :memory:).
    Для других СУБД передайте connection_factory, возвращающий DBAPI-соединение
    (параметры подключения остаются целиком на стороне продукта).
    """

    def __init__(
        self,
        dsn: str = ":memory:",
        connection_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._dsn = dsn
        if connection_factory is not None:
            self._conn = connection_factory()
        else:
            try:
                self._conn = sqlite3.connect(dsn, check_same_thread=False)
            except sqlite3.Error as e:
                raise StorageError(f"Не удалось открыть SQLite '{dsn}': {e}") from e
        self._lock = asyncio.Lock()
        self._ensure_schema()

    # ---------- схема ----------

    def _ensure_schema(self) -> None:
        sql = f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            platform   TEXT NOT NULL,
            user_id    TEXT NOT NULL,
            chat_id    TEXT NOT NULL,
            scene_id   TEXT NOT NULL,
            step_id    TEXT NOT NULL,
            data       TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (platform, user_id, chat_id)
        )
        """
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            self._conn.commit()
        except Exception as e:
            raise StorageError(f"Не удалось создать таблицу сессий: {e}") from e
        finally:
            cur.close()

    # ---------- DBAPI-операции (в потоке) ----------

    def _get_sync(self, key: SessionKey) -> Optional[UserSession]:
        cur = self._conn.cursor()
        try:
            cur.execute(
                f"SELECT scene_id, step_id, data, updated_at FROM {TABLE_NAME} "
                "WHERE platform=? AND user_id=? AND chat_id=?",
                (key.platform, key.user_id, key.chat_id),
            )
            row = cur.fetchone()
        finally:
            cur.close()
        if row is None:
            return None
        scene_id, step_id, data_json, updated_at = row[0], row[1], row[2], row[3]
        try:
            data = json.loads(data_json)
        except (ValueError, TypeError) as e:
            raise StorageError(f"Повреждённые данные сессии {key}: {e}") from e
        try:
            ts = datetime.fromisoformat(updated_at)
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)
        return UserSession(
            session_key=key,
            scene_id=scene_id,
            step_id=step_id,
            data=data,
            updated_at=ts,
        )

    def _set_sync(self, session: UserSession) -> None:
        k = session.session_key
        cur = self._conn.cursor()
        try:
            cur.execute(
                f"INSERT INTO {TABLE_NAME} (platform, user_id, chat_id, scene_id, step_id, data, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(platform, user_id, chat_id) DO UPDATE SET "
                "scene_id=excluded.scene_id, step_id=excluded.step_id, "
                "data=excluded.data, updated_at=excluded.updated_at",
                (
                    k.platform,
                    k.user_id,
                    k.chat_id,
                    session.scene_id,
                    session.step_id,
                    json.dumps(session.data, ensure_ascii=False),
                    session.updated_at.isoformat(),
                ),
            )
            self._conn.commit()
        except Exception as e:
            raise StorageError(f"Не удалось сохранить сессию: {e}") from e
        finally:
            cur.close()

    def _clear_sync(self, key: SessionKey) -> None:
        cur = self._conn.cursor()
        try:
            cur.execute(
                f"DELETE FROM {TABLE_NAME} WHERE platform=? AND user_id=? AND chat_id=?",
                (key.platform, key.user_id, key.chat_id),
            )
            self._conn.commit()
        finally:
            cur.close()

    def _count_sync(self) -> int:
        cur = self._conn.cursor()
        try:
            cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            cur.close()

    # ---------- интерфейс StateStorage ----------

    async def get(self, key: SessionKey) -> Optional[UserSession]:
        if not isinstance(key, SessionKey):
            raise StorageError("Invalid session key type")
        async with self._lock:
            return await asyncio.to_thread(self._get_sync, key)

    async def set(self, session: UserSession) -> None:
        if not isinstance(session, UserSession) or not isinstance(session.session_key, SessionKey):
            raise StorageError("Invalid session or session key")
        async with self._lock:
            await asyncio.to_thread(self._set_sync, session)

    async def clear(self, key: SessionKey) -> None:
        if not isinstance(key, SessionKey):
            raise StorageError("Invalid session key type")
        async with self._lock:
            await asyncio.to_thread(self._clear_sync, key)

    async def count(self) -> int:
        """Число активных сессий (как у MemoryStateStorage)."""
        async with self._lock:
            return await asyncio.to_thread(self._count_sync)

    def close(self) -> None:
        """Закрыть соединение (sqlite; для внешних connection_factory — на усмотрение продукта)."""
        try:
            self._conn.close()
        except Exception:
            pass
