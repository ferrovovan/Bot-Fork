"""
СценоМост Bot Fork - Python library for prototyping dialogue scenes for Telegram and VKontakte.
Version 3.1 (MVP)
"""

from bot_fork.adapters.base import PlatformAdapter
from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.adapters.vk import VKAdapter
from bot_fork.app import BotForkApp
from bot_fork.builder import ButtonBuilder
from bot_fork.exceptions import (
    BotForkError,
    ConfigError,
    InvalidInputError,
    PlatformError,
    PlatformTimeoutError,
    StorageError,
)
from bot_fork.fsm import FSMEngine, apply_branding
from bot_fork.models import (
    Button,
    ErrorInfo,
    HandlerResult,
    IncomingEvent,
    OutgoingMessage,
    SessionKey,
    UserSession,
)
from bot_fork.router import DialogRouter, SceneRegistry
from bot_fork.scene import Scene, SceneDefinition, Step, StepDefinition
from bot_fork.storage import MemoryStateStorage, StateStorage

__version__ = "3.1.0"
__all__ = [
    "BotForkApp",
    "Scene",
    "Step",
    "Button",
    "ButtonBuilder",
    "SceneDefinition",
    "StepDefinition",
    "SessionKey",
    "IncomingEvent",
    "OutgoingMessage",
    "UserSession",
    "ErrorInfo",
    "HandlerResult",
    "StateStorage",
    "MemoryStateStorage",
    "DialogRouter",
    "SceneRegistry",
    "FSMEngine",
    "PlatformAdapter",
    "TelegramAdapter",
    "VKAdapter",
    "BotForkError",
    "ConfigError",
    "InvalidInputError",
    "StorageError",
    "PlatformError",
    "PlatformTimeoutError",
    "apply_branding",
]
