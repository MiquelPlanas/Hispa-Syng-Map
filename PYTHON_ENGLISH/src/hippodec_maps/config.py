"""Configuration, paths, and execution parameters."""

from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "paths": {
        "input_excel": "auto",
        "sheet": "BD depurada",
        "grids": "auto",
        "gshhg": "auto",
        "demarcations": "auto",
        "logo": "auto",
        "protected_areas": "auto",
        "traits": "auto",
        "results": "Results",
    },
    "execution": {
        "interactive": True,
        "years": "all",
        "grid_km": 10,
        "region": "all",
        "species": "all",
        "open_browser": False,
        "maps_only": False,
    },
    "spatial": {
        "target_crs": 3035,
        "nearest_tolerance_factor": 1.0,
        "clip_land_with_gshhg": True,
        "grid_bbox_buffer_factor": 1.25,
    },
    "maps": {
        "initial_basemap": "satellite",
        "simplify_cells_m": 0,
        "simplify_boundaries_m": 100,
        "simplify_coast_m": 200,
    },
    "analysis": {
        "permutations": 999,
        "random_seed": 20260501,
        "bootstrap_iterations": 1000,
        "min_records_cell": 2,
        "coastal_threshold_km": 10.0,
        "similarity_threshold": 0.55,
        "temporal_periods": [
            {"label": "2017–2022", "start": "2017-01-01", "end": "2022-12-31"},
            {"label": "2023–2026", "start": "2023-01-01", "end": "2026-12-31"},
        ],
    },
}


REGIONS: dict[str, dict[str, str]] = {
    "all": {"label": "All marine subdivisions (MITECO)", "tag": "all"},
    "cantabrica": {"label": "North-western Cantabrian subregion", "tag": "cantabrian"},
    "sudatlantica": {"label": "South Atlantic subregion", "tag": "south_atlantic"},
    "alboran": {"label": "Strait of Gibraltar and Alboran Sea", "tag": "alboran"},
    "levantina": {"label": "Levantine-Balearic subregion", "tag": "levantine_balearic"},
    "canarias": {"label": "Canary Islands", "tag": "canary_islands"},
}

REGION_MENU = {
    "0": "all",
    "1": "cantabrica",
    "2": "sudatlantica",
    "3": "alboran",
    "4": "levantina",
    "5": "canarias",
}


@dataclass(frozen=True)
class RunParameters:
    year_min: int
    year_max: int
    grid_km: int
    region: str
    species_raw: tuple[str, ...]
    open_browser: bool = False
    execution_id: str | None = None
    language_code: str | None = None

    @property
    def year_tag(self) -> str:
        return f"{self.year_min}-{self.year_max}"

    @property
    def region_label(self) -> str:
        return REGIONS[self.region]["label"]


def _merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError("config.yaml must contain a YAML mapping.")
    return _merge(DEFAULT_CONFIG, loaded)


