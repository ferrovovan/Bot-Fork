"""
F-13/F-19 (WP3): групповые чаты — chat_type, служебные события, операции адаптеров,
редактирование сообщений. Тесты обеих платформ (telegram + vk), как требует приёмка WP.
"""

from __future__ import annotations

import unittest

from bot_fork import (
    BotForkApp,
    Button,
    IncomingEvent,
    OutgoingMessage,
    PlatformOperationNotSupported,
    Step,
    MemoryStateStorage,
)
from bot_fork.adapters.base import PlatformAdapter
from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.adapters.vk import VKAdapter, VK_CHAT_PEER_BASE


def _survey_scene():
    from bot_fork.scene import SceneDefinition

    return SceneDefinition(
        id="g",
        entry_commands=("/g",),
        start_step_id="one",
        steps=(
            Step.text(id="one", prompt="Шаг 1?", next="two"),
            Step.text(id="two", prompt="Шаг 2?", complete=True),
        ),
    )


class TestTGNormalization(unittest.TestCase):
    """TG: chat_type и сервис-события в normalize_event."""

    def setUp(self):
        self.adapter = TelegramAdapter()

    def test_private_message_chat_type(self):
        ev = self.adapter.normalize_event({
            "update_id": 1,
            "message": {"message_id": 5, "from": {"id": 11}, "chat": {"id": 11, "type": "private"}, "text": "привет"},
        })
        self.assertEqual(ev.chat_type, "private")
        self.assertEqual(ev.event_type, "message")

    def test_group_message_and_service_join(self):
        group_msg = {
            "update_id": 2,
            "message": {
                "message_id": 6,
                "from": {"id": 11},
                "chat": {"id": -1001234, "type": "supergroup"},
                "new_chat_members": [{"id": 77, "is_bot": False, "first_name": "Игрок"}],
            },
        }
        ev = self.adapter.normalize_event(group_msg)
        self.assertEqual(ev.event_type, "system")
        self.assertEqual(ev.system_kind, "member_joined")
        self.assertEqual(ev.user_id, "77")
        self.assertEqual(ev.chat_type, "supergroup")

        leave = {
            "update_id": 3,
            "message": {
                "message_id": 7,
                "from": {"id": 77},
                "chat": {"id": -1001234, "type": "supergroup"},
                "left_chat_member": {"id": 77},
            },
        }
        ev2 = self.adapter.normalize_event(leave)
        self.assertEqual((ev2.event_type, ev2.system_kind), ("system", "member_left"))

    def test_my_chat_member_added_and_removed(self):
        added = self.adapter.normalize_event({
            "update_id": 4,
            "my_chat_member": {
                "from": {"id": 77},
                "chat": {"id": -1001234, "type": "supergroup"},
                "new_chat_member": {"status": "member"},
            },
        })
        self.assertEqual((added.event_type, added.system_kind, added.chat_type),
                         ("system", "bot_added", "supergroup"))

        removed = self.adapter.normalize_event({
            "update_id": 5,
            "my_chat_member": {
                "from": {"id": 77},
                "chat": {"id": -1001234, "type": "supergroup"},
                "new_chat_member": {"status": "kicked"},
            },
        })
        self.assertEqual(removed.system_kind, "bot_removed")

    def test_group_callback_keeps_who_pressed(self):
        """F-19: callback в группе несёт нажавшего (user_id) и саму группу (chat_id)."""
        ev = self.adapter.normalize_event({
            "update_id": 6,
            "callback_query": {
                "id": "cb1",
                "from": {"id": 77},
                "message": {"message_id": 9, "chat": {"id": -1001234, "type": "supergroup"}},
                "data": "vote:yes",
            },
        })
        self.assertEqual(ev.user_id, "77")
        self.assertEqual(ev.chat_id, "-1001234")
        self.assertEqual(ev.chat_type, "supergroup")
        self.assertEqual(ev.payload, "vote:yes")


