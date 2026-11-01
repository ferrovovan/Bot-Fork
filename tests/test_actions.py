"""
Тесты F-04/F-06: async-валидаторы и шага-действия (Step.action).
Покрывает: acceptance действия, мутацию данных, отказ (строка-причина), исключение,
однокнопочный шаг выбора и сквозной проход через BotForkApp на платформе vk
с SqlStateStorage — без реальных токенов.
"""

import unittest

from bot_fork.adapters.vk import VKAdapter
from bot_fork.app import BotForkApp
from bot_fork.fsm import FSMEngine
from bot_fork.models import Button, IncomingEvent, SessionKey, UserSession
from bot_fork.scene import Scene, Step
from bot_fork.sql_storage import SqlStateStorage


async def _async_ok(text: str):
    """Async-валидатор: принимает только цифры."""
    return (text.isdigit(), "Нужны только цифры.")


class TestAsyncValidator(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fsm = FSMEngine()
        self.scene = Scene(
            id="async_val",
            entry_commands=("/aval",),
            steps=(
                Step.text("num", "Введите число", validator=_async_ok, next="end"),
                Step.text("end", "Готово", complete=True),
            ),
        )
        self.key = SessionKey(platform="telegram", user_id="1", chat_id="1")

    async def test_async_validator_rejects(self):
        session = UserSession(session_key=self.key, scene_id="async_val", step_id="num", data={})
        event = IncomingEvent(platform="telegram", user_id="1", chat_id="1", text="abc")

        result = await self.fsm.process_step(event, session, self.scene)

        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "INVALID_INPUT")
        self.assertIn("Нужны только цифры", result.error.message)
        self.assertEqual(result.session_after.step_id, "num")

    async def test_async_validator_accepts(self):
        session = UserSession(session_key=self.key, scene_id="async_val", step_id="num", data={})
        event = IncomingEvent(platform="telegram", user_id="1", chat_id="1", text="42")

        result = await self.fsm.process_step(event, session, self.scene)

        self.assertIsNone(result.error)
        self.assertEqual(result.session_after.step_id, "end")
        self.assertEqual(result.session_after.data["num"], "42")


class TestStepAction(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fsm = FSMEngine()
        self.key = SessionKey(platform="vk", user_id="7", chat_id="7")

    async def _run_text(self, scene: Scene, step_id: str, text: str):
        session = UserSession(session_key=self.key, scene_id=scene.id, step_id=step_id, data={})
        event = IncomingEvent(platform="vk", user_id="7", chat_id="7", text=text)
        return await self.fsm.process_step(event, session, scene)

    async def test_action_mutates_data_and_advances(self):
        def action(value: str, data: dict) -> None:
            data["steam_id"] = value.split("/")[-1]

        scene = Scene(
            id="mut",
            entry_commands=("/mut",),
            steps=(
                Step.text("steam", "Ссылка Steam?", action=action, next="end"),
                Step.text("end", "Готово", complete=True),
            ),
        )

        result = await self._run_text(scene, "steam", "https://steamcommunity.com/profiles/76561197000000000")

        self.assertIsNone(result.error)
        self.assertEqual(result.session_after.step_id, "end")
        self.assertEqual(result.session_after.data["steam_id"], "76561197000000000")

    async def test_async_action_rejection_keeps_step_and_data(self):
        async def action(value: str, data: dict) -> str:
            return "Такой Steam уже зарегистрирован. Отправьте другую ссылку."

        scene = Scene(
            id="rej",
            entry_commands=("/rej",),
            steps=(
                Step.text("steam", "Ссылка Steam?", action=action, next="end"),
                Step.text("end", "Готово", complete=True),
            ),
        )

        result = await self._run_text(scene, "steam", "https://steamcommunity.com/id/dup")

        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "ACTION_REJECTED")
        self.assertIn("уже зарегистрирован", result.messages[0].text)
        # Игрок остался на шаге, данные не сохранились
        self.assertEqual(result.session_after.step_id, "steam")
        self.assertNotIn("steam", result.session_after.data)

    async def test_action_receives_session_context(self):
        seen = {}

        async def action(value: str, data: dict, session) -> None:
            seen["platform"] = session.session_key.platform
            seen["user"] = session.session_key.user_id
            data["who"] = f"{session.session_key.platform}:{session.session_key.user_id}"

        scene = Scene(
            id="ctx",
            entry_commands=("/ctx",),
            steps=(Step.text("q", "Ответ?", action=action, next="end"), Step.text("end", "Ок", complete=True)),
        )

        result = await self._run_text(scene, "q", "да")

        self.assertIsNone(result.error)
        self.assertEqual(seen["platform"], "vk")
        self.assertEqual(result.session_after.data["who"], "vk:7")

    async def test_two_arg_actions_still_work(self):
        calls = []

        def action(value: str, data: dict) -> None:
            calls.append(value)

        scene = Scene(
            id="two",
            entry_commands=("/two",),
            steps=(Step.text("q", "Ответ?", action=action, next="end"), Step.text("end", "Ок", complete=True)),
        )
        await self._run_text(scene, "q", "раз")
        self.assertEqual(calls, ["раз"])

    async def test_action_exception_maps_to_action_error(self):
        def action(value: str, data: dict) -> None:
            raise RuntimeError("база недоступна")

        scene = Scene(
            id="boom",
            entry_commands=("/boom",),
            steps=(
                Step.text("q", "Вопрос?", action=action, next="end"),
                Step.text("end", "Готово", complete=True),
            ),
        )

        result = await self._run_text(scene, "q", "ответ")

        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "ACTION_ERROR")
        self.assertIn("Не получилось сохранить ответ", result.messages[0].text)
        self.assertEqual(result.session_after.step_id, "q")

    async def test_single_button_choice_with_action(self):
        clicks = []

        async def action(value: str, data: dict) -> None:
            clicks.append(value)

        scene = Scene(
            id="one_btn",
            entry_commands=("/one",),
            steps=(
                Step.choice(
                    "confirm",
                    "Подтвердите участие в тестовой игре",
                    buttons=(Button("✅ Подтверждаю", "yes"),),
                    transitions={"yes": "done"},
                    action=action,
                ),
                Step.text("done", "Вы в игре!", complete=True),
            ),
        )

        session = UserSession(session_key=self.key, scene_id="one_btn", step_id="confirm", data={})
        event = IncomingEvent(platform="vk", user_id="7", chat_id="7", payload="yes")

        result = await self.fsm.process_step(event, session, scene)

        self.assertIsNone(result.error)
        self.assertEqual(result.session_after.step_id, "done")
        self.assertEqual(clicks, ["yes"])

    async def test_one_button_rejection_shows_same_button(self):
        def action(value: str, data: dict) -> str:
            return "Вы отклонили уже 3 приглашения — нужен администратор."

        scene = Scene(
            id="decline",
            entry_commands=("/dec",),
            steps=(
                Step.choice(
                    "invite",
                    "Игра найдена!",
                    buttons=(Button("✅ Играть", "ok"),),
                    transitions={"ok": "done"},
                    action=action,
                ),
                Step.text("done", "Ок", complete=True),
            ),
        )

        session = UserSession(session_key=self.key, scene_id="decline", step_id="invite", data={})
        event = IncomingEvent(platform="vk", user_id="7", chat_id="7", payload="ok")

        result = await self.fsm.process_step(event, session, scene)

        self.assertEqual(result.error.code, "ACTION_REJECTED")
        # Кнопка осталась на месте — игрок может попробовать осознанно снова
        self.assertEqual(len(result.messages[0].buttons), 1)
        self.assertEqual(result.messages[0].buttons[0].value, "ok")


