"""Paths and read-only profile enumeration for the initial backend."""

from __future__ import annotations

import os
from pathlib import Path


APP_DIRECTORY = "omarchy-workspace-layout-presets"


def data_home(environment: dict[str, str] | None = None) -> Path:
    """Return the XDG data root without creating or changing any directory."""
    env = os.environ if environment is None else environment
    configured = env.get("XDG_DATA_HOME")
    if configured:
        return Path(configured)
    return Path(env.get("HOME", str(Path.home()))) / ".local" / "share"


def profiles_directory(environment: dict[str, str] | None = None) -> Path:
    return data_home(environment) / APP_DIRECTORY / "profiles"


def list_profiles(environment: dict[str, str] | None = None) -> list[str]:
    """List profile JSON filenames only; malformed files are not interpreted yet."""
    directory = profiles_directory(environment)
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.glob("*.json") if path.is_file())
