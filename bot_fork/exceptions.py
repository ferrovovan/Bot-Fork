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


class PlatformTimeoutError(PlatformError):
    """Raised when platform request times out."""
    pass
