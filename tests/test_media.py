"""
Тесты F-01 (вложения) и F-21 (content_type события) — на обоих адаптерах.
Реальные API не дёргаются: mock_sender + нормализация сырых payload'ов.
"""

import unittest

from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.adapters.vk import VKAdapter
from bot_fork.app import BotForkApp
from bot_fork.models import Attachment, OutgoingMessage


class TestAttachmentValidation(unittest.TestCase):
    def test_rejects_bad_kind(self):
        with self.assertRaises(ValueError):
            Attachment(kind="audio", data=b"x", filename="a.mp3")

    def test_rejects_empty_data(self):
        with self.assertRaises(ValueError):
            Attachment(kind="photo", data=b"", filename="chart.png")

    def test_to_dict_has_no_bytes(self):
        att = Attachment(kind="photo", data=b"12345", filename="chart.png", caption="Отчёт")
        d = att.to_dict()
        self.assertEqual(d, {"kind": "photo", "filename": "chart.png", "caption": "Отчёт", "size": 5})


class TestAttachmentDelivery(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_format_carries_attachment(self):
        adapter = TelegramAdapter(mock_sender=lambda p: None)
        msg = OutgoingMessage(
            chat_id="1", text="График", attachment=Attachment("photo", b"\x89PNG", "chart.png")
        )
        formatted = adapter.format_outgoing(msg)
        self.assertEqual(formatted["attachment"]["filename"], "chart.png")
        self.assertEqual(formatted["attachment"]["kind"], "photo")

        await adapter.send(msg)
        self.assertEqual(adapter.sent_messages[-1]["attachment"]["size"], 4)

    async def test_vk_format_carries_attachment(self):
        adapter = VKAdapter(mock_sender=lambda p: None)
        msg = OutgoingMessage(
            chat_id="222",
            text="Выгрузка",
            attachment=Attachment("document", b"CsvData", "players.csv", caption="Игроки"),
        )
        formatted = adapter.format_outgoing(msg)
        self.assertEqual(formatted["attachment"]["kind"], "document")
        self.assertEqual(formatted["attachment"]["filename"], "players.csv")

    async def test_app_send_with_attachment(self):
        sent = []
        adapter = VKAdapter(mock_sender=lambda p: sent.append(p))
        app = BotForkApp(platform="vk", adapter=adapter)
        await app.send(
            "999", "Отчёт за неделю", attachment=Attachment("photo", b"PNG", "week.png")
        )
        self.assertEqual(sent[-1]["attachment"]["filename"], "week.png")


class TestContentType(unittest.TestCase):
    def test_telegram_text_vs_sticker_dict(self):
        adapter = TelegramAdapter()
        text_ev = adapter.normalize_event(
            {"message": {"from": {"id": 1}, "chat": {"id": 1}, "text": "привет"}}
        )
        self.assertEqual(text_ev.content_type, "text")

        sticker_ev = adapter.normalize_event(
            {"message": {"from": {"id": 1}, "chat": {"id": 1}, "sticker": {"file_id": "x"}}}
        )
        self.assertEqual(sticker_ev.content_type, "sticker")

        photo_ev = adapter.normalize_event(
            {"message": {"from": {"id": 1}, "chat": {"id": 1}, "photo": [{"file_id": "x"}]}}
        )
        self.assertEqual(photo_ev.content_type, "photo")

    def test_telegram_aiogram_object(self):
        adapter = TelegramAdapter()

        class Chat:
            id = 5

        class VoiceMsg:
            chat = Chat()
            text = None
            voice = {"file_id": "v"}
            message_id = 7

        ev = adapter.normalize_event(VoiceMsg())
        self.assertEqual(ev.content_type, "voice")

    def test_vk_sticker_and_attachments(self):
        adapter = VKAdapter()
        sticker = adapter.normalize_event({"from_id": 1, "peer_id": 1, "text": "", "sticker": {"x": 1}})
        self.assertEqual(sticker.content_type, "sticker")

        photo = adapter.normalize_event(
            {
                "from_id": 1,
                "peer_id": 1,
                "text": "",
                "attachments": [{"type": "photo", "photo": {}}],
            }
        )
        self.assertEqual(photo.content_type, "photo")

        plain = adapter.normalize_event({"from_id": 1, "peer_id": 1, "text": "ок"})
        self.assertEqual(plain.content_type, "text")


if __name__ == "__main__":
    unittest.main()
