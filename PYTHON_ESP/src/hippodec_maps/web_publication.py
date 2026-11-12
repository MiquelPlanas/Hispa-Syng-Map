"""Construye el paquete web estático de Hispa-Syng listo para publicar."""

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


PUBLICATION_NAME = "Publicacion_Web"
MARINE_DENSITY_FORMULA = "abundancia / área marina efectiva (km²)"
NAVY = "16344C"
TEAL = "187F8C"
PALE_TEAL = "DDEFF1"
PALE_GOLD = "FFF3D0"
MID_GREY = "D5DEE3"


FIELD_DESCRIPTIONS = {
    "grid_id": "Identificador interno estable de la celda de la malla marina MITECO seleccionada.",
    "official_cell_code": "Código oficial de celda suministrado por la capa de malla MITECO.",
    "Area_mar_km2": "Área marina efectiva de la celda en kilómetros cuadrados; se excluye la tierra.",
    "Marine_area_km2": "Área marina efectiva de la celda en kilómetros cuadrados; se excluye la tierra.",
    "Density_per_marine_km2": "Abundancia dividida por el área marina efectiva.",
    "Densidad_total": "Densidad total por km² de área marina efectiva.",
    "Densidad_ajustada": "Densidad de la especie por km² de área marina efectiva.",
    "N_total_celda": "Suma de todos los individuos asignados a la celda.",
    "N_sum": "Suma de individuos de la especie en la celda.",
    "n_especies": "Número de especies distintas registradas en la celda.",
    "ecological_priority_score": "Índice relativo de prioridad de conservación (0–100) que integra tres vías explícitas: convergencia de evidencia biológica, núcleo de presencia persistente y núcleo de diversidad. LCBD se conserva como contexto y no determina la selección.",
    "ecological_priority_class": "Clase de prioridad ecológica derivada de umbrales fijos y de familias ecológicas independientes; puede ser no evaluable o sin capacidad de discriminación.",
    "monitoring_priority_score": "Índice independiente de prioridad de seguimiento temporal (0–100); no modifica la prioridad ecológica.",
    "monitoring_priority_class": "Clase independiente de prioridad de seguimiento temporal.",
    "data_adequacy_score": "Suficiencia de datos (0–100) basada en soporte real de eventos proxy, años, escalas y coberturas disponibles; no es evidencia ecológica.",
    "data_adequacy_class": "Clase de suficiencia de datos independiente de la prioridad ecológica.",
    "n_sampling_events": "Número de eventos proxy de observación; es un proxy reproducible de intensidad de observación y no esfuerzo de muestreo medido.",
    "sensitivity_class": "Estabilidad de la prioridad ecológica frente a tres ponderaciones de las mismas familias independientes; la señal temporal no forma parte de estos escenarios.",
    "zone_id": "Identificador de una zona contigua de prioridad alta o muy alta.",
    "pct_zone_protected": "Porcentaje de la zona prioritaria solapado con polígonos de áreas protegidas marinas.",
    "grid_assignment_status": "Indica si una observación válida se asignó a la malla marina oficial MITECO; los registros fuera de la malla se conservan solo para auditoría.",
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
                "Un valor de densidad total de celda no utiliza el área marina efectiva."
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
                "Un valor de densidad de especie no utiliza el área marina efectiva."
            )
        species["Density_per_marine_km2"] = recalculated
        species = species.drop(columns="Densidad_ajustada", errors="ignore")
    return cells, species


