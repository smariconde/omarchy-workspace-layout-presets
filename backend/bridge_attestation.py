"""Short-lived evidence that the tested Hyprland Lua bridge answered."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Callable, Mapping


APP_DIRECTORY = "omarchy-workspace-layout-presets"
ATTESTATION_NAME = "lua-bridge-attestation.json"
ATTESTATION_TTL_SECONDS = 300
MAX_ATTESTATION_BYTES = 4096
_VERSION_PATTERN = re.compile(r"(?:Hyprland\s+)?v?(\d+)\.(\d+)\.(\d+)")


class AttestationError(ValueError):
    """Raised when bridge evidence cannot be trusted or created."""


def _root(environment: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    runtime = env.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime)
    data_home = env.get("XDG_DATA_HOME")
    if data_home:
        return Path(data_home)
    return Path(env.get("HOME", str(Path.home()))) / ".local" / "share"


def attestation_path(environment: Mapping[str, str] | None = None) -> Path:
    return _root(environment) / APP_DIRECTORY / ATTESTATION_NAME


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AttestationError("attestation timestamp is invalid")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise AttestationError("attestation timestamp is invalid") from error


def _version(output: str) -> tuple[int, int, int]:
    match = _VERSION_PATTERN.search(output)
    if match is None:
        raise AttestationError("Hyprland version is unparseable")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _run(runner: Callable[..., subprocess.CompletedProcess[str]], argv: list[str]) -> str:
    try:
        completed = runner(argv, capture_output=True, text=True, timeout=5, check=False, shell=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AttestationError("Hyprland is unavailable") from error
    if completed.returncode != 0:
        raise AttestationError("Hyprland rejected the attestation query")
    return completed.stdout


def record_attestation(
    workspace_id: int,
    *,
    environment: Mapping[str, str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record probe evidence after the QML dispatch already succeeded."""
    if isinstance(workspace_id, bool) or not isinstance(workspace_id, int) or workspace_id <= 0:
        raise AttestationError("workspace id must be a positive integer")
    version_output = _run(runner, ["hyprctl", "version"])
    try:
        active = json.loads(_run(runner, ["hyprctl", "-j", "activeworkspace"]))
    except json.JSONDecodeError as error:
        raise AttestationError("active workspace returned invalid JSON") from error
    if not isinstance(active, Mapping) or active.get("id") != workspace_id:
        raise AttestationError("active workspace changed during the probe")
    moment = datetime.now(UTC) if now is None else now
    record = {
        "schemaVersion": 1,
        "bridge": "hyprctl-dispatch-lua",
        "checks": ["focus"],
        "hyprlandVersion": version_output.strip(),
        "workspaceId": workspace_id,
        "createdAt": _timestamp(moment),
        "expiresAt": _timestamp(moment + timedelta(seconds=ATTESTATION_TTL_SECONDS)),
    }
    path = attestation_path(environment)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return record


def read_attestation(
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    path = attestation_path(environment)
    try:
        if not path.is_file() or path.stat().st_size > MAX_ATTESTATION_BYTES:
            raise AttestationError("Lua bridge evidence is missing")
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AttestationError("Lua bridge evidence is unreadable") from error
    if not isinstance(record, dict):
        raise AttestationError("Lua bridge evidence is malformed")
    if record.get("schemaVersion") != 1 or record.get("bridge") != "hyprctl-dispatch-lua":
        raise AttestationError("Lua bridge evidence has an unsupported schema")
    if record.get("checks") != ["focus"] or not isinstance(record.get("workspaceId"), int):
        raise AttestationError("Lua bridge evidence is incomplete")
    moment = datetime.now(UTC) if now is None else now
    if _parse_timestamp(record.get("expiresAt")) <= moment:
        raise AttestationError("Lua bridge evidence has expired")
    return record


def validate_attestation(record: Mapping[str, Any], current_version_output: str) -> None:
    """Ensure evidence belongs to the current Hyprland version."""
    if not isinstance(record.get("hyprlandVersion"), str):
        raise AttestationError("Lua bridge evidence has no version")
    if _version(record["hyprlandVersion"]) != _version(current_version_output):
        raise AttestationError("Lua bridge evidence belongs to another Hyprland version")


def main(arguments: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="bridge_attestation")
    parser.add_argument("action", choices=["record"])
    parser.add_argument("workspace_id", type=int)
    args = parser.parse_args(arguments)
    try:
        print(json.dumps(record_attestation(args.workspace_id), ensure_ascii=False, separators=(",", ":")))
    except AttestationError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False, separators=(",", ":")))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
