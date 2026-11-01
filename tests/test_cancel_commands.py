"""F-31 (v1.11.3): набор команд отмены задаёт продукт.

В VK нет меню команд Telegram — игрок печатает руками и по-русски.
DialogRouter/BotForkApp принимают cancel_commands; по-прежнему только
точное совпадение первого токена, регистр не важен.
"""

import unittest

from bot_fork.adapters.vk import VKAdapter
from bot_fork.models import IncomingEvent, SessionKey
from bot_fork.router import DialogRouter, SceneRegistry
from bot_fork.scene import Scene, Step
from bot_fork.storage import MemoryStateStorage


def _scene():
    return Scene(id="info", entry_commands=("/info",),
                 steps=(Step.text("name", "Как вас зовут?", complete=True),))


class TestCancelCommands(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.registry = SceneRegistry()
        self.registry.register(_scene())
        self.storage = MemoryStateStorage()
        self.key = SessionKey(platform="vk", user_id="2001", chat_id="2001")

    def _router(self, **kw):
        return DialogRouter(registry=self.registry, storage=self.storage, **kw)

    async def _start(self, router):
        await router.route(IncomingEvent(platform="vk", user_id="2001", chat_id="2001", text="/info"))
        self.assertIsNotNone(await self.storage.get(self.key))

    async def test_alias_cancels(self):
        router = self._router(cancel_commands=("/cancel", "/отмена"))
        await self._start(router)
        result = await router.route(
            IncomingEvent(platform="vk", user_id="2001", chat_id="2001", text="/Отмена")
        )
        self.assertIsNone(result.error)
        self.assertIsNone(await self.storage.get(self.key))

    async def test_default_knows_only_cancel(self):
        router = self._router()
        await self._start(router)
        result = await router.route(
            IncomingEvent(platform="vk", user_id="2001", chat_id="2001", text="/отмена")
        )
        # без алиаса «/отмена» — не команда отмены: активная сцена съедит её
        # как ответ, слово «отменён» в ответе не зазвучит
        self.assertNotIn("отменён", result.messages[0].text)

    async def test_app_passes_aliases(self):
        app = BotForkAppSafe(platform="vk", cancel_commands=("/cancel", "/отмена"))
        self.assertEqual(app.router.cancel_commands, ("/cancel", "/отмена"))


def BotForkAppSafe(platform, **kw):
    from bot_fork import BotForkApp
    return BotForkApp(platform=platform, adapter=VKAdapter(mock_sender=lambda p: None), **kw)


if __name__ == "__main__":
    unittest.main()


class TestCancelHint(unittest.IsolatedAsyncioTestCase):
    """F-32: подсказка после отмены — живые команды реестра, не демо-/info."""

    async def test_hint_names_real_command(self):
        registry = SceneRegistry()
        registry.register(Scene(id="anketa", entry_commands=("/анкета", "/reg"),
                                steps=(Step.text("q", "?", complete=True),)))
        router = DialogRouter(registry=registry, storage=MemoryStateStorage())
        await router.route(IncomingEvent(platform="vk", user_id="3001", chat_id="3001",
                                         text="/анкета"))
        r = await router.route(IncomingEvent(platform="vk", user_id="3001", chat_id="3001",
                                             text="/cancel"))
        self.assertIn("Заново — /анкета.", r.messages[0].text)
        self.assertNotIn("/info", r.messages[0].text)

    async def test_scene_without_commands_no_phantom_hint(self):
        registry = SceneRegistry()
        registry.register(Scene(id="hidden", entry_commands=(),
                                steps=(Step.text("q", "?", complete=True),)))
        router = DialogRouter(registry=registry, storage=MemoryStateStorage())
        from bot_fork.models import SessionKey
        scene = registry.get_scene("hidden")
        key = SessionKey(platform="vk", user_id="3002", chat_id="3002").with_lane("user")
        await router.begin_scene(scene, key, "3002", had_session=False)
        r = await router.route(IncomingEvent(platform="vk", user_id="3002", chat_id="3002",
                                             text="/cancel"))
        self.assertIn("Диалог отменён", r.messages[0].text)
        self.assertNotIn("/info", r.messages[0].text)
