import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI_SOURCE = ROOT / "src" / "gui.py"


class GuiImportContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GUI_SOURCE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(GUI_SOURCE))

    def test_gui_has_no_wildcard_imports(self):
        wildcard_imports = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
            and any(alias.name == "*" for alias in node.names)
        ]
        self.assertFalse(
            wildcard_imports,
            "gui.py must not use wildcard imports",
        )

    def test_gui_does_not_keep_unused_tkinter_alias(self):
        tkinter_aliases = {
            alias.asname or alias.name.split(".")[-1]
            for node in self.tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name == "tkinter"
        }
        used_names = {
            node.id
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        self.assertNotIn(
            "tk",
            tkinter_aliases - used_names,
            "gui.py must not retain an unused `import tkinter as tk`",
        )

    def test_gui_imports_used_ttkbootstrap_constants_explicitly(self):
        expected = {
            "BOTH",
            "DISABLED",
            "END",
            "HORIZONTAL",
            "INFO",
            "LEFT",
            "NORMAL",
            "PRIMARY",
            "RIGHT",
            "SUCCESS",
            "VERTICAL",
            "X",
            "Y",
        }
        constant_imports = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "ttkbootstrap.constants"
        ]
        self.assertEqual(len(constant_imports), 1)
        imported_names = {alias.name for alias in constant_imports[0].names}
        self.assertEqual(imported_names, expected)

    def test_gui_imports_configuration_without_wildcard(self):
        config_imports = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
            and node.level == 1
            and node.module == "config"
        ]
        self.assertEqual(len(config_imports), 1)
        self.assertNotIn(
            "*",
            {alias.name for alias in config_imports[0].names},
        )


if __name__ == "__main__":
    unittest.main()
