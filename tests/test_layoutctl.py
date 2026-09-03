from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

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

    def test_declared_future_commands_are_not_silently_accepted(self) -> None:
        for arguments in (
            ["capture", "Coding"],
            ["plan", "coding"],
            ["restore", "plan-v1-example"],
            ["profile", "show", "coding"],
            ["profile", "rename", "coding", "Writing"],
            ["profile", "duplicate", "coding", "coding-copy"],
            ["profile", "delete", "coding"],
            ["profile", "export", "coding", "/tmp/coding.json"],
            ["profile", "import", "/tmp/coding.json"],
        ):
            with self.subTest(arguments=arguments):
                exit_code, response = layoutctl.execute(arguments)
                self.assertEqual(exit_code, layoutctl.EXIT_UNIMPLEMENTED)
                self.assertEqual(response["status"], "error")
                self.assertEqual(response["error"]["code"], "unimplemented")

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
