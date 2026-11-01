"""
Exception hierarchy for Bot Fork library.
"""


class BotForkError(Exception):
    """Base exception for all Bot Fork errors."""
    pass


class ConfigError(BotForkError):
    """Raised when configuration, scene, step, or platform setup is invalid."""
    pass


class InvalidInputError(BotForkError):
    """Raised when user input fails step validation."""
    pass


class StorageError(BotForkError):
    """Raised when state storage fails to get/set/clear session."""
    pass


class PlatformError(BotForkError):
    """Raised when platform adapter encounters an API or transmission error."""
    pass


class PlatformOperationNotSupported(PlatformError):
    """
    F-13: платформа принципиально не умеет операцию (Telegram-бот не создаёт чаты
    и не добавляет участников). Не путать с PlatformError — это не сбой, это ограничение API.
    """
    pass


class PlatformTimeoutError(PlatformError):
    """Raised when platform request times out."""
    pass
