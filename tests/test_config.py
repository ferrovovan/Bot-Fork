"""
Test suite for T10: BotForkApp configuration checks.
Verifies single platform rule: ENABLED_PLATFORMS must be exactly 'telegram' or 'vk'.
Rejects simultaneous dual-platform launch with ConfigError.
"""

import os
import unittest
from bot_fork.app import BotForkApp
from bot_fork.exceptions import ConfigError


class TestConfig(unittest.TestCase):
    def test_single_platform_telegram_accepted(self):
        os.environ["ENABLED_PLATFORMS"] = "telegram"
        app = BotForkApp.from_env()
        self.assertEqual(app.platform, "telegram")
        self.assertEqual(app.adapter.platform_name, "telegram")

    def test_single_platform_vk_accepted(self):
        os.environ["ENABLED_PLATFORMS"] = "vk"
        app = BotForkApp.from_env()
        self.assertEqual(app.platform, "vk")
        self.assertEqual(app.adapter.platform_name, "vk")

    def test_dual_platform_telegram_vk_rejected(self):
        os.environ["ENABLED_PLATFORMS"] = "telegram,vk"
        with self.assertRaises(ConfigError):
            BotForkApp.from_env()

        os.environ["ENABLED_PLATFORMS"] = "vk,telegram"
        with self.assertRaises(ConfigError):
            BotForkApp.from_env()

    def test_invalid_platform_name_rejected(self):
        os.environ["ENABLED_PLATFORMS"] = "discord"
        with self.assertRaises(ConfigError):
            BotForkApp.from_env()

        os.environ["ENABLED_PLATFORMS"] = ""
        with self.assertRaises(ConfigError):
            BotForkApp.from_env()


if __name__ == "__main__":
    unittest.main()
