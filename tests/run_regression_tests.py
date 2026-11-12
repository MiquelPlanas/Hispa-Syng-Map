from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
import argparse
import hashlib
import importlib.metadata
import importlib
import json
import platform
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = [ROOT / "PYTHON_ESP", ROOT / "PYTHON_ENGLISH"]
RECORDS = []
REPORT_DIR = None


def recorded_run(command, env):
    started = time.perf_counter()
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    label = Path(command[1]).stem + ("_" + Path(command[2]).name if len(command) > 2 else "")
    output = result.stdout + result.stderr
    if REPORT_DIR:
        (REPORT_DIR / (label + ".log")).write_text(output, encoding="utf-8")
    print(output, end="")
    RECORDS.append({"name": label, "command": [str(p).replace(str(ROOT), "<project>") for p in command],
                    "returncode": result.returncode, "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "status": "PASS" if result.returncode == 0 else "FAIL",
                    "log": label + ".log"})
    result.check_returncode()


def check_release_structure() -> None:
    problems: list[str] = []
    caches = list(ROOT.rglob("__pycache__")) + list(ROOT.rglob("*.pyc"))
    if caches:
        problems.append(f"Compiled Python artifacts present: {len(caches)}")
    build_artifacts = [
        path for path in ROOT.rglob("*")
        if path.is_dir() and (path.name in {"build", "dist"} or path.name.endswith(".egg-info"))
    ]
    if build_artifacts:
        problems.append(f"Build/package artifacts present: {len(build_artifacts)}")

    for edition in EDITIONS:
        pyproject = edition / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        patterns = data.get("tool", {}).get("setuptools", {}).get("package-data", {}).get("hippodec_maps", [])
        if "templates/*.js" not in patterns:
            problems.append(f"{edition.name}: templates/*.js missing from package-data")
        common_js = edition / "src" / "hippodec_maps" / "templates" / "_common.js"
        if not common_js.is_file():
            problems.append(f"{edition.name}: _common.js missing")

        # Syntax check without writing .pyc files.
        for path in edition.rglob("*.py"):
            try:
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            except Exception as exc:
                problems.append(f"Syntax error in {path.relative_to(ROOT)}: {exc}")

        source = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in (edition / "src" / "hippodec_maps").glob("*.py")
        )
        if re.search(r"\.notna\(\)\s*&\s*~[^\n]*\.is_empty", source):
            problems.append(f"{edition.name}: obsolete GeoSeries.notna/is_empty pattern remains")
        if "filterwarnings" in source and "GeoSeries.notna" in source:
            problems.append(f"{edition.name}: warning is being hidden instead of fixed")

    if problems:
        raise AssertionError("\n".join(problems))


def run_edition_tests() -> None:
    helper = Path(__file__).with_name("_edition_regressions.py")
    conservation_smoke = Path(__file__).with_name("_conservation_smoke.py")
    multiscale_integration = Path(__file__).with_name("_multiscale_integration_smoke.py")
    conservation_integration = Path(__file__).with_name("_conservation_integration_smoke.py")
    functional_integration = Path(__file__).with_name("_functional_integration_smoke.py")
    configuration_matrix = Path(__file__).with_name("_configuration_matrix.py")
    output_folder_localization = Path(__file__).with_name("_output_folder_localization.py")
    community_integration = Path(__file__).with_name("_community_integration_smoke.py")
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("MPLBACKEND", "Agg")
    env.setdefault("TERM", "xterm")
    env.setdefault("PYTHONWARNINGS", "error::FutureWarning")
    for edition in EDITIONS:
        recorded_run([sys.executable, str(Path(__file__).with_name("_species_selection.py")), str(edition)], env)
        for helper_script in (Path(__file__).with_name("_grid_reading.py"), helper, conservation_smoke, community_integration, multiscale_integration,
                              conservation_integration, functional_integration, configuration_matrix, output_folder_localization, Path(__file__).with_name("_metadata_exports.py"), Path(__file__).with_name("_public_output_policy.py"), Path(__file__).with_name("_public_geometry.py")):
            recorded_run([sys.executable, str(helper_script), str(edition)], env)
    parity = Path(__file__).with_name("_bilingual_parity.py")
    recorded_run([sys.executable, str(parity)], env)
    presentation = Path(__file__).with_name("_presentation_and_distribution.py")
    recorded_run([sys.executable, str(presentation)], env)
    recorded_run([sys.executable, str(Path(__file__).with_name("_json_reference_integrity.py"))], env)
    security = Path(__file__).with_name("_security_regressions.py")
    recorded_run([sys.executable, str(security)], env)
    recorded_run([sys.executable, str(Path(__file__).with_name("_security_lifecycle.py"))], env)
    recorded_run([sys.executable, str(Path(__file__).with_name("_coordinator_security.py"))], env)
    recorded_run([sys.executable, str(Path(__file__).with_name("_execution_recovery.py"))], env)
    recorded_run([sys.executable, str(Path(__file__).with_name("_distribution_recovery.py"))], env)
    hygiene = Path(__file__).with_name("_release_hygiene.py")
    recorded_run([sys.executable, str(hygiene)], env)


def main() -> int:
    global REPORT_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    REPORT_DIR = args.report_dir
    if REPORT_DIR:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
    print("Hispa-Syng v1.0 — regression suite")
    started_at = datetime.now(timezone.utc).isoformat()
    print(f"Python: {sys.version.split()[0]}")
    check_release_structure()
    print("PASS: release structure and source syntax")
    try:
        run_edition_tests()
    finally:
        if REPORT_DIR:
            versions = {}
            for name in ("numpy", "pandas", "geopandas", "shapely", "pyproj", "pyogrio", "scipy", "matplotlib", "seaborn", "scikit-learn", "statsmodels", "cryptography", "python-docx"):
                try:
                    module_name = {"scikit-learn": "sklearn", "python-docx": "docx"}.get(name, name)
                    module = importlib.import_module(module_name)
                    versions[name] = getattr(module, "__version__", None) or importlib.metadata.version(name)
                except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
                    versions[name] = f"unavailable: {type(exc).__name__}"
            source_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(ROOT.rglob("*.py"))}
            report = {"python": sys.version, "platform": platform.platform(), "dependencies": versions,
                      "started_at_utc": started_at, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                      "tests": RECORDS, "processes_executed": len(RECORDS), "source_sha256": source_hashes,
                      "native_windows_dpapi": "PASS: current-user roundtrip" if os.name == "nt" and any(r["name"] == "_security_lifecycle" and r["status"] == "PASS" for r in RECORDS) else "NOT VERIFIED",
                      "cross_windows_user_isolation": "NOT EXECUTED: requires a second Windows account",
                      "parity_criterion": "Exact equality of the serialized synthetic snapshots after their defined rounding; not a full operational-data equivalence certificate."}
            (REPORT_DIR / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    check_release_structure()
    print("PASS: no compiled artifacts generated")
    print("ALL REGRESSION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
