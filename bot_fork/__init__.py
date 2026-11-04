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
    PlatformOperationNotSupported,
    PlatformTimeoutError,
    StorageError,
)
from bot_fork.fsm import FSMEngine, apply_branding
from bot_fork.models import (
    Attachment,
    Button,
    ErrorInfo,
    HandlerResult,
    IncomingEvent,
    OutgoingMessage,
    Reject,
    SessionKey,
    UserSession,
)
from bot_fork.router import DialogRouter, SceneRegistry
from bot_fork.scene import Scene, SceneDefinition, Step, StepDefinition
from bot_fork.storage import MemoryStateStorage, StateStorage
from bot_fork.sql_storage import SqlStateStorage

# Версия читается из метаданных установленного пакета (решение D-19, пакет п49-4):
# ручная сверка разъезжалась каждым патчем (факт 2026-11-04: `__version__` «1.12.5»
# при `pyproject.toml` 1.12.8). Константа — только fallback для запуска из клона,
# где пакет не установлен; на нормальном пути ручных цифр в коде нет.
_FALLBACK_VERSION = "1.12.9"


def _resolve_version() -> str:
    """Версия пакета `bot-fork`: метаданные установленной дистрибуции;
    PackageNotFoundError (или любая нечитаемая метаданность) — fallback-константа."""
    try:
        from importlib.metadata import version
        return version("bot-fork")
    except Exception:
        return _FALLBACK_VERSION


__version__ = _resolve_version()
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
    "Reject",
    "Attachment",
    "UserSession",
    "ErrorInfo",
    "HandlerResult",
    "StateStorage",
    "MemoryStateStorage",
    "SqlStateStorage",
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
    "PlatformOperationNotSupported",
    "PlatformTimeoutError",
    "apply_branding",
]
