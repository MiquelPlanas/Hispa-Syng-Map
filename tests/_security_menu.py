"""Exercise menu routing, state changes and cancellation in both languages."""
from __future__ import annotations

import builtins
from contextlib import ExitStack, redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "herramientas"))
import seguridad_proyecto as ui

CASES = 0
CFG = {"project_id": "menu-fixture", "mode": "protected"}


def route(lang, menu, answers, protected, expected):
    global CASES
    calls = []
    names = ["_status", "_enable", "_credential", "_create_open_copy", "_create_protected_copy",
             "_open_protected", "_change_password", "_import_and_remember", "_recovery_credential",
             "_rotate", "_protect_existing", "cleanup_decrypted_temp", "forget_remembered_access"]
    with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
        root = Path(td)
        stack.enter_context(patch.object(ui, "load_security_config", return_value=CFG if protected else None))
        stack.enter_context(patch.object(builtins, "input", side_effect=answers))
        for name in names:
            def handler(*args, _name=name, **kwargs):
                if _name not in {"cleanup_decrypted_temp", "forget_remembered_access"}:
                    assert args == (root, lang)
                calls.append(_name)
                return True
            stack.enter_context(patch.object(ui, name, side_effect=handler))
        output = io.StringIO()
        with redirect_stdout(output):
            menu(root, lang)
        assert calls == expected, (lang, answers, calls, expected)
        assert "Seguridad" not in output.getvalue() if lang == "EN" else "PREPARE A COPY" not in output.getvalue()
        assert not list(root.iterdir()), "Menu routing must not create files on its own"
    CASES += 1


for lang in ("ES", "EN"):
    route(lang, ui._security_menu, ["0"], False, [])
    route(lang, ui._security_menu, ["1", "0"], False, ["_status"])
    route(lang, ui._security_menu, ["2", "0"], False, ["_enable"])
    route(lang, ui._security_menu, ["3", "1", "0", "0"], False, ["_create_protected_copy"])
    route(lang, ui._security_menu, ["3", "2", "0", "0"], False, ["_create_open_copy"])
    route(lang, ui._security_menu, ["3", "3", "0", "0"], False, [])
    route(lang, ui._security_menu, ["4", "0"], False, [])
    route(lang, ui._security_menu, ["2", "0"], True, ["_open_protected"])
    route(lang, ui._security_menu, ["3", "3", "0", "0"], True, ["_credential"])
    route(lang, ui._security_menu, ["3", "1", "0", "0"], True, ["_create_protected_copy"])
    route(lang, ui._security_menu, ["3", "2", "0", "0"], True, ["_create_open_copy"])
    for n,name in enumerate(["_change_password", "_import_and_remember", "_recovery_credential",
                             "_rotate", "_protect_existing", "forget_remembered_access",
                             "cleanup_decrypted_temp"], 1):
        route(lang, ui._security_menu, ["4", str(n), "0", "0"], True, [name])
    route(lang, ui._security_menu, ["bad", "0"], True, [])
    # Protection changes the visible menu without leaving the same project.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = {"protected": False}
        def enable(*args): state["protected"] = True
        with patch.object(ui, "load_security_config", side_effect=lambda *_: CFG if state["protected"] else None), \
             patch.object(ui, "_enable", side_effect=enable) as enabled, \
             patch.object(ui, "_open_protected") as opened, \
             patch.object(builtins, "input", side_effect=["2", "2", "0"]), redirect_stdout(io.StringIO()):
            ui._security_menu(root, lang)
            enabled.assert_called_once_with(root, lang)
            opened.assert_called_once_with(root, lang)
        CASES += 1
    # Cancelling either copy stops before authentication, destination selection or mutation.
    for function in (ui._create_open_copy, ui._create_protected_copy):
        with patch.object(ui, "yn", return_value=False), \
             patch.object(ui, "_authenticate") as auth, \
             patch.object(ui, "choose_folder") as folder, \
             patch.object(ui, "create_open_copy") as opened, \
             patch.object(ui, "create_protected_copy") as protected, redirect_stdout(io.StringIO()):
            function(ROOT, lang)
            auth.assert_not_called(); folder.assert_not_called()
            opened.assert_not_called(); protected.assert_not_called()
        CASES += 1

print(f"PASS: {CASES} menu scenarios across ES and EN; cancellation creates no files.")
