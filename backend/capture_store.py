"""Private, short-lived storage for capture reviews.

Drafts contain only profile-safe data and the desktop IDs allowed for each
ambiguous node. Window titles, addresses, URLs and launcher commands are never
written here.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from .atomic_json import AlreadyExistsError, sync_directory, write_json_atomic
from .launchers import valid_desktop_id
from .profile_store import APP_DIRECTORY, data_home, validate_profile, validate_profile_id

CAPTURE_TTL_SECONDS = 300
MAX_CAPTURE_BYTES = 1_048_576
_CAPTURE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


class CaptureStoreError(ValueError):
    pass


class CaptureNotFoundError(CaptureStoreError):
    pass


class CaptureExpiredError(CaptureStoreError):
    pass


def captures_directory(environment: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    root = Path(env["XDG_RUNTIME_DIR"]) if env.get("XDG_RUNTIME_DIR") else data_home(env)
    return root / APP_DIRECTORY / "captures"


def validate_capture_id(capture_id: str) -> str:
    if not isinstance(capture_id, str) or not _CAPTURE_ID_PATTERN.fullmatch(capture_id):
        raise CaptureStoreError("capture id must contain 32 lowercase hexadecimal characters")
    return capture_id


def capture_path(capture_id: str, environment: Mapping[str, str] | None = None) -> Path:
    return captures_directory(environment) / f"{validate_capture_id(capture_id)}.json"


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CaptureStoreError("capture expiry must be an ISO-8601 UTC timestamp")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise CaptureStoreError("capture expiry must be an ISO-8601 UTC timestamp") from error


def issue_capture(
    profile_id: str,
    profile: Mapping[str, Any],
    allowed_assignments: Mapping[str, list[str]],
    *,
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> str:
    moment = datetime.now(UTC) if now is None else now
    validate_profile_id(profile_id)
    validate_profile(profile)
    if not allowed_assignments or len(allowed_assignments) > 20:
        raise CaptureStoreError("capture review must contain 1–20 ambiguous windows")
    normalized = _validate_allowed_assignments(allowed_assignments)

    record = {
        "captureId": "",
        "profileId": profile_id,
        "profile": json.loads(json.dumps(profile)),
        "allowedAssignments": normalized,
        "expiresAt": _timestamp(moment + timedelta(seconds=CAPTURE_TTL_SECONDS)),
    }
    for _ in range(4):
        capture_id = secrets.token_hex(16)
        record["captureId"] = capture_id
        try:
            write_json_atomic(capture_path(capture_id, environment), record, create_parent=True, overwrite=False)
        except AlreadyExistsError:
            continue
        return capture_id
    raise CaptureStoreError("could not allocate a unique capture id")


def _validate_allowed_assignments(allowed_assignments: object) -> dict[str, list[str]]:
    if not isinstance(allowed_assignments, Mapping) or not allowed_assignments or len(allowed_assignments) > 20:
        raise CaptureStoreError("capture review must contain 1–20 ambiguous windows")
    normalized: dict[str, list[str]] = {}
    for node_id, desktop_ids in allowed_assignments.items():
        if not isinstance(node_id, str) or not node_id.startswith("window-"):
            raise CaptureStoreError("capture review contains an invalid window id")
        if not isinstance(desktop_ids, list) or not desktop_ids:
            raise CaptureStoreError("capture review contains no launcher choices")
        if not all(valid_desktop_id(desktop_id) for desktop_id in desktop_ids):
            raise CaptureStoreError("capture review contains an invalid desktop id")
        normalized[node_id] = list(dict.fromkeys(desktop_ids))
    return normalized


def read_capture(
    capture_id: str,
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    path = capture_path(capture_id, environment)
    try:
        if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise CaptureNotFoundError(f"capture {capture_id!r} does not exist")
        if path.stat().st_size > MAX_CAPTURE_BYTES:
            raise CaptureStoreError("capture review exceeds its size limit")
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CaptureNotFoundError(f"capture {capture_id!r} does not exist") from error
    except json.JSONDecodeError as error:
        raise CaptureStoreError("capture review is not valid JSON") from error
    expected_fields = {"captureId", "profileId", "profile", "allowedAssignments", "expiresAt"}
    if not isinstance(record, dict) or set(record) != expected_fields or record.get("captureId") != capture_id:
        raise CaptureStoreError("capture review is malformed")
    if _parse_timestamp(record.get("expiresAt")) <= (datetime.now(UTC) if now is None else now):
        raise CaptureExpiredError("capture review expired; scan the workspace again")
    validate_profile_id(record.get("profileId"))
    validate_profile(record.get("profile"))
    record["allowedAssignments"] = _validate_allowed_assignments(record.get("allowedAssignments"))
    return record


def consume_capture(capture_id: str, environment: Mapping[str, str] | None = None) -> None:
    path = capture_path(capture_id, environment)
    path.unlink(missing_ok=True)
    sync_directory(path.parent)
