"""
F-25: инфо-шаг (Step.info) — печатает и идёт дальше без ввода; и честный
INVALID_BUTTON, когда кнопка прилетает в текстовый шаг (живая приёмка:
после «О проекте» любая кнопка отвечала «Ответ не должен быть пустым»).
"""

import unittest

from bot_fork.app import BotForkApp
from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.exceptions import ConfigError
from bot_fork.models import Button, IncomingEvent
from bot_fork.scene import Scene, Step


def _app() -> BotForkApp:
    app = BotForkApp(platform="telegram", adapter=TelegramAdapter(mock_sender=lambda p: None))
    app.register_scene(Scene(
        id="menu",
        entry_commands=("/start",),
        steps=(
            Step.choice(
                "root", "Меню:",
                buttons=(Button("ℹ️ О боте", "about"), Button("⚙️ Ещё", "more")),
                transitions={"about": "about", "more": "more"},
            ),
            Step.info("about", "Бот подбирает команды.", next="root"),
            Step.choice(
                "more", "Что ещё?",
                buttons=(Button("Назад", "root_btn"),),
                transitions={"root_btn": "root"},
            ),
        ),
    ))
    app.register_scene(Scene(
        id="chain",
        entry_commands=("/chain",),
        steps=(
            Step.choice("q", "Выбор?", buttons=(Button("Дальше", "i1"),), transitions={"i1": "i1"}),
            Step.info("i1", "Инфа 1.", next="i2"),
            Step.info("i2", "Инфа 2 (финал).", complete=True),
        ),
    ))
    # F-33: сцена из одного info-шага (документ/правила)
    app.register_scene(Scene(
        id="doc",
        entry_commands=("/doc",),
        steps=(Step.info("doc", "Политика. Точка."),),
        on_complete=lambda session: None,
    ))
    # F-33: info первым, потом шаг с вводом — встать на ввод, не глотать его
    app.register_scene(Scene(
        id="infomix",
        entry_commands=("/infomix",),
        steps=(
            Step.info("lead", "Сначала прочти.", next="ask"),
            Step.text("ask", "Твой ответ?"),
        ),
    ))
    return app


class TestInfoStart(unittest.IsolatedAsyncioTestCase):
    """F-33: info-шаг как ПЕРВЫЙ шаг сцены авто-завершается на старте."""

    async def test_scene_of_single_info_completes_on_start(self):
        app = _app()
        r = await app.handle(IncomingEvent(platform="telegram", user_id="u", chat_id="u", text="/doc"))
        self.assertEqual([m.text for m in r.messages], ["Политика. Точка."])
        self.assertIsNone(r.session_after)  # сцена завершилась сразу (F-33)

    async def test_info_then_input_step_parks_on_input(self):
        app = _app()
        r = await app.handle(IncomingEvent(platform="telegram", user_id="u", chat_id="u", text="/infomix"))
        self.assertEqual([m.text for m in r.messages], ["Сначала прочти.", "Твой ответ?"])
        self.assertEqual(r.session_after.scene_id, "infomix")
        self.assertEqual(r.session_after.step_id, "ask")
        r = await app.handle(IncomingEvent(platform="telegram", user_id="u", chat_id="u", text="да"))
        self.assertIsNone(r.error)  # текст дошёл до шага, не проглочен


class TestInfoStep(unittest.IsolatedAsyncioTestCase):
    async def test_info_returns_to_menu_and_old_buttons_work(self):
        app = _app()
        r = await app.handle(IncomingEvent(platform="telegram", user_id="u", chat_id="u", text="/start"))
        self.assertIn("Меню:", r.messages[0].text)
        # «О проекте» → текст и сам возврат в меню, сессия снова на root
        r = await app.handle(IncomingEvent(platform="telegram", user_id="u", chat_id="u", payload="about"))
        self.assertEqual([m.text.splitlines()[0] for m in r.messages],
                         ["Бот подбирает команды.", "Меню:"])
        self.assertEqual(r.session_after.step_id, "root")
        # следующая кнопка со старого сообщения меню работает — не «пустой ответ»
        r = await app.handle(IncomingEvent(platform="telegram", user_id="u", chat_id="u", payload="more"))
        self.assertIn("Что ещё?", r.messages[0].text)
        self.assertNotIn("пустым", r.messages[0].text)

    async def test_info_chain_until_completion(self):
        app = _app()
        await app.handle(IncomingEvent(platform="telegram", user_id="u", chat_id="u", text="/chain"))
        r = await app.handle(IncomingEvent(platform="telegram", user_id="u", chat_id="u", payload="i1"))
        texts = [m.text for m in r.messages]
        self.assertIn("Инфа 1.", texts[0])
        self.assertIn("Инфа 2 (финал).", texts[1])
        self.assertTrue(r.clear_session)

    async def test_payload_at_text_step_is_invalid_button(self):
        app = _app()
        app.register_scene(Scene(
            id="ask", entry_commands=("/ask",),
            steps=(Step.text("name", "Имя?"),),
        ))
        await app.handle(IncomingEvent(platform="telegram", user_id="u", chat_id="u", text="/ask"))
        r = await app.handle(IncomingEvent(platform="telegram", user_id="u", chat_id="u", payload="about"))
        self.assertEqual(r.error.code, "INVALID_BUTTON")
        self.assertNotIn("пустым", r.messages[0].text)

    async def test_info_rejects_buttons(self):
        from bot_fork.scene import StepDefinition
        with self.assertRaises(ConfigError):
            StepDefinition(id="i", prompt="нельзя", input_type="info",
                           buttons=(Button("а", "а"),))


if __name__ == "__main__":
    unittest.main()
