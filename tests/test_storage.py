"""
Test suite for T4: StateStorage and MemoryStateStorage.
Tests get, set, clear, and isolation across 100 concurrent SessionKeys.
"""

import asyncio
import unittest
from bot_fork.models import SessionKey, UserSession
from bot_fork.storage import MemoryStateStorage


class TestStorage(unittest.IsolatedAsyncioTestCase):
    async def test_get_set_clear(self):
        storage = MemoryStateStorage()
        key = SessionKey(platform="telegram", user_id="100", chat_id="100")

        # Initially None
        self.assertIsNone(await storage.get(key))

        # Set session
        session = UserSession(session_key=key, scene_id="info", step_id="name", data={"name": "Иван"})
        await storage.set(session)

        # Retrieve and verify
        retrieved = await storage.get(key)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.scene_id, "info")
        self.assertEqual(retrieved.step_id, "name")
        self.assertEqual(retrieved.data.get("name"), "Иван")

        # Clear is idempotent
        await storage.clear(key)
        self.assertIsNone(await storage.get(key))
        await storage.clear(key)  # Second clear should not raise
        self.assertIsNone(await storage.get(key))

    async def test_100_sessions_isolation(self):
        """Verifies FR-01 and NFR-01: isolating 100 sessions across Telegram and VK."""
        storage = MemoryStateStorage()

        # Insert 100 sessions (50 Telegram, 50 VK)
        for i in range(50):
            key_tg = SessionKey(platform="telegram", user_id=f"u_tg_{i}", chat_id=f"c_tg_{i}")
            key_vk = SessionKey(platform="vk", user_id=f"u_vk_{i}", chat_id=f"c_vk_{i}")

            sess_tg = UserSession(session_key=key_tg, scene_id="info", step_id=f"step_{i}", data={"val": f"tg_{i}"})
            sess_vk = UserSession(session_key=key_vk, scene_id="info", step_id=f"step_{i}", data={"val": f"vk_{i}"})

            await storage.set(sess_tg)
            await storage.set(sess_vk)

        self.assertEqual(await storage.count(), 100)

        # Verify each session is retrieved independently without cross-talk
        for i in range(50):
            key_tg = SessionKey(platform="telegram", user_id=f"u_tg_{i}", chat_id=f"c_tg_{i}")
            key_vk = SessionKey(platform="vk", user_id=f"u_vk_{i}", chat_id=f"c_vk_{i}")

            res_tg = await storage.get(key_tg)
            res_vk = await storage.get(key_vk)

            self.assertEqual(res_tg.data["val"], f"tg_{i}")
            self.assertEqual(res_vk.data["val"], f"vk_{i}")
            self.assertEqual(res_tg.session_key.platform, "telegram")
            self.assertEqual(res_vk.session_key.platform, "vk")


if __name__ == "__main__":
    unittest.main()