def _metadata(context: dict[str, object]) -> pd.DataFrame:
    rows = [
        ("Producto", context.get("brand_label", "Hispa-Syng v1.0")),
        ("Institución", context.get("institution", "")),
        ("Proyecto", context.get("project", "Hippo-DEC")),
        ("Autoría", context.get("author", "")),
        ("Periodo", f"{context.get('year_min', '')}–{context.get('year_max', '')}"),
        ("Resolución seleccionada", f"{context.get('grid_km', '')} × {context.get('grid_km', '')} km"),
        ("Área seleccionada", context.get("region_label", "")),
        ("Fecha de creación", context.get("creation_date", date.today().isoformat())),
        ("Denominador de densidad", "Área marina efectiva de cada celda; se excluye la superficie terrestre"),
        ("Fórmula de densidad", MARINE_DENSITY_FORMULA),
    ]
    return pd.DataFrame(rows, columns=["Campo", "Valor"])


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
    candidate = candidate[:31] or "Datos"
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
        identifier = "Tabla_" + hashlib.sha1(worksheet.title.encode("utf-8")).hexdigest()[:10]
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

    readme = workbook.create_sheet(_unique_sheet_name("LEEME", used))
    readme.append([title])
    readme.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
    readme["A1"].fill = PatternFill("solid", fgColor=TEAL)
    readme["A1"].font = Font(color="FFFFFF", bold=True, size=16)
    readme["A1"].alignment = Alignment(vertical="center")
    for row in _metadata(context).itertuples(index=False, name=None):
        readme.append([_safe_value(value) for value in row])
    readme.append([])
    readme.append(["Cómo utilizar este libro", "Cada hoja de datos contiene la información completa exportada para el mapa. Se conservan las cabeceras filtrables, los nombres de columna inmovilizados y los valores numéricos tipados."])
    _format_worksheet(readme, tabular=False)
    readme.column_dimensions["A"].width = 28
    readme.column_dimensions["B"].width = 92

    method_sheet = workbook.create_sheet(_unique_sheet_name("Metodologia", used))
    method_sheet.append(["Paso", "Descripción"])
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
                    FIELD_DESCRIPTIONS.get(str(column), "Campo analítico o de origen exportado; consulte el manual de usuario y la hoja de metodología."),
                ]
            )
    dictionary_sheet = workbook.create_sheet(_unique_sheet_name("Diccionario_datos", used))
    dictionary_sheet.append(["Conjunto de datos", "Campo", "Significado"])
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
        worksheet.append(headers or ["Información"])
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
                        "Campo analítico o de origen exportado; consulte el manual de usuario y la metodología.",
                    ),
                }
            )
    return pd.DataFrame(rows, columns=["conjunto_datos", "campo", "significado"])


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
    """Escribe un paquete de datos portable junto a los productos Word y Excel."""

    path.parent.mkdir(parents=True, exist_ok=True)
    # Construye fuera del árbol de publicación. Una limpieza del sistema
    # operativo que falle no debe dejar una segunda copia parcial de Word o
    # Excel junto al ZIP descargable final.
    with tempfile.TemporaryDirectory(prefix="hippodec_data_package_") as temporary:
        root = Path(temporary)
        (root / "documentos").mkdir()
        (root / "datos").mkdir()
        (root / "geodatos").mkdir()
        shutil.copy2(excel_path, root / "documentos" / excel_path.name)
        shutil.copy2(word_path, root / "documentos" / word_path.name)

        translated_datasets: dict[str, pd.DataFrame] = {}
        for dataset_name, source in datasets.items():
            translated = translate_frame(_plain(source))
            translated_datasets[dataset_name] = translated
            csv_path = root / "datos" / f"{_package_safe_name(dataset_name)}.csv"
            translated.to_csv(
                csv_path,
                sep=";",
                decimal=".",
                index=False,
                encoding="utf-8-sig",
                na_rep="",
            )
        translate_frame(_data_dictionary(datasets)).to_csv(
            root / "diccionario_datos.csv",
            sep=";",
            index=False,
            encoding="utf-8-sig",
        )

        geodata_manifest: list[str] = []
        for layer_name, frame in (geodata or {}).items():
            if frame is None or frame.empty or "geometry" not in frame:
                continue
            layer = _package_safe_name(layer_name, "layer")
            gpkg_path = root / "geodatos" / f"{layer}.gpkg"
            translated_geo = translate_geodataframe(frame)
            translated_geo.to_file(
                gpkg_path,
                layer=layer[:60],
                driver="GPKG",
                engine="pyogrio",
            )
            geodata_manifest.append(f"geodatos/{gpkg_path.name}:{layer[:60]}")

        package_context = {
            key: value
            for key, value in context.items()
            if key not in {"logo_uri", "map_downloads"}
        }
        (root / "parametros.json").write_text(
            json.dumps(
                {
                    "product": title,
                    "run_context": _json_safe(package_context),
                    "habitat_translation": {
                        "Arena": "Arena",
                        "Pradera marina": "Pradera marina",
                        "Rocas": "Rocas",
                        "No determinado": "No determinado",
                        "Antrópico": "Antrópico",
                        "Pelágico": "Pelágico",
                    },
                    "region_assignment_method": "Primero se utiliza la intersección directa punto-demarcación; si no está disponible, la región canónica se fija con la malla oficial MITECO de referencia de 10 km, independientemente de la resolución analítica.",
                    "out_of_marine_grid": "El Mapa 1 incluye los registros válidos fuera de la malla marina oficial en un conjunto de auditoría separado; esos registros no se utilizan en la densidad por celda marina ni en los resúmenes analíticos regionales.",
                    "density_formula": MARINE_DENSITY_FORMULA,
                    "geodata_layers": geodata_manifest,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        methodology_text = "\n".join(str(item) for item in methodology)
        (root / "metodologia.txt").write_text(
            (
                "PAQUETE DE DATOS REUTILIZABLE HISPA-SYNG v1.0 (PROYECTO HIPPO-DEC)\n\n"
                f"{title}\n\n"
                "Los valores de hábitat se mantienen en español y el libro de entrada original no se modifica.\n"
                "Los archivos CSV utilizan UTF-8 con BOM, separadores de punto y coma y marcador decimal de punto.\n"
                f"Fórmula de densidad marina: {MARINE_DENSITY_FORMULA}\n"
                "El denominador es el área marina efectiva de cada celda costera; se excluye la tierra.\n"
                "Asignación regional: intersección directa con la demarcación MITECO y, si falta, referencia canónica en la malla oficial MITECO de 10 km, independiente de la resolución analítica.\n\n"
                "El Mapa 1 incluye un conjunto de auditoría separado para los registros válidos que quedan fuera de la malla marina oficial; esos registros no se utilizan en la densidad por celda marina ni en los resúmenes analíticos regionales.\n\n"
                + methodology_text
            ).rstrip()
            + "\n",
            encoding="utf-8",
        )
        readme = (
            "PAQUETE DE DATOS REUTILIZABLE HISPA-SYNG v1.0 (PROYECTO HIPPO-DEC)\n\n"
            "Esta carpeta contiene los productos completos específicos de cada mapa en Word y Excel, datos CSV reutilizables, un diccionario de datos, parámetros, metodología y sumas de comprobación.\n"
            "El libro de entrada original en español se conserva como solo lectura y no se incluye ni modifica. Los hábitats se mantienen en español en estos productos.\n"
            "El Mapa 1 incluye, cuando existen, los registros válidos fuera de la malla marina oficial en un conjunto de auditoría separado; no se tratan como celdas marinas.\n"
            "Las capas GeoPackage se encuentran en geodatos/ cuando está disponible la geometría de origen.\n"
        )
        (root / "LEEME.txt").write_text(readme, encoding="utf-8")

        records: list[dict[str, object]] = []
        for candidate in sorted(root.rglob("*")):
            if not candidate.is_file() or candidate.name == "manifiesto.json":
                continue
            records.append(
                {
                    "file": candidate.relative_to(root).as_posix(),
                    "bytes": candidate.stat().st_size,
                    "sha256": _sha256(candidate),
                }
            )
        (root / "manifiesto.json").write_text(
            json.dumps(
                {
                    "product": title,
                    "format": "Paquete de datos reutilizable Hispa-Syng v1.0 (Proyecto Hippo-DEC)",
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
        document.add_paragraph("No había registros disponibles para este conjunto de datos.")
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
                f"Grupo de campos {chunk_index} de {len(chunks)} — {len(table_frame):,} registros completos"
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
        "Descarga completa y legible generada a partir de la ejecución activa de Hispa-Syng v1.0 (Proyecto Hippo-DEC)"
    )
    subtitle.alignment = WD_ALIGN_PARAGRAPH.LEFT

    document.add_heading("Ámbito de la ejecución", level=1)
    metadata = _metadata(context)
    table = document.add_table(rows=0, cols=2)
    table.style = "Light Shading Accent 1"
    for field, value in metadata.itertuples(index=False, name=None):
        cells = table.add_row().cells
        cells[0].text = str(field)
        cells[1].text = "" if value is None else str(value)
        cells[0].paragraphs[0].runs[0].bold = True

    document.add_heading("Método e interpretación", level=1)
    for paragraph in methodology:
        document.add_paragraph(paragraph, style="List Bullet")
    note = document.add_paragraph()
    note.add_run("Regla del área marina. ").bold = True
    note.add_run(
        "Todos los valores de densidad utilizan el área marina efectiva de cada celda MITECO. "
        "La fracción terrestre de las celdas costeras nunca se incluye en el denominador."
    )

    document.add_heading("Apéndice de información completa", level=1)
    document.add_paragraph(
        "Las tablas siguientes contienen todos los registros exportados. Los conjuntos de datos anchos se dividen en grupos de campos; el identificador de la primera columna se repite para que los grupos puedan unirse sin ambigüedad. El archivo Excel adjunto contiene la misma información en hojas filtrables."
    )
    for index, (dataset_name, frame) in enumerate(datasets.items()):
        document.add_heading(translate_text(dataset_name.replace("_", " ")), level=2)
        document.add_paragraph(
            f"Filas: {len(frame):,}. Campos: {len(_plain(frame).columns):,}."
        )
        _add_word_table(document, frame, keys.get(dataset_name))
        if index < len(datasets) - 1:
            document.add_page_break()

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Hispa-Syng v1.0 · Proyecto Hippo-DEC · Información completa de mapas · Densidades con área marina efectiva")
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
        raise FileNotFoundError(f"Falta el archivo obligatorio de publicación o está vacío: {source}")
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
    """Crea una carpeta estática que puede publicarse sin un servicio Python."""

    root = run_root / PUBLICATION_NAME
    maps_dir = root / "mapas"
    downloads_dir = root / "descargas"
    documents_dir = root / "documentos"
    for directory in (maps_dir, downloads_dir, documents_dir):
        directory.mkdir(parents=True, exist_ok=True)

    published_maps: dict[str, Path] = {}
    for key, source in map_paths.items():
        published_maps[key] = _copy_required(source, maps_dir / source.name)

    cells, species = _density_tables(occupied, species_metrics)
    sex = _with_cell_reference(sex_metrics, occupied)
    map1_datasets: dict[str, pd.DataFrame] = {"Observaciones": _plain(master)}
    map1_geodata: dict[str, gpd.GeoDataFrame | None] = {"observaciones": assigned}
    if outside_grid is not None:
        map1_datasets["Observaciones_fuera_malla_marina"] = _plain(outside_grid)
        map1_geodata["observaciones_fuera_malla_marina"] = outside_grid
    map_definitions: dict[str, dict[str, Any]] = {
        "map1": {
            "title": "Hispa-Syng v1.0 (Proyecto Hippo-DEC) — Mapa 1 — Información completa de observaciones",
            "method": [
                "Cada fila de Observaciones representa una observación validada, asignada a la malla marina oficial MITECO y conservada para los productos analíticos marinos.",
                "Observaciones_fuera_malla_marina se incluye cuando los registros filtrados válidos no pudieron asignarse a esa malla marina oficial; se conservan para auditoría y no se utilizan en la densidad por celda marina ni en los resúmenes analíticos regionales.",
                "El Id de origen se conserva únicamente como metadato. Los valores de Id repetidos no eliminan ni fusionan registros.",
                "Los símbolos del mapa identifican especies y su tamaño se basa en la abundancia y en los registros coincidentes; las coordenadas originales permanecen en los datos.",
            ],
            "datasets": map1_datasets,
            "keys": {"Observaciones": "obs_id", "Observaciones_fuera_malla_marina": "obs_id"},
            "geodata": map1_geodata,
        },
        "map2": {
            "title": "Hispa-Syng v1.0 (Proyecto Hippo-DEC) — Mapa 2 — Información completa de densidad",
            "method": [
                "Las observaciones se asignan a la resolución seleccionada de la malla marina MITECO.",
                f"Las densidades de celda y de especie utilizan {MARINE_DENSITY_FORMULA}.",
                "El área marina efectiva excluye la fracción terrestre de las celdas costeras; para la visualización se utiliza la geometría oficial de la celda marina MITECO.",
                "El filtrado interactivo de especies recalcula la abundancia, la densidad, la riqueza, los colores y el contenido de las ventanas emergentes.",
            ],
            "datasets": {"Celdas": cells, "Especies_por_celda": species},
            "keys": {"Celdas": "grid_id", "Especies_por_celda": "grid_id"},
            "geodata": {"celdas_ocupadas": occupied},
        },
        "map3": {
            "title": "Hispa-Syng v1.0 (Proyecto Hippo-DEC) — Mapa 3 — Información completa de variables ecológicas",
            "method": [
                "El mapa combina las variables de riqueza, abundancia total, densidad total, especie dominante y composición sexual.",
                f"Las densidades totales y de especie utilizan {MARINE_DENSITY_FORMULA}.",
                "Las métricas sexuales siguen siendo específicas de cada especie e incluyen umbrales de tamaño muestral para una interpretación responsable.",
                "La fracción terrestre de cada celda costera se excluye de los denominadores de densidad y de las geometrías de visualización.",
            ],
            "datasets": {
                "Celdas": cells,
                "Especies_por_celda": species,
                "Sexo_por_especie_y_celda": sex,
            },
            "keys": {
                "Celdas": "grid_id",
                "Especies_por_celda": "grid_id",
                "Sexo_por_especie_y_celda": "grid_id",
            },
            "geodata": {"celdas_ocupadas": occupied},
        },
    }
    if conservation is not None and "priority" in published_maps:
        map_definitions["priority"] = {
            "title": "Hispa-Syng v1.0 (Proyecto Hippo-DEC) — Información completa de zonas prioritarias de conservación",
            "method": [
                "La prioridad de conservación exige convergencia entre riqueza, persistencia temporal, uso recurrente y representación repetida de especies de baja ocupación; LCBD/hotspots se conservan como contexto y no disparan por sí solos la selección.",
                "Las zonas prioritarias estratégicas agrupan unidades Alta/Muy alta mediante contigüidad rook (borde compartido) y mantienen la metodología científica de selección. Si la malla solicitada es 1 km, el visor conserva una capa independiente de prioridad descriptiva a 1 km y la delimitación estratégica utiliza unidades de planificación de 5 km. Después se generan zonas operativas a partir de celdas MITECO oficiales de 1 km con observaciones dentro de cada zona estratégica; solo se unen celdas con evidencia que comparten borde y nunca se añaden celdas vacías para conectar concentraciones separadas. Con 5 o 10 km, la resolución descriptiva y la de planificación coinciden, pero la huella operativa sigue usando la malla multiescala oficial de 1 km.",
                "Las celdas y zonas prioritarias se recortan a la superficie marina para su visualización y para los cálculos de solapamiento con áreas protegidas.",
                "Solo se conserva la geometría de las áreas protegidas marinas; cuando están disponibles, se exportan el nombre del área, el tipo de protección y el nivel de protección.",
                "Las salidas de prioridad sirven para la evaluación técnica y requieren validación de campo, revisión experta y los procedimientos normativos aplicables.",
            ],
            "datasets": {
                "Celdas_prioritarias": _plain(conservation.get("priority_grid")),
                "Celdas_prioritarias_seleccionadas": _plain(conservation.get("selected_cells")),
                "Zonas_prioritarias": _plain(conservation.get("zone_summary")),
                "Areas_protegidas_marinas": _plain(conservation.get("protected_areas")),
            },
            "keys": {
                "Celdas_prioritarias": "master_id",
                "Celdas_prioritarias_seleccionadas": "master_id",
                "Zonas_prioritarias": "zone_id",
                "Areas_protegidas_marinas": "protected_name",
            },
            "geodata": {
                "celdas_prioritarias": conservation.get("priority_grid"),
                "celdas_seleccionadas": conservation.get("selected_cells"),
                "zonas_prioritarias": conservation.get("zones"),
                "áreas_protegidas_marinas": conservation.get("protected_areas"),
            },
        }

    download_links: dict[str, dict[str, str]] = {}
    generated: dict[str, Path] = {}
    LOGGER.info("[Publicación web] Preparando descargas completas para %d productos", len(map_definitions))
    for key, definition in map_definitions.items():
        LOGGER.info("[Publicación web] %s: libro Excel", key)
        prefix = {
            "map1": "Mapa1_Informacion_Completa",
            "map2": "Mapa2_Informacion_Completa",
            "map3": "Mapa3_Informacion_Completa",
            "priority": "Zonas_Prioritarias_Conservacion_Informacion_Completa",
        }[key]
        excel_path = _write_excel(
            downloads_dir / f"{prefix}.xlsx",
            definition["title"],
            context,
            definition["method"],
            definition["datasets"],
        )
        LOGGER.info("[Publicación web] %s: documento Word", key)
        if key == "priority":
            priority_report = Path(conservation.get("report", "")) if conservation else None
            if priority_report is None or not priority_report.exists():
                raise FileNotFoundError("Falta el informe técnico completo de zonas prioritarias.")
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
        LOGGER.info("[Publicación web] %s: paquete de datos", key)
        data_path = _write_data_package(
            downloads_dir / f"{prefix}_Paquete_Datos.zip",
            definition["title"],
            context,
            definition["method"],
            definition["datasets"],
            excel_path,
            word_path,
            definition.get("geodata", {}),
        )
        LOGGER.info("[Publicación web] %s: descargas completadas", key)
        generated[f"{key}_excel"] = excel_path
        generated[f"{key}_word"] = word_path
        generated[f"{key}_data"] = data_path
        download_links[key] = {
            "excel": f"descargas/{excel_path.name}",
            "word": f"descargas/{word_path.name}",
            "data": f"descargas/{data_path.name}",
        }

    copied_manuals: list[Path] = []
    for manual in manual_paths:
        if manual.exists():
            copied_manuals.append(_copy_required(manual, documents_dir / manual.name))

    publication_context = _publication_language_context(context, published_maps)
    index = render_viewer(
        root / "index.html",
        f"mapas/{published_maps['map1'].name}",
        f"mapas/{published_maps['map2'].name}",
        f"mapas/{published_maps['map3'].name}",
        f"mapas/{published_maps['priority'].name}" if "priority" in published_maps else None,
        download_links,
        publication_context,
        open_browser,
    )

    # Los mapas publicados viven un nivel por debajo de la raíz. Sus mapas de
    # origen se generaron en el árbol de ejecución, por lo que tras copiarlos
    # solo se reescribe el prefijo relativo de descarga; los mapas independientes
    # conservan sus enlaces válidos.
    for key, published_map in published_maps.items():
        text = published_map.read_text(encoding="utf-8")
        text = text.replace("../../Publicacion_Web/descargas/", "../descargas/")
        text = text.replace("../Publicacion_Web/descargas/", "../descargas/")
        text = text.replace("../../Web_Publication/downloads/", "../descargas/")
        text = text.replace("../Web_Publication/downloads/", "../descargas/")
        published_map.write_text(text, encoding="utf-8")
        rewrite_language_switch(
            published_map,
            publication_context.get("language_switch"),
            published_map,
            key,
        )

    for key, published_map in published_maps.items():
        copy_public_registration(map_paths[key], published_map)

    upload_note = root / "LEEME_SUBIDA.txt"
    upload_note.write_text(
        "PUBLICACIÓN WEB HISPA-SYNG v1.0 (PROYECTO HIPPO-DEC)\n\n"
        "Esta carpeta contiene la publicación española. Súbala completa al servidor web institucional sin cambiar su estructura interna.\n"
        "Para publicar los dos idiomas desde una sola carpeta, use Publicacion_Web_Bilingue_<id>, creada por el coordinador bilingüe en Resultados.\n"
        "Configure el servidor para publicar index.html como documento predeterminado y comparta después la URL resultante.\n\n"
        "Carpetas necesarias:\n"
        "- mapas: cuatro mapas HTML interactivos.\n"
        "- descargas: un archivo Word completo, un archivo Excel completo y un ZIP de datos reutilizable para cada mapa.\n"
        "- documentos: manuales de usuario suministrados con esta versión.\n\n"
        "Esta es una publicación estática para los productos no sensibles. En un proyecto protegido, Mapa 1 y las descargas controladas se sustituyen al final de la ejecución por contenedores cifrados .hse; ábralos desde Hispa-Syng.bat > Seguridad y accesos.\n"
        "Si decide publicar una copia completamente abierta, aplique en el servidor las medidas de autenticación y autorización que correspondan a la sensibilidad de los datos.\n"
        "Los vectores del mapa, la interfaz y Leaflet funcionan desde archivos locales. Los fondos Satélite (Esri World Imagery), Batimetría marina (EMODnet Bathymetry) y Físico (OpenTopoMap) se cargan en línea al abrir el HTML. Satélite está activo por defecto. Los tres requieren conexión a Internet y no requieren una API key ni suscripción.\n",
        encoding="utf-8",
    )

    manifest_records = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if path.name in {"manifiesto.json", REGISTRY_NAME}:
            continue
        manifest_records.append(
            {
                "file": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    manifest = root / "manifiesto.json"
    manifest.write_text(
        json.dumps(
            {
                "product": "Publicación web Hispa-Syng v1.0 (Proyecto Hippo-DEC)",
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
