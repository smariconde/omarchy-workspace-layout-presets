from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
PROBE = REPOSITORY / "qml_process_probe.qml"


def has_wayland_socket() -> bool:
    """Avoid launching Qt when this test process has no usable GUI session."""
    runtime_directory = os.environ.get("XDG_RUNTIME_DIR")
    display = os.environ.get("WAYLAND_DISPLAY")
    socket_path = Path(runtime_directory) / display if runtime_directory and display else None
    if socket_path is None or not socket_path.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.2)
            connection.connect(str(socket_path))
    except OSError:
        return False
    return True


@unittest.skipUnless(shutil.which("qs") and has_wayland_socket(), "requires Quickshell and a live Wayland socket")
class QmlProcessProbeTests(unittest.TestCase):
    def test_profile_list_uses_argv_and_can_enqueue_again_from_its_callback(self) -> None:
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