def ascii_slug(value: object) -> str:
    text = (
        unicodedata.normalize("NFKD", str(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return re.sub(r"_+", "_", text)


def taxon_slug(value: object) -> str:
    """Compact filename component retaining genus and specific epithet."""

    parts = ascii_slug(value).split("_")
    return "_".join(parts[:2]) if len(parts) >= 2 else "_".join(parts)


def normalize_region(value: object) -> str:
    text = ascii_slug(value)
    if text in {"", "all", "todas", "toda", "todo", "0"}:
        return "all"
    if text in REGION_MENU:
        return REGION_MENU[text]
    if any(
        token in text for token in ("cantabr", "norocc", "noratlant", "north_atlantic")
    ):
        return "cantabrica"
    if any(token in text for token in ("sudatl", "south_atlantic")):
        return "sudatlantica"
    if any(token in text for token in ("estrecho", "gibraltar", "albor", "straigh")):
        return "alboran"
    if any(token in text for token in ("levant", "balear", "penbal")):
        return "levantina"
    if any(token in text for token in ("canaria", "canary", "dm_can")):
        return "canarias"
    raise ValueError(f"Unrecognized region: {value!r}")


def _is_ignored(path: Path) -> bool:
    ignored = {".venv", ".git", "Results", ".cache", "__pycache__"}
    return any(part in ignored or part.startswith("run_") for part in path.parts)


def _find_first(
    root: Path, patterns: list[str], *, want_dir: bool = False
) -> Path | None:
    for pattern in patterns:
        valid = [
            path
            for path in root.rglob(pattern)
            if (path.is_dir() if want_dir else path.is_file())
            and not _is_ignored(path.relative_to(root))
        ]
        if valid:
            return sorted(
                set(valid), key=lambda path: (len(path.parts), str(path).casefold())
            )[0]
    return None


def resolve_input_paths(
    project_root: Path, config: dict[str, Any]
) -> dict[str, Path | str | None]:
    paths = config["paths"]
    resources_dir = project_root / "Resources"

    def explicit_or_auto(
        key: str, patterns: list[str], *, want_dir: bool = False
    ) -> Path | None:
        raw = paths.get(key, "auto")
        if raw not in (None, "", "auto"):
            candidate = Path(str(raw)).expanduser()
            if not candidate.is_absolute():
                candidate = project_root / candidate
            candidate = candidate.resolve()
            if not candidate.exists():
                raise FileNotFoundError(
                    f"The configured path for '{key}' does not exist: {candidate}"
                )
            return candidate
        return _find_first(project_root, patterns, want_dir=want_dir)

    raw_input = paths.get("input_excel", "auto")
    if raw_input in (None, "", "auto"):
        data_dir = project_root / "Datos_data"
        exact_input = data_dir / "Ingesta_provisional.xlsx"
        encrypted_input = data_dir / "Ingesta_provisional.hse"
        if exact_input.is_file():
            excel = exact_input.resolve()
        elif encrypted_input.is_file():
            excel = encrypted_input.resolve()
        else:
            variants = sorted(data_dir.glob("Ingesta_provisional*.xlsx")) if data_dir.is_dir() else []
            if not variants and data_dir.is_dir():
                variants = sorted(data_dir.glob("Ingesta_provisional*.hse"))
            excel = variants[0].resolve() if variants else None
    else:
        excel = explicit_or_auto(
            "input_excel", ["Ingesta_provisional.xlsx", "Ingesta_provisional*.xlsx", "Ingesta_provisional.hse"]
        )
    if excel is None:
        raise FileNotFoundError(
            "Ingesta_provisional.xlsx (or a filename variant) was not found."
        )

    raw_grids = paths.get("grids", "auto")
    grid_dir = None
    grid_zip = None
    if raw_grids in (None, "", "auto"):
        native_grid_dir = resources_dir / "Mallas_marinas_MITECO"
        native_grid_zip = resources_dir / "Mallas_marinas_MITECO.zip"
        if native_grid_dir.is_dir():
            grid_dir = native_grid_dir.resolve()
        elif native_grid_zip.is_file():
            grid_zip = native_grid_zip.resolve()
        else:
            grid_dir = _find_first(project_root, ["Mallas_marinas_MITECO"], want_dir=True)
            if grid_dir is None:
                grid_zip = _find_first(project_root, ["Mallas_marinas_MITECO*.zip"])
    else:
        candidate = Path(str(raw_grids)).expanduser()
        if not candidate.is_absolute():
            candidate = project_root / candidate
        candidate = candidate.resolve()
        if not candidate.exists():
            raise FileNotFoundError(
                f"The configured path for 'grids' does not exist: {candidate}"
            )
        if candidate.is_dir():
            grid_dir = candidate
        elif candidate.suffix.lower() == ".zip":
            grid_zip = candidate
        else:
            raise FileNotFoundError(
                f"The configured path for 'grids' is neither a folder nor a ZIP file: {candidate}"
            )
    grids = grid_dir or grid_zip
    if grids is None:
        raise FileNotFoundError(
            "Neither the Mallas_marinas_MITECO folder nor ZIP file was found."
        )

    native_gshhg = resources_dir / "GSHHS" / "GSHHS_h_L1.shp"
    gshhg = (
        native_gshhg.resolve()
        if paths.get("gshhg", "auto") in (None, "", "auto") and native_gshhg.is_file()
        else explicit_or_auto("gshhg", ["GSHHS_h_L1.shp", "GSHHS*.zip"])
    )
    native_demarc = resources_dir / "demarcaciones_miteco" / "Demarcaciones_Marinas_20220909_ModeloDatosINSPIRE.shp"
    demarc = (
        native_demarc.resolve()
        if paths.get("demarcations", "auto") in (None, "", "auto") and native_demarc.is_file()
        else explicit_or_auto(
            "demarcations", ["Demarcaciones_Marinas_20220909_ModeloDatosINSPIRE.shp"]
        )
    )
    # Distribution resources are deliberately looked up in the extracted
    # package root first. This keeps the installation portable even when the
    # parent folder is moved or renamed.
    root_logo_candidates = [
        project_root / name
        for name in ("logos.png", "Logos.png", "logos.jpg", "logos.jpeg", "Logos.jpg", "Logos.jpeg")
    ]
    logo = next((path.resolve() for path in root_logo_candidates if path.is_file()), None)
    if logo is None:
        logo = explicit_or_auto("logo", ["[Ll]ogos*.jpg", "[Ll]ogos*.jpeg", "[Ll]ogos*.png"])
    native_protected = resources_dir / "areas_protegidas"
    if paths.get("protected_areas", "auto") in (None, "", "auto") and native_protected.is_dir():
        protected = native_protected.resolve()
    else:
        protected = explicit_or_auto(
            "protected_areas",
            ["areas_protegidas", "Areas_protegidas", "Áreas_protegidas"],
            want_dir=True,
        )
        if protected is None:
            protected = explicit_or_auto(
                "protected_areas",
                ["*areas*protegidas*.gpkg", "*areas*protegidas*.shp"],
            )
    data_traits = project_root / "Datos_data" / "traits.xlsx"
    traits = data_traits.resolve() if data_traits.is_file() else explicit_or_auto(
        "traits",
        ["*rasgos*.xlsx", "*rasgos*.csv", "*traits*.xlsx", "*traits*.csv"],
    )
    # GSHHS is required: the official MITECO grid is retained for observation
    # assignment, while GSHHS removes land from every cell and determines the
    # marine area used by densities and maps.
    if gshhg is None:
        raise FileNotFoundError(
            "Neither GSHHS_h_L1.shp nor GSHHS.zip was found. GSHHS is required to calculate the actual marine surface used by densities and clip maps."
        )
    if demarc is None:
        raise FileNotFoundError(
            "The MITECO marine-subdivision shapefile was not found."
        )

    results_raw = Path(str(paths.get("results", "Results")))
    results = results_raw if results_raw.is_absolute() else project_root / results_raw
    return {
        "excel": excel,
        "sheet": str(paths.get("sheet", "BD depurada")),
        "grids": grids,
        "gshhg": gshhg,
        "demarcations": demarc,
        "logo": logo,
        "protected_areas": protected,
        "traits": traits,
        "results": results.resolve(),
    }
