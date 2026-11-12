"""Build the static, upload-ready Hispa-Syng web publication package."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile

import geopandas as gpd
import numpy as np
import pandas as pd
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .localization import (
    translate_column_name,
    translate_frame,
    translate_geodataframe,
    translate_text,
)
from .output_policy import register_public_output, copy_public_registration, REGISTRY_NAME
from .maps import render_viewer, rewrite_language_switch


LOGGER = logging.getLogger("hippodec_maps")


PUBLICATION_NAME = "Web_Publication"
MARINE_DENSITY_FORMULA = "abundance / effective marine area (km²)"
NAVY = "16344C"
TEAL = "187F8C"
PALE_TEAL = "DDEFF1"
PALE_GOLD = "FFF3D0"
MID_GREY = "D5DEE3"


FIELD_DESCRIPTIONS = {
    "grid_id": "Stable internal identifier for the selected MITECO marine grid cell.",
    "official_cell_code": "Official cell code supplied by the MITECO grid layer.",
    "Area_mar_km2": "Effective marine area of the cell in square kilometres; land is excluded.",
    "Marine_area_km2": "Effective marine area of the cell in square kilometres; land is excluded.",
    "Density_per_marine_km2": "Abundance divided by effective marine area.",
    "Densidad_total": "Total density per km² of effective marine area.",
    "Densidad_ajustada": "Species density per km² of effective marine area.",
    "N_total_celda": "Sum of all individuals assigned to the cell.",
    "N_sum": "Sum of individuals for the species in the cell.",
    "n_especies": "Number of distinct species recorded in the cell.",
    "ecological_priority_score": "Relative conservation-priority index (0–100) integrating three explicit pathways: convergent biological evidence, a persistent occurrence core, and a diversity core. LCBD is retained as context and does not determine selection.",
    "ecological_priority_class": "Ecological-priority class derived from fixed thresholds and independent ecological families; it can be not evaluable or have no discriminatory capacity.",
    "monitoring_priority_score": "Independent temporal-monitoring priority index (0–100); it never modifies ecological priority.",
    "monitoring_priority_class": "Independent temporal-monitoring priority class.",
    "data_adequacy_score": "Data adequacy (0–100) based on real support from proxy events, years, scales and available coverage; it is not ecological evidence.",
    "data_adequacy_class": "Data-adequacy class independent of ecological priority.",
    "n_sampling_events": "Number of observation proxy events; this is a reproducible observation-intensity proxy, not measured sampling effort.",
    "sensitivity_class": "Stability of ecological priority under three weightings of the same independent families; temporal signal is not one of these scenarios.",
    "zone_id": "Identifier of a contiguous High or Very high priority area.",
    "pct_zone_protected": "Percentage of the priority area overlapping marine protected-area polygons.",
    "grid_assignment_status": "Whether a valid observation was assigned to the official MITECO marine grid; outside-grid records are retained for audit only.",
}


def _plain(frame: pd.DataFrame | gpd.GeoDataFrame | None) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    return pd.DataFrame(frame.drop(columns=["geometry"], errors="ignore")).copy()


def _cell_reference(occupied: gpd.GeoDataFrame) -> pd.DataFrame:
    columns = [
        column
        for column in (
            "grid_id",
            "official_cell_code",
            "Region_MITECO",
            "Area_mar_km2",
        )
        if column in occupied.columns
    ]
    return _plain(occupied[columns]).drop_duplicates("grid_id")


def _with_cell_reference(
    frame: pd.DataFrame, occupied: gpd.GeoDataFrame
) -> pd.DataFrame:
    table = _plain(frame)
    reference = _cell_reference(occupied)
    if "grid_id" not in table or reference.empty:
        return table
    missing = [
        column
        for column in reference.columns
        if column != "grid_id" and column not in table.columns
    ]
    return table.merge(reference[["grid_id", *missing]], on="grid_id", how="left")


def _density_tables(
    occupied: gpd.GeoDataFrame,
    species_metrics: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cells = _plain(occupied)
    if {"N_total_celda", "Area_mar_km2"}.issubset(cells.columns):
        area = pd.to_numeric(cells["Area_mar_km2"], errors="coerce")
        abundance = pd.to_numeric(cells["N_total_celda"], errors="coerce")
        recalculated_cells = pd.Series(
            np.where(area.gt(0), abundance / area, np.nan),
            index=cells.index,
            dtype=float,
        )
        existing_cells = pd.to_numeric(
            cells.get("Densidad_total", pd.Series(np.nan, index=cells.index)),
            errors="coerce",
        )
        comparable_cells = recalculated_cells.notna() & existing_cells.notna()
        if comparable_cells.any() and not np.allclose(
            recalculated_cells[comparable_cells],
            existing_cells[comparable_cells],
            rtol=1e-12,
            atol=1e-9,
        ):
            raise AssertionError(
                "A total cell-density value does not use the effective marine area."
            )
        cells["Density_per_marine_km2"] = recalculated_cells
        cells = cells.drop(columns="Densidad_total", errors="ignore")

    species = _with_cell_reference(species_metrics, occupied)
    if {"N_sum", "Area_mar_km2"}.issubset(species.columns):
        area = pd.to_numeric(species["Area_mar_km2"], errors="coerce")
        abundance = pd.to_numeric(species["N_sum"], errors="coerce")
        recalculated = pd.Series(
            np.where(area.gt(0), abundance / area, np.nan),
            index=species.index,
            dtype=float,
        )
        existing = pd.to_numeric(
            species.get("Densidad_ajustada", pd.Series(np.nan, index=species.index)),
            errors="coerce",
        )
        comparable = recalculated.notna() & existing.notna()
        if comparable.any() and not np.allclose(
            recalculated[comparable], existing[comparable], rtol=1e-12, atol=1e-9
        ):
            raise AssertionError(
                "A species-density value does not use the effective marine area."
            )
        species["Density_per_marine_km2"] = recalculated
        species = species.drop(columns="Densidad_ajustada", errors="ignore")
    return cells, species


def _metadata(context: dict[str, object]) -> pd.DataFrame:
    rows = [
        ("Product", context.get("brand_label", "Hispa-Syng v1.0")),
        ("Institution", context.get("institution", "")),
        ("Project", context.get("project", "Hippo-DEC")),
        ("Author", context.get("author", "")),
        ("Period", f"{context.get('year_min', '')}–{context.get('year_max', '')}"),
        ("Selected resolution", f"{context.get('grid_km', '')} × {context.get('grid_km', '')} km"),
        ("Selected area", context.get("region_label", "")),
        ("Creation date", context.get("creation_date", date.today().isoformat())),
        ("Density denominator", "Effective marine area of each cell; terrestrial area is excluded"),
        ("Density formula", MARINE_DENSITY_FORMULA),
    ]
    return pd.DataFrame(rows, columns=["Field", "Value"])


def _safe_value(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.to_pydatetime() if isinstance(value, pd.Timestamp) else value
    if isinstance(value, (list, tuple, set, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value if isinstance(value, (str, int, float, bool, datetime, date)) else str(value)


def _unique_sheet_name(raw: str, used: set[str]) -> str:
    forbidden = "\\/*?:[]"
    translated = translate_column_name(raw)
    candidate = "".join("_" if character in forbidden else character for character in translated)
    candidate = candidate[:31] or "Data"
    base = candidate
    suffix = 2
    while candidate.lower() in used:
        ending = f"_{suffix}"
        candidate = base[: 31 - len(ending)] + ending
        suffix += 1
    used.add(candidate.lower())
    return candidate


def _format_worksheet(worksheet, *, tabular: bool) -> None:
    worksheet.sheet_view.showGridLines = False
    worksheet.freeze_panes = "A2" if tabular else None
    worksheet.auto_filter.ref = worksheet.dimensions if tabular and worksheet.max_row > 1 else None
    worksheet.row_dimensions[1].height = 28
    for cell in worksheet[1]:
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    thin = Side(style="thin", color=MID_GREY)
    for row in worksheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin)
    for column_index in range(1, worksheet.max_column + 1):
        values = [worksheet.cell(row, column_index).value for row in range(1, min(worksheet.max_row, 250) + 1)]
        longest = max((len(str(value)) for value in values if value is not None), default=8)
        worksheet.column_dimensions[get_column_letter(column_index)].width = min(max(longest + 2, 11), 42)
    if tabular and worksheet.max_row > 1 and worksheet.max_column > 0:
        identifier = "Table_" + hashlib.sha1(worksheet.title.encode("utf-8")).hexdigest()[:10]
        table = Table(displayName=identifier, ref=worksheet.dimensions)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        worksheet.add_table(table)


def _write_excel(
    path: Path,
    title: str,
    context: dict[str, object],
    methodology: Iterable[str],
    datasets: dict[str, pd.DataFrame],
) -> Path:
    workbook = Workbook()
    workbook.remove(workbook.active)
    used: set[str] = set()

    readme = workbook.create_sheet(_unique_sheet_name("README", used))
    readme.append([title])
    readme.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
    readme["A1"].fill = PatternFill("solid", fgColor=TEAL)
    readme["A1"].font = Font(color="FFFFFF", bold=True, size=16)
    readme["A1"].alignment = Alignment(vertical="center")
    for row in _metadata(context).itertuples(index=False, name=None):
        readme.append([_safe_value(value) for value in row])
    readme.append([])
    readme.append(["How to use this workbook", "Each data sheet contains the complete exported information for the map. Filterable headers, frozen column names and typed numeric values are retained."])
    _format_worksheet(readme, tabular=False)
    readme.column_dimensions["A"].width = 28
    readme.column_dimensions["B"].width = 92

    method_sheet = workbook.create_sheet(_unique_sheet_name("Methodology", used))
    method_sheet.append(["Step", "Description"])
    for index, paragraph in enumerate(methodology, start=1):
        method_sheet.append([index, paragraph])
    _format_worksheet(method_sheet, tabular=True)
    method_sheet.column_dimensions["A"].width = 10
    method_sheet.column_dimensions["B"].width = 110

    dictionary_rows: list[list[object]] = []
    for dataset_name, source in datasets.items():
        for column in source.columns:
            dictionary_rows.append(
                [
                    dataset_name,
                    translate_column_name(str(column)),
                    FIELD_DESCRIPTIONS.get(str(column), "Exported analytical or source field; see the user manual and methodology sheet."),
                ]
            )
    dictionary_sheet = workbook.create_sheet(_unique_sheet_name("Data_dictionary", used))
    dictionary_sheet.append(["Dataset", "Field", "Meaning"])
    for row in dictionary_rows:
        dictionary_sheet.append(row)
    _format_worksheet(dictionary_sheet, tabular=True)
    dictionary_sheet.column_dimensions["A"].width = 28
    dictionary_sheet.column_dimensions["B"].width = 36
    dictionary_sheet.column_dimensions["C"].width = 86

    for raw_name, raw_frame in datasets.items():
        frame = translate_frame(_plain(raw_frame))
        worksheet = workbook.create_sheet(_unique_sheet_name(raw_name, used))
        headers = [str(column) for column in frame.columns]
        worksheet.append(headers or ["Information"])
        if headers:
            for row in frame.itertuples(index=False, name=None):
                worksheet.append([_safe_value(value) for value in row])
        _format_worksheet(worksheet, tabular=bool(headers))

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


def _data_dictionary(datasets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for dataset_name, source in datasets.items():
        for column in source.columns:
            rows.append(
                {
                    "dataset": dataset_name,
                    "field": translate_column_name(str(column)),
                    "meaning": FIELD_DESCRIPTIONS.get(
                        str(column),
                        "Exported analytical or source field; see the user manual and methodology.",
                    ),
                }
            )
    return pd.DataFrame(rows, columns=["dataset", "field", "meaning"])


def _package_safe_name(value: object, fallback: str = "dataset") -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return text or fallback


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value if value is None or isinstance(value, (str, int, float, bool)) else str(value)


def _write_data_package(
    path: Path,
    title: str,
    context: dict[str, object],
    methodology: Iterable[str],
    datasets: dict[str, pd.DataFrame],
    excel_path: Path,
    word_path: Path,
    geodata: dict[str, gpd.GeoDataFrame | None] | None = None,
) -> Path:
    """Write a portable data bundle alongside the Word and Excel products."""

    path.parent.mkdir(parents=True, exist_ok=True)
    # Build outside the publication tree.  A failed OS-level cleanup must not
    # leave a second, partial copy of a Word/Excel product beside the final
    # downloadable ZIP.
    with tempfile.TemporaryDirectory(prefix="hippodec_data_package_") as temporary:
        root = Path(temporary)
        (root / "documents").mkdir()
        (root / "data").mkdir()
        (root / "geodata").mkdir()
        shutil.copy2(excel_path, root / "documents" / excel_path.name)
        shutil.copy2(word_path, root / "documents" / word_path.name)

        translated_datasets: dict[str, pd.DataFrame] = {}
        for dataset_name, source in datasets.items():
            translated = translate_frame(_plain(source))
            translated_datasets[dataset_name] = translated
            csv_path = root / "data" / f"{_package_safe_name(dataset_name)}.csv"
            translated.to_csv(
                csv_path,
                sep=";",
                decimal=".",
                index=False,
                encoding="utf-8-sig",
                na_rep="",
            )
        _data_dictionary(datasets).to_csv(
            root / "data_dictionary.csv",
            sep=";",
            index=False,
            encoding="utf-8-sig",
        )

        geodata_manifest: list[str] = []
        for layer_name, frame in (geodata or {}).items():
            if frame is None or frame.empty or "geometry" not in frame:
                continue
            layer = _package_safe_name(layer_name, "layer")
            gpkg_path = root / "geodata" / f"{layer}.gpkg"
            translated_geo = translate_geodataframe(frame)
            translated_geo.to_file(
                gpkg_path,
                layer=layer[:60],
                driver="GPKG",
                engine="pyogrio",
            )
            geodata_manifest.append(f"geodata/{gpkg_path.name}:{layer[:60]}")

        package_context = {
            key: value
            for key, value in context.items()
            if key not in {"logo_uri", "map_downloads"}
        }
        (root / "parameters.json").write_text(
            json.dumps(
                {
                    "product": title,
                    "run_context": _json_safe(package_context),
                    "habitat_translation": {
                        "Arena": "Sand",
                        "Pradera marina": "Seagrass/Macroalgae",
                        "Rocas": "Rock",
                        "No determinado": "Undetermined",
                        "Antrópico": "Anthropogenic",
                        "Pelágico": "Pelagic",
                    },
                    "region_assignment_method": "Direct point-subdivision intersection first; if unavailable, fix the canonical region from the official 10-km MITECO reference grid, independently of analytical resolution.",
                    "out_of_marine_grid": "Map 1 includes valid records outside the official marine grid in a separate audit dataset; those records are not used in marine-cell density or regional analytical summaries.",
                    "density_formula": MARINE_DENSITY_FORMULA,
                    "geodata_layers": geodata_manifest,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        methodology_text = "\n".join(str(item) for item in methodology)
        (root / "methodology.txt").write_text(
            translate_text(
                "HISPA-SYNG v1.0 REUSABLE DATA PACKAGE (HIPPO-DEC PROJECT)\n\n"
                f"{title}\n\n"
                "Habitat values are translated only in English exports; the original workbook is not changed.\n"
                "CSV files use UTF-8 with BOM, semicolon separators and a dot decimal marker.\n"
                f"Marine density formula: {MARINE_DENSITY_FORMULA}\n"
                "The denominator is the effective marine area of each coastal cell; land is excluded.\n"
                "Regional assignment: direct MITECO subdivision intersection, then the official 10-km MITECO reference grid when direct assignment is missing, independently of analytical resolution.\n\n"
                "Map 1 includes a separate outside-marine-grid audit dataset when valid records cannot be assigned to an official marine cell; those records are not used in marine-cell density or regional analytical summaries.\n\n"
                + methodology_text
            ).rstrip()
            + "\n",
            encoding="utf-8",
        )
        readme = (
            "HISPA-SYNG v1.0 REUSABLE DATA PACKAGE (HIPPO-DEC PROJECT)\n\n"
            "This folder contains the complete map-specific Word and Excel products, reusable CSV data, a data dictionary, parameters, methodology and checksums.\n"
            "The original Spanish input workbook is read-only and is not included or modified. Habitat translations apply only to these English outputs.\n"
            "Map 1 includes valid records outside the official marine grid in a separate audit dataset when present; they are not treated as marine cells.\n"
            "GeoPackage layers are in geodata/ when source geometry is available.\n"
        )
        (root / "README.txt").write_text(readme, encoding="utf-8")

        records: list[dict[str, object]] = []
        for candidate in sorted(root.rglob("*")):
            if not candidate.is_file() or candidate.name == "manifest.json":
                continue
            records.append(
                {
                    "file": candidate.relative_to(root).as_posix(),
                    "bytes": candidate.stat().st_size,
                    "sha256": _sha256(candidate),
                }
            )
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "product": title,
                    "format": "Hispa-Syng v1.0 reusable data package (Hippo-DEC project)",
                    "files": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
            for candidate in sorted(root.rglob("*")):
                if candidate.is_file():
                    archive.write(candidate, candidate.relative_to(root).as_posix())
    return path


def _shade_word_cell(cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def _add_word_table(document: Document, frame: pd.DataFrame, key: str | None) -> None:
    table_frame = translate_frame(_plain(frame))
    if table_frame.empty:
        document.add_paragraph("No records were available for this dataset.")
        return
    columns = list(table_frame.columns)
    translated_key = translate_column_name(key) if key else None
    if translated_key not in columns:
        translated_key = columns[0]
    other = [column for column in columns if column != translated_key]
    chunks = [other[index : index + 6] for index in range(0, len(other), 6)] or [[]]
    for chunk_index, chunk in enumerate(chunks, start=1):
        selected = [translated_key, *chunk]
        if len(chunks) > 1:
            paragraph = document.add_paragraph(
                f"Field group {chunk_index} of {len(chunks)} — {len(table_frame):,} complete records"
            )
            paragraph.style = document.styles["Caption"]
        table = document.add_table(rows=1, cols=len(selected))
        table.style = "Table Grid"
        table.autofit = True
        for cell, label in zip(table.rows[0].cells, selected):
            cell.text = str(label)
            _shade_word_cell(cell, NAVY)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for run in cell.paragraphs[0].runs:
                run.font.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.font.size = Pt(7)
            cell.paragraphs[0].paragraph_format.keep_with_next = True
        header_properties = table.rows[0]._tr.get_or_add_trPr()
        repeat_header = OxmlElement("w:tblHeader")
        repeat_header.set(qn("w:val"), "true")
        header_properties.append(repeat_header)
        # Preserve every body row and field while relying on the document
        # Normal style and Table Grid style instead of restyling tens of
        # thousands of cells/runs individually. This removes a severe
        # python-docx bottleneck without changing exported values.
        for values in table_frame[selected].itertuples(index=False, name=None):
            cells = table.add_row().cells
            for cell, value in zip(cells, values):
                rendered = _safe_value(value)
                cell.text = "" if rendered is None else str(rendered)
        document.add_paragraph()


def _write_word(
    path: Path,
    title: str,
    context: dict[str, object],
    methodology: Iterable[str],
    datasets: dict[str, pd.DataFrame],
    logo: Path | None,
    keys: dict[str, str | None],
) -> Path:
    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    section.top_margin = Cm(1.4)
    section.bottom_margin = Cm(1.4)
    section.left_margin = Cm(1.4)
    section.right_margin = Cm(1.4)
    styles = document.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"].font.size = Pt(9)
    styles["Title"].font.name = "Georgia"
    styles["Title"].font.color.rgb = RGBColor(22, 52, 76)
    styles["Heading 1"].font.color.rgb = RGBColor(24, 127, 140)

    if logo and logo.exists():
        document.add_picture(str(logo), width=Cm(20))
    title_paragraph = document.add_paragraph(style="Title")
    title_paragraph.add_run(title)
    subtitle = document.add_paragraph(
        "Complete, human-readable download generated from the active Hispa-Syng v1.0 run (Hippo-DEC project)"
    )
    subtitle.alignment = WD_ALIGN_PARAGRAPH.LEFT

    document.add_heading("Run scope", level=1)
    metadata = _metadata(context)
    table = document.add_table(rows=0, cols=2)
    table.style = "Light Shading Accent 1"
    for field, value in metadata.itertuples(index=False, name=None):
        cells = table.add_row().cells
        cells[0].text = str(field)
        cells[1].text = "" if value is None else str(value)
        cells[0].paragraphs[0].runs[0].bold = True

    document.add_heading("Method and interpretation", level=1)
    for paragraph in methodology:
        document.add_paragraph(paragraph, style="List Bullet")
    note = document.add_paragraph()
    note.add_run("Marine-area rule. ").bold = True
    note.add_run(
        "All density values use the effective marine area of each MITECO cell. "
        "The terrestrial fraction of coastal cells is never included in the denominator."
    )

    document.add_heading("Complete information appendix", level=1)
    document.add_paragraph(
        "The following tables contain every exported record. Wide datasets are divided into field groups; the identifier in the first column is repeated so that groups can be joined without ambiguity. The accompanying Excel file contains the same information in filterable sheets."
    )
    for index, (dataset_name, frame) in enumerate(datasets.items()):
        document.add_heading(translate_text(dataset_name.replace("_", " ")), level=2)
        document.add_paragraph(
            f"Rows: {len(frame):,}. Fields: {len(_plain(frame).columns):,}."
        )
        _add_word_table(document, frame, keys.get(dataset_name))
        if index < len(datasets) - 1:
            document.add_page_break()

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Hispa-Syng v1.0 · Hippo-DEC project · Complete map information · Effective marine-area densities")
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_required(source: Path, destination: Path) -> Path:
    if not source.exists() or source.stat().st_size == 0:
        raise FileNotFoundError(f"Required publication file is missing or empty: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _publication_language_context(
    context: dict[str, object],
    published_maps: dict[str, Path],
) -> dict[str, object]:
    """Build language targets for the copied static publication tree."""

    value = context.get("language_switch")
    if not isinstance(value, dict) or not value.get("enabled"):
        return context
    roots = value.get("run_roots", {})
    names = value.get("names", {})
    if not isinstance(roots, dict) or not isinstance(names, dict):
        return context
    publication_names = {"ES": "Publicacion_Web", "EN": "Web_Publication"}
    map_folder_names = {"ES": "mapas", "EN": "maps"}
    targets: dict[str, dict[str, Path]] = {}
    for page in ("map1", "map2", "map3", "priority"):
        if page == "priority" and "priority" not in published_maps:
            continue
        targets[page] = {
            code: Path(str(roots[code]))
            / publication_names[code]
            / map_folder_names[code]
            / str(names[code][page])
            for code in ("ES", "EN")
        }
    targets["viewer"] = {
        code: Path(str(roots[code])) / publication_names[code] / "index.html"
        for code in ("ES", "EN")
    }
    updated = dict(value)
    updated["targets"] = targets
    output = dict(context)
    output["language_switch"] = updated
    return output


def build_web_publication(
    run_root: Path,
    context: dict[str, object],
    map_paths: dict[str, Path],
    master: pd.DataFrame,
    occupied: gpd.GeoDataFrame,
    species_metrics: pd.DataFrame,
    sex_metrics: pd.DataFrame,
    conservation: dict[str, Any] | None,
    logo: Path | None,
    manual_paths: Iterable[Path] = (),
    open_browser: bool = False,
    assigned: gpd.GeoDataFrame | None = None,
    outside_grid: gpd.GeoDataFrame | None = None,
) -> dict[str, Path]:
    """Create a static folder that can be uploaded without a Python service."""

    root = run_root / PUBLICATION_NAME
    maps_dir = root / "maps"
    downloads_dir = root / "downloads"
    documents_dir = root / "documents"
    for directory in (maps_dir, downloads_dir, documents_dir):
        directory.mkdir(parents=True, exist_ok=True)

    published_maps: dict[str, Path] = {}
    for key, source in map_paths.items():
        published_maps[key] = _copy_required(source, maps_dir / source.name)

    cells, species = _density_tables(occupied, species_metrics)
    sex = _with_cell_reference(sex_metrics, occupied)
    map1_datasets: dict[str, pd.DataFrame] = {"Observations": _plain(master)}
    map1_geodata: dict[str, gpd.GeoDataFrame | None] = {"observations": assigned}
    if outside_grid is not None:
        map1_datasets["Observations_outside_marine_grid"] = _plain(outside_grid)
        map1_geodata["observations_outside_marine_grid"] = outside_grid
    map_definitions: dict[str, dict[str, Any]] = {
        "map1": {
            "title": "Hispa-Syng v1.0 (Hippo-DEC project) — Map 1 — Complete observation information",
            "method": [
                "Each row in Observations represents a validated observation assigned to the official MITECO marine grid and retained for the marine analytical products.",
                "Observations_outside_marine_grid is included when valid filtered records could not be assigned to that official marine grid; these records are retained for audit and are not used in marine-cell density or regional analytical summaries.",
                "Source Id is retained only as metadata. Repeated Id values do not remove or merge records.",
                "Map symbols identify species and are sized from abundance and coincident records; original coordinates remain in the data.",
            ],
            "datasets": map1_datasets,
            "keys": {"Observations": "obs_id", "Observations_outside_marine_grid": "obs_id"},
            "geodata": map1_geodata,
        },
        "map2": {
            "title": "Hispa-Syng v1.0 (Hippo-DEC project) — Map 2 — Complete density information",
            "method": [
                "Observations are assigned to the selected MITECO marine grid resolution.",
                f"Cell and species densities use {MARINE_DENSITY_FORMULA}.",
                "The effective marine area excludes the terrestrial fraction of coastal cells; the official MITECO marine-cell geometry is used for display.",
                "Interactive species filtering recalculates abundance, density, richness, colours and pop-up contents.",
            ],
            "datasets": {"Cells": cells, "Species_by_cell": species},
            "keys": {"Cells": "grid_id", "Species_by_cell": "grid_id"},
            "geodata": {"occupied_cells": occupied},
        },
        "map3": {
            "title": "Hispa-Syng v1.0 (Hippo-DEC project) — Map 3 — Complete ecological-variable information",
            "method": [
                "The map combines richness, total abundance, total density, dominant species and sex-composition variables.",
                f"Total and species densities use {MARINE_DENSITY_FORMULA}.",
                "Sex metrics remain species-specific and include sample-size thresholds for responsible interpretation.",
                "The terrestrial fraction of every coastal cell is excluded from density denominators and display geometries.",
            ],
            "datasets": {
                "Cells": cells,
                "Species_by_cell": species,
                "Sex_by_species_and_cell": sex,
            },
            "keys": {
                "Cells": "grid_id",
                "Species_by_cell": "grid_id",
                "Sex_by_species_and_cell": "grid_id",
            },
            "geodata": {"occupied_cells": occupied},
        },
    }
    if conservation is not None and "priority" in published_maps:
        map_definitions["priority"] = {
            "title": "Hispa-Syng v1.0 (Hippo-DEC project) — Complete priority conservation-area information",
            "method": [
                "Conservation priority requires convergence among richness, temporal persistence, repeated use, and repeated representation of low-occupancy species; LCBD/hotspots are retained as context and never trigger selection by themselves.",
                "Strategic priority areas group High/Very-high planning units using rook contiguity (shared edge) and retain the scientific selection method. If a 1-km grid is requested, the viewer retains a separate 1-km descriptive-priority layer while strategic-area delineation uses 5-km planning units. Operational conservation areas are then generated from official MITECO 1-km cells containing observations inside each strategic area; only edge-sharing evidence cells are merged and empty cells are never added to connect separated concentrations. At 5 or 10 km, descriptive and planning resolutions coincide, while the operational footprint still uses the official 1-km multiscale grid.",
                "Priority cells and areas are clipped to the marine surface for display and protected-area overlap calculations.",
                "Only marine protected-area geometry is retained; area name, protection type and protection level are exported where available.",
                "Priority outputs support technical assessment and require field validation, expert review and applicable regulatory procedures.",
            ],
            "datasets": {
                "Priority_cells": _plain(conservation.get("priority_grid")),
                "Selected_priority_cells": _plain(conservation.get("selected_cells")),
                "Priority_areas": _plain(conservation.get("zone_summary")),
                "Marine_protected_areas": _plain(conservation.get("protected_areas")),
            },
            "keys": {
                "Priority_cells": "master_id",
                "Selected_priority_cells": "master_id",
                "Priority_areas": "zone_id",
                "Marine_protected_areas": "protected_name",
            },
            "geodata": {
                "priority_cells": conservation.get("priority_grid"),
                "selected_cells": conservation.get("selected_cells"),
                "priority_areas": conservation.get("zones"),
                "marine_protected_areas": conservation.get("protected_areas"),
            },
        }

    download_links: dict[str, dict[str, str]] = {}
    generated: dict[str, Path] = {}
    LOGGER.info("[Web publication] Preparing complete downloads for %d products", len(map_definitions))
    for key, definition in map_definitions.items():
        LOGGER.info("[Web publication] %s: Excel workbook", key)
        prefix = {
            "map1": "Map1_Complete_Information",
            "map2": "Map2_Complete_Information",
            "map3": "Map3_Complete_Information",
            "priority": "Priority_Conservation_Areas_Complete_Information",
        }[key]
        excel_path = _write_excel(
            downloads_dir / f"{prefix}.xlsx",
            definition["title"],
            context,
            definition["method"],
            definition["datasets"],
        )
        LOGGER.info("[Web publication] %s: Word document", key)
        if key == "priority":
            priority_report = Path(conservation.get("report", "")) if conservation else None
            if priority_report is None or not priority_report.exists():
                raise FileNotFoundError("The complete technical priority-areas report is missing.")
            word_path = _copy_required(
                priority_report, downloads_dir / priority_report.name
            )
        else:
            word_path = _write_word(
                downloads_dir / f"{prefix}.docx",
                definition["title"],
                context,
                definition["method"],
                definition["datasets"],
                logo,
                definition["keys"],
            )
        LOGGER.info("[Web publication] %s: data package", key)
        data_path = _write_data_package(
            downloads_dir / f"{prefix}_Data_Package.zip",
            definition["title"],
            context,
            definition["method"],
            definition["datasets"],
            excel_path,
            word_path,
            definition.get("geodata", {}),
        )
        LOGGER.info("[Web publication] %s: downloads completed", key)
        generated[f"{key}_excel"] = excel_path
        generated[f"{key}_word"] = word_path
        generated[f"{key}_data"] = data_path
        download_links[key] = {
            "excel": f"downloads/{excel_path.name}",
            "word": f"downloads/{word_path.name}",
            "data": f"downloads/{data_path.name}",
        }

    copied_manuals: list[Path] = []
    for manual in manual_paths:
        if manual.exists():
            copied_manuals.append(_copy_required(manual, documents_dir / manual.name))

    publication_context = _publication_language_context(context, published_maps)
    index = render_viewer(
        root / "index.html",
        f"maps/{published_maps['map1'].name}",
        f"maps/{published_maps['map2'].name}",
        f"maps/{published_maps['map3'].name}",
        f"maps/{published_maps['priority'].name}" if "priority" in published_maps else None,
        download_links,
        publication_context,
        open_browser,
    )

    # Published maps live one level below the publication root. Their source
    # maps were rendered in the run tree, so rewrite only the relative
    # download prefix after copying; the standalone run maps retain their own
    # valid links.
    for key, published_map in published_maps.items():
        text = published_map.read_text(encoding="utf-8")
        text = text.replace("../../Web_Publication/downloads/", "../downloads/")
        text = text.replace("../Web_Publication/downloads/", "../downloads/")
        published_map.write_text(text, encoding="utf-8")
        rewrite_language_switch(
            published_map,
            publication_context.get("language_switch"),
            published_map,
            key,
        )

    for key, published_map in published_maps.items():
        copy_public_registration(map_paths[key], published_map)

    upload_note = root / "README_UPLOAD.txt"
    upload_note.write_text(
        "HISPA-SYNG v1.0 WEB PUBLICATION (HIPPO-DEC PROJECT)\n\n"
        "This folder contains the English publication. Upload it in full to the institutional web server without changing its internal structure.\n"
        "To publish both languages from one self-contained folder, use Publicacion_Web_Bilingue_<id>, created by the bilingual coordinator under Results.\n"
        "Configure the server to publish index.html as the default document, then share the resulting URL.\n\n"
        "Required folders:\n"
        "- maps: four interactive HTML maps.\n"
        "- downloads: one complete Word file, one complete Excel file and one reusable data ZIP for each map.\n"
        "- documents: user manuals supplied with this v1.0 package.\n\n"
        "This is a static publication for non-sensitive products. In a protected project, Map 1 and controlled downloads are replaced after the run by encrypted .hse containers; open them from Hispa-Syng.bat > Security and access.\n"
        "If you deliberately publish a fully open copy, apply server-side authentication and authorization appropriate to the sensitivity of the data.\n"
        "The map vectors, interface, and Leaflet work from local files. The Satellite (Esri World Imagery), Marine bathymetry (EMODnet Bathymetry), and Physical (OpenTopoMap) basemaps are loaded online when the HTML opens. Satellite is active by default. All three require an Internet connection and require neither an API key nor a subscription.\n",
        encoding="utf-8",
    )

    manifest_records = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if path.name in {"manifest.json", REGISTRY_NAME}:
            continue
        manifest_records.append(
            {
                "file": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "product": "Hispa-Syng v1.0 Web Publication (Hippo-DEC project)",
                "created": datetime.now().isoformat(timespec="seconds"),
                "files": manifest_records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    register_public_output(upload_note, "upload_instructions")
    register_public_output(manifest, "integrity_manifest")
    generated.update(
        {
            "root": root,
            "index": index,
            "manifest": manifest,
            "upload_note": upload_note,
        }
    )
    if copied_manuals:
        generated["user_manual"] = copied_manuals[0]
    return generated
