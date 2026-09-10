from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta

from backend.capture_store import CaptureExpiredError, issue_capture, read_capture
from tests.test_profile_store import valid_profile


class CaptureStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.environment = {"XDG_RUNTIME_DIR": self.temporary_directory.name}
        self.now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_review_is_private_short_lived_and_contains_only_safe_identity_data(self) -> None:
        capture_id = issue_capture(
            "web",
            valid_profile(),
            {"window-1": ["brave-browser", "Google Docs"]},
            environment=self.environment,
            now=self.now,
        )
        record = read_capture(capture_id, self.environment, self.now)
        serialized = json.dumps(record)

        self.assertEqual(record["allowedAssignments"]["window-1"][1], "Google Docs")
        self.assertNotIn("title", serialized.casefold())
        self.assertNotIn("http", serialized.casefold())
        from backend.capture_store import capture_path
        self.assertEqual(capture_path(capture_id, self.environment).stat().st_mode & 0o777, 0o600)

        with self.assertRaises(CaptureExpiredError):
            read_capture(capture_id, self.environment, self.now + timedelta(seconds=301))
