"""Validated, atomic storage for workspace layout profiles.

Profiles are data, never executable configuration. This module owns every
profile path and every write, including imports and exports. It deliberately
rejects unknown schema fields so profiles cannot become a side channel for
command lines, documents, URLs, or other session data.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


APP_DIRECTORY = "omarchy-workspace-layout-presets"
SCHEMA_VERSION = 1
MAX_PROFILE_BYTES = 1_048_576
_PROFILE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_NODE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_DESKTOP_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_VALID_CONFIDENCE = {"exact", "fallback"}
_VALID_DIRECTIONS = {"left", "right", "up", "down"}


class ProfileError(ValueError):
    """Base exception for invalid profile input or profile data."""


class ProfileNotFoundError(ProfileError):
    """Raised when a requested profile does not exist."""


class ProfileAlreadyExistsError(ProfileError):
    """Raised when an operation would replace a profile without consent."""


def data_home(environment: Mapping[str, str] | None = None) -> Path:
    """Return the XDG data root without creating or changing any directory."""
    env = os.environ if environment is None else environment
    configured = env.get("XDG_DATA_HOME")
    if configured:
        return Path(configured)
    return Path(env.get("HOME", str(Path.home()))) / ".local" / "share"


def profiles_directory(environment: Mapping[str, str] | None = None) -> Path:
    return data_home(environment) / APP_DIRECTORY / "profiles"


def validate_profile_id(profile_id: str) -> str:
    """Validate an opaque profile identifier used as a filename stem."""
    if not isinstance(profile_id, str) or not _PROFILE_ID_PATTERN.fullmatch(profile_id):
        raise ProfileError("profile id must contain 1–64 lowercase letters, digits, or hyphens")
    return profile_id


def profile_path(profile_id: str, environment: Mapping[str, str] | None = None) -> Path:
    """Return the sole permitted path for *profile_id*."""
    return profiles_directory(environment) / f"{validate_profile_id(profile_id)}.json"


def _require_object(value: Any, label: str, fields: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileError(f"{label} must be an object")
    missing = fields - value.keys()
    unknown = value.keys() - fields
    if missing:
        raise ProfileError(f"{label} is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ProfileError(f"{label} contains unsupported fields: {', '.join(sorted(unknown))}")
    return value


def _require_string(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ProfileError(f"{label} must contain 1–{maximum} characters")
    if any(character.isspace() and character not in {" ", "\t"} for character in value):
        raise ProfileError(f"{label} must not contain control characters")
    return value


def _require_positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProfileError(f"{label} must be a positive integer")
    return value


def _require_number(value: Any, label: str, minimum: float, maximum: float, *, exclusive_minimum: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProfileError(f"{label} must be a finite number")
    if value > maximum or (value <= minimum if exclusive_minimum else value < minimum):
        boundary = "greater than" if exclusive_minimum else "at least"
        raise ProfileError(f"{label} must be {boundary} {minimum} and at most {maximum}")
    return float(value)


def _validate_desktop_id(value: Any, label: str) -> str:
    result = _require_string(value, label, 128)
    if not _DESKTOP_ID_PATTERN.fullmatch(result):
        raise ProfileError(f"{label} contains unsupported characters")
    return result


def _validate_app(app: Any, label: str) -> None:
    value = _require_object(app, label, {"desktopId", "wmClass", "ordinal"})
    desktop_id = value["desktopId"]
    if desktop_id is not None:
        _validate_desktop_id(desktop_id, f"{label}.desktopId")
    _require_string(value["wmClass"], f"{label}.wmClass", 256)
    _require_positive_integer(value["ordinal"], f"{label}.ordinal")


def _validate_launch(launch: Any, label: str) -> None:
    if not isinstance(launch, Mapping) or not isinstance(launch.get("kind"), str):
        raise ProfileError(f"{label} must be an object with a kind")
    kind = launch["kind"]
    if kind == "desktop":
        value = _require_object(launch, label, {"kind", "desktopId"})
        _validate_desktop_id(value["desktopId"], f"{label}.desktopId")
    elif kind == "unresolved":
        _require_object(launch, label, {"kind"})
    else:
        raise ProfileError(f"{label}.kind must be 'desktop' or 'unresolved'")


def _validate_window(node: Any, label: str, *, floating: bool) -> str:
    fields = {"id", "app", "launch", "geometry"} if floating else {"id", "app", "launch"}
    value = _require_object(node, label, fields)
    identifier = _require_string(value["id"], f"{label}.id", 64)
    if not _NODE_ID_PATTERN.fullmatch(identifier):
        raise ProfileError(f"{label}.id contains unsupported characters")
    _validate_app(value["app"], f"{label}.app")
    _validate_launch(value["launch"], f"{label}.launch")
    if floating:
        geometry = _require_object(value["geometry"], f"{label}.geometry", {"x", "y", "width", "height"})
        _require_number(geometry["x"], f"{label}.geometry.x", 0, 1)
        _require_number(geometry["y"], f"{label}.geometry.y", 0, 1)
        _require_number(geometry["width"], f"{label}.geometry.width", 0, 1, exclusive_minimum=True)
        _require_number(geometry["height"], f"{label}.geometry.height", 0, 1, exclusive_minimum=True)
    return identifier


def _validate_warnings(warnings: Any) -> None:
    if not isinstance(warnings, list) or len(warnings) > 50:
        raise ProfileError("warnings must be a list with at most 50 entries")
    for index, warning in enumerate(warnings):
        value = _require_object(warning, f"warnings[{index}]", {"code", "message"})
        _require_string(value["code"], f"warnings[{index}].code", 64)
        _require_string(value["message"], f"warnings[{index}].message", 500)


def validate_profile(profile: Mapping[str, Any]) -> None:
    """Validate the complete V1 data schema before any profile I/O or restore."""
    value = _require_object(
        profile,
        "profile",
        {"schemaVersion", "name", "createdAt", "source", "layoutConfidence", "tiled", "floating", "warnings"},
    )
    if value["schemaVersion"] != SCHEMA_VERSION:
        raise ProfileError(f"unsupported schemaVersion (expected {SCHEMA_VERSION})")
    name = _require_string(value["name"], "profile.name", 100)
    if not name.strip():
        raise ProfileError("profile.name must not be whitespace")
    created_at = _require_string(value["createdAt"], "profile.createdAt", 32)
    if not created_at.endswith("Z"):
        raise ProfileError("profile.createdAt must be an ISO-8601 UTC timestamp")
    try:
        datetime.fromisoformat(created_at[:-1] + "+00:00")
    except ValueError as error:
        raise ProfileError("profile.createdAt must be an ISO-8601 UTC timestamp") from error

    source = _require_object(value["source"], "profile.source", {"hyprlandLayout", "workspace", "monitor"})
    if source["hyprlandLayout"] != "dwindle":
        raise ProfileError("profile.source.hyprlandLayout must be 'dwindle'")
    workspace = _require_object(source["workspace"], "profile.source.workspace", {"name"})
    _require_string(workspace["name"], "profile.source.workspace.name", 128)
    monitor = _require_object(source["monitor"], "profile.source.monitor", {"connector", "usableWidth", "usableHeight"})
    _require_string(monitor["connector"], "profile.source.monitor.connector", 128)
    _require_positive_integer(monitor["usableWidth"], "profile.source.monitor.usableWidth")
    _require_positive_integer(monitor["usableHeight"], "profile.source.monitor.usableHeight")
    if value["layoutConfidence"] not in _VALID_CONFIDENCE:
        raise ProfileError("profile.layoutConfidence must be 'exact' or 'fallback'")

    tiled = _require_object(value["tiled"], "profile.tiled", {"anchor", "nodes", "splits"})
    nodes = tiled["nodes"]
    splits = tiled["splits"]
    if not isinstance(nodes, list) or len(nodes) > 10:
        raise ProfileError("profile.tiled.nodes must contain at most 10 entries")
    if not isinstance(splits, list):
        raise ProfileError("profile.tiled.splits must be a list")
    node_ids = [_validate_window(node, f"profile.tiled.nodes[{index}]", floating=False) for index, node in enumerate(nodes)]
    if len(set(node_ids)) != len(node_ids):
        raise ProfileError("profile.tiled.nodes contains duplicate ids")
    anchor = tiled["anchor"]
    if not nodes:
        if anchor is not None or splits:
            raise ProfileError("an empty tiled layout must have a null anchor and no splits")
    else:
        if not isinstance(anchor, str) or anchor not in node_ids:
            raise ProfileError("profile.tiled.anchor must reference a tiled node")
        if len(splits) != len(nodes) - 1:
            raise ProfileError("profile.tiled.splits must add each non-anchor node exactly once")
        known_ids = {anchor}
        for index, split in enumerate(splits):
            split_value = _require_object(split, f"profile.tiled.splits[{index}]", {"focus", "direction", "new", "ratio"})
            focus = split_value["focus"]
            new = split_value["new"]
            if focus not in known_ids:
                raise ProfileError(f"profile.tiled.splits[{index}].focus must reference an existing node")
            if not isinstance(new, str) or new not in node_ids or new in known_ids:
                raise ProfileError(f"profile.tiled.splits[{index}].new must add one remaining tiled node")
            if split_value["direction"] not in _VALID_DIRECTIONS:
                raise ProfileError(f"profile.tiled.splits[{index}].direction is unsupported")
            ratio = _require_number(split_value["ratio"], f"profile.tiled.splits[{index}].ratio", 0, 1, exclusive_minimum=True)
            if ratio >= 1:
                raise ProfileError(f"profile.tiled.splits[{index}].ratio must be less than 1")
            known_ids.add(new)

    floating = value["floating"]
    if not isinstance(floating, list) or len(floating) > 10:
        raise ProfileError("profile.floating must contain at most 10 entries")
    floating_ids = [_validate_window(node, f"profile.floating[{index}]", floating=True) for index, node in enumerate(floating)]
    if len(set(floating_ids)) != len(floating_ids) or set(node_ids) & set(floating_ids):
        raise ProfileError("window ids must be unique across tiled and floating entries")
    _validate_warnings(value["warnings"])


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        if not path.exists():
            raise ProfileNotFoundError(f"{label} does not exist")
        if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise ProfileError(f"{label} must be a regular file")
        if path.stat().st_size > MAX_PROFILE_BYTES:
            raise ProfileError(f"{label} exceeds the {MAX_PROFILE_BYTES}-byte limit")
        with path.open(encoding="utf-8") as profile_file:
            value = json.load(profile_file)
    except FileNotFoundError as error:
        raise ProfileNotFoundError(f"{label} does not exist") from error
    except json.JSONDecodeError as error:
        raise ProfileError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ProfileError(f"{label} must be a JSON object")
    validate_profile(value)
    return value


def read_profile(profile_id: str, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Load and validate one profile, never treating its contents as commands."""
    return _load_json(profile_path(profile_id, environment), f"profile {profile_id!r}")


