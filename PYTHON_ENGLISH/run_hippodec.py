#!/usr/bin/env python3
"""Entry point for Hispa-Syng v1.0 (maps and analyses)."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from windows_dll_setup import configure_windows_dll_search  # noqa: E402

configure_windows_dll_search()

from hippodec_maps.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
