from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
PROBE = REPOSITORY / "qml_process_probe.qml"


@unittest.skipUnless(shutil.which("qs"), "requires Quickshell's qs executable")
class QmlProcessProbeTests(unittest.TestCase):
    def test_profile_list_uses_argv_and_returns_json_to_qml(self) -> None:
        with tempfile.TemporaryDirectory() as data_home:
            environment = os.environ.copy()
            environment["XDG_DATA_HOME"] = data_home
            completed = subprocess.run(
                ["qs", "--no-color", "--path", str(PROBE)],
                cwd=REPOSITORY,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        marker = next(
            (
                line.partition("LAYOUTCTL_PROCESS_PROBE=")[2]
                for line in (completed.stdout + completed.stderr).splitlines()
                if "LAYOUTCTL_PROCESS_PROBE=" in line
            ),
            "",
        )
        self.assertTrue(marker, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(marker), {"success": True, "reason": "ok"})
