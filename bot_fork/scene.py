"""
SceneDefinition, StepDefinition, and factory classes for Bot Fork.
Enforces structural integrity and immutability of dialogue scenes.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Union
from bot_fork.builder import ButtonBuilder
from bot_fork.exceptions import ConfigError
from bot_fork.models import Button

ValidatorFunc = Callable[[str], Union[bool, Tuple[bool, str], None]]
# F-05: prompt может быть функцией от сессии (карточка слота, регламент из анкет).
# Вызывается с UserSession (или без аргументов); обязана вернуть непустую str.
PromptFunc = Callable[..., str]
# F-04: действие шага — сид-эффект после валидного ответа (вызов сервиса продукта).
# Принимает (значение, словарь данных сессии — можно дополнять), может быть async.
# Возврат строки трактуется как причина отказа: шаг не завершается, данные не сохраняются.
ActionFunc = Callable[..., Any]


@dataclass(frozen=True)
class StepDefinition:
    """
    Immutable description of a scene step.
    Defines prompt, input validation, buttons, and transitions.
    """
    id: str
    prompt: Union[str, PromptFunc]  # F-05: str или Callable[[UserSession], str]
    input_type: str = "text"  # "text" | "choice"
    buttons: Tuple[Button, ...] = ()
    validator: Optional[ValidatorFunc] = None
    transitions: Dict[str, str] = field(default_factory=dict)
    next_step_id: Optional[str] = None
    complete: bool = False
    action: Optional[ActionFunc] = None

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ConfigError("Step id must be a non-empty string")
        if not callable(self.prompt) and (not self.prompt or not isinstance(self.prompt, str)):
            raise ConfigError(f"Step '{self.id}' prompt must be a non-empty string or a callable")
        if self.input_type not in ("text", "choice"):
            raise ConfigError(f"Step '{self.id}' input_type must be 'text' or 'choice', got '{self.input_type}'")
        if len(self.buttons) > 4:
            raise ConfigError(f"Step '{self.id}' cannot have more than 4 buttons (got {len(self.buttons)})")
        if self.input_type == "choice" and not self.buttons:
            raise ConfigError(f"Step '{self.id}' has input_type='choice' but no buttons were provided")

        values = [b.value for b in self.buttons]
        if len(values) != len(set(values)):
            raise ConfigError(f"Step '{self.id}' has duplicate button values: {values}")

    def render_prompt(self, session: Any = None) -> str:
        """F-05: статический prompt или текст, вычисленный из данных сессии."""
        if not callable(self.prompt):
            return self.prompt
        try:
            params = inspect.signature(self.prompt).parameters
            takes_arg = any(
                p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                for p in params.values()
            )
            result = self.prompt(session) if takes_arg else self.prompt()
        except Exception as e:  # исключение продукта не должно ронять роутер
            raise ConfigError(f"Step '{self.id}' dynamic prompt raised {e!r}") from e
        if not isinstance(result, str) or not result:
            raise ConfigError(f"Step '{self.id}' dynamic prompt must return a non-empty string")
        return result


class Step:
    """Convenience factory for StepDefinition."""

    @staticmethod
    def text(
        id: str,
        prompt: str,
        validator: Optional[ValidatorFunc] = None,
        next: Optional[str] = None,
        complete: bool = False,
        action: Optional[ActionFunc] = None,
    ) -> StepDefinition:
        return StepDefinition(
            id=id,
            prompt=prompt,
            input_type="text",
            buttons=(),
            validator=validator,
            transitions={},
            next_step_id=next,
            complete=complete,
            action=action,
        )

    @staticmethod
    def choice(
        id: str,
        prompt: str,
        buttons: Sequence[Button] = (),
        transitions: Optional[Dict[str, str]] = None,
        next: Optional[str] = None,
        complete: bool = False,
        action: Optional[ActionFunc] = None,
    ) -> StepDefinition:
        btn_tuple = ButtonBuilder.keyboard(*buttons)
        trans = dict(transitions) if transitions else {}
        return StepDefinition(
            id=id,
            prompt=prompt,
            input_type="choice",
            buttons=btn_tuple,
            validator=None,
            transitions=trans,
            next_step_id=next,
            complete=complete,
            action=action,
        )


@dataclass(frozen=True)
class SceneDefinition:
    """
    Immutable definition of an entire dialogue scene.
    F-06: lane="system" — приоритетная сцена: её активная сессия перехватывает события чата,
    пока не завершится; пользовательские диалоги (lane="user") при этом не теряются.
    """
    id: str
    entry_commands: Tuple[str, ...]
    start_step_id: str
    steps: Tuple[StepDefinition, ...]
    lane: str = "user"
    # F-09: чем сцена отвечает на завершение. Вызывается с UserSession;
    # возврат: None (тихо) | str | list[str] | list[OutgoingMessage] | list смешанно.
    # Без него — прежний generic-отчёт. Ядро больше не знает текстов конкретных сцен.
    on_complete: Optional[Callable[..., Any]] = None
    _step_map: Dict[str, StepDefinition] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ConfigError("Scene id must be a non-empty string")
        if self.lane not in ("user", "system"):
            raise ConfigError(f"Scene '{self.id}' lane must be 'user' or 'system', got '{self.lane}'")
        if not self.steps:
            raise ConfigError(f"Scene '{self.id}' must define at least 1 step (max 50)")
        if len(self.steps) > 50:
            raise ConfigError(f"Scene '{self.id}' exceeds maximum of 50 steps (got {len(self.steps)})")

        step_map: Dict[str, StepDefinition] = {}
        for s in self.steps:
            if s.id in step_map:
                raise ConfigError(f"Duplicate step id '{s.id}' in scene '{self.id}'")
            step_map[s.id] = s

        object.__setattr__(self, "_step_map", step_map)

        if not self.start_step_id or self.start_step_id not in step_map:
            raise ConfigError(
                f"Scene '{self.id}' start_step_id '{self.start_step_id}' does not exist in steps"
            )

        # Validate transitions and next_step_id references
        for s in self.steps:
            if s.next_step_id and s.next_step_id not in step_map:
                raise ConfigError(
                    f"Step '{s.id}' in scene '{self.id}' references non-existent next_step_id '{s.next_step_id}'"
                )
            for val, target_id in s.transitions.items():
                if target_id not in step_map:
                    raise ConfigError(
                        f"Step '{s.id}' transition for '{val}' points to non-existent step '{target_id}'"
                    )

            if s.input_type == "choice":
                # Ensure each button value either has an explicit transition or default next_step_id.
                # F-23: launch-кнопки `scene:<id>` перехватывает DialogRouter до FSM — переход не нужен.
                for btn in s.buttons:
                    if btn.value.startswith("scene:"):
                        continue
                    if btn.value not in s.transitions and not s.next_step_id and not s.complete:
                        raise ConfigError(
                            f"Step '{s.id}' choice button '{btn.value}' has no transition and no default next_step_id"
                        )

    def get_step(self, step_id: str) -> Optional[StepDefinition]:
        return self._step_map.get(step_id)


def Scene(
    id: str,
    entry_commands: Sequence[str] = (),
    steps: Sequence[StepDefinition] = (),
    start_step_id: Optional[str] = None,
    lane: str = "user",
    on_complete: Optional[Callable[..., Any]] = None,
) -> SceneDefinition:
    """
    Factory function matching MVP target API specification:
    info = Scene(
        id="info",
        entry_commands=("/info",),
        steps=(...),
    )
    """
    step_tuple = tuple(steps)
    start_id = start_step_id if start_step_id is not None else (step_tuple[0].id if step_tuple else "")
    norm_commands = tuple(cmd.strip() for cmd in entry_commands if cmd.strip())
    return SceneDefinition(
        id=id,
        entry_commands=norm_commands,
        start_step_id=start_id,
        steps=step_tuple,
        lane=lane,
        on_complete=on_complete,
    )
