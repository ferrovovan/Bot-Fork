"""
Test suite for T6: DialogRouter and system commands /info, /cancel.
"""

import unittest
from bot_fork.models import Button, IncomingEvent, SessionKey, UserSession
from bot_fork.router import DialogRouter, SceneRegistry
from bot_fork.scene import Scene, Step
from bot_fork.storage import MemoryStateStorage


class TestDialogRouter(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = MemoryStateStorage()
        self.registry = SceneRegistry()

        self.scene = Scene(
            id="info",
            entry_commands=("/info",),
            steps=(
                Step.text("name", "Как к вам обращаться?", next="role"),
                Step.choice(
                    "role",
                    "Выберите роль:",
                    buttons=(Button("Разработчик", "dev"), Button("Фрилансер", "freelance")),
                    complete=True,
                ),
            ),
        )
        self.registry.register(self.scene)
        self.router = DialogRouter(registry=self.registry, storage=self.storage)
        self.key = SessionKey(platform="telegram", user_id="555", chat_id="555")

    async def test_start_scene_via_info_command(self):
        event = IncomingEvent(platform="telegram", user_id="555", chat_id="555", text="/info")
        result = await self.router.route(event)

        self.assertIsNone(result.error)
        self.assertIsNotNone(result.session_after)
        self.assertEqual(result.session_after.scene_id, "info")
        self.assertEqual(result.session_after.step_id, "name")
        self.assertIn("Как к вам обращаться?", result.messages[0].text)

        # Storage should hold the session
        stored = await self.storage.get(self.key)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.step_id, "name")

    async def test_unknown_command_no_session(self):
        event = IncomingEvent(platform="telegram", user_id="555", chat_id="555", text="/unknown")
        result = await self.router.route(event)

        self.assertEqual(result.error.code, "UNKNOWN_COMMAND")
        self.assertIn("Команда не найдена", result.messages[0].text)
        self.assertIsNone(await self.storage.get(self.key))

    async def test_plain_text_no_session(self):
        event = IncomingEvent(platform="telegram", user_id="555", chat_id="555", text="Привет!")
        result = await self.router.route(event)

        self.assertEqual(result.error.code, "NO_ACTIVE_SCENE")
        self.assertIn("Сначала запустите /info", result.messages[0].text)
        self.assertIsNone(await self.storage.get(self.key))

    async def test_cancel_with_active_session(self):
        # Create active session first
        session = UserSession(session_key=self.key, scene_id="info", step_id="name", data={"name": "Тест"})
        await self.storage.set(session)

        event = IncomingEvent(platform="telegram", user_id="555", chat_id="555", text="/cancel")
        result = await self.router.route(event)

        self.assertTrue(result.clear_session)
        self.assertIn("Диалог отменён", result.messages[0].text)
        self.assertIsNone(await self.storage.get(self.key))

    async def test_cancel_without_session_is_idempotent(self):
        event = IncomingEvent(platform="telegram", user_id="555", chat_id="555", text="/cancel")
        result = await self.router.route(event)

        self.assertIn("Активного диалога нет", result.messages[0].text)
        self.assertFalse(result.clear_session)
        self.assertIsNone(await self.storage.get(self.key))

    async def test_restart_scene_with_info(self):
        # Existing session in middle of flow
        session = UserSession(session_key=self.key, scene_id="info", step_id="role", data={"name": "Анна"})
        await self.storage.set(session)

        event = IncomingEvent(platform="telegram", user_id="555", chat_id="555", text="/info")
        result = await self.router.route(event)

        self.assertIn("Анкета начата заново", result.messages[0].text)
        self.assertIn("Как к вам обращаться?", result.messages[0].text)
        # Previous data should be cleared
        stored = await self.storage.get(self.key)
        self.assertEqual(stored.data, {})
        self.assertEqual(stored.step_id, "name")


if __name__ == "__main__":
    unittest.main()
