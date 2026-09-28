"""
Platform adapters package for Bot Fork.
"""

from bot_fork.adapters.base import PlatformAdapter
from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.adapters.vk import VKAdapter

__all__ = ["PlatformAdapter", "TelegramAdapter", "VKAdapter"]
