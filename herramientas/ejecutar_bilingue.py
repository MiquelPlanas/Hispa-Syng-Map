#!/usr/bin/env python3
"""Coordinate one shared Hispa-Syng selection and the two language runs."""

from __future__ import annotations

import argparse
import calendar
import copy
import html
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

from output_policy import register_public_output, public_product, REGISTRY_NAME
from hispa_security import SecurityError, _project_activity_lock, access_from_environment, project_is_protected, protect_all_existing_outputs
from secure_execution import begin_protected_execution, finish_protected_execution


def _project_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _language(value: str | None) -> str:
    return "EN" if str(value or "ES").strip().upper() in {"EN", "ENGLISH", "2"} else "ES"


def _load_spanish_api(project_root: Path):
    """Use the Spanish core only for the common input audit and menu logic.

    The analytical runs themselves are separate Python processes, each using
    its own language edition. This process does not execute either pipeline.
    """

    spanish_root = project_root / "PYTHON_ESP"
    source = spanish_root / "src"
    if not source.is_dir():
        raise FileNotFoundError(f"Missing Spanish source folder: {source}")
    sys.path.insert(0, str(spanish_root))
    sys.path.insert(0, str(source))
    from hippodec_maps.config import (  # type: ignore[import-not-found]
        REGION_MENU,
        load_config,
        normalize_region,
        resolve_input_paths,
    )
    from hippodec_maps.cli import _parse_years  # type: ignore[import-not-found]
    from hippodec_maps.data import read_and_clean_excel  # type: ignore[import-not-found]

    return {
        "REGION_MENU": REGION_MENU,
        "load_config": load_config,
        "normalize_region": normalize_region,
        "resolve_input_paths": resolve_input_paths,
        "parse_years": _parse_years,
        "read_and_clean_excel": read_and_clean_excel,
    }


def _check_layout(project_root: Path) -> tuple[Path, Path]:
    """Validate both editions before creating a bilingual run manifest."""

    spanish_root = project_root / "PYTHON_ESP"
    english_root = project_root / "PYTHON_ENGLISH"
    required = (
        spanish_root / "ejecutar_hippodec.py",
        english_root / "run_hippodec.py",
        spanish_root / "configuracion.yaml",
        english_root / "config.yaml",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Faltan archivos de una de las dos ediciones / "
            "Required files are missing from one edition: "
            + ", ".join(missing)
        )
    return spanish_root, english_root


def _relative_path(path: Path | str | None, project_root: Path) -> str | None:
    if path is None:
        return None
    resolved = Path(path).expanduser().resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        # External configured inputs remain usable. They are recorded as
        # absolute paths only when they genuinely live outside the project.
        return str(resolved)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_record(path: Path | str | None, project_root: Path) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False}
    resolved = Path(path).expanduser().resolve()
    record: dict[str, Any] = {
        "path": _relative_path(resolved, project_root),
        "exists": resolved.exists(),
        "kind": "directory" if resolved.is_dir() else "file",
    }
    if resolved.is_file():
        record["size_bytes"] = resolved.stat().st_size
        record["sha256"] = _sha256(resolved)
    elif resolved.is_dir():
        files = [item for item in resolved.rglob("*") if item.is_file()]
        record["file_count"] = len(files)
        record["relative_files"] = [
            item.relative_to(resolved).as_posix() for item in sorted(files)
        ][:2000]
    return record


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _message(language: str, spanish: str, english: str) -> str:
    return spanish if language == "ES" else english


