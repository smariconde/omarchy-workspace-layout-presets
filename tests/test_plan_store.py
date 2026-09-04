from __future__ import annotations

import stat
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from backend.plan_store import (
    PlanExpiredError,
    PlanNotFoundError,
    PlanStoreError,
    consume_plan,
    issue_plan,
    plan_path,
    plans_directory,
    profile_digest,
    purge_expired_plans,
    read_plan,
)


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
TARGET = {"workspace": {"id": 5, "name": "5"}, "clientCount": 0}


class PlanStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = {"XDG_RUNTIME_DIR": self.directory.name, "XDG_DATA_HOME": self.directory.name}

    def issue(self, now: datetime = NOW) -> str:
        return issue_plan("coding", {"schemaVersion": 1}, TARGET, environment=self.environment, now=now)[0]

    def test_plans_live_in_the_runtime_directory_and_fall_back_to_the_data_directory(self) -> None:
        self.assertEqual(
            plans_directory({"XDG_RUNTIME_DIR": "/run/user/1000"}),
            Path("/run/user/1000/omarchy-workspace-layout-presets/plans"),
        )
        self.assertEqual(
            plans_directory({"XDG_DATA_HOME": "/home/user/.local/share"}),
            Path("/home/user/.local/share/omarchy-workspace-layout-presets/plans"),
        )

    def test_an_issued_plan_is_private_readable_once_and_then_gone(self) -> None:
        plan_id = self.issue()
        path = plan_path(plan_id, self.environment)

        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(read_plan(plan_id, self.environment, NOW)["profileId"], "coding")
        self.assertEqual(consume_plan(plan_id, self.environment, NOW)["planId"], plan_id)
        self.assertFalse(path.exists())
        with self.assertRaises(PlanNotFoundError):
            consume_plan(plan_id, self.environment, NOW)

    def test_an_approval_stops_being_valid_once_its_window_closes(self) -> None:
        plan_id = self.issue()

        with self.assertRaises(PlanExpiredError):
            read_plan(plan_id, self.environment, datetime(2026, 9, 4, 12, 5, tzinfo=UTC))

    def test_issuing_a_plan_purges_records_that_can_no_longer_be_honoured(self) -> None:
        stale = self.issue()
        fresh = self.issue(datetime(2026, 9, 4, 12, 10, tzinfo=UTC))

        self.assertFalse(plan_path(stale, self.environment).exists())
        self.assertTrue(plan_path(fresh, self.environment).exists())

    def test_unreadable_records_are_purged_rather_than_trusted(self) -> None:
        directory = plans_directory(self.environment)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        (directory / f"{'a' * 32}.json").write_text("{not json", encoding="utf-8")

        self.assertEqual(purge_expired_plans(self.environment, NOW), 1)

    def test_only_opaque_hexadecimal_ids_can_become_a_path(self) -> None:
        for candidate in ("../../etc/passwd", "coding", "", "A" * 32, "a" * 31):
            with self.subTest(candidate=candidate), self.assertRaises(PlanStoreError):
                plan_path(candidate, self.environment)

    def test_the_digest_follows_profile_content_not_key_order(self) -> None:
        self.assertEqual(
            profile_digest({"name": "Coding", "schemaVersion": 1}),
            profile_digest({"schemaVersion": 1, "name": "Coding"}),
        )
        self.assertNotEqual(profile_digest({"name": "Coding"}), profile_digest({"name": "Writing"}))


if __name__ == "__main__":
    unittest.main()
