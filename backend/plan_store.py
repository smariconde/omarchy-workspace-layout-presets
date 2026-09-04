"""Short-lived storage for approved restore plans.

A plan record is a *capability*, not a script. It stores the profile it was
issued for, a digest of that profile, and the conditions that were verified to
be safe — never launch arguments, dispatch operations, or geometry. ``restore``
rebuilds the plan from the validated profile and re-checks every condition, so
no instruction can ever reach Hyprland through this file.

Records live in the user's runtime directory, so they disappear when the
session ends, and each one is single-use: it is consumed before any state
change and cannot be replayed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from .atomic_json import AlreadyExistsError, sync_directory, write_json_atomic
from .profile_store import APP_DIRECTORY, data_home

PLAN_TTL_SECONDS = 300
MAX_PLAN_BYTES = 16_384
_PLAN_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


class PlanStoreError(ValueError):
    """Base exception for an unusable or unavailable plan record."""


class PlanNotFoundError(PlanStoreError):
    """Raised when an approved plan does not exist or was already consumed."""


class PlanExpiredError(PlanStoreError):
    """Raised when an approved plan outlived the window it was checked in."""


def plans_directory(environment: Mapping[str, str] | None = None) -> Path:
    """Return the runtime location for plan records without creating it.

    ``XDG_RUNTIME_DIR`` is preferred because approvals must not survive the
    session that granted them; the data directory is only a fallback for
    environments that do not provide one.
    """
    env = os.environ if environment is None else environment
    runtime = env.get("XDG_RUNTIME_DIR")
    root = Path(runtime) if runtime else data_home(env)
    return root / APP_DIRECTORY / "plans"


def validate_plan_id(plan_id: str) -> str:
    """Validate an opaque plan identifier used as a filename stem."""
    if not isinstance(plan_id, str) or not _PLAN_ID_PATTERN.fullmatch(plan_id):
        raise PlanStoreError("plan id must contain 32 lowercase hexadecimal characters")
    return plan_id


def plan_path(plan_id: str, environment: Mapping[str, str] | None = None) -> Path:
    """Return the sole permitted path for *plan_id*."""
    return plans_directory(environment) / f"{validate_plan_id(plan_id)}.json"


def profile_digest(profile: Mapping[str, Any]) -> str:
    """Fingerprint a profile so a plan cannot outlive the data it described."""
    canonical = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PlanStoreError(f"{label} must be an ISO-8601 UTC timestamp")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise PlanStoreError(f"{label} must be an ISO-8601 UTC timestamp") from error


def purge_expired_plans(environment: Mapping[str, str] | None = None, now: datetime | None = None) -> int:
    """Delete every record whose approval window has closed. Returns the count."""
    directory = plans_directory(environment)
    if not directory.is_dir():
        return 0
    moment = datetime.now(UTC) if now is None else now
    removed = 0
    for path in directory.glob("*.json"):
        if not path.is_file() or not _PLAN_ID_PATTERN.fullmatch(path.stem):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            expired = _parse_timestamp(record["expiresAt"], "plan expiresAt") <= moment
        except (OSError, KeyError, TypeError, json.JSONDecodeError, PlanStoreError):
            expired = True  # An unreadable approval can never be honoured anyway.
        if expired:
            path.unlink(missing_ok=True)
            removed += 1
    if removed:
        sync_directory(directory)
    return removed


def issue_plan(
    profile_id: str,
    profile: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
    ttl_seconds: int = PLAN_TTL_SECONDS,
) -> tuple[str, dict[str, Any]]:
    """Record the verified conditions of one plan under a fresh opaque token."""
    moment = datetime.now(UTC) if now is None else now
    purge_expired_plans(environment, moment)
    record = {
        "planId": "",
        "profileId": profile_id,
        "profileDigest": profile_digest(profile),
        "createdAt": _timestamp(moment),
        "expiresAt": _timestamp(moment + timedelta(seconds=ttl_seconds)),
        "target": json.loads(json.dumps(target)),
    }
    for _ in range(4):  # A collision is practically impossible; never overwrite one.
        plan_id = secrets.token_hex(16)
        record["planId"] = plan_id
        try:
            write_json_atomic(plan_path(plan_id, environment), record, create_parent=True, overwrite=False)
        except AlreadyExistsError:
            continue
        return plan_id, record
    raise PlanStoreError("could not allocate a unique plan id")


def read_plan(
    plan_id: str, environment: Mapping[str, str] | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Load one unexpired plan record without consuming it."""
    path = plan_path(plan_id, environment)
    try:
        if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise PlanNotFoundError(f"plan {plan_id!r} does not exist")
        if path.stat().st_size > MAX_PLAN_BYTES:
            raise PlanStoreError(f"plan {plan_id!r} exceeds the {MAX_PLAN_BYTES}-byte limit")
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PlanNotFoundError(f"plan {plan_id!r} does not exist") from error
    except json.JSONDecodeError as error:
        raise PlanStoreError(f"plan {plan_id!r} is not valid JSON") from error
    if not isinstance(record, dict) or record.get("planId") != plan_id:
        raise PlanStoreError(f"plan {plan_id!r} is malformed")
    if _parse_timestamp(record.get("expiresAt"), "plan expiresAt") <= (datetime.now(UTC) if now is None else now):
        raise PlanExpiredError(f"plan {plan_id!r} expired and must be produced again")
    return record


def consume_plan(
    plan_id: str, environment: Mapping[str, str] | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Read one plan and invalidate it, so an approval is never replayed."""
    record = read_plan(plan_id, environment, now)
    path = plan_path(plan_id, environment)
    path.unlink(missing_ok=True)
    sync_directory(path.parent)
    return record
