"""
Test suite for T11 & FR-07: Demonstration scene /info and final report.
Verifies the exact same scene definition runs through Telegram and VK sequentially.
"""

import unittest
from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.adapters.vk import VKAdapter
from bot_fork.app import BotForkApp
from bot_fork.models import IncomingEvent
from examples.demo_info import info_scene


class TestDemoInfo(unittest.IsolatedAsyncioTestCase):
    async def _run_full_flow(self, platform_name: str):
        adapter_cls = TelegramAdapter if platform_name == "telegram" else VKAdapter
        adapter = adapter_cls()
        app = BotForkApp(platform=platform_name, adapter=adapter)
        app.register_scene(info_scene)

        user_id = f"usr_{platform_name}"
        chat_id = f"chat_{platform_name}"

        # 1. Send /info
        ev1 = IncomingEvent(platform=platform_name, user_id=user_id, chat_id=chat_id, text="/info")
        res1 = await app.handle(ev1)
        self.assertIsNone(res1.error)
        self.assertFalse(res1.clear_session)
        self.assertEqual(res1.session_after.step_id, "name")
        self.assertIn("Как к вам обращаться?", res1.messages[0].text)
        self.assertIn("Made with Bot Fork", res1.messages[0].text)

        # 2. Send name
        ev2 = IncomingEvent(platform=platform_name, user_id=user_id, chat_id=chat_id, text="Дмитрий")
        res2 = await app.handle(ev2)
        self.assertIsNone(res2.error)
        self.assertEqual(res2.session_after.step_id, "role")
        self.assertEqual(res2.session_after.data.get("name"), "Дмитрий")
        self.assertIn("Выберите вашу роль:", res2.messages[0].text)
        self.assertEqual(len(res2.messages[0].buttons), 3)

        # 3. Select role button (developer)
        ev3 = IncomingEvent(platform=platform_name, user_id=user_id, chat_id=chat_id, payload="developer")
        res3 = await app.handle(ev3)
        self.assertIsNone(res3.error)
        self.assertEqual(res3.session_after.step_id, "goal")
        self.assertEqual(res3.session_after.data.get("role"), "developer")
        self.assertIn("Кратко опишите цель проекта.", res3.messages[0].text)

        # 4. Send goal
        ev4 = IncomingEvent(platform=platform_name, user_id=user_id, chat_id=chat_id, text="Прототип бота для хакатона")
        res4 = await app.handle(ev4)
        self.assertIsNone(res4.error)
        self.assertTrue(res4.clear_session)
        self.assertIsNone(res4.session_after)

        # Check final summary report
        report = res4.messages[0].text
        self.assertIn("Спасибо за ответы! Итоги анкеты:", report)
        self.assertIn("Имя: Дмитрий", report)
        self.assertIn("Роль: Разработчик", report)
        self.assertIn("Цель проекта: Прототип бота для хакатона", report)
        self.assertIn("Made with Bot Fork", report)

        # Session should be completely cleared in storage
        cleared = await app.storage.get(ev1.session_key)
        self.assertIsNone(cleared)

    async def test_info_flow_on_telegram(self):
        await self._run_full_flow("telegram")

    async def test_info_flow_on_vk(self):
        await self._run_full_flow("vk")


if __name__ == "__main__":
    unittest.main()
