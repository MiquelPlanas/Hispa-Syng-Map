"""Reading, cleaning, and filtering the observation database."""

from __future__ import annotations

import base64
import io
import os
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import RunParameters


REQUIRED_COLUMNS = (
    "Date of observation",
    "Species",
    "Latitude",
    "Longitude",
    "X",
    "Y",
    "EPSG",
    "N_total",
)

TEXT_OPTIONAL = ("Habitat", "Captura incidental", "Observer")
SEX_OPTIONAL = ("N hembra", "N macho", "N_indeterminado")
NUMERIC_EXPECTED = (
    "Depth",
    "Temperatura_gC",
    "N_total",
    "N hembra",
    "N macho",
    "N_indeterminado",
)

NA_TEXT = {"", "NA", "<NA>", "N/A", "na", "n/a", "NULL", "Null", "null"}

AUDITED_OPTIONAL_COLUMNS = (
    "Observer",
    "Habitat",
    "Captura incidental",
    "Depth",
    "Temperatura_gC",
    "N hembra",
    "N macho",
    "N_indeterminado",
)

SPECIES_WITH_AUTHORITY = {
    "Entelurus aequoreus": "Entelurus aequoreus (Linnaeus, 1758)",
    "Hippocampus algiricus": "Hippocampus algiricus Kaup, 1856",
    "Hippocampus guttulatus": "Hippocampus guttulatus Cuvier, 1829",
    "Hippocampus hippocampus": "Hippocampus hippocampus (Linnaeus, 1758)",
    "Minyichthys sentus": "Minyichthys sentus Dawson, 1982",
    "Nerophis lumbriciformis": "Nerophis lumbriciformis (Jenyns, 1835)",
    "Nerophis maculatus": "Nerophis maculatus Rafinesque, 1810",
    "Nerophis ophidion": "Nerophis ophidion (Linnaeus, 1758)",
    "Syngnathus acus": "Syngnathus acus Linnaeus, 1758",
    "Syngnathus phlegon": "Syngnathus phlegon Risso, 1827",
    "Syngnathus tenuirostris": "Syngnathus tenuirostris Rathke, 1837",
    "Syngnathus typhle": "Syngnathus typhle Linnaeus, 1758",
    "Syngnathus abaster": "Syngnathus abaster Risso, 1827",
    "Syngnathus rostellatus": "Syngnathus rostellatus Nilsson, 1855",
}


