#!/usr/bin/env python3
"""Refuse to ship coding-assistant instruction files inside the plugin payload.

Installing this plugin clones the repository into the Omarchy plugin directory,
so the tracked tree *is* the installed tree. A file that configures a coding
assistant is harmless in a library checkout and is not harmless here: once
installed it becomes an instruction channel inside someone else's environment,
which is why the Omarchy Plugin Marketplace rejects payloads that carry one.

The check is recursive and matches on names, not locations: a forbidden file
is a blocker at the repository root and equally at ``docs/vendor/AGENTS.md``.
Untracked local copies are deliberately ignored — keeping assistant
configuration on your own machine is fine, committing it is not.

Run it directly, or let ``tests/test_release_payload.py`` run it with the
suite::

    python tools/check_release_payload.py

Exit status is 0 when the payload is clean and 1 when it is not.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent.parent

#: File names that carry instructions to a coding assistant, lowercased. Names
#: are matched on their own, so nesting them in a subdirectory does not help.
FORBIDDEN_FILE_NAMES = frozenset(
    {
        ".aider.conf.yml",
        ".aiderrules",
        ".clinerules",
        ".codeiumrules",
        ".continuerules",
        ".cursorrules",
        ".goosehints",
        ".mcp.json",
        ".windsurfrules",
        "agent.md",
        "agents.md",
        "claude.md",
        "codex.md",
        "copilot-instructions.md",
        "gemini.md",
        "llm.md",
        "opencode.md",
        "qwen.md",
    }
)

#: Directory names whose whole subtree is assistant configuration, lowercased.
FORBIDDEN_DIRECTORY_NAMES = frozenset(
    {
        ".aider",
        ".claude",
        ".cline",
        ".codeium",
        ".continue",
        ".cursor",
        ".gemini",
        ".goose",
        ".junie",
        ".opencode",
        ".roo",
        ".windsurf",
    }
)

#: Exact tracked paths that are assistant configuration only in this position;
#: the surrounding directory has legitimate uses.
FORBIDDEN_PATH_PREFIXES = (
    ".github/chatmodes/",
    ".github/instructions/",
    ".github/prompts/",
)


def payload_paths() -> list[str]:
    """Return every path that ships to an installed plugin, as POSIX strings.

    The installed tree is a clone, so the tracked file list is the payload.
    When git is unavailable — an exported tarball, for instance — fall back to
    walking the working tree, which in that situation holds the same files.
    """
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return sorted(
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(ROOT).parts
        )
    return sorted(entry for entry in listing.stdout.split("\0") if entry)


def offending_paths(paths: list[str]) -> list[str]:
    """Return the subset of ``paths`` that may not ship inside the plugin."""
    offenders = []
    for path in paths:
        parts = PurePosixPath(path).parts
        if not parts:
            continue
        directories = {part.lower() for part in parts[:-1]}
        if (
            parts[-1].lower() in FORBIDDEN_FILE_NAMES
            or directories & FORBIDDEN_DIRECTORY_NAMES
            or path.startswith(FORBIDDEN_PATH_PREFIXES)
        ):
            offenders.append(path)
    return offenders


def main() -> int:
    offenders = offending_paths(payload_paths())
    if not offenders:
        return 0
    print("Coding-assistant instruction files must not be committed:", file=sys.stderr)
    for path in offenders:
        print(f"  {path}", file=sys.stderr)
    print(
        "\nInstalling the plugin clones this repository, so these files would\n"
        "ship to end users. Keep them untracked, or move the contributor\n"
        "documentation into a neutrally named file such as docs/repository-guide.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
