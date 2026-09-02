from __future__ import annotations

import unittest
from pathlib import Path

from backend.profile_store import profiles_directory


class ProfileStorePathTests(unittest.TestCase):
    def test_uses_xdg_data_home_when_supplied(self) -> None:
        environment = {"XDG_DATA_HOME": "/var/example-data", "HOME": "/home/example"}
        self.assertEqual(
            profiles_directory(environment),
            Path("/var/example-data/omarchy-workspace-layout-presets/profiles"),
        )

    def test_defaults_to_local_share(self) -> None:
        self.assertEqual(
            profiles_directory({"HOME": "/home/example"}),
            Path("/home/example/.local/share/omarchy-workspace-layout-presets/profiles"),
        )
