"""Safe, data-only desktop-entry launch resolution.

This module deliberately discovers *identifiers* only.  It never stores an
``Exec`` value, expands desktop-entry field codes, or invokes a launcher.
Those operations belong to the guarded restore milestone.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Iterable, Mapping


def application_directories(environment: Mapping[str, str] | None = None) -> list[Path]:
    """Return desktop-entry directories in XDG precedence order."""
    env = os.environ if environment is None else environment
    directories: list[Path] = []
    data_home = env.get("XDG_DATA_HOME")
    if data_home:
        directories.append(Path(data_home) / "applications")
    else:
        directories.append(Path(env.get("HOME", str(Path.home()))) / ".local" / "share" / "applications")
    data_dirs = env.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    directories.extend(Path(directory) / "applications" for directory in data_dirs.split(":") if directory)
    return directories


def _desktop_id(path: Path, directory: Path) -> str | None:
    """Derive an ID only for a simple, non-traversing desktop-file name."""
    try:
        relative = path.relative_to(directory)
    except ValueError:
        return None
    if len(relative.parts) != 1 or path.suffix != ".desktop":
        return None
    candidate = path.stem
    if not candidate or any(character.isspace() for character in candidate):
        return None
    return candidate


def _matches_window_class(path: Path, window_class: str) -> bool:
    """Return whether one regular Application desktop entry matches a class."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        with path.open(encoding="utf-8") as desktop_file:
            parser.read_file(desktop_file)
    except (OSError, UnicodeError, configparser.Error):
        return False
    if not parser.has_section("Desktop Entry"):
        return False
    entry = parser["Desktop Entry"]
    if entry.get("Type", "Application") != "Application" or entry.get("Hidden", "false").lower() == "true":
        return False
    # An entry without Exec cannot be used safely for the later launcher.
    if not entry.get("Exec", "").strip():
        return False
    startup_class = entry.get("StartupWMClass", "")
    return startup_class.casefold() == window_class.casefold()


def resolve_desktop_id(
    window_class: str,
    *,
    directories: Iterable[Path] | None = None,
    environment: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve a window class to one safe desktop-entry ID, or ``None``.

    ``StartupWMClass`` is the reliable explicit match.  If it is absent, an
    exact case-insensitive filename match is accepted as a conservative
    fallback.  XDG directory precedence and lexicographic traversal make a
    result deterministic.
    """
    if not isinstance(window_class, str) or not window_class or len(window_class) > 256:
        return None
    search_directories = list(application_directories(environment) if directories is None else directories)
    expected_filename = window_class.casefold()
    for directory in search_directories:
        try:
            paths = sorted(directory.glob("*.desktop"))
        except OSError:
            continue
        for path in paths:
            desktop_id = _desktop_id(path, directory)
            if desktop_id is None:
                continue
            if _matches_window_class(path, window_class) or desktop_id.casefold() == expected_filename:
                return desktop_id
    return None
