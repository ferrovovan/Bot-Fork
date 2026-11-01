"""
BotForkApp - Main application entry point for Bot Fork.
Enforces single-platform selection, configuration validation, and orchestrates scenes and adapters.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from collections import OrderedDict
from typing import Callable, Optional, Tuple, Union
from bot_fork.adapters.base import PlatformAdapter
from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.adapters.vk import VKAdapter
from bot_fork.exceptions import ConfigError
from bot_fork.models import Attachment, Button, ErrorInfo, HandlerResult, IncomingEvent, OutgoingMessage
from bot_fork.router import DialogRouter, SceneRegistry
from bot_fork.scene import SceneDefinition
from bot_fork.storage import MemoryStateStorage, StateStorage

logger = logging.getLogger("bot_fork")


class BotForkApp:
    """
    Main application orchestrator.
    In MVP, exactly one platform is enabled per process (Telegram OR VK).
    """

    def __init__(
        self,
        platform: str,
        adapter: Optional[PlatformAdapter] = None,
        storage: Optional[StateStorage] = None,
        token: Optional[str] = None,
        on_error: Optional[Callable[[Exception, IncomingEvent], object]] = None,
        on_system_event: Optional[Callable[[IncomingEvent], object]] = None,
        dedupe_capacity: int = 1024,
    ) -> None:
        norm_platform = (platform or "").strip().lower()
        if norm_platform not in ("telegram", "vk"):
            raise ConfigError(
                f"ENABLED_PLATFORMS must be exactly 'telegram' or 'vk'. Got: '{platform}'. "
                "Simultaneous dual-platform orchestration is reserved for Bot Fork Business."
            )

        self.platform = norm_platform
        self.storage = storage or MemoryStateStorage()
        self.registry = SceneRegistry()
        # F-13: служебные события группы («игрок присоединился») идут в хук, диалог молчит.
        self.on_system_event = on_system_event
        self.router = DialogRouter(
            registry=self.registry,
            storage=self.storage,
            on_system_event=self._dispatch_system_event,
        )
        # F-20: хук на внутренние ошибки; по умолчанию None — поведение как раньше (raise).
        self.on_error = on_error
        # F-18: LRU-кэш event_id для дедупликации повторных callback'ов платформы.
        self._dedupe_capacity = max(1, int(dedupe_capacity))
        self._seen_event_ids: "OrderedDict[str, None]" = OrderedDict()

        if adapter is not None:
            if adapter.platform_name != self.platform:
                raise ConfigError(
                    f"Configured platform '{self.platform}' does not match adapter '{adapter.platform_name}'"
                )
            self.adapter = adapter
        else:
            if self.platform == "telegram":
                self.adapter = TelegramAdapter(token=token)
            else:
                self.adapter = VKAdapter(token=token)

    @classmethod
    def from_env(cls) -> BotForkApp:
        """
        Creates and configures BotForkApp from environment variables.
        Reads:
          - ENABLED_PLATFORMS: must be 'telegram' or 'vk'
          - TELEGRAM_BOT_TOKEN
          - VK_BOT_TOKEN
          - LOG_LEVEL (default INFO)
        """
        raw_platform = os.environ.get("ENABLED_PLATFORMS", "telegram").strip().lower()

        # Check for multiple platforms
        if "," in raw_platform or ";" in raw_platform or raw_platform in ("telegram,vk", "vk,telegram", "all"):
            raise ConfigError(
                f"Invalid ENABLED_PLATFORMS='{raw_platform}'. In MVP only one platform is allowed per process. "
                "Choose either ENABLED_PLATFORMS=telegram OR ENABLED_PLATFORMS=vk."
            )

        if raw_platform not in ("telegram", "vk"):
            raise ConfigError(
                f"Unknown ENABLED_PLATFORMS='{raw_platform}'. Must be 'telegram' or 'vk'."
            )

        log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        token: Optional[str] = None
        if raw_platform == "telegram":
            token = os.environ.get("TELEGRAM_BOT_TOKEN")
        elif raw_platform == "vk":
            token = os.environ.get("VK_BOT_TOKEN")

        return cls(platform=raw_platform, token=token)

    async def _dispatch_system_event(self, event: IncomingEvent) -> None:
        """F-13: гасит ошибки хука — событие о чате не должно ронять рантайм."""
        if self.on_system_event is None:
            return
        try:
            res = self.on_system_event(event)
            if inspect.isawaitable(res):
                await res
        except Exception as e:
            logger.error("on_system_event hook failed: %s", e)

    def register_scene(self, scene: SceneDefinition) -> None:
        """Registers a dialogue scene definition with the app."""
        if not isinstance(scene, SceneDefinition):
            raise ConfigError("register_scene expects a SceneDefinition instance")
        self.registry.register(scene)
        logger.info("Registered scene '%s' with entry commands: %s", scene.id, scene.entry_commands)

    async def handle(self, event: IncomingEvent) -> HandlerResult:
        """
        Processes an incoming event from adapter, records anonymous telemetry,
        and returns HandlerResult. Tokens and user message text are never logged.
        """
        start_time = time.perf_counter()

        # F-18: повтор того же события (double callback от платформы) — молча гасим.
        event_id = (event.event_id or "").strip()
        if event_id:
            if event_id in self._seen_event_ids:
                logger.info("Duplicate event ignored | platform=%s", self.platform)
                return HandlerResult()
            self._seen_event_ids[event_id] = None
            while len(self._seen_event_ids) > self._dedupe_capacity:
                self._seen_event_ids.popitem(last=False)

        try:
            result = await self.router.route(event)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            active_scene = result.session_after.scene_id if result.session_after else "none"
            active_step = result.session_after.step_id if result.session_after else "none"
            err_code = result.error.code if result.error else "OK"

            logger.info(
                "Event handled | platform=%s | scene=%s | step=%s | status=%s | duration=%.2fms",
                event.platform,
                active_scene,
                active_step,
                err_code,
                duration_ms,
            )
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error("Internal error handling event: %s | duration=%.2fms", e, duration_ms)
            # F-20: если задан хук — цикл не падает, ошибка уходит продукту.
            if self.on_error is not None:
                try:
                    hook_res = self.on_error(e, event)
                    if inspect.isawaitable(hook_res):
                        await hook_res
                except Exception as hook_exc:  # хук не должен ронять рантайм
                    logger.error("on_error hook failed: %s", hook_exc)
                return HandlerResult(
                    messages=(
                        OutgoingMessage(
                            chat_id=event.chat_id,
                            text="Произошла внутренняя ошибка. Попробуйте ещё раз позже.",
                        ),
                    ),
                    error=ErrorInfo(code="INTERNAL_ERROR", message=str(e), retryable=True),
                )
            raise

    async def send(
        self,
        chat_id: str,
        text: str,
        buttons: Tuple[Button, ...] = (),
        attachment: Optional[Attachment] = None,
    ) -> None:
        """
        F-11: исходящая отправка без входящего события (напоминания, отчёты, эскалации).
        F-01: необязательное вложение (график botgraph — фото, выгрузка — документ).
        Сообщение форматируется текущим адаптером платформы и уходит напрямую.
        """
        message = OutgoingMessage(
            chat_id=str(chat_id),
            text=text,
            buttons=tuple(buttons),
            attachment=attachment,
        )
        await self.adapter.send(message)
        logger.info(
            "Proactive send | platform=%s | len=%d | attachment=%s",
            self.platform,
            len(text),
            "yes" if attachment else "no",
        )

    async def _run_async(self) -> None:
        """Internal asynchronous runner for adapter polling."""
        logger.info("Bot Fork starting on platform: %s", self.platform)
        await self.adapter.start_polling(self.handle)

    def run(self) -> None:
        """Starts the Bot Fork event loop."""
        try:
            asyncio.run(self._run_async())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot Fork stopped.")
