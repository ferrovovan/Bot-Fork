"""F-05: динамический prompt — текст из данных сессии (карточка слота, регламент)."""

import unittest

from bot_fork import BotForkApp, Button, MemoryStateStorage, TelegramAdapter
from bot_fork.exceptions import ConfigError
from bot_fork.models import IncomingEvent
from bot_fork.scene import SceneDefinition, Step


def _event(user_id, text=""):
    return IncomingEvent(platform="telegram", user_id=str(user_id), chat_id=str(user_id), text=text)


class DynamicPromptTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.adapter = TelegramAdapter()
        self.app = BotForkApp(platform="telegram", adapter=self.adapter, storage=MemoryStateStorage())

    def _card_scene(self):
        def card(session):
            d = session.data
            return f"Слот: {d.get('slot', '?')} · состав: {d.get('roster', '?')}"

        return SceneDefinition(
            id="test_confirm", entry_commands=("/slot",), start_step_id="ask", lane="system",
            steps=(Step.choice(id="ask", prompt=card, complete=True,
                               buttons=(Button(label="Да", value="yes"),)),),
        )

    async def test_start_scene_renders_data_card(self):
        self.app.register_scene(self._card_scene())
        res = await self.app.start_scene("test_confirm", user_id="77", chat_id="77",
                                         data={"slot": "сб 18:00", "roster": "5 игроков"})
        self.assertIsNone(res.error)
        self.assertIn("сб 18:00 · состав: 5 игроков", res.messages[0].text)

    async def test_entry_command_prompt_without_data(self):
        self.app.register_scene(self._card_scene())
        res = await self.app.handle(_event(77, "/slot"))
        # данных нет — prompt обязан отрендериться фолбэком, а не упасть
        self.assertIn("Слот: ? · состав: ?", res.messages[0].text)

    async def test_transition_prompt_is_dynamic(self):
        scene = SceneDefinition(
            id="flow", entry_commands=("/flow",), start_step_id="one",
            steps=(
                Step.text(id="one", prompt="Имя?", next="two"),
                Step.text(id="two", prompt=lambda s: f"Привет, {s.data.get('one', '?')}!", complete=True),
            ),
        )
        self.app.register_scene(scene)
        await self.app.handle(_event(88, "/flow"))
        res = await self.app.handle(_event(88, "Ваня"))
        self.assertIn("Привет, Ваня!", res.messages[0].text)

    async def test_zero_arg_callable_ok(self):
        scene = SceneDefinition(
            id="zero", entry_commands=("/zero",), start_step_id="s",
            steps=(Step.text(id="s", prompt=lambda: "Константа из лени", complete=True),),
        )
        self.app.register_scene(scene)
        res = await self.app.handle(_event(90, "/zero"))
        self.assertIn("Константа из лени", res.messages[0].text)

    def test_bad_return_rejected(self):
        step = Step.text(id="x", prompt=lambda s: "")
        with self.assertRaises(ConfigError):
            step.render_prompt(type("S", (), {"data": {}})())

    def test_raising_callable_wrapped(self):
        def boom(session):
            raise KeyError("slot")
        step = Step.text(id="x", prompt=boom)
        with self.assertRaises(ConfigError):
            step.render_prompt(type("S", (), {"data": {}})())


if __name__ == "__main__":
    unittest.main()
