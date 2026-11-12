"""Command-line interface for users and automated runs."""

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
        description="Generates the complete Hispa-Syng v1.0 maps (Hippo-DEC project) and ecological analyses.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config", default="config.yaml", help="YAML configuration file."
    )
    parser.add_argument(
        "--project-root", help="Main folder containing the input data."
    )
    parser.add_argument(
        "--resource-root",
        help="Program folder containing manuals and resources for this edition.",
    )
    parser.add_argument(
        "--results-root",
        help="Shared folder where the execution results are stored.",
    )
    parser.add_argument(
        "--run-root",
        help="Exact folder for this run; used to coordinate both editions.",
    )
    parser.add_argument(
        "--execution-id",
        help="Common identifier of the bilingual run.",
    )
    parser.add_argument(
        "--language-code",
        help="Edition code being executed: ES or EN.",
    )
    parser.add_argument("--years", help="Period, for example 2017-2022, or 'all'.")
    parser.add_argument(
        "--grid", type=int, choices=[1, 5, 10], help="Grid resolution in kilometres."
    )
    parser.add_argument(
        "--region", help="all, cantabrica, sudatlantica, alboran, levantina or canarias."
    )
    parser.add_argument(
        "--species",
        action="append",
        help="Species; may be repeated or separated by commas.",
    )
    parser.add_argument(
        "--no-interactive", action="store_true", help="Do not ask interactive questions."
    )
    parser.add_argument(
        "--open-browser", action="store_true", help="Open HTML files after creation."
    )
    parser.add_argument(
        "--maps-only",
        action="store_true",
        help="Generate maps only and skip analytical blocks 8–21.",
    )
    parser.add_argument(
        "--permutations",
        type=int,
        help="Number of test permutations (production: 999; quick check: 49).",
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
        raise ValueError("The period must be written as YYYY-YYYY or 'all'.")
    start, end = map(int, parts)
    if not year_min <= start <= year_max:
        raise ValueError(
            f"The initial year must be between {year_min} and {year_max}."
        )
    if not year_min <= end <= year_max:
        raise ValueError(
            f"The final year must be between {year_min} and {year_max}."
        )
    if start > end:
        raise ValueError("The initial year cannot be later than the final year.")
    return start, end


def _interactive_parameters(
    summary: dict, defaults: dict
) -> tuple[int, int, int, str, tuple[str, ...]]:
    available_min = int(summary["available_year_min"])
    available_max = int(summary["available_year_max"])
    available_species = list(summary["available_species"])
    print(f"\nAvailable year range: {available_min}–{available_max}")
    years_default = defaults.get("years", "all")
    while True:
        entered = input(
            f"Period [All; configured value: {years_default}]: "
        ).strip()
        try:
            years = _parse_years(entered or years_default, available_min, available_max)
            break
        except ValueError as exc:
            print(f"Invalid option: {exc}")

    grid_default = int(defaults.get("grid_km", 10))
    while True:
        entered = input(
            f"Grid size: 1, 5 or 10 km [{grid_default}]: "
        ).strip() or str(grid_default)
        if entered in {"1", "5", "10"}:
            grid = int(entered)
            break
        print("Invalid option.")

    print(
        "\nMITECO marine subdivisions:\n 0 All\n 1 Northwestern Cantabrian\n 2 South Atlantic\n 3 Strait and Alboran\n 4 Levantine-Balearic\n 5 Canary Islands"
    )
    region_default = normalize_region(defaults.get("region", "all"))
    default_code = next(
        code for code, slug in REGION_MENU.items() if slug == region_default
    )
    while True:
        entered = input(f"Region 0–5 [{default_code}]: ").strip() or default_code
        try:
            region = normalize_region(entered)
            break
        except ValueError:
            print("Invalid option.")

    print("\nAvailable species:\n 0 All")
    for index, species in enumerate(available_species, 1):
        print(f" {index:2d} {species}")
    while True:
        entered = (
            input("Species by number (e.g. 1,3), or 0 for all [0]: ").strip()
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
            print("Invalid selection.")
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
                raise ValueError("--permutations must be at least 9.")
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
                raise ValueError("grid_km must be 1, 5 or 10.")
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
        print("\nRun completed successfully.")
        print(f"Unified viewer: {outputs['viewer']}")
        print(f"Quality control: {outputs['qa']}")
        if "analysis_manifest" in outputs:
            print(f"Analysis manifest: {outputs['analysis_manifest']}")
            print(f"Priority map: {outputs['priority_map']}")
            print(f"Conservation report: {outputs['priority_report']}")
        return 0
    except KeyboardInterrupt:
        print("\nRun cancelled by the user.", file=sys.stderr)
        return 130
    except Exception as exc:
        detail = translate_text(str(exc)).strip() or type(exc).__name__
        print(f"\nERROR: {detail}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return 1
