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
