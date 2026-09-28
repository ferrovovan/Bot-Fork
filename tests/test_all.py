"""
Master test runner for Bot Fork.
Executes all unit and integration tests across T1 through T15.
"""

import os
import sys
import unittest

# Ensure bot_fork is importable from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def suite():
    loader = unittest.TestLoader()
    test_suite = unittest.TestSuite()

    # Discover and add all tests in tests directory
    discovered = loader.discover(start_dir="tests", pattern="test_*.py")
    test_suite.addTests(discovered)
    return test_suite


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite())
    sys.exit(not result.wasSuccessful())
