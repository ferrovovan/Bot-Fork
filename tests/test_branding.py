"""
Test suite for T10: Message limits and clean text (proprietary branding removed in v1.0).
Verifies messages respect limits and do not contain forced proprietary branding.
"""

import unittest
from bot_fork.exceptions import ConfigError
from bot_fork.fsm import apply_branding


class TestBranding(unittest.TestCase):
    def test_no_forced_branding(self):
        text = "Как к вам обращаться?"
        formatted = apply_branding(text)
        self.assertEqual(formatted, "Как к вам обращаться?")
        self.assertNotIn("Made with Bot Fork", formatted)

    def test_branding_limit_4096(self):
        fits = "x" * 4096
        formatted = apply_branding(fits)
        self.assertEqual(len(formatted), 4096)

        # Exceeding 4096 raises ConfigError
        too_long = "x" * 4097
        with self.assertRaises(ConfigError):
            apply_branding(too_long)


if __name__ == "__main__":
    unittest.main()
