"""
Test suite for T2: Universal models and error types.
"""

import unittest
from bot_fork.models import (
    Button,
    ErrorInfo,
    HandlerResult,
    IncomingEvent,
    OutgoingMessage,
    SessionKey,
    UserSession,
)


class TestModels(unittest.TestCase):
    def test_session_key_validation(self):
        key = SessionKey(platform="telegram", user_id="101", chat_id="101")
        self.assertEqual(key.platform, "telegram")
        self.assertEqual(key.user_id, "101")
        self.assertEqual(key.chat_id, "101")

        # Invalid platform
        with self.assertRaises(ValueError):
            SessionKey(platform="discord", user_id="101", chat_id="101")

        # Empty user_id or chat_id
        with self.assertRaises(ValueError):
            SessionKey(platform="vk", user_id="", chat_id="101")

    def test_session_key_isolation(self):
        key_tg = SessionKey(platform="telegram", user_id="101", chat_id="101")
        key_vk = SessionKey(platform="vk", user_id="101", chat_id="101")
        self.assertNotEqual(key_tg, key_vk)
        self.assertNotEqual(hash(key_tg), hash(key_vk))

    def test_button_constraints(self):
        btn = Button(label="Разработчик", value="developer")
        self.assertEqual(btn.label, "Разработчик")
        self.assertEqual(btn.value, "developer")

        # Label too long (> 40 chars)
        with self.assertRaises(ValueError):
            Button(label="A" * 41, value="val")

        # Value too long (> 64 chars)
        with self.assertRaises(ValueError):
            Button(label="Label", value="V" * 65)

        # Empty label
        with self.assertRaises(ValueError):
            Button(label="", value="val")

    def test_incoming_event(self):
        event = IncomingEvent(
            platform="telegram",
            user_id="200",
            chat_id="200",
            text="  /info   ",
            payload=None,
            event_id="tg-1",
        )
        self.assertEqual(event.text, "/info")  # Trimmed
        self.assertEqual(event.session_key.platform, "telegram")
        self.assertEqual(event.session_key.user_id, "200")

    def test_outgoing_message_button_limit(self):
        buttons = (
            Button("1", "1"),
            Button("2", "2"),
            Button("3", "3"),
            Button("4", "4"),
        )
        msg = OutgoingMessage(chat_id="200", text="Test", buttons=buttons)
        self.assertEqual(len(msg.buttons), 4)

        # 5 buttons should raise ValueError
        with self.assertRaises(ValueError):
            OutgoingMessage(chat_id="200", text="Test", buttons=buttons + (Button("5", "5"),))

    def test_error_info_and_handler_result(self):
        err = ErrorInfo(code="INVALID_INPUT", message="Ответ не должен быть пустым", retryable=True)
        res = HandlerResult(
            messages=(OutgoingMessage(chat_id="1", text="Prompt"),),
            clear_session=False,
            error=err,
        )
        self.assertEqual(res.error.code, "INVALID_INPUT")
        self.assertTrue(res.error.retryable)
        self.assertFalse(res.clear_session)
        self.assertEqual(len(res.messages), 1)


if __name__ == "__main__":
    unittest.main()
