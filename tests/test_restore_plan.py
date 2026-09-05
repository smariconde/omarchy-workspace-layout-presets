from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from backend.plan_store import plans_directory, profile_digest, read_plan
from backend.profile_store import write_profile
from backend.restore import (
    Plan,
    PlanBlocked,
    PlanError,
    build_plan,
    compatibility_blockers,
    parse_hyprland_version,
    plan_profile,
    revalidate_approved_plan,
)


def node(identifier: str, wm_class: str, desktop_id: str | None, ordinal: int = 1) -> dict[str, object]:
    return {
        "id": identifier,
        "app": {"desktopId": desktop_id, "wmClass": wm_class, "ordinal": ordinal},
        "launch": {"kind": "desktop", "desktopId": desktop_id} if desktop_id else {"kind": "unresolved"},
    }


PROFILE: dict[str, object] = {
    "schemaVersion": 1,
    "name": "Coding",
    "createdAt": "2026-09-03T12:00:00Z",
    "source": {
        "hyprlandLayout": "dwindle",
        "workspace": {"name": "3"},
        "monitor": {"connector": "HDMI-A-2", "usableWidth": 1920, "usableHeight": 1024},
    },
    "layoutConfidence": "exact",
    "tiled": {
        "anchor": "window-1",
        "nodes": [node("window-1", "Code", "code"), node("window-2", "kitty", "kitty")],
        "splits": [{"focus": "window-1", "direction": "right", "new": "window-2", "ratio": 0.6}],
    },
    "floating": [dict(node("window-3", "Pavucontrol", "pavucontrol"), geometry={"x": 0.5, "y": 0.25, "width": 0.25, "height": 0.5})],
    "warnings": [],
}

EMPTY_WORKSPACE = {"id": 5, "name": "5", "monitor": "HDMI-A-2"}
MONITORS = [
    {
        "name": "HDMI-A-2",
        "x": 0,
        "y": 0,
        "width": 1920,
        "height": 1080,
        "reserved": [24, 32, 0, 0],
        "activeWorkspace": {"id": 5, "name": "5"},
    }
]
LAYOUT = {"str": "dwindle"}


def plan_for(profile: dict[str, object] | None = None, **overrides: object) -> Plan:
    arguments: dict[str, object] = {
        "active_workspace": EMPTY_WORKSPACE,
        "clients": [{"workspace": {"id": 7, "name": "7"}, "class": "Firefox"}],
        "monitors": copy.deepcopy(MONITORS),
        "layout": LAYOUT,
    }
    arguments.update(overrides)
    return build_plan(copy.deepcopy(PROFILE) if profile is None else profile, **arguments)  # type: ignore[arg-type]


def codes(entries: list[dict[str, str]]) -> list[str]:
    return [entry["code"] for entry in entries]