def _clean_text(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip()
    return values.mask(values.isin(NA_TEXT), pd.NA)


def to_numeric(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip().str.replace(",", ".", regex=False)
    values = values.mask(values.eq(""), pd.NA)
    return pd.to_numeric(values, errors="coerce")


def parse_dates(series: pd.Series) -> pd.Series:
    """Reproduce the R script's dmy priority, with ymd as a fallback."""
    already_dates = pd.to_datetime(
        series.where(~series.map(lambda x: isinstance(x, str))), errors="coerce"
    )
    text = series.astype("string").str.strip()
    parsed = pd.to_datetime(text, format="mixed", dayfirst=True, errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(
            text.loc[missing], format="mixed", yearfirst=True, errors="coerce"
        )
    return parsed.fillna(already_dates)


def audit_excel_input(data: pd.DataFrame) -> dict[str, object]:
    """Summarise coverage and detectable issues without altering source data."""

    fields: list[dict[str, object]] = []
    numeric_columns = set(NUMERIC_EXPECTED) | {
        "Latitude",
        "Longitude",
        "X",
        "Y",
        "EPSG",
    }
    audited = list(dict.fromkeys((*REQUIRED_COLUMNS, *AUDITED_OPTIONAL_COLUMNS)))
    for column in audited:
        present = column in data.columns
        non_empty = int(data[column].notna().sum()) if present else 0
        numeric_valid: int | None = None
        non_numeric: int | None = None
        if present and column in numeric_columns:
            parsed = to_numeric(data[column])
            numeric_valid = int(parsed.notna().sum())
            non_numeric = int((data[column].notna() & parsed.isna()).sum())
        fields.append(
            {
                "field": column,
                "required": column in REQUIRED_COLUMNS,
                "present": present,
                "non_empty": non_empty,
                "missing": int(len(data) - non_empty),
                "numeric_valid": numeric_valid,
                "non_numeric": non_numeric,
            }
        )

    depth_ranges: dict[str, int] = {}
    if "Depth" in data.columns:
        depth_numeric = to_numeric(data["Depth"])
        invalid_depth = (
            data.loc[data["Depth"].notna() & depth_numeric.isna(), "Depth"]
            .astype("string")
            .str.strip()
        )
        depth_ranges = {
            str(value): int(count)
            for value, count in invalid_depth.value_counts().items()
        }

    n_total_missing = 0
    sex_total_mismatch = 0
    if "N_total" in data.columns:
        total = to_numeric(data["N_total"])
        n_total_missing = int(total.isna().sum())
        if all(column in data.columns for column in SEX_OPTIONAL):
            sexes = pd.concat(
                [to_numeric(data[column]).rename(column) for column in SEX_OPTIONAL],
                axis=1,
            )
            sex_sum = sexes.sum(axis=1, min_count=3)
            comparable = total.notna() & sexes.notna().all(axis=1)
            sex_total_mismatch = int(
                (~np.isclose(total[comparable], sex_sum[comparable])).sum()
            )

    warnings: list[str] = []
    if depth_ranges:
        warnings.append(
            f"{sum(depth_ranges.values())} Depth values are non-numeric and are excluded from depth analyses."
        )
    if n_total_missing:
        warnings.append(
            f"{n_total_missing} rows have an empty N_total; they contribute record effort/presence but zero abundance to sums."
        )
    if sex_total_mismatch:
        warnings.append(
            f"{sex_total_mismatch} rows differ between N_total and the sum of females, males, and indeterminate individuals."
        )
    return {
        "rows": int(len(data)),
        "required_columns_complete": all(
            column in data.columns for column in REQUIRED_COLUMNS
        ),
        "fields": fields,
        "depth_non_numeric_values": depth_ranges,
        "n_total_missing": n_total_missing,
        "sex_total_mismatch_rows": sex_total_mismatch,
        "warnings": warnings,
    }


def _encrypted_input_bytes(path: Path) -> bytes:
    from struct import unpack
    import hashlib
    import json

    magic = b"HISPA-HSE1\n"
    blob = Path(path).read_bytes()
    if not blob.startswith(magic):
        raise ValueError("El archivo cifrado de entrada no tiene un formato Hispa-Syng válido.")
    raw_key = os.environ.get("HISPA_SYNG_PROJECT_KEY_B64")
    expected_project = os.environ.get("HISPA_SYNG_PROJECT_ID")
    if not raw_key or not expected_project:
        raise PermissionError("El proyecto está protegido. Abra Hispa-Syng desde Hispa-Syng.bat y autorice el acceso antes de ejecutar el análisis.")
    try:
        key = base64.urlsafe_b64decode(raw_key.encode("ascii"))
        offset = len(magic)
        header_len = unpack(">I", blob[offset:offset+4])[0]
        start = offset + 4
        end = start + header_len
        header = json.loads(blob[start:end].decode("utf-8"))
        if header.get("project_id") != expected_project:
            raise PermissionError("El archivo cifrado pertenece a otro proyecto Hispa-Syng.")
        nonce = base64.urlsafe_b64decode(header["nonce_b64"].encode("ascii"))
        aad = f"Hispa-Syng|file|{header['project_id']}|v1|{header['original_name']}".encode("utf-8")
        plain = AESGCM(key).decrypt(nonce, blob[end:], aad)
        if hashlib.sha256(plain).hexdigest() != header.get("sha256"):
            raise ValueError("La integridad del archivo cifrado de entrada no es válida.")
        return plain
    except PermissionError:
        raise
    except Exception as exc:
        raise PermissionError("No se ha podido descifrar la entrada protegida del proyecto.") from exc


def read_and_clean_excel(
    path: Path, sheet: str
) -> tuple[pd.DataFrame, dict[str, object]]:
    if Path(path).suffix.lower() == ".hse":
        workbook = pd.ExcelFile(io.BytesIO(_encrypted_input_bytes(Path(path))), engine="openpyxl")
    else:
        workbook = pd.ExcelFile(path, engine="openpyxl")
    if sheet not in workbook.sheet_names:
        raise ValueError(
            f"Worksheet {sheet!r} does not exist. Available worksheets: {', '.join(workbook.sheet_names)}"
        )
    data = pd.read_excel(workbook, sheet_name=sheet)
    input_audit = audit_excel_input(data)
    missing = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"Required columns are missing: {', '.join(missing)}")

    for column in TEXT_OPTIONAL:
        if column not in data.columns:
            data[column] = pd.NA
    for column in SEX_OPTIONAL:
        if column not in data.columns:
            data[column] = np.nan
    for column in NUMERIC_EXPECTED:
        if column not in data.columns:
            data[column] = np.nan

    numeric_columns = set(NUMERIC_EXPECTED) | {
        "Latitude",
        "Longitude",
        "X",
        "Y",
        "EPSG",
    }
    for column in data.columns:
        if column not in numeric_columns and (
            pd.api.types.is_object_dtype(data[column])
            or pd.api.types.is_string_dtype(data[column])
        ):
            data[column] = _clean_text(data[column])
    for column in numeric_columns:
        if column in data.columns:
            data[column] = to_numeric(data[column])

    data["Fecha_aux"] = parse_dates(data["Date of observation"])
    data["source_row"] = np.arange(2, len(data) + 2, dtype=int)
    years = sorted(int(year) for year in data["Fecha_aux"].dt.year.dropna().unique())
    species = sorted(data["Species"].dropna().astype(str).str.strip().unique().tolist())
    if not years:
        raise ValueError(
            "No valid date could be interpreted in 'Date of observation'."
        )
    if not species:
        raise ValueError("No valid species was found in 'Species'.")
    summary = {
        "rows_read": int(len(data)),
        "columns_read": int(len(data.columns) - 2),
        "available_year_min": min(years),
        "available_year_max": max(years),
        "available_species": species,
        "invalid_dates": int(data["Fecha_aux"].isna().sum()),
        "input_audit": input_audit,
    }
    return data, summary


def species_without_authority(value: object) -> str:
    text = str(value).strip()
    text = re.sub(r"\s*\([^)]*\)", "", text)
    parts = text.split()
    return " ".join(parts[:2]) if len(parts) >= 2 else text


def abbreviate_species(value: object) -> str:
    clean = species_without_authority(value)
    parts = clean.split()
    return f"{parts[0][0]}. {parts[1]}" if len(parts) >= 2 else clean


def add_species_authorities(data: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    out["Species_raw"] = out["Species"].astype("string")
    out["Species"] = (
        out["Species_raw"].map(SPECIES_WITH_AUTHORITY).fillna(out["Species_raw"])
    )
    out["Species_clean"] = out["Species"].map(species_without_authority)
    out["Species_short"] = out["Species"].map(abbreviate_species)
    return out


def filter_observations(
    data: pd.DataFrame, params: RunParameters
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    counts: dict[str, int] = {"rows_initial": int(len(data))}
    selected = data[data["Species"].isin(params.species_raw)].copy()
    counts["rows_after_species"] = int(len(selected))
    if selected.empty:
        raise ValueError("No records remain after the species filter.")

    years = selected["Fecha_aux"].dt.year
    selected = selected[
        selected["Fecha_aux"].notna() & years.between(params.year_min, params.year_max)
    ].copy()
    counts["rows_after_years"] = int(len(selected))
    if selected.empty:
        raise ValueError("No records remain after the temporal filter.")

    basic_geo = selected[
        selected["Longitude"].notna() & selected["Latitude"].notna()
    ].copy()
    counts["rows_with_basic_geography"] = int(len(basic_geo))

    valid = (
        basic_geo["Latitude"].between(27, 44)
        & basic_geo["Longitude"].between(-18, 5)
        & basic_geo["X"].notna()
        & basic_geo["Y"].notna()
        & basic_geo["EPSG"].notna()
    )
    discarded = basic_geo.loc[~valid].copy()
    selected = basic_geo.loc[valid].copy()
    selected["EPSG"] = selected["EPSG"].astype(int)
    counts["rows_invalid_coordinates"] = int(len(discarded))
    counts["rows_after_coordinate_validation"] = int(len(selected))
    if selected.empty:
        raise ValueError("No records with complete and plausible coordinates remain.")
    return selected, discarded, counts


def parse_species_argument(value: object, available: Iterable[str]) -> tuple[str, ...]:
    available_list = list(available)
    if value is None:
        return tuple(available_list)
    items = value if isinstance(value, (list, tuple)) else [value]
    names = sorted(available_list, key=len, reverse=True)
    pieces: list[str] = []
    for item in items:
        remaining = str(item).strip()
        while remaining:
            # Match complete workbook names before treating commas as list
            # separators: taxonomic authorities can themselves contain commas.
            matched = None
            for name in names:
                if remaining.startswith(name):
                    tail = remaining[len(name):].lstrip()
                    if not tail or tail[0] in ",;":
                        matched = name
                        break
            if matched is not None:
                pieces.append(matched)
                remaining = remaining[len(matched):].lstrip(",; \t\r\n")
            else:
                parts = re.split(r"[,;]", remaining, maxsplit=1)
                pieces.append(parts[0])
                remaining = parts[1].strip() if len(parts) > 1 else ""
    selected = tuple(dict.fromkeys(piece.strip() for piece in pieces if piece.strip()))
    # argparse uses action='append' for --species, so ``--species all`` arrives
    # as ['all']. Accept the documented/configured all-species tokens in both
    # scalar and list form; ``0`` is also the root-launcher convention.
    if any(piece.casefold() in {"all", "todos", "todas", "0"} for piece in selected):
        return tuple(available_list)
    unknown = [species for species in selected if species not in available_list]
    if unknown:
        raise ValueError("Unrecognised species: " + " | ".join(unknown))
    return selected
