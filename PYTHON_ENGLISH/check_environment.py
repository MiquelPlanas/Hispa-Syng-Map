#!/usr/bin/env python3
"""Checks the environment without loading scientific libraries at startup."""

from __future__ import annotations

import argparse
import importlib
import os
import platform
import struct
import sys
import tempfile
import traceback
from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path

from windows_dll_setup import (
    bundled_pyogrio_dll_dir,
    configure_windows_dll_search,
)


MODULES = (
    ("numpy", "NumPy"),
    ("pandas", "pandas"),
    ("openpyxl", "openpyxl"),
    ("geopandas", "GeoPandas"),
    ("shapely", "Shapely"),
    ("pyproj", "pyproj"),
    ("pyogrio", "pyogrio"),
    ("yaml", "PyYAML"),
    ("jinja2", "Jinja2"),
    ("scipy", "SciPy"),
    ("matplotlib", "Matplotlib"),
    ("seaborn", "seaborn"),
    ("sklearn", "scikit-learn"),
    ("statsmodels", "statsmodels"),
    ("networkx", "NetworkX"),
    ("docx", "python-docx"),
    ("PIL", "Pillow"),
    ("cryptography", "cryptography"),
)

PINNED_DISTRIBUTIONS = {
    "pandas": ("2.3.3", 3),
    "pyogrio": ("0.11.1", 5),
}


def _windows_policy_error(exc: BaseException) -> bool:
    message = " ".join(
        str(item) for item in (exc, getattr(exc, "__cause__", None)) if item
    ).casefold()
    markers = (
        "directiva de control de aplicaciones",
        "application control policy",
        "blocked this file",
        "bloqueó este archivo",
        "blocked by group policy",
        "software restriction policy",
    )
    return any(marker in message for marker in markers)


def _gdal_dll_error(exc: BaseException) -> bool:
    message = str(exc).casefold()
    return "gdal dll could not be found" in message or "no se encontró gdal" in message


def _check_pyogrio_bundle() -> str | None:
    if os.name != "nt":
        return None
    dll_dir = bundled_pyogrio_dll_dir()
    if dll_dir is None:
        return "The pyogrio.libs folder does not exist inside .venv."
    if not any(dll_dir.glob("gdal*.dll")):
        return f"The folder {dll_dir} does not contain the GDAL DLL."
    return None


def _check_pinned_versions() -> int:
    for distribution, (expected, exit_code) in PINNED_DISTRIBUTIONS.items():
        try:
            installed = distribution_version(distribution)
        except PackageNotFoundError:
            print(f"ERROR: {distribution} is not installed.", file=sys.stderr)
            return exit_code
        if installed != expected:
            print(
                f"ERROR: {distribution} {installed} is not the validated version "
                f"{expected}.",
                file=sys.stderr,
            )
            if distribution == "pyogrio":
                print("Run repair_gdal_windows.bat.", file=sys.stderr)
            else:
                print("Run repair_windows_environment.bat.", file=sys.stderr)
            return exit_code
    return 0


def _check_gis_roundtrip() -> None:
    """Checks that GDAL can write and read back a minimal GeoPackage."""

    geopandas = importlib.import_module("geopandas")
    pyogrio = importlib.import_module("pyogrio")
    geometry = importlib.import_module("shapely.geometry")
    drivers = pyogrio.list_drivers()
    missing = {"ESRI Shapefile", "GPKG"}.difference(drivers)
    if missing:
        raise RuntimeError(
            "GDAL does not provide the required drivers: " + ", ".join(sorted(missing))
        )
    with tempfile.TemporaryDirectory(prefix="hippodec_gdal_") as directory:
        path = Path(directory) / "check.gpkg"
        source = geopandas.GeoDataFrame(
            {"value": [1]}, geometry=[geometry.Point(-8.0, 42.0)], crs=4326
        )
        source.to_file(path, layer="test", driver="GPKG", engine="pyogrio")
        restored = geopandas.read_file(path, layer="test", engine="pyogrio")
        if len(restored) != 1 or int(restored.loc[0, "value"]) != 1:
            raise RuntimeError("The GDAL read-back test did not preserve the data.")


def check_environment(*, quiet: bool = False, full: bool = False) -> int:
    version = sys.version_info[:2]
    if not ((3, 10) <= version < (3, 14)):
        print(
            "ERROR: Hispa-Syng v1.0 requires Python 3.10, 3.11, 3.12, or 3.13; "
            f"current version is {platform.python_version()}.",
            file=sys.stderr,
        )
        return 2
    if struct.calcsize("P") * 8 != 64:
        print("ERROR: Hispa-Syng v1.0 requires Python 64-bit.", file=sys.stderr)
        return 2

    configure_windows_dll_search()
    bundle_error = _check_pyogrio_bundle()
    if bundle_error:
        print(f"pyogrio/GDAL ERROR: {bundle_error}", file=sys.stderr)
        print(
            "Run repair_gdal_windows.bat; do not add GDAL manually to PATH.",
            file=sys.stderr,
        )
        return 5

    pinned_error = _check_pinned_versions()
    if pinned_error:
        return pinned_error

    versions: list[str] = []
    for module_name, display_name in MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # ImportError may also wrap OSError.
            print(f"ERROR loading {display_name}: {exc}", file=sys.stderr)
            if _gdal_dll_error(exc):
                print(
                    "The pyogrio installation cannot load the GDAL bundled in its "
                    "wheel. Run repair_gdal_windows.bat.",
                    file=sys.stderr,
                )
                exit_code = 5
            elif _windows_policy_error(exc):
                print(
                    "Windows blocked a compiled library in the .venv environment. "
                    "Run repair_windows_environment.bat; this is not an Excel error.",
                    file=sys.stderr,
                )
                exit_code = 4
            else:
                exit_code = 3
            if not quiet:
                traceback.print_exc()
            return exit_code
        versions.append(f"{display_name} {getattr(module, '__version__', '?')}")

    if full:
        try:
            _check_gis_roundtrip()
        except Exception as exc:
            print(f"ERROR in the live GDAL test: {exc}", file=sys.stderr)
            if not quiet:
                traceback.print_exc()
            return 5

    if not quiet:
        print(f"Environment OK: Python {platform.python_version()} 64-bit.")
        print("Checked libraries: " + ", ".join(versions))
        if full:
            print("GIS test passed: GeoPackage write and read through GDAL.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="Hides the successful summary")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Adds a live GIS write-and-read test",
    )
    args = parser.parse_args()
    return check_environment(quiet=args.quiet, full=args.full)


if __name__ == "__main__":
    raise SystemExit(main())
