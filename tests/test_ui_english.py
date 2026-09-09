from pathlib import Path
import unittest


class UserInterfaceLanguageTests(unittest.TestCase):
    def test_plugin_qml_has_no_known_spanish_user_facing_labels(self) -> None:
        root = Path(__file__).resolve().parent.parent
        qml_files = [root / "Panel.qml", root / "BarWidget.qml", *sorted((root / "qml").glob("*.qml"))]
        source = "\n".join(path.read_text(encoding="utf-8") for path in qml_files)
        for forbidden in ("Confirmar", "Guardar", "Borrar", "Eliminar", "Cancelar"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_main_panel_exposes_only_the_three_primary_actions(self) -> None:
        source = (Path(__file__).resolve().parent.parent / "Panel.qml").read_text(encoding="utf-8")
        self.assertIn('text: "Save"', source)
        self.assertIn('text: "Use"', source)
        self.assertIn('text: "Delete"', source)
        for hidden_action in ('View details', 'Preview restore', 'Rename'):
            self.assertNotIn(hidden_action, source)

    def test_restore_preview_is_the_only_restore_confirmation(self) -> None:
        root = Path(__file__).resolve().parent.parent
        panel = (root / "Panel.qml").read_text(encoding="utf-8")
        preview = (root / "qml" / "RestorePreview.qml").read_text(encoding="utf-8")

        self.assertIn('text: "Restore"', preview)
        self.assertIn("onRestoreRequested: root.runAction(", panel)
        self.assertNotIn("Restore here", panel + preview)
        self.assertNotIn("confirmRestore", panel)

    def test_restore_refreshes_bridge_evidence_before_calling_layoutctl(self) -> None:
        root = Path(__file__).resolve().parent.parent
        client = (root / "qml" / "LayoutctlClient.qml").read_text(encoding="utf-8")
        probe = (root / "qml" / "BridgeProbe.qml").read_text(encoding="utf-8")

        self.assertIn("if (!bridgeProbe.start())", client)
        restore_call = 'process.command = [root.backendExecutable, "restore", planId]'
        self.assertIn(restore_call, client)
        self.assertLess(client.index("if (!bridgeProbe.start())"), client.index(restore_call))
        self.assertIn('["hyprctl", "-j", "activeworkspace"]', probe)
        self.assertIn('"hl.dsp.focus({ workspace = " + workspace.id + " })"', probe)
        self.assertIn('"record",', probe)
        self.assertNotIn("sh -c", probe)

    def test_expired_preview_requires_a_fresh_use_action(self) -> None:
        source = (Path(__file__).resolve().parent.parent / "qml" / "RestorePreview.qml").read_text(encoding="utf-8")
        self.assertIn('"Preview expired. Press Use again."', source)
        self.assertIn("!root.expired", source)

    def test_process_results_are_deferred_until_the_client_is_idle(self) -> None:
        source = (Path(__file__).resolve().parent.parent / "qml" / "LayoutctlClient.qml").read_text(encoding="utf-8")
        self.assertIn("Qt.callLater(function()", source)
        self.assertLess(source.index("Qt.callLater(function()"), source.rindex("root.commandFinished(operation"))

    def test_successful_delete_clears_the_removed_selection(self) -> None:
        source = (Path(__file__).resolve().parent.parent / "Panel.qml").read_text(encoding="utf-8")
        delete_success = source.index('if (operation === "profile-delete")')
        refresh = source.index("root.refresh()", delete_success)
        self.assertLess(delete_success, refresh)
        self.assertIn("root.clearSelection()", source[delete_success:refresh])

    def test_each_panel_instance_refreshes_and_reconciles_when_opened(self) -> None:
        source = (Path(__file__).resolve().parent.parent / "Panel.qml").read_text(encoding="utf-8")
        self.assertIn("onOpenedChanged: if (opened) refresh()", source)
        self.assertIn("profiles.indexOf(root.selectedProfile) < 0", source)
        self.assertLess(source.index("function clearSelection()"), source.index("function choose(profileId)"))

    def test_panel_size_is_content_driven_and_scrolls_when_needed(self) -> None:
        source = (Path(__file__).resolve().parent.parent / "Panel.qml").read_text(encoding="utf-8")
        self.assertNotIn("panelHeight", source)
        self.assertIn("fittedContentHeight(contentColumn.implicitHeight", source)
        self.assertIn("contentHeight: contentColumn.implicitHeight", source)
        self.assertIn("interactive: contentHeight > height", source)
