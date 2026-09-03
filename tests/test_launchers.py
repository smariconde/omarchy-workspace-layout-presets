from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.launchers import resolve_desktop_id


class LauncherResolutionTests(unittest.TestCase):
    def test_resolves_only_a_valid_matching_application_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "code.desktop").write_text("[Desktop Entry]\nType=Application\nExec=code\nStartupWMClass=Code\n", encoding="utf-8")
            (directory / "broken.desktop").write_text("[Desktop Entry]\nType=Application\nStartupWMClass=kitty\n", encoding="utf-8")

            self.assertEqual(resolve_desktop_id("code", directories=[directory]), "code")
            self.assertIsNone(resolve_desktop_id("kitty", directories=[directory]))

    def test_uses_filename_only_as_a_conservative_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "org.example.App.desktop").write_text("[Desktop Entry]\nType=Application\nExec=app\n", encoding="utf-8")

            self.assertEqual(resolve_desktop_id("org.example.app", directories=[directory]), "org.example.App")
