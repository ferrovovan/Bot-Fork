"""
F-29 (v1.11.1): динамическая клавиатура шага — buttons как функция от сессии
(sync или async) и async prompt. Развилка меню «гость / зарегистрирован».
"""

import unittest

from bot_fork.exceptions import ConfigError
from bot_fork.models import Button, IncomingEvent, SessionKey
from bot_fork.router import DialogRouter, SceneRegistry
from bot_fork.scene import Scene, Step, StepDefinition
from bot_fork.storage import MemoryStateStorage


def _menu_buttons(state: dict):
    async def buttons(session):
        if state.get("registered"):
            return (Button("📝 Пройти заново", "scene:survey"), Button("👥 Моя команда", "team"))
        return (Button("📝 Анкета", "scene:survey"), Button("ℹ️ О боте", "about"))
    return buttons


class TestDynamicButtons(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = MemoryStateStorage()
        self.registry = SceneRegistry()
        self.state = {"registered": False}

        async def about_prompt(session):
            return "Зарегистрирован" if self.state.get("registered") else "Гость"

        self.scene = Scene(
            id="menu",
            entry_commands=("/start",),
            steps=(
                Step.choice(
                    "root",
                    about_prompt,  # async prompt (F-29)
                    buttons=_menu_buttons(self.state),
                    transitions={"about": "about", "team": "team"},
                ),
                Step.info("about", "О проекте.", next="root"),
                Step.info("team", "Команды нет.", next="root"),
            ),
        )
        self.registry.register(self.scene)
        self.router = DialogRouter(registry=self.registry, storage=self.storage)
        self.key = SessionKey(platform="telegram", user_id="777", chat_id="777")

    async def _start(self):
        return await self.router.route(
            IncomingEvent(platform="telegram", user_id="777", chat_id="777", text="/start")
        )

    async def test_async_prompt_and_sync_keyboard_guest(self):
        result = await self._start()
        self.assertIsNone(result.error)
        self.assertIn("Гость", result.messages[0].text)
        values = [b.value for b in result.messages[0].buttons]
        self.assertEqual(values, ["scene:survey", "about"])

    async def test_registered_branch_resolved_live(self):
        self.state["registered"] = True
        result = await self._start()
        self.assertIn("Зарегистрирован", result.messages[0].text)
        values = [b.value for b in result.messages[0].buttons]
        self.assertEqual(values, ["scene:survey", "team"])
        # кнопка живой клавиатуры матчится и ведёт по transitions
        result = await self.router.route(
            IncomingEvent(platform="telegram", user_id="777", chat_id="777", payload="team")
        )
        self.assertIsNone(result.error)
        self.assertIn("Команды нет.", result.messages[0].text)

    async def test_stale_button_gets_resolved_keyboard_back(self):
        # гость получил «О боте», стал зарегистрирован, жмёт устаревшую «about»
        await self._start()
        self.state["registered"] = True
        result = await self.router.route(
            IncomingEvent(platform="telegram", user_id="777", chat_id="777", payload="about")
        )
        self.assertEqual(result.error.code, "INVALID_BUTTON")
        values = [b.value for b in result.messages[0].buttons]
        self.assertEqual(values, ["scene:survey", "team"])  # свежая клавиатура, не гостевая

    async def test_dynamic_keyboard_limited_to_four(self):
        step = StepDefinition(
            id="big",
            prompt="?",
            input_type="choice",
            buttons=lambda session: tuple(Button(f"b{i}", str(i)) for i in range(5)),
        )
        with self.assertRaises(ConfigError):
            await step.resolve_buttons(None)

    def test_info_step_rejects_dynamic_keyboard(self):
        with self.assertRaises(ConfigError):
            StepDefinition(id="i", prompt="x", input_type="info", buttons=lambda s: ())

    async def test_dynamic_buttons_callable_error_wrapped(self):
        def boom(session):
            raise RuntimeError("репозиторий лёг")
        step = StepDefinition(id="s", prompt="?", input_type="choice", buttons=boom)
        with self.assertRaises(ConfigError):
            await step.resolve_buttons(None)


if __name__ == "__main__":
    unittest.main()
