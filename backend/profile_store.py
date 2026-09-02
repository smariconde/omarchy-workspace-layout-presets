"""Validated, atomic storage for workspace layout profiles.

Profiles are data, never executable configuration. This module keeps the
filesystem boundary deliberately small so callers cannot select arbitrary
paths, and a partially written profile can never replace a valid one.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping


APP_DIRECTORY = "omarchy-workspace-layout-presets"
SCHEMA_VERSION = 1
_PROFILE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_VALID_CONFIDENCE = {"exact", "fallback"}


class ProfileError(ValueError):
    """Base exception for invalid profile input or profile data."""


class ProfileNotFoundError(ProfileError):
    """Raised when a requested profile does not exist."""


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


def _require(value: Mapping[str, Any], key: str, expected: type) -> Any:
    result = value.get(key)
    if not isinstance(result, expected):
        raise ProfileError(f"profile field {key!r} must be a {expected.__name__}")
    return result


def validate_profile(profile: Mapping[str, Any]) -> None:
    """Check structural safety invariants shared by capture and import."""
    if not isinstance(profile, Mapping):
        raise ProfileError("profile must be a JSON object")
    if profile.get("schemaVersion") != SCHEMA_VERSION:
        raise ProfileError(f"unsupported schemaVersion (expected {SCHEMA_VERSION})")

    name = _require(profile, "name", str)
    if not name.strip() or len(name) > 100:
        raise ProfileError("profile name must contain 1–100 non-whitespace characters")
    _require(profile, "createdAt", str)
    source = _require(profile, "source", dict)
    _require(source, "hyprlandLayout", str)
    workspace = _require(source, "workspace", dict)
    _require(workspace, "name", str)
    monitor = _require(source, "monitor", dict)
    _require(monitor, "connector", str)
    for key in ("usableWidth", "usableHeight"):
        dimension = _require(monitor, key, int)
        if isinstance(dimension, bool) or dimension <= 0:
            raise ProfileError(f"monitor field {key!r} must be a positive integer")
    if profile.get("layoutConfidence") not in _VALID_CONFIDENCE:
        raise ProfileError("layoutConfidence must be 'exact' or 'fallback'")
    tiled = _require(profile, "tiled", dict)
    _require(tiled, "nodes", list)
    _require(tiled, "splits", list)
    if tiled.get("anchor") is not None and not isinstance(tiled["anchor"], str):
        raise ProfileError("tiled anchor must be a string or null")
    _require(profile, "floating", list)
    _require(profile, "warnings", list)


def read_profile(profile_id: str, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Load and validate one profile, never treating its contents as commands."""
    path = profile_path(profile_id, environment)
    try:
        with path.open(encoding="utf-8") as profile_file:
            profile = json.load(profile_file)
    except FileNotFoundError as error:
        raise ProfileNotFoundError(f"profile {profile_id!r} does not exist") from error
    except json.JSONDecodeError as error:
        raise ProfileError(f"profile {profile_id!r} is not valid JSON") from error
    validate_profile(profile)
    return profile


def write_profile(
    profile_id: str, profile: Mapping[str, Any], environment: Mapping[str, str] | None = None
) -> Path:
    """Validate then atomically replace a profile with owner-only permissions."""
    validate_profile_id(profile_id)
    validate_profile(profile)
    directory = profiles_directory(environment)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = profile_path(profile_id, environment)
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
        os.replace(temporary_path, path)
        _sync_directory(directory)
    except BaseException:
        if descriptor != -1:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
        raise
    return path


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
