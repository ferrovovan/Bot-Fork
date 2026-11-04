"""F-36 (v1.12.6): кнопки продолжения после `/cancel` задаёт продукт.

Механизм в движке (`cancel_buttons`, симметрия F-31), политика — в продукте:
движок прикрепляет переданные кнопки к обоим служебным ответам отмены и не
изобретает подписей (урок F-32). Пусто по умолчанию — текстовый ответ как
раньше. Форма — RFC-06 §2 (`ARCH-CHANGE: RfI-06-2`).
"""

import unittest

from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.adapters.vk import VKAdapter
from bot_fork.models import Button, IncomingEvent, SessionKey
from bot_fork.router import DialogRouter, SceneRegistry
from bot_fork.scene import Scene, Step
from bot_fork.storage import MemoryStateStorage

MENU = Button("🏠 В меню", "scene:menu")
HELP = Button("Справка", "scene:help")


def _scene():
    return Scene(id="info", entry_commands=("/info",),
                 steps=(Step.text("q", "?", complete=True),))


def _event(text: str, platform: str = "vk", user_id: str = "1001") -> IncomingEvent:
    return IncomingEvent(platform=platform, user_id=user_id, chat_id=user_id, text=text)


class TestCancelButtons(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.registry = SceneRegistry()
        self.registry.register(_scene())

    def _router(self, **kw):
        return DialogRouter(registry=self.registry, storage=MemoryStateStorage(), **kw)

    async def _active_user(self, router, platform="vk", user_id="1001"):
        await router.route(_event("/info", platform, user_id))

    async def test_cancel_of_active_dialog_carries_buttons(self):
        router = self._router(cancel_buttons=(MENU,))
        await self._active_user(router)
        r = await router.route(_event("/cancel"))
        self.assertIn("Диалог отменён", r.messages[0].text)
        self.assertEqual(r.messages[0].buttons, (MENU,))

    async def test_no_active_dialog_branch_also_carries_buttons(self):
        # ветка «Активного диалога нет» — без сцены; кнопка возврата нужна и здесь
        router = self._router(cancel_buttons=(MENU, HELP))
        r = await router.route(_event("/cancel"))
        self.assertIn("Активного диалога нет", r.messages[0].text)
        self.assertEqual(r.messages[0].buttons, (MENU, HELP))

    async def test_default_no_buttons_backward_compatible(self):
        for start, text in ((True, "Диалог отменён"), (False, "Активного диалога нет")):
            router = self._router()
            if start:
                await self._active_user(router, user_id="1001")
            r = await router.route(_event("/cancel"))
            self.assertIn(text, r.messages[0].text)
            self.assertEqual(r.messages[0].buttons, ())

    async def test_platform_neutral_both_platforms(self):
        # движок не различает платформы: один и тот же объект кнопки доезжает
        # до TG и VK без изменений
        for platform in ("vk", "telegram"):
            router = self._router(cancel_buttons=(MENU,))
            r = await router.route(_event("/cancel", platform))
            self.assertEqual(r.messages[0].buttons, (MENU,))
            self.assertEqual(r.messages[0].buttons[0].to_dict(),
                             {"label": "🏠 В меню", "value": "scene:menu"})

    async def test_app_passes_cancel_buttons_to_router(self):
        from bot_fork import BotForkApp
        app = BotForkApp(platform="telegram",
                         adapter=TelegramAdapter(mock_sender=lambda p: None),
                         cancel_commands=("/cancel", "/стоп"),
                         cancel_buttons=(MENU, HELP))
        self.assertEqual(app.router.cancel_buttons, (MENU, HELP))
        # без параметра — пусто (совместимость)
        plain = BotForkApp(platform="vk", adapter=VKAdapter(mock_sender=lambda p: None))
        self.assertEqual(plain.router.cancel_buttons, ())


if __name__ == "__main__":
    unittest.main()
