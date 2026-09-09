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
