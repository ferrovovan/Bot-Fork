"""
F-06 (lanes) и F-22 (программный вход в сцену) — WP4.
Главный сценарий приёмки из 07: «анкета + подтверждение слота» без потери данных.
"""

from __future__ import annotations

import sqlite3
import unittest

from bot_fork import (
    BotForkApp,
    Button,
    IncomingEvent,
    MemoryStateStorage,
    SessionKey,
    Step,
    TelegramAdapter,
)
from bot_fork.exceptions import ConfigError
from bot_fork.scene import SceneDefinition
from bot_fork.sql_storage import SqlStateStorage


def _survey():
    return SceneDefinition(
        id="survey",
        entry_commands=("/reg",),
        start_step_id="s1",
        steps=(
            Step.text(id="s1", prompt="Вопрос 1", next="s2"),
            Step.text(id="s2", prompt="Вопрос 2", next="s3"),
            Step.text(id="s3", prompt="Вопрос 3", complete=True),
        ),
    )


def _confirm():
    return SceneDefinition(
        id="confirm",
        entry_commands=(),
        start_step_id="ask",
        lane="system",
        steps=(
            Step.choice(
                id="ask",
                prompt="Подтверждаете слот?",
                buttons=(Button(label="Да", value="yes"), Button(label="Нет", value="no")),
                complete=True,
            ),
        ),
    )


class TestSessionKeyLane(unittest.TestCase):
    def test_defaults_and_validation(self):
        k = SessionKey(platform="telegram", user_id="1", chat_id="2")
        self.assertEqual(k.lane, "user")  # обратная совместимость
        self.assertEqual(k.with_lane("system").lane, "system")
        self.assertNotEqual(k, k.with_lane("system"))  # разные слоты — разные ключи
        self.assertEqual(k.to_dict()["lane"], "user")
        with self.assertRaises(ValueError):
            SessionKey(platform="telegram", user_id="1", chat_id="2", lane="admin")

    def test_scene_lane_validation(self):
        with self.assertRaises(ConfigError):
            SceneDefinition(id="x", entry_commands=(), start_step_id="a",
                            steps=(Step.text(id="a", prompt="p", complete=True),), lane="vip")


class TestLanesRouting(unittest.IsolatedAsyncioTestCase):
    """Роутер: system перехватывает, завершается — анкета продолжается с того же шага."""

    def _app(self):
        app = BotForkApp(platform="telegram", storage=MemoryStateStorage())
        app.register_scene(_survey())
        app.register_scene(_confirm())
        return app

    async def test_confirm_interrupts_survey_without_data_loss(self):
        app = self._app()
        # игрок проходит анкету: шаг 1 → шаг 2
        await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="/reg"))
        await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="Иван"))
        # jobs достраивают system-сцену поверх (F-22)
        res = await app.start_scene("confirm", user_id="77", chat_id="77")
        self.assertIn("Подтверждаете слот?", res.messages[0].text)
        self.assertEqual(res.session_after.session_key.lane, "system")

        # случайное сообщение игрока перехватывает system-сцена, а не анкета
        res = await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77",
                                             payload="yes"))
        self.assertTrue(res.clear_session)  # confirm (system-слот) завершён

        # system завершилась → следующий ход возвращается в анкету на её же шаг
        res = await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="вопрос2"))
        self.assertIn("Вопрос 3", res.messages[0].text)  # шаг s2 принят, ждём s3 — данные целы

        res = await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="вопрос3"))
        self.assertTrue(res.clear_session)
        self.assertIn("вопрос2", res.messages[0].text)  # ответ анкеты дошёл до итога

    async def test_system_scene_ignores_user_entry_command_replacement(self):
        """Команда user-сцены во время system-перехвата пишет в user-слот, перехват жив."""
        app = self._app()
        await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="/reg"))
        await app.start_scene("confirm", user_id="77", chat_id="77")
        res = await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="/reg"))
        # перезапустилась анкета (user-слот), но следующий ответ по-прежнему перехватывает confirm
        self.assertIn("Вопрос 1", res.messages[0].text)
        res = await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77",
                                             payload="no"))
        self.assertTrue(res.clear_session)
        # и только теперь текст уходит в анкету (s1 → s2)
        res = await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="Пётр"))
        self.assertIn("Вопрос 2", res.messages[0].text)

    async def test_cancel_takes_system_first_then_user(self):
        app = self._app()
        await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="/reg"))
        await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="Иван"))
        await app.start_scene("confirm", user_id="77", chat_id="77")

        await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="/cancel"))
        # system снят, анкета цела и снова верхняя: ответ Х принимает шаг s2
        res = await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="Х"))
        self.assertIn("Вопрос 3", res.messages[0].text)

        await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="/cancel"))
        res = await app.handle(IncomingEvent(platform="telegram", user_id="77", chat_id="77", text="Й"))
        self.assertIsNotNone(res.error)  # диалогов нет


