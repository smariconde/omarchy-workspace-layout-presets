from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backend import layoutctl


EXECUTABLE = Path(layoutctl.__file__).resolve()


class LayoutctlContractTests(unittest.TestCase):
    def test_profile_list_returns_the_common_success_envelope(self) -> None:
        exit_code, response = layoutctl.execute(
            ["profile", "list"], profile_lister=lambda: ["coding", "writing"]
        )

        self.assertEqual(exit_code, layoutctl.EXIT_OK)
        self.assertEqual(
            response,
            {
                "contractVersion": 1,
                "status": "ok",
                "data": {"profiles": ["coding", "writing"]},
                "warnings": [],
                "blocked": [],
                "error": None,
            },
        )

    def test_restore_returns_the_structured_replay_result(self) -> None:
        replay = {"status": "ok", "planId": "0123456789abcdef0123456789abcdef", "executedActions": 1}
        exit_code, response = layoutctl.execute(
            ["restore", "0123456789abcdef0123456789abcdef"],
            restorer=lambda plan_id: replay,
        )

        self.assertEqual(exit_code, layoutctl.EXIT_OK)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["data"], replay)

    def test_restore_compilation_failure_stays_inside_the_json_contract(self) -> None:
        def fail_restore(plan_id: str) -> dict[str, object]:
            del plan_id
            raise layoutctl.ReplayError("desktop entry contains an unsupported field code")

        exit_code, response = layoutctl.execute(
            ["restore", "0123456789abcdef0123456789abcdef"],
            restorer=fail_restore,
        )

        self.assertEqual(exit_code, layoutctl.EXIT_ERROR)
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"]["code"], "replay_error")

    def test_plan_returns_its_preview_and_warnings_without_changing_anything(self) -> None:
        preview = {"planId": "0123456789abcdef0123456789abcdef", "profileId": "coding", "layoutMode": "tree"}
        warnings = [{"code": "monitor_changed", "message": "scaled"}]

        exit_code, response = layoutctl.execute(["plan", "coding"], planner=lambda profile_id: (preview, warnings))

        self.assertEqual(exit_code, layoutctl.EXIT_OK)
        self.assertEqual(response["data"], preview)
        self.assertEqual(response["warnings"], warnings)
        self.assertEqual(response["blocked"], [])

    def test_a_blocked_plan_reports_its_reasons_and_keeps_the_warnings(self) -> None:
        blocked = [{"code": "workspace_not_empty", "message": "The active workspace has windows."}]
        warnings = [{"code": "layout_fallback", "message": "order only"}]

        def planner(profile_id: str) -> tuple[dict, list]:
            raise layoutctl.PlanBlocked(blocked, warnings)

        exit_code, response = layoutctl.execute(["plan", "coding"], planner=planner)

        self.assertEqual(exit_code, layoutctl.EXIT_ERROR)
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["data"], None)
        self.assertEqual(response["blocked"], blocked)
        self.assertEqual(response["warnings"], warnings)

    def test_plan_failures_stay_inside_the_json_contract(self) -> None:
        cases = (
            (layoutctl.PlanError("bad profile"), "plan_error"),
            (layoutctl.ProfileError("missing"), "profile_error"),
            (layoutctl.CaptureError("Hyprland is unavailable"), "hyprland_error"),
            (OSError("no runtime directory"), "storage_error"),
        )
        for error, code in cases:
            with self.subTest(code=code):
                def planner(profile_id: str, error: Exception = error) -> tuple[dict, list]:
                    raise error

                exit_code, response = layoutctl.execute(["plan", "coding"], planner=planner)

                self.assertEqual(exit_code, layoutctl.EXIT_ERROR)
                self.assertEqual(response["status"], "error")
                self.assertEqual(response["error"]["code"], code)

    def test_capture_returns_a_profile_and_its_read_only_warnings(self) -> None:
        profile = {"schemaVersion": 1, "name": "Coding", "warnings": [{"code": "layout_fallback", "message": "pending"}]}
        data = {"saved": True, "profileId": "coding", "profile": profile, "review": []}

        exit_code, response = layoutctl.execute(
            ["capture", "prepare", "Coding"], capture_preparer=lambda name: (data, profile["warnings"])
        )

        self.assertEqual(exit_code, layoutctl.EXIT_OK)
        self.assertEqual(response["data"], data)
        self.assertEqual(response["warnings"], profile["warnings"])

    def test_capture_commit_passes_only_structured_assignment_data(self) -> None:
        profile = {"schemaVersion": 1, "name": "Web", "warnings": []}
        assignments = '{"window-1":"YouTube"}'

        exit_code, response = layoutctl.execute(
            ["capture", "commit", "0" * 32, assignments],
            capture_committer=lambda capture_id, value: ("web", profile),
        )

        self.assertEqual(exit_code, layoutctl.EXIT_OK)
        self.assertTrue(response["data"]["saved"])
        self.assertEqual(response["data"]["profileId"], "web")

    def test_capture_commit_conflict_is_a_non_destructive_block(self) -> None:
        def conflict(capture_id: str, assignments: str):
            raise layoutctl.ProfileAlreadyExistsError("profile already exists")

        exit_code, response = layoutctl.execute(
            ["capture", "commit", "0" * 32, "{}"], capture_committer=conflict
        )

        self.assertEqual(exit_code, layoutctl.EXIT_ERROR)
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["blocked"][0]["code"], "already_exists")

    def test_profile_management_commands_return_json_data(self) -> None:
        profile = {"schemaVersion": 1, "name": "Coding", "tiled": {"nodes": []}, "floating": []}
        with (
            patch.object(layoutctl, "read_profile", return_value=profile),
            patch.object(layoutctl, "rename_profile", return_value=profile),
            patch.object(layoutctl, "duplicate_profile", return_value=profile),
            patch.object(layoutctl, "export_profile", return_value="/tmp/coding.json"),
            patch.object(layoutctl, "import_profile", return_value=("imported", profile)),
        ):
            cases = (
                (["profile", "show", "coding"], {"profileId": "coding", "profile": profile, "details": []}),
                (["profile", "rename", "coding", "Writing"], {"profileId": "coding", "profile": profile}),
                (
                    ["profile", "duplicate", "coding", "coding-copy"],
                    {"profileId": "coding-copy", "sourceProfileId": "coding", "profile": profile},
                ),
                (["profile", "export", "coding", "/tmp/coding.json"], {"profileId": "coding", "destination": "/tmp/coding.json"}),
                (["profile", "import", "/tmp/imported.json"], {"profileId": "imported", "profile": profile}),
            )
            for arguments, expected_data in cases:
                with self.subTest(arguments=arguments):
                    exit_code, response = layoutctl.execute(arguments)
                    self.assertEqual(exit_code, layoutctl.EXIT_OK)
                    self.assertEqual(response["status"], "ok")
                    self.assertEqual(response["data"], expected_data)

    def test_profile_show_keeps_profile_unchanged_and_adds_safe_derived_details(self) -> None:
        profile = {
            "name": "Coding",
            "tiled": {"nodes": [{"id": "window-1", "app": {"desktopId": "code", "wmClass": "Code", "ordinal": 1}}]},
            "floating": [],
        }
        metadata = {"displayName": "Code", "genericName": "Code Editor", "categories": ["Development"], "kind": "application"}
        with (
            patch.object(layoutctl, "read_profile", return_value=profile),
            patch.object(layoutctl, "desktop_entry_metadata", return_value=metadata),
        ):
            exit_code, response = layoutctl.execute(["profile", "show", "coding"])

        self.assertEqual(exit_code, layoutctl.EXIT_OK)
        self.assertEqual(response["data"]["profile"], profile)
        self.assertEqual(response["data"]["details"][0]["metadata"], metadata)
        self.assertNotIn("Exec", response["data"]["details"][0])

    def test_delete_requires_confirmation_before_the_store_is_called(self) -> None:
        with patch.object(layoutctl, "delete_profile") as delete:
            exit_code, response = layoutctl.execute(["profile", "delete", "coding"])

        self.assertEqual(exit_code, layoutctl.EXIT_ERROR)
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["blocked"][0]["code"], "confirmation_required")
        delete.assert_not_called()

    def test_confirmed_delete_calls_the_store(self) -> None:
        with patch.object(layoutctl, "delete_profile") as delete:
            exit_code, response = layoutctl.execute(["profile", "delete", "coding", "--confirm"])

        self.assertEqual(exit_code, layoutctl.EXIT_OK)
        self.assertEqual(response["data"], {"profileId": "coding"})
        delete.assert_called_once_with("coding")

    def test_profile_conflicts_become_non_destructive_blocked_responses(self) -> None:
        with patch.object(layoutctl, "duplicate_profile", side_effect=layoutctl.ProfileAlreadyExistsError("already exists")):
            exit_code, response = layoutctl.execute(["profile", "duplicate", "coding", "copy"])

        self.assertEqual(exit_code, layoutctl.EXIT_ERROR)
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["blocked"][0]["code"], "already_exists")

    def test_invalid_argv_returns_json_not_argparse_text(self) -> None:
        exit_code, response = layoutctl.execute(["restore"])

        self.assertEqual(exit_code, layoutctl.EXIT_INVALID_ARGUMENTS)
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"]["code"], "invalid_arguments")
        self.assertEqual(response["warnings"], [])
        self.assertEqual(response["blocked"], [])

    def test_help_flags_cannot_escape_the_json_contract(self) -> None:
        exit_code, response = layoutctl.execute(["profile", "--help"])

        self.assertEqual(exit_code, layoutctl.EXIT_INVALID_ARGUMENTS)
        self.assertEqual(response["error"]["code"], "invalid_arguments")

    def test_blocked_response_preserves_the_common_envelope(self) -> None:
        response = layoutctl.result_blocked(
            [{"code": "workspace_not_empty", "message": "The active workspace has windows."}],
            data={"profileId": "coding"},
        )

        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["data"], {"profileId": "coding"})
        self.assertEqual(response["error"], None)
        self.assertEqual(response["blocked"][0]["code"], "workspace_not_empty")

    def test_main_writes_one_json_document(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = layoutctl.main(["nonsense"])

        self.assertEqual(exit_code, layoutctl.EXIT_INVALID_ARGUMENTS)
        self.assertEqual(json.loads(output.getvalue())["status"], "error")
        self.assertEqual(len(output.getvalue().splitlines()), 1)

    def test_parser_fixes_the_public_argument_grammar(self) -> None:
        parsed = layoutctl.parse_arguments(["profile", "duplicate", "coding", "coding-copy"])

        self.assertEqual(parsed.command, "profile")
        self.assertEqual(parsed.profile_action, "duplicate")
        self.assertEqual(parsed.profile_id, "coding")
        self.assertEqual(parsed.new_profile_id, "coding-copy")

        capture = layoutctl.parse_arguments(["capture", "prepare", "Web apps"])
        self.assertEqual(capture.capture_action, "prepare")
        self.assertEqual(capture.name, "Web apps")

    def test_parser_requires_an_explicit_delete_confirmation_flag(self) -> None:
        parsed = layoutctl.parse_arguments(["profile", "delete", "coding", "--confirm"])

        self.assertTrue(parsed.confirm)

    def test_the_executable_qml_invokes_by_path_answers_with_one_json_object(self) -> None:
        """QML runs this file by absolute path, so it must work outside the package."""
        with tempfile.TemporaryDirectory() as data_home:
            completed = subprocess.run(
                [sys.executable, str(EXECUTABLE), "profile", "list"],
                cwd=data_home,
                env={**os.environ, "XDG_DATA_HOME": data_home},
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

        self.assertEqual(completed.returncode, layoutctl.EXIT_OK, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), layoutctl.result_ok({"profiles": []}))
