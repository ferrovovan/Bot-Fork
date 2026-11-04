"""
Тесты F-03: UserSession.data — JSON-совместимые значения (Dict[str, Any]).

Проверяет:
- dict/list/int/float/bool/None принимаются и переживают round-trip
  через MemoryStateStorage и SqlStateStorage (JSON-колонка);
- отказ на несериализуемом (set, datetime, объект, tuple, NaN, не-str ключ)
  с ConfigError и понятным текстом — до попадания в хранилище;
- обратная совместимость: старые строковые данные читаются как раньше.
Снятие обёрток в продукте — отдельный пакет (D2.4), здесь только движок.
"""

import datetime
import unittest

from bot_fork.exceptions import ConfigError, StorageError
from bot_fork.models import SessionKey, UserSession
from bot_fork.sql_storage import SqlStateStorage
from bot_fork.storage import MemoryStateStorage


def _key(user_id: str = "101") -> SessionKey:
    return SessionKey(platform="telegram", user_id=user_id, chat_id=user_id)


NESTED = {
    "roles": ["developer", "qa"],
    "profile": {"steam": "id123", "tags": {"vip": True}},
    "count": 3,
    "rating": 4.5,
    "confirmed": False,
    "note": None,
}


class TestSessionDataValidation(unittest.TestCase):
    """Валидация при создании сессии: JSON-совместимое проходит, мусор — ConfigError."""

    def test_accepts_json_types(self):
        s = UserSession(session_key=_key(), scene_id="s", step_id="t", data=dict(NESTED))
        self.assertEqual(s.data["profile"]["tags"]["vip"], True)
        self.assertEqual(s.data["roles"], ["developer", "qa"])

    def test_rejects_non_serializable_with_clear_text(self):
        bad_cases = [
            ({"x": {1, 2}}, "set"),
            ({"x": datetime.datetime.now()}, "datetime"),
            ({"x": object()}, "object"),
            ({"x": ("a", "b")}, "tuple"),
            ({"x": float("nan")}, "NaN"),
            ({"x": float("inf")}, "Infinity"),
            ({"outer": {"inner": [ {1, 2} ]}}, "вложенный set"),
        ]
        for data, label in bad_cases:
            with self.subTest(case=label):
                with self.assertRaises(ConfigError) as cm:
                    UserSession(session_key=_key(), scene_id="s", step_id="t", data=data)
                msg = str(cm.exception)
                self.assertIn("UserSession.data", msg)
                self.assertIn("JSON", msg)

    def test_rejects_non_str_keys(self):
        with self.assertRaises(ConfigError):
            UserSession(session_key=_key(), scene_id="s", step_id="t", data={7: "x"})
        with self.assertRaises(ConfigError):
            UserSession(
                session_key=_key(), scene_id="s", step_id="t",
                data={"x": {1: "вложенный не-str ключ"}},
            )

    def test_backward_compatible_str_data(self):
        # старый контракт Dict[str, str] остаётся валидным подмножеством
        s = UserSession(
            session_key=_key(), scene_id="survey", step_id="steam",
            data={"steam": "profile/123", "имя": "Ваня"},
        )
        self.assertEqual(s.data, {"steam": "profile/123", "имя": "Ваня"})
        self.assertEqual(s.to_dict()["data"], s.data)

    def test_clone_detaches_nested(self):
        s = UserSession(session_key=_key(), scene_id="s", step_id="t", data=dict(NESTED))
        c = s.clone()
        c.data["profile"]["tags"]["vip"] = False
        c.data["roles"].append("admin")
        self.assertIs(s.data["profile"]["tags"]["vip"], True)
        self.assertEqual(len(s.data["roles"]), 2)