class TestStartScene(unittest.IsolatedAsyncioTestCase):
    async def test_start_scene_delivers_prompt_and_initial_data(self):
        adapter = TelegramAdapter()  # mock-режим
        app = BotForkApp(platform="telegram", adapter=adapter, storage=MemoryStateStorage())
        app.register_scene(_confirm())
        res = await app.start_scene("confirm", user_id="77", chat_id="77", data={"slot_id": "42"})
        self.assertEqual(len(adapter.sent_messages), 1)  # prompt доставлен адаптером
        self.assertEqual(res.session_after.data["slot_id"], "42")
        with self.assertRaises(ConfigError):
            await app.start_scene("ghost", user_id="77", chat_id="77")

    async def test_restart_in_same_lane(self):
        app = BotForkApp(platform="telegram", storage=MemoryStateStorage())
        app.register_scene(_confirm())
        await app.start_scene("confirm", user_id="77", chat_id="77")
        res = await app.start_scene("confirm", user_id="77", chat_id="77")
        self.assertIn("заново", res.messages[0].text)  # перезапуск в той же полосе

    async def test_start_scene_vk_platform_key(self):
        app = BotForkApp(platform="vk", storage=MemoryStateStorage())
        app.register_scene(_confirm())
        res = await app.start_scene("confirm", user_id="1", chat_id="2000000001")
        self.assertEqual(res.session_after.session_key.platform, "vk")
        self.assertEqual(res.session_after.session_key.lane, "system")


class TestSqlLanePersistence(unittest.IsolatedAsyncioTestCase):
    async def test_two_lanes_in_sql_and_migration_from_v1(self):
        storage = SqlStateStorage(":memory:")
        from bot_fork.models import UserSession
        k_user = SessionKey(platform="telegram", user_id="7", chat_id="7")
        k_sys = k_user.with_lane("system")
        await storage.set(UserSession(session_key=k_user, scene_id="survey", step_id="s2", data={"s1": "Иван"}))
        await storage.set(UserSession(session_key=k_sys, scene_id="confirm", step_id="ask", data={}))
        self.assertEqual(await storage.count(), 2)  # PK учитывает lane
        sess = await storage.get(k_user)
        self.assertEqual(sess.data["s1"], "Иван")
        await storage.clear(k_sys)
        self.assertEqual(await storage.count(), 1)
        self.assertIsNotNone(await storage.get(k_user))

    def test_v1_table_migrates_to_v2(self):
        """Старая база (PK без lane) переживает апгрейд: строки остаются в user-слоте."""
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.execute(
            """CREATE TABLE botfork_sessions (
                platform TEXT NOT NULL, user_id TEXT NOT NULL, chat_id TEXT NOT NULL,
                scene_id TEXT NOT NULL, step_id TEXT NOT NULL, data TEXT NOT NULL,
                updated_at TEXT NOT NULL, PRIMARY KEY (platform, user_id, chat_id))"""
        )
        conn.execute(
            "INSERT INTO botfork_sessions VALUES (?,?,?,?,?,?,?)",
            ("telegram", "7", "7", "survey", "s2", '{"s1": "Иван"}', "2026-11-01T00:00:00+00:00"),
        )
        conn.commit()

        storage = SqlStateStorage(connection_factory=lambda: conn)  # триггерит _ensure_schema
        import asyncio
        sess = asyncio.run(storage.get(SessionKey(platform="telegram", user_id="7", chat_id="7")))
        self.assertIsNotNone(sess)
        self.assertEqual(sess.data["s1"], "Иван")
        self.assertEqual(sess.step_id, "s2")
        # старая таблица переименована корректно, дубликатов нет
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {r[0] for r in cur.fetchall()}
        self.assertEqual(names, {"botfork_sessions"})


if __name__ == "__main__":
    unittest.main()
