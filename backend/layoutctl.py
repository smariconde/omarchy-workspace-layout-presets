#!/usr/bin/env python3
"""Typed JSON-only command boundary between QML and the backend.

``layoutctl`` is always invoked as an executable plus an argv array. It emits
exactly one JSON result on stdout and never treats profile content as shell
source. See ``docs/architecture.md`` for the stable version-one contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from typing import Any

try:  # Supports both `python backend/layoutctl.py` and `python -m backend.layoutctl`.
    from .profile_store import (
        ProfileAlreadyExistsError,
        ProfileError,
        delete_profile,
        duplicate_profile,
        export_profile,
        import_profile,
        list_profiles,
        read_profile,
        rename_profile,
    )
except ImportError:  # pragma: no cover - exercised by the installed script entry point.
    from profile_store import (  # type: ignore[no-redef]
        ProfileAlreadyExistsError,
        ProfileError,
        delete_profile,
        duplicate_profile,
        export_profile,
        import_profile,
        list_profiles,
        read_profile,
        rename_profile,
    )


CONTRACT_VERSION = 1
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID_ARGUMENTS = 2
EXIT_UNIMPLEMENTED = 3


class ArgumentParser(argparse.ArgumentParser):
    """An argparse parser that keeps syntax errors inside the JSON contract."""

    def error(self, message: str) -> None:
        raise ArgumentError(message)


class ArgumentError(ValueError):
    """Raised for an invalid argv sequence."""


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    """Parse the public command grammar without running any desktop action."""
    parser = ArgumentParser(prog="layoutctl", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)

    capture = commands.add_parser("capture", add_help=False)
    capture.add_argument("name")

    plan = commands.add_parser("plan", add_help=False)
    plan.add_argument("profile_id")

    restore = commands.add_parser("restore", add_help=False)
    restore.add_argument("approved_plan_id")

    profile = commands.add_parser("profile", add_help=False)
    profile_actions = profile.add_subparsers(dest="profile_action", required=True)
    profile_actions.add_parser("list", add_help=False)
    show = profile_actions.add_parser("show", add_help=False)
    show.add_argument("profile_id")
    rename = profile_actions.add_parser("rename", add_help=False)
    rename.add_argument("profile_id")
    rename.add_argument("name")
    duplicate = profile_actions.add_parser("duplicate", add_help=False)
    duplicate.add_argument("profile_id")
    duplicate.add_argument("new_profile_id")
    delete = profile_actions.add_parser("delete", add_help=False)
    delete.add_argument("profile_id")
    delete.add_argument("--confirm", action="store_true")
    export = profile_actions.add_parser("export", add_help=False)
    export.add_argument("profile_id")
    export.add_argument("destination")
    profile_import = profile_actions.add_parser("import", add_help=False)
    profile_import.add_argument("source")
    try:
        return parser.parse_args(arguments)
    except SystemExit as error:  # ``required=True`` may still exit in argparse internals.
        raise ArgumentError("invalid arguments") from error


def result_ok(data: Mapping[str, Any], warnings: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Build a successful response with the fields every caller can expect."""
    return {
        "contractVersion": CONTRACT_VERSION,
        "status": "ok",
        "data": dict(data),
        "warnings": [] if warnings is None else warnings,
        "blocked": [],
        "error": None,
    }


def result_error(code: str, message: str) -> dict[str, Any]:
    """Build a non-destructive error response."""
    return {
        "contractVersion": CONTRACT_VERSION,
        "status": "error",
        "data": None,
        "warnings": [],
        "blocked": [],
        "error": {"code": code, "message": message},
    }


def result_blocked(
    blocked: list[dict[str, str]],
    data: Mapping[str, Any] | None = None,
    warnings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a read-only refusal response for a failed safety precondition."""
    return {
        "contractVersion": CONTRACT_VERSION,
        "status": "blocked",
        "data": None if data is None else dict(data),
        "warnings": [] if warnings is None else warnings,
        "blocked": blocked,
        "error": None,
    }


def result_unimplemented(command: str) -> dict[str, Any]:
    """Report a declared command whose implementation milestone is pending."""
    return result_error("unimplemented", f"{command} is not available yet")


def execute(
    arguments: list[str], profile_lister: Callable[[], list[str]] = list_profiles
) -> tuple[int, dict[str, Any]]:
    """Execute one command and return its exit code plus JSON-safe response data."""
    try:
        args = parse_arguments(arguments)
    except ArgumentError as error:
        return EXIT_INVALID_ARGUMENTS, result_error("invalid_arguments", str(error))

    if args.command == "profile" and args.profile_action == "list":
        try:
            return EXIT_OK, result_ok({"profiles": profile_lister()})
        except ProfileError as error:
            return EXIT_ERROR, result_error("profile_error", str(error))
        except OSError as error:
            return EXIT_ERROR, result_error("storage_error", str(error))

    if args.command == "profile":
        try:
            if args.profile_action == "show":
                return EXIT_OK, result_ok({"profileId": args.profile_id, "profile": read_profile(args.profile_id)})
            if args.profile_action == "rename":
                profile = rename_profile(args.profile_id, args.name)
                return EXIT_OK, result_ok({"profileId": args.profile_id, "profile": profile})
            if args.profile_action == "duplicate":
                profile = duplicate_profile(args.profile_id, args.new_profile_id)
                return EXIT_OK, result_ok(
                    {"profileId": args.new_profile_id, "sourceProfileId": args.profile_id, "profile": profile}
                )
            if args.profile_action == "delete":
                if not args.confirm:
                    return EXIT_ERROR, result_blocked(
                        [{"code": "confirmation_required", "message": "Deleting a profile requires explicit confirmation."}],
                        data={"profileId": args.profile_id},
                    )
                delete_profile(args.profile_id)
                return EXIT_OK, result_ok({"profileId": args.profile_id})
            if args.profile_action == "export":
                destination = export_profile(args.profile_id, args.destination)
                return EXIT_OK, result_ok({"profileId": args.profile_id, "destination": str(destination)})
            if args.profile_action == "import":
                profile_id, profile = import_profile(args.source)
                return EXIT_OK, result_ok({"profileId": profile_id, "profile": profile})
        except ProfileAlreadyExistsError as error:
            return EXIT_ERROR, result_blocked(
                [{"code": "already_exists", "message": str(error)}],
            )
        except ProfileError as error:
            return EXIT_ERROR, result_error("profile_error", str(error))
        except OSError as error:
            return EXIT_ERROR, result_error("storage_error", str(error))
    return EXIT_UNIMPLEMENTED, result_unimplemented(args.command)


def main(arguments: list[str] | None = None) -> int:
    """Write exactly one compact JSON response and return its documented code."""
    exit_code, response = execute(sys.argv[1:] if arguments is None else arguments)
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
