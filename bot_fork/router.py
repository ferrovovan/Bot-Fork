"""
DialogRouter and SceneRegistry implementation for Bot Fork.
Routes commands, manages active session transitions, and handles /cancel and /info.
"""

from __future__ import annotations

from typing import Dict, List, Optional
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
    ) -> None:
        self.registry = registry
        self.storage = storage
        self.fsm = fsm_engine or FSMEngine()

    async def route(self, event: IncomingEvent) -> HandlerResult:
        """Processes an incoming normalized event."""
        text = (event.text or "").strip()
        command_token = text.split()[0].lower() if text.startswith("/") else ""

        # Step 1: Handle /cancel command (system command, handled before any scene logic)
        if command_token == "/cancel":
            existing_session = await self.storage.get(event.session_key)
            if existing_session is not None:
                await self.storage.clear(event.session_key)
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
            else:
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

        # Step 2: Fetch active session
        session = await self.storage.get(event.session_key)

        # Step 3: Handle entry commands (e.g., /info)
        matched_scene = self.registry.resolve_command(text)
        if matched_scene is not None:
            # Starting new or restarting active scene
            new_session = UserSession(
                session_key=event.session_key,
                scene_id=matched_scene.id,
                step_id=matched_scene.start_step_id,
                data={},
            )
            start_step = matched_scene.get_step(matched_scene.start_step_id)
            if start_step is None:
                return HandlerResult(
                    messages=(
                        OutgoingMessage(
                            chat_id=event.chat_id,
                            text=apply_branding("Ошибка запуска сцены: начальный шаг не найден."),
                        ),
                    ),
                    clear_session=True,
                    error=ErrorInfo(code="INTERNAL_ERROR", message="Start step not found", retryable=False),
                )

            # If user already had a session in this scene, notify restart
            prefix = "Анкета начата заново.\n\n" if session is not None else ""
            prompt_text = prefix + start_step.prompt

            await self.storage.set(new_session)
            return HandlerResult(
                messages=(
                    OutgoingMessage(
                        chat_id=event.chat_id,
                        text=apply_branding(prompt_text),
                        buttons=start_step.buttons,
                    ),
                ),
                session_after=new_session,
                clear_session=False,
                error=None,
            )

        # Step 4: If no active session and not an entry command
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

        # Step 5: Active session exists - dispatch to FSMEngine
        scene = self.registry.get_scene(session.scene_id)
        if scene is None:
            await self.storage.clear(event.session_key)
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

        # Persist updated session or clear upon completion
        if result.clear_session:
            await self.storage.clear(event.session_key)
        elif result.session_after is not None:
            await self.storage.set(result.session_after)

        return result
