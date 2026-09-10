from __future__ import annotations

import json
import unittest

from backend.capture_review import commit_capture, prepare_capture
from tests.test_capture import FixtureReader, fixture


class BrowserReader(FixtureReader):
    def __init__(self) -> None:
        super().__init__()
        clients = fixture("clients.json")
        clients[0]["class"] = "Brave-browser"
        clients[0]["title"] = "YouTube — Brave"
        self.responses["clients"] = clients


class CaptureReviewTests(unittest.TestCase):
    def test_browser_window_requires_review_and_draft_contains_no_title_or_url(self) -> None:
        issued = {}

        def issuer(profile_id, profile, allowed):
            issued.update({"profileId": profile_id, "profile": profile, "allowed": allowed})
            return "a" * 32

        data, warnings = prepare_capture(
            "Videos",
            reader=BrowserReader(),
            desktop_resolver=lambda window_class: "brave-browser" if "Brave" in window_class else "kitty",
            webapp_lister=lambda: [{"desktopId": "YouTube", "displayName": "YouTube"}],
            writer=lambda profile_id, profile: self.fail("ambiguous capture must not be persisted"),
            draft_issuer=issuer,
        )

        self.assertFalse(data["saved"])
        self.assertEqual(data["review"][0]["suggestedDesktopId"], "YouTube")
        self.assertEqual(data["review"][0]["title"], "YouTube — Brave")
        self.assertEqual(issued["allowed"]["window-1"], ["brave-browser", "YouTube"])
        serialized_draft = json.dumps(issued)
        self.assertNotIn("YouTube — Brave", serialized_draft)
        self.assertNotIn("youtube.com", serialized_draft.casefold())
        self.assertIn("webapp_review", [warning["code"] for warning in warnings])

    def test_confirmed_webapp_desktop_id_is_the_only_persisted_identity(self) -> None:
        holder = {}

        def issuer(profile_id, profile, allowed):
            holder["record"] = {
                "profileId": profile_id,
                "profile": profile,
                "allowedAssignments": allowed,
            }
            return "b" * 32

        prepare_capture(
            "Videos",
            reader=BrowserReader(),
            desktop_resolver=lambda window_class: "brave-browser" if "Brave" in window_class else "kitty",
            webapp_lister=lambda: [{"desktopId": "YouTube", "displayName": "YouTube"}],
            draft_issuer=issuer,
        )
        written = {}
        consumed = []
        profile_id, profile = commit_capture(
            "b" * 32,
            '{"window-1":"YouTube"}',
            draft_reader=lambda capture_id: holder["record"],
            draft_consumer=consumed.append,
            writer=lambda key, value: written.update({"id": key, "profile": value}),
        )

        node = profile["tiled"]["nodes"][0]
        self.assertEqual(profile_id, "videos")
        self.assertEqual(node["launch"], {"kind": "desktop", "desktopId": "YouTube"})
        self.assertEqual(node["app"]["wmClass"], "Brave-browser")
        self.assertNotIn("title", json.dumps(profile))
        self.assertEqual(consumed, ["b" * 32])
        self.assertEqual(written["id"], "videos")

    def test_unoffered_launcher_is_rejected_before_writing(self) -> None:
        record = {
            "profileId": "videos",
            "profile": {
                "schemaVersion": 1,
                "name": "Videos",
                "createdAt": "2026-09-09T12:00:00Z",
                "source": {"hyprlandLayout": "dwindle", "workspace": {"name": "3"}, "monitor": {"connector": "HDMI-A-2", "usableWidth": 1920, "usableHeight": 1024}},
                "layoutConfidence": "exact",
                "tiled": {
                    "anchor": "window-1",
                    "nodes": [{
                        "id": "window-1",
                        "app": {"desktopId": None, "wmClass": "Brave-browser", "ordinal": 1},
                        "launch": {"kind": "unresolved"},
                    }],
                    "splits": [],
                },
                "floating": [],
                "warnings": [],
            },
            "allowedAssignments": {"window-1": ["YouTube"]},
        }
        with self.assertRaisesRegex(Exception, "not offered"):
            commit_capture(
                "c" * 32,
                '{"window-1":"../../bad"}',
                draft_reader=lambda capture_id: record,
                writer=lambda key, value: self.fail("invalid assignment must not be written"),
            )