def _duration_hms(seconds: float) -> str:
    elapsed = max(0, int(seconds))
    hours, remainder = divmod(elapsed, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _parse_year_pair_text(value: str) -> tuple[int, int]:
    """Parse a YYYY-YYYY pair without applying availability constraints."""

    text = value.strip()
    parts = text.split("-")
    if len(parts) != 2 or not all(
        part.strip().isdigit() and len(part.strip()) == 4 for part in parts
    ):
        raise ValueError("Invalid year-pair syntax")
    return int(parts[0].strip()), int(parts[1].strip())


def _prompt_year_correction(
    language: str,
    *,
    which: str,
    year_min: int,
    year_max: int,
    minimum_allowed: int | None = None,
) -> int:
    """Ask again only for the invalid start or end year."""

    is_start = which == "start"
    while True:
        prompt = _message(
            language,
            (
                f"Introduzca de nuevo el año inicial ({year_min}–{year_max}): "
                if is_start
                else f"Introduzca de nuevo el año final ({year_min}–{year_max}): "
            ),
            (
                f"Enter the initial year again ({year_min}–{year_max}): "
                if is_start
                else f"Enter the final year again ({year_min}–{year_max}): "
            ),
        )
        text = input(prompt).strip()
        if not (text.isdigit() and len(text) == 4):
            print(
                _message(
                    language,
                    "Año no válido. Introduzca un año de cuatro cifras.",
                    "Invalid year. Enter a four-digit year.",
                )
            )
            continue
        year = int(text)
        if not year_min <= year <= year_max:
            print(
                _message(
                    language,
                    f"Año fuera del rango válido ({year_min}–{year_max}).",
                    f"Year outside the valid range ({year_min}–{year_max}).",
                )
            )
            continue
        if minimum_allowed is not None and year < minimum_allowed:
            print(
                _message(
                    language,
                    f"El año final no puede ser anterior a {minimum_allowed}.",
                    f"The final year cannot be earlier than {minimum_allowed}.",
                )
            )
            continue
        return year


def _prompt_global_years(
    parse_years,
    *,
    language: str,
    years_default: object,
    available_min: int,
    available_max: int,
) -> tuple[int, int]:
    """Collect the overall period and re-ask only a wrong boundary year."""

    while True:
        entered = input(
            _message(
                language,
                f"Periodo [Todos; valor configurado: {years_default}]: ",
                f"Period [all; configured value: {years_default}]: ",
            )
        ).strip()
        source = entered or str(years_default)
        if source.strip().lower() in {"", "all", "todos", "todas"}:
            return available_min, available_max

        parts = source.split("-")
        if len(parts) != 2:
            print(
                _message(
                    language,
                    "Periodo no válido. Utilice AAAA-AAAA o 'todos'.",
                    "Invalid period. Use YYYY-YYYY or 'all'.",
                )
            )
            continue

        start_text, end_text = (part.strip() for part in parts)
        if not (start_text.isdigit() and len(start_text) == 4):
            print(
                _message(
                    language,
                    f"Año inicial no válido: '{start_text}'.",
                    f"Invalid initial year: '{start_text}'.",
                )
            )
            start = _prompt_year_correction(
                language, which="start", year_min=available_min, year_max=available_max
            )
        else:
            start = int(start_text)
            if not available_min <= start <= available_max:
                print(
                    _message(
                        language,
                        f"El año inicial {start} está fuera del rango disponible {available_min}–{available_max}.",
                        f"The initial year {start} is outside the available range {available_min}–{available_max}.",
                    )
                )
                start = _prompt_year_correction(
                    language, which="start", year_min=available_min, year_max=available_max
                )

        if not (end_text.isdigit() and len(end_text) == 4):
            print(
                _message(
                    language,
                    f"Año final no válido: '{end_text}'.",
                    f"Invalid final year: '{end_text}'.",
                )
            )
            end = _prompt_year_correction(
                language,
                which="end",
                year_min=available_min,
                year_max=available_max,
                minimum_allowed=start,
            )
        else:
            end = int(end_text)
            if not available_min <= end <= available_max:
                print(
                    _message(
                        language,
                        f"El año final {end} está fuera del rango disponible {available_min}–{available_max}.",
                        f"The final year {end} is outside the available range {available_min}–{available_max}.",
                    )
                )
                end = _prompt_year_correction(
                    language,
                    which="end",
                    year_min=available_min,
                    year_max=available_max,
                    minimum_allowed=start,
                )

        if start > end:
            print(
                _message(
                    language,
                    f"El año final {end} es anterior al año inicial {start}.",
                    f"The final year {end} is earlier than the initial year {start}.",
                )
            )
            end = _prompt_year_correction(
                language,
                which="end",
                year_min=available_min,
                year_max=available_max,
                minimum_allowed=start,
            )

        # Final core validation. Years without observations between the available
        # minimum and maximum remain valid by design.
        return parse_years(f"{start}-{end}", available_min, available_max)


def _parse_period_boundary(value: str, *, end: bool) -> datetime:
    """Parse MM-YYYY, YYYY-MM, or a bare year into a month boundary."""

    text = value.strip()
    match = re.fullmatch(r"(\d{1,2})[-/](\d{4})", text)
    if match:
        month, year = int(match.group(1)), int(match.group(2))
    else:
        match = re.fullmatch(r"(\d{4})[-/](\d{1,2})", text)
        if match:
            year, month = int(match.group(1)), int(match.group(2))
        elif re.fullmatch(r"\d{4}", text):
            year, month = int(text), 12 if end else 1
        else:
            raise ValueError("Invalid month-year value")
    if not 1 <= month <= 12:
        raise ValueError("Month must be between 1 and 12")
    day = calendar.monthrange(year, month)[1] if end else 1
    return datetime(year, month, day)


def _prompt_temporal_periods(
    year_min: int,
    year_max: int,
    language: str,
) -> tuple[dict[str, str], ...]:
    """Collect the comparison periods after the global selection is known."""

    print()
    print(
        _message(
            language,
            f"Período global seleccionado: {year_min}–{year_max}",
            f"Selected overall period: {year_min}–{year_max}",
        )
    )
    while True:
        entered = input(
            _message(
                language,
                "¿Cuántos períodos desea comparar? [0 = sin comparación; 2 o más]: ",
                "How many periods do you want to compare? [0 = no comparison; 2 or more]: ",
            )
        ).strip() or "2"
        try:
            number = int(entered)
            if number == 0:
                print(
                    _message(
                        language,
                        "No se realizará ninguna comparación entre períodos.",
                        "No comparison between periods will be performed.",
                    )
                )
                return ()
            if number < 2:
                raise ValueError
            break
        except ValueError:
            print(
                _message(
                    language,
                    "Introduzca 0 o un número entero igual o superior a 2.",
                    "Enter 0 or an integer greater than or equal to 2.",
                )
            )

    periods: list[dict[str, str]] = []
    overall_start = datetime(year_min, 1, 1)
    overall_end = datetime(year_max, 12, 31)
    for index in range(number):
        while True:
            start_value = input(
                _message(
                    language,
                    f"Período {index + 1}: inicio (MM-AAAA o AAAA): ",
                    f"Period {index + 1}: start (MM-YYYY or YYYY): ",
                )
            ).strip()
            try:
                start = _parse_period_boundary(start_value, end=False)
            except ValueError:
                print(
                    _message(
                        language,
                        "Inicio no válido. Use MM-AAAA o AAAA.",
                        "Invalid start. Use MM-YYYY or YYYY.",
                    )
                )
                continue
            if not overall_start <= start <= overall_end:
                print(
                    _message(
                        language,
                        f"El inicio debe estar dentro del período global {year_min}–{year_max}.",
                        f"The start must fall within the overall period {year_min}–{year_max}.",
                    )
                )
                continue
            if periods and start <= datetime.fromisoformat(periods[-1]["end"]):
                print(
                    _message(
                        language,
                        "El inicio debe ser posterior al final del período anterior y no puede solaparse.",
                        "The start must be later than the end of the previous period and cannot overlap it.",
                    )
                )
                continue
            break

        while True:
            end_value = input(
                _message(
                    language,
                    f"Período {index + 1}: fin (MM-AAAA o AAAA): ",
                    f"Period {index + 1}: end (MM-YYYY or YYYY): ",
                )
            ).strip()
            try:
                end = _parse_period_boundary(end_value, end=True)
            except ValueError:
                print(
                    _message(
                        language,
                        "Fin no válido. Use MM-AAAA o AAAA.",
                        "Invalid end. Use MM-YYYY or YYYY.",
                    )
                )
                continue
            if not overall_start <= end <= overall_end:
                print(
                    _message(
                        language,
                        f"El fin debe estar dentro del período global {year_min}–{year_max}.",
                        f"The end must fall within the overall period {year_min}–{year_max}.",
                    )
                )
                continue
            if end < start:
                print(
                    _message(
                        language,
                        "El fin no puede ser anterior al inicio de este período.",
                        "The end cannot be earlier than the start of this period.",
                    )
                )
                continue
            break

        label = f"{start:%m-%Y}–{end:%m-%Y}"
        periods.append(
            {
                "label": label,
                "start": start.date().isoformat(),
                "end": end.date().isoformat(),
            }
        )

    print(
        _message(language, "Períodos comparativos seleccionados:", "Selected comparison periods:")
    )
    for period in periods:
        print(f"  {period['label']}")
    return tuple(periods)


def _prompt_parameters(api: dict[str, Any], summary: dict[str, Any], defaults: dict[str, Any], language: str):
    parse_years = api["parse_years"]
    normalize_region = api["normalize_region"]
    region_menu = api["REGION_MENU"]
    available_min = int(summary["available_year_min"])
    available_max = int(summary["available_year_max"])
    available_species = list(summary["available_species"])

    print()
    print(
        _message(
            language,
            f"Rango de años disponible: {available_min}–{available_max}",
            f"Available year range: {available_min}–{available_max}",
        )
    )
    years_default = defaults.get("years", "all")
    years = _prompt_global_years(
        parse_years,
        language=language,
        years_default=years_default,
        available_min=available_min,
        available_max=available_max,
    )

    grid_default = int(defaults.get("grid_km", 10))
    while True:
        entered = input(
            _message(
                language,
                f"Tamaño de malla: 1, 5 o 10 km [{grid_default}]: ",
                f"Grid size: 1, 5, or 10 km [{grid_default}]: ",
            )
        ).strip() or str(grid_default)
        if entered in {"1", "5", "10"}:
            grid = int(entered)
            break
        print(_message(language, "Opción no válida.", "Invalid option."))

    print()
    print(
        _message(
            language,
            "Demarcaciones marinas MITECO:\n 0 Todas\n 1 Cantábrica noroccidental\n 2 Sudatlántica\n 3 Estrecho y Alborán\n 4 Levantino-Balear\n 5 Islas Canarias",
            "MITECO marine subdivisions:\n 0 All\n 1 North-western Cantabrian\n 2 South Atlantic\n 3 Strait and Alboran\n 4 Levantine-Balearic\n 5 Canary Islands",
        )
    )
    region_default = normalize_region(defaults.get("region", "all"))
    default_code = next(code for code, slug in region_menu.items() if slug == region_default)
    while True:
        entered = input(
            _message(language, f"Región 0–5 [{default_code}]: ", f"Region 0–5 [{default_code}]: ")
        ).strip() or default_code
        try:
            region = normalize_region(entered)
            break
        except ValueError:
            print(_message(language, "Opción no válida.", "Invalid option."))

    print()
    print(_message(language, "Especies disponibles:\n 0 Todas", "Available species:\n 0 All"))
    for index, species in enumerate(available_species, 1):
        print(f" {index:2d} {species}")
    while True:
        entered = input(
            _message(
                language,
                "Especies por número (p. ej., 1,3), o 0 para todas [0]: ",
                "Species by number (e.g. 1,3), or 0 for all [0]: ",
            )
        ).strip() or "0"
        if entered.casefold() in {"0", "all", "todas", "todos"}:
            species_selected = tuple(available_species)
            break
        try:
            indices = [
                int(piece)
                for piece in entered.replace(";", ",").split(",")
                if piece.strip()
            ]
            if not indices or any(index < 1 or index > len(available_species) for index in indices):
                raise ValueError
            species_selected = tuple(
                dict.fromkeys(available_species[index - 1] for index in indices)
            )
            break
        except ValueError:
            print(_message(language, "Selección no válida.", "Invalid selection."))
    temporal_periods = _prompt_temporal_periods(
        years[0],
        years[1],
        language,
    )
    return years[0], years[1], grid, region, species_selected, temporal_periods


def _run_config(
    base_config: dict[str, Any],
    resolved_paths: dict[str, Path | str | None],
    project_root: Path,
    results_root: Path,
    year_min: int,
    year_max: int,
    grid: int,
    region: str,
    species: tuple[str, ...],
    temporal_periods: tuple[dict[str, str], ...],
    args: argparse.Namespace,
) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    config["paths"]["input_excel"] = _relative_path(resolved_paths["excel"], project_root)
    config["paths"]["sheet"] = str(resolved_paths["sheet"])
    for config_key, path_key in (
        ("grids", "grids"),
        ("gshhg", "gshhg"),
        ("demarcations", "demarcations"),
        ("logo", "logo"),
        ("protected_areas", "protected_areas"),
        ("traits", "traits"),
    ):
        config["paths"][config_key] = _relative_path(resolved_paths[path_key], project_root)
    config["paths"]["results"] = _relative_path(results_root, project_root)
    config["execution"].update(
        {
            "interactive": False,
            "years": f"{year_min}-{year_max}",
            "grid_km": grid,
            "region": region,
            "species": list(species),
            "open_browser": False,
        }
    )
    config["analysis"]["temporal_periods"] = list(temporal_periods)
    if args.maps_only:
        config["execution"]["maps_only"] = True
    if args.permutations is not None:
        if args.permutations < 9:
            raise ValueError("--permutations must be at least 9.")
        config["analysis"]["permutations"] = args.permutations
    return config


def _viewer_paths(
    run_root: Path,
    language: str,
    project_root: Path | None = None,
) -> dict[str, str | None]:
    def shown_path(path: Path | None) -> str | None:
        if path is None:
            return None
        return (
            _relative_path(path, project_root)
            if project_root is not None
            else str(path)
        )

    if not run_root.is_dir():
        return {
            "run_root": shown_path(run_root),
            "viewer": None,
            "standalone_viewer": None,
        }
    publication_name = "Publicacion_Web" if language == "ES" else "Web_Publication"
    viewer_dir_name = "08_visores" if language == "ES" else "08_viewers"
    publication_index = run_root / publication_name / "index.html"
    viewer_dir = run_root / viewer_dir_name
    patterns = ("Visor_Hippo_DEC_*.html", "Hippo_DEC_Viewer_*.html")
    candidates = [path for pattern in patterns for path in sorted(viewer_dir.glob(pattern))]
    standalone = candidates[0] if candidates else None
    viewer = publication_index if publication_index.is_file() else standalone
    return {
        "run_root": shown_path(run_root),
        "viewer": shown_path(viewer),
        "standalone_viewer": shown_path(standalone),
    }


def _publication_map_files(publication_root: Path, language: str) -> dict[str, Path]:
    """Find the canonical HTML pages inside one language publication."""

    folder = publication_root / ("mapas" if language == "ES" else "maps")
    patterns = (
        ("map1", "Mapa1_Observaciones_*.html")
        if language == "ES"
        else ("map1", "Map1_Observations_*.html"),
        ("map2", "Mapa2_Densidad_*.html")
        if language == "ES"
        else ("map2", "Map2_Density_*.html"),
        ("map3", "Mapa3_Variables_*.html")
        if language == "ES"
        else ("map3", "Map3_Variables_*.html"),
        ("priority", "Mapa_Interactivo_Zonas_Prioritarias_Conservacion_*.html")
        if language == "ES"
        else ("priority", "Interactive_Priority_Conservation_Areas_Map_*.html"),
    )
    found: dict[str, Path] = {}
    for key, pattern in patterns:
        candidates = sorted(folder.glob(pattern))
        if candidates:
            found[key] = candidates[0]
    found["viewer"] = publication_root / "index.html"
    return found


def _rewrite_bilingual_publication_links(
    path: Path,
    targets: dict[str, Path],
) -> None:
    """Rebase ES/EN selector links after copying both publications together."""

    if not path.is_file():
        return
    product = public_product(path)
    text = path.read_text(encoding="utf-8")
    for code in ("ES", "EN"):
        target = targets.get(code)
        if target is None:
            continue
        link = html.escape(
            os.path.relpath(target.resolve(), start=path.parent.resolve()).replace(
                os.sep, "/"
            ),
            quote=True,
        )
        text = re.sub(
            rf'(data-{code.lower()}-url=")[^"]*(")',
            rf"\g<1>{link}\g<2>",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    path.write_text(text, encoding="utf-8")
    if product:
        register_public_output(path, product)


def _refresh_publication_manifest(root: Path, language: str) -> None:
    """Refresh the integrity manifest after bilingual links are rewritten."""

    manifest_name = "manifiesto.json" if language == "ES" else "manifest.json"
    manifest_path = root / manifest_name
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        manifest = {
            "product": (
                "Publicación web Hispa-Syng v1.0 (Proyecto Hippo-DEC)"
                if language == "ES"
                else "Hispa-Syng v1.0 Web Publication (Hippo-DEC project)"
            ),
            "created": datetime.now().isoformat(timespec="seconds"),
        }

    records = []
    for candidate in sorted(path for path in root.rglob("*") if path.is_file()):
        if candidate == manifest_path or candidate.name == REGISTRY_NAME:
            continue
        records.append(
            {
                "file": candidate.relative_to(root).as_posix(),
                "bytes": candidate.stat().st_size,
                "sha256": _sha256(candidate),
            }
        )
    manifest["files"] = records
    manifest["updated"] = datetime.now().isoformat(timespec="seconds")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    register_public_output(manifest_path, "integrity_manifest")

def _publication_logo_source(project_root: Path, preferred: Path | None = None) -> Path | None:
    """Return the configured or automatically discovered institutional logo."""

    if preferred is not None and preferred.is_file():
        return preferred
    candidates = sorted(
        path
        for path in project_root.iterdir()
        if path.is_file()
        and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
        and path.stem.casefold().startswith("logos")
    )
    return candidates[0] if candidates else None


def _build_bilingual_publication(
    project_root: Path,
    execution_id: str,
    logo_source: Path | None = None,
    results_root: Path | None = None,
) -> Path | None:
    """Create one self-contained bilingual static publication for a run."""

    results_root = results_root or project_root / "Resultados"
    spanish_source = results_root / f"ejecucion_{execution_id}_ESP" / "Publicacion_Web"
    english_source = results_root / f"run_{execution_id}_EN" / "Web_Publication"
    if not spanish_source.is_dir() or not english_source.is_dir():
        return None

    bundle = results_root / f"Publicacion_Web_Bilingue_{execution_id}"
    if bundle.exists():
        raise FileExistsError(f"La publicación bilingüe ya existe: {bundle}")
    spanish_destination = bundle / "ES"
    english_destination = bundle / "EN"
    shutil.copytree(spanish_source, spanish_destination)
    shutil.copytree(english_source, english_destination)

    logo = _publication_logo_source(project_root, logo_source)
    logo_name = "logos.png"
    if logo is not None:
        logo_name = "logos" + logo.suffix.lower()
        shutil.copy2(logo, bundle / logo_name)
        register_public_output(bundle / logo_name, "institutional_logo")

    source_pages = {
        "ES": _publication_map_files(spanish_destination, "ES"),
        "EN": _publication_map_files(english_destination, "EN"),
    }
    for code in ("ES", "EN"):
        for page, current in source_pages[code].items():
            targets = {
                target_code: source_pages[target_code][page]
                for target_code in ("ES", "EN")
                if page in source_pages[target_code]
            }
            _rewrite_bilingual_publication_links(current, targets)
    _refresh_publication_manifest(spanish_destination, "ES")
    _refresh_publication_manifest(english_destination, "EN")

    logo_markup = (
        '<header class="institutional-header">'
        f'<img src="{html.escape(logo_name, quote=True)}" '
        'alt="Hispa-Syng, Hippo-DEC and institutional logos">'
        "</header>\n"
        if logo is not None
        else ""
    )
    security_publication_note = (
        "<p class=\"note\">Proyecto protegido: Map 1 y las descargas sensibles están cifrados; ábralos mediante Hispa-Syng.bat &gt; Seguridad y accesos. / Protected project: Map 1 and sensitive downloads are encrypted; open them through Hispa-Syng.bat &gt; Security and access.</p>\n"
        if os.environ.get("HISPA_SYNG_SECURITY_MODE", "open").casefold() == "protected"
        else ""
    )
    index_html = (
        "<!doctype html>\n"
        '<html lang="es">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Hispa-Syng v1.0 (Proyecto Hippo-DEC / Hippo-DEC project) — Publicación web bilingüe / Bilingual web publication</title>\n"
        "<style>body{font-family:Arial,sans-serif;max-width:820px;margin:6vh auto;padding:24px;color:#12304a;background:#f5f8fa}"
        "a{display:inline-block;margin:8px 8px 8px 0;padding:12px 18px;border-radius:7px;background:#176b87;color:#fff;text-decoration:none;font-weight:700}"
        "a:hover{background:#12304a}.note{color:#587080}.institutional-header{margin:0 0 18px;text-align:center}.institutional-header img{display:block;height:auto;margin:auto;max-width:100%;width:720px}</style>\n</head>\n<body>\n"
        + logo_markup
        + (
            "<h1>Hispa-Syng v1.0 (Proyecto Hippo-DEC / Hippo-DEC project)</h1>\n            <h2>Publicación web bilingüe / Bilingual web publication</h2>\n"
            "<p>Seleccione el idioma / Select a language.</p>\n"
            "<p>El visor permite cambiar de idioma conservando el estado del mapa / The viewer preserves the map state when you change language.</p>\n"
            '<p><a href="ES/index.html">Español</a><a href="EN/index.html">English</a></p>\n'
            '<p class="note">La publicación es estática para los productos no sensibles / The publication is static for non-sensitive products.</p>\n'
            + security_publication_note
            + "</body>\n</html>\n"
        )
    )
    (bundle / "index.html").write_text(
        index_html,
        encoding="utf-8",
    )
    (bundle / "LEEME_SUBIDA.txt").write_text(
        "HISPA-SYNG v1.0 — PROYECTO HIPPO-DEC / HIPPO-DEC PROJECT — PUBLICACIÓN WEB BILINGÜE / BILINGUAL WEB PUBLICATION\n\n"
        "Suba esta carpeta completa al servidor web sin cambiar la estructura interna.\n"
        "Upload this complete folder to the web server without changing its internal structure.\n"
        "Configure index.html como documento predeterminado / Set index.html as the default document.\n"
        "Las subcarpetas ES y EN contienen las publicaciones completas y deben permanecer juntas.\n"
        "The ES and EN subfolders contain the complete publications and must remain together.\n"
        "No necesita instalar Python, R ni una base de datos para los productos no sensibles. En un proyecto protegido, los contenidos sensibles .hse se abren desde el menú Seguridad y accesos de Hispa-Syng.\n"
        "Python, R and a database are not needed for non-sensitive products. In a protected project, sensitive .hse content is opened through Hispa-Syng Security and access.\n",
        encoding="utf-8",
    )
    register_public_output(bundle / "index.html", "bilingual_index")
    register_public_output(bundle / "LEEME_SUBIDA.txt", "upload_instructions")
    return bundle


def _child_command(
    project_root: Path,
    language_root: Path,
    language: str,
    config_path: Path,
    results_root: Path,
    run_root: Path,
    execution_id: str,
    year_min: int,
    year_max: int,
    grid: int,
    region: str,
    species: tuple[str, ...],
) -> list[str]:
    entrypoint = language_root / ("ejecutar_hippodec.py" if language == "ES" else "run_hippodec.py")
    command = [
        sys.executable,
        str(entrypoint),
        "--config",
        str(config_path),
        "--project-root",
        str(project_root),
        "--resource-root",
        str(language_root),
        "--results-root",
        str(results_root),
        "--run-root",
        str(run_root),
        "--execution-id",
        execution_id,
        "--language-code",
        language,
        "--years",
        f"{year_min}-{year_max}",
        "--grid",
        str(grid),
        "--region",
        region,
        "--no-interactive",
    ]
    for name in species:
        command.extend(["--species", name])
    if not species:
        command.extend(["--species", ""])
    return command


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui-language", default="ES", help="Language for prompts: ES or EN.")
    parser.add_argument("--project-root", help="Hispa-Syng project root folder.")
    parser.add_argument("--maps-only", action="store_true", help="Run maps only in both editions.")
    parser.add_argument("--permutations", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--open-browser", action="store_true", help=argparse.SUPPRESS)
    return parser


def _main(argv: list[str] | None = None) -> int:
    total_started = time.perf_counter()
    args = _parser().parse_args(argv)
    language = _language(args.ui_language)
    project_root = _project_root(args.project_root)
    protected_mode = project_is_protected(project_root)
    security_context = access_from_environment(project_root)
    if protected_mode and security_context is None:
        print(_message(language, "ERROR: el proyecto está protegido y no se ha autorizado el acceso desde Hispa-Syng.bat.", "ERROR: the project is protected and access was not authorized through Hispa-Syng.bat."), file=sys.stderr)
        return 1
    spanish_root = project_root / "PYTHON_ESP"
    english_root = project_root / "PYTHON_ENGLISH"
    execution_id = None
    try:
        if security_context is not None:
            protect_all_existing_outputs(project_root, security_context)
        spanish_root, english_root = _check_layout(project_root)
        api = _load_spanish_api(project_root)
        base_config = api["load_config"](spanish_root / "configuracion.yaml")
        resolved_paths = api["resolve_input_paths"](project_root, base_config)
        raw_data, summary = api["read_and_clean_excel"](
            Path(resolved_paths["excel"]), str(resolved_paths["sheet"])
        )
        del raw_data  # The child pipelines read the same input afresh from the manifest config.
        year_min, year_max, grid, region, species, temporal_periods = _prompt_parameters(
            api,
            summary,
            base_config["execution"],
            language,
        )

        results_root = project_root / "Resultados"
        execution_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        if security_context is not None:
            results_root = begin_protected_execution(project_root, execution_id, security_context)
        else:
            results_root.mkdir(parents=True, exist_ok=True)
        control_root = project_root / ".ejecuciones" / execution_id
        control_root.mkdir(parents=True, exist_ok=False)
        es_run_root = results_root / f"ejecucion_{execution_id}_ESP"
        en_run_root = results_root / f"run_{execution_id}_EN"

        es_config = _run_config(
            base_config,
            resolved_paths,
            project_root,
            results_root,
            year_min,
            year_max,
            grid,
            region,
            species,
            temporal_periods,
            args,
        )
        en_config = copy.deepcopy(es_config)
        es_config_path = control_root / "configuracion_ejecucion_ES.yaml"
        en_config_path = control_root / "execution_config_EN.yaml"
        import yaml

        es_config_path.write_text(
            yaml.safe_dump(es_config, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        en_config_path.write_text(
            yaml.safe_dump(en_config, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

        manifest_path = control_root / "manifiesto_ejecucion_bilingue.json"
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "execution_id": execution_id,
            "created_at": datetime.now().astimezone().isoformat(),
            "ui_language": language,
            "project_root": ".",
            "parameters": {
                "year_min": year_min,
                "year_max": year_max,
                "grid_km": grid,
                "region": region,
                "species": list(species),
                "temporal_periods": list(temporal_periods),
                "maps_only": bool(es_config["execution"].get("maps_only", False)),
                "permutations": es_config["analysis"].get("permutations"),
                "gshhs_required": True,
            },
            "shared_inputs": {
                key: _input_record(value, project_root)
                for key, value in resolved_paths.items()
                if key != "sheet"
            },
            "control_files": {
                "spanish_config": _relative_path(es_config_path, project_root),
                "english_config": _relative_path(en_config_path, project_root),
                "manifest": _relative_path(manifest_path, project_root),
            },
            "runs": {
                "ES": {
                    "status": "pending",
                    "root": _relative_path(es_run_root, project_root),
                    "config": _relative_path(es_config_path, project_root),
                },
                "EN": {
                    "status": "pending",
                    "root": _relative_path(en_run_root, project_root),
                    "config": _relative_path(en_config_path, project_root),
                },
            },
        }
        _write_json(manifest_path, manifest)

        print()
        print(_message(language, "Iniciando la versión española con la selección común...", "Starting the Spanish edition with the shared selection..."))
        command_es = _child_command(
            project_root,
            spanish_root,
            "ES",
            es_config_path,
            results_root,
            es_run_root,
            execution_id,
            year_min,
            year_max,
            grid,
            region,
            species,
        )
        es_started = time.perf_counter()
        result_es = subprocess.run(command_es, cwd=str(project_root), check=False)
        es_elapsed = time.perf_counter() - es_started
        print(_message(language, f"Versión española: {_duration_hms(es_elapsed)}.", f"Spanish edition: {_duration_hms(es_elapsed)}."))
        if result_es.returncode != 0:
            manifest["status"] = "failed"
            manifest["failed_language"] = "ES"
            manifest["runs"]["ES"]["status"] = "failed"
            manifest["runs"]["ES"]["returncode"] = result_es.returncode
            _write_json(manifest_path, manifest)
            print(_message(language, "La versión española ha fallado; la inglesa no se iniciará.", "The Spanish edition failed; the English edition will not start."))
            if security_context is not None:
                finish_protected_execution(project_root, execution_id, security_context, publish=False)
            return result_es.returncode or 1
        manifest["runs"]["ES"].update(
            {
                "status": "completed",
                "elapsed_seconds": round(es_elapsed, 3),
                "outputs": _viewer_paths(es_run_root, "ES", project_root),
            }
        )
        _write_json(manifest_path, manifest)

        print()
        print(_message(language, "Iniciando la versión inglesa con exactamente la misma selección...", "Starting the English edition with exactly the same selection..."))
        command_en = _child_command(
            project_root,
            english_root,
            "EN",
            en_config_path,
            results_root,
            en_run_root,
            execution_id,
            year_min,
            year_max,
            grid,
            region,
            species,
        )
        en_started = time.perf_counter()
        result_en = subprocess.run(command_en, cwd=str(project_root), check=False)
        en_elapsed = time.perf_counter() - en_started
        print(_message(language, f"Versión inglesa: {_duration_hms(en_elapsed)}.", f"English edition: {_duration_hms(en_elapsed)}."))
        if result_en.returncode != 0:
            manifest["status"] = "failed"
            manifest["failed_language"] = "EN"
            manifest["runs"]["EN"]["status"] = "failed"
            manifest["runs"]["EN"]["returncode"] = result_en.returncode
            _write_json(manifest_path, manifest)
            print(_message(language, "La versión inglesa ha fallado después de completar la española.", "The English edition failed after the Spanish edition completed."))
            if security_context is not None:
                finish_protected_execution(project_root, execution_id, security_context, publish=False)
            return result_en.returncode or 1
        manifest["runs"]["EN"].update(
            {
                "status": "completed",
                "elapsed_seconds": round(en_elapsed, 3),
                "outputs": _viewer_paths(en_run_root, "EN", project_root),
            }
        )
        bilingual_publication = _build_bilingual_publication(
            project_root,
            execution_id,
            Path(resolved_paths["logo"]) if resolved_paths.get("logo") else None,
            results_root=results_root,
        )
        if bilingual_publication is not None:
            manifest["bilingual_publication"] = _relative_path(
                bilingual_publication, project_root
            )
        if security_context is not None:
            security_result = finish_protected_execution(project_root, execution_id, security_context)
            results_root = project_root / "Resultados"
            es_run_root = results_root / f"ejecucion_{execution_id}_ESP"
            en_run_root = results_root / f"run_{execution_id}_EN"
            for code, run in (("ES", es_run_root), ("EN", en_run_root)):
                manifest["runs"][code]["root"] = _relative_path(run, project_root)
                manifest["runs"][code]["outputs"] = _viewer_paths(run, code, project_root)
            if bilingual_publication is not None:
                bilingual_publication = results_root / f"Publicacion_Web_Bilingue_{execution_id}"
                manifest["bilingual_publication"] = _relative_path(bilingual_publication, project_root)
            manifest["security"] = {
                "mode": "protected",
                "project_id": security_context.project_id,
                "protected_output_files": int(security_result.get("files", 0)),
                "audit": _relative_path(Path(security_result["audit"]), project_root) if security_result.get("audit") else None,
            }
            print(_message(language, f"Protección aplicada: {security_result.get('files', 0)} archivos sensibles cifrados.", f"Protection applied: {security_result.get('files', 0)} sensitive files encrypted."))
        else:
            manifest["security"] = {"mode": "open"}
        manifest["status"] = "completed"
        manifest["completed_at"] = datetime.now().astimezone().isoformat()
        manifest["elapsed_seconds"] = round(time.perf_counter() - total_started, 3)
        _write_json(manifest_path, manifest)

        selected_run = es_run_root if language == "ES" else en_run_root
        selected_output = _viewer_paths(selected_run, language).get("viewer")
        if args.open_browser or bool(base_config["execution"].get("open_browser", False)):
            if selected_output:
                webbrowser.open(Path(selected_output).resolve().as_uri())
        print()
        print(_message(language, "Las dos versiones han finalizado correctamente.", "Both editions completed successfully."))
        print(_message(language, f"Tiempo total: {_duration_hms(time.perf_counter() - total_started)}.", f"Total elapsed time: {_duration_hms(time.perf_counter() - total_started)}."))
        print(_message(language, f"Manifiesto común: {manifest_path}", f"Shared manifest: {manifest_path}"))
        if bilingual_publication is not None:
            print(
                _message(
                    language,
                    f"Publicación web bilingüe: {bilingual_publication}",
                    f"Bilingual web publication: {bilingual_publication}",
                )
            )
        return 0
    except KeyboardInterrupt:
        if security_context is not None and execution_id:
            try:
                finish_protected_execution(project_root, execution_id, security_context, publish=False)
            except Exception:
                pass  # The durable journal remains for authenticated recovery.
        print(_message(language, "\nEjecución cancelada.", "\nRun cancelled."), file=sys.stderr)
        return 130
    except Exception as exc:
        print(_message(language, f"\nERROR en el coordinador bilingüe: {exc}", f"\nERROR in the bilingual coordinator: {exc}"), file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        with _project_activity_lock(_project_root(args.project_root)):
            return _main(argv)
    except SecurityError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