class BuildPlanTests(unittest.TestCase):
    def test_compatibility_guard_requires_the_tested_version_and_verified_lua_bridge(self) -> None:
        self.assertEqual(parse_hyprland_version("Hyprland v0.56.1 built from abc"), (0, 56, 1))
        self.assertEqual(
            [entry["code"] for entry in compatibility_blockers("Hyprland v0.56.1", layout=LAYOUT, lua_bridge_verified=False)],
            ["dispatch_unverified"],
        )
        self.assertEqual(
            [entry["code"] for entry in compatibility_blockers("Hyprland v0.55.2", layout=LAYOUT, lua_bridge_verified=True)],
            ["unsupported_hyprland"],
        )

    def test_compatibility_guard_does_not_guess_from_a_version_or_layout(self) -> None:
        blocked = compatibility_blockers("not a version", layout={"str": "master"}, lua_bridge_verified=False)
        self.assertEqual([entry["code"] for entry in blocked], ["unsupported_hyprland", "unsupported_layout", "dispatch_unverified"])

    def test_approved_plan_is_rejected_when_profile_or_target_changed(self) -> None:
        plan = plan_for()
        record = {
            "profileId": "coding",
            "profileDigest": profile_digest(PROFILE),
            "target": plan.data["target"],
        }

        revalidate_approved_plan(record, profile_id="coding", profile=PROFILE, current_plan=plan)

        changed_profile = copy.deepcopy(PROFILE)
        changed_profile["name"] = "Different"
        with self.assertRaises(PlanBlocked) as profile_error:
            revalidate_approved_plan(record, profile_id="coding", profile=changed_profile, current_plan=plan)
        self.assertEqual(codes(profile_error.exception.blocked), ["profile_changed"])

        changed_target = copy.deepcopy(plan.data["target"])
        changed_target["workspace"]["id"] = 6  # type: ignore[index]
        changed_plan = Plan({**plan.data, "target": changed_target}, plan.warnings)
        with self.assertRaises(PlanBlocked) as target_error:
            revalidate_approved_plan(record, profile_id="coding", profile=PROFILE, current_plan=changed_plan)
        self.assertEqual(codes(target_error.exception.blocked), ["target_changed"])

    def test_empty_workspace_yields_launch_entries_and_the_saved_split_tree(self) -> None:
        plan = plan_for()

        self.assertEqual(plan.data["layoutMode"], "tree")
        self.assertEqual(
            plan.data["target"],
            {
                "workspace": {"id": 5, "name": "5"},
                "monitor": {"connector": "HDMI-A-2", "usableWidth": 1920, "usableHeight": 1024},
                "clientCount": 0,
            },
        )
        self.assertEqual(plan.data["summary"], {"launch": 3, "skip": 0, "tiled": 2, "floating": 1})
        self.assertEqual(
            plan.data["steps"],
            [
                {"op": "anchor", "windowId": "window-1"},
                {"op": "split", "focus": "window-1", "direction": "right", "new": "window-2", "ratio": 0.6},
            ],
        )
        self.assertEqual([entry["kind"] for entry in plan.data["entries"]], ["launch", "launch", "launch"])
        self.assertEqual(plan.data["entries"][2]["geometry"], {"x": 960, "y": 256, "width": 480, "height": 512})
        self.assertEqual(plan.warnings, [])

    def test_a_client_in_the_target_workspace_blocks_the_restore(self) -> None:
        occupied = [{"workspace": {"id": 5, "name": "5"}, "class": "Firefox"}]

        with self.assertRaises(PlanBlocked) as raised:
            plan_for(clients=occupied)

        self.assertEqual(codes(raised.exception.blocked), ["workspace_not_empty"])

    def test_unsupported_layout_or_special_workspace_blocks_before_any_read_of_windows(self) -> None:
        with self.assertRaises(PlanBlocked) as unsupported_layout:
            plan_for(layout={"str": "master"})
        self.assertEqual(codes(unsupported_layout.exception.blocked), ["unsupported_layout"])

        with self.assertRaises(PlanBlocked) as special:
            plan_for(active_workspace={"id": 5, "name": "special:magic", "monitor": "HDMI-A-2"})
        self.assertEqual(codes(special.exception.blocked), ["unsupported_workspace"])

    def test_an_unusable_target_monitor_blocks_instead_of_guessing_a_rectangle(self) -> None:
        with self.assertRaises(PlanBlocked) as raised:
            plan_for(monitors=[])
        self.assertEqual(codes(raised.exception.blocked), ["monitor_unavailable"])

    def test_a_profile_without_any_resolved_launcher_has_nothing_to_restore(self) -> None:
        profile = copy.deepcopy(PROFILE)
        profile["tiled"]["nodes"] = [node("window-1", "Code", None), node("window-2", "kitty", None)]  # type: ignore[index]
        profile["floating"] = []  # type: ignore[index]

        with self.assertRaises(PlanBlocked) as raised:
            plan_for(profile)

        self.assertEqual(codes(raised.exception.blocked), ["nothing_to_restore"])
        self.assertIn("unresolved_launcher", codes(raised.exception.warnings))

    def test_an_unresolved_tiled_window_degrades_to_launch_order_and_says_so(self) -> None:
        profile = copy.deepcopy(PROFILE)
        profile["tiled"]["nodes"][1] = node("window-2", "kitty", None)  # type: ignore[index]

        plan = plan_for(profile)

        self.assertEqual(plan.data["layoutMode"], "order")
        self.assertEqual(plan.data["steps"], [{"op": "append", "windowId": "window-1"}])
        self.assertEqual(plan.data["summary"], {"launch": 2, "skip": 1, "tiled": 2, "floating": 1})
        self.assertEqual(plan.data["entries"][1]["reason"]["code"], "unresolved_launcher")
        self.assertIn("tree_incomplete", codes(plan.warnings))

    def test_a_fallback_profile_never_claims_an_exact_tree(self) -> None:
        profile = copy.deepcopy(PROFILE)
        profile["layoutConfidence"] = "fallback"

        plan = plan_for(profile)

        self.assertEqual(plan.data["layoutMode"], "order")
        self.assertEqual(codes(plan.warnings), ["layout_fallback"])

    def test_a_smaller_monitor_scales_and_clamps_floating_geometry_with_a_warning(self) -> None:
        monitors = copy.deepcopy(MONITORS)
        monitors[0].update({"name": "eDP-1", "width": 1280, "height": 800, "reserved": [24, 0, 0, 0]})
        workspace = dict(EMPTY_WORKSPACE, monitor="eDP-1")
        profile = copy.deepcopy(PROFILE)
        profile["floating"][0]["geometry"] = {"x": 0.9, "y": 0.9, "width": 0.5, "height": 0.5}  # type: ignore[index]

        plan = plan_for(profile, active_workspace=workspace, monitors=monitors)

        self.assertEqual(plan.data["target"]["monitor"], {"connector": "eDP-1", "usableWidth": 1280, "usableHeight": 776})
        self.assertEqual(plan.data["entries"][2]["geometry"], {"x": 640, "y": 388, "width": 640, "height": 388})
        self.assertEqual(codes(plan.warnings), ["monitor_changed", "geometry_clamped"])

    def test_an_invalid_profile_is_an_error_rather_than_a_plan(self) -> None:
        profile = copy.deepcopy(PROFILE)
        profile["tiled"]["splits"][0]["ratio"] = 4  # type: ignore[index]

        with self.assertRaises(PlanError):
            plan_for(profile)


