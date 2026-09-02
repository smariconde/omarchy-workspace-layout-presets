from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.profile_store import (
    ProfileError,
    ProfileNotFoundError,
    list_profiles,
    profiles_directory,
    read_profile,
    validate_profile_id,
    write_profile,
)


def valid_profile() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "name": "Coding",
        "createdAt": "2026-09-02T12:00:00Z",
        "source": {
            "hyprlandLayout": "dwindle",
            "workspace": {"name": "3"},
            "monitor": {"connector": "HDMI-A-2", "usableWidth": 1920, "usableHeight": 1048},
        },
        "layoutConfidence": "exact",
        "tiled": {"anchor": None, "nodes": [], "splits": []},
        "floating": [],
        "warnings": [],
    }


class ProfileStorePathTests(unittest.TestCase):
    def test_uses_xdg_data_home_when_supplied(self) -> None:
        environment = {"XDG_DATA_HOME": "/var/example-data", "HOME": "/home/example"}
        self.assertEqual(
            profiles_directory(environment),
            Path("/var/example-data/omarchy-workspace-layout-presets/profiles"),
        )

    def test_defaults_to_local_share(self) -> None:
        self.assertEqual(
            profiles_directory({"HOME": "/home/example"}),
            Path("/home/example/.local/share/omarchy-workspace-layout-presets/profiles"),
        )


class ProfileStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.environment = {"XDG_DATA_HOME": self.temporary_directory.name}

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_writes_and_reads_valid_profile(self) -> None:
        path = write_profile("coding", valid_profile(), self.environment)

        self.assertEqual(path.name, "coding.json")
        self.assertEqual(read_profile("coding", self.environment)["name"], "Coding")
        self.assertEqual(list_profiles(self.environment), ["coding"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_rejects_path_traversal_in_profile_id(self) -> None:
        for profile_id in ("../outside", "UPPERCASE", "", "space name"):
            with self.subTest(profile_id=profile_id):
                with self.assertRaises(ProfileError):
                    validate_profile_id(profile_id)

    def test_rejects_invalid_profile_before_creating_file(self) -> None:
        invalid = valid_profile()
        invalid["layoutConfidence"] = "unknown"

        with self.assertRaises(ProfileError):
            write_profile("coding", invalid, self.environment)
        self.assertFalse(profiles_directory(self.environment).exists())

    def test_rejects_malformed_json_when_reading(self) -> None:
        directory = profiles_directory(self.environment)
        directory.mkdir(parents=True)
        (directory / "broken.json").write_text("{not json", encoding="utf-8")

        with self.assertRaises(ProfileError):
            read_profile("broken", self.environment)

    def test_reports_missing_profile(self) -> None:
        with self.assertRaises(ProfileNotFoundError):
            read_profile("missing", self.environment)

    def test_only_lists_safe_profile_identifiers(self) -> None:
        directory = profiles_directory(self.environment)
        directory.mkdir(parents=True)
        (directory / "valid-name.json").write_text(json.dumps(valid_profile()), encoding="utf-8")
        (directory / "not valid.json").write_text(json.dumps(valid_profile()), encoding="utf-8")

        self.assertEqual(list_profiles(self.environment), ["valid-name"])
