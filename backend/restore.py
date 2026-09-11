"""Read-only restore planning, and the single home for Hyprland dispatch syntax.

Planning changes nothing. It reads the current desktop, decides whether the
active workspace can safely receive a profile, and returns a preview made of
``launch`` and ``skip`` entries plus the layout steps a later restore would
replay. Any failed precondition — a non-empty workspace above all — is a
``blocked`` result, never a partial action.

The plan the user approves is remembered only as an opaque token plus the
conditions that were verified (see ``plan_store``); the steps below are always
recomputed from the validated profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
import subprocess
import time
from typing import Any, Callable, Mapping, Protocol

from .capture import CaptureError, HyprctlReader, SystemHyprctlReader, usable_workspace_rectangle
from .layout_preview import expand_layout
from .plan_store import PlanStoreError, consume_plan, issue_plan, profile_digest, read_plan
from .profile_store import ProfileError, read_profile, validate_profile


class PlanError(ValueError):
    """Raised when a plan cannot be produced from valid, available data."""


class PlanBlocked(Exception):
    """Raised when a safety precondition refuses the restore before any change."""

    def __init__(self, blocked: list[dict[str, str]], warnings: list[dict[str, str]] | None = None) -> None:
        super().__init__("; ".join(entry["message"] for entry in blocked))
        self.blocked = blocked
        self.warnings = [] if warnings is None else warnings


class ReplayError(ValueError):
    """Raised when a validated plan cannot become safe replay actions."""


class ReplayExecutor(Protocol):
    """Injectable boundary for the state-changing part of a restore."""

    def launch(self, argv: list[str]) -> None: ...

    def dispatch(self, argv: list[str]) -> None: ...

    def focus_target(self) -> None: ...

    def focus_window(self, window_id: str, wm_class: str) -> None: ...

    def wait_for_window(self, window_id: str, wm_class: str, placement: str) -> bool: ...

    def verify(self, plan: Mapping[str, Any]) -> Mapping[str, Any]: ...


class SystemReplayExecutor:
    """Execute already-validated argv actions against one target workspace."""

    def __init__(
        self,
        *,
        target_workspace_id: int,
        reader: HyprctlReader,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        launcher: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        command_timeout: float = 5.0,
        window_timeout: float = 30.0,
        poll_interval: float = 0.1,
    ) -> None:
        self._target_workspace_id = target_workspace_id
        self._reader = reader
        self._runner = runner
        self._launcher = launcher
        self._clock = clock
        self._sleeper = sleeper
        self._command_timeout = command_timeout
        self._window_timeout = window_timeout
        self._poll_interval = poll_interval
        self._addresses_before_launch: set[str] = set()
        self._window_addresses: dict[str, str] = {}

    def _target_addresses(self) -> set[str]:
        try:
            clients = self._reader.read_json("clients")
        except (OSError, CaptureError) as error:
            raise ReplayError("could not snapshot target windows before launch") from error
        if not isinstance(clients, list):
            raise ReplayError("Hyprland clients snapshot was not an array")
        return {
            client["address"]
            for client in clients
            if isinstance(client, Mapping)
            and isinstance(client.get("address"), str)
            and isinstance(client.get("workspace"), Mapping)
            and client["workspace"].get("id") == self._target_workspace_id
        }

    def _run(self, argv: list[str]) -> None:
        if not argv or not all(isinstance(argument, str) and argument for argument in argv):
            raise ReplayError("executor received an invalid argv")
        try:
            completed = self._runner(
                argv,
                capture_output=True,
                text=True,
                timeout=self._command_timeout,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ReplayError(f"command failed to execute: {argv[0]!r}") from error
        if completed.returncode != 0:
            raise ReplayError(f"command returned exit code {completed.returncode}: {argv[0]!r}")

    def launch(self, argv: list[str]) -> None:
        # Browser-hosted webapps can all have the same WM class. Snapshot the
        # target workspace so wait_for_window observes the window created by
        # this launch instead of accepting an older matching instance.
        self._addresses_before_launch = self._target_addresses()
        if not argv or not all(isinstance(argument, str) and argument for argument in argv):
            raise ReplayError("executor received an invalid launcher argv")
        try:
            # Applications are expected to outlive this short-lived backend.
            # Waiting with the dispatch timeout would kill a new browser
            # process after five seconds; a separate session also prevents
            # Quickshell from treating it as part of layoutctl's process tree.
            self._launcher(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
                shell=False,
            )
        except (OSError, ValueError) as error:
            raise ReplayError(f"launcher failed to execute: {argv[0]!r}") from error

    def dispatch(self, argv: list[str]) -> None:
        self._run(argv)

    def focus_target(self) -> None:
        self._run(
            [
                "hyprctl",
                "dispatch",
                f'hl.dsp.focus({{ workspace = "{self._target_workspace_id}" }})',
            ]
        )

    def focus_window(self, window_id: str, wm_class: str) -> None:
        del wm_class
        address = self._window_addresses.get(window_id)
        if address is None:
            raise ReplayError(f"window {window_id!r} has no observed address")
        self._run(_focus_address_dispatch(address))

    def wait_for_window(self, window_id: str, wm_class: str, placement: str) -> bool:
        del placement
        deadline = self._clock() + self._window_timeout
        while self._clock() <= deadline:
            try:
                clients = self._reader.read_json("clients")
            except (OSError, CaptureError) as error:
                raise ReplayError("could not observe target windows after launch") from error
            if not isinstance(clients, list):
                raise ReplayError("Hyprland clients response was not an array after launch")
            for client in clients:
                if (
                    isinstance(client, Mapping)
                    and isinstance(client.get("address"), str)
                    and client["address"] not in self._addresses_before_launch
                    and isinstance(client.get("class"), str)
                    and client["class"].casefold() == wm_class.casefold()
                    and isinstance(client.get("workspace"), Mapping)
                    and client["workspace"].get("id") == self._target_workspace_id
                ):
                    self._addresses_before_launch.add(client["address"])
                    self._window_addresses[window_id] = client["address"]
                    return True
            self._sleeper(self._poll_interval)
        return False

    def verify(self, plan: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            clients = self._reader.read_json("clients")
        except (OSError, CaptureError) as error:
            raise ReplayError("could not read target windows during verification") from error
        target = plan["target"]
        if not isinstance(target, Mapping) or not isinstance(target.get("workspace"), Mapping):
            raise ReplayError("plan target is malformed during verification")
        workspace_id = target["workspace"].get("id")
        if workspace_id != self._target_workspace_id or not isinstance(clients, list):
            raise ReplayError("target workspace changed during verification")
        actual = [
            client
            for client in clients
            if isinstance(client, Mapping)
            and isinstance(client.get("workspace"), Mapping)
            and client["workspace"].get("id") == workspace_id
        ]
        expected = [entry for entry in plan.get("entries", []) if entry.get("kind") == "launch"]
        remaining = list(actual)
        matched = 0
        for entry in expected:
            observed_address = self._window_addresses.get(entry.get("windowId"))
            for index, client in enumerate(remaining):
                if (
                    (observed_address is None or client.get("address") == observed_address)
                    and isinstance(client.get("class"), str)
                    and isinstance(entry.get("wmClass"), str)
                    and client["class"].casefold() == entry["wmClass"].casefold()
                ):
                    matched += 1
                    remaining.pop(index)
                    break
        geometry_mismatched = _count_geometry_mismatches(
            plan,
            actual,
            self._window_addresses,
        )
        return {
            "expected": len(expected),
            "matched": matched,
            "unmatched": len(expected) - matched,
            "unexpected": len(remaining),
            "geometryMismatched": geometry_mismatched,
        }


def _expected_tiled_rectangles(plan: Mapping[str, Any]) -> dict[str, tuple[float, float, float, float]]:
    """Rebuild normalized leaf rectangles from the approved split sequence."""
    if plan.get("layoutMode") != "tree":
        return {}
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        return {}
    anchor: Any = None
    splits: list[Any] = []
    for step in steps:
        if not isinstance(step, Mapping):
            return {}
        if step.get("op") == "anchor":
            anchor = step.get("windowId")
        elif step.get("op") == "split":
            splits.append(step)
    return expand_layout(anchor, splits)


def _count_geometry_mismatches(
    plan: Mapping[str, Any],
    clients: list[Any],
    window_addresses: Mapping[str, str],
    *,
    tolerance: float = 0.03,
) -> int:
    """Compare tiled leaf geometry while tolerating Hyprland gaps and borders."""
    expected = _expected_tiled_rectangles(plan)
    if not expected:
        return 0
    actual_by_id: dict[str, tuple[float, float, float, float]] = {}
    by_address = {
        client.get("address"): client
        for client in clients
        if isinstance(client, Mapping) and isinstance(client.get("address"), str)
    }
    for window_id in expected:
        client = by_address.get(window_addresses.get(window_id))
        if not isinstance(client, Mapping) or client.get("floating") is not False:
            return len(expected)
        at, size = client.get("at"), client.get("size")
        if (
            not isinstance(at, list) or len(at) != 2
            or not isinstance(size, list) or len(size) != 2
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in [*at, *size])
        ):
            return len(expected)
        actual_by_id[window_id] = (float(at[0]), float(at[1]), float(size[0]), float(size[1]))
    left = min(rectangle[0] for rectangle in actual_by_id.values())
    top = min(rectangle[1] for rectangle in actual_by_id.values())
    right = max(rectangle[0] + rectangle[2] for rectangle in actual_by_id.values())
    bottom = max(rectangle[1] + rectangle[3] for rectangle in actual_by_id.values())
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return len(expected)
    mismatched = 0
    for window_id, wanted in expected.items():
        x, y, item_width, item_height = actual_by_id[window_id]
        observed = ((x - left) / width, (y - top) / height, item_width / width, item_height / height)
        if any(abs(first - second) > tolerance for first, second in zip(observed, wanted)):
            mismatched += 1
    return mismatched


MIN_HYPRLAND_VERSION = (0, 56, 0)
_VERSION_PATTERN = re.compile(r"(?:Hyprland\s+)?v?(\d+)\.(\d+)\.(\d+)")


def parse_hyprland_version(output: str) -> tuple[int, int, int]:
    """Parse the stable numeric part of ``hyprctl version`` output."""
    if not isinstance(output, str):
        raise PlanError("Hyprland version output must be text")
    match = _VERSION_PATTERN.search(output)
    if match is None:
        raise PlanError("Hyprland returned an unparseable version")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def compatibility_blockers(
    version_output: str,
    *,
    layout: Any,
    lua_bridge_verified: bool,
) -> list[dict[str, str]]:
    """Return explicit restore blockers without probing or changing the desktop.

    Version text alone cannot prove that the exact Lua bridge is installed and
    usable by the current Omarchy shell.  That fact must come from a verified
    fixture/live-session probe, never from a version-based guess.
    """
    blocked: list[dict[str, str]] = []
    try:
        version = parse_hyprland_version(version_output)
    except PlanError as error:
        blocked.append(_entry("unsupported_hyprland", str(error)))
    else:
        if version < MIN_HYPRLAND_VERSION:
            blocked.append(
                _entry(
                    "unsupported_hyprland",
                    "Restore requires Hyprland 0.56.0 or newer for the tested Lua bridge.",
                )
            )
    if not isinstance(layout, Mapping) or layout.get("str") != "dwindle":
        blocked.append(_entry("unsupported_layout", "Restore requires the dwindle layout to be active."))
    if not lua_bridge_verified:
        blocked.append(
            _entry(
                "dispatch_unverified",
                "The exact Lua focus, preselect, placement and ratio dispatches have not been verified.",
            )
        )
    return blocked


def revalidate_approved_plan(
    record: Mapping[str, Any],
    *,
    profile_id: str,
    profile: Mapping[str, Any],
    current_plan: "Plan",
) -> None:
    """Reject an approval whose profile or target conditions changed.

    This check is deliberately pure.  Token consumption belongs immediately
    before a future executor call, after all live read-only checks succeed.
    """
    if not isinstance(record, Mapping):
        raise PlanError("approved plan record must be an object")
    if record.get("profileId") != profile_id:
        raise PlanBlocked([_entry("plan_profile_mismatch", "The approval does not belong to this profile.")])
    if record.get("profileDigest") != profile_digest(profile):
        raise PlanBlocked([_entry("profile_changed", "The profile changed after the restore was approved.")])
    if record.get("target") != current_plan.data.get("target"):
        raise PlanBlocked([_entry("target_changed", "The active workspace or monitor changed after approval.")])


@dataclass(frozen=True)
class Plan:
    """A preview of one restore, with the warnings the user must see first."""

    data: dict[str, Any]
    warnings: list[dict[str, str]] = field(default_factory=list)


def _lua_string(value: str) -> str:
    """Encode a value as a Lua double-quoted string without interpolation."""
    escaped: list[str] = []
    for character in value:
        if character == "\\":
            escaped.append("\\\\")
        elif character == '"':
            escaped.append('\\"')
        elif character == "\n":
            escaped.append("\\n")
        elif character == "\r":
            escaped.append("\\r")
        elif character == "\t":
            escaped.append("\\t")
        elif ord(character) < 32:
            raise ReplayError("window class contains an unsupported control character")
        else:
            escaped.append(character)
    return '"' + "".join(escaped) + '"'


def _focus_address_dispatch(address: str) -> list[str]:
    if not isinstance(address, str) or re.fullmatch(r"0x[0-9a-fA-F]+", address) is None:
        raise ReplayError("Hyprland returned an invalid window address")
    selector = f"address:{address}"
    expression = f"hl.dsp.focus({{ window = {_lua_string(selector)} }})"
    return ["hyprctl", "dispatch", expression]


def _layout_dispatch(message: str) -> list[str]:
    return ["hyprctl", "dispatch", f"hl.dsp.layout({_lua_string(message)})"]


def _window_dispatch(expression: str) -> list[str]:
    return ["hyprctl", "dispatch", expression]


def _number(value: Any, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReplayError(f"{label} must be numeric")
    return format(value, ".17g")


def _exact_split_ratio(direction: str, new_fraction: Any) -> float:
    """Translate a saved side fraction to Hyprland's 0.1–1.9 exact scale.

    With Omarchy's default ``dwindle:split_bias = 0``, Hyprland applies the
    exact value to the top/left side and 1.0 means an even split. Profiles
    instead store the fraction occupied by the newly inserted side.
    """
    if isinstance(new_fraction, bool) or not isinstance(new_fraction, (int, float)):
        raise ReplayError("split ratio must be numeric")
    top_left_fraction = float(new_fraction) if direction in {"left", "up"} else 1.0 - float(new_fraction)
    exact = 2.0 * top_left_fraction
    if not 0.1 <= exact <= 1.9:
        raise ReplayError("split ratio is outside Hyprland's exact range")
    return exact


def build_replay_actions(
    profile: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    launcher_resolver: Callable[[str], list[str]],
) -> list[dict[str, Any]]:
    """Compile a plan to typed argv actions without executing them.

    The resulting dispatches are complete argv arrays. No shell source is
    created, and profile strings are only placed into escaped Lua literals.
    """
    try:
        validate_profile(profile)
    except ProfileError as error:
        raise ReplayError(f"profile cannot be replayed: {error}") from error
    if not isinstance(plan, Mapping) or plan.get("layoutMode") not in {"tree", "order"}:
        raise ReplayError("replay plan has an unsupported layout mode")
    raw_entries = plan.get("entries")
    if not isinstance(raw_entries, list):
        raise ReplayError("replay plan entries must be a list")
    entries = {entry.get("windowId"): entry for entry in raw_entries if isinstance(entry, Mapping)}
    profile_nodes = {
        node["id"]: node
        for node in [*profile["tiled"]["nodes"], *profile["floating"]]
    }
    actions: list[dict[str, Any]] = []

    def launch(window_id: str, placement: str) -> None:
        entry = entries.get(window_id)
        node = profile_nodes.get(window_id)
        if not isinstance(entry, Mapping) or entry.get("kind") != "launch" or not isinstance(node, Mapping):
            raise ReplayError(f"window {window_id!r} has no safe launch action")
        desktop_id = entry.get("desktopId")
        if not isinstance(desktop_id, str):
            raise ReplayError(f"window {window_id!r} has no desktop id")
        try:
            argv = launcher_resolver(desktop_id)
        except Exception as error:
            raise ReplayError(f"could not resolve launcher for {window_id!r}") from error
        if not isinstance(argv, list) or not argv or not all(isinstance(argument, str) and argument for argument in argv):
            raise ReplayError(f"launcher for {window_id!r} did not return a valid argv")
        actions.append(
            {
                "op": "launch",
                "windowId": window_id,
                "placement": placement,
                "wmClass": node["app"]["wmClass"],
                "argv": list(argv),
            }
        )

    for step in plan.get("steps", []):
        if not isinstance(step, Mapping):
            raise ReplayError("replay plan contains a malformed step")
        operation = step.get("op")
        if operation in {"anchor", "append"}:
            window_id = step.get("windowId")
            if not isinstance(window_id, str):
                raise ReplayError("replay launch step has no window id")
            launch(window_id, "tiled")
        elif operation == "split":
            focus = step.get("focus")
            direction = step.get("direction")
            new_window = step.get("new")
            if not isinstance(focus, str) or not isinstance(new_window, str) or direction not in {"left", "right", "up", "down"}:
                raise ReplayError("replay split step is malformed")
            focus_node = profile_nodes.get(focus)
            if not isinstance(focus_node, Mapping):
                raise ReplayError(f"split focus {focus!r} is not in the profile")
            wm_class = focus_node["app"]["wmClass"]
            actions.append({"op": "focus", "windowId": focus, "wmClass": wm_class})
            direction_code = {"left": "l", "right": "r", "up": "u", "down": "d"}[direction]
            actions.append({"op": "dispatch", "argv": _layout_dispatch(f"preselect {direction_code}")})
            launch(new_window, "tiled")
            exact_ratio = _exact_split_ratio(direction, step.get("ratio"))
            actions.append(
                {
                    "op": "dispatch",
                    "argv": _layout_dispatch(f"splitratio {_number(exact_ratio, 'split ratio')} exact"),
                    "windowId": new_window,
                }
            )
        else:
            raise ReplayError(f"replay plan contains unsupported operation {operation!r}")

    for node in profile["floating"]:
        window_id = node["id"]
        launch(window_id, "floating")
        geometry = next(entry.get("geometry") for entry in raw_entries if entry.get("windowId") == window_id)
        if not isinstance(geometry, Mapping):
            raise ReplayError(f"floating window {window_id!r} has no planned geometry")
        actions.extend(
            [
                {"op": "dispatch", "argv": _window_dispatch('hl.dsp.window.float({ action = "set" })'), "windowId": window_id},
                {
                    "op": "dispatch",
                    "argv": _window_dispatch(
                        f"hl.dsp.window.move({{ x = {geometry['x']}, y = {geometry['y']}, relative = false }})"
                    ),
                    "windowId": window_id,
                },
                {
                    "op": "dispatch",
                    "argv": _window_dispatch(
                        f"hl.dsp.window.resize({{ x = {geometry['width']}, y = {geometry['height']}, relative = false }})"
                    ),
                    "windowId": window_id,
                },
            ]
        )
    return actions


def _entry(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _target_geometry(
    geometry: Mapping[str, Any], usable_width: float, usable_height: float
) -> tuple[dict[str, int], bool]:
    """Scale normalized floating geometry onto the target monitor, kept onscreen."""
    width = max(1, min(round(geometry["width"] * usable_width), int(usable_width)))
    height = max(1, min(round(geometry["height"] * usable_height), int(usable_height)))
    raw_x = round(geometry["x"] * usable_width)
    raw_y = round(geometry["y"] * usable_height)
    x = max(0, min(raw_x, int(usable_width) - width))
    y = max(0, min(raw_y, int(usable_height) - height))
    return {"x": x, "y": y, "width": width, "height": height}, (x, y) != (raw_x, raw_y)


def build_plan(
    profile: Mapping[str, Any],
    *,
    active_workspace: Any,
    clients: Any,
    monitors: Any,
    layout: Any,
) -> Plan:
    """Produce the read-only plan for restoring *profile* into the active workspace."""
    try:
        validate_profile(profile)
    except ProfileError as error:
        raise PlanError(f"profile cannot be restored: {error}") from error

    if not isinstance(layout, Mapping) or layout.get("str") != "dwindle":
        raise PlanBlocked([_entry("unsupported_layout", "Restore requires the dwindle layout to be active.")])
    if not isinstance(active_workspace, Mapping):
        raise PlanError("active workspace must be an object")
    workspace_id = active_workspace.get("id")
    workspace_name = active_workspace.get("name")
    if not isinstance(workspace_id, int) or isinstance(workspace_id, bool) or workspace_id <= 0:
        raise PlanError("active workspace id must be a positive integer")
    if not isinstance(workspace_name, str) or not workspace_name or workspace_name.startswith("special:"):
        raise PlanBlocked(
            [_entry("unsupported_workspace", "Restore targets a regular named workspace, not a special one.")]
        )
    if not isinstance(clients, list):
        raise PlanError("Hyprland clients must be an array")
    try:
        left, top, usable_width, usable_height, connector = usable_workspace_rectangle(active_workspace, monitors)
    except CaptureError as error:
        raise PlanBlocked([_entry("monitor_unavailable", f"The target monitor is unusable: {error}")]) from error

    occupants = sum(
        1
        for client in clients
        if isinstance(client, Mapping)
        and isinstance(client.get("workspace"), Mapping)
        and client["workspace"].get("id") == workspace_id
    )

    warnings: list[dict[str, str]] = []
    source_monitor = profile["source"]["monitor"]
    if (
        source_monitor["connector"] != connector
        or source_monitor["usableWidth"] != int(usable_width)
        or source_monitor["usableHeight"] != int(usable_height)
    ):
        warnings.append(
            _entry(
                "monitor_changed",
                f"Saved on {source_monitor['connector']} at {source_monitor['usableWidth']}x"
                f"{source_monitor['usableHeight']}; floating geometry is scaled to {connector} at "
                f"{int(usable_width)}x{int(usable_height)}.",
            )
        )

    entries: list[dict[str, Any]] = []
    launchable_tiled: list[str] = []
    skipped_tiled = False
    clamped = False
    repeated = False
    for placement, nodes in (("tiled", profile["tiled"]["nodes"]), ("floating", profile["floating"])):
        for node in nodes:
            app = node["app"]
            repeated = repeated or app["ordinal"] > 1
            entry: dict[str, Any] = {
                "kind": "launch" if node["launch"]["kind"] == "desktop" else "skip",
                "windowId": node["id"],
                "placement": placement,
                "wmClass": app["wmClass"],
                "desktopId": node["launch"].get("desktopId"),
            }
            if entry["kind"] == "skip":
                entry["reason"] = _entry(
                    "unresolved_launcher",
                    f"No desktop entry was recorded for {app['wmClass']!r}; this window is not launched.",
                )
            elif placement == "floating":
                entry["geometry"], entry_clamped = _target_geometry(node["geometry"], usable_width, usable_height)
                clamped = clamped or entry_clamped
            if placement == "tiled":
                if entry["kind"] == "launch":
                    launchable_tiled.append(node["id"])
                else:
                    skipped_tiled = True
            entries.append(entry)

    if any(entry["kind"] == "skip" for entry in entries):
        warnings.append(
            _entry("unresolved_launcher", "Some windows have no safe launcher and are skipped; nothing else changes.")
        )
    if repeated:
        warnings.append(
            _entry("duplicate_window", "The profile repeats an application; restored instances may differ in content.")
        )
    if clamped:
        warnings.append(
            _entry("geometry_clamped", "A floating window was clamped to stay fully reachable on the target monitor.")
        )

    exact_tree = profile["layoutConfidence"] == "exact" and not skipped_tiled
    if profile["layoutConfidence"] != "exact":
        warnings.append(
            _entry("layout_fallback", "This profile has no inferred split tree; windows are launched in saved order.")
        )
    elif skipped_tiled:
        warnings.append(
            _entry("tree_incomplete", "A tiled window is unresolved, so the split tree cannot be rebuilt exactly.")
        )

    if exact_tree:
        steps: list[dict[str, Any]] = [{"op": "anchor", "windowId": profile["tiled"]["anchor"]}]
        steps.extend(
            {
                "op": "split",
                "focus": split["focus"],
                "direction": split["direction"],
                "new": split["new"],
                "ratio": split["ratio"],
            }
            for split in profile["tiled"]["splits"]
        )
    else:
        steps = [{"op": "append", "windowId": window_id} for window_id in launchable_tiled]

    blocked: list[dict[str, str]] = []
    if occupants:
        blocked.append(
            _entry(
                "workspace_not_empty",
                f"Workspace {workspace_name!r} already contains {occupants} window(s); restore only fills an empty one.",
            )
        )
    if not any(entry["kind"] == "launch" for entry in entries):
        blocked.append(_entry("nothing_to_restore", "No window in this profile has a safe launcher."))
    if blocked:
        raise PlanBlocked(blocked, warnings)

    data = {
        "profileName": profile["name"],
        "layoutMode": "tree" if exact_tree else "order",
        "target": {
            "workspace": {"id": workspace_id, "name": workspace_name},
            "monitor": {
                "connector": connector,
                "usableWidth": int(usable_width),
                "usableHeight": int(usable_height),
            },
            "clientCount": occupants,
        },
        "entries": entries,
        "steps": steps,
        "summary": {
            "launch": sum(entry["kind"] == "launch" for entry in entries),
            "skip": sum(entry["kind"] == "skip" for entry in entries),
            "tiled": len(profile["tiled"]["nodes"]),
            "floating": len(profile["floating"]),
        },
    }
    return Plan(data, warnings)


def plan_profile(
    profile_id: str,
    *,
    reader: HyprctlReader | None = None,
    environment: Mapping[str, str] | None = None,
    profile_loader: Callable[..., dict[str, Any]] = read_profile,
    now: datetime | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Plan one profile against the live desktop and issue its approval token."""
    profile = profile_loader(profile_id, environment)
    source = SystemHyprctlReader() if reader is None else reader
    plan = build_plan(
        profile,
        active_workspace=source.read_json("activeworkspace"),
        clients=source.read_json("clients"),
        monitors=source.read_json("monitors"),
        layout=source.read_json("getoption general:layout"),
    )
    try:
        plan_id, record = issue_plan(profile_id, profile, plan.data["target"], environment=environment, now=now)
    except (OSError, PlanStoreError) as error:
        raise PlanError(f"could not record the approved plan: {error}") from error
    data = {"planId": plan_id, "profileId": profile_id, "expiresAt": record["expiresAt"], **plan.data}
    return data, plan.warnings


