#!/usr/bin/env python3
"""Typed JSON-only command boundary between QML and the backend.

Only ``profile list`` is intentionally available in Milestone 0. Future
subcommands must preserve the argument-array and JSON-only contract.
"""

from __future__ import annotations

import argparse
import json
import sys

from profile_store import list_profiles


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="layoutctl")
    commands = parser.add_subparsers(dest="command", required=True)
    profile = commands.add_parser("profile")
    profile_actions = profile.add_subparsers(dest="profile_action", required=True)
    profile_actions.add_parser("list")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    args = parse_arguments(sys.argv[1:] if arguments is None else arguments)
    if args.command == "profile" and args.profile_action == "list":
        print(json.dumps({"profiles": list_profiles()}, separators=(",", ":")))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
