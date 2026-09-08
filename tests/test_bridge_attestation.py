from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta

from backend.bridge_attestation import (
    AttestationError,
    attestation_path,
    read_attestation,
    record_attestation,
    validate_attestation,
)


class BridgeAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = {"XDG_RUNTIME_DIR": self.directory.name}
        self.now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

    def runner(self, argv: list[str], **kwargs: object):
        del kwargs
        if argv == ["hyprctl", "version"]:
            return _Completed("Hyprland v0.56.2\n")
        if argv == ["hyprctl", "-j", "activeworkspace"]:
            return _Completed('{"id":4,"name":"4"}\n')
        raise AssertionError(argv)

    def test_record_is_private_ephemeral_and_contains_no_replay_instructions(self) -> None:
        record = record_attestation(4, environment=self.environment, runner=self.runner, now=self.now)

        self.assertEqual(record["bridge"], "hyprctl-dispatch-lua")
        self.assertEqual(record["checks"], ["focus"])
        self.assertEqual(record["workspaceId"], 4)
        self.assertEqual(read_attestation(self.environment, self.now + timedelta(seconds=1)), record)
        serialized = json.dumps(record)
        for forbidden in ("argv", "desktopId", "steps", "geometry", "command"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(attestation_path(self.environment).stat().st_mode & 0o777, 0o600)

    def test_expired_or_version_mismatched_evidence_is_rejected(self) -> None:
        record_attestation(4, environment=self.environment, runner=self.runner, now=self.now)

        with self.assertRaises(AttestationError):
            read_attestation(self.environment, self.now + timedelta(seconds=301))
        record = record_attestation(4, environment=self.environment, runner=self.runner, now=self.now)
        with self.assertRaises(AttestationError):
            validate_attestation(record, "Hyprland v0.56.3")


class _Completed:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


if __name__ == "__main__":
    unittest.main()
