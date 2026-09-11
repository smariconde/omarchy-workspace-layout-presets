import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "tools" / "check_release_payload.py"


def load_guard():
    """Import the guard from its path; ``tools`` is a script directory, not a package."""
    specification = importlib.util.spec_from_file_location("check_release_payload", GUARD)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


guard = load_guard()


class ReleasePayloadTests(unittest.TestCase):
    def test_the_installable_tree_carries_no_assistant_instruction_files(self) -> None:
        offenders = guard.offending_paths(guard.payload_paths())

        self.assertEqual(offenders, [], "these files would ship to every user who installs the plugin")

    def test_the_guard_matches_forbidden_names_at_any_depth(self) -> None:
        paths = [
            "AGENTS.md",
            "CLAUDE.md",
            "docs/vendor/agents.md",
            "backend/.claude/settings.json",
            ".github/copilot-instructions.md",
            ".github/prompts/review.prompt.md",
            ".cursor/rules/safety.mdc",
        ]

        self.assertEqual(guard.offending_paths(paths), paths)

    def test_the_guard_leaves_ordinary_documentation_alone(self) -> None:
        paths = [
            "CONTRIBUTING.md",
            "README.md",
            "docs/repository-guide.md",
            "docs/architecture.md",
            ".github/workflows/tests.yml",
            "backend/layoutctl.py",
        ]

        self.assertEqual(guard.offending_paths(paths), [])

    def test_the_guard_reports_a_failure_exit_code_to_continuous_integration(self) -> None:
        completed = subprocess.run([sys.executable, str(GUARD)], cwd=ROOT, capture_output=True, text=True)

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_the_ignore_file_keeps_the_common_names_from_being_staged(self) -> None:
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")

        for name in ("CLAUDE.md", "AGENTS.md", ".claude/"):
            with self.subTest(name=name):
                self.assertIn(name, ignored)


if __name__ == "__main__":
    unittest.main()
