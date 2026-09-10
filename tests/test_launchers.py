from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.launchers import (
    LauncherError,
    desktop_entry_command,
    desktop_entry_metadata,
    list_webapp_entries,
    resolve_desktop_id,
)


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

    def test_resolves_a_desktop_entry_to_argv_without_expanding_user_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "code.desktop").write_text(
                "[Desktop Entry]\nType=Application\nExec=code --reuse-window %%\n", encoding="utf-8"
            )

            self.assertEqual(desktop_entry_command("code", directories=[directory]), ["code", "--reuse-window", "%"])

    def test_omits_empty_file_or_url_field_codes_and_rejects_unsupported_ones(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "files.desktop").write_text(
                "[Desktop Entry]\nType=Application\nExec=app %U\n", encoding="utf-8"
            )
            (directory / "unsupported.desktop").write_text(
                "[Desktop Entry]\nType=Application\nExec=app %c\n", encoding="utf-8"
            )
            (directory / "shell.desktop").write_text(
                "[Desktop Entry]\nType=Application\nExec=sh -c 'echo unsafe'\n", encoding="utf-8"
            )

            self.assertEqual(desktop_entry_command("files", directories=[directory]), ["app"])
            with self.assertRaises(LauncherError):
                desktop_entry_command("unsupported", directories=[directory])
            with self.assertRaises(LauncherError):
                desktop_entry_command("shell", directories=[directory])

    def test_reads_display_metadata_and_classifies_omarchy_webapps_without_leaking_exec(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "code.desktop").write_text(
                "[Desktop Entry]\nType=Application\nName=Code\nGenericName=Code Editor\n"
                "Categories=Development;IDE;\nExec=code\n",
                encoding="utf-8",
            )
            (directory / "YouTube.desktop").write_text(
                "[Desktop Entry]\nType=Application\nName=YouTube\nCategories=AudioVideo;\n"
                "Exec=omarchy-launch-webapp https://youtube.com/\n",
                encoding="utf-8",
            )

            app = desktop_entry_metadata("code", directories=[directory])
            webapp = desktop_entry_metadata("YouTube", directories=[directory])

            self.assertEqual(app["displayName"], "Code")
            self.assertEqual(app["genericName"], "Code Editor")
            self.assertEqual(app["kind"], "application")
            self.assertEqual(webapp["kind"], "webapp")
            self.assertNotIn("Exec", app)
            self.assertNotIn("Exec", webapp)
            self.assertNotIn("youtube.com", str(webapp))

    def test_metadata_falls_back_cleanly_for_missing_or_malformed_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "broken.desktop").write_text("not a desktop entry", encoding="utf-8")

            self.assertIsNone(desktop_entry_metadata("missing", directories=[directory]))
            self.assertIsNone(desktop_entry_metadata("broken", directories=[directory]))

    def test_webapps_with_spaces_are_listed_and_launchable_without_leaking_urls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "Google Docs.desktop").write_text(
                "[Desktop Entry]\nType=Application\nName=Google Docs\n"
                "Exec=omarchy-launch-webapp https://docs.google.com/\n",
                encoding="utf-8",
            )

            entries = list_webapp_entries(directories=[directory])

            self.assertEqual(entries, [{"desktopId": "Google Docs", "displayName": "Google Docs"}])
            self.assertEqual(
                desktop_entry_command("Google Docs", directories=[directory]),
                ["omarchy-launch-webapp", "https://docs.google.com/"],
            )
            self.assertNotIn("google.com", str(entries))

    def test_desktop_ids_with_path_components_remain_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            for desktop_id in ("../YouTube", "folder/YouTube", "folder\\YouTube", " YouTube"):
                with self.subTest(desktop_id=desktop_id), self.assertRaises(LauncherError):
                    desktop_entry_command(desktop_id, directories=[Path(temporary_directory)])
