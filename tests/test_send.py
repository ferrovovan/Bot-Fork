"""
Тесты F-11: BotForkApp.send() — инициативная отправка сообщения пользователю.
Проверяется на обоих адаптерах (telegram и vk) через mock_sender без реальных токенов.
"""

import unittest

from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.adapters.vk import VKAdapter
from bot_fork.app import BotForkApp
from bot_fork.models import Button


class TestAppProactiveSend(unittest.IsolatedAsyncioTestCase):
    async def test_send_telegram_text_and_buttons(self):
        sent_payloads = []
        adapter = TelegramAdapter(mock_sender=lambda payload: sent_payloads.append(payload))
        app = BotForkApp(platform="telegram", adapter=adapter)

        await app.send("12345", "Игра найдена!", buttons=(Button("✅ Подтвердить", "confirm_game"),))

        self.assertEqual(len(sent_payloads), 1)
        payload = sent_payloads[0]
        self.assertEqual(payload["chat_id"], "12345")
        self.assertEqual(payload["text"], "Игра найдена!")
        keyboard = payload["reply_markup"]["inline_keyboard"]
        self.assertEqual(keyboard[0][0]["text"], "✅ Подтвердить")
        self.assertEqual(keyboard[0][0]["callback_data"], "confirm_game")
        # Продублировано в журнал адаптера
        self.assertEqual(adapter.sent_messages, sent_payloads)

    async def test_send_vk_text_and_buttons(self):
        sent_payloads = []
        adapter = VKAdapter(mock_sender=lambda payload: sent_payloads.append(payload))
        app = BotForkApp(platform="vk", adapter=adapter)

        await app.send("987654321", "Отчёт готов", buttons=(Button("📊 Показать", "show_report"),))

        self.assertEqual(len(sent_payloads), 1)
        payload = sent_payloads[0]
        self.assertEqual(payload["peer_id"], 987654321)
        self.assertEqual(payload["message"], "Отчёт готов")
        self.assertIn("show_report", payload["keyboard"])
        self.assertIn("📊 Показать", payload["keyboard"])

    async def test_send_without_buttons(self):
        adapter = TelegramAdapter(mock_sender=lambda payload: None)
        app = BotForkApp(platform="telegram", adapter=adapter)

        await app.send("42", "Просто текст")

        payload = adapter.sent_messages[-1]
        self.assertEqual(payload["text"], "Просто текст")
        self.assertNotIn("reply_markup", payload)


if __name__ == "__main__":
    unittest.main()
