"""
Test suite for T8, T9, T13: Telegram & VK adapters mapping and mock API tests.
Verifies event normalization and keyboard formatting without external tokens.
"""

import json
import unittest
from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.adapters.vk import VKAdapter
from bot_fork.models import Button, OutgoingMessage


class TestAdapters(unittest.IsolatedAsyncioTestCase):
    def test_telegram_message_normalization(self):
        adapter = TelegramAdapter()
        raw_tg_msg = {
            "update_id": 1001,
            "message": {
                "message_id": 55,
                "from": {"id": 12345, "first_name": "User"},
                "chat": {"id": 12345, "type": "private"},
                "text": "  Привет  ",
            },
        }
        event = adapter.normalize_event(raw_tg_msg)
        self.assertEqual(event.platform, "telegram")
        self.assertEqual(event.user_id, "12345")
        self.assertEqual(event.chat_id, "12345")
        self.assertEqual(event.text, "Привет")
        self.assertIsNone(event.payload)

    def test_telegram_callback_query_normalization(self):
        adapter = TelegramAdapter()
        raw_callback = {
            "update_id": 1002,
            "callback_query": {
                "id": "cb-99",
                "from": {"id": 12345},
                "message": {"chat": {"id": 12345}},
                "data": "developer",
            },
        }
        event = adapter.normalize_event(raw_callback)
        self.assertEqual(event.platform, "telegram")
        self.assertEqual(event.user_id, "12345")
        self.assertEqual(event.payload, "developer")
        self.assertIsNone(event.text)

    def test_telegram_outgoing_formatting(self):
        adapter = TelegramAdapter()
        msg = OutgoingMessage(
            chat_id="12345",
            text="Выберите роль:",
            buttons=(Button("Разработчик", "dev"), Button("Фрилансер", "freelance")),
        )
        formatted = adapter.format_outgoing(msg)
        self.assertEqual(formatted["chat_id"], "12345")
        self.assertEqual(formatted["text"], "Выберите роль:")
        self.assertIn("reply_markup", formatted)
        kb = formatted["reply_markup"]["inline_keyboard"]
        self.assertEqual(len(kb), 2)
        self.assertEqual(kb[0][0]["text"], "Разработчик")
        self.assertEqual(kb[0][0]["callback_data"], "dev")

    def test_vk_message_normalization(self):
        adapter = VKAdapter()
        raw_vk_msg = {
            "type": "message_new",
            "object": {
                "message": {
                    "id": 88,
                    "from_id": 98765,
                    "peer_id": 98765,
                    "text": "Тест VK",
                }
            },
        }
        event = adapter.normalize_event(raw_vk_msg)
        self.assertEqual(event.platform, "vk")
        self.assertEqual(event.user_id, "98765")
        self.assertEqual(event.chat_id, "98765")
        self.assertEqual(event.text, "Тест VK")
        self.assertIsNone(event.payload)

    def test_vk_callback_payload_normalization(self):
        adapter = VKAdapter()
        raw_vk_payload = {
            "type": "message_new",
            "object": {
                "message": {
                    "from_id": 98765,
                    "peer_id": 98765,
                    "payload": json.dumps({"button": "developer"}),
                }
            },
        }
        event = adapter.normalize_event(raw_vk_payload)
        self.assertEqual(event.platform, "vk")
        self.assertEqual(event.payload, "developer")

    def test_vk_outgoing_formatting(self):
        adapter = VKAdapter()
        msg = OutgoingMessage(
            chat_id="98765",
            text="Выберите роль:",
            buttons=(Button("Разработчик", "dev"),),
        )
        formatted = adapter.format_outgoing(msg)
        self.assertEqual(formatted["peer_id"], 98765)
        self.assertIn("keyboard", formatted)
        kb = json.loads(formatted["keyboard"])
        self.assertTrue(kb["inline"])
        self.assertEqual(kb["buttons"][0][0]["action"]["label"], "Разработчик")

    async def test_mock_sender_transmission(self):
        sent = []
        adapter = TelegramAdapter(mock_sender=lambda p: sent.append(p))
        msg = OutgoingMessage(chat_id="111", text="Hello mock")
        await adapter.send(msg)

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["text"], "Hello mock")
        self.assertEqual(len(adapter.sent_messages), 1)


if __name__ == "__main__":
    unittest.main()
