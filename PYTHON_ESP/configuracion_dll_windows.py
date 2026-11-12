#!/usr/bin/env python3
"""Prepara en Windows la carpeta de DLL incluida en la rueda de pyogrio."""

from __future__ import annotations

import os
import sys
from pathlib import Path


_DLL_DIRECTORY_HANDLES: list[object] = []


def bundled_pyogrio_dll_dir(prefix: str | Path | None = None) -> Path | None:
    """Devuelve la carpeta pyogrio.libs del entorno virtual, si existe."""

    if os.name != "nt":
        return None
    environment = Path(prefix) if prefix is not None else Path(sys.prefix)
    candidates = (
        environment / "Lib" / "site-packages" / "pyogrio.libs",
        environment / "lib" / "site-packages" / "pyogrio.libs",
    )
    return next((candidate for candidate in candidates if candidate.is_dir()), None)


def configure_windows_dll_search() -> Path | None:
    """Añade pyogrio.libs a PATH y a la búsqueda segura de DLL de Windows."""

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
            # Conserva el identificador durante toda la ejecución para que
            # Windows no retire antes de tiempo la carpeta de búsqueda de DLL.
            _DLL_DIRECTORY_HANDLES.append(add_directory(dll_text))
        except OSError:
            # PATH sigue configurado y el importador comunica el error real.
            pass
    return dll_dir