class TestAppEndToEndVkSqlite(unittest.IsolatedAsyncioTestCase):
    """Сквозной проход через BotForkApp: vk-адаптер + SqlStateStorage (F-02+F-04+F-11 вместе)."""

    async def test_full_scene_on_vk_with_sqlite_storage(self):
        saved = []

        async def save_agreement(value: str, data: dict) -> None:
            saved.append(data.get("agree"))

        sent = []
        adapter = VKAdapter(mock_sender=lambda payload: sent.append(payload))
        storage = SqlStateStorage(dsn=":memory:")
        app = BotForkApp(platform="vk", adapter=adapter, storage=storage)

        app.register_scene(
            Scene(
                id="opros",
                entry_commands=("/opros",),
                steps=(
                    Step.choice(
                        "agree",
                        "Согласны на обработку данных?",
                        buttons=(Button("Да", "yes"), Button("Нет", "no")),
                        transitions={"yes": "nick", "no": "bye"},
                    ),
                    Step.text("nick", "Ваш ник?", action=save_agreement, next="done"),
                    Step.text("done", "Анкета принята", complete=True),
                    Step.text("bye", "Без согласия анкета невозможна", complete=True),
                ),
            )
        )

        async def deliver(event):  # как это делает polling-цикл адаптера
            result = await app.handle(event)
            for m in result.messages:
                await app.adapter.send(m)
            return result

        # 1. Запуск сцены
        r1 = await deliver(IncomingEvent(platform="vk", user_id="42", chat_id="42", text="/opros"))
        self.assertIn("Согласны", r1.messages[0].text)
        self.assertEqual(await storage.count(), 1)

        # 2. Нажатие кнопки "Да"
        r2 = await deliver(IncomingEvent(platform="vk", user_id="42", chat_id="42", payload="yes"))
        self.assertIn("Ваш ник?", r2.messages[0].text)

        # 3. Текст с async-действием -> переход на финальный шаг
        r3 = await deliver(IncomingEvent(platform="vk", user_id="42", chat_id="42", text="Vovan"))
        self.assertIn("Анкета принята", r3.messages[0].text)
        self.assertFalse(r3.clear_session)
        self.assertEqual(saved, ["yes"])
        self.assertEqual(await storage.count(), 1)

        # 4. Ответ на финальном шаге завершает сцену и очищает сессию
        r4 = await deliver(IncomingEvent(platform="vk", user_id="42", chat_id="42", text="👍"))
        self.assertTrue(r4.clear_session)
        self.assertEqual(await storage.count(), 0)

        # Все четыре ответа ушли в VK-адаптер
        self.assertEqual(len(sent), 4)


if __name__ == "__main__":
    unittest.main()
