"""Interfaz de línea de comandos para personas usuarias y ejecuciones automáticas."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from .config import (
    REGION_MENU,
    RunParameters,
    load_config,
    normalize_region,
    resolve_input_paths,
)
from .data import parse_species_argument, read_and_clean_excel
from .pipeline import run_pipeline
from .localization import translate_text


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Genera los mapas completos de Hispa-Syng v1.0 (Proyecto Hippo-DEC) y los análisis ecológicos.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config", default="configuracion.yaml", help="Archivo de configuración YAML."
    )
    parser.add_argument(
        "--project-root", help="Carpeta principal que contiene los datos de entrada."
    )
    parser.add_argument(
        "--resource-root",
        help="Carpeta del programa que contiene manuales y recursos de esta edición.",
    )
    parser.add_argument(
        "--results-root",
        help="Carpeta común donde se guardan los resultados de la ejecución.",
    )
    parser.add_argument(
        "--run-root",
        help="Carpeta exacta de esta ejecución; se usa para coordinar las dos ediciones.",
    )
    parser.add_argument(
        "--execution-id",
        help="Identificador común de la ejecución bilingüe.",
    )
    parser.add_argument(
        "--language-code",
        help="Código de la edición que se está ejecutando: ES o EN.",
    )
    parser.add_argument("--years", help="Periodo, por ejemplo 2017-2022, o 'todos'.")
    parser.add_argument(
        "--grid", type=int, choices=[1, 5, 10], help="Resolución de la malla en kilómetros."
    )
    parser.add_argument(
        "--region", help="todas, cantabrica, sudatlantica, alboran, levantina o canarias."
    )
    parser.add_argument(
        "--species",
        action="append",
        help="Especie; puede repetirse o separarse mediante comas.",
    )
    parser.add_argument(
        "--no-interactive", action="store_true", help="No formular preguntas interactivas."
    )
    parser.add_argument(
        "--open-browser", action="store_true", help="Abrir los archivos HTML después de crearlos."
    )
    parser.add_argument(
        "--maps-only",
        action="store_true",
        help="Generar solo los mapas y omitir los bloques analíticos 8–21.",
    )
    parser.add_argument(
        "--permutations",
        type=int,
        help="Número de permutaciones de las pruebas (producción: 999; comprobación rápida: 49).",
    )
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    return parser


def _parse_years(value: object, year_min: int, year_max: int) -> tuple[int, int]:
    if value is None or str(value).strip().lower() in {"", "all", "todos", "todas"}:
        return year_min, year_max
    text = str(value).strip()
    parts = text.split("-")
    if len(parts) != 2 or not all(
        part.strip().isdigit() and len(part.strip()) == 4 for part in parts
    ):
        raise ValueError("El periodo debe escribirse como AAAA-AAAA o 'todos'.")
    start, end = map(int, parts)
    if not year_min <= start <= year_max:
        raise ValueError(
            f"El año inicial debe estar comprendido entre {year_min} y {year_max}."
        )
    if not year_min <= end <= year_max:
        raise ValueError(
            f"El año final debe estar comprendido entre {year_min} y {year_max}."
        )
    if start > end:
        raise ValueError("El año inicial no puede ser posterior al año final.")
    return start, end


def _interactive_parameters(
    summary: dict, defaults: dict
) -> tuple[int, int, int, str, tuple[str, ...]]:
    available_min = int(summary["available_year_min"])
    available_max = int(summary["available_year_max"])
    available_species = list(summary["available_species"])
    print(f"\nRango de años disponible: {available_min}–{available_max}")
    years_default = defaults.get("years", "all")
    while True:
        entered = input(
            f"Periodo [Todos; valor configurado: {years_default}]: "
        ).strip()
        try:
            years = _parse_years(entered or years_default, available_min, available_max)
            break
        except ValueError as exc:
            print(f"Opción no válida: {exc}")

    grid_default = int(defaults.get("grid_km", 10))
    while True:
        entered = input(
            f"Tamaño de malla: 1, 5 o 10 km [{grid_default}]: "
        ).strip() or str(grid_default)
        if entered in {"1", "5", "10"}:
            grid = int(entered)
            break
        print("Opción no válida.")

    print(
        "\nDemarcaciones marinas MITECO:\n 0 Todas\n 1 Cantábrica noroccidental\n 2 Sudatlántica\n 3 Estrecho y Alborán\n 4 Levantino-Balear\n 5 Islas Canarias"
    )
    region_default = normalize_region(defaults.get("region", "all"))
    default_code = next(
        code for code, slug in REGION_MENU.items() if slug == region_default
    )
    while True:
        entered = input(f"Región 0–5 [{default_code}]: ").strip() or default_code
        try:
            region = normalize_region(entered)
            break
        except ValueError:
            print("Opción no válida.")

    print("\nEspecies disponibles:\n 0 Todas")
    for index, species in enumerate(available_species, 1):
        print(f" {index:2d} {species}")
    while True:
        entered = (
            input("Especies por número (p. ej., 1,3), o 0 para todas [0]: ").strip()
            or "0"
        )
        if entered.lower() in {"0", "all", "todas", "todos"}:
            species_selected = tuple(available_species)
            break
        try:
            indices = [
                int(piece)
                for piece in entered.replace(";", ",").split(",")
                if piece.strip()
            ]
            if not indices or any(
                index < 1 or index > len(available_species) for index in indices
            ):
                raise ValueError
            species_selected = tuple(
                dict.fromkeys(available_species[index - 1] for index in indices)
            )
            break
        except ValueError:
            print("Selección no válida.")
    return years[0], years[1], grid, region, species_selected


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    script_root = Path(__file__).resolve().parents[2]
    project_root = (
        Path(args.project_root).expanduser().resolve()
        if args.project_root
        else script_root
    )
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        candidate = project_root / config_path
        if not candidate.exists() and (script_root / config_path).exists():
            candidate = script_root / config_path
        config_path = candidate
    try:
        config = load_config(config_path)
        if args.results_root:
            results_root = Path(args.results_root).expanduser()
            if not results_root.is_absolute():
                results_root = project_root / results_root
            config["paths"]["results"] = str(results_root.resolve())
        if args.maps_only:
            config["execution"]["maps_only"] = True
        if args.permutations is not None:
            if args.permutations < 9:
                raise ValueError("--permutations debe ser como mínimo 9.")
            config["analysis"]["permutations"] = args.permutations
        paths = resolve_input_paths(project_root, config)
        raw_data, summary = read_and_clean_excel(
            Path(paths["excel"]), str(paths["sheet"])
        )
        interactive = (
            bool(config["execution"].get("interactive", True))
            and not args.no_interactive
        )
        if interactive:
            year_min, year_max, grid, region, species = _interactive_parameters(
                summary, config["execution"]
            )
        else:
            year_source = (
                args.years
                if args.years is not None
                else config["execution"].get("years", "all")
            )
            year_min, year_max = _parse_years(
                year_source,
                int(summary["available_year_min"]),
                int(summary["available_year_max"]),
            )
            grid = (
                args.grid
                if args.grid is not None
                else int(config["execution"].get("grid_km", 10))
            )
            if grid not in {1, 5, 10}:
                raise ValueError("grid_km debe ser 1, 5 o 10.")
            region = normalize_region(
                args.region
                if args.region is not None
                else config["execution"].get("region", "all")
            )
            species_source = (
                args.species
                if args.species is not None
                else config["execution"].get("species", "all")
            )
            species = parse_species_argument(
                species_source, summary["available_species"]
            )
        params = RunParameters(
            year_min=year_min,
            year_max=year_max,
            grid_km=grid,
            region=region,
            species_raw=species,
            open_browser=bool(
                args.open_browser or config["execution"].get("open_browser", False)
            ),
            execution_id=args.execution_id,
            language_code=args.language_code,
        )
        resource_root = (
            Path(args.resource_root).expanduser().resolve()
            if args.resource_root
            else script_root
        )
        forced_run_root = (
            Path(args.run_root).expanduser().resolve() if args.run_root else None
        )
        # Protected execution is coordinated through the private staging area.
        security_tools = project_root / "herramientas"
        if (security_tools / "hispa_security.py").is_file():
            sys.path.insert(0, str(security_tools))
            from hispa_security import project_is_protected
            from secure_execution import guard_child_execution
            if project_is_protected(project_root):
                guard_child_execution(project_root, forced_run_root, Path(config["paths"]["results"]), args.execution_id)
                params = __import__("dataclasses").replace(params, open_browser=False)
        outputs = run_pipeline(
            project_root,
            config,
            paths,
            raw_data,
            summary,
            params,
            forced_run_root=forced_run_root,
            resource_root=resource_root,
        )
        print("\nLa ejecución ha finalizado correctamente.")
        print(f"Visor unificado: {outputs['viewer']}")
        print(f"Control de calidad: {outputs['qa']}")
        if "analysis_manifest" in outputs:
            print(f"Manifiesto del análisis: {outputs['analysis_manifest']}")
            print(f"Mapa de prioridad: {outputs['priority_map']}")
            print(f"Informe de conservación: {outputs['priority_report']}")
        return 0
    except KeyboardInterrupt:
        print("\nLa ejecución ha sido cancelada por la persona usuaria.", file=sys.stderr)
        return 130
    except Exception as exc:
        detail = translate_text(str(exc)).strip() or type(exc).__name__
        print(f"\nERROR: {detail}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return 1
