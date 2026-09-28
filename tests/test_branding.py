"""
Test suite for T10: Mandatory branding "Made with Bot Fork" in free tier.
Verifies branding is appended exactly once and limits are respected.
"""

import unittest
from bot_fork.exceptions import ConfigError
from bot_fork.fsm import apply_branding


class TestBranding(unittest.TestCase):
    def test_branding_appended_once(self):
        text = "Как к вам обращаться?"
        branded = apply_branding(text)
        self.assertTrue(branded.endswith("Made with Bot Fork"))
        self.assertEqual(branded.count("Made with Bot Fork"), 1)

        # Re-applying does not duplicate
        rebranded = apply_branding(branded)
        self.assertEqual(rebranded.count("Made with Bot Fork"), 1)
        self.assertEqual(branded, rebranded)

    def test_branding_limit_4096(self):
        # 4096 - len("\n\nMade with Bot Fork") = 4096 - 20 = 4076
        fits = "x" * 4076
        branded = apply_branding(fits)
        self.assertEqual(len(branded), 4096)

        # Exceeding 4096 raises ConfigError
        too_long = "x" * 4077
        with self.assertRaises(ConfigError):
            apply_branding(too_long)


if __name__ == "__main__":
    unittest.main()
