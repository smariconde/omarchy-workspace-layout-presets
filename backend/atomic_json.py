"""Shared primitive for private, all-or-nothing JSON writes.

Saved profiles and issued restore plans must reach disk complete or not at all,
with owner-only permissions. Keeping the primitive here lets each store own its
own paths, schema validation, and error vocabulary while the durability rules
stay in one tested place.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


class AlreadyExistsError(FileExistsError):
    """Raised when a no-overwrite write would replace an existing file."""


def sync_directory(directory: Path) -> None:
    """Persist a rename or unlink where the platform supports directory fsync."""
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


def write_json_atomic(
    path: Path, payload: Mapping[str, Any], *, create_parent: bool, overwrite: bool = True
) -> Path:
    """Write *payload* to *path* through a private temporary sibling file.

    Callers validate the payload first; this function only guarantees that a
    reader never observes a partial file and that no file is created world- or
    group-readable.
    """
    directory = path.parent
    if create_parent:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not directory.is_dir():
        raise NotADirectoryError(f"destination directory {str(directory)!r} does not exist")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".write-", suffix=".tmp", dir=directory)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            descriptor = -1
            target.write(serialized)
            target.flush()
            os.fsync(target.fileno())
        if overwrite:
            os.replace(temporary_path, path)
        else:
            try:
                os.link(temporary_path, path)
            except FileExistsError as error:
                raise AlreadyExistsError(f"destination {str(path)!r} already exists") from error
            temporary_path.unlink()
        sync_directory(directory)
    except BaseException:
        if descriptor != -1:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
        raise
    return path
