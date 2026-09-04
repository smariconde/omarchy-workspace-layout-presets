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
from typing import Any, Callable, Mapping

from .capture import CaptureError, HyprctlReader, SystemHyprctlReader, usable_workspace_rectangle
from .plan_store import PlanStoreError, issue_plan
from .profile_store import ProfileError, read_profile, validate_profile


class PlanError(ValueError):
    """Raised when a plan cannot be produced from valid, available data."""


class PlanBlocked(Exception):
    """Raised when a safety precondition refuses the restore before any change."""

    def __init__(self, blocked: list[dict[str, str]], warnings: list[dict[str, str]] | None = None) -> None:
        super().__init__("; ".join(entry["message"] for entry in blocked))
        self.blocked = blocked
        self.warnings = [] if warnings is None else warnings


@dataclass(frozen=True)
class Plan:
    """A preview of one restore, with the warnings the user must see first."""

    data: dict[str, Any]
    warnings: list[dict[str, str]] = field(default_factory=list)


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
