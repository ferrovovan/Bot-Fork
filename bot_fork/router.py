"""
DialogRouter and SceneRegistry implementation for Bot Fork.
Routes commands, manages active session transitions, and handles /cancel and /info.
"""

from __future__ import annotations

import inspect
import logging
from typing import Dict, List, Optional, Tuple
from bot_fork.exceptions import ConfigError
from bot_fork.fsm import FSMEngine, apply_branding
from bot_fork.models import (
    ErrorInfo,
    HandlerResult,
    IncomingEvent,
    OutgoingMessage,
    UserSession,
)
from bot_fork.scene import SceneDefinition
from bot_fork.storage import StateStorage

logger = logging.getLogger("bot_fork.router")


class SceneRegistry:
    """Registry maintaining unique scenes and their entry commands."""

    def __init__(self) -> None:
        self._scenes: Dict[str, SceneDefinition] = {}
        self._command_map: Dict[str, str] = {}  # entry_command -> scene_id

    def register(self, scene: SceneDefinition) -> None:
        if scene.id in self._scenes:
            raise ConfigError(f"Scene with id '{scene.id}' is already registered")

        for cmd in scene.entry_commands:
            norm_cmd = cmd.lower().strip()
            if norm_cmd in self._command_map:
                existing_scene = self._command_map[norm_cmd]
                raise ConfigError(
                    f"Entry command '{cmd}' is already assigned to scene '{existing_scene}'"
                )
            self._command_map[norm_cmd] = scene.id

        self._scenes[scene.id] = scene

    def get_scene(self, scene_id: str) -> Optional[SceneDefinition]:
        return self._scenes.get(scene_id)

    def resolve_command(self, text: str) -> Optional[SceneDefinition]:
        if not text:
            return None
        first_token = text.strip().split()[0].lower()
        scene_id = self._command_map.get(first_token)
        if scene_id:
            return self._scenes.get(scene_id)
        return None

    def list_entry_commands(self) -> List[str]:
        return sorted(list(self._command_map.keys()))