def _write_json_atomic(
    path: Path, profile: Mapping[str, Any], *, create_parent: bool, overwrite: bool = True
) -> Path:
    validate_profile(profile)
    directory = path.parent
    if create_parent:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ProfileError(f"destination directory {str(directory)!r} does not exist")
    serialized = json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".profile-", suffix=".tmp", dir=directory)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as profile_file:
            descriptor = -1
            profile_file.write(serialized)
            profile_file.flush()
            os.fsync(profile_file.fileno())
        if overwrite:
            os.replace(temporary_path, path)
        else:
            try:
                os.link(temporary_path, path)
            except FileExistsError as error:
                raise ProfileAlreadyExistsError(f"destination {str(path)!r} already exists") from error
            temporary_path.unlink()
        _sync_directory(directory)
    except BaseException:
        if descriptor != -1:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
        raise
    return path


def write_profile(profile_id: str, profile: Mapping[str, Any], environment: Mapping[str, str] | None = None) -> Path:
    """Validate then atomically replace a profile with owner-only permissions."""
    return _write_json_atomic(profile_path(profile_id, environment), profile, create_parent=True)


def _sync_directory(directory: Path) -> None:
    """Persist the rename where the platform supports directory fsync."""
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def list_profiles(environment: Mapping[str, str] | None = None) -> list[str]:
    """List profile IDs. Invalid filenames and temporary files are excluded."""
    directory = profiles_directory(environment)
    if not directory.is_dir():
        return []
    return sorted(
        path.stem
        for path in directory.glob("*.json")
        if path.is_file() and _PROFILE_ID_PATTERN.fullmatch(path.stem)
    )


