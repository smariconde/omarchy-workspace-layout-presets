from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from backend.profile_store import (
    ProfileAlreadyExistsError,
    ProfileError,
    ProfileNotFoundError,
    delete_profile,
    duplicate_profile,
    export_profile,
    import_profile,
    list_profiles,
    profiles_directory,
    read_profile,
    rename_profile,
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


def valid_window(identifier: str) -> dict[str, object]:
    return {
        "id": identifier,
        "app": {"desktopId": "kitty", "wmClass": "kitty", "ordinal": 1},
        "launch": {"kind": "desktop", "desktopId": "kitty"},
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

    def test_deep_validation_rejects_unknown_and_unsafe_profile_fields(self) -> None:
        profile = valid_profile()
        profile["command"] = "sh -c bad"
        with self.assertRaises(ProfileError):
            write_profile("coding", profile, self.environment)

    def test_deep_validation_rejects_invalid_tree_references_and_ratios(self) -> None:
        profile = valid_profile()
        profile["tiled"] = {
            "anchor": "editor",
            "nodes": [valid_window("editor"), valid_window("terminal")],
            "splits": [{"focus": "unknown", "direction": "right", "new": "terminal", "ratio": 1.2}],
        }
        with self.assertRaises(ProfileError):
            write_profile("coding", profile, self.environment)

    def test_deep_validation_accepts_exact_tree_and_normalized_floating_geometry(self) -> None:
        profile = valid_profile()
        profile["tiled"] = {
            "anchor": "editor",
            "nodes": [valid_window("editor"), valid_window("terminal")],
            "splits": [{"focus": "editor", "direction": "right", "new": "terminal", "ratio": 0.58}],
        }
        floating = valid_window("monitor")
        floating["geometry"] = {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.4}
        profile["floating"] = [floating]
        profile["warnings"] = [{"code": "duplicate_window", "message": "Window identity is best effort."}]

        write_profile("coding", profile, self.environment)
        self.assertEqual(read_profile("coding", self.environment), profile)

    def test_rename_changes_only_the_display_name(self) -> None:
        original = valid_profile()
        write_profile("coding", original, self.environment)

        renamed = rename_profile("coding", "Writing", self.environment)

        self.assertEqual(renamed["name"], "Writing")
        self.assertEqual(read_profile("coding", self.environment)["createdAt"], original["createdAt"])

    def test_duplicate_requires_an_unused_safe_identifier(self) -> None:
        write_profile("coding", valid_profile(), self.environment)

        duplicate_profile("coding", "coding-copy", self.environment)
        self.assertEqual(list_profiles(self.environment), ["coding", "coding-copy"])
        with self.assertRaises(ProfileAlreadyExistsError):
            duplicate_profile("coding", "coding-copy", self.environment)

    def test_delete_removes_only_the_selected_profile(self) -> None:
        write_profile("coding", valid_profile(), self.environment)
        write_profile("writing", valid_profile(), self.environment)

        delete_profile("coding", self.environment)

        self.assertEqual(list_profiles(self.environment), ["writing"])
        with self.assertRaises(ProfileNotFoundError):
            delete_profile("coding", self.environment)

    def test_export_is_validated_private_and_never_overwrites(self) -> None:
        write_profile("coding", valid_profile(), self.environment)
        destination = Path(self.temporary_directory.name) / "coding.json"

        exported = export_profile("coding", str(destination), self.environment)

        self.assertEqual(exported, destination)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8"))["name"], "Coding")
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ProfileAlreadyExistsError):
            export_profile("coding", str(destination), self.environment)

    def test_import_uses_safe_filename_id_validates_data_and_blocks_collisions(self) -> None:
        source = Path(self.temporary_directory.name) / "imported.json"
        source.write_text(json.dumps(valid_profile()), encoding="utf-8")

        profile_id, profile = import_profile(str(source), self.environment)

        self.assertEqual(profile_id, "imported")
        self.assertEqual(profile["name"], "Coding")
        with self.assertRaises(ProfileAlreadyExistsError):
            import_profile(str(source), self.environment)

        invalid_source = Path(self.temporary_directory.name) / "invalid.json"
        unsafe = deepcopy(valid_profile())
        unsafe["source"]["workspace"]["url"] = "https://example.invalid"
        invalid_source.write_text(json.dumps(unsafe), encoding="utf-8")
        with self.assertRaises(ProfileError):
            import_profile(str(invalid_source), self.environment)

    def test_transfers_require_absolute_paths(self) -> None:
        write_profile("coding", valid_profile(), self.environment)
        with self.assertRaises(ProfileError):
            export_profile("coding", "coding.json", self.environment)
        with self.assertRaises(ProfileError):
            import_profile("coding.json", self.environment)
