"""
Тесты F-23: запуск сцены из кнопки — payload `scene:<scene_id>` стартует сцену
как entry-команда. Проверяется на обеих платформах; форматы кнопок тоже.
"""

import json
import unittest

from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.adapters.vk import VKAdapter
from bot_fork.app import BotForkApp
from bot_fork.models import Button, IncomingEvent
from bot_fork.scene import Scene, Step


def _scenes() -> tuple:
    menu = Scene(
        id="menu",
        entry_commands=("/start",),
        steps=(
            Step.choice(
                "m",
                "Меню:",
                buttons=(Button("📝 Анкета", "scene:survey"), Button("ℹ️ О боте", "about")),
                transitions={"about": "about"},
            ),
            Step.text("about", "Бот подбирает команды.", complete=True),
        ),
    )
    survey = Scene(
        id="survey",
        entry_commands=("/reg",),
        steps=(Step.text("q1", "Вопрос 1?", next="q2"), Step.text("q2", "Вопрос 2?", complete=True)),
    )
    return menu, survey


class TestSceneButton(unittest.IsolatedAsyncioTestCase):
    def _app(self, platform: str):
        adapter = (
            TelegramAdapter(mock_sender=lambda p: None)
            if platform == "telegram"
            else VKAdapter(mock_sender=lambda p: None)
        )
        app = BotForkApp(platform=platform, adapter=adapter)
        for s in _scenes():
            app.register_scene(s)
        return app

    async def _run(self, platform: str):
        app = self._app(platform)
        key_ev = IncomingEvent(platform=platform, user_id="7", chat_id="7", text="/start", event_id="e1")
        r1 = await app.handle(key_ev)
        self.assertEqual(r1.session_after.scene_id, "menu")
        # кнопка «📝 Анкета» → запуск сцены survey, сессия замещается
        r2 = await app.handle(
            IncomingEvent(platform=platform, user_id="7", chat_id="7", payload="scene:survey", event_id="e2")
        )
        self.assertIsNone(r2.error)
        self.assertEqual(r2.session_after.scene_id, "survey")
        self.assertEqual(r2.session_after.step_id, "q1")
        self.assertIn("Вопрос 1?", r2.messages[0].text)
        # сцена работает дальше как обычно
        r3 = await app.handle(
            IncomingEvent(platform=platform, user_id="7", chat_id="7", text="ответ", event_id="e3")
        )
        self.assertEqual(r3.session_after.step_id, "q2")
        return app

    async def test_scene_button_telegram(self):
        await self._run("telegram")

    async def test_scene_button_vk(self):
        await self._run("vk")

    async def test_scene_button_without_active_session(self):
        app = self._app("telegram")
        r = await app.handle(
            IncomingEvent(platform="telegram", user_id="8", chat_id="8", payload="scene:survey", event_id="e1")
        )
        self.assertEqual(r.session_after.scene_id, "survey")
        self.assertIsNone(r.error)

    async def test_unknown_scene_payload_falls_through(self):
        app = self._app("telegram")
        await app.handle(IncomingEvent(platform="telegram", user_id="9", chat_id="9", text="/start", event_id="e1"))
        r = await app.handle(
            IncomingEvent(platform="telegram", user_id="9", chat_id="9", payload="scene:ghost", event_id="e2")
        )
        # неKnown scene — обычное поведение FSM (невалидная кнопка), сессия цела
        self.assertIsNotNone(r.error)
        self.assertEqual(r.session_after.scene_id, "menu")

    def test_button_formats_on_both_platforms(self):
        tg = TelegramAdapter(mock_sender=lambda p: None)
        vk = VKAdapter(mock_sender=lambda p: None)
        from bot_fork.models import OutgoingMessage

        msg = OutgoingMessage(chat_id="1", text="?", buttons=(Button("📝 Анкета", "scene:survey"),))
        tg_payload = tg.format_outgoing(msg)
        self.assertEqual(tg_payload["reply_markup"]["inline_keyboard"][0][0]["callback_data"], "scene:survey")
        vk_payload = vk.format_outgoing(msg)
        keyboard = json.loads(vk_payload["keyboard"])
        self.assertEqual(json.loads(keyboard["buttons"][0][0]["action"]["payload"])["button"], "scene:survey")


if __name__ == "__main__":
    unittest.main()