class TestVKNormalization(unittest.TestCase):
    """VK: беседа по peer_id и действия из message_new.action."""

    def setUp(self):
        self.adapter = VKAdapter()

    def test_chat_vs_private(self):
        peer = VK_CHAT_PEER_BASE + 42
        ev = self.adapter.normalize_event({"object": {"message": {
            "id": 1, "date": 0, "peer_id": peer, "from_id": 77, "text": "го", "out": 0,
        }}})
        self.assertEqual(ev.chat_type, "group")
        self.assertEqual(ev.chat_id, str(peer))

        ev2 = self.adapter.normalize_event({"object": {"message": {
            "id": 2, "date": 0, "peer_id": 77, "from_id": 77, "text": "го", "out": 0,
        }}})
        self.assertEqual(ev2.chat_type, "private")

    def test_action_events(self):
        peer = VK_CHAT_PEER_BASE + 42
        joined = self.adapter.normalize_event({"event_id": "e1", "type": "message_new", "object": {"message": {
            "id": 3, "date": 0, "peer_id": peer, "from_id": 55, "text": "",
            "action": {"type": "chat_invite_user", "member_id": 88},
        }}})
        self.assertEqual(joined.event_type, "system")
        self.assertEqual(joined.system_kind, "member_joined")
        self.assertEqual(joined.user_id, "88")
        self.assertEqual(joined.chat_type, "group")

        kicked = self.adapter.normalize_event({"event_id": "e2", "type": "message_new", "object": {"message": {
            "id": 4, "date": 0, "peer_id": peer, "from_id": 55, "text": "",
            "action": {"type": "chat_kick_user", "member_id": 88},
        }}})
        self.assertEqual(kicked.system_kind, "member_left")

        renamed = self.adapter.normalize_event({"event_id": "e3", "type": "message_new", "object": {"message": {
            "id": 5, "date": 0, "peer_id": peer, "from_id": 55, "text": "",
            "action": {"type": "chat_title_update", "member_id": None, "title": "T1"},
        }}})
        self.assertEqual((renamed.event_type, renamed.system_kind), ("system", "chat_title_changed"))


class TestRouterSystemEvents(unittest.IsolatedAsyncioTestCase):
    """Роутер: system-события не трогают диалог и уходят в хук (обе платформы)."""

    async def _run(self, platform: str):
        seen = []

        async def hook(event: IncomingEvent):
            seen.append((event.system_kind, event.user_id, event.chat_id))

        app = BotForkApp(platform=platform, storage=MemoryStateStorage(), on_system_event=hook)
        app.register_scene(_survey_scene())

        # сначала запустим диалог, чтобы доказать, что событие его не сдвинуло
        await app.handle(IncomingEvent(platform=platform, user_id="77", chat_id="999", text="/g"))
        sys_ev = IncomingEvent(
            platform=platform, user_id="88", chat_id="999",
            event_type="system", system_kind="member_joined", chat_type="group",
        )
        result = await app.handle(sys_ev)
        return app, seen, result

    async def test_telegram_system_swallowed(self):
        app, seen, result = await self._run("telegram")
        self.assertEqual(result.messages, ())
        self.assertIsNone(result.session_after)
        self.assertFalse(result.clear_session)
        self.assertEqual(seen, [("member_joined", "88", "999")])
        # сессия на месте: следующий текст ответит шаг «two», а не начнёт заново
        nxt = await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="999", text="ок"))
        self.assertIn("Шаг 2", nxt.messages[0].text)

    async def test_vk_system_swallowed(self):
        app, seen, result = await self._run("vk")
        self.assertEqual(seen, [("member_joined", "88", "999")])
        self.assertEqual(result.messages, ())

    async def test_system_without_hook_is_silent(self):
        app = BotForkApp(platform="telegram", storage=MemoryStateStorage())
        app.register_scene(_survey_scene())
        result = await app.handle(IncomingEvent(
            platform="telegram", user_id="88", chat_id="999",
            event_type="system", system_kind="bot_added",
        ))
        self.assertEqual(result.messages, ())


