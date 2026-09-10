import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_PLUGIN_ID = "io.github.smariconde.workspace-layout-presets"


class ReleaseMetadataTests(unittest.TestCase):
    def test_manifest_uses_permanent_identity_and_semver(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["id"], EXPECTED_PLUGIN_ID)
        self.assertEqual(manifest["license"], "MIT")
        self.assertRegex(manifest["version"], r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

    def test_release_version_is_documented_in_changelog(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn(f"## [{manifest['version']}]", changelog)

    def test_public_docs_contain_install_remove_and_license(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "omarchy plugin add https://github.com/smariconde/omarchy-workspace-layout-presets.git --enable",
            readme,
        )
        self.assertIn(f"omarchy plugin remove {EXPECTED_PLUGIN_ID}", readme)
        self.assertIn("[MIT License](LICENSE)", readme)

    def test_qml_identity_matches_manifest_and_version_is_not_hardcoded(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        bar = (ROOT / "BarWidget.qml").read_text(encoding="utf-8")
        panel = (ROOT / "Panel.qml").read_text(encoding="utf-8")

        self.assertIn(f'moduleName: "{manifest["id"]}"', bar)
        self.assertIn(f'moduleName: "{manifest["id"]}"', panel)
        self.assertIn(f'ipcTarget: "{manifest["id"]}"', panel)
        self.assertIn("target.pluginVersion = root.manifest.version", bar)
        self.assertNotIn(f'property string pluginVersion: "{manifest["version"]}"', panel)

    def test_preview_is_marketplace_compatible(self) -> None:
        allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".avif"}
        previews = [path for path in ROOT.glob("preview.*") if path.suffix.lower() in allowed_suffixes]

        self.assertEqual(len(previews), 1)
        self.assertLess(previews[0].stat().st_size, 50 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
