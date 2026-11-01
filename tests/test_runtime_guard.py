"""
Тесты F-18/F-20/F-16: дедупликация событий, хук on_error, флаг брендинга.
Оба адаптера не затрагиваются (логика уровня app/fsm), но проверка идёт
через реальный mock-адаптер платформы vk.
"""

import os
import unittest
from unittest.mock import patch

from bot_fork.adapters.vk import VKAdapter
from bot_fork.app import BotForkApp
from bot_fork.fsm import apply_branding
from bot_fork.models import IncomingEvent
from bot_fork.scene import Scene, Step


def _app_with_scene(**kwargs) -> BotForkApp:
    adapter = VKAdapter(mock_sender=lambda payload: None)
    app = BotForkApp(platform="vk", adapter=adapter, **kwargs)
    app.register_scene(
        Scene(
            id="guard",
            entry_commands=("/guard",),
            steps=(Step.text("q", "Ваш ответ?", complete=True),),
        )
    )
    return app


class TestEventDedupe(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_event_id_produces_no_messages(self):
        app = _app_with_scene()
        event = IncomingEvent(platform="vk", user_id="1", chat_id="1", text="/guard", event_id="ev-1")

        first = await app.handle(event)
        self.assertTrue(first.messages)

        second = await app.handle(event)
        self.assertEqual(second.messages, ())
        self.assertIsNone(second.error)

    async def test_events_without_id_are_never_deduped(self):
        app = _app_with_scene()
        for _ in range(3):
            result = await app.handle(IncomingEvent(platform="vk", user_id="2", chat_id="2", text="/guard"))
            self.assertTrue(result.messages)

    async def test_lru_capacity_bounded(self):
        app = _app_with_scene(dedupe_capacity=3)
        for i in range(5):
            await app.handle(
                IncomingEvent(platform="vk", user_id="3", chat_id="3", text="ответ", event_id=f"e{i}")
            )
        self.assertLessEqual(len(app._seen_event_ids), 3)
        # Вытесненный старый id снова будет обработан (не молча проглочен)
        result = await app.handle(
            IncomingEvent(platform="vk", user_id="3", chat_id="3", text="ответ", event_id="e0")
        )
        self.assertTrue(result.messages)


class TestOnErrorHook(unittest.IsolatedAsyncioTestCase):
    async def test_hook_receives_exception_and_loop_survives(self):
        caught = []

        def hook(exc: Exception, event: IncomingEvent) -> None:
            caught.append((exc, event))

        app = _app_with_scene(on_error=hook)

        async def broken_route(event):
            raise RuntimeError("БД упала")

        app.router.route = broken_route  # имитация внутренней ошибки рантайма

        result = await app.handle(IncomingEvent(platform="vk", user_id="9", chat_id="9", text="привет"))

        self.assertEqual(len(caught), 1)
        self.assertIsInstance(caught[0][0], RuntimeError)
        self.assertEqual(caught[0][1].user_id, "9")
        self.assertEqual(result.error.code, "INTERNAL_ERROR")
        self.assertIn("внутренняя ошибка", result.messages[0].text.lower())

    async def test_async_hook_is_awaited(self):
        caught = []

        async def hook(exc: Exception, event: IncomingEvent) -> None:
            caught.append(exc)

        app = _app_with_scene(on_error=hook)

        async def broken_route(event):
            raise ValueError("сбой")

        app.router.route = broken_route
        await app.handle(IncomingEvent(platform="vk", user_id="9", chat_id="9", text="x"))
        self.assertEqual(len(caught), 1)

    async def test_default_behavior_still_raises(self):
        app = _app_with_scene()  # on_error не задан

        async def broken_route(event):
            raise RuntimeError("сбой")

        app.router.route = broken_route
        with self.assertRaises(RuntimeError):
            await app.handle(IncomingEvent(platform="vk", user_id="9", chat_id="9", text="x"))


class TestBrandingFlag(unittest.TestCase):
    def test_branding_off_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(apply_branding("Привет"), "Привет")

    def test_branding_on_appends_watermark(self):
        with patch.dict(os.environ, {"BOT_FORK_BRANDING": "on"}):
            self.assertTrue(apply_branding("Привет").endswith("Made with Bot Fork"))

    def test_branding_on_still_respects_length_limit(self):
        with patch.dict(os.environ, {"BOT_FORK_BRANDING": "on"}):
            with self.assertRaises(Exception):
                apply_branding("x" * 4096)


if __name__ == "__main__":
    unittest.main()
