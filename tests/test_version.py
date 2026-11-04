"""D-19 (v1.12.9): `__version__` читается из метаданных установленного пакета.

Ручная синхронизация разъехалась снова: «1.12.5» при `pyproject.toml` 1.12.8
(замечание п49-2 №4). Источник истины — метаданные дистрибуции
(`importlib.metadata.version("bot-fork")`); константа `_FALLBACK_VERSION`
работает только когда пакет не установлен (запуск из клона). Пакет п49-4,
решение комнаты `D-19` / RFC-06 §6.
"""

import importlib.metadata
import unittest
from unittest import mock

import bot_fork


class TestVersion(unittest.TestCase):
    def test_version_non_empty(self):
        """`__version__` — непустая строка вида мажор.минор.патч."""
        self.assertIsInstance(bot_fork.__version__, str)
        self.assertRegex(bot_fork.__version__, r"^\d+\.\d+\.\d+$")

    def test_version_matches_installed_metadata(self):
        """Когда пакет установлен, `__version__` равен версии из метаданных."""
        try:
            meta = importlib.metadata.version("bot-fork")
        except importlib.metadata.PackageNotFoundError:
            meta = None
        if meta is not None:
            self.assertEqual(bot_fork.__version__, meta)
        else:
            # Клон без установленного пакета — нормальный путь fallback: константа.
            self.assertEqual(bot_fork.__version__, bot_fork._FALLBACK_VERSION)

    def test_fallback_when_package_not_installed(self):
        """PackageNotFoundError (клон без установки) → константа, не исключение."""
        with mock.patch.object(
            importlib.metadata, "version",
            side_effect=importlib.metadata.PackageNotFoundError("bot-fork"),
        ):
            self.assertEqual(bot_fork._resolve_version(), bot_fork._FALLBACK_VERSION)

    def test_fallback_survives_any_metadata_failure(self):
        """Любой сбой чтения метаданных не роняет импорт библиотеки."""
        with mock.patch.object(
            importlib.metadata, "version",
            side_effect=OSError("метаданные не читаются"),
        ):
            self.assertEqual(bot_fork._resolve_version(), bot_fork._FALLBACK_VERSION)


if __name__ == "__main__":
    unittest.main()
