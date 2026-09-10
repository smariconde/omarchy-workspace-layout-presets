from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from backend.capture import CaptureError
from backend.plan_store import PlanNotFoundError, plans_directory, profile_digest, read_plan
from backend.profile_store import write_profile
from backend.restore import (
    Plan,
    PlanBlocked,
    PlanError,
    ReplayError,
    SystemReplayExecutor,
    build_plan,
    compatibility_blockers,
    build_replay_actions,
    parse_hyprland_version,
    plan_profile,
    revalidate_approved_plan,
    restore_approved_plan,
)


class SystemReplayExecutorTests(unittest.TestCase):
    def test_wait_requires_the_new_window_when_browser_classes_repeat(self) -> None:
        old = {"address": "0x1", "class": "Brave-browser", "workspace": {"id": 4}}
        new = {"address": "0x2", "class": "Brave-browser", "workspace": {"id": 4}}

        class Reader:
            def __init__(self) -> None:
                self.responses = [[old], [old], [old, new]]
                self.reads = 0

            def read_json(self, subject: str):
                self.reads += 1
                return self.responses.pop(0)

        elapsed = [0.0]
        reader = Reader()
        commands = []
        launches = []
        executor = SystemReplayExecutor(
            target_workspace_id=4,
            reader=reader,
            runner=lambda argv, **kwargs: commands.append(argv) or SimpleNamespace(returncode=0),
            launcher=lambda argv, **kwargs: launches.append((argv, kwargs)) or SimpleNamespace(),
            clock=lambda: elapsed[0],
            sleeper=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
            command_timeout=1,
            window_timeout=1,
            poll_interval=0.1,
        )

        executor.launch(["omarchy-launch-webapp", "https://example.invalid"])

        self.assertEqual(launches[0][0], ["omarchy-launch-webapp", "https://example.invalid"])
        self.assertTrue(launches[0][1]["start_new_session"])
        self.assertFalse(launches[0][1]["shell"])
        self.assertTrue(executor.wait_for_window("window-2", "Brave-browser", "tiled"))
        executor.focus_window("window-2", "Brave-browser")
        self.assertEqual(reader.reads, 3)
        self.assertEqual(
            commands[-1],
            ["hyprctl", "dispatch", 'hl.dsp.focus({ window = "address:0x2" })'],
        )

    def test_launch_does_not_apply_the_dispatch_timeout_to_a_long_lived_application(self) -> None:
        class Reader:
            def read_json(self, subject: str):
                return []

        launches = []
        executor = SystemReplayExecutor(
            target_workspace_id=4,
            reader=Reader(),
            runner=lambda *args, **kwargs: self.fail("application launch must not use subprocess.run"),
            launcher=lambda argv, **kwargs: launches.append((argv, kwargs)) or SimpleNamespace(),
            command_timeout=5,
        )

        executor.launch(["/usr/bin/chromium"])

        self.assertEqual(launches[0][0], ["/usr/bin/chromium"])
        self.assertNotIn("timeout", launches[0][1])
        self.assertEqual(launches[0][1]["stdout"], subprocess.DEVNULL)
        self.assertEqual(launches[0][1]["stderr"], subprocess.DEVNULL)

    def test_window_wait_has_a_longer_budget_than_short_dispatch_commands(self) -> None:
        elapsed = [0.0]

        class Reader:
            def read_json(self, subject: str):
                if elapsed[0] < 8:
                    return []
                return [{"address": "0x8", "class": "SlowApp", "workspace": {"id": 4}}]

        executor = SystemReplayExecutor(
            target_workspace_id=4,
            reader=Reader(),
            launcher=lambda argv, **kwargs: SimpleNamespace(),
            clock=lambda: elapsed[0],
            sleeper=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
            command_timeout=5,
            window_timeout=30,
            poll_interval=1,
        )

        executor.launch(["slow-app"])

        self.assertTrue(executor.wait_for_window("slow", "SlowApp", "tiled"))
        self.assertEqual(elapsed[0], 8)

    def test_invalid_launcher_input_is_reported_as_a_replay_error(self) -> None:
        class Reader:
            def read_json(self, subject: str):
                return []

        def invalid_launcher(argv, **kwargs):
            raise ValueError("embedded null byte")

        executor = SystemReplayExecutor(
            target_workspace_id=4,
            reader=Reader(),
            launcher=invalid_launcher,
        )

        with self.assertRaisesRegex(ReplayError, "launcher failed to execute"):
            executor.launch(["invalid\0launcher"])

    def test_hyprland_read_failure_after_launch_is_a_replay_error(self) -> None:
        class Reader:
            def __init__(self) -> None:
                self.reads = 0

            def read_json(self, subject: str):
                self.reads += 1
                if self.reads == 1:
                    return []
                raise CaptureError("socket disappeared")

        executor = SystemReplayExecutor(
            target_workspace_id=4,
            reader=Reader(),
            launcher=lambda argv, **kwargs: SimpleNamespace(),
        )
        executor.launch(["app"])

        with self.assertRaisesRegex(ReplayError, "could not observe target windows"):
            executor.wait_for_window("app", "App", "tiled")

    def test_verification_detects_a_restored_tree_with_swapped_sides(self) -> None:
        correct_clients = [
            {"address": "0xa", "class": "YouTube", "floating": False, "workspace": {"id": 4}, "at": [10, 10], "size": [574, 980]},
            {"address": "0xb", "class": "X", "floating": False, "workspace": {"id": 4}, "at": [594, 10], "size": [396, 980]},
        ]

        class Reader:
            def __init__(self, clients):
                self.clients = clients

            def read_json(self, subject: str):
                return self.clients

        plan = {
            "layoutMode": "tree",
            "target": {"workspace": {"id": 4}},
            "entries": [
                {"kind": "launch", "windowId": "youtube", "wmClass": "YouTube", "placement": "tiled"},
                {"kind": "launch", "windowId": "x", "wmClass": "X", "placement": "tiled"},
            ],
            "steps": [
                {"op": "anchor", "windowId": "youtube"},
                {"op": "split", "focus": "youtube", "direction": "right", "new": "x", "ratio": 0.4},
            ],
        }
        executor = SystemReplayExecutor(target_workspace_id=4, reader=Reader(correct_clients))
        executor._window_addresses = {"youtube": "0xa", "x": "0xb"}

        self.assertEqual(executor.verify(plan)["geometryMismatched"], 0)

        swapped = [dict(correct_clients[0], at=[594, 10], size=[396, 980]), dict(correct_clients[1], at=[10, 10], size=[574, 980])]
        executor._reader = Reader(swapped)
        self.assertEqual(executor.verify(plan)["geometryMismatched"], 2)


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
    def test_replay_compiler_emits_only_explicit_argv_actions(self) -> None:
        plan = plan_for()
        actions = build_replay_actions(
            PROFILE,
            plan.data,
            launcher_resolver=lambda desktop_id: [desktop_id, "--safe"],
        )

        self.assertEqual(
            actions,
            [
                {"op": "launch", "windowId": "window-1", "placement": "tiled", "wmClass": "Code", "argv": ["code", "--safe"]},
                {"op": "focus", "windowId": "window-1", "wmClass": "Code"},
                {"op": "dispatch", "argv": ["hyprctl", "dispatch", 'hl.dsp.layout("preselect r")']},
                {"op": "launch", "windowId": "window-2", "placement": "tiled", "wmClass": "kitty", "argv": ["kitty", "--safe"]},
                {
                    "op": "dispatch",
                    "argv": ["hyprctl", "dispatch", 'hl.dsp.layout("splitratio 0.80000000000000004 exact")'],
                    "windowId": "window-2",
                },
                {"op": "launch", "windowId": "window-3", "placement": "floating", "wmClass": "Pavucontrol", "argv": ["pavucontrol", "--safe"]},
                {
                    "op": "dispatch",
                    "argv": ["hyprctl", "dispatch", 'hl.dsp.window.float({ action = "set" })'],
                    "windowId": "window-3",
                },
                {
                    "op": "dispatch",
                    "argv": ["hyprctl", "dispatch", "hl.dsp.window.move({ x = 960, y = 256, relative = false })"],
                    "windowId": "window-3",
                },
                {
                    "op": "dispatch",
                    "argv": ["hyprctl", "dispatch", "hl.dsp.window.resize({ x = 480, y = 512, relative = false })"],
                    "windowId": "window-3",
                },
            ],
        )
        for action in actions:
            if action["op"] == "launch":
                self.assertNotIn("shell", action["argv"])

    def test_replay_converts_the_nested_ratios_from_the_reported_layout(self) -> None:
        profile = copy.deepcopy(PROFILE)
        profile["floating"] = []
        profile["tiled"] = {
            "anchor": "window-1",
            "nodes": [
                node("window-1", "Brave-browser", "YouTube", 1),
                node("window-2", "com.mitchellh.ghostty", "com.mitchellh.ghostty"),
                node("window-3", "Brave-browser", "X", 2),
            ],
            "splits": [
                {
                    "focus": "window-1",
                    "direction": "right",
                    "new": "window-3",
                    "ratio": 0.41244725738396626,
                },
                {
                    "focus": "window-1",
                    "direction": "down",
                    "new": "window-2",
                    "ratio": 0.4669902912621359,
                },
            ],
        }
        actions = build_replay_actions(
            profile,
            plan_for(profile).data,
            launcher_resolver=lambda desktop_id: [desktop_id],
        )

        ratio_dispatches = [
            action["argv"][2]
            for action in actions
            if action["op"] == "dispatch" and "splitratio" in action["argv"][2]
        ]
        self.assertEqual(
            ratio_dispatches,
            [
                'hl.dsp.layout("splitratio 1.1751054852320675 exact")',
                'hl.dsp.layout("splitratio 1.066019417475728 exact")',
            ],
        )

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

    def test_restore_revalidates_before_consuming_the_token(self) -> None:
        data, _ = plan_profile(
            "coding",
            reader=self.Reader(),
            environment=self.environment,
            now=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
        )
        with self.assertRaises(PlanBlocked) as raised:
            restore_approved_plan(
                data["planId"],
                reader=self.Reader(clients=[{"workspace": {"id": 5, "name": "5"}}]),
                executor=object(),  # The safety check fails before the executor can be touched.
                version_output="Hyprland v0.56.2",
                lua_bridge_verified=True,
                launcher_resolver=lambda desktop_id: [desktop_id],
                environment=self.environment,
                now=datetime(2026, 9, 4, 12, 1, tzinfo=UTC),
            )

        self.assertEqual(codes(raised.exception.blocked), ["workspace_not_empty"])
        self.assertEqual(read_plan(data["planId"], self.environment, datetime(2026, 9, 4, 12, 1, tzinfo=UTC))["profileId"], "coding")

    def test_restore_consumes_once_then_reports_verified_result(self) -> None:
        data, _ = plan_profile(
            "coding",
            reader=self.Reader(),
            environment=self.environment,
            now=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
        )

        class Executor:
            def __init__(self) -> None:
                self.operations: list[tuple[str, object]] = []

            def launch(self, argv: list[str]) -> None:
                self.operations.append(("launch", argv))

            def dispatch(self, argv: list[str]) -> None:
                self.operations.append(("dispatch", argv))

            def focus_target(self) -> None:
                self.operations.append(("focus_target", None))

            def focus_window(self, window_id: str, wm_class: str) -> None:
                self.operations.append(("focus_window", (window_id, wm_class)))

            def wait_for_window(self, window_id: str, wm_class: str, placement: str) -> bool:
                self.operations.append(("wait", (window_id, wm_class, placement)))
                return True

            def verify(self, plan: dict[str, object]) -> dict[str, object]:
                self.operations.append(("verify", plan["target"]))
                return {"matched": 3, "mismatched": 0}

        executor = Executor()
        result = restore_approved_plan(
            data["planId"],
            reader=self.Reader(),
            executor=executor,
            version_output="Hyprland v0.56.2",
            lua_bridge_verified=True,
            launcher_resolver=lambda desktop_id: [desktop_id],
            environment=self.environment,
            now=datetime(2026, 9, 4, 12, 1, tzinfo=UTC),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["verification"], {"matched": 3, "mismatched": 0})
        self.assertEqual(result["executedActions"], 9)
        with self.assertRaises(PlanNotFoundError):
            read_plan(data["planId"], self.environment, datetime(2026, 9, 4, 12, 1, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()
