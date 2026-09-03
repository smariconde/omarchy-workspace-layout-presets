"""Read-only, fixture-testable Hyprland workspace capture.

No process command line, title, PID, document location, or desktop-entry
``Exec`` value enters the profile.  Capture obtains only the JSON needed for
the V1 schema and writes through ``profile_store`` after complete validation.
"""

from __future__ import annotations

import json
import math
import subprocess
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from .launchers import resolve_desktop_id
from .profile_store import ProfileAlreadyExistsError, ProfileError, create_profile, validate_profile


class CaptureError(ValueError):
    """Raised when Hyprland data cannot safely become a V1 profile."""


class HyprctlReader(Protocol):
    """Small injectable boundary for Hyprland's JSON-only queries."""

    def read_json(self, subject: str) -> Any: ...


class SystemHyprctlReader:
    """Run fixed ``hyprctl -j`` query arrays without invoking a shell."""

    _ALLOWED_SUBJECTS = {"activeworkspace", "clients", "monitors", "getoption general:layout"}

    def __init__(self, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> None:
        self._runner = runner

    def read_json(self, subject: str) -> Any:
        if subject not in self._ALLOWED_SUBJECTS:
            raise CaptureError("unsupported Hyprland query")
        try:
            completed = self._runner(
                ["hyprctl", "-j", *subject.split()],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CaptureError("Hyprland is unavailable") from error
        if completed.returncode != 0:
            raise CaptureError("Hyprland rejected a JSON query")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise CaptureError("Hyprland returned invalid JSON") from error


def profile_id_from_name(name: str) -> str:
    """Derive the opaque storage ID from a display name without unsafe bytes."""
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise CaptureError("profile name must contain 1–100 non-whitespace characters")
    if any(character.isspace() and character not in {" ", "\t"} for character in name):
        raise CaptureError("profile name must not contain control characters")
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    parts = [part for part in normalized.replace("_", "-").split() if part]
    candidate = "-".join("".join(character if character.isalnum() else "-" for character in part) for part in parts)
    candidate = "-".join(part for part in candidate.split("-") if part)[:64].strip("-")
    if not candidate:
        raise CaptureError("profile name must contain at least one letter or digit")
    return candidate


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CaptureError(f"{label} must be an object")
    return value


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CaptureError(f"{label} must be a positive integer")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CaptureError(f"{label} must be a finite number")
    return float(value)


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _active_monitor(active_workspace: Mapping[str, Any], monitors: Sequence[Any]) -> Mapping[str, Any]:
    workspace_id = _positive_integer(active_workspace.get("id"), "active workspace id")
    monitor_name = active_workspace.get("monitor")
    candidates: list[Mapping[str, Any]] = []
    for raw_monitor in monitors:
        monitor = _object(raw_monitor, "monitor")
        current_workspace = monitor.get("activeWorkspace")
        if isinstance(current_workspace, Mapping) and current_workspace.get("id") == workspace_id:
            candidates.append(monitor)
    if monitor_name:
        candidates = [monitor for monitor in candidates if monitor.get("name") == monitor_name]
    if len(candidates) != 1:
        raise CaptureError("could not identify the active workspace monitor")
    return candidates[0]


def _usable_rectangle(monitor: Mapping[str, Any]) -> tuple[float, float, float, float, str]:
    name = monitor.get("name")
    if not isinstance(name, str) or not name:
        raise CaptureError("active monitor name is missing")
    width = _positive_integer(monitor.get("width"), "monitor width")
    height = _positive_integer(monitor.get("height"), "monitor height")
    x = _finite_number(monitor.get("x"), "monitor x")
    y = _finite_number(monitor.get("y"), "monitor y")
    reserved = monitor.get("reserved", [0, 0, 0, 0])
    if not isinstance(reserved, list) or len(reserved) != 4:
        raise CaptureError("monitor reserved margins must contain top, bottom, left, and right")
    top, bottom, left, right = (_finite_number(value, "monitor reserved margin") for value in reserved)
    if min(top, bottom, left, right) < 0:
        raise CaptureError("monitor reserved margins must not be negative")
    usable_width = width - left - right
    usable_height = height - top - bottom
    if usable_width <= 0 or usable_height <= 0:
        raise CaptureError("monitor has no usable workspace rectangle")
    return x + left, y + top, usable_width, usable_height, name


def _normalized_geometry(client: Mapping[str, Any], rectangle: tuple[float, float, float, float, str]) -> tuple[dict[str, float], bool]:
    at = client.get("at")
    size = client.get("size")
    if not isinstance(at, list) or len(at) != 2 or not isinstance(size, list) or len(size) != 2:
        raise CaptureError("client geometry must contain two-element at and size arrays")
    left, top, usable_width, usable_height, _ = rectangle
    raw_x = (_finite_number(at[0], "client at[0]") - left) / usable_width
    raw_y = (_finite_number(at[1], "client at[1]") - top) / usable_height
    raw_width = _finite_number(size[0], "client size[0]") / usable_width
    raw_height = _finite_number(size[1], "client size[1]") / usable_height
    if raw_width <= 0 or raw_height <= 0:
        raise CaptureError("client size must be positive")
    geometry = {
        "x": min(1.0, max(0.0, raw_x)),
        "y": min(1.0, max(0.0, raw_y)),
        "width": min(1.0, raw_width),
        "height": min(1.0, raw_height),
    }
    return geometry, geometry != {"x": raw_x, "y": raw_y, "width": raw_width, "height": raw_height}


def build_profile(
    name: str,
    *,
    active_workspace: Any,
    clients: Any,
    monitors: Any,
    layout: Any,
    desktop_resolver: Callable[[str], str | None] = resolve_desktop_id,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Convert fixed Hyprland JSON responses into one validated fallback profile."""
    active = _object(active_workspace, "active workspace")
    workspace_id = _positive_integer(active.get("id"), "active workspace id")
    workspace_name = active.get("name")
    if not isinstance(workspace_name, str) or not workspace_name or workspace_name.startswith("special:"):
        raise CaptureError("active workspace must be a regular named workspace")
    layout_value = _object(layout, "Hyprland layout option").get("str")
    if layout_value != "dwindle":
        raise CaptureError("the active Hyprland layout is not dwindle")
    if not isinstance(clients, list) or not isinstance(monitors, list):
        raise CaptureError("Hyprland clients and monitors must be arrays")
    monitor = _active_monitor(active, monitors)
    rectangle = _usable_rectangle(monitor)
    selected: list[Mapping[str, Any]] = []
    for raw_client in clients:
        if not isinstance(raw_client, Mapping):
            continue
        client = raw_client
        workspace = client.get("workspace")
        if not isinstance(workspace, Mapping):
            continue
        if workspace.get("id") == workspace_id:
            if not isinstance(client.get("floating"), bool):
                raise CaptureError("client floating state must be a boolean")
            selected.append(client)
    if sum(not client["floating"] for client in selected) > 10 or sum(client["floating"] for client in selected) > 10:
        raise CaptureError("a profile can contain at most 10 tiled and 10 floating windows")
    if any(client.get("fullscreen") not in (0, False, None) for client in selected):
        raise CaptureError("fullscreen workspace capture is not representable by the V1 profile schema")

    ordinals: dict[str, int] = {}
    tiled_nodes: list[dict[str, Any]] = []
    floating_nodes: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for index, client in enumerate(selected, start=1):
        window_class = client.get("class")
        if not isinstance(window_class, str) or not window_class:
            raise CaptureError("client class is missing")
        ordinals[window_class] = ordinals.get(window_class, 0) + 1
        desktop_id = desktop_resolver(window_class)
        app = {"desktopId": desktop_id, "wmClass": window_class, "ordinal": ordinals[window_class]}
        launch = {"kind": "desktop", "desktopId": desktop_id} if desktop_id else {"kind": "unresolved"}
        node = {"id": f"window-{index}", "app": app, "launch": launch}
        if ordinals[window_class] > 1:
            warnings.append(_warning("duplicate_window", f"{window_class!r} appears more than once; identity is best effort."))
        if desktop_id is None:
            warnings.append(_warning("unresolved_launcher", f"No safe desktop entry matches {window_class!r}."))
        if client["floating"]:
            geometry, clamped = _normalized_geometry(client, rectangle)
            node["geometry"] = geometry
            floating_nodes.append(node)
            if clamped:
                warnings.append(_warning("geometry_clamped", f"Floating window {index} exceeded the usable workspace rectangle."))
        else:
            tiled_nodes.append(node)
    if tiled_nodes:
        anchor = tiled_nodes[0]["id"]
        splits = [
            {"focus": tiled_nodes[position - 1]["id"], "direction": "right", "new": node["id"], "ratio": 0.5}
            for position, node in enumerate(tiled_nodes[1:], start=1)
        ]
    else:
        anchor, splits = None, []
    warnings.insert(0, _warning("layout_fallback", "Dwindle tree inference is pending; restore will use launch order only."))
    timestamp = (datetime.now(UTC) if created_at is None else created_at).astimezone(UTC).replace(microsecond=0)
    profile: dict[str, Any] = {
        "schemaVersion": 1,
        "name": name,
        "createdAt": timestamp.isoformat().replace("+00:00", "Z"),
        "source": {
            "hyprlandLayout": "dwindle",
            "workspace": {"name": workspace_name},
            "monitor": {"connector": rectangle[4], "usableWidth": int(rectangle[2]), "usableHeight": int(rectangle[3])},
        },
        "layoutConfidence": "fallback",
        "tiled": {"anchor": anchor, "nodes": tiled_nodes, "splits": splits},
        "floating": floating_nodes,
        "warnings": warnings,
    }
    try:
        validate_profile(profile)
    except ProfileError as error:
        raise CaptureError(f"captured data cannot form a safe profile: {error}") from error
    return profile


def capture_current_workspace(
    name: str,
    *,
    reader: HyprctlReader | None = None,
    desktop_resolver: Callable[[str], str | None] = resolve_desktop_id,
    writer: Callable[[str, Mapping[str, Any]], Path] = create_profile,
    created_at: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    """Capture one active workspace and create a previously unused profile."""
    profile_id = profile_id_from_name(name)
    source = SystemHyprctlReader() if reader is None else reader
    profile = build_profile(
        name,
        active_workspace=source.read_json("activeworkspace"),
        clients=source.read_json("clients"),
        monitors=source.read_json("monitors"),
        layout=source.read_json("getoption general:layout"),
        desktop_resolver=desktop_resolver,
        created_at=created_at,
    )
    try:
        writer(profile_id, profile)
    except ProfileAlreadyExistsError:
        raise
    except (OSError, ProfileError) as error:
        raise CaptureError(f"could not save captured profile: {error}") from error
    return profile_id, profile
