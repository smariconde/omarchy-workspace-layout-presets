from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
PROBE = REPOSITORY / "qml_hyprland_dispatch_probe.qml"


def has_wayland_socket() -> bool:
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
class QmlDispatchProbeTests(unittest.TestCase):
    def test_live_qml_probe_reaches_the_omarchy_lua_dispatch_bridge(self) -> None:
        completed = subprocess.run(
            ["qs", "--no-color", "--path", str(PROBE)],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        output = completed.stdout + completed.stderr
        marker = next(
            (line.partition("HYPRLAND_DISPATCH_PROBE=")[2] for line in output.splitlines() if "HYPRLAND_DISPATCH_PROBE=" in line),
            "",
        )
        self.assertEqual(completed.returncode, 0, output)
        self.assertTrue(marker, output)
        self.assertEqual(json.loads(marker), {"success": True, "reason": "ok"})


if __name__ == "__main__":
    unittest.main()