class TestChatOperations(unittest.IsolatedAsyncioTestCase):
    """F-13: операции над чатами в мок-режиме — контракт и PlatformOperationNotSupported."""

    async def test_tg_plan_b_operations(self):
        tg = TelegramAdapter()
        with self.assertRaises(PlatformOperationNotSupported):
            await tg.create_chat(["77", "88"], "Катка 5x5")  # боевой путь TG не умеет
        with self.assertRaises(PlatformOperationNotSupported):
            await tg.add_member("-1001234", "77")
        link = await tg.get_invite_link("-1001234")
        self.assertTrue(link.startswith("https://t.me/+"))
        await tg.remove_member("-1001234", "77")
        ops = [o["op"] for o in tg.chat_ops]
        self.assertEqual(ops, ["get_invite_link", "remove_member"])

    async def test_vk_full_support(self):
        vk = VKAdapter()
        chat = await vk.create_chat(["77", "88"], "Катка 5x5")
        self.assertEqual(chat, str(VK_CHAT_PEER_BASE + 1))
        await vk.add_member(chat, "88")
        await vk.remove_member(chat, "88")
        link = await vk.get_invite_link(chat)
        self.assertTrue(link.startswith("https://vk.me/join/"))
        self.assertEqual([o["op"] for o in vk.chat_ops],
                         ["create_chat", "add_member", "remove_member", "get_invite_link"])
        # локальный chat_id для add/remove = peer - 2e9
        self.assertEqual(vk._peer_to_chat_id(chat), 1)

    async def test_base_adapter_default_rejections(self):
        """Сторонний адаптер (web-симулятор) не обязан их реализовать — базовый дефолт."""
        from bot_fork.adapters.base import PlatformAdapter
        from bot_fork.models import HandlerResult as _HR

        class MinimalAdapter(PlatformAdapter):
            @property
            def platform_name(self) -> str:
                return "telegram"

            def normalize_event(self, raw_event):
                raise NotImplementedError

            def format_outgoing(self, message):
                return {}

            async def send(self, message):
                return None

            async def start_polling(self, handler):
                return None

        adapter = MinimalAdapter()
        with self.assertRaises(PlatformOperationNotSupported):
            await adapter.create_chat(["77"], "t")
        with self.assertRaises(PlatformOperationNotSupported):
            await adapter.add_member("1", "2")
        with self.assertRaises(PlatformOperationNotSupported):
            await adapter.remove_member("1", "2")
        with self.assertRaises(PlatformOperationNotSupported):
            await adapter.get_invite_link("1")
        with self.assertRaises(PlatformOperationNotSupported):
            await adapter.edit_message("1", "2", OutgoingMessage(chat_id="1", text="x"))
        # send_ex по дефолту = send и None
        self.assertIsNone(await adapter.send_ex(OutgoingMessage(chat_id="1", text="x")))


class TestMessageEditing(unittest.IsolatedAsyncioTestCase):
    """F-19: send_ex возвращает id; edit_message обновляет карточку (мок-журнал)."""

    async def test_send_ex_and_edit_telegram(self):
        tg = TelegramAdapter()
        msg = OutgoingMessage(chat_id="-1001234", text="Слот: ждут голоса 0/5",
                              buttons=(Button(label="Голосую", value="vote:yes"),))
        mid = await tg.send_ex(msg)
        self.assertEqual(mid, "tg-mock-1")
        await tg.edit_message("-1001234", mid, OutgoingMessage(
            chat_id="-1001234", text="Слот: ждут голоса 1/5",
            buttons=(Button(label="Уже голосовал", value="noop"),),
        ))
        edit = tg.chat_ops[-1]
        self.assertEqual(edit["op"], "edit_message")
        self.assertEqual(edit["message_id"], "tg-mock-1")
        kb = edit["payload"]["reply_markup"]["inline_keyboard"]
        self.assertEqual(kb[0][0]["callback_data"], "noop")

    async def test_send_ex_and_edit_vk(self):
        vk = VKAdapter()
        msg = OutgoingMessage(chat_id=str(VK_CHAT_PEER_BASE + 1), text="Слот: ждут голоса 0/5")
        mid = await vk.send_ex(msg)
        self.assertEqual(mid, "vk-mock-1")
        await vk.edit_message(str(VK_CHAT_PEER_BASE + 1), mid,
                              OutgoingMessage(chat_id=str(VK_CHAT_PEER_BASE + 1), text="Слот: собран"))
        edit = vk.chat_ops[-1]
        self.assertEqual(edit["payload"]["message"], "Слот: собран")

    async def test_edit_with_attachment_rejected(self):
        from bot_fork import Attachment
        vk = VKAdapter()
        with self.assertRaises(PlatformOperationNotSupported):
            await vk.edit_message("1", "1", OutgoingMessage(
                chat_id="1", text="x",
                attachment=Attachment(kind="photo", data=b"png", filename="a.png"),
            ))


if __name__ == "__main__":
    unittest.main()


class RenameChatTests(unittest.IsolatedAsyncioTestCase):
    """F-24: переименование чата (team_name, 03 §6)."""

    async def test_vk_mock_renames(self):
        a = VKAdapter()
        await a.rename_chat("2000000001", "Волки с Уолл-стрит")
        op = [o for o in a.chat_ops if o["op"] == "rename_chat"]
        self.assertEqual(op[0]["title"], "Волки с Уолл-стрит")

    async def test_tg_mock_renames(self):
        a = TelegramAdapter()
        await a.rename_chat("-100555", "Медведи")
        self.assertIn("rename_chat", [o["op"] for o in a.chat_ops])

    async def test_base_default_raises(self):
        class Bare(PlatformAdapter):
            platform_name = "bare"

            def format_outgoing(self, message):
                return {}

            async def send(self, message):
                return None

            def normalize_event(self, update):
                return None

            async def start_polling(self, handler):
                return None

        with self.assertRaises(PlatformOperationNotSupported):
            await Bare().rename_chat("1", "x")
