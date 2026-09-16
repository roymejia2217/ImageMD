"""Expose packaged Tcl modules to Tk before the GUI imports ttkbootstrap."""

from __future__ import annotations

import os
import sys
from pathlib import Path


bundle_root = getattr(sys, "_MEIPASS", None)
if bundle_root:
    module_directory = Path(bundle_root) / "_tcl_data" / "tcl8"
    if module_directory.is_dir():
        existing = os.environ.get("TCLLIBPATH", "")
        module_path = str(module_directory)
    if module_path not in existing.split():
        os.environ["TCLLIBPATH"] = " ".join(filter(None, (existing, module_path)))

        import _tkinter

        original_create = _tkinter.create

        def create_with_msgcat(*args, **kwargs):
            interpreter = original_create(*args, **kwargs)
            interpreter.call("lappend", "auto_path", module_path)
            interpreter.call("::tcl::tm::path", "add", module_path)
            interpreter.call("package", "require", "msgcat")
            return interpreter

        _tkinter.create = create_with_msgcat
