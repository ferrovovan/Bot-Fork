"""
ButtonBuilder implementation for Bot Fork.
Validates constraints and creates universal Button objects without platform dependencies.
"""

from __future__ import annotations

from typing import List, Tuple
from bot_fork.exceptions import ConfigError
from bot_fork.models import Button


class ButtonBuilder:
    """Universal text button builder."""

    @staticmethod
    def text(label: str, value: str) -> Button:
        """
        Creates a universal Button after validating constraints.
        - label: 1 to 40 characters
        - value: 1 to 64 characters
        """
        if not isinstance(label, str) or not (1 <= len(label.strip()) <= 40):
            raise ConfigError(
                f"Button label must be a string of 1-40 characters, got: {repr(label)}"
            )
        if not isinstance(value, str) or not (1 <= len(value.strip()) <= 64):
            raise ConfigError(
                f"Button value must be a string of 1-64 characters, got: {repr(value)}"
            )
        return Button(label=label.strip(), value=value.strip())

    @staticmethod
    def keyboard(*buttons: Button) -> Tuple[Button, ...]:
        """
        Validates button list limits (0-4 buttons, unique values).
        """
        if len(buttons) > 4:
            raise ConfigError(f"Maximum of 4 buttons allowed per step, got {len(buttons)}")
        values = [b.value for b in buttons]
        if len(values) != len(set(values)):
            raise ConfigError(f"Duplicate button values within step: {values}")
        return tuple(buttons)
