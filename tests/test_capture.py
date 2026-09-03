from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from backend.capture import CaptureError, build_profile, capture_current_workspace, profile_id_from_name
from backend.profile_store import ProfileAlreadyExistsError, read_profile


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FixtureReader:
    def __init__(self) -> None:
        self.responses = {
            "activeworkspace": fixture("activeworkspace.json"),
            "clients": fixture("clients.json"),
            "monitors": fixture("monitors.json"),
            "getoption general:layout": fixture("layout.json"),
        }

    def read_json(self, subject: str) -> object:
        return self.responses[subject]


class CaptureTests(unittest.TestCase):
    def test_fixture_capture_is_valid_profile_without_sensitive_client_fields(self) -> None:
        profile = build_profile(
            "Coding",
            active_workspace=fixture("activeworkspace.json"),
            clients=fixture("clients.json"),
            monitors=fixture("monitors.json"),
            layout=fixture("layout.json"),
            desktop_resolver=lambda window_class: {"Code": "code", "kitty": "kitty"}.get(window_class),
            created_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(profile["createdAt"], "2026-09-03T12:00:00Z")
        self.assertEqual(profile["source"], {"hyprlandLayout": "dwindle", "workspace": {"name": "3"}, "monitor": {"connector": "HDMI-A-2", "usableWidth": 1920, "usableHeight": 1024}})
        self.assertEqual([node["app"]["wmClass"] for node in profile["tiled"]["nodes"]], ["Code"])
        self.assertEqual(profile["floating"][0]["geometry"], {"x": 0.0625, "y": 0.09765625, "width": 0.3125, "height": 0.390625})
        serialized = json.dumps(profile)
        self.assertNotIn("Firefox", serialized)
        self.assertNotIn("pid", serialized)
        self.assertNotIn("title", serialized)
        self.assertEqual(profile["layoutConfidence"], "fallback")
        self.assertEqual(profile["warnings"][0]["code"], "layout_fallback")

    def test_capture_writes_a_new_profile_once_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as data_home:
            environment = {"XDG_DATA_HOME": data_home}

            def writer(profile_id: str, profile: object) -> Path:
                from backend.profile_store import create_profile
                return create_profile(profile_id, profile, environment)

            result = capture_current_workspace(
                "Código diario", reader=FixtureReader(), desktop_resolver=lambda _: "kitty", writer=writer,
                created_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            )
            self.assertEqual(result[0], "codigo-diario")
            self.assertEqual(read_profile("codigo-diario", environment)["name"], "Código diario")
            with self.assertRaises(ProfileAlreadyExistsError):
                capture_current_workspace("Código diario", reader=FixtureReader(), desktop_resolver=lambda _: "kitty", writer=writer)

    def test_non_dwindle_or_fullscreen_state_blocks_before_a_profile_is_written(self) -> None:
        bad_layout = fixture("layout.json")
        assert isinstance(bad_layout, dict)
        bad_layout["str"] = "master"
        with self.assertRaises(CaptureError):
            build_profile("Coding", active_workspace=fixture("activeworkspace.json"), clients=fixture("clients.json"), monitors=fixture("monitors.json"), layout=bad_layout)

        fullscreen_clients = fixture("clients.json")
        assert isinstance(fullscreen_clients, list)
        fullscreen_clients[0]["fullscreen"] = 1
        with self.assertRaises(CaptureError):
            build_profile("Coding", active_workspace=fixture("activeworkspace.json"), clients=fullscreen_clients, monitors=fixture("monitors.json"), layout=fixture("layout.json"))

    def test_unresolved_and_repeated_windows_are_explicitly_warned(self) -> None:
        clients = fixture("clients.json")
        assert isinstance(clients, list)
        repeated = dict(clients[0])
        repeated["at"] = [1200, 24]
        clients.append(repeated)
        profile = build_profile("Coding", active_workspace=fixture("activeworkspace.json"), clients=clients, monitors=fixture("monitors.json"), layout=fixture("layout.json"), desktop_resolver=lambda _: None)
        self.assertEqual(profile["tiled"]["nodes"][0]["launch"], {"kind": "unresolved"})
        self.assertIn("unresolved_launcher", [warning["code"] for warning in profile["warnings"]])
        self.assertIn("duplicate_window", [warning["code"] for warning in profile["warnings"]])

    def test_profile_ids_are_safe_and_deterministic(self) -> None:
        self.assertEqual(profile_id_from_name("  Código diario!  "), "codigo-diario")
        with self.assertRaises(CaptureError):
            profile_id_from_name("---")