class TestMemoryStorageJsonData(unittest.IsolatedAsyncioTestCase):
    async def test_roundtrip_nested(self):
        storage = MemoryStateStorage()
        key = _key()
        await storage.set(
            UserSession(session_key=key, scene_id="survey", step_id="q", data=dict(NESTED))
        )
        loaded = await storage.get(key)
        self.assertEqual(loaded.data, NESTED)
        self.assertIsInstance(loaded.data["profile"], dict)

    async def test_returned_copy_does_not_alias_storage(self):
        storage = MemoryStateStorage()
        key = _key()
        await storage.set(
            UserSession(session_key=key, scene_id="survey", step_id="q", data=dict(NESTED))
        )
        first = await storage.get(key)
        first.data["profile"]["tags"]["vip"] = False
        second = await storage.get(key)
        self.assertIs(second.data["profile"]["tags"]["vip"], True)

    async def test_list_scene_snapshot_detaches_nested(self):
        storage = MemoryStateStorage()
        key = _key()
        await storage.set(
            UserSession(session_key=key, scene_id="survey", step_id="q", data=dict(NESTED))
        )
        snap = (await storage.list_scene("survey"))[0]
        snap.data["roles"].append("admin")
        live = await storage.get(key)
        self.assertEqual(live.data["roles"], ["developer", "qa"])


class TestSqlStorageJsonData(unittest.IsolatedAsyncioTestCase):
    async def test_roundtrip_nested(self):
        storage = SqlStateStorage(dsn=":memory:")
        key = _key()
        await storage.set(
            UserSession(session_key=key, scene_id="survey", step_id="q", data=dict(NESTED))
        )
        loaded = await storage.get(key)
        # JSON round-trip сохраняет структуру и типы (кроме tuple, который запрещён)
        self.assertEqual(loaded.data, NESTED)
        self.assertIsInstance(loaded.data["profile"], dict)
        self.assertIsInstance(loaded.data["roles"], list)
        self.assertIsInstance(loaded.data["count"], int)
        self.assertIsInstance(loaded.data["rating"], float)
        self.assertIs(loaded.data["confirmed"], False)
        self.assertIsNone(loaded.data["note"])
        storage.close()

    async def test_backward_compatible_str_data(self):
        # старые строковые данные читаются как раньше
        storage = SqlStateStorage(dsn=":memory:")
        key = _key()
        await storage.set(
            UserSession(
                session_key=key, scene_id="survey", step_id="steam",
                data={"steam": "profile/123", "имя": "Ваня"},
            )
        )
        loaded = await storage.get(key)
        self.assertEqual(loaded.data["steam"], "profile/123")
        self.assertEqual(loaded.data["имя"], "Ваня")
        storage.close()

    async def test_mixed_str_and_json_columns(self):
        # строки и structures в одной сессии, как это делает продукт после снятия обёрток
        storage = SqlStateStorage(dsn=":memory:")
        key = _key(user_id="77")
        await storage.set(
            UserSession(
                session_key=key, scene_id="survey", step_id="merge",
                data={"answer": "да", "choices": ["a", "b"], "meta": {"n": 2}},
            )
        )
        loaded = await storage.get(key)
        self.assertEqual(loaded.data["answer"], "да")
        self.assertEqual(loaded.data["choices"], ["a", "b"])
        self.assertEqual(loaded.data["meta"], {"n": 2})
        storage.close()

    async def test_list_scene_roundtrip_nested(self):
        storage = SqlStateStorage(dsn=":memory:")
        key = _key(user_id="55")
        await storage.set(
            UserSession(session_key=key, scene_id="survey", step_id="q", data=dict(NESTED))
        )
        snap = (await storage.list_scene("survey"))[0]
        self.assertEqual(snap.data, NESTED)
        storage.close()

    async def test_corrupt_json_row_still_storage_error(self):
        storage = SqlStateStorage(dsn=":memory:")
        key = _key(user_id="99")
        await storage.set(
            UserSession(session_key=key, scene_id="s", step_id="t", data={"x": "y"})
        )
        cur = storage._conn.cursor()
        cur.execute(
            "UPDATE botfork_sessions SET data=? WHERE user_id=?", ("{битый json", "99")
        )
        storage._conn.commit()
        cur.close()
        with self.assertRaises(StorageError):
            await storage.get(key)
        storage.close()

    async def test_constructor_blocks_before_storage(self):
        # несериализуемое не доходит до json.dumps: отказ на уровне модели
        with self.assertRaises(ConfigError):
            UserSession(
                session_key=_key(), scene_id="s", step_id="t",
                data={"answer": object()},
            )


if __name__ == "__main__":
    unittest.main()
