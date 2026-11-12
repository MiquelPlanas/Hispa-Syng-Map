#!/usr/bin/env python3
"""Prepare the DLL folder bundled in the pyogrio wheel on Windows."""

from __future__ import annotations

import os
import sys
from pathlib import Path


_DLL_DIRECTORY_HANDLES: list[object] = []


def bundled_pyogrio_dll_dir(prefix: str | Path | None = None) -> Path | None:
    """Return the virtual environment's pyogrio.libs folder, if it exists."""

    if os.name != "nt":
        return None
    environment = Path(prefix) if prefix is not None else Path(sys.prefix)
    candidates = (
        environment / "Lib" / "site-packages" / "pyogrio.libs",
        environment / "lib" / "site-packages" / "pyogrio.libs",
    )
    return next((candidate for candidate in candidates if candidate.is_dir()), None)


def configure_windows_dll_search() -> Path | None:
    """Add pyogrio.libs to PATH and the secure Windows DLL search path."""

    dll_dir = bundled_pyogrio_dll_dir()
    if dll_dir is None:
        return None

    dll_text = str(dll_dir.resolve())
    path_parts = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    if dll_text.casefold() not in {item.casefold() for item in path_parts}:
        os.environ["PATH"] = os.pathsep.join((dll_text, *path_parts))

    add_directory = getattr(os, "add_dll_directory", None)
    if add_directory is not None:
        try:
            # Keep the handle for the whole run so Windows does not remove the
            # folder prematurely from the DLL search path.
            _DLL_DIRECTORY_HANDLES.append(add_directory(dll_text))
        except OSError:
            # PATH remains configured and the importer reports the actual error.
            pass
    return dll_dir
