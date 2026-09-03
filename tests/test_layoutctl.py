from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from backend import layoutctl


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

    def test_unimplemented_desktop_commands_are_not_silently_accepted(self) -> None:
        for arguments in (["plan", "coding"], ["restore", "plan-v1-example"]):
            with self.subTest(arguments=arguments):
                exit_code, response = layoutctl.execute(arguments)
                self.assertEqual(exit_code, layoutctl.EXIT_UNIMPLEMENTED)
                self.assertEqual(response["status"], "error")
                self.assertEqual(response["error"]["code"], "unimplemented")

    def test_capture_returns_a_profile_and_its_read_only_warnings(self) -> None:
        profile = {"schemaVersion": 1, "name": "Coding", "warnings": [{"code": "layout_fallback", "message": "pending"}]}

        exit_code, response = layoutctl.execute(
            ["capture", "Coding"], capture_workspace=lambda name: ("coding", profile)
        )

        self.assertEqual(exit_code, layoutctl.EXIT_OK)
        self.assertEqual(response["data"], {"profileId": "coding", "profile": profile})
        self.assertEqual(response["warnings"], profile["warnings"])

    def test_profile_management_commands_return_json_data(self) -> None:
        profile = {"schemaVersion": 1, "name": "Coding"}
        with (
            patch.object(layoutctl, "read_profile", return_value=profile),
            patch.object(layoutctl, "rename_profile", return_value=profile),
            patch.object(layoutctl, "duplicate_profile", return_value=profile),
            patch.object(layoutctl, "export_profile", return_value="/tmp/coding.json"),
            patch.object(layoutctl, "import_profile", return_value=("imported", profile)),
        ):
            cases = (
                (["profile", "show", "coding"], {"profileId": "coding", "profile": profile}),
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

    def test_parser_requires_an_explicit_delete_confirmation_flag(self) -> None:
        parsed = layoutctl.parse_arguments(["profile", "delete", "coding", "--confirm"])

        self.assertTrue(parsed.confirm)
