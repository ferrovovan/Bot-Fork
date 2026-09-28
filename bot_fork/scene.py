"""
SceneDefinition, StepDefinition, and factory classes for Bot Fork.
Enforces structural integrity and immutability of dialogue scenes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Sequence, Tuple, Union
from bot_fork.builder import ButtonBuilder
from bot_fork.exceptions import ConfigError
from bot_fork.models import Button

ValidatorFunc = Callable[[str], Union[bool, Tuple[bool, str], None]]


@dataclass(frozen=True)
class StepDefinition:
    """
    Immutable description of a scene step.
    Defines prompt, input validation, buttons, and transitions.
    """
    id: str
    prompt: str
    input_type: str = "text"  # "text" | "choice"
    buttons: Tuple[Button, ...] = ()
    validator: Optional[ValidatorFunc] = None
    transitions: Dict[str, str] = field(default_factory=dict)
    next_step_id: Optional[str] = None
    complete: bool = False

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ConfigError("Step id must be a non-empty string")
        if not self.prompt or not isinstance(self.prompt, str):
            raise ConfigError(f"Step '{self.id}' prompt must be a non-empty string")
        if self.input_type not in ("text", "choice"):
            raise ConfigError(f"Step '{self.id}' input_type must be 'text' or 'choice', got '{self.input_type}'")
        if len(self.buttons) > 4:
            raise ConfigError(f"Step '{self.id}' cannot have more than 4 buttons (got {len(self.buttons)})")
        if self.input_type == "choice" and not self.buttons:
            raise ConfigError(f"Step '{self.id}' has input_type='choice' but no buttons were provided")

        values = [b.value for b in self.buttons]
        if len(values) != len(set(values)):
            raise ConfigError(f"Step '{self.id}' has duplicate button values: {values}")


class Step:
    """Convenience factory for StepDefinition."""

    @staticmethod
    def text(
        id: str,
        prompt: str,
        validator: Optional[ValidatorFunc] = None,
        next: Optional[str] = None,
        complete: bool = False,
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
        )

    @staticmethod
    def choice(
        id: str,
        prompt: str,
        buttons: Sequence[Button] = (),
        transitions: Optional[Dict[str, str]] = None,
        next: Optional[str] = None,
        complete: bool = False,
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
        )


@dataclass(frozen=True)
class SceneDefinition:
    """
    Immutable definition of an entire dialogue scene.
    """
    id: str
    entry_commands: Tuple[str, ...]
    start_step_id: str
    steps: Tuple[StepDefinition, ...]
    _step_map: Dict[str, StepDefinition] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ConfigError("Scene id must be a non-empty string")
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
                # Ensure each button value either has an explicit transition or default next_step_id
                for btn in s.buttons:
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
    )
