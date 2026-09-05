"""Safe, data-only desktop-entry launch resolution.

This module deliberately discovers *identifiers* only.  It never stores an
``Exec`` value, expands desktop-entry field codes, or invokes a launcher.
Those operations belong to the guarded restore milestone.
"""

from __future__ import annotations

import configparser
import os
import re
import shlex
from pathlib import Path
from typing import Iterable, Mapping


class LauncherError(ValueError):
    """Raised when a desktop entry cannot become a safe argv launch."""


_DESKTOP_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHELL_EXECUTABLES = {"ash", "bash", "csh", "dash", "fish", "ksh", "sh", "tcsh", "zsh"}


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


def _desktop_entry_path(desktop_id: str, directories: Iterable[Path]) -> Path | None:
    if not isinstance(desktop_id, str) or not _DESKTOP_ID_PATTERN.fullmatch(desktop_id):
        raise LauncherError("desktop id contains unsupported characters")
    for directory in directories:
        candidate = directory / f"{desktop_id}.desktop"
        try:
            if candidate.is_file() and candidate.parent == directory:
                return candidate
        except OSError:
            continue
    return None


def desktop_entry_command(
    desktop_id: str,
    *,
    directories: Iterable[Path] | None = None,
    environment: Mapping[str, str] | None = None,
) -> list[str]:
    """Resolve a desktop entry to safe argv without invoking a shell.

    V1 launches only entries with no unresolved desktop-entry field codes. A
    literal ``%%`` is reduced to ``%``; file, URL and startup field codes are
    rejected because the profile has no user-approved values for them.
    """
    search_directories = list(application_directories(environment) if directories is None else directories)
    path = _desktop_entry_path(desktop_id, search_directories)
    if path is None:
        raise LauncherError(f"desktop entry {desktop_id!r} was not found")
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        with path.open(encoding="utf-8") as desktop_file:
            parser.read_file(desktop_file)
    except (OSError, UnicodeError, configparser.Error) as error:
        raise LauncherError(f"desktop entry {desktop_id!r} could not be read") from error
    if not parser.has_section("Desktop Entry"):
        raise LauncherError(f"desktop entry {desktop_id!r} has no Desktop Entry section")
    entry = parser["Desktop Entry"]
    if entry.get("Type", "Application") != "Application" or entry.get("Hidden", "false").lower() == "true":
        raise LauncherError(f"desktop entry {desktop_id!r} is not launchable")
    executable = entry.get("Exec", "").strip()
    if not executable:
        raise LauncherError(f"desktop entry {desktop_id!r} has no Exec value")
    try:
        arguments = shlex.split(executable, posix=True)
    except ValueError as error:
        raise LauncherError(f"desktop entry {desktop_id!r} has invalid Exec quoting") from error
    if not arguments:
        raise LauncherError(f"desktop entry {desktop_id!r} has an empty Exec value")
    if Path(arguments[0]).name.casefold() in _SHELL_EXECUTABLES or "-c" in arguments[1:]:
        raise LauncherError(f"desktop entry {desktop_id!r} requires unsafe shell execution")
    normalized: list[str] = []
    for argument in arguments:
        if "%" not in argument:
            normalized.append(argument)
            continue
        literal: list[str] = []
        position = 0
        while position < len(argument):
            if argument[position] != "%":
                literal.append(argument[position])
                position += 1
                continue
            if position + 1 < len(argument) and argument[position + 1] == "%":
                literal.append("%")
                position += 2
                continue
            raise LauncherError(f"desktop entry {desktop_id!r} contains an unsupported field code")
        normalized.append("".join(literal))
    return normalized