class DialogRouter:
    """
    Main dialogue router coordinating SceneRegistry, StateStorage, and FSMEngine.
    """

    def __init__(
        self,
        registry: SceneRegistry,
        storage: StateStorage,
        fsm_engine: Optional[FSMEngine] = None,
        on_system_event=None,
        cancel_commands: Optional[Tuple[str, ...]] = None,
    ) -> None:
        self.registry = registry
        self.storage = storage
        self.fsm = fsm_engine or FSMEngine()
        # F-31: отмена — системная команда, а в VK её печатают руками по-русски.
        # Продукт задаёт свои алиасы («/отмена» для VK); по-прежнему всё lowercase.
        self.cancel_commands = tuple(
            c.lower() for c in (cancel_commands or ("/cancel",))
        )
        # F-13: callback(event) -> None | Awaitable, куда роутер отдаёт служебные события
        # («игрок присоединился», «бота добавили в чат»). Диалог на них не запускается.
        self.on_system_event = on_system_event

    async def route(self, event: IncomingEvent) -> HandlerResult:
        """Processes an incoming normalized event."""
        # F-13: служебные события группы не попадают в диалог вовсе — только в хук.
        if event.event_type == "system":
            if self.on_system_event is not None:
                res = self.on_system_event(event)
                if inspect.isawaitable(res):
                    await res
            return HandlerResult()

        text = (event.text or "").strip()
        logger.debug("event %s: text=%r payload=%r", event.platform, text[:100], event.payload)
        command_token = text.split()[0].lower() if text.startswith("/") else ""

        # Step 1: Handle /cancel (system command, before any scene logic).
        # F-06: отменяется «верхний» диалог — сначала system-слот, иначе user.
        # F-31: набор отмен задаёт продукт (в VK печатают «/отмена»).
        if command_token in self.cancel_commands:
            for lane in ("system", "user"):
                key = event.session_key.with_lane(lane)
                existing_session = await self.storage.get(key)
                if existing_session is not None:
                    await self.storage.clear(key)
                    return HandlerResult(
                        messages=(
                            OutgoingMessage(
                                chat_id=event.chat_id,
                                text=apply_branding("Диалог отменён. Для нового запуска отправьте /info."),
                            ),
                        ),
                        session_after=None,
                        clear_session=True,
                        error=None,
                    )
            return HandlerResult(
                messages=(
                    OutgoingMessage(
                        chat_id=event.chat_id,
                        text=apply_branding("Активного диалога нет."),
                    ),
                ),
                session_after=None,
                clear_session=False,
                error=None,
            )

        # Step 2: F-06 — активные сессии обеих полос чата
        system_session = await self.storage.get(event.session_key.with_lane("system"))
        user_session = await self.storage.get(event.session_key.with_lane("user"))

        # Step 3: entry-команды и scene-кнопки (F-23: payload "scene:<id>").
        # Сцена стартует в своей полосе: system-сцены не трогают анкету игрока.
        matched_scene = self.registry.resolve_command(text)
        if matched_scene is None:
            matched_scene = self._resolve_scene_button(event)

        if matched_scene is not None:
            lane_key = event.session_key.with_lane(matched_scene.lane)
            existing = system_session if matched_scene.lane == "system" else user_session
            return await self.begin_scene(matched_scene, lane_key, event.chat_id, had_session=existing is not None)

        # Step 4: нет активной сессии ни в одной полосе — служебный ответ
        session = system_session or user_session
        if session is None:
            available_cmds = ", ".join(self.registry.list_entry_commands()) or "/info"
            if command_token:
                msg = f"Команда не найдена. Доступно: {available_cmds}"
                code = "UNKNOWN_COMMAND"
            else:
                msg = f"Сначала запустите {available_cmds}."
                code = "NO_ACTIVE_SCENE"

            return HandlerResult(
                messages=(
                    OutgoingMessage(
                        chat_id=event.chat_id,
                        text=apply_branding(msg),
                    ),
                ),
                session_after=None,
                clear_session=False,
                error=ErrorInfo(code=code, message=msg, retryable=True),
            )

        # Step 5: активная сессия — system-полоса перехватывает (F-06), иначе user
        scene = self.registry.get_scene(session.scene_id)
        if scene is None:
            await self.storage.clear(session.session_key)
            return HandlerResult(
                messages=(
                    OutgoingMessage(
                        chat_id=event.chat_id,
                        text=apply_branding("Сценарий не найден в реестре. Сессия очищена."),
                    ),
                ),
                clear_session=True,
                error=ErrorInfo(code="INTERNAL_ERROR", message="Scene not in registry", retryable=False),
            )

        result = self.fsm.process_step(event, session, scene)
        # Совместимость: собственный FSMEngine может остаться синхронным (F-04).
        if inspect.isawaitable(result):
            result = await result

        # Persist updated session or clear upon completion — в полосе самой сессии,
        # завершение system-сцены открывает дорогу user-сессии (F-06).
        if result.clear_session:
            await self.storage.clear(session.session_key)
        elif result.session_after is not None:
            await self.storage.set(result.session_after)

        return result

    async def begin_scene(
        self,
        scene: SceneDefinition,
        lane_key,
        chat_id: str,
        had_session: bool = False,
        initial_data: Optional[Dict] = None,
    ) -> HandlerResult:
        """Старт/перезапуск сцены в заданной полосе (общий путь для команд, кнопок и F-22)."""
        start_step = scene.get_step(scene.start_step_id)
        if start_step is None:
            return HandlerResult(
                messages=(
                    OutgoingMessage(
                        chat_id=chat_id,
                        text=apply_branding("Ошибка запуска сцены: начальный шаг не найден."),
                    ),
                ),
                clear_session=True,
                error=ErrorInfo(code="INTERNAL_ERROR", message="Start step not found", retryable=False),
            )

        new_session = UserSession(
            session_key=lane_key,
            scene_id=scene.id,
            step_id=scene.start_step_id,
            data=dict(initial_data or {}),
        )
        # F-27: перезапуск сцены, где уже шёл диалог. Текст шапки принадлежит сцене,
        # а не ядру: раньше тут было вшито «Анкета начата заново.», чем портили
        # ответ админского меню и дневника. None → generic, "" → шапки нет.
        if had_session and scene.restart_text != "":
            prefix = f"{scene.restart_text or 'Диалог начат заново.'}\n\n"
        else:
            prefix = ""
        prompt_text = prefix + await start_step.arender_prompt(new_session)

        await self.storage.set(new_session)
        return HandlerResult(
            messages=(
                OutgoingMessage(
                    chat_id=chat_id,
                    text=apply_branding(prompt_text),
                    buttons=await start_step.resolve_buttons(new_session),
                ),
            ),
            session_after=new_session,
            clear_session=False,
            error=None,
        )

    def _resolve_scene_button(self, event: IncomingEvent) -> Optional[SceneDefinition]:
        """
        F-23: кнопка запуска сцены. Зарезервированный payload `scene:<scene_id>`
        стартует сцену так же, как entry-команда. Прочие payload'ы — как раньше.
        """
        payload = event.payload
        if not isinstance(payload, str) or not payload.startswith("scene:"):
            return None
        return self.registry.get_scene(payload[len("scene:"):].strip())