def restore_approved_plan(
    plan_id: str,
    *,
    reader: HyprctlReader,
    executor: ReplayExecutor,
    version_output: str,
    lua_bridge_verified: bool,
    launcher_resolver: Callable[[str], list[str]],
    environment: Mapping[str, str] | None = None,
    profile_loader: Callable[..., dict[str, Any]] = read_profile,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Revalidate and execute one approved plan through an injected executor.

    All reads, compatibility checks, and action compilation happen before the
    token is consumed.  Once consumed, failures are reported as partial
    results; no rollback or cleanup action is attempted.
    """
    try:
        record = read_plan(plan_id, environment, now)
    except PlanStoreError as error:
        raise PlanError(f"could not read approved plan: {error}") from error

    profile_id = record.get("profileId")
    if not isinstance(profile_id, str):
        raise PlanError("approved plan has no valid profile id")
    profile = profile_loader(profile_id, environment)
    source = reader
    active_workspace = source.read_json("activeworkspace")
    clients = source.read_json("clients")
    monitors = source.read_json("monitors")
    layout = source.read_json("getoption general:layout")
    blockers = compatibility_blockers(
        version_output,
        layout=layout,
        lua_bridge_verified=lua_bridge_verified,
    )
    if blockers:
        raise PlanBlocked(blockers)
    current_plan = build_plan(
        profile,
        active_workspace=active_workspace,
        clients=clients,
        monitors=monitors,
        layout=layout,
    )
    revalidate_approved_plan(record, profile_id=profile_id, profile=profile, current_plan=current_plan)
    try:
        actions = build_replay_actions(profile, current_plan.data, launcher_resolver=launcher_resolver)
    except ReplayError:
        raise

    # This is the first point at which any state-changing operation is allowed.
    try:
        consume_plan(plan_id, environment, now)
    except PlanStoreError as error:
        raise PlanError(f"could not consume approved plan: {error}") from error

    failures: list[dict[str, str]] = []
    executed = 0
    for action in actions:
        try:
            executor.focus_target()
            if action["op"] == "launch":
                executor.launch(action["argv"])
                if not executor.wait_for_window(action["windowId"], action["wmClass"], action["placement"]):
                    failures.append(
                        _entry(
                            "window_timeout",
                            f"Window {action['windowId']!r} did not appear after launch.",
                        )
                    )
                    break
            elif action["op"] == "focus":
                executor.focus_window(action["windowId"], action["wmClass"])
            elif action["op"] == "dispatch":
                executor.dispatch(action["argv"])
            else:
                failures.append(_entry("unsupported_action", f"Unsupported replay action {action['op']!r}."))
                break
            executed += 1
        except (OSError, ReplayError, RuntimeError) as error:
            failures.append(_entry("action_failed", str(error)))
            break

    verification: Mapping[str, Any] = {}
    if not failures:
        try:
            verification = executor.verify(current_plan.data)
            if (
                verification.get("unmatched", 0)
                or verification.get("unexpected", 0)
                or verification.get("geometryMismatched", 0)
            ):
                failures.append(
                    _entry(
                        "verification_mismatch",
                        "The resulting workspace differs from the approved restore plan.",
                    )
                )
        except (OSError, ReplayError, RuntimeError) as error:
            failures.append(_entry("verification_failed", str(error)))

    return {
        "status": "partial" if failures else "ok",
        "planId": plan_id,
        "profileId": profile_id,
        "executedActions": executed,
        "failures": failures,
        "verification": dict(verification),
    }
