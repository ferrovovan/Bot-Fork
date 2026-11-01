"""F-09: on_complete — завершение сцены решает сама сцена, generic-отчёт остаётся фолбэком."""

import unittest

from bot_fork import BotForkApp, Button, MemoryStateStorage, TelegramAdapter
from bot_fork.models import IncomingEvent, OutgoingMessage
from bot_fork.scene import SceneDefinition, Step


def _event(text="", payload=None, user="77"):
    return IncomingEvent(platform="telegram", user_id=user, chat_id=user, text=text, payload=payload)


def _scene(on_complete):
    return SceneDefinition(
        id="confirm", entry_commands=("/c",), start_step_id="ask",
        steps=(Step.choice(id="ask", prompt="Подтверждаете?", complete=True,
                           buttons=(Button(label="Да", value="ok"),)),),
        on_complete=on_complete,
    )


class OnCompleteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = BotForkApp(platform="telegram", adapter=TelegramAdapter(), storage=MemoryStateStorage())

    async def _finish(self, on_complete):
        self.app.register_scene(_scene(on_complete))
        await self.app.handle(_event("/c"))
        return await self.app.handle(_event(payload="ok"))

    async def test_str_result(self):
        res = await self._finish(lambda s: "Принято ✓")
        self.assertEqual([m.text for m in res.messages], ["Принято ✓"])
        self.assertTrue(res.clear_session)

    async def test_list_result_multiple_messages(self):
        res = await self._finish(lambda s: ["Раз", "Два"])
        self.assertEqual([m.text for m in res.messages], ["Раз", "Два"])

    async def test_none_means_silent_completion(self):
        res = await self._finish(lambda s: None)
        self.assertEqual(res.messages, ())
        self.assertTrue(res.clear_session)  # сессия всё равно снята

    async def test_async_on_complete_awaited(self):
        async def finish(s):
            return f"async ок ({s.data['ask']})"
        res = await self._finish(finish)
        self.assertIn("async ок", res.messages[0].text)

    async def test_outgoing_message_passes_through(self):
        res = await self._finish(lambda s: [OutgoingMessage(chat_id="", text="готово",
                                                            buttons=(Button("Ок", "k"),))])
        self.assertEqual(res.messages[0].text, "готово")
        self.assertEqual(res.messages[0].chat_id, "77")  # chat_id подставлен из события

    async def test_crash_falls_back_to_generic(self):
        def boom(s):
            raise RuntimeError("сервис лёг")
        res = await self._finish(boom)
        self.assertIn("Сценарий завершён", res.messages[0].text)

    async def test_no_on_complete_generic_report(self):
        res = await self._finish(None)
        self.assertIn("Сценарий завершён", res.messages[0].text)


if __name__ == "__main__":
    unittest.main()