def rename_profile(profile_id: str, name: str, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Change a profile display name without changing its stable identifier."""
    profile = read_profile(profile_id, environment)
    updated = dict(profile)
    updated["name"] = name
    write_profile(profile_id, updated, environment)
    return updated


def duplicate_profile(
    profile_id: str, new_profile_id: str, environment: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Create a separate profile copy; existing profiles are never replaced."""
    source = read_profile(profile_id, environment)
    destination = profile_path(new_profile_id, environment)
    if destination.exists():
        raise ProfileAlreadyExistsError(f"profile {new_profile_id!r} already exists")
    _write_json_atomic(destination, source, create_parent=True, overwrite=False)
    return source


def delete_profile(profile_id: str, environment: Mapping[str, str] | None = None) -> None:
    """Delete exactly one validated profile path after the caller confirms it."""
    path = profile_path(profile_id, environment)
    if not path.is_file():
        raise ProfileNotFoundError(f"profile {profile_id!r} does not exist")
    path.unlink()
    _sync_directory(path.parent)


def _transfer_path(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ProfileError(f"{label} must be a non-empty path")
    path = Path(value)
    if not path.is_absolute():
        raise ProfileError(f"{label} must be an absolute path")
    return path


def export_profile(
    profile_id: str, destination: str, environment: Mapping[str, str] | None = None
) -> Path:
    """Copy one validated profile to a new user-selected regular-file path."""
    profile = read_profile(profile_id, environment)
    destination_path = _transfer_path(destination, "export destination")
    if destination_path.exists():
        raise ProfileAlreadyExistsError(f"export destination {destination!r} already exists")
    return _write_json_atomic(destination_path, profile, create_parent=False, overwrite=False)


def import_profile(source: str, environment: Mapping[str, str] | None = None) -> tuple[str, dict[str, Any]]:
    """Import a validated profile under the safe ID derived from its filename."""
    source_path = _transfer_path(source, "import source")
    profile_id = validate_profile_id(source_path.stem)
    profile = _load_json(source_path, f"import source {source!r}")
    destination = profile_path(profile_id, environment)
    if destination.exists():
        raise ProfileAlreadyExistsError(f"profile {profile_id!r} already exists")
    _write_json_atomic(destination, profile, create_parent=True, overwrite=False)
    return profile_id, profile
