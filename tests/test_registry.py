"""F-35 (v1.12.5): публичный перечислитель сцен `SceneRegistry.list_scenes()`.

Продукт читал приватный `_scenes` через getattr (152-ФЗ-очистка,
delete_account.py) — обход, запрещённый router/ARCH.md. Норма: публичный
контракт + инвариант 10 (`ARCH-CHANGE: RfI-06-1`, комната engine-contracts,
RFC-06 §1). Форма — только id по возрастанию: новых типов нет, состояние
сцен живёт в StateStorage (F-34), не в реестре.
"""

import unittest

from bot_fork.router import SceneRegistry
from bot_fork.scene import Scene, Step


def _scene(scene_id: str, commands: tuple = ()) -> Scene:
    return Scene(id=scene_id, entry_commands=commands,
                 steps=(Step.text("q", "?", complete=True),))


class TestListScenes(unittest.TestCase):
    def test_empty_registry_returns_empty_tuple(self):
        self.assertEqual(SceneRegistry().list_scenes(), ())

    def test_ids_sorted_ascending(self):
        registry = SceneRegistry()
        # регистрируем вразнохлёст — обещан порядок по возрастанию id
        for sid, cmd in (("survey", "/анкета"), ("menu", "/меню"),
                         ("delete_account", "/удали"), ("anketa", "/reg")):
            registry.register(_scene(sid, (cmd,)))
        listed = registry.list_scenes()
        self.assertIsInstance(listed, tuple)
        self.assertEqual(listed, ("anketa", "delete_account", "menu", "survey"))

    def test_idempotent(self):
        registry = SceneRegistry()
        registry.register(_scene("b", ("/b",)))
        registry.register(_scene("a", ("/a",)))
        self.assertEqual(registry.list_scenes(), registry.list_scenes())

    def test_call_does_not_mutate_registry(self):
        registry = SceneRegistry()
        registry.register(_scene("beta", ("/beta",)))
        registry.register(_scene("alpha", ("/alpha",)))
        scenes_before = dict(registry._scenes)
        commands_before = dict(registry._command_map)
        listed = registry.list_scenes()
        self.assertEqual(registry._scenes, scenes_before)
        self.assertEqual(registry._command_map, commands_before)
        # кортеж — снимок, а не живой view: испортить реестр результатом нельзя
        self.assertIsInstance(listed, tuple)

    def test_scene_without_entry_commands_is_listed(self):
        # 152-ФЗ-очистке нужны ВСЕ сцены, в т.ч. без команд входа (программный старт)
        registry = SceneRegistry()
        registry.register(_scene("hidden"))
        registry.register(_scene("visible", ("/open",)))
        self.assertEqual(registry.list_scenes(), ("hidden", "visible"))


if __name__ == "__main__":
    unittest.main()
