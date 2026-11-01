"""
Тесты F-02: SqlStateStorage — асинхронное хранилище сессий поверх sqlite3 (stdlib).
Проверяет round-trip, upsert, персистентность между экземплярами, изоляцию платформ.
"""

import os
import tempfile
import unittest

from bot_fork.models import SessionKey, UserSession
from bot_fork.sql_storage import SqlStateStorage, _sqlite_path


def _key(platform="telegram", user_id="101", chat_id="101") -> SessionKey:
    return SessionKey(platform=platform, user_id=user_id, chat_id=chat_id)


class TestSqlStateStorage(unittest.IsolatedAsyncioTestCase):
    async def test_roundtrip_set_get(self):
        storage = SqlStateStorage(dsn=":memory:")
        key = _key()
        session = UserSession(
            session_key=key,
            scene_id="survey",
            step_id="steam",
            data={"steam": "steamcommunity.com/profiles/123", "имя": "Ваня"},
        )

        await storage.set(session)
        loaded = await storage.get(key)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.scene_id, "survey")
        self.assertEqual(loaded.step_id, "steam")
        # Русские ключи и значения сохраняются без экранирования
        self.assertEqual(loaded.data["steam"], "steamcommunity.com/profiles/123")
        self.assertEqual(loaded.data["имя"], "Ваня")
        self.assertEqual(loaded.session_key, key)

    async def test_get_missing_returns_none(self):
        storage = SqlStateStorage(dsn=":memory:")
        self.assertIsNone(await storage.get(_key(user_id="777")))

    async def test_upsert_overwrites_same_key(self):
        storage = SqlStateStorage(dsn=":memory:")
        key = _key()

        await storage.set(UserSession(session_key=key, scene_id="s1", step_id="a", data={"x": "1"}))
        await storage.set(UserSession(session_key=key, scene_id="s1", step_id="b", data={"x": "2"}))

        loaded = await storage.get(key)
        self.assertEqual(loaded.step_id, "b")
        self.assertEqual(loaded.data["x"], "2")
        self.assertEqual(await storage.count(), 1)

    async def test_clear_removes_session(self):
        storage = SqlStateStorage(dsn=":memory:")
        key = _key()
        await storage.set(UserSession(session_key=key, scene_id="s1", step_id="a", data={}))

        await storage.clear(key)

        self.assertIsNone(await storage.get(key))
        self.assertEqual(await storage.count(), 0)
        # Повторный clear не должен падать
        await storage.clear(key)

    async def test_platform_isolation(self):
        storage = SqlStateStorage(dsn=":memory:")
        tg_key = _key(platform="telegram", user_id="55", chat_id="55")
        vk_key = _key(platform="vk", user_id="55", chat_id="55")

        await storage.set(UserSession(session_key=tg_key, scene_id="tg_scene", step_id="a", data={}))
        await storage.set(UserSession(session_key=vk_key, scene_id="vk_scene", step_id="b", data={}))

        tg = await storage.get(tg_key)
        vk = await storage.get(vk_key)
        self.assertEqual(tg.scene_id, "tg_scene")
        self.assertEqual(vk.scene_id, "vk_scene")
        self.assertEqual(await storage.count(), 2)

        await storage.clear(tg_key)
        self.assertIsNone(await storage.get(tg_key))
        self.assertIsNotNone(await storage.get(vk_key))

    async def test_persistence_between_instances(self):
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            key = _key(platform="vk", user_id="202", chat_id="202")
            writer = SqlStateStorage(dsn=path)
            await writer.set(
                UserSession(session_key=key, scene_id="survey", step_id="rank", data={"ранг": "Кристалл IV"})
            )
            writer.close()

            reader = SqlStateStorage(dsn=path)
            loaded = await reader.get(key)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.step_id, "rank")
            self.assertEqual(loaded.data["ранг"], "Кристалл IV")
            reader.close()
        finally:
            os.unlink(path)

    async def test_concurrent_writes_many_sessions(self):
        import asyncio

        storage = SqlStateStorage(dsn=":memory:")

        async def save(i: int) -> None:
            key = _key(user_id=str(i), chat_id=str(i))
            await storage.set(UserSession(session_key=key, scene_id="bulk", step_id="s", data={"i": str(i)}))

        await asyncio.gather(*(save(i) for i in range(50)))

        self.assertEqual(await storage.count(), 50)
        loaded = await storage.get(_key(user_id="42", chat_id="42"))
        self.assertEqual(loaded.data["i"], "42")


if __name__ == "__main__":
    unittest.main()


class SqliteDsnTests(unittest.TestCase):
    """v1.8.1: DSN вида sqlite:///rel, sqlite:////abs, sqlite+aiosqlite://…"""

    def test_dsn_forms(self):
        self.assertEqual(_sqlite_path("sqlite:///dev.db"), "dev.db")
        self.assertEqual(_sqlite_path("sqlite+aiosqlite:///dev.db"), "dev.db")
        self.assertEqual(_sqlite_path("sqlite:////tmp/x.db"), "/tmp/x.db")
        self.assertEqual(_sqlite_path("sqlite:///:memory:"), ":memory:")
        self.assertEqual(_sqlite_path(":memory:"), ":memory:")
        self.assertEqual(_sqlite_path("/plain.db"), "/plain.db")

    def test_file_url_opens(self):
        st = SqlStateStorage(dsn=f"sqlite:///{os.path.join(tempfile.mkdtemp(), 's.db')}")
        self.assertTrue(os.path.exists(f"{st._dsn}".replace("sqlite:///", "")))


class TestListSceneSqlF34(unittest.IsolatedAsyncioTestCase):
    """F-34: SqlStateStorage.list_scene — снимок сессий сцены (шаг TTL-саметчера)."""

    async def test_filters_by_scene(self):
        storage = SqlStateStorage(dsn=":memory:")
        await storage.set(UserSession(session_key=_key(user_id="1", chat_id="1"),
                                      scene_id="survey", step_id="s2", data={"x": "1"}))
        await storage.set(UserSession(session_key=_key(user_id="2", chat_id="2"),
                                      scene_id="survey", step_id="s5", data={}))
        await storage.set(UserSession(session_key=_key(user_id="3", chat_id="3"),
                                      scene_id="menu", step_id="m", data={}))

        found = await storage.list_scene("survey")
        self.assertEqual({s.session_key.user_id for s in found}, {"1", "2"})
        snap = next(s for s in found if s.session_key.user_id == "1")
        self.assertEqual(snap.step_id, "s2")
        self.assertEqual(snap.data["x"], "1")
        self.assertIsNotNone(snap.updated_at.tzinfo)

        await storage.clear(snap.session_key)  # ключ из снимка — рабочий
        self.assertEqual(await storage.count(), 2)

    async def test_empty_scene(self):
        storage = SqlStateStorage(dsn=":memory:")
        self.assertEqual(await storage.list_scene("nope"), [])