class PlanProfileTests(unittest.TestCase):
    class Reader:
        def __init__(self, clients: list[dict[str, object]] | None = None) -> None:
            self.responses = {
                "activeworkspace": EMPTY_WORKSPACE,
                "clients": [] if clients is None else clients,
                "monitors": copy.deepcopy(MONITORS),
                "getoption general:layout": LAYOUT,
            }

        def read_json(self, subject: str) -> object:
            return self.responses[subject]

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.environment = {"XDG_DATA_HOME": str(root / "data"), "XDG_RUNTIME_DIR": str(root / "run")}
        write_profile("coding", PROFILE, self.environment)

    def test_planning_issues_a_single_use_token_that_carries_no_instructions(self) -> None:
        data, warnings = plan_profile(
            "coding",
            reader=self.Reader(),
            environment=self.environment,
            now=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(warnings, [])
        self.assertEqual(data["profileId"], "coding")
        self.assertEqual(data["expiresAt"], "2026-09-04T12:05:00Z")
        record = read_plan(data["planId"], self.environment, datetime(2026, 9, 4, 12, 1, tzinfo=UTC))
        self.assertEqual(record["target"], data["target"])
        self.assertEqual(sorted(record), ["createdAt", "expiresAt", "planId", "profileDigest", "profileId", "target"])
        serialized = json.dumps(record)
        for forbidden in ("desktopId", "steps", "entries", "anchor", "split", "code"):
            self.assertNotIn(forbidden, serialized)

    def test_a_blocked_plan_issues_no_token_at_all(self) -> None:
        reader = self.Reader(clients=[{"workspace": {"id": 5, "name": "5"}, "class": "Firefox"}])

        with self.assertRaises(PlanBlocked):
            plan_profile("coding", reader=reader, environment=self.environment)

        self.assertFalse(plans_directory(self.environment).exists())


if __name__ == "__main__":
    unittest.main()
