"""
Test suite for T5: FSMEngine: text, choice, transitions, completion, validation.
"""

import unittest
from bot_fork.fsm import FSMEngine
from bot_fork.models import Button, IncomingEvent, SessionKey, UserSession
from bot_fork.scene import Scene, Step


class TestFSMEngine(unittest.TestCase):
    def setUp(self):
        self.fsm = FSMEngine()
        self.scene = Scene(
            id="test_flow",
            entry_commands=("/test",),
            steps=(
                Step.text(
                    "name",
                    "Как вас зовут?",
                    validator=lambda text: (len(text) >= 2, "Имя слишком короткое"),
                    next="branch",
                ),
                Step.choice(
                    "branch",
                    "Выберите путь:",
                    buttons=(Button("Ветка А", "opt_a"), Button("Ветка Б", "opt_b")),
                    transitions={"opt_a": "step_a", "opt_b": "step_b"},
                ),
                Step.text("step_a", "Вы выбрали ветку А", complete=True),
                Step.text("step_b", "Вы выбрали ветку Б", complete=True),
            ),
        )
        self.key = SessionKey(platform="telegram", user_id="101", chat_id="101")

    def test_text_step_valid(self):
        session = UserSession(session_key=self.key, scene_id="test_flow", step_id="name", data={})
        event = IncomingEvent(platform="telegram", user_id="101", chat_id="101", text="Алексей")

        result = self.fsm.process_step(event, session, self.scene)

        self.assertIsNone(result.error)
        self.assertFalse(result.clear_session)
        self.assertIsNotNone(result.session_after)
        self.assertEqual(result.session_after.step_id, "branch")
        self.assertEqual(result.session_after.data.get("name"), "Алексей")
        self.assertIn("Выберите путь:", result.messages[0].text)
        self.assertIn("Made with Bot Fork", result.messages[0].text)

    def test_text_step_invalid_empty(self):
        session = UserSession(session_key=self.key, scene_id="test_flow", step_id="name", data={})
        event = IncomingEvent(platform="telegram", user_id="101", chat_id="101", text="   ")

        result = self.fsm.process_step(event, session, self.scene)

        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "INVALID_INPUT")
        # Session state must NOT be modified
        self.assertEqual(result.session_after.step_id, "name")
        self.assertEqual(result.session_after.data, {})

    def test_text_step_validator_failure(self):
        session = UserSession(session_key=self.key, scene_id="test_flow", step_id="name", data={})
        event = IncomingEvent(platform="telegram", user_id="101", chat_id="101", text="А")

        result = self.fsm.process_step(event, session, self.scene)

        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "INVALID_INPUT")
        self.assertIn("Имя слишком короткое", result.error.message)
        self.assertEqual(result.session_after.step_id, "name")

    def test_choice_step_transition_a(self):
        session = UserSession(
            session_key=self.key,
            scene_id="test_flow",
            step_id="branch",
            data={"name": "Алексей"},
        )
        event = IncomingEvent(platform="telegram", user_id="101", chat_id="101", payload="opt_a")

        result = self.fsm.process_step(event, session, self.scene)

        self.assertIsNone(result.error)
        self.assertEqual(result.session_after.step_id, "step_a")
        self.assertEqual(result.session_after.data.get("branch"), "opt_a")
        self.assertIn("Вы выбрали ветку А", result.messages[0].text)

    def test_choice_step_invalid_payload(self):
        session = UserSession(
            session_key=self.key,
            scene_id="test_flow",
            step_id="branch",
            data={"name": "Алексей"},
        )
        event = IncomingEvent(platform="telegram", user_id="101", chat_id="101", payload="unknown_val")

        result = self.fsm.process_step(event, session, self.scene)

        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "INVALID_BUTTON")
        # State unchanged
        self.assertEqual(result.session_after.step_id, "branch")
        self.assertNotIn("branch", result.session_after.data)

    def test_complete_step_clears_session(self):
        session = UserSession(
            session_key=self.key,
            scene_id="test_flow",
            step_id="step_a",
            data={"name": "Алексей", "branch": "opt_a"},
        )
        event = IncomingEvent(platform="telegram", user_id="101", chat_id="101", text="Завершить")

        result = self.fsm.process_step(event, session, self.scene)

        self.assertTrue(result.clear_session)
        self.assertIsNone(result.session_after)
        self.assertIn("Made with Bot Fork", result.messages[0].text)


if __name__ == "__main__":
    unittest.main()
