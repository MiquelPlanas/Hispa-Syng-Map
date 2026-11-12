"""Informe técnico integral generado al final de cada ejecución de Hispa-Syng v1.0.

El informe es determinista: utiliza exclusivamente los datos filtrados y los
resultados producidos por la ejecución actual. No consulta servicios externos ni
utiliza modelos de IA.
"""
from __future__ import annotations

import math
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .source_notices import add_cartographic_notice

LOGGER = logging.getLogger("hippodec_maps")

import numpy as np
import pandas as pd
try:
    import geopandas as gpd  # type: ignore
except Exception:  # pragma: no cover
    gpd = None  # type: ignore
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore
except Exception:  # pragma: no cover
    plt = None  # type: ignore
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .analysis_utils import AnalysisSettings


TITLE = "Informe técnico integral de resultados"
PRODUCT = "Hispa-Syng v1.0"
PROJECT = "Proyecto Hippo-DEC"


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _fmt(value: Any, digits: int = 1, missing: str = "N.D.") -> str:
    if value is None or value is pd.NA:
        return missing
    number = _num(value)
    if number is not None:
        if abs(number - round(number)) < 1e-10 and digits == 0:
            return f"{int(round(number)):,}".replace(",", ".")
        text = f"{number:,.{digits}f}"
        return text.replace(",", "X").replace(".", ",").replace("X", ".")
    text = str(value).strip()
    return text if text else missing


def _pct(value: Any, digits: int = 1) -> str:
    number = _num(value)
    return "N.D." if number is None else f"{_fmt(number, digits)} %"


def _clean_text(value: Any, default: str = "N.D.") -> str:
    if value is None or value is pd.NA:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or default


def _shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def _set_cant_split(row) -> None:
    """Keep a table row on one page whenever Word/LibreOffice can do so."""
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        cant_split = OxmlElement("w:cantSplit")
        cant_split.set(qn("w:val"), "true")
        tr_pr.append(cant_split)


def _style_document(document: Document) -> None:
    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.08
    for name, size, color in (
        ("Title", 24, "17365D"),
        ("Heading 1", 17, "17365D"),
        ("Heading 2", 14, "1F4E79"),
        ("Heading 3", 12, "2F5597"),
    ):
        style = styles[name]
        style.font.name = "Aptos Display" if name != "Normal" else "Aptos"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = Pt(9 if name != "Title" else 0)
        style.paragraph_format.space_after = Pt(4)


def _add_footer(document: Document) -> None:
    for section in document.sections:
        paragraph = section.footer.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(f"{PRODUCT} · {TITLE}")
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(100, 100, 100)


def _add_kv_table(document: Document, rows: Iterable[tuple[str, Any]], *, digits: int = 1) -> None:
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    table.autofit = False
    table.columns[0].width = Cm(6.2)
    table.columns[1].width = Cm(10.0)
    for label, value in rows:
        row = table.add_row()
        _set_cant_split(row)
        cells = row.cells
        cells[0].text = str(label)
        cells[0].paragraphs[0].runs[0].bold = True
        _shade_cell(cells[0], "D9EAF7")
        label_cf = str(label).casefold()
        if isinstance(value, (int, float, np.number)) and _num(value) is not None:
            if any(token in label_cf for token in ("p_value", "p-value", "p value", "valor p", "p-valor")):
                cells[1].text = _fmt(value, 4)
            elif "lcbd" in label_cf:
                cells[1].text = _fmt(value, 4)
            elif any(token in label_cf for token in ("número", "number", "celdas", "cells", "riqueza", "richness", "hotspots", "registros", "records", "años", "years", "permutaciones", "permutations", "semilla", "seed", "especies", "species", "individuos", "individuals", "abundancia registrada", "recorded abundance")):
                cells[1].text = _fmt(value, 0)
            else:
                cells[1].text = _fmt(value, digits)
        else:
            cells[1].text = _clean_text(value)
        for cell in cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _add_df_table(
    document: Document,
    frame: pd.DataFrame,
    columns: list[tuple[str, str]],
    *,
    max_rows: int = 20,
    sort_by: str | None = None,
    ascending: bool = False,
    digits: int = 2,
) -> None:
    if frame is None or frame.empty:
        document.add_paragraph("No existen resultados calculables para esta tabla en la ejecución actual.")
        return
    data = frame.copy()
    if sort_by and sort_by in data.columns:
        data = data.sort_values(sort_by, ascending=ascending, kind="stable")
    data = data.head(max_rows)
    table = document.add_table(rows=1, cols=len(columns))
    table.style = "Table Grid"
    _set_repeat_table_header(table.rows[0])
    _set_cant_split(table.rows[0])
    for cell, (_, label) in zip(table.rows[0].cells, columns):
        cell.text = label
        cell.paragraphs[0].runs[0].bold = True
        # Avoid orphaned table headers at the bottom of a page.
        cell.paragraphs[0].paragraph_format.keep_with_next = True
        _shade_cell(cell, "1F4E79")
        for run in cell.paragraphs[0].runs:
            run.font.color.rgb = RGBColor(255, 255, 255)
            run.font.size = Pt(8)
    for _, row in data.iterrows():
        out_row = table.add_row()
        _set_cant_split(out_row)
        cells = out_row.cells
        for cell, (field, _) in zip(cells, columns):
            value = row.get(field, pd.NA)
            field_cf = str(field).casefold()
            if field_cf in {"year", "año"} and _num(value) is not None:
                cell.text = str(int(round(float(value))))
            elif ("significant" in field_cf or "significativo" in field_cf) and value is not pd.NA:
                if isinstance(value, str):
                    token = value.strip().casefold()
                    truth = token in {"true", "1", "yes", "sí", "si"}
                else:
                    try:
                        truth = bool(value)
                    except Exception:
                        truth = False
                cell.text = "Sí" if truth else "No"
            elif field_cf in {"n_records", "total_abundance", "n_cells", "n_species", "records", "occupied_cells", "abundance", "female", "male", "indeterminate", "n_obs_cell", "n_years_cell", "n_depth", "n", "hotspot_cells_multiscale", "hotspot_cells_persistent_all_scales", "n_especies", "n_total_celda", "richness", "richness_max", "abundance_sum", "cluster", "n_protected_areas_overlap", "scale_km", "n_cells_total_with_records", "n_cells_evaluable", "n_lcbd_significant", "n_hotspots", "n_hotspots_significant"} and _num(value) is not None:
                cell.text = _fmt(value, 0)
            elif field_cf.endswith("_id"):
                cell.text = _clean_text(value)
            elif isinstance(value, (int, float, np.number)) and _num(value) is not None:
                cell.text = _fmt(value, digits)
            else:
                cell.text = _clean_text(value)
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(8)
    if len(frame) > max_rows:
        document.add_paragraph(
            f"Se muestran {max_rows} filas de {len(frame)}. La tabla completa se conserva en las salidas tabulares de la ejecución.",
            style=None,
        )


def _find_figure(root: Path, patterns: Iterable[str]) -> Path | None:
    figures_root = root / "05_figuras"
    if not figures_root.exists():
        return None
    pngs = list(figures_root.rglob("*.png"))
    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        matches = [path for path in pngs if regex.search(path.stem)]
        if matches:
            return sorted(matches, key=lambda p: (len(p.parts), str(p)))[0]
    return None


def _add_figure(document: Document, root: Path, patterns: Iterable[str], caption: str, *, width_cm: float = 15.7) -> None:
    path = _find_figure(root, patterns)
    if path is None:
        return
    try:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.keep_with_next = True
        paragraph.add_run().add_picture(str(path), width=Cm(width_cm))
        cap = document.add_paragraph(caption)
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].italic = True
        cap.runs[0].font.size = Pt(8.5)
    except Exception:
        document.add_paragraph(f"Figura disponible en: {path.name}")


def _add_picture(document: Document, path: Path | None, caption: str, *, width_cm: float = 15.7) -> None:
    if path is None or not Path(path).exists():
        return
    try:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.keep_with_next = True
        paragraph.add_run().add_picture(str(path), width=Cm(width_cm))
        cap = document.add_paragraph(caption)
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if cap.runs:
            cap.runs[0].italic = True
            cap.runs[0].font.size = Pt(8.5)
    except Exception:
        document.add_paragraph(f"Figura disponible en: {Path(path).name}")


def _safe_relative(path: Path | str | None, base: Path, fallback: str) -> str:
    if path is None:
        return fallback
    try:
        return str(Path(path).resolve().relative_to(base.resolve()))
    except Exception:
        return fallback


def _folder_locations_es(run_root: Path, output_dir: Path) -> pd.DataFrame:
    rows = []
    candidates = [
        ("00_registros", "Registros y log de la ejecución"),
        ("01_parametros", "Parámetros, filtros, manifiestos y metadatos de la ejecución"),
        ("02_intermedios", "Objetos intermedios y archivos auxiliares del análisis"),
        ("03_mapas", "Mapas estáticos y cartografía derivada"),
        ("04_tablas", "Tablas de resultados y resúmenes tabulares"),
        ("05_figuras", "Figuras PNG empleadas y/o generadas por los análisis"),
        ("06_modelos", "Matrices, modelos y salidas analíticas"),
        ("07_control_calidad", "Controles de calidad, advertencias y comprobaciones de la ejecución"),
        ("08_visores", "Visores HTML e interfaces cartográficas de consulta"),
        ("09_zonas_prioritarias_conservacion", "Resultados específicos de zonas prioritarias: mapas, tablas, paquetes de datos e informe específico"),
        ("10_informe_tecnico", "Informe técnico integral bilingüe generado al final de la ejecución"),
    ]
    for rel, desc in candidates:
        if (run_root / rel).exists() or rel == _safe_relative(output_dir, run_root, rel).split("/")[0]:
            rows.append({"tipo": rel, "ruta": rel + "/", "contenido": desc})
    return pd.DataFrame(rows)


def _priority_macroarea_es(lon: float, lat: float) -> str:
    if lat < 31.8:
        return "Canarias"
    if lat < 36.35 and lon > -6.7:
        return "Ceuta / Melilla y sector sur de Alborán"
    return "Península Ibérica y Baleares"


def _set_plot_bounds(ax, bounds: tuple[float, float, float, float], *, pad_frac: float = 0.08, min_pad: float = 0.2) -> None:
    minx, miny, maxx, maxy = bounds
    dx = max(maxx - minx, min_pad)
    dy = max(maxy - miny, min_pad)
    padx = max(dx * pad_frac, min_pad)
    pady = max(dy * pad_frac, min_pad)
    ax.set_xlim(minx - padx, maxx + padx)
    ax.set_ylim(miny - pady, maxy + pady)


def _render_priority_zone_maps_es(run_root: Path, output_dir: Path, conservation: dict[str, Any], zones_summary: pd.DataFrame) -> list[tuple[Path, str]]:
    """Genera dos figuras cartográficas para incrustar en el informe técnico.

    Usa primero las celdas seleccionadas con geometría y, como respaldo, las
    geometrías agregadas de ``conservation['zones']``. Nunca depende de rutas
    absolutas del equipo del usuario.
    """
    if gpd is None or plt is None:
        return []

    source = conservation.get("selected_cells", pd.DataFrame())
    use_cells = source is not None and len(source) > 0 and "geometry" in getattr(source, "columns", [])
    if not use_cells:
        source = conservation.get("zones", pd.DataFrame())
    if source is None or len(source) == 0 or "geometry" not in getattr(source, "columns", []):
        return []

    try:
        gdf = gpd.GeoDataFrame(source.copy(), geometry="geometry", crs=getattr(source, "crs", None))
    except Exception:
        return []
    gdf = gdf[(~gdf.geometry.isna()) & (~gdf.geometry.is_empty)].copy()
    if gdf.empty or "zone_id" not in gdf.columns:
        return []
    gdf["zone_id"] = gdf["zone_id"].astype(str)
    try:
        if gdf.crs is not None:
            gdf = gdf.to_crs(4326)
    except Exception:
        pass

    try:
        zones_gdf = gdf.dissolve(by="zone_id", as_index=False) if use_cells else gdf[["zone_id", "geometry"]].dissolve(by="zone_id", as_index=False)
    except Exception:
        return []
    if zones_gdf.empty:
        return []

    merge_cols = [c for c in ["zone_id", "ecological_priority_class_zone", "Region_MITECO_dominante", "ecological_priority_score_mean"] if c in zones_summary.columns]
    if merge_cols:
        zones_gdf = zones_gdf.merge(zones_summary[merge_cols].drop_duplicates("zone_id"), on="zone_id", how="left")
    zones_gdf = zones_gdf.sort_values("zone_id", kind="stable").reset_index(drop=True)

    try:
        metric = zones_gdf.to_crs(3035) if zones_gdf.crs is not None else zones_gdf.copy()
        metric["geometry"] = metric.geometry.representative_point()
        labels = metric.to_crs(4326) if metric.crs is not None else metric
    except Exception:
        labels = zones_gdf.copy()
        labels["geometry"] = labels.geometry.representative_point()

    def macroarea(lon: float, lat: float) -> str:
        if lat < 31.8:
            return "Canarias"
        if lat < 36.35 and lon > -6.7:
            return "Ceuta / Melilla y mar de Alborán"
        return "Península Ibérica y Baleares"

    macro = []
    for geom in labels.geometry:
        if geom is None or geom.is_empty:
            macro.append("Península Ibérica y Baleares")
        else:
            macro.append(macroarea(float(geom.x), float(geom.y)))
    zones_gdf["_macroarea"] = macro

    colors=[]
    for val in zones_gdf.get("ecological_priority_class_zone", pd.Series([""]*len(zones_gdf))):
        txt=_clean_text(val, "").casefold()
        colors.append("#C94C4C" if ("muy alta" in txt or "very high" in txt) else "#F0AD4E" if ("alta" in txt or "high" in txt) else "#8CB9D8")
    zones_gdf["_fill_color"] = colors

    # Reuse the validated local GSHHG context from the main pipeline so the
    # report map uses the same land and coastline geometry as the analysis.
    map_context = conservation.get("map_context")
    context_land = getattr(map_context, "land", None)
    context_coastline = getattr(map_context, "coastline", None)
    try:
        if context_land is not None and not context_land.empty and context_land.crs is not None:
            context_land = context_land.to_crs(4326)
        if context_coastline is not None and not context_coastline.empty and context_coastline.crs is not None:
            context_coastline = context_coastline.to_crs(4326)
    except Exception:
        context_land = None
        context_coastline = None

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[tuple[Path, str]]=[]

    def bounds(ax, subset) -> None:
        minx,miny,maxx,maxy=map(float, subset.total_bounds)
        dx=max(maxx-minx,0.4); dy=max(maxy-miny,0.4)
        ax.set_xlim(minx-max(0.25,dx*0.10), maxx+max(0.25,dx*0.10))
        ax.set_ylim(miny-max(0.20,dy*0.10), maxy+max(0.20,dy*0.10))

    def draw(ax, subset, title: str, legend: bool=False, label_size: float=6.5) -> None:
        minx,miny,maxx,maxy=map(float, subset.total_bounds)
        dx=max(maxx-minx,0.4); dy=max(maxy-miny,0.4)
        pad_x=max(0.25,dx*0.10); pad_y=max(0.20,dy*0.10)
        ax.set_facecolor("#DCEFF5")
        if context_land is not None and not context_land.empty:
            context_land.plot(ax=ax, color="#EFEEE9", edgecolor="none", linewidth=0, zorder=0)
        if context_coastline is not None and not context_coastline.empty:
            context_coastline.plot(ax=ax, color="#303030", linewidth=0.70, zorder=1)
        subset.plot(ax=ax, color=subset["_fill_color"], edgecolor="#17365D", linewidth=1.2, zorder=3)
        lab=labels[labels["zone_id"].isin(subset["zone_id"])].copy()
        n_labels=len(lab)
        adaptive_size=min(
            float(label_size),
            5.2 if n_labels <= 8 else 4.8 if n_labels <= 18 else 4.4 if n_labels <= 35 else 4.0,
        )
        x_step=max(dx*(0.020 if n_labels <= 18 else 0.014),0.025)
        y_step=max(dy*(0.026 if n_labels <= 18 else 0.018),0.020)
        placed=[]
        directions=((0,0),(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1),(2,1),(-2,1),(2,-1),(-2,-1))
        for _, row in lab.iterrows():
            geom=row.geometry
            if geom is None or geom.is_empty: continue
            anchor=(float(geom.x),float(geom.y)); chosen=anchor; best_score=float("inf")
            for radius in range(0,9):
                for ux,uy in directions:
                    if radius == 0 and (ux,uy) != (0,0): continue
                    if radius > 0 and (ux,uy) == (0,0): continue
                    candidate=(anchor[0]+ux*radius*x_step,anchor[1]+uy*radius*y_step)
                    if not (minx-pad_x*0.85 <= candidate[0] <= maxx+pad_x*0.85 and miny-pad_y*0.85 <= candidate[1] <= maxy+pad_y*0.85):
                        continue
                    collisions=sum(abs(candidate[0]-px)<x_step*1.7 and abs(candidate[1]-py)<y_step*1.25 for px,py in placed)
                    score=collisions*1000+radius
                    if score < best_score:
                        chosen=candidate; best_score=score
                    if collisions == 0:
                        break
                if best_score < 1000:
                    break
            placed.append(chosen)
            moved=abs(chosen[0]-anchor[0])>1e-12 or abs(chosen[1]-anchor[1])>1e-12
            ax.annotate(str(row["zone_id"]),xy=anchor,xytext=chosen,textcoords="data",ha="center",va="center",
                        fontsize=adaptive_size,fontweight="bold",zorder=5,
                        arrowprops=dict(arrowstyle="-",color="#536579",linewidth=0.45,alpha=0.75) if moved else None,
                        bbox=dict(boxstyle="round,pad=0.07",facecolor="white",edgecolor="#17365D",linewidth=0.40,alpha=0.88))
        bounds(ax, subset)
        ax.set_aspect("equal", adjustable="box")
        add_cartographic_notice(ax.figure)
        ax.set_title(title, fontsize=11, color="#17365D", pad=8)
        ax.set_xlabel("Longitud (°)", fontsize=8); ax.set_ylabel("Latitud (°)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, linewidth=0.35, alpha=0.35)
        if legend:
            import matplotlib.patches as mpatches
            ax.legend(handles=[mpatches.Patch(facecolor="#C94C4C", edgecolor="#17365D", label="Prioridad muy alta"),
                               mpatches.Patch(facecolor="#F0AD4E", edgecolor="#17365D", label="Prioridad alta")],
                      loc="lower left", fontsize=8, frameon=True)

    p1=output_dir/"Mapa_11_Zonas_Prioritarias_Etiquetadas_General.png"
    fig,ax=plt.subplots(figsize=(10.8,7.6),dpi=220)
    draw(ax,zones_gdf,"Zonas prioritarias de conservación · vista general",legend=True,label_size=4.8)
    fig.tight_layout(); fig.savefig(p1,bbox_inches="tight",facecolor="white"); plt.close(fig)
    outputs.append((p1,"Figura. Mapa general de las zonas prioritarias de conservación con sus etiquetas. Incluye Península Ibérica, Baleares, Canarias, Ceuta y Melilla cuando existen zonas seleccionadas en esos ámbitos."))

    order=[a for a in ["Península Ibérica y Baleares","Canarias","Ceuta / Melilla y mar de Alborán"] if a in set(macro)]
    if not order:
        order=["Península Ibérica y Baleares"]
    p2=output_dir/"Mapa_11_Zonas_Prioritarias_Etiquetadas_Detalle.png"
    if len(order)==1:
        fig,ax=plt.subplots(figsize=(10.8,5.2),dpi=220)
        subset=zones_gdf[zones_gdf["_macroarea"].eq(order[0])]
        draw(ax,subset,order[0],legend=False,label_size=5.0)
    elif len(order)==2:
        fig,axes=plt.subplots(1,2,figsize=(10.8,5.0),dpi=220)
        for ax,name in zip(np.atleast_1d(axes),order):
            subset=zones_gdf[zones_gdf["_macroarea"].eq(name)]
            draw(ax,subset,name,legend=False,label_size=5.0)
    else:
        fig=plt.figure(figsize=(10.8,6.0),dpi=220)
        gs=fig.add_gridspec(2,2,width_ratios=[1.55,1.0],hspace=0.28,wspace=0.18)
        axes=[fig.add_subplot(gs[:,0]),fig.add_subplot(gs[0,1]),fig.add_subplot(gs[1,1])]
        for ax,name in zip(axes,order[:3]):
            subset=zones_gdf[zones_gdf["_macroarea"].eq(name)]
            draw(ax,subset,name,legend=False,label_size=5.0)
    fig.suptitle("Detalle geográfico de las zonas prioritarias",fontsize=13,color="#17365D",y=0.995)
    fig.subplots_adjust(left=0.06,right=0.98,bottom=0.08,top=0.90); fig.savefig(p2,bbox_inches="tight",facecolor="white"); plt.close(fig)
    outputs.append((p2,"Figura. Detalle geográfico de las zonas prioritarias, separado por ámbitos cuando procede, para facilitar la lectura de etiquetas y su correspondencia con las fichas de cada zona."))
    return outputs


def _species_zone_table(selected_cells: pd.DataFrame, assigned: pd.DataFrame, zones_summary: pd.DataFrame) -> pd.DataFrame:
    if selected_cells is None or assigned is None or len(selected_cells) == 0 or len(assigned) == 0:
        return pd.DataFrame(columns=["zone_id", "Species", "abundance", "density", "records", "occupied_cells"])
    cells = pd.DataFrame(selected_cells.drop(columns="geometry", errors="ignore")).copy()
    if not {"zone_id", "master_id"}.issubset(cells.columns):
        return pd.DataFrame()
    cells["grid_id"] = cells["master_id"].astype(str)
    cells["zone_id"] = cells["zone_id"].astype(str)
    zone_area = pd.to_numeric(cells.get("Area_mar_km2"), errors="coerce")
    cells["Area_mar_km2"] = zone_area
    areas = cells.groupby("zone_id", observed=True)["Area_mar_km2"].sum(min_count=1)
    if zones_summary is not None and not zones_summary.empty and "area_zone_km2" in zones_summary:
        fallback = pd.to_numeric(zones_summary.set_index(zones_summary["zone_id"].astype(str))["area_zone_km2"], errors="coerce")
        areas = areas.combine_first(fallback)
    obs = pd.DataFrame(assigned.drop(columns="geometry", errors="ignore")).copy()
    if not {"grid_id", "N_total"}.issubset(obs.columns):
        return pd.DataFrame()
    species_col = "Species_clean" if "Species_clean" in obs.columns else "Species"
    if species_col not in obs.columns:
        return pd.DataFrame()
    obs["grid_id"] = obs["grid_id"].astype(str)
    obs["Species"] = obs[species_col].astype("string").str.strip()
    obs["N_total"] = pd.to_numeric(obs["N_total"], errors="coerce").fillna(0).clip(lower=0)
    obs = obs.merge(cells[["grid_id", "zone_id"]].drop_duplicates(), on="grid_id", how="inner")
    obs = obs[obs["Species"].notna() & obs["Species"].ne("")]
    if obs.empty:
        return pd.DataFrame()
    result = obs.groupby(["zone_id", "Species"], observed=True).agg(
        abundance=("N_total", "sum"),
        records=("Species", "size"),
        occupied_cells=("grid_id", "nunique"),
    ).reset_index()
    result["zone_area_km2"] = result["zone_id"].map(areas)
    result["density"] = np.where(result["zone_area_km2"].gt(0), result["abundance"] / result["zone_area_km2"], np.nan)
    return result.sort_values(["zone_id", "abundance", "Species"], ascending=[True, False, True], kind="stable")


def _zone_temporal_summary(zone_id: str, selected_cells: pd.DataFrame, temporal_changes: pd.DataFrame) -> dict[str, int]:
    summary = {"Ganancia": 0, "Pérdida": 0, "Persistencia": 0, "Ausencia en ambos": 0, "No comparable": 0}
    if selected_cells is None or temporal_changes is None or len(selected_cells) == 0 or len(temporal_changes) == 0:
        return summary
    cells = pd.DataFrame(selected_cells.drop(columns="geometry", errors="ignore"))
    if not {"zone_id", "master_id"}.issubset(cells.columns) or "grid_id" not in temporal_changes.columns or "status" not in temporal_changes.columns:
        return summary
    ids = set(cells.loc[cells["zone_id"].astype(str).eq(str(zone_id)), "master_id"].astype(str))
    subset = temporal_changes[temporal_changes["grid_id"].astype(str).isin(ids)]
    for key in summary:
        summary[key] = int(subset["status"].astype(str).eq(key).sum())
    return summary


def _measure(
    category: str,
    action: str,
    rationale: str,
    timeframe: str,
    evidence: str,
    indicator: str,
    implementation: str,
) -> dict[str, str]:
    return {
        "category": category,
        "action": action,
        "rationale": rationale,
        "timeframe": timeframe,
        "evidence": evidence,
        "indicator": indicator,
        "implementation": implementation,
    }


def _zone_measures(
    row: pd.Series,
    species: pd.DataFrame,
    temporal_summary: dict[str, int],
    protected_loaded: bool,
) -> list[dict[str, str]]:
    measures: list[dict[str, str]] = []
    pct_protected = _num(row.get("pct_zone_protected"))
    priority = _clean_text(row.get("ecological_priority_class_zone"), "No calculada")
    data_adequacy = _clean_text(row.get("data_adequacy_class_zone"), "No calculada")
    evidence = data_adequacy
    habitat = _clean_text(row.get("habitat_dominant_zone"), "No determinado")
    depth = _num(row.get("depth_median_zone"))
    lcbd = _num(row.get("LCBD_max"))
    hotspot_multi = _num(row.get("hotspot_cells_multiscale")) or 0
    hotspot_persist = _num(row.get("hotspot_cells_persistent_all_scales")) or 0
    protected_names = _clean_text(row.get("protected_area_names"), "Sin información")
    protected_types = _clean_text(row.get("protected_area_types"), "Sin información")

    if not protected_loaded or pct_protected is None:
        measures.append(_measure(
            "Cobertura espacial y figuras de protección",
            "Completar la evaluación espacial de protección antes de decidir ampliaciones o nuevas figuras.",
            "La ejecución no dispone de una evaluación completa del solapamiento con áreas protegidas. Sin esa referencia no puede distinguirse entre un vacío real de protección y una zona ya cubierta por instrumentos existentes.",
            "Inmediato",
            evidence,
            "% de la zona y de sus celdas de máxima prioridad con protección evaluable",
            "Incorporar/validar las capas marinas de protección, repetir el cruce espacial y revisar nombres, categorías, competencias y planes de gestión aplicables.",
        ))
    elif pct_protected < 5:
        measures.append(_measure(
            "Cobertura espacial y figuras de protección",
            "Evaluar formalmente un instrumento de protección o gestión espacial para el núcleo prioritario.",
            f"La zona presenta prioridad {priority} y solo {_pct(pct_protected)} de cobertura protegida. La recomendación es técnica y no presupone una figura jurídica concreta: debe valorarse qué instrumento es compatible con los valores ecológicos, las competencias y los usos locales.",
            "Corto plazo (1–3 años)",
            evidence,
            "% de celdas de prioridad alta/muy alta incorporadas a un instrumento efectivo",
            "Delimitar el núcleo ecológico, contrastarlo en campo, identificar usos y presiones, analizar conectividad y tramitar la opción de gestión/protección que corresponda.",
        ))
    elif pct_protected < 50:
        measures.append(_measure(
            "Cobertura espacial y figuras de protección",
            "Evaluar ampliación funcional, ajuste de límites o medidas complementarias en el sector no cubierto.",
            f"La cobertura actual es parcial ({_pct(pct_protected)}). Las figuras que intersectan la zona son: {protected_names} ({protected_types}). Debe comprobarse si las celdas de mayor prioridad quedan dentro o fuera de esos límites.",
            "Corto plazo (1–3 años)",
            evidence,
            "% de núcleos de alta prioridad y hotspots persistentes efectivamente cubiertos",
            "Superponer límites de protección con score, LCBD, hotspots, persistencia y distribución de especies; priorizar los vacíos que concentren más componentes ecológicos.",
        ))
    elif pct_protected < 95:
        measures.append(_measure(
            "Cobertura espacial y figuras de protección",
            "Revisar los sectores no cubiertos y la conectividad con la protección existente.",
            f"La zona está mayoritariamente protegida ({_pct(pct_protected)}), pero persiste superficie exterior. La protección existente incluye: {protected_names} ({protected_types}). El porcentaje global no garantiza que el núcleo ecológico esté cubierto.",
            "Medio plazo (3–6 años)",
            evidence,
            "% de celdas de máxima prioridad fuera de límites y continuidad espacial del núcleo",
            "Identificar vacíos internos y de borde; si concentran LCBD, persistencia o hábitat esencial, valorar ajuste de límites o medidas sectoriales específicas.",
        ))
    else:
        measures.append(_measure(
            "Efectividad de la protección existente",
            "Priorizar la revisión de la efectividad de gestión antes que una ampliación espacial automática.",
            f"La cobertura espacial es muy alta ({_pct(pct_protected)}). La cuestión principal pasa a ser si los instrumentos existentes ({protected_names}; {protected_types}) contienen objetivos, regulación, vigilancia y seguimiento adecuados para los signátidos y sus hábitats.",
            "Inmediato y permanente",
            evidence,
            "Cumplimiento de objetivos de conservación y tendencia de ocupación/abundancia dentro de la zona",
            "Revisar planes de gestión, presiones permitidas, vigilancia, indicadores biológicos y estado del hábitat; corregir medidas si los resultados no son compatibles con los objetivos.",
        ))

    if hotspot_multi > 0 or hotspot_persist > 0 or (lcbd is not None and lcbd > 0):
        measures.append(_measure(
            "Zonificación interna y núcleos ecológicos",
            "Definir un núcleo de conservación reforzada y una zona de amortiguación basada en la evidencia espacial de la ejecución.",
            f"La zona contiene {int(hotspot_multi)} celdas hotspot multiescala y {int(hotspot_persist)} persistentes en todas las escalas; LCBD máximo {_fmt(lcbd, 4) if lcbd is not None else 'N.D.'}. Estos componentes permiten identificar sectores donde concentrar medidas sin imponer la misma intensidad de regulación a toda la zona.",
            "Corto plazo (1–3 años)",
            evidence,
            "% del núcleo ecológico sometido a medidas reforzadas y estabilidad de LCBD/hotspots",
            "Cartografiar núcleo, amortiguación, conectores y sectores de uso compatible; vincular cada subzona a objetivos e indicadores explícitos.",
        ))

    habitat_lower = habitat.casefold()
    structured = any(token in habitat_lower for token in ("pradera", "posidonia", "cymodocea", "zostera", "seagrass", "macroalg"))
    artificial = any(token in habitat_lower for token in ("artificial", "antrop", "puerto", "harbour", "harbor"))
    soft_bottom = any(token in habitat_lower for token in ("arena", "fango", "grava", "sand", "mud", "gravel"))
    if structured:
        measures.append(_measure(
            "Protección de hábitat estructural",
            "Conservar la integridad y continuidad de praderas y/o macroalgas y evitar pérdidas netas de hábitat funcional.",
            f"El hábitat dominante de la zona es {habitat}. Para signátidos, la complejidad estructural del hábitat puede sostener refugio, alimentación, reproducción y conectividad. La medida debe centrarse en mantener el hábitat y no solo en la presencia puntual de individuos.",
            "Inmediato y permanente",
            evidence,
            "Cobertura, continuidad y estado ecológico del hábitat; ocupación de signátidos asociada",
            "Cartografiar extensión y estado; prevenir daño físico, enterramiento, pérdida de cobertura, turbidez crónica y fragmentación; restaurar solo cuando la presión causante esté controlada.",
        ))
        if depth is None or depth <= 30:
            measures.append(_measure(
                "Fondeo y navegación recreativa",
                "Evaluar y, si existe presión relevante, ordenar el fondeo para evitar impactos sobre hábitats sensibles y núcleos de presencia.",
                "La combinación de hábitat estructural y aguas someras hace razonable comprobar la presión de fondeo. El informe no asume que exista daño: propone verificarlo y aplicar regulación únicamente cuando la presión esté documentada.",
                "Corto plazo (1–3 años)",
                evidence,
                "Número/densidad de fondeos sobre hábitat sensible, superficie afectada y evolución de cicatrices",
                "Inventariar fondeos, delimitar áreas compatibles/no compatibles, instalar amarres de bajo impacto cuando proceda, señalizar y verificar cumplimiento.",
            ))
    elif soft_bottom:
        measures.append(_measure(
            "Integridad del fondo marino",
            "Evaluar actividades que alteren directamente el sustrato y establecer medidas espaciales o temporales si coinciden con núcleos prioritarios.",
            f"El hábitat dominante ({habitat}) puede ser sensible a perturbaciones físicas, resuspensión y cambios granulométricos. La necesidad de restricciones debe basarse en la presencia real de artes, dragados u obras, no inferirse únicamente del hábitat.",
            "Medio plazo (3–6 años)",
            evidence,
            "Superficie del fondo sometida a perturbación y tendencia de ocupación de las celdas afectadas",
            "Caracterizar actividades de fondo, comparar su huella con las celdas prioritarias y establecer exclusiones/ventanas temporales solo cuando exista solapamiento demostrado.",
        ))
    elif artificial:
        measures.append(_measure(
            "Infraestructuras costeras y hábitats artificiales",
            "Gestionar obras, mantenimiento, limpieza y dragado de infraestructuras de forma compatible con la presencia de signátidos.",
            f"El hábitat dominante se ha clasificado como {habitat}. Las estructuras artificiales pueden actuar como hábitat utilizado, pero también están sometidas a mantenimiento periódico y perturbaciones intensas.",
            "Inmediato y permanente",
            evidence,
            "Incidencias durante mantenimiento, ocupación antes/después y superficie de hábitat funcional conservada",
            "Incluir prospección previa, protocolos de rescate/relocación solo cuando sean legal y técnicamente apropiados, ventanas de menor sensibilidad y seguimiento posterior a actuaciones.",
        ))

    measures.append(_measure(
        "Pesca y captura accidental",
        "Caracterizar el solapamiento con artes profesionales y recreativas y aplicar reducción de bycatch si se confirma interacción significativa.",
        "La ejecución identifica valor de conservación, pero no contiene por sí sola un mapa completo de esfuerzo pesquero. Por ello la medida se formula como evaluación dirigida y no como atribución de impacto.",
        "Corto plazo (1–3 años)",
        evidence,
        "Capturas accidentales por unidad de esfuerzo, supervivencia de liberación y solapamiento con núcleos prioritarios",
        "Trabajar con el sector para registrar bycatch, identificar artes/periodos de mayor interacción, ensayar mitigación, formar en manipulación y liberación y valorar restricciones focalizadas si la evidencia lo requiere.",
    ))

    species_names = species.get("Species", pd.Series(dtype="string")).dropna().astype(str) if species is not None and not species.empty else pd.Series(dtype="string")
    if species_names.str.contains(r"^Hippocampus\b", case=False, regex=True).any():
        measures.append(_measure(
            "Extracción, manipulación y perturbación recreativa",
            "Prevenir la extracción deliberada y la manipulación innecesaria de caballitos de mar y evaluar la presión asociada a buceo, fotografía y otras actividades recreativas si son relevantes localmente.",
            "La zona contiene al menos una especie del género Hippocampus en los resultados de esta ejecución. La presencia no demuestra que exista extracción o perturbación recreativa; por ello la primera acción es verificar la presión y, cuando proceda, aplicar un enfoque preventivo de no captura, no contacto y no reubicación de individuos.",
            "Inmediato y permanente",
            evidence,
            "Incidencias de extracción/manipulación, frecuencia de contactos observados, cumplimiento de códigos de conducta y tendencia de ocupación en puntos de alta frecuentación",
            "Coordinar con centros de buceo, operadores náuticos, vigilancia y programas de ciencia ciudadana; establecer códigos de conducta, comunicación específica y protocolos de no manipulación; reforzar control únicamente cuando se documente una presión relevante.",
        ))

    if depth is None or depth <= 30:
        measures.append(_measure(
            "Obras costeras, dragados, turbidez y sedimentación",
            "Aplicar evaluación reforzada a actuaciones capaces de modificar profundidad, sustrato, turbidez o sedimentación dentro o aguas arriba del núcleo prioritario.",
            "Las poblaciones costeras y someras pueden verse afectadas por alteraciones físicas del fondo y por plumas de sedimento. La existencia de riesgo debe comprobarse proyecto a proyecto.",
            "Permanente",
            evidence,
            "Turbidez, sedimentación, área alterada y respuesta de ocupación/abundancia antes-después",
            "Exigir línea base, ventanas temporales cuando proceda, umbrales operativos de turbidez, seguimiento durante obra y control posterior del hábitat.",
        ))

    measures.append(_measure(
        "Calidad del agua y contaminación",
        "Mantener o recuperar condiciones de calidad del agua compatibles con los hábitats y especies de la zona.",
        "La prioridad ecológica de la zona justifica incorporar nutrientes, materia orgánica, contaminantes, vertidos y episodios de baja calidad del agua al esquema de vigilancia, aun cuando esta ejecución no establezca causalidad con esos factores.",
        "Permanente",
        evidence,
        "Indicadores fisicoquímicos relevantes y estabilidad de hábitat, ocupación y densidad",
        "Coordinar seguimiento biológico con redes de calidad del agua; investigar coincidencias temporales entre deterioro ambiental y cambios biológicos antes de atribuir causalidad.",
    ))

    losses = temporal_summary.get("Pérdida", 0)
    gains = temporal_summary.get("Ganancia", 0)
    persistence = temporal_summary.get("Persistencia", 0)
    if losses > gains and losses > 0:
        measures.append(_measure(
            "Pérdidas temporales y restauración",
            "Priorizar verificación de campo y diagnóstico de causas antes de decidir restauración activa.",
            f"En las comparaciones temporales vinculadas a las celdas de la zona se registran {losses} pérdidas, {gains} ganancias y {persistence} persistencias. Una pérdida de registros no equivale automáticamente a declive poblacional porque puede reflejar esfuerzo o detectabilidad.",
            "Inmediato (0–1 año)",
            evidence,
            "Reocupación de celdas, tendencia estandarizada de abundancia/densidad y estado del hábitat",
            "Repetir prospecciones estandarizadas, revisar esfuerzo histórico y presiones recientes; solo plantear restauración tras identificar y reducir la causa de degradación.",
        ))
    elif gains > losses and gains > 0:
        measures.append(_measure(
            "Consolidación de áreas emergentes",
            "Verificar si las ganancias temporales representan expansión/recuperación real o incremento del esfuerzo y mantener seguimiento reforzado.",
            f"Se observan {gains} ganancias frente a {losses} pérdidas y {persistence} persistencias en las celdas relacionadas con la zona.",
            "Corto plazo (1–3 años)",
            evidence,
            "Persistencia de la ocupación nueva en campañas sucesivas y esfuerzo de observación comparable",
            "Diseñar prospecciones repetidas en las celdas de ganancia y comparar detectabilidad/esfuerzo antes de interpretar expansión biológica.",
        ))

    measures.append(_measure(
        "Conectividad ecológica",
        "Mantener la continuidad entre celdas prioritarias y evaluar corredores hacia zonas próximas.",
        "Las zonas se definen por contigüidad de celdas de prioridad alta/muy alta, pero la conservación efectiva puede depender también de hábitats intermedios y conectividad con otros núcleos.",
        "Medio y largo plazo",
        evidence,
        "Continuidad del hábitat, distancia funcional entre núcleos y persistencia de ocupación",
        "Identificar discontinuidades, evitar nuevas barreras o pérdidas de hábitat en conectores y coordinar gestión cuando las zonas pertenezcan a distintas figuras o administraciones.",
    ))

    if data_adequacy.casefold() in {"baja", "muy baja", "low", "very low", "no calculada"}:
        measures.append(_measure(
            "Reducción de incertidumbre",
            "Aumentar el esfuerzo de validación antes de adoptar medidas restrictivas de gran alcance.",
            f"La suficiencia de información de la zona se clasifica como {data_adequacy}. Una prioridad ecológica alta con soporte limitado debe interpretarse de forma precautoria pero explícitamente incierta.",
            "Inmediato (0–1 año)",
            evidence,
            "Número de campañas/años, cobertura espacial, repetición de detecciones y precisión del hábitat",
            "Realizar prospecciones dirigidas, estandarizadas y repetidas; verificar hábitat y profundidades; actualizar el análisis después de mejorar la base de evidencia.",
        ))

    measures.append(_measure(
        "Seguimiento adaptativo",
        "Implantar un programa de seguimiento específico de la zona con indicadores biológicos, de hábitat, presión y efectividad de gestión.",
        f"La conservación debe poder evaluarse. La zona contiene {len(species)} especies registradas en la tabla específica de esta ejecución y requiere indicadores comparables en el tiempo.",
        "Permanente",
        evidence,
        "Ocupación, abundancia/densidad estandarizada, riqueza, reproducción cuando exista información, estado del hábitat, LCBD/hotspots y presión relevante",
        "Definir línea base, periodicidad, protocolos de campo y umbrales de revisión. Vincular cada medida a un indicador y revisar la estrategia cuando el indicador se deteriore o la incertidumbre cambie.",
    ))
    return measures


def _add_measure_block(document: Document, measure: dict[str, str], number: int) -> None:
    p = document.add_paragraph()
    run = p.add_run(f"Medida {number}. {measure['category']}")
    run.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor.from_string("1F4E79")
    _add_kv_table(document, [
        ("Medida propuesta", measure["action"]),
        ("Justificación", measure["rationale"]),
        ("Horizonte", measure["timeframe"]),
        ("Nivel de evidencia de la zona", measure["evidence"]),
        ("Indicador de seguimiento", measure["indicator"]),
        ("Aplicación práctica", measure["implementation"]),
    ])


def _report_parameters(context: dict[str, object], assigned: pd.DataFrame, selected_grid_km: int, settings: AnalysisSettings) -> list[tuple[str, Any]]:
    species_col = "Species_clean" if "Species_clean" in assigned.columns else "Species"
    species = sorted(assigned.get(species_col, pd.Series(dtype="string")).dropna().astype(str).unique())
    regions = sorted(assigned.get("Region_MITECO", pd.Series(dtype="string")).dropna().astype(str).unique())
    periods = settings.temporal_periods
    period_text = "; ".join(f"{label}: {start} a {end}" for label, start, end in periods) if periods else "Sin comparación temporal configurada"
    return [
        ("Producto", PRODUCT),
        ("Proyecto", PROJECT),
        ("Fecha de ejecución", context.get("creation_date", datetime.now().strftime("%d-%m-%Y"))),
        ("Periodo analizado", f"{context.get('year_min', 'N.D.')}–{context.get('year_max', 'N.D.') }"),
        ("Resolución espacial", f"{selected_grid_km} km"),
        ("Regiones MITECO representadas", " | ".join(regions) if regions else context.get("region_label", "N.D.")),
        ("Especies incluidas", " | ".join(species) if species else "N.D."),
        ("Periodos comparativos", period_text),
        ("Permutaciones", settings.permutations),
        ("Semilla aleatoria", settings.random_seed),
    ]



def _year_series(frame: pd.DataFrame) -> pd.Series:
    """Return calendar year using the actual fields produced by the pipeline."""
    if "Year" in frame.columns:
        years = pd.to_numeric(frame["Year"], errors="coerce")
    elif "year" in frame.columns:
        years = pd.to_numeric(frame["year"], errors="coerce")
    elif "Fecha_aux" in frame.columns:
        years = pd.to_datetime(frame["Fecha_aux"], errors="coerce").dt.year
    elif "Date" in frame.columns:
        years = pd.to_datetime(frame["Date"], errors="coerce").dt.year
    elif "Date of observation" in frame.columns:
        years = pd.to_datetime(frame["Date of observation"], errors="coerce", dayfirst=True).dt.year
    elif "observation_date_parsed" in frame.columns:
        years = pd.to_datetime(frame["observation_date_parsed"], errors="coerce").dt.year
    else:
        years = pd.Series(pd.NA, index=frame.index, dtype="Float64")
    return pd.Series(years, index=frame.index, dtype="Float64")


def _report_effort_frame(frame: pd.DataFrame, species_col: str, context: dict[str, object]) -> pd.DataFrame:
    work = frame.copy()
    work["Year_report"] = _year_series(work)
    work["Abundance_report"] = pd.to_numeric(work.get("N_total"), errors="coerce").fillna(0).clip(lower=0)
    valid = work.dropna(subset=["Year_report"]).copy()
    event_available = "sampling_event_id" in valid.columns and valid["sampling_event_id"].notna().any()
    if valid.empty:
        return pd.DataFrame(columns=["Year", "n_records", "n_sampling_events", "total_abundance", "n_species"])
    valid["Year_report"] = valid["Year_report"].astype(int)
    agg = {
        "n_records": (species_col, "size"),
        "total_abundance": ("Abundance_report", "sum"),
        "n_species": (species_col, "nunique"),
    }
    if event_available:
        agg["n_sampling_events"] = ("sampling_event_id", "nunique")
    summary = valid.groupby("Year_report", observed=True).agg(**agg).reset_index().rename(columns={"Year_report": "Year"})
    if not event_available:
        summary["n_sampling_events"] = np.nan
    start = _num(context.get("year_min"))
    end = _num(context.get("year_max"))
    if start is None:
        start = int(summary["Year"].min())
    if end is None:
        end = int(summary["Year"].max())
    start, end = int(start), int(end)
    if end >= start and end - start <= 300:
        years = pd.DataFrame({"Year": range(start, end + 1)})
        summary = years.merge(summary, on="Year", how="left")
        for col in ("n_records", "total_abundance", "n_species"):
            summary[col] = pd.to_numeric(summary[col], errors="coerce").fillna(0)
        if event_available:
            summary["n_sampling_events"] = pd.to_numeric(summary["n_sampling_events"], errors="coerce").fillna(0)
    return summary.sort_values("Year").reset_index(drop=True)

def _report_region_frame(frame: pd.DataFrame, species_col: str) -> pd.DataFrame:
    if "Region_MITECO" not in frame.columns:
        return pd.DataFrame(columns=["Region_MITECO", "n_records", "total_abundance", "n_species"])
    work = frame.copy()
    work["Abundance_report"] = pd.to_numeric(work.get("N_total"), errors="coerce").fillna(0).clip(lower=0)
    valid = work.dropna(subset=["Region_MITECO"]).copy()
    valid["Region_MITECO"] = valid["Region_MITECO"].astype(str).str.strip()
    valid = valid[valid["Region_MITECO"].ne("")]
    if valid.empty:
        return pd.DataFrame(columns=["Region_MITECO", "n_records", "total_abundance", "n_species"])
    return (
        valid.groupby("Region_MITECO", observed=True)
        .agg(
            n_records=(species_col, "size"),
            total_abundance=("Abundance_report", "sum"),
            n_species=(species_col, "nunique"),
        )
        .reset_index()
        .sort_values(["n_records", "Region_MITECO"], ascending=[False, True], kind="stable")
        .reset_index(drop=True)
    )


def _report_species_frame(descriptive: dict[str, Any]) -> pd.DataFrame:
    frame = descriptive.get("species_global", pd.DataFrame())
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy().rename(columns={
        "frequency_records": "n_records",
        "abundance": "total_abundance",
        "occupied_cells": "n_cells",
        "occupancy_pct_sampled_cells": "occupancy_pct",
    })
    return out


def _report_sex_frame(frame: pd.DataFrame, species_col: str, sex: dict[str, Any]) -> pd.DataFrame:
    required = {"N hembra", "N macho", "N_indeterminado"}
    if required.issubset(frame.columns):
        work = frame.copy()
        work["female"] = pd.to_numeric(work["N hembra"], errors="coerce").fillna(0).clip(lower=0)
        work["male"] = pd.to_numeric(work["N macho"], errors="coerce").fillna(0).clip(lower=0)
        work["indeterminate"] = pd.to_numeric(work["N_indeterminado"], errors="coerce").fillna(0).clip(lower=0)
        work = work[(work[["female", "male", "indeterminate"]].sum(axis=1) > 0)].copy()
        if not work.empty:
            summary = (
                work.groupby(species_col, observed=True)
                .agg(female=("female", "sum"), male=("male", "sum"), indeterminate=("indeterminate", "sum"))
                .reset_index()
                .rename(columns={species_col: "Species"})
            )
            summary["sexed"] = summary["female"] + summary["male"]
            summary["female_proportion"] = summary["female"] / summary["sexed"].replace(0, np.nan)
            return summary.sort_values("Species", kind="stable").reset_index(drop=True)
    source = sex.get("species", pd.DataFrame()) if isinstance(sex, dict) else pd.DataFrame()
    if source is None or source.empty:
        return pd.DataFrame(columns=["Species", "female", "male", "indeterminate", "female_proportion"])
    return source.copy().rename(columns={"females": "female", "males": "male"})



def _species_discussion(frame: pd.DataFrame) -> list[str]:
    if frame is None or frame.empty:
        return ["No existe una síntesis por especie suficiente para interpretar la composición taxonómica de esta ejecución."]
    work = frame.copy()
    for col in ("n_records", "total_abundance", "n_cells", "occupancy_pct"):
        if col in work:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    paragraphs: list[str] = []
    if "total_abundance" in work and work["total_abundance"].notna().any():
        ordered = work.sort_values("total_abundance", ascending=False, kind="stable")
        total = float(ordered["total_abundance"].fillna(0).sum())
        top = ordered.iloc[0]
        top3_share = 100 * float(ordered.head(min(3, len(ordered)))["total_abundance"].fillna(0).sum()) / max(total, 1.0)
        paragraphs.append(
            f"La composición taxonómica no es uniforme. {_clean_text(top.get('Species'))} aporta la mayor abundancia registrada ({_fmt(top.get('total_abundance'),0)} individuos; {_pct(100*float(top.get('total_abundance') or 0)/max(total,1),1)} del total). "
            f"Las tres especies con mayor abundancia reúnen {_pct(top3_share,1)} de los individuos registrados. Esta concentración cuantifica la estructura de la base analizada, pero no debe confundirse con dominancia poblacional sin controlar esfuerzo, detectabilidad y diferencias de hábitat."
        )
    if "n_records" in work and work["n_records"].notna().any():
        rec = work.sort_values("n_records", ascending=False, kind="stable").iloc[0]
        paragraphs.append(
            f"La especie con mayor frecuencia de observación es {_clean_text(rec.get('Species'))}, con {_fmt(rec.get('n_records'),0)} registros. La frecuencia de registros y la abundancia total aportan información distinta: una especie puede aparecer en muchos eventos con pocos individuos por evento o concentrar muchos individuos en un número menor de observaciones."
        )
    if "occupancy_pct" in work and work["occupancy_pct"].notna().any():
        valid = work.dropna(subset=["occupancy_pct"]).sort_values("occupancy_pct", ascending=False, kind="stable")
        broad, restricted = valid.iloc[0], valid.iloc[-1]
        paragraphs.append(
            f"La mayor frecuencia relativa de detección registrada corresponde a {_clean_text(broad.get('Species'))} ({_pct(broad.get('occupancy_pct'))}), mientras que la menor entre las especies calculables corresponde a {_clean_text(restricted.get('Species'))} ({_pct(restricted.get('occupancy_pct'))}). "
            "La frecuencia de detección resume la amplitud espacial registrada dentro del dominio documentado y debe interpretarse junto con el número de celdas con esfuerzo, la resolución seleccionada y la distribución regional de las observaciones."
        )
    return paragraphs

def _add_interpretation(document: Document, paragraphs: Iterable[str], title: str = "Interpretación y discusión") -> None:
    clean = [re.sub(r"\s+", " ", str(p)).strip() for p in paragraphs if str(p).strip()]
    if not clean:
        return
    document.add_heading(title, level=2)
    for text in clean:
        paragraph = document.add_paragraph(text)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def _effort_discussion(frame: pd.DataFrame) -> list[str]:
    if frame is None or frame.empty:
        return ["No existe una serie anual suficiente para caracterizar la intensidad de observación de esta ejecución."]
    work = frame.copy()
    for col in ("Year", "n_records", "n_sampling_events", "total_abundance", "n_species"):
        if col in work:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    event_available = "n_sampling_events" in work.columns and work["n_sampling_events"].notna().any()
    primary = "n_sampling_events" if event_available else "n_records"
    observed = work[work[primary].fillna(0).gt(0)].copy()
    if observed.empty:
        return ["El periodo seleccionado no contiene observaciones asignadas tras los filtros de la ejecución."]
    first, last = int(observed["Year"].min()), int(observed["Year"].max())
    top = observed.sort_values(primary, ascending=False, kind="stable").iloc[0]
    total_primary = float(observed[primary].sum())
    total_records = float(observed["n_records"].fillna(0).sum())
    total_ind = float(observed["total_abundance"].fillna(0).sum())
    top3 = float(observed.nlargest(min(3, len(observed)), primary)[primary].sum())
    zero_years = work.loc[work[primary].fillna(0).eq(0), "Year"].dropna().astype(int).tolist()
    mean_primary = float(observed[primary].mean())
    cv = float(observed[primary].std(ddof=0) / mean_primary) if mean_primary > 0 else np.nan
    heterogeneity = "alta" if np.isfinite(cv) and cv >= 0.75 else "moderada" if np.isfinite(cv) and cv >= 0.40 else "relativamente baja"
    if event_available:
        paragraphs = [
            f"La cobertura temporal efectiva se extiende de {first} a {last}. La mayor intensidad de observación basada en eventos proxy se concentra en {int(top['Year'])}, con {_fmt(top['n_sampling_events'],0)} eventos y {_fmt(top['n_records'],0)} registros. Los tres años con más eventos reúnen {_pct(100*top3/max(total_primary,1),1)} de los eventos de la serie, con heterogeneidad temporal {heterogeneity} (CV de eventos anuales = {_fmt(cv,2) if np.isfinite(cv) else 'N.D.'}).",
            f"En los años con datos se registran {_fmt(total_ind,0)} individuos en {_fmt(total_primary,0)} eventos proxy y {_fmt(total_records,0)} registros. La media descriptiva es {_fmt(total_ind/max(total_primary,1),2)} individuos registrados por evento proxy. Este denominador reduce la dependencia respecto a cómo se fragmentan las observaciones en filas, pero no equivale a tiempo, superficie o probabilidad de detección y, por tanto, no es esfuerzo de muestreo verdadero.",
        ]
    else:
        paragraphs = [
            f"La cobertura temporal efectiva se extiende de {first} a {last}. No está disponible `sampling_event_id` en esta tabla de informe; se muestran {_fmt(total_records,0)} registros como volumen descriptivo de datos, no como esfuerzo de muestreo.",
        ]
    if len(observed) >= 4 and observed["Year"].nunique() > 1 and observed[primary].nunique() > 1:
        rho = observed["Year"].corr(observed[primary], method="spearman")
        if np.isfinite(rho):
            trend = "aumenta hacia los años recientes" if rho > 0.25 else "disminuye hacia los años recientes" if rho < -0.25 else "no muestra un gradiente monotónico marcado"
            metric = "número de eventos proxy" if event_available else "volumen de registros"
            paragraphs.append(f"La relación monotónica entre año y {metric} es Spearman ρ={_fmt(rho,3)} y {trend}. Esta variación de intensidad de observación debe separarse de cualquier tendencia biológica: cambios en plataforma, accesibilidad, participación u organización del registro pueden modificar la serie sin implicar un cambio poblacional equivalente.")
    if "n_species" in observed and observed["n_species"].notna().any():
        rich = observed.sort_values(["n_species", primary], ascending=[False, False], kind="stable").iloc[0]
        paragraphs.append(f"La mayor riqueza anual observada es de {_fmt(rich.get('n_species'),0)} especies en {int(rich['Year'])}. La riqueza anual depende de la comunidad registrada, pero también de la intensidad de observación, la cobertura regional y la variedad de hábitats visitados; debe interpretarse junto con los eventos proxy y la cobertura espacial.")
    caveat = "Los eventos proxy son un ajuste reproducible de intensidad de observación, no una medida directa de esfuerzo ni de detectabilidad. Los cambios de abundancia bruta, tasa por evento o frecuencia de detección deben interpretarse conjuntamente con la cobertura espacial, las fuentes de datos y los criterios de suficiencia temporal."
    if zero_years:
        shown = ", ".join(map(str, zero_years[:12])) + ("…" if len(zero_years) > 12 else "")
        caveat += f" Dentro del intervalo analizado hay años sin eventos/registros ({shown}); se mantienen explícitamente para no ocultar la ausencia de información."
    paragraphs.append(caveat)
    return paragraphs

def _region_discussion(frame: pd.DataFrame) -> list[str]:
    if frame is None or frame.empty:
        return ["No existe información regional suficiente para comparar la cobertura espacial entre demarcaciones MITECO."]
    work = frame.copy()
    for col in ("n_records", "total_abundance", "n_species"):
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)
    total_records = float(work["n_records"].sum())
    total_abundance = float(work["total_abundance"].sum())
    top_records = work.sort_values("n_records", ascending=False, kind="stable").iloc[0]
    low_records = work.sort_values("n_records", ascending=True, kind="stable").iloc[0]
    top_abund = work.sort_values("total_abundance", ascending=False, kind="stable").iloc[0]
    top_rich = work.sort_values(["n_species", "n_records"], ascending=[False, False], kind="stable").iloc[0]
    paragraphs = [
        f"La cobertura regional no es homogénea. {_clean_text(top_records['Region_MITECO'])} concentra {_fmt(top_records['n_records'],0)} registros ({_pct(100*top_records['n_records']/max(total_records,1),1)} del total), mientras que la mayor abundancia registrada corresponde a {_clean_text(top_abund['Region_MITECO'])} con {_fmt(top_abund['total_abundance'],0)} individuos ({_pct(100*top_abund['total_abundance']/max(total_abundance,1),1)}). La mayor riqueza regional observada es de {_fmt(top_rich['n_species'],0)} especies en {_clean_text(top_rich['Region_MITECO'])}.",
    ]
    if len(work) > 1:
        ratio = float(top_records["n_records"] / max(float(low_records["n_records"]), 1.0))
        paragraphs.append(f"La región con menor número de registros es {_clean_text(low_records['Region_MITECO'])}, con {_fmt(low_records['n_records'],0)}. La razón entre el mayor y el menor esfuerzo regional es aproximadamente {_fmt(ratio,1)}:1. Cuanto mayor sea este desequilibrio, menor es la comparabilidad directa de abundancia y riqueza brutas entre regiones.")
    if total_records > 0:
        work["ind_per_record"] = work["total_abundance"] / work["n_records"].replace(0, np.nan)
        valid = work.dropna(subset=["ind_per_record"])
        if not valid.empty:
            hi = valid.sort_values("ind_per_record", ascending=False, kind="stable").iloc[0]
            paragraphs.append(f"El mayor número medio de individuos por registro se observa en {_clean_text(hi['Region_MITECO'])} ({_fmt(hi['ind_per_record'],2)} ind./registro). Esta métrica describe concentración dentro de los eventos observados y ayuda a contextualizar la abundancia total, pero sigue estando condicionada por el tipo de observación y no equivale a densidad ecológica.")
    paragraphs.append("Las diferencias regionales combinan señal biológica y desigualdad de observación. Los contrastes ecológicos deben interpretarse junto con registros, celdas ocupadas, años, profundidad y hábitats representados. Una región con menor esfuerzo no puede considerarse automáticamente menos diversa ni menos importante para conservación.")
    return paragraphs


def _dominance_discussion(frame: pd.DataFrame) -> list[str]:
    if frame is None or frame.empty:
        return []
    work = frame.copy()
    if "relative_abundance_pct" in work:
        work["relative_abundance_pct"] = pd.to_numeric(work["relative_abundance_pct"], errors="coerce")
    if "abundance" in work:
        work["abundance"] = pd.to_numeric(work["abundance"], errors="coerce")
    paragraphs: list[str] = []
    if {"Region_MITECO", "Species"}.issubset(work.columns):
        sort_col = "relative_abundance_pct" if "relative_abundance_pct" in work else "abundance" if "abundance" in work else None
        if sort_col:
            leaders = work.sort_values(sort_col, ascending=False, kind="stable").groupby("Region_MITECO", observed=True).head(1)
            examples = "; ".join(f"{_clean_text(r.get('Region_MITECO'))}: {_clean_text(r.get('Species'))} ({_pct(r.get('relative_abundance_pct')) if 'relative_abundance_pct' in work else _fmt(r.get('abundance'),0)+' ind.'})" for _, r in leaders.head(8).iterrows())
            paragraphs.append(f"La especie dominante no es necesariamente la misma en todas las regiones. Los máximos regionales incluyen {examples}. Este patrón ayuda a distinguir una dominancia nacional agregada de estructuras comunitarias regionalmente diferentes.")
            if "relative_abundance_pct" in work and work["relative_abundance_pct"].notna().any():
                vals = leaders["relative_abundance_pct"].dropna()
                if len(vals):
                    paragraphs.append(f"La abundancia relativa de la especie dominante regional oscila entre {_pct(vals.min(),1)} y {_pct(vals.max(),1)}. Valores muy altos indican comunidades observadas fuertemente concentradas en pocos taxones; valores menores sugieren mayor reparto de la abundancia. Esta interpretación debe cotejarse con Shannon/Pielou y con el esfuerzo regional.")
    return paragraphs

def _sex_discussion(frame: pd.DataFrame) -> list[str]:
    if frame is None or frame.empty:
        return ["No existen individuos con información sexual suficiente para desarrollar una interpretación por especie en esta ejecución."]
    work = frame.copy()
    for col in ("female", "male", "indeterminate", "female_proportion"):
        if col in work:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    total_f = float(work.get("female", pd.Series(dtype=float)).fillna(0).sum())
    total_m = float(work.get("male", pd.Series(dtype=float)).fillna(0).sum())
    total_i = float(work.get("indeterminate", pd.Series(dtype=float)).fillna(0).sum())
    sexed = total_f + total_m
    classified = sexed + total_i
    p = total_f / sexed if sexed > 0 else np.nan
    ind_pct = 100 * total_i / classified if classified > 0 else np.nan
    paragraphs = [
        f"En el conjunto de datos con información sexual se contabilizan {_fmt(total_f,0)} hembras, {_fmt(total_m,0)} machos y {_fmt(total_i,0)} individuos indeterminados. Entre los individuos sexados, la proporción global de hembras es {_fmt(p,2) if np.isfinite(p) else 'N.D.'}. Los indeterminados representan {_pct(ind_pct,1) if np.isfinite(ind_pct) else 'N.D.'} de los individuos con alguna categoría sexual y no forman parte del denominador de la proporción hembras/(hembras+machos).",
        "La proporción observada no debe interpretarse automáticamente como sex ratio poblacional. Puede estar condicionada por detectabilidad diferencial, conducta, temporada reproductiva, hábitat, tamaño corporal, calidad de las imágenes y facilidad para asignar el sexo. Por ello conviene considerar simultáneamente el número de individuos sexados y el porcentaje de indeterminados.",
    ]
    if "female_proportion" in work and work["female_proportion"].notna().any():
        valid = work.dropna(subset=["female_proportion"]).copy()
        valid["sexed_n"] = valid.get("female", 0).fillna(0) + valid.get("male", 0).fillna(0)
        highest = valid.sort_values("female_proportion", ascending=False, kind="stable").iloc[0]
        lowest = valid.sort_values("female_proportion", ascending=True, kind="stable").iloc[0]
        paragraphs.append(f"La proporción de hembras más alta corresponde a {_clean_text(highest.get('Species'))} ({_fmt(highest['female_proportion'],2)}; n sexado={_fmt(highest.get('sexed_n'),0)}) y la más baja a {_clean_text(lowest.get('Species'))} ({_fmt(lowest['female_proportion'],2)}; n sexado={_fmt(lowest.get('sexed_n'),0)}). La diferencia entre proporciones es descriptiva y no debe valorarse sin los tamaños muestrales y las pruebas específicas del bloque sexual.")
        weak = valid[valid["sexed_n"].lt(10)]
        if not weak.empty:
            names = ", ".join(weak["Species"].astype(str).head(8))
            paragraphs.append(f"Hay {len(weak)} especie(s) con menos de 10 individuos sexados ({names}{'…' if len(weak)>8 else ''}). En estas especies, una diferencia de pocos individuos puede cambiar mucho la proporción calculada, por lo que el resultado debe considerarse exploratorio.")
    return paragraphs

def _spatial_discussion(cell_metrics: pd.DataFrame, hotspots: pd.DataFrame, multiscale_summary: pd.DataFrame) -> list[str]:
    paragraphs: list[str] = []
    if cell_metrics is not None and len(cell_metrics):
        cm = pd.DataFrame(cell_metrics).copy()
        for col in ("N_total_celda", "n_especies", "Densidad_total", "n_obs_cell"):
            if col in cm:
                cm[col] = pd.to_numeric(cm[col], errors="coerce")
        parts = []
        if "N_total_celda" in cm and cm["N_total_celda"].notna().any():
            row = cm.loc[cm["N_total_celda"].idxmax()]
            parts.append(f"la mayor abundancia por celda es {_fmt(row['N_total_celda'],0)} individuos en {_clean_text(row.get('grid_id'))}")
            positive = cm["N_total_celda"].fillna(0).clip(lower=0)
            if positive.sum() > 0:
                n_top = max(1, int(math.ceil(0.10 * len(positive))))
                share = 100 * positive.nlargest(n_top).sum() / positive.sum()
                parts.append(f"el 10 % de celdas con mayor abundancia concentra aproximadamente {_pct(share,1)} de los individuos registrados")
        if "n_especies" in cm and cm["n_especies"].notna().any():
            row = cm.loc[cm["n_especies"].idxmax()]
            parts.append(f"la riqueza máxima es de {_fmt(row['n_especies'],0)} especies en {_clean_text(row.get('grid_id'))}")
        if "Densidad_total" in cm and cm["Densidad_total"].notna().any():
            row = cm.loc[cm["Densidad_total"].idxmax()]
            parts.append(f"la densidad registrada máxima alcanza {_fmt(row['Densidad_total'],2)} ind./km² en {_clean_text(row.get('grid_id'))}")
        if parts:
            paragraphs.append("La estructura espacial de la ejecución es heterogénea: " + "; ".join(parts) + ". Estos máximos describen concentración de registros y no estimaciones directas de densidad poblacional.")
    if hotspots is not None and not hotspots.empty:
        h = hotspots.copy()
        counts = []
        for col, label in (("hotspot_richness", "riqueza"), ("hotspot_abundance", "abundancia"), ("hotspot_density", "densidad")):
            if col in h:
                count = int(h[col].fillna(False).astype(bool).sum())
                counts.append(f"{count} de {label}")
        if counts:
            paragraphs.append("Los percentiles altos identifican hotspots específicos de " + ", ".join(counts) + ". La coincidencia de varios tipos de hotspot en una misma celda proporciona una señal más integrada que cualquiera de ellos por separado, aunque sigue siendo sensible al esfuerzo y a la resolución espacial.")
    if multiscale_summary is not None and not multiscale_summary.empty and "scale_km" in multiscale_summary:
        ms = multiscale_summary.copy().sort_values("scale_km")
        smallest, largest = ms.iloc[0], ms.iloc[-1]
        phrases = []
        if "mean_richness" in ms:
            phrases.append(f"la riqueza media pasa de {_fmt(smallest.get('mean_richness'),2)} a {_fmt(largest.get('mean_richness'),2)} especies/celda entre {int(smallest['scale_km'])} y {int(largest['scale_km'])} km")
        if "n_hotspots_significant" in ms:
            phrases.append(f"los hotspots altos y significativos varían de {_fmt(smallest.get('n_hotspots_significant'),0)} a {_fmt(largest.get('n_hotspots_significant'),0)}")
        if phrases:
            paragraphs.append("La síntesis multiescala confirma que los indicadores cambian con el tamaño de celda: " + "; ".join(phrases) + ". Las zonas que mantienen señal a varias escalas son, por definición, menos dependientes de una única resolución y aportan mayor robustez espacial a la priorización.")
    if cell_metrics is not None and len(cell_metrics):
        cm = pd.DataFrame(cell_metrics).copy()
        if {"n_obs_cell", "n_especies"}.issubset(cm.columns):
            pair = cm[["n_obs_cell", "n_especies"]].apply(pd.to_numeric, errors="coerce").dropna()
            if len(pair) >= 5 and pair.nunique().min() > 1:
                rho = pair["n_obs_cell"].corr(pair["n_especies"], method="spearman")
                if np.isfinite(rho):
                    strength = "fuerte" if abs(rho) >= 0.70 else "moderada" if abs(rho) >= 0.40 else "débil"
                    paragraphs.append(f"La asociación entre esfuerzo por celda y riqueza observada es {strength} (Spearman ρ={_fmt(rho,3)}). Una correlación positiva elevada indica que parte del patrón de riqueza puede estar condicionado por intensidad de observación; una correlación débil sugiere mayor independencia entre ambos componentes, sin eliminar otros sesgos de detectabilidad.")
        if {"n_obs_cell", "N_total_celda"}.issubset(cm.columns):
            pair = cm[["n_obs_cell", "N_total_celda"]].apply(pd.to_numeric, errors="coerce").dropna()
            if len(pair) >= 5 and pair.nunique().min() > 1:
                rho = pair["n_obs_cell"].corr(pair["N_total_celda"], method="spearman")
                if np.isfinite(rho):
                    paragraphs.append(f"La asociación entre número de registros y abundancia acumulada por celda es ρ={_fmt(rho,3)}. Este valor ayuda a distinguir concentración biológica de acumulación debida al esfuerzo y justifica interpretar la densidad, la persistencia y las métricas comunitarias junto con la abundancia bruta.")
    paragraphs.append("La interpretación espacial debe separar patrón ecológico y patrón de muestreo. Las celdas con muchos registros tienen mayor probabilidad de acumular especies e individuos; por ello Hispa-Syng combina abundancia, riqueza, densidad, esfuerzo, LCBD, significación y persistencia en lugar de basar la conservación en un único mapa.")
    return paragraphs


def _habitat_depth_discussion(descriptive: dict[str, Any]) -> list[str]:
    paragraphs: list[str] = []
    habitat = descriptive.get("habitat", pd.DataFrame())
    if habitat is not None and not habitat.empty and "Habitat_clean" in habitat:
        h = habitat.copy()
        if "n_records" not in h.columns:
            h["n_records"] = 0.0
        if "abundance" not in h.columns:
            h["abundance"] = pd.to_numeric(h.get("total_abundance", pd.Series(0.0, index=h.index)), errors="coerce")
        h["n_records"] = pd.to_numeric(h["n_records"], errors="coerce").fillna(0)
        h["abundance"] = pd.to_numeric(h["abundance"], errors="coerce").fillna(0)
        total = h.groupby("Habitat_clean", observed=True).agg(records=("n_records", "sum"), abundance=("abundance", "sum")).reset_index()
        all_records = float(total["records"].sum())
        top = total.sort_values("records", ascending=False, kind="stable").iloc[0]
        paragraphs.append(f"El hábitat con mayor representación en los registros clasificados es {_clean_text(top['Habitat_clean'])}, con {_fmt(top['records'],0)} registros ({_pct(100*top['records']/max(all_records,1),1)}) y {_fmt(top['abundance'],0)} individuos. Este predominio describe la muestra disponible y puede reflejar simultáneamente preferencia ecológica, disponibilidad real del hábitat, accesibilidad y frecuencia de prospección.")
        if len(total) > 1:
            second = total.sort_values("records", ascending=False, kind="stable").iloc[1]
            paragraphs.append(f"El segundo hábitat más representado es {_clean_text(second['Habitat_clean'])} con {_fmt(second['records'],0)} registros. La diferencia entre ambos aporta una primera medida de concentración del muestreo por hábitat; cuando pocos hábitats concentran la mayoría de registros, la comparación de preferencias requiere especial cautela.")
        if "Species" in h.columns:
            breadth = h.groupby("Species", observed=True)["Habitat_clean"].nunique().sort_values(ascending=False)
            if len(breadth):
                broad = breadth.index[0]
                narrow = breadth.index[-1]
                paragraphs.append(f"La amplitud de hábitat observada varía entre especies: {_clean_text(broad)} aparece en {int(breadth.iloc[0])} categorías, mientras que {_clean_text(narrow)} aparece en {int(breadth.iloc[-1])}. Esta amplitud es aparente y depende de la cobertura de muestreo; una especie con pocos registros puede parecer especializada simplemente porque ha sido observada en menos contextos.")
    depth = descriptive.get("depth_species", pd.DataFrame())
    if depth is not None and not depth.empty and "depth_median" in depth:
        d = depth.copy()
        for col in ("depth_median","depth_mean","depth_min","depth_max","n_depth_valid"):
            if col in d: d[col]=pd.to_numeric(d[col],errors="coerce")
        valid = d.dropna(subset=["depth_median"])
        if not valid.empty:
            deep = valid.sort_values("depth_median", ascending=False, kind="stable").iloc[0]
            shallow = valid.sort_values("depth_median", ascending=True, kind="stable").iloc[0]
            paragraphs.append(f"La posición batimétrica típica difiere entre especies: {_clean_text(deep.get('Species'))} presenta la mediana más profunda ({_fmt(deep['depth_median'],1)} m; n={_fmt(deep.get('n_depth_valid'),0)}), mientras que {_clean_text(shallow.get('Species'))} presenta la más somera ({_fmt(shallow['depth_median'],1)} m; n={_fmt(shallow.get('n_depth_valid'),0)}). La mediana se prioriza porque reduce la influencia de observaciones extremas.")
            if {"depth_min","depth_max"}.issubset(valid.columns):
                valid["depth_range"] = valid["depth_max"]-valid["depth_min"]
                wide=valid.dropna(subset=["depth_range"]).sort_values("depth_range",ascending=False,kind="stable")
                if not wide.empty:
                    w=wide.iloc[0]
                    paragraphs.append(f"La mayor amplitud batimétrica observada corresponde a {_clean_text(w.get('Species'))}, desde {_fmt(w.get('depth_min'),1)} hasta {_fmt(w.get('depth_max'),1)} m (amplitud {_fmt(w.get('depth_range'),1)} m). Los extremos deben revisarse junto con el tamaño muestral y la calidad de la profundidad, porque una sola observación excepcional puede ampliar mucho el rango.")
    depth_region = descriptive.get("depth_region", pd.DataFrame())
    if depth_region is not None and not depth_region.empty and "depth_median" in depth_region:
        dr=depth_region.copy(); dr["depth_median"]=pd.to_numeric(dr["depth_median"],errors="coerce"); v=dr.dropna(subset=["depth_median"])
        if len(v)>1:
            de=v.sort_values("depth_median",ascending=False,kind="stable").iloc[0]; sh=v.sort_values("depth_median",ascending=True,kind="stable").iloc[0]
            paragraphs.append(f"A escala regional, la mediana de profundidad más alta se registra en {_clean_text(de.get('Region_MITECO'))} ({_fmt(de.get('depth_median'),1)} m) y la más baja en {_clean_text(sh.get('Region_MITECO'))} ({_fmt(sh.get('depth_median'),1)} m). Estas diferencias pueden reflejar disponibilidad de hábitat y geomorfología regional, pero también distintas profundidades de prospección.")
    tests = descriptive.get("depth_tests", pd.DataFrame())
    if tests is not None and not tests.empty and "p_value" in tests:
        valid = tests.copy(); valid["p_value"] = pd.to_numeric(valid["p_value"], errors="coerce")
        sig = valid[valid["p_value"].lt(0.05)]
        if not sig.empty:
            labels = "; ".join((sig.get("test", pd.Series(dtype=str)).astype(str) + " [" + sig.get("group", pd.Series(dtype=str)).astype(str) + "]: p=" + sig["p_value"].map(lambda x:_fmt(x,4))).head(6))
            paragraphs.append(f"Las pruebas exploratorias detectan {len(sig)} contraste(s) con p<0,05, entre ellos {labels}. La significación indica heterogeneidad o asociación en la muestra, pero no identifica por sí sola el mecanismo ecológico responsable; debe interpretarse con tamaños muestrales, magnitud del efecto y gráficos.")
        else:
            paragraphs.append("Las pruebas de profundidad disponibles no detectan contrastes con p<0,05. Esto no demuestra igualdad ecológica entre especies, regiones o hábitats: puede reflejar solapamiento real, elevada variabilidad, muestreo desigual o potencia estadística limitada.")
    if not paragraphs:
        paragraphs.append("La información de hábitat y/o profundidad es insuficiente para desarrollar comparaciones robustas en esta ejecución; esta limitación debe conservarse explícitamente al interpretar distribución y prioridad.")
    paragraphs.append("Hábitat y profundidad deben interpretarse conjuntamente. Una asociación aparente con un hábitat puede deberse a que ese hábitat domina precisamente en el intervalo batimétrico más muestreado. Las conclusiones más robustas son las que se mantienen al comparar especies, regiones y años con esfuerzo suficiente.")
    return paragraphs

def _community_discussion(community: dict[str, Any]) -> list[str]:
    paragraphs: list[str] = []
    primary = community.get("permanova_hellinger", community.get("permanova", {}))
    primary_disp = community.get("betadisper_hellinger", community.get("betadisper", {}))
    incidence = community.get("permanova_jaccard", {})
    sensitivity = community.get("permanova_bray_sensitivity", {})
    if isinstance(primary, dict) and _num(primary.get("p_value")) is not None:
        p = _num(primary.get("p_value")); r2 = _num(primary.get("R2")); f = _num(primary.get("pseudo_F"))
        text = f"El contraste regional principal usa Hellinger–Euclídea y produce pseudo-F={_fmt(f,3)}, p={_fmt(p,4)} y R²={_fmt(r2,3) if r2 is not None else 'N.D.'}."
        dp = _num(primary_disp.get("p_value")) if isinstance(primary_disp, dict) else None
        if dp is not None:
            text += f" Betadisper asociado: p={_fmt(dp,4)}; una dispersión significativa obliga a interpretar con cautela una separación de centroides."
        jp = _num(incidence.get("p_value")) if isinstance(incidence, dict) else None
        bp = _num(sensitivity.get("p_value")) if isinstance(sensitivity, dict) else None
        if jp is not None:
            text += f" El contraste complementario de incidencia Jaccard da p={_fmt(jp,4)}."
        if bp is not None:
            text += f" Bray–Curtis sobre abundancia bruta se conserva solo como sensibilidad (p={_fmt(bp,4)}), porque los totales acumulados dependen fuertemente de la intensidad de observación."
        paragraphs.append(text)
    indicators = community.get("indicators_region", pd.DataFrame())
    if indicators is not None and not indicators.empty:
        ind = indicators.copy()
        ind["IndVal"] = pd.to_numeric(ind.get("IndVal"), errors="coerce")
        ind["p_adjust_BH"] = pd.to_numeric(ind.get("p_adjust_BH"), errors="coerce")
        sig = ind[ind["p_adjust_BH"].lt(0.05)].sort_values(["IndVal", "p_adjust_BH"], ascending=[False, True], kind="stable")
        if not sig.empty:
            examples = "; ".join(f"{_clean_text(r.get('Species'))} → {_clean_text(r.get('indicator_group'))} (IndVal={_fmt(r.get('IndVal'),2)}, qBH={_fmt(r.get('p_adjust_BH'),4)})" for _, r in sig.head(6).iterrows())
            paragraphs.append(f"Tras controlar FDR mediante Benjamini–Hochberg, IndVal identifica {len(sig)} especie(s) indicadora(s): {examples}. Se interpretan como asociaciones regionales de especificidad y fidelidad, no como evidencia de amenaza o prioridad legal.")
        else:
            paragraphs.append("IndVal no identifica especies indicadoras con qBH<0,05. Se conserva el p crudo en las tablas para trazabilidad, pero la inferencia principal utiliza el ajuste FDR.")
    simper = community.get("simper_region", pd.DataFrame())
    if simper is not None and not simper.empty:
        s = simper.copy(); s["contribution_pct"] = pd.to_numeric(s.get("contribution_pct"), errors="coerce")
        top = s.sort_values("contribution_pct", ascending=False, kind="stable").head(6)
        examples = "; ".join(f"{_clean_text(r.get('Species'))} ({_fmt(r.get('contribution_pct'),1)} %)" for _, r in top.iterrows())
        paragraphs.append(f"SIMPER se mantiene como descomposición descriptiva de la disimilitud; las contribuciones más altas incluyen {examples}. No se usa como prueba inferencial independiente.")
    core = community.get("core_satellite", pd.DataFrame())
    if core is not None and not core.empty and "occupancy_class" in core:
        counts = core["occupancy_class"].astype(str).value_counts()
        paragraphs.append(f"La clasificación de frecuencia de detección es relativa a esta ejecución: {int(counts.get('High-occupancy',0))} especie(s) de detección relativa alta y {int(counts.get('Low-occupancy',0))} de detección relativa baja. Estos nombres sustituyen la interpretación fuerte de 'core/satellite'.")
    paragraphs.append("La interpretación comunitaria debe apoyarse conjuntamente en incidencia, composición relativa, dispersión, soporte de eventos y sensibilidad del método; ninguna métrica aislada se considera evidencia independiente suficiente.")
    return paragraphs

def _regional_diversity_discussion(descriptive: dict[str, Any]) -> list[str]:
    frame = descriptive.get("community_region", pd.DataFrame())
    if frame is None or frame.empty:
        return []
    work = frame.copy()
    for col in ("richness", "abundance", "shannon", "simpson", "pielou"):
        if col in work:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    paragraphs: list[str] = []
    if "shannon" in work and work["shannon"].notna().any():
        hi = work.sort_values("shannon", ascending=False, kind="stable").iloc[0]
        lo = work.dropna(subset=["shannon"]).sort_values("shannon", ascending=True, kind="stable").iloc[0]
        paragraphs.append(f"La diversidad de Shannon alcanza su máximo regional en {_clean_text(hi.get('Region_MITECO'))} (H'={_fmt(hi.get('shannon'),3)}) y su mínimo calculable en {_clean_text(lo.get('Region_MITECO'))} (H'={_fmt(lo.get('shannon'),3)}). Shannon integra riqueza y reparto de abundancias, por lo que dos regiones con igual riqueza pueden diferir si una está más dominada por una sola especie.")
    if "pielou" in work and work["pielou"].notna().any():
        hi = work.sort_values("pielou", ascending=False, kind="stable").iloc[0]
        lo = work.dropna(subset=["pielou"]).sort_values("pielou", ascending=True, kind="stable").iloc[0]
        paragraphs.append(f"La equitatividad de Pielou varía entre {_fmt(lo.get('pielou'),3)} y {_fmt(hi.get('pielou'),3)}. El valor más alto corresponde a {_clean_text(hi.get('Region_MITECO'))}; una equitatividad baja indica mayor concentración de abundancia entre pocas especies, mientras que valores próximos a 1 reflejan un reparto más uniforme en la muestra observada.")
    paragraphs.append("Los índices de diversidad comunitaria son descriptivos del conjunto observado. Deben compararse con esfuerzo, cobertura de hábitat y número de celdas, porque la riqueza y la diversidad tienden a aumentar cuando se amplía el muestreo o se incorporan más tipos de hábitat.")
    return paragraphs

def _biogeography_discussion(community: dict[str, Any]) -> list[str]:
    paragraphs: list[str] = []
    net = community.get("network_metrics", pd.DataFrame())
    if net is not None and not net.empty and {"metric", "value"}.issubset(net.columns):
        lookup = dict(zip(net["metric"].astype(str), net["value"]))
        ari = _num(lookup.get("ARI_region_cluster")); threshold = _num(lookup.get("similarity_threshold")); edges = _num(lookup.get("edges")); nodes = _num(lookup.get("nodes"))
        paragraphs.append(f"La red Louvain es exploratoria y contiene {_fmt(nodes,0) if nodes is not None else 'N.D.'} nodos y {_fmt(edges,0) if edges is not None else 'N.D.'} aristas; ARI región–clúster={_fmt(ari,3) if ari is not None else 'N.D.'} y umbral de similitud={_fmt(threshold,3) if threshold is not None else 'N.D.'}.")
    cp = community.get("permanova_clusters", {})
    if isinstance(cp, dict) and _num(cp.get("p_value")) is not None:
        paragraphs.append(f"La PERMANOVA entre clústeres produce pseudo-F={_fmt(cp.get('pseudo_F'),3)}, p={_fmt(cp.get('p_value'),4)} y R²={_fmt(cp.get('R2'),3)}. Se presenta exclusivamente como caracterización post hoc: los clústeres fueron construidos a partir de la misma información composicional, por lo que este p-valor no constituye validación confirmatoria independiente.")
    ci = community.get("indicators_cluster", pd.DataFrame())
    if ci is not None and not ci.empty:
        paragraphs.append("IndVal entre clústeres se conserva para describir qué especies caracterizan los grupos, pero sus p-valores son post hoc y no se interpretan como confirmación independiente de la partición Louvain.")
    sensitivity = community.get("threshold_sensitivity", pd.DataFrame())
    if sensitivity is not None and not sensitivity.empty and "n_clusters" in sensitivity:
        vals = pd.to_numeric(sensitivity["n_clusters"], errors="coerce").dropna()
        if len(vals):
            paragraphs.append(f"La sensibilidad del umbral genera entre {_fmt(vals.min(),0)} y {_fmt(vals.max(),0)} clústeres; la estabilidad frente a estas alternativas es más informativa que una única partición.")
    decay = community.get("distance_decay_summary", {})
    if isinstance(decay, dict):
        rho = _num(decay.get("mantel_rho")); p = _num(decay.get("mantel_p_value")); jr = _num(decay.get("mantel_rho_jaccard")); jp = _num(decay.get("mantel_p_value_jaccard")); slope = _num(decay.get("slope")); r2 = _num(decay.get("r_squared"))
        if rho is not None:
            paragraphs.append(f"El distance-decay se contrasta mediante Mantel-Spearman entre distancia geográfica y distancia comunitaria Hellinger (ρ={_fmt(rho,3)}, p={_fmt(p,4) if p is not None else 'N.D.'}); el contraste Jaccard da ρ={_fmt(jr,3) if jr is not None else 'N.D.'}, p={_fmt(jp,4) if jp is not None else 'N.D.'}. La pendiente lineal={_fmt(slope,5) if slope is not None else 'N.D.'} y R²={_fmt(r2,3) if r2 is not None else 'N.D.'} se conservan solo como descriptores porque los pares de celdas no son independientes.")
    paragraphs.append("NMDS, red Louvain, concordancia regional y distance-decay son líneas complementarias. Las agrupaciones de red deben considerarse unidades exploratorias de síntesis y no unidades biogeográficas confirmadas por el mismo conjunto de datos que las generó.")
    return paragraphs

def _lcbd_discussion(community: dict[str, Any]) -> list[str]:
    lcbd = community.get("lcbd", pd.DataFrame())
    if lcbd is None or lcbd.empty:
        return ["No se dispone de LCBD calculable para esta ejecución."]
    l = lcbd.copy(); l["LCBD"] = pd.to_numeric(l.get("LCBD"), errors="coerce"); l["LCBD_hellinger"] = pd.to_numeric(l.get("LCBD_hellinger"), errors="coerce")
    sig = l.get("significant_FDR", pd.Series(False, index=l.index)).fillna(False).astype(bool)
    sig_h = l.get("LCBD_hellinger_significant_FDR", pd.Series(False, index=l.index)).fillna(False).astype(bool)
    supported = l.get("support_events_ge2", pd.Series(False, index=l.index)).fillna(False).astype(bool)
    top = l.dropna(subset=["LCBD"]).sort_values("LCBD", ascending=False, kind="stable").head(1)
    paragraphs: list[str] = []
    if not top.empty:
        r = top.iloc[0]
        paragraphs.append(f"El mayor LCBD-Jaccard corresponde a la celda {_clean_text(r.get('grid_id'))} (LCBD={_fmt(r.get('LCBD'),5)}, p={_fmt(r.get('LCBD_p_value'),4)}, qBH={_fmt(r.get('LCBD_p_adjust_BH'),4)}).")
    paragraphs.append(f"Tras BH-FDR, {int(sig.sum())} celdas son significativas para LCBD-Jaccard y {int(sig_h.sum())} para LCBD-Hellinger. {int(supported.sum())} de {len(l)} celdas tienen al menos dos eventos proxy de observación. La concordancia entre Jaccard y Hellinger se exporta explícitamente y se considera más robusta que cualquiera de las dos versiones aisladas.")
    paragraphs.append("Un LCBD alto mide singularidad composicional observada, no valor de conservación automático. Las celdas con pocos eventos pueden parecer singulares por detectabilidad incompleta; por ello el soporte de observación debe mantenerse separado del valor de LCBD.")
    return paragraphs

def _temporal_discussion(temporal: dict[str, Any]) -> list[str]:
    paragraphs: list[str] = []
    ps=temporal.get("period_summary",pd.DataFrame())
    if ps is not None and not ps.empty and {"period","n_sampling_events_period"}.issubset(ps.columns):
        p=ps.copy(); p["n_sampling_events_period"]=pd.to_numeric(p["n_sampling_events_period"],errors="coerce"); p["abundance"]=pd.to_numeric(p.get("abundance"),errors="coerce")
        agg=p.groupby("period",observed=True).agg(events=("n_sampling_events_period","first"),abundance=("abundance","sum")).reset_index()
        if len(agg):
            hi=agg.sort_values("events",ascending=False,kind="stable").iloc[0]; lo=agg.sort_values("events",ascending=True,kind="stable").iloc[0]
            paragraphs.append(f"La intensidad de observación agregada por periodos no es necesariamente equivalente: {_clean_text(hi['period'])} reúne {_fmt(hi['events'],0)} eventos proxy, frente a {_fmt(lo['events'],0)} en {_clean_text(lo['period'])}. Por ello, la tasa principal se expresa por evento proxy y se contrasta con frecuencia de detección y densidad anualizada; no representa esfuerzo de muestreo verdadero ni detectabilidad corregida.")
    comparisons = temporal.get("comparisons", pd.DataFrame())
    if comparisons is not None and not comparisons.empty:
        c = comparisons.copy(); c["relative_change_abundance_pct"] = pd.to_numeric(c.get("relative_change_abundance_pct"), errors="coerce"); valid = c.dropna(subset=["relative_change_abundance_pct"])
        if not valid.empty:
            inc = valid.sort_values("relative_change_abundance_pct", ascending=False, kind="stable").iloc[0]; dec = valid.sort_values("relative_change_abundance_pct", ascending=True, kind="stable").iloc[0]
            paragraphs.append(f"Usando el proxy de eventos, la mayor variación positiva de la tasa relativa de observación corresponde a {_clean_text(inc.get('Species'))} en {_clean_text(inc.get('comparison'))} ({_fmt(inc.get('relative_change_abundance_pct'),1)} %), mientras que la mayor variación negativa corresponde a {_clean_text(dec.get('Species'))} ({_fmt(dec.get('relative_change_abundance_pct'),1)} %). Estas magnitudes son índices comparativos de la ejecución, no tasas demográficas.")
            pcol="p_adjust_BH" if "p_adjust_BH" in valid else "p_value" if "p_value" in valid else None
            if pcol:
                pv=pd.to_numeric(valid[pcol],errors="coerce"); nsig=int(pv.lt(0.05).sum()); paragraphs.append(f"Considerando {pcol}, {nsig} de {pv.notna().sum()} comparaciones calculables presentan p<0,05. La significación estadística no sustituye la evaluación de magnitud, comparabilidad de la intensidad de observación y coherencia con frecuencia de detección/densidad.")
    changes = temporal.get("cell_changes", pd.DataFrame())
    if changes is not None and not changes.empty and "status" in changes:
        counts = changes["status"].astype(str).value_counts(); gain=int(counts.get("Ganancia",counts.get("Gain",0))); loss=int(counts.get("Pérdida",counts.get("Loss",0))); persist=int(counts.get("Persistencia",counts.get("Persistence",0))); noncomp=int(counts.get("No comparable",0)); both=int(counts.get("Ausencia en ambos",counts.get("Absent in both",0))); comparable=gain+loss+persist+both
        paragraphs.append(f"A escala de celda se registran {gain} ganancias, {loss} pérdidas y {persist} persistencias; {noncomp} casos son no comparables por muestreo insuficiente. Entre los casos comparables, persistencia representa {_pct(100*persist/max(comparable,1),1)}. La persistencia repetida aporta más evidencia de estabilidad espacial que una detección aislada, mientras que las pérdidas requieren verificación antes de interpretarse como desaparición biológica.")
    ranking = temporal.get("ranking", pd.DataFrame())
    if ranking is not None and hasattr(ranking, "empty") and not ranking.empty:
        r=ranking.copy(); rankcol="temporal_priority_rank" if "temporal_priority_rank" in r else None
        if rankcol:
            rr=pd.to_numeric(r[rankcol],errors="coerce"); r=r.assign(_rank=rr).dropna(subset=["_rank"]).sort_values("_rank")
            if not r.empty:
                top=r.iloc[0]; paragraphs.append(f"La mayor prioridad temporal corresponde a {_clean_text(top.get('Species'))} (rango {_fmt(top.get('_rank'),0)}; dirección {_clean_text(top.get('trend_direction'))}; score {_fmt(top.get('temporal_priority_score'),3)}). El ranking combina cambio y variabilidad observacional y sirve para ordenar necesidades de seguimiento, no para declarar automáticamente declive o recuperación.")
    if not paragraphs:
        paragraphs.append("No se configuró una comparación temporal con resultados suficientes. El informe mantiene la cobertura anual y la intensidad de observación, pero evita inferir expansión, retracción o cambio poblacional sin periodos comparables.")
    paragraphs.append("Cualquier interpretación temporal debe contrastarse con el número de eventos proxy, duración efectiva de los periodos, celdas muestreadas, detectabilidad, cambios de plataforma/fuente y distribución regional. La tasa por evento es un índice relativo de observación, no una tendencia poblacional corregida por detectabilidad.")
    return paragraphs

def _functional_discussion(functional: dict[str, Any]) -> list[str]:
    if not functional.get("available"):
        return ["La diversidad funcional no puede discutirse porque los rasgos disponibles o el soporte de especies son insuficientes. Esto no afecta a los análisis taxonómicos."]
    fr = functional.get("results", pd.DataFrame())
    if fr is None or fr.empty:
        return ["La diversidad funcional figura como disponible, pero no existen filas regionales calculables para una interpretación adicional."]
    work = fr.copy()
    for metric in ("FRic_relative", "FEve", "FDiv", "FDis", "RaoQ", "trait_coverage_fraction"):
        if metric in work:
            work[metric] = pd.to_numeric(work[metric], errors="coerce")
    paragraphs: list[str] = []
    space = functional.get("space_diagnostics", pd.DataFrame())
    if isinstance(space, pd.DataFrame) and not space.empty:
        row = space.iloc[0]
        paragraphs.append(
            "El espacio funcional se construyó únicamente con especies presentes en esta ejecución, utilizando "
            f"{_fmt(row.get('traits_variable_used'),0)} rasgos variables y una dimensionalidad común de "
            f"{_fmt(row.get('functional_dimensions_common'),0)} ejes PCoA para todas las regiones comparables. "
            f"Los ejes retenidos explican {_pct(100 * float(row.get('positive_inertia_explained_common_axes'))) if pd.notna(row.get('positive_inertia_explained_common_axes')) else 'N.D.'} de la inercia positiva corregida. "
            f"Corrección PCoA: {_clean_text(row.get('pcoa_correction'), 'ninguna')}."
        )
    valid_fric = work.dropna(subset=["FRic_relative"]) if "FRic_relative" in work else pd.DataFrame()
    if not valid_fric.empty:
        top = valid_fric.sort_values("FRic_relative", ascending=False, kind="stable").iloc[0]
        low = valid_fric.sort_values("FRic_relative", ascending=True, kind="stable").iloc[0]
        paragraphs.append(
            f"La riqueza funcional relativa es máxima en {_clean_text(top.get('Region_MITECO'))} "
            f"({_fmt(top.get('FRic_relative'),3)}) y mínima entre las regiones estimables en "
            f"{_clean_text(low.get('Region_MITECO'))} ({_fmt(low.get('FRic_relative'),3)}). "
            "Estos valores son directamente comparables porque todos los FRic regionales usan la misma dimensionalidad y se expresan respecto al casco funcional global de las especies seleccionadas."
        )
    valid_fdis = work.dropna(subset=["FDis"]) if "FDis" in work else pd.DataFrame()
    if not valid_fdis.empty:
        hi = valid_fdis.sort_values("FDis", ascending=False, kind="stable").iloc[0]
        paragraphs.append(
            f"FDis basado en incidencia alcanza su máximo en {_clean_text(hi.get('Region_MITECO'))} "
            f"({_fmt(hi.get('FDis'),3)}). FDis se calcula con la corrección de Anderson para los ejes PCoA negativos del espacio Gower original."
        )
    valid_rao = work.dropna(subset=["RaoQ"]) if "RaoQ" in work else pd.DataFrame()
    if not valid_rao.empty:
        hi = valid_rao.sort_values("RaoQ", ascending=False, kind="stable").iloc[0]
        paragraphs.append(
            f"RaoQ basado en incidencia alcanza su máximo en {_clean_text(hi.get('Region_MITECO'))} "
            f"({_fmt(hi.get('RaoQ'),3)}), integrando las distancias Gower por pares entre las especies registradas en la región."
        )
    if "trait_coverage_fraction" in work and work["trait_coverage_fraction"].notna().any():
        min_cov = float(work["trait_coverage_fraction"].dropna().min())
        paragraphs.append(
            f"La cobertura regional de rasgos se informa de forma explícita; la cobertura mínima entre las regiones representadas es {_pct(100 * min_cov,1)}. "
            "Las especies con rasgos obligatorios incompletos se excluyen de las métricas funcionales en lugar de imputarse silenciosamente."
        )
    paragraphs.append(
        "Las métricas funcionales principales se basan en incidencia, con el mismo peso para cada especie registrada. "
        "Las variantes ponderadas por abundancia observada se exportan únicamente como análisis de sensibilidad porque N_total acumulado está fuertemente condicionado por la intensidad de observación. "
        "La diversidad funcional complementa, pero no sustituye, a la diversidad taxonómica y actualmente no se utiliza como puntuación directa de prioridad de conservación."
    )
    return paragraphs

def _conservation_discussion(zones: pd.DataFrame) -> list[str]:
    if zones is None or zones.empty:
        return ["La ejecución no delimita zonas de prioridad ecológica alta o muy alta; por tanto, no procede desarrollar medidas espaciales específicas a escala de zona. Esto no significa ausencia de valor ecológico: puede reflejar que no existan familias de evidencia ecológica estimables, ausencia de capacidad discriminante o que ninguna celda alcance los umbrales fijos de prioridad Alta/Muy alta. La suficiencia de datos se informa de forma independiente y no determina por sí sola esta ausencia de zonas."]
    z=zones.copy()
    z["pct_zone_protected"]=pd.to_numeric(z.get("pct_zone_protected"),errors="coerce")
    z["ecological_priority_score_mean"]=pd.to_numeric(z.get("ecological_priority_score_mean"),errors="coerce")
    z["area_zone_km2"]=pd.to_numeric(z.get("area_zone_km2"),errors="coerce")
    evaluated=z["pct_zone_protected"].notna()
    unprotected=int((evaluated & z["pct_zone_protected"].lt(5)).sum())
    partial=int((evaluated & z["pct_zone_protected"].between(5,50,inclusive="left")).sum())
    high=int((evaluated & z["pct_zone_protected"].ge(50)).sum())
    not_evaluated=int((~evaluated).sum())
    top=z.sort_values("ecological_priority_score_mean",ascending=False,kind="stable").iloc[0]
    total_area=float(z["area_zone_km2"].fillna(0).sum())
    core_total=int(pd.to_numeric(z.get("n_core_cells",pd.Series(dtype=float)),errors="coerce").fillna(0).sum())
    extension_total=int(pd.to_numeric(z.get("n_extension_cells",pd.Series(dtype=float)),errors="coerce").fillna(0).sum())
    paragraphs=[f"La ejecución delimita {len(z)} zonas prioritarias estratégicas que suman {_fmt(total_area,2)} km² de superficie marina. Todas están ancladas en al menos un núcleo de prioridad Alta/Muy alta; en conjunto contienen {core_total} núcleos y {extension_total} extensiones Media de apoyo. Estas extensiones solo se incorporan por contigüidad rook directa y soporte mínimo, no crean zonas por sí solas ni modifican la clase ecológica zonal, que se calcula únicamente a partir de los núcleos. Dos unidades que solo se tocan por un vértice no se unen."]
    if evaluated.any():
        eval_area=z.loc[evaluated,"area_zone_km2"].fillna(0)
        denom=max(float(eval_area.sum()),1e-12)
        weighted=float((z.loc[evaluated,"pct_zone_protected"].fillna(0)*eval_area).sum()/denom)
        paragraphs.append(f"Entre las {int(evaluated.sum())} zonas con protección evaluable, {unprotected} presentan cobertura <5 %, {partial} cobertura 5–<50 % y {high} al menos 50 %. La cobertura media ponderada por superficie evaluada es aproximadamente {_pct(weighted,1)}. {not_evaluated} zonas quedan explícitamente como no evaluadas por falta de una capa válida de protección.")
    else:
        paragraphs.append("La cobertura de áreas protegidas no pudo evaluarse en esta ejecución. Los valores ausentes no se interpretan como 0 % de protección ni como ausencia de solape.")
    paragraphs.append(f"La zona con mayor índice ecológico medio es {_clean_text(top.get('zone_id'))}, con {_fmt(top.get('ecological_priority_score_mean'),1)} puntos. Este índice es relativo a la selección de la ejecución actual y no constituye una categoría legal o una estimación de valor de conservación absoluto.")
    if "data_adequacy_class_zone" in z:
        col="data_adequacy_class_zone"
        counts=z[col].astype(str).value_counts(); label=counts.index[0] if len(counts) else None
        if label: paragraphs.append(f"La clase de suficiencia de datos más frecuente es {_clean_text(label)} ({int(counts.iloc[0])} zonas). La suficiencia se mantiene separada de la evidencia ecológica y resume soporte real en eventos, años, escalas y coberturas observacionales.")
    if "sensitivity_class_zone" in z:
        counts=z["sensitivity_class_zone"].astype(str).value_counts(); label=counts.index[0] if len(counts) else None
        if label: paragraphs.append(f"La sensibilidad ecológica se resume principalmente como {_clean_text(label)} ({int(counts.iloc[0])} zonas). Los tres escenarios comparan ponderaciones de riqueza, persistencia temporal, uso recurrente y representación repetida de especies de baja ocupación; mantienen los mismos requisitos de convergencia.")
    paragraphs.append("La señal temporal se utiliza exclusivamente para priorizar necesidades de seguimiento y no modifica la prioridad ecológica. Las medidas propuestas requieren confirmar presión local, competencia regulatoria, proporcionalidad y validez de los datos antes de cualquier aplicación administrativa.")
    return paragraphs

def build_integrated_technical_report(
    *,
    run_root: Path,
    output_dir: Path,
    context: dict[str, object],
    assigned: pd.DataFrame,
    occupied_cells: pd.DataFrame,
    cell_metrics: pd.DataFrame,
    selected_grid_km: int,
    settings: AnalysisSettings,
    descriptive: dict[str, Any],
    community: dict[str, Any],
    functional: dict[str, Any],
    multiscale: dict[str, Any],
    sex: dict[str, Any],
    temporal: dict[str, Any],
    conservation: dict[str, Any],
    quality_control_path: Path | None = None,
    runtime_warning_rows: list[dict[str, Any]] | None = None,
) -> Path:
    """Genera el informe técnico integral de la ejecución actual."""

    LOGGER.info("    [8/8 · 1/4] Preparación del documento y parámetros")

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "Informe_Tecnico_Integral_Hispa-Syng_v1.0_ES.docx"
    document = Document()
    section = document.sections[0]
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.7)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(1.8)
    _style_document(document)

    # Portada
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(PRODUCT)
    r.bold = True
    r.font.size = Pt(28)
    r.font.color.rgb = RGBColor.from_string("17365D")
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(TITLE)
    r.bold = True
    r.font.size = Pt(22)
    r.font.color.rgb = RGBColor.from_string("1F4E79")
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(PROJECT)
    r.font.size = Pt(14)
    r.italic = True
    document.add_paragraph("")
    _add_kv_table(document, _report_parameters(context, assigned, selected_grid_km, settings), digits=0)
    document.add_paragraph("")
    note = document.add_paragraph(
        "Informe generado automáticamente al finalizar la ejecución, utilizando exclusivamente los datos filtrados y los resultados, tablas, modelos, figuras y controles de calidad producidos por esta misma ejecución. No se realizan consultas externas ni se incorporan resultados de otras ejecuciones."
    )
    note.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    document.add_page_break()

    # Índice descriptivo
    document.add_heading("Contenido", level=1)
    for item in (
        "1. Resumen ejecutivo", "2. Datos y metodología", "3. Descripción general del conjunto de datos",
        "4. Distribución espacial", "5. Hábitat y profundidad", "6. Estructura de la comunidad",
        "7. Biogeografía", "8. LCBD y singularidad ecológica", "9. Cambios temporales",
        "10. Diversidad funcional", "11. Zonas prioritarias de conservación y medidas de protección",
        "12. Discusión integrada, limitaciones y precauciones", "13. Conclusiones", "14. Trazabilidad y anexos",
    ):
        document.add_paragraph(item)
    document.add_page_break()

    # Datos básicos
    LOGGER.info("    [8/8 · 2/4] Síntesis de tablas, resultados y figuras")
    assigned_df = pd.DataFrame(assigned.drop(columns="geometry", errors="ignore")).copy()
    species_col = "Species_clean" if "Species_clean" in assigned_df.columns else "Species"
    # Tablas de informe derivadas de los campos reales de esta ejecución.
    # Se calculan aquí para no depender de alias internos distintos entre módulos.
    report_effort = _report_effort_frame(assigned_df, species_col, context)
    report_regions = _report_region_frame(assigned_df, species_col)
    report_species = _report_species_frame(descriptive)
    report_sex = _report_sex_frame(assigned_df, species_col, sex)
    total_records = len(assigned_df)
    total_individuals = pd.to_numeric(assigned_df.get("N_total"), errors="coerce").fillna(0).clip(lower=0).sum()
    n_species = assigned_df.get(species_col, pd.Series(dtype="string")).dropna().astype(str).nunique()
    n_cells = assigned_df.get("grid_id", pd.Series(dtype="string")).dropna().astype(str).nunique()
    n_year_metric = "n_sampling_events" if (not report_effort.empty and "n_sampling_events" in report_effort.columns and report_effort["n_sampling_events"].notna().any()) else "n_records"
    n_years = int((pd.to_numeric(report_effort[n_year_metric], errors="coerce").fillna(0) > 0).sum()) if not report_effort.empty else 0
    zones = conservation.get("zone_summary", pd.DataFrame()).copy()
    operational_zones = conservation.get("operational_zone_summary", pd.DataFrame()).copy()
    n_zones = len(zones)
    n_operational_zones = len(operational_zones)
    protected_counts = pd.to_numeric(zones.get("n_protected_areas_overlap"), errors="coerce") if not zones.empty else pd.Series(dtype=float)
    n_unprotected = int(protected_counts.fillna(0).eq(0).sum()) if len(protected_counts) else 0
    n_low_protection = int(pd.to_numeric(zones.get("pct_zone_protected"), errors="coerce").fillna(0).lt(50).sum()) if not zones.empty else 0

    document.add_heading("1. Resumen ejecutivo", level=1)
    document.add_paragraph(
        f"La ejecución analizó {total_records:,} registros".replace(",", ".")
        + f" y {_fmt(total_individuals, 0)} individuos correspondientes a {n_species} especies, distribuidos en {n_cells} celdas marinas de {selected_grid_km} km y {n_years} años con información. "
        + f"El análisis de conservación delimitó {n_zones} zonas prioritarias estratégicas y {n_operational_zones} zonas operativas de conservación; {n_unprotected} zonas estratégicas no presentan solapamiento detectado con áreas protegidas y {n_low_protection} tienen menos del 50 % de su superficie marina cubierta por protección en las capas disponibles."
    )
    _add_kv_table(document, [
        ("Registros validados y asignados", total_records),
        ("Individuos registrados", total_individuals),
        ("Especies detectadas", n_species),
        ("Celdas ocupadas", n_cells),
        ("Años con datos", n_years),
        ("Zonas prioritarias estratégicas", n_zones),
        ("Zonas operativas de conservación", n_operational_zones),
        ("Zonas sin solape protegido", n_unprotected),
        ("Zonas con <50 % protegido", n_low_protection),
    ], digits=0)
    if report_species is not None and not report_species.empty:
        document.add_heading("Síntesis por especie", level=2)
        _add_df_table(document, report_species, [
            ("Species", "Especie"), ("n_records", "Registros"), ("total_abundance", "Individuos"),
            ("n_cells", "Celdas"), ("occupancy_pct", "Frecuencia de detección registrada (%)"),
        ], max_rows=30, sort_by="total_abundance", ascending=False, digits=1)
        top = report_species.sort_values("total_abundance", ascending=False, kind="stable").iloc[0]
        document.add_paragraph(
            f"La especie con mayor abundancia registrada es {_clean_text(top.get('Species'))}, con {_fmt(top.get('total_abundance'),0)} individuos en {_fmt(top.get('n_records'),0)} registros y presencia en {_fmt(top.get('n_cells'),0)} celdas. Esta dominancia describe el conjunto de datos filtrado y no debe interpretarse de forma aislada como dominancia poblacional real."
        )
        _add_interpretation(document, _species_discussion(report_species), title="Interpretación de la composición por especies")
    document.add_heading("Hallazgos principales de la ejecución", level=2)
    executive_findings = []
    for group in (
        _effort_discussion(report_effort),
        _region_discussion(report_regions),
        _spatial_discussion(pd.DataFrame(cell_metrics) if cell_metrics is not None else pd.DataFrame(), community.get("hotspots", pd.DataFrame()), multiscale.get("summary", pd.DataFrame())),
        _community_discussion(community),
        _temporal_discussion(temporal),
        _conservation_discussion(zones),
    ):
        if group:
            executive_findings.append(group[0])
    for finding in executive_findings:
        document.add_paragraph(finding, style="List Bullet")
    document.add_paragraph(
        "Las interpretaciones deben leerse conjuntamente con el esfuerzo de observación, la detectabilidad, la cobertura espacial y temporal y la precisión de las variables ambientales. Presencia y abundancia registrada no equivalen necesariamente a abundancia poblacional real."
    )

    # Metodología
    document.add_heading("2. Datos y metodología", level=1)
    document.add_paragraph(
        "Hispa-Syng aplica los filtros de años, resolución, región y especies seleccionados al inicio de la ejecución. Las observaciones se asignan a la malla marina oficial MITECO y los cálculos de densidad utilizan la superficie marina validada de cada celda, excluyendo la fracción terrestre."
    )
    _add_kv_table(document, _report_parameters(context, assigned_df, selected_grid_km, settings), digits=0)
    document.add_heading("Esfuerzo y métricas", level=2)
    document.add_paragraph(
        "El informe integra abundancia, riqueza, densidad, frecuencia de detección registrada y soporte temporal; profundidad y hábitat; composición comunitaria; diversidad beta y sus componentes turnover/nestedness; LCBD; especies indicadoras mediante IndVal; contribuciones SIMPER; ordenación NMDS; PERMANOVA y betadisper; redes y clusters Louvain; persistencia y hotspots multiescala; análisis temporal; diversidad funcional cuando existen rasgos suficientes; composición sexual cuando es calculable; y screening separado de prioridad ecológica, seguimiento temporal y suficiencia de datos."
    )
    document.add_heading("Criterio de priorización de conservación", level=2)
    document.add_paragraph(
        "La prioridad de conservación utiliza tres vías complementarias: convergencia entre riqueza, persistencia temporal, uso recurrente y representación repetida de especies de baja ocupación, con un mínimo adicional de 6 eventos/6 individuos para Alta y 12 eventos/12 individuos para Muy alta; núcleos de presencia persistente de una especie; y núcleos de diversidad. La vía de presencia persistente permite prioridad Alta con baja riqueza cuando la misma especie aparece en al menos 3 años, 8 eventos independientes y 8 individuos acumulados. La vía de diversidad permite prioridad Alta con al menos 4 especies, 2 años y 5 eventos, y admite concentraciones excepcionales con al menos 5 especies, 12 eventos y 2 especies de baja ocupación repetidas aunque la cobertura temporal sea de un solo año, marcándolas para validación temporal prioritaria. Un registro aislado nunca basta. LCBD y hotspots se conservan como contexto y no seleccionan por sí solos. Si se solicita una malla de 1 km, el visor muestra la prioridad descriptiva a 1 km como capa separada, mientras la delimitación de zonas estratégicas utiliza unidades mínimas de planificación de 5 km; la capa descriptiva no crea ni amplía zonas estratégicas. Con 5 o 10 km, ambas escalas coinciden. Las zonas estratégicas agrupan unidades Alta/Muy alta mediante contigüidad rook y mantienen la metodología científica de selección. Después, sin recalcular prioridad, se generan zonas operativas a partir de celdas oficiales MITECO de 1 km con observaciones dentro de cada zona estratégica, uniendo únicamente celdas de evidencia que comparten borde y sin rellenar huecos con celdas vacías. Estas huellas orientan la focalización práctica y no equivalen a límites completos de población o hábitat. La señal temporal y la suficiencia de datos se calculan por separado."
    )
    document.add_heading("Control de calidad y reproducibilidad", level=2)
    document.add_paragraph(
        "La ejecución incorpora controles de asignación espacial, coherencia de abundancias, geometría marina, LCBD, análisis temporal, conservación, advertencias de ejecución y duplicados. El informe se genera después de esos análisis y conserva la trazabilidad hacia las tablas y figuras originales."
    )

    # Descripción general
    document.add_heading("3. Descripción general del conjunto de datos", level=1)
    document.add_heading("Cobertura temporal y esfuerzo", level=2)
    _add_df_table(document, report_effort, [("Year", "Año"), ("n_sampling_events", "Eventos proxy"), ("n_records", "Registros"), ("total_abundance", "Individuos"), ("n_species", "Especies")], max_rows=400, sort_by="Year", ascending=True, digits=0)
    _add_figure(document, run_root, [r"Figure_09_01_Temporal_Effort"], "Figura. Esfuerzo temporal de observación en la ejecución actual.")
    _add_interpretation(document, _effort_discussion(report_effort))

    document.add_heading("Cobertura regional", level=2)
    _add_df_table(document, report_regions, [("Region_MITECO", "Región MITECO"), ("n_records", "Registros"), ("total_abundance", "Individuos"), ("n_species", "Especies")], max_rows=30, digits=0)
    _add_interpretation(document, _region_discussion(report_regions))

    if not descriptive.get("habitat", pd.DataFrame()).empty:
        document.add_heading("Hábitats registrados", level=2)
        habitat_frame = descriptive["habitat"].copy()
        habitat_labels = {
            "Species": "Especie", "Habitat_clean": "Hábitat", "Habitat": "Hábitat", "habitat": "Hábitat",
            "n_records": "Registros", "abundance": "Individuos", "richness": "Especies",
            "occupied_cells": "Celdas", "relative_frequency_pct": "Frecuencia relativa (%)",
        }
        wanted = [c for c in ("Species", "Habitat_clean", "n_records", "abundance", "occupied_cells", "relative_frequency_pct") if c in habitat_frame.columns]
        _add_df_table(document, habitat_frame, [(c, habitat_labels[c]) for c in wanted], max_rows=40, sort_by="n_records" if "n_records" in habitat_frame else None, ascending=False, digits=1)

    if sex.get("available") or not report_sex.empty:
        document.add_heading("Composición sexual", level=2)
        _add_df_table(document, report_sex, [("Species", "Especie"), ("female", "Hembras"), ("male", "Machos"), ("indeterminate", "Indeterminados"), ("female_proportion", "Proporción hembras")], max_rows=30, digits=2)
        _add_figure(document, run_root, [r"Figura_Composicion_Sexual_por_Especie", r"Figure_Sex_Composition_by_Species", r"sexo"], "Figura. Composición sexual por especie cuando existen datos suficientes.")
        _add_interpretation(document, _sex_discussion(report_sex))

    # Espacial
    document.add_heading("4. Distribución espacial", level=1)
    document.add_paragraph(
        "La distribución espacial se interpreta mediante celdas marinas oficiales, separando número de registros, abundancia, riqueza, densidad y dominancia. La densidad se expresa respecto de la superficie marina de la celda y no de su superficie terrestre+marina teórica."
    )
    if cell_metrics is not None and len(cell_metrics):
        cm = pd.DataFrame(cell_metrics).copy()
        spatial_labels = {
            "grid_id": "Celda MITECO", "N_total_celda": "Individuos", "n_especies": "Riqueza",
            "Densidad_total": "Densidad (ind./km²)", "n_obs_cell": "Registros", "n_years_cell": "Años con datos",
        }
        columns = [(c, spatial_labels[c]) for c in ["grid_id", "N_total_celda", "n_especies", "Densidad_total", "n_obs_cell", "n_years_cell"] if c in cm.columns]
        if columns:
            _add_df_table(document, cm, columns, max_rows=20, sort_by="N_total_celda" if "N_total_celda" in cm else None, ascending=False, digits=2)
    _add_figure(document, run_root, [r"Figure_09_02_Richness_by_Region", r"Figure_09_03_Overall_Species_Occupancy"], "Figura. Síntesis espacial de riqueza y frecuencia de detección registrada generada por la ejecución.")
    dominance = descriptive.get("dominance", pd.DataFrame())
    if dominance is not None and not dominance.empty:
        document.add_heading("Dominancia regional de especies", level=2)
        dominance_labels = {"Region_MITECO":"Región MITECO", "Species":"Especie", "n_records":"Registros", "abundance":"Individuos", "occupied_cells":"Celdas", "relative_abundance_pct":"Abundancia relativa (%)", "rank_region":"Rango regional"}
        dom_cols = [c for c in dominance_labels if c in dominance.columns]
        _add_df_table(document, dominance, [(c, dominance_labels[c]) for c in dom_cols], max_rows=40, sort_by="relative_abundance_pct" if "relative_abundance_pct" in dominance else "abundance" if "abundance" in dominance else None, ascending=False, digits=2)
        _add_interpretation(document, _dominance_discussion(dominance), title="Interpretación de la dominancia regional")
    _add_figure(document, run_root, [r"Figure_09_04_Regional_Dominance"], "Figura. Dominancia relativa de especies por región MITECO.")
    if not community.get("hotspots", pd.DataFrame()).empty:
        document.add_heading("Hotspots y cobertura espacial", level=2)
        hotspots = community["hotspots"]
        hotspot_labels = {
            "grid_id": "Celda MITECO", "hotspot_type": "Tipo de hotspot", "richness": "Riqueza",
            "abundance": "Abundancia", "density": "Densidad", "p_value": "p-valor",
        }
        _add_df_table(document, hotspots, [(c, hotspot_labels.get(c, c.replace("_", " ").capitalize())) for c in hotspots.columns[:6]], max_rows=20, digits=3)
    _add_figure(document, run_root, [r"Figure_12_Hotspots_by_Scale", r"Figura_Hotspots_Altos_y_Significativos_por_Escala"], "Figura. Hotspots identificados a las escalas analizadas.")
    multiscale_summary = multiscale.get("summary", pd.DataFrame())
    if multiscale_summary is not None and not multiscale_summary.empty:
        document.add_heading("Síntesis multiescala", level=2)
        ms = multiscale_summary.copy()
        if "scale_km" in ms.columns:
            ms["scale_km"] = pd.to_numeric(ms["scale_km"], errors="coerce").round().astype("Int64")
        document.add_paragraph("La primera tabla resume cobertura y esfuerzo por escala; la segunda conserva los indicadores de beta-diversidad, singularidad, hotspots y distance-decay.")
        ms_cov_labels = {
            "scale_km": "Escala (km)", "n_cells_total_with_records": "Celdas con registros",
            "n_cells_evaluable": "Celdas evaluables", "mean_records_cell": "Registros medios/celda",
            "mean_richness": "Riqueza media", "mean_occupancy_pct": "Frecuencia media de detección registrada (%)",
        }
        cov_fields = [c for c in ms_cov_labels if c in ms.columns]
        _add_df_table(document, ms, [(c, ms_cov_labels[c]) for c in cov_fields], max_rows=10, sort_by="scale_km" if "scale_km" in ms else None, ascending=False, digits=2)
        ms_eco_labels = {
            "scale_km": "Escala (km)", "mean_beta_jaccard_pa": "Beta media (Jaccard incidencia)",
            "max_LCBD": "LCBD máximo", "n_LCBD_significant": "LCBD significativos",
            "n_hotspots": "Hotspots", "n_hotspots_significant": "Hotspots significativos",
            "distance_decay_slope_per_km": "Pendiente distance-decay/km",
            "distance_decay_p_value": "p-valor distance-decay", "distance_decay_R2": "R² distance-decay",
        }
        eco_fields = [c for c in ms_eco_labels if c in ms.columns]
        # Keep the second table readable by separating distance-decay when all fields are available.
        main_fields = [c for c in eco_fields if c not in {"distance_decay_slope_per_km", "distance_decay_p_value", "distance_decay_R2"}]
        _add_df_table(document, ms, [(c, ms_eco_labels[c]) for c in main_fields], max_rows=10, sort_by="scale_km" if "scale_km" in ms else None, ascending=False, digits=4)
        decay_fields = [c for c in ["scale_km", "distance_decay_slope_per_km", "distance_decay_p_value", "distance_decay_R2"] if c in ms.columns]
        if len(decay_fields) > 1:
            document.add_heading("Distance-decay multiescala", level=3)
            _add_df_table(document, ms, [(c, ms_eco_labels[c]) for c in decay_fields], max_rows=10, sort_by="scale_km" if "scale_km" in ms else None, ascending=False, digits=4)
    _add_figure(document, run_root, [r"Figure_12_Multiscale_Richness", r"Figura_12_Riqueza_Multiescala", r"Figura_Riqueza_Multiescala"], "Figura. Riqueza y cobertura a múltiples escalas espaciales.")
    _add_figure(document, run_root, [r"Figure_12_Hotspot_Persistence", r"Figura_Persistencia_Hotspots_Altos_y_Significativos_Malla_Maestra", r"Figura_Estabilidad_Hotspots_Altos_y_Significativos_Malla_Maestra"], "Figura. Persistencia de hotspots en la malla maestra y concordancia entre escalas.")
    _add_figure(document, run_root, [r"Figure_Moran_MC_High_Significant_Hotspot_Histogram"], "Figura. Distribución de Monte Carlo utilizada para evaluar la autocorrelación espacial de la persistencia de hotspots.")
    _add_interpretation(document, _spatial_discussion(pd.DataFrame(cell_metrics) if cell_metrics is not None else pd.DataFrame(), community.get("hotspots", pd.DataFrame()), multiscale_summary))

    # Habitat depth
    document.add_heading("5. Hábitat y profundidad", level=1)
    document.add_paragraph(
        "Los patrones de hábitat y profundidad se resumen por especie y región. La mediana de profundidad se prioriza para describir la posición batimétrica típica porque es más robusta frente a valores extremos; la media y amplitud se conservan como información complementaria."
    )
    if not descriptive.get("depth_species", pd.DataFrame()).empty:
        ds = descriptive["depth_species"].copy()
        depth_labels = {
            "Species": "Especie", "depth_median": "Profundidad mediana (m)", "depth_mean": "Profundidad media (m)",
            "depth_min": "Profundidad mínima (m)", "depth_max": "Profundidad máxima (m)",
            "n_depth_valid": "N con profundidad", "depth_q25": "P25 profundidad (m)", "depth_q75": "P75 profundidad (m)",
            "median_ci_low": "IC95% mediana - inferior", "median_ci_high": "IC95% mediana - superior",
        }
        wanted = [c for c in ("Species", "depth_median", "depth_mean", "depth_min", "depth_max", "n_depth_valid", "depth_q25", "depth_q75") if c in ds.columns]
        _add_df_table(document, ds, [(c, depth_labels[c]) for c in wanted], max_rows=30, sort_by="depth_median" if "depth_median" in ds else None, ascending=False, digits=2)
    depth_region = descriptive.get("depth_region", pd.DataFrame())
    if depth_region is not None and not depth_region.empty:
        document.add_heading("Profundidad por región MITECO", level=2)
        depth_region_labels = {"Region_MITECO":"Región MITECO", "n_depth_valid":"N con profundidad", "depth_median":"Profundidad mediana (m)", "depth_mean":"Profundidad media (m)", "depth_q25":"P25 (m)", "depth_q75":"P75 (m)", "depth_min":"Mínimo (m)", "depth_max":"Máximo (m)"}
        dr_cols = [c for c in depth_region_labels if c in depth_region.columns]
        _add_df_table(document, depth_region, [(c, depth_region_labels[c]) for c in dr_cols], max_rows=30, sort_by="depth_median" if "depth_median" in depth_region else None, ascending=False, digits=2)
    depth_tests = descriptive.get("depth_tests", pd.DataFrame())
    if depth_tests is not None and not depth_tests.empty:
        document.add_heading("Contrastes estadísticos de profundidad", level=2)
        test_labels = {"test":"Prueba", "variable":"Variable", "group":"Grupo/predictor", "statistic":"Estadístico", "p_value":"p-valor", "n_groups":"N/grupos", "R2":"R²", "slope":"Pendiente"}
        dt_cols = [c for c in test_labels if c in depth_tests.columns]
        _add_df_table(document, depth_tests, [(c, test_labels[c]) for c in dt_cols], max_rows=40, digits=4)
    _add_figure(document, run_root, [r"Figure_Habitat_Frequency"], "Figura. Frecuencia de observaciones por categoría de hábitat.")
    _add_figure(document, run_root, [r"Figure_09_05_Depth_by_Species"], "Figura. Distribución de profundidad por especie, ordenada por profundidad típica.")
    _add_figure(document, run_root, [r"Figure_09_06_Species_Habitat_Heatmap"], "Figura. Asociación observada entre especies y categorías de hábitat.")
    _add_figure(document, run_root, [r"Figure_Depth_Overall_Histogram"], "Figura. Distribución global de profundidades de las observaciones válidas.")
    _add_figure(document, run_root, [r"Figure_Depth_Bathymetric_Classes"], "Figura. Distribución de registros entre clases batimétricas.")
    _add_figure(document, run_root, [r"Figure_Depth_Annual_Trend"], "Figura. Evolución temporal de la profundidad de observación.")
    _add_figure(document, run_root, [r"Figure_Depth_vs_Total_Abundance"], "Figura. Relación observada entre profundidad y abundancia registrada.")
    _add_figure(document, run_root, [r"Figure_Depth_by_Habitat_Boxplot"], "Figura. Distribución de profundidad por hábitat.")
    _add_figure(document, run_root, [r"Figure_Depth_Habitat_by_Species_Boxplot"], "Figura. Profundidad y hábitat por especie.")
    _add_interpretation(document, _habitat_depth_discussion(descriptive))

    # Community
    document.add_heading("6. Estructura de la comunidad", level=1)
    community_region = descriptive.get("community_region", pd.DataFrame())
    if community_region is not None and not community_region.empty:
        document.add_heading("Diversidad comunitaria por región", level=2)
        cr_labels = {"Region_MITECO":"Región MITECO", "richness":"Riqueza", "abundance":"Individuos", "shannon":"Shannon", "simpson":"Simpson", "pielou":"Equitatividad de Pielou"}
        cr_cols = [c for c in cr_labels if c in community_region.columns]
        _add_df_table(document, community_region, [(c, cr_labels[c]) for c in cr_cols], max_rows=30, sort_by="richness" if "richness" in community_region else None, ascending=False, digits=3)
        _add_interpretation(document, _regional_diversity_discussion(descriptive), title="Interpretación de la diversidad comunitaria regional")
    abundance_matrix = community.get("abundance_matrix", pd.DataFrame())
    document.add_paragraph(
        f"La matriz comunitaria contiene {len(abundance_matrix)} celdas y {len(abundance_matrix.columns) if hasattr(abundance_matrix, 'columns') else 0} especies. Los análisis de diversidad beta cuantifican diferencias de composición entre unidades espaciales y distinguen reemplazo de especies (turnover) de diferencias debidas a subconjuntos de riqueza (nestedness)."
    )
    beta_summary = community.get("beta_clusters_component_summary", pd.DataFrame())
    if beta_summary is not None and not beta_summary.empty:
        beta_labels = {
            "comparison": "Comparación", "dominant_component": "Componente dominante",
            "beta_total_sorensen": "Beta total (Sørensen)", "beta_turnover_simpson": "Turnover (Simpson)",
            "beta_nestedness_sorensen": "Nestedness (Sørensen)",
        }
        beta_cols = [c for c in beta_labels if c in beta_summary.columns]
        _add_df_table(document, beta_summary, [(c, beta_labels[c]) for c in beta_cols], max_rows=20, digits=4)
    document.add_heading("PERMANOVA y dispersión", level=2)
    regional_tests = [
        ("Principal: Hellinger–Euclídea", community.get("permanova_hellinger", community.get("permanova", {})), community.get("betadisper_hellinger", community.get("betadisper", {}))),
        ("Complementaria: Jaccard incidencia", community.get("permanova_jaccard", {}), community.get("betadisper_jaccard", {})),
        ("Sensibilidad: Bray–Curtis abundancia bruta", community.get("permanova_bray_sensitivity", {}), community.get("betadisper_bray_sensitivity", {})),
    ]
    rows = []
    for method_name, perm_stats, disp_stats in regional_tests:
        if isinstance(perm_stats, dict):
            rows.append({
                "Método": method_name,
                "pseudo-F": perm_stats.get("pseudo_F"),
                "p-valor": perm_stats.get("p_value"),
                "R²": perm_stats.get("R2"),
                "Betadisper F": disp_stats.get("F") if isinstance(disp_stats, dict) else np.nan,
                "Betadisper p": disp_stats.get("p_value") if isinstance(disp_stats, dict) else np.nan,
            })
    if rows:
        _add_df_table(document, pd.DataFrame(rows), [(c, c) for c in rows[0]], max_rows=10, digits=4)
    document.add_paragraph("La inferencia principal usa Hellinger–Euclídea; Jaccard evalúa incidencia y Bray–Curtis bruto se conserva como sensibilidad frente al efecto de los totales acumulados.")
    indicators = community.get("indicators_region", pd.DataFrame())
    # IndVal/SIMPER are exported to tables and may not be returned directly by every analysis call.
    if indicators is not None and not indicators.empty:
        indval_labels = {
            "Species": "Especie", "IndVal": "IndVal", "p_value": "p-valor", "p_adjust_BH": "q BH-FDR", "significant_FDR": "Significativo FDR", "indicator_group": "Grupo indicador",
            "group": "Grupo", "A_specificity": "Especificidad (A)", "B_fidelity": "Fidelidad (B)",
        }
        indval_fields = [c for c in ("Species", "indicator_group", "IndVal", "A_specificity", "B_fidelity", "p_value", "p_adjust_BH", "significant_FDR") if c in indicators.columns]
        _add_df_table(document, indicators, [(c, indval_labels.get(c, c.replace("_", " ").capitalize())) for c in indval_fields], max_rows=20, sort_by="IndVal" if "IndVal" in indicators else None, ascending=False, digits=3)
    simper_region = community.get("simper_region", pd.DataFrame())
    if simper_region is not None and not simper_region.empty:
        document.add_heading("SIMPER: especies que más contribuyen a las diferencias regionales", level=2)
        simper_labels = {
            "group_1": "Grupo 1", "group_2": "Grupo 2", "Species": "Especie",
            "mean_contribution": "Contribución media", "contribution_pct": "Contribución (%)",
            "cumulative_pct": "Acumulado (%)", "rank": "Rango",
        }
        _add_df_table(document, simper_region, [(c, simper_labels.get(c, c.replace("_", " ").capitalize())) for c in simper_region.columns[:7]], max_rows=40, sort_by="contribution_pct" if "contribution_pct" in simper_region else None, ascending=False, digits=3)
        document.add_paragraph(
            "SIMPER identifica qué especies explican una mayor fracción de la disimilitud media entre grupos. Debe interpretarse como una descomposición descriptiva de las diferencias de composición, no como una prueba causal ni como evidencia independiente de importancia de conservación."
        )
    core_satellite = community.get("core_satellite", pd.DataFrame())
    if core_satellite is not None and not core_satellite.empty:
        # Keep this relatively wide table together: when it starts at the very
        # bottom of a page LibreOffice can orphan the repeated header row.
        document.add_page_break()
        document.add_heading("Clasificación relativa de frecuencia de detección", level=2)
        core_labels = {
            "Species": "Especie", "occupancy": "Frecuencia de detección registrada (proporción)",
            "mean_abundance_occupied_cells": "Abundancia media en celdas ocupadas",
            "total_abundance": "Abundancia total", "n_habitats": "Nº de hábitats",
            "depth_median": "Profundidad mediana (m)", "occupancy_class_display": "Clase relativa de detección",
        }
        core_fields = [c for c in ("Species", "occupancy", "mean_abundance_occupied_cells", "total_abundance", "n_habitats", "depth_median", "occupancy_class_display") if c in core_satellite.columns]
        _add_df_table(document, core_satellite, [(c, core_labels.get(c, c.replace("_", " ").capitalize())) for c in core_fields], max_rows=30, sort_by="occupancy" if "occupancy" in core_satellite else None, ascending=False, digits=3)
        document.add_paragraph(
            "La clasificación resume la frecuencia de detección relativa dentro de esta ejecución (alta, intermedia o baja). No se interpreta como demostración de un patrón poblacional core–satellite; depende del dominio, resolución y filtros aplicados."
        )
    _add_figure(document, run_root, [r"Figure_10_Rank_Abundance"], "Figura. Patrón de abundancia relativa de la comunidad.")
    _add_figure(document, run_root, [r"Figure_13_Indicator_Species"], "Figura. Especies indicadoras calculadas por la ejecución.")
    _add_figure(document, run_root, [r"Figure_14_Core_Satellite"], "Figura. Clasificación relativa de la frecuencia de detección registrada de las especies.")
    _add_interpretation(document, _community_discussion(community))

    # Biogeography
    document.add_heading("7. Biogeografía", level=1)
    clusters = community.get("cluster_summary", pd.DataFrame())
    if clusters is not None and not clusters.empty:
        document.add_paragraph(
            f"El análisis de red/Louvain identificó {len(clusters)} agrupaciones exploratorias. Su composición y tamaño se describen junto con NMDS y distance-decay; PERMANOVA, betadisper e IndVal entre estos mismos clusters se muestran solo como caracterización post hoc no independiente, porque los grupos se construyeron a partir de la propia composición comunitaria."
        )
        cluster_labels = {
            "community_cluster": "Cluster", "n_cells": "Celdas", "depth_median": "Profundidad mediana (m)",
            "habitat_dominant": "Hábitat dominante", "region_dominant": "Región dominante",
            "betweenness_mean": "Intermediación media", "macro_cluster": "Macrocluster",
        }
        cluster_cols = [c for c in cluster_labels if c in clusters.columns]
        _add_df_table(document, clusters, [(c, cluster_labels[c]) for c in cluster_cols], max_rows=40, sort_by="n_cells" if "n_cells" in clusters else None, ascending=False, digits=2)
    network_metrics = community.get("network_metrics", pd.DataFrame())
    if network_metrics is not None and not network_metrics.empty:
        document.add_heading("Métricas de la red biogeográfica", level=2)
        nm_labels = {"metric":"Métrica", "value":"Valor"}
        metric_names = {
            "nodes": "Nodos", "edges": "Enlaces", "clusters": "Clusters",
            "density": "Densidad de red", "transitivity": "Transitividad",
            "similarity_threshold": "Umbral de similitud",
            "ARI_region_cluster": "ARI región-cluster",
        }
        network_metrics = network_metrics.copy()
        if "metric" in network_metrics.columns:
            network_metrics["metric"] = network_metrics["metric"].map(lambda x: metric_names.get(str(x), str(x)))
        nm_cols = [c for c in nm_labels if c in network_metrics.columns]
        _add_df_table(document, network_metrics, [(c, nm_labels[c]) for c in nm_cols], max_rows=40, digits=4)
    cluster_perm = community.get("permanova_clusters", {})
    cluster_disp = community.get("betadisper_clusters", {})
    if isinstance(cluster_perm, dict):
        document.add_heading("Caracterización post hoc de composición entre clusters", level=2)
        stat_labels = {"pseudo_F":"pseudo-F", "p_value":"p-valor", "R2":"R²", "permutations":"Permutaciones", "F":"F"}
        _add_kv_table(document, [(stat_labels.get(k,k),v) for k,v in cluster_perm.items()])
        if isinstance(cluster_disp, dict):
            _add_kv_table(document, [("Betadisper " + stat_labels.get(k,k),v) for k,v in cluster_disp.items()])
    cluster_ind = community.get("indicators_cluster", pd.DataFrame())
    if cluster_ind is not None and not cluster_ind.empty:
        document.add_heading("IndVal post hoc por clusters biogeográficos", level=2)
        ci_labels = {"Species":"Especie", "IndVal":"IndVal", "p_value":"p-valor", "p_adjust_BH":"q BH-FDR", "significant_FDR":"Significativo FDR", "indicator_group":"Cluster indicador", "A_specificity":"Especificidad (A)", "B_fidelity":"Fidelidad (B)", "inference_scope":"Alcance inferencial"}
        ci_cols = [c for c in ci_labels if c in cluster_ind.columns]
        _add_df_table(document, cluster_ind, [(c,ci_labels[c]) for c in ci_cols], max_rows=30, sort_by="IndVal" if "IndVal" in cluster_ind else None, ascending=False, digits=4)
    decay = community.get("distance_decay_summary", {})
    if isinstance(decay, dict) and decay:
        document.add_heading("Resumen de distance-decay", level=2)
        dd_labels = {
            "mantel_rho":"Mantel ρ (Hellinger)", "mantel_p_value":"p-valor Mantel (Hellinger)",
            "mantel_rho_jaccard":"Mantel ρ (Jaccard)", "mantel_p_value_jaccard":"p-valor Mantel (Jaccard)",
            "mantel_rho_bray_sensitivity":"Mantel ρ (Bray bruto, sensibilidad)", "mantel_p_value_bray_sensitivity":"p-valor Mantel (Bray, sensibilidad)",
            "permutations":"Permutaciones", "n_cells":"Celdas", "n_pairs":"Pares de celdas",
            "spearman_rho_pairwise_descriptive":"Spearman por pares (solo descriptivo)",
            "slope":"Pendiente lineal descriptiva", "r_squared":"R² descriptivo", "adj_r_squared":"R² ajustado descriptivo",
            "linear_inference_status":"Alcance de la regresión lineal",
        }
        _add_kv_table(document, [(dd_labels.get(k,k),v) for k,v in decay.items() if k in dd_labels], digits=4)
    _add_figure(document, run_root, [r"Figure_10_Community_NMDS"], "Figura. Ordenación NMDS de la estructura comunitaria.")
    _add_figure(document, run_root, [r"Figure_18_Biogeographic_Clusters"], "Figura. Clusters biogeográficos identificados mediante la estructura de similitud comunitaria.")
    _add_figure(document, run_root, [r"Figure_18_Cluster_Composition", r"Figura_18_Composicion_Clusters"], "Figura. Composición taxonómica de los clusters biogeográficos.")
    _add_figure(document, run_root, [r"Figure_18_10_Betadisper_Clusters", r"Figura_18_10_Betadisper_Clusters"], "Figura. Dispersión multivariante post hoc entre clusters exploratorios.")
    _add_figure(document, run_root, [r"Figure_Top_Species_by_Macrocluster", r"Figura_Top_Especies_por_Macrocluster"], "Figura. Especies con mayor contribución a la composición de los macroclusters.")
    _add_figure(document, run_root, [r"Figure_18_12_Distance_Decay_Similitud", r"Figure_18_12_Distance_Decay_Similarity"], "Figura. Relación distance-decay entre distancia geográfica y similitud comunitaria.")
    _add_figure(document, run_root, [r"Figure_18_Network_Threshold_Sensitivity"], "Figura. Sensibilidad de la estructura de red al umbral de similitud.")
    _add_figure(document, run_root, [r"Figure_18_11_Sensibilidad_Umbral_Modularidad", r"Figure_18_11_Threshold_Sensitivity_Modularity"], "Figura. Sensibilidad de la modularidad al umbral de red.")
    _add_figure(document, run_root, [r"Figure_18_11_Sensibilidad_Umbral_NumClusters", r"Figure_18_11_Threshold_Sensitivity_Number_Clusters"], "Figura. Sensibilidad del número de clusters al umbral de red.")
    _add_figure(document, run_root, [r"Figure_18_14_Concordancia_Region_Cluster", r"Figure_18_14_Region_Cluster_Concordance"], "Figura. Concordancia entre regiones MITECO y clusters comunitarios.")
    _add_figure(document, run_root, [r"Figure_18_17_Mapa_Macroclusters_PieCharts_TopSpecies", r"Figure_18_17_Macrocluster_Map_PieCharts_TopSpecies"], "Figura. Composición espacial de macroclusters y especies principales.")
    _add_figure(document, run_root, [r"Figure_18_18_Mapa_Macroclusters_PieCharts_TamanoFijo", r"Figure_18_18_Macrocluster_Map_PieCharts_FixedSize"], "Figura. Composición de macroclusters con símbolos de tamaño fijo para facilitar la comparación espacial.")
    if not community.get("top10_macrocluster_species", pd.DataFrame()).empty:
        document.add_heading("Especies dominantes por macrocluster", level=2)
        mc = community["top10_macrocluster_species"]
        macro_labels = {"macrocluster": "Macrocluster", "macro_cluster": "Macrocluster", "Species": "Especie", "Species_short": "Especie", "total_abundance": "Abundancia", "n_grids": "Celdas", "relative_abundance_pct": "Abundancia relativa (%)"}
        macro_cols = [c for c in ("macro_cluster", "macrocluster", "Species", "Species_short", "total_abundance", "n_grids", "relative_abundance_pct") if c in mc.columns]
        _add_df_table(document, mc, [(c, macro_labels[c]) for c in macro_cols], max_rows=40, sort_by="total_abundance" if "total_abundance" in mc else None, ascending=False, digits=2)
    _add_interpretation(document, _biogeography_discussion(community))

    # LCBD
    document.add_heading("8. LCBD y singularidad ecológica", level=1)
    lcbd = community.get("lcbd", pd.DataFrame())
    if lcbd is not None and not lcbd.empty:
        document.add_paragraph(
            "LCBD cuantifica la contribución local de cada celda a la diversidad beta total. Se presentan LCBD-Jaccard (incidencia) y LCBD-Hellinger (composición relativa), con p-valores brutos y ajuste Benjamini–Hochberg. Un LCBD alto describe singularidad composicional observada; la significación FDR y el soporte en eventos proxy se informan por separado y no convierten automáticamente la celda en prioridad de conservación."
        )
        lcbd_display = lcbd.copy()
        lcbd_labels = {
            "grid_id": "Celda MITECO", "LCBD": "LCBD-Jaccard",
            "LCBD_p_value": "p bruto Jaccard", "LCBD_p_adjust_BH": "q BH-FDR Jaccard",
            "significant_FDR": "Significativo FDR Jaccard",
            "LCBD_hellinger": "LCBD-Hellinger",
            "LCBD_hellinger_p_value": "p bruto Hellinger",
            "LCBD_hellinger_p_adjust_BH": "q BH-FDR Hellinger",
            "LCBD_hellinger_significant_FDR": "Significativo FDR Hellinger",
            "n_sampling_events": "Eventos proxy", "n_years_observed": "Años observados",
            "LCBD_high_concordant": "LCBD alto concordante", "LCBD_FDR_concordant": "FDR concordante",
            "richness": "Riqueza", "abundance": "Abundancia", "Region_MITECO": "Región MITECO",
        }
        lcbd_fields = [c for c in lcbd_labels if c in lcbd_display.columns]
        lcbd_cols = [(c, lcbd_labels[c]) for c in lcbd_fields]
        sort_col = "LCBD" if "LCBD" in lcbd_display.columns else None
        _add_df_table(document, lcbd_display, lcbd_cols, max_rows=20, sort_by=sort_col, ascending=False, digits=5)
    _add_figure(document, run_root, [r"Figure_11_Cell_LCBD"], "Figura. Distribución espacial del LCBD por celda.")
    _add_figure(document, run_root, [r"Figure_15_LCBD_Rarity"], "Figura. Relación entre singularidad comunitaria y rareza.")
    _add_figure(document, run_root, [r"Figure_11_Latitudinal_Gradient"], "Figura. Gradiente latitudinal de las métricas comunitarias calculadas por la ejecución.")
    _add_interpretation(document, _lcbd_discussion(community))

    # Temporal
    document.add_heading("9. Cambios temporales", level=1)
    periods = temporal.get("periods", [])
    if periods:
        document.add_paragraph("Periodos comparados: " + "; ".join(getattr(p, "label", str(p)) for p in periods) + ".")
    period_summary = temporal.get("period_summary", pd.DataFrame())
    if period_summary is not None and not period_summary.empty:
        document.add_heading("Resumen por periodos y especies", level=2)
        ps_labels = {"Species":"Especie", "period":"Periodo", "n_records":"Registros de la especie", "n_sampling_events_period":"Eventos proxy totales", "species_sampling_events":"Eventos con registro de la especie", "abundance":"Individuos registrados", "detected_cells":"Celdas con detección", "detection_frequency_sampled_cells_period":"Frecuencia de detección en celdas muestreadas", "abundance_per_sampling_event_global_period":"Individuos registrados por evento proxy", "density_occupied_area_annualized_km2":"Densidad anualizada (ind./km²)", "depth_median":"Profundidad mediana (m)", "habitat_dominant":"Hábitat dominante"}
        document.add_heading("Eventos proxy, tasa relativa de observación y frecuencia de detección por periodo", level=3)
        ps_core = [c for c in ("Species", "period", "n_records", "n_sampling_events_period", "species_sampling_events", "abundance", "detected_cells", "detection_frequency_sampled_cells_period", "abundance_per_sampling_event_global_period") if c in period_summary.columns]
        _add_df_table(document, period_summary, [(c, ps_labels[c]) for c in ps_core], max_rows=60, sort_by="Species" if "Species" in period_summary else None, ascending=True, digits=3)
        ps_env = [c for c in ("Species", "period", "density_occupied_area_annualized_km2", "depth_median", "habitat_dominant") if c in period_summary.columns]
        if len(ps_env) > 2:
            document.add_heading("Densidad, profundidad y hábitat por periodo", level=3)
            _add_df_table(document, period_summary, [(c, ps_labels[c]) for c in ps_env], max_rows=60, sort_by="Species" if "Species" in period_summary else None, ascending=True, digits=3)
    comparisons = temporal.get("comparisons", pd.DataFrame())
    if comparisons is not None and not comparisons.empty:
        document.add_heading("Comparaciones entre periodos", level=2)
        temporal_labels = {
            "Species": "Especie", "comparison": "Comparación",
            "abundance_1": "Abundancia periodo 1", "abundance_2": "Abundancia periodo 2",
            "relative_change_abundance_pct": "Cambio de tasa de observación por evento (%)",
            "occupied_cells_1": "Celdas con detección periodo 1", "occupied_cells_2": "Celdas con detección periodo 2",
            "delta_detection_frequency": "Cambio de frecuencia de detección",
            "annualized_density_1": "Densidad anualizada periodo 1", "annualized_density_2": "Densidad anualizada periodo 2",
            "delta_annualized_density": "Cambio de densidad anualizada", "p_adjust_BH": "p ajustado BH",
        }
        abundance_fields = [c for c in ("Species", "comparison", "abundance_1", "abundance_2", "relative_change_abundance_pct", "occupied_cells_1", "occupied_cells_2", "delta_detection_frequency") if c in comparisons.columns]
        _add_df_table(document, comparisons, [(c, temporal_labels[c]) for c in abundance_fields], max_rows=40, sort_by="Species" if "Species" in comparisons else None, ascending=True, digits=2)
        density_fields = [c for c in ("Species", "comparison", "annualized_density_1", "annualized_density_2", "delta_annualized_density", "p_adjust_BH") if c in comparisons.columns]
        if len(density_fields) > 2:
            document.add_heading("Densidad y significación de los cambios", level=3)
            _add_df_table(document, comparisons, [(c, temporal_labels[c]) for c in density_fields], max_rows=40, sort_by="Species" if "Species" in comparisons else None, ascending=True, digits=2)
    changes = temporal.get("cell_changes", pd.DataFrame())
    if changes is not None and not changes.empty and "status" in changes.columns:
        status = changes["status"].astype(str).value_counts().rename_axis("Estado").reset_index(name="N")
        document.add_heading("Ganancias, pérdidas y persistencia", level=2)
        _add_df_table(document, status, [("Estado", "Estado"), ("N", "Número de casos")], max_rows=10, digits=0)
    temporal_ranking = temporal.get("ranking", pd.DataFrame())
    if temporal_ranking is not None and not temporal_ranking.empty:
        document.add_heading("Prioridad temporal por especie", level=2)
        temporal_ranking = temporal_ranking.copy()
        if "trend_direction" in temporal_ranking.columns:
            direction_map = {"increase":"Aumento", "stable":"Estable", "decrease":"Disminución", "gain":"Aumento", "loss":"Disminución"}
            temporal_ranking["trend_direction"] = temporal_ranking["trend_direction"].map(lambda x: direction_map.get(str(x).strip().casefold(), x))
        tr_labels = {"Species":"Especie", "active_years":"Años con detección", "observation_rate_mean":"Tasa media por 100 eventos proxy", "detection_frequency_mean":"Frecuencia media de detección (%)", "inference_scope":"Ámbito inferencial", "n_detection_years":"Años con detección", "n_detection_events":"Eventos con detección", "detection_span_years":"Extensión temporal (años)", "pearson_dispersion_used":"Dispersión Pearson usada", "annual_change_pct":"Cambio anual estimado de la tasa (%)", "p_value":"p-valor", "stability_score":"Estabilidad", "change_score":"Cambio", "temporal_priority_score":"Prioridad de seguimiento temporal", "temporal_priority_rank":"Rango", "trend_direction":"Dirección"}
        tr_cols = [c for c in tr_labels if c in temporal_ranking.columns]
        _add_df_table(document, temporal_ranking, [(c,tr_labels[c]) for c in tr_cols], max_rows=40, sort_by="temporal_priority_rank" if "temporal_priority_rank" in temporal_ranking else None, ascending=True, digits=3)
    document.add_paragraph(
        "Las ganancias, pérdidas y cambios de abundancia/densidad son señales observacionales. Su interpretación como expansión, retracción o cambio poblacional requiere comprobar que el esfuerzo y la detectabilidad sean comparables entre periodos."
    )
    _add_figure(document, run_root, [r"Figure_20_Adjusted_Annual_Series"], "Figura. Series temporales ajustadas generadas por la ejecución.")
    _add_figure(document, run_root, [r"Figure_20_Changes_Between_Periods"], "Figura. Cambios entre periodos comparativos.")
    _add_figure(document, run_root, [r"Figure_20_Abundance_Change_Map"], "Figura. Cambio espacial de abundancia entre periodos.")
    _add_figure(document, run_root, [r"Figure_20_Temporal_Priority_Ranking", r"Figura_20_Ranking_Prioridad_Temporal"], "Figura. Síntesis de prioridad temporal cuando es calculable en la ejecución.")
    _add_interpretation(document, _temporal_discussion(temporal))

    # Functional
    document.add_heading("10. Diversidad funcional", level=1)
    if functional.get("available"):
        fr = functional.get("results", pd.DataFrame())
        document.add_paragraph(
            "La diversidad funcional se calcula cuando las especies seleccionadas disponen de cobertura de rasgos suficiente. Los índices principales se basan en incidencia y usan un único espacio funcional corregido; la ponderación por abundancia observada se conserva solo como análisis de sensibilidad."
        )
        if isinstance(fr, pd.DataFrame) and not fr.empty:
            functional_labels = {
                "Region_MITECO": "Región MITECO",
                "functional_species": "Especies con rasgos",
                "trait_coverage_fraction": "Cobertura de rasgos",
                "FRic_relative": "FRic relativo",
                "FEve": "FEve", "FDiv": "FDiv", "FDis": "FDis", "RaoQ": "RaoQ",
            }
            functional_columns = [c for c in ("Region_MITECO", "functional_species", "trait_coverage_fraction", "FRic_relative", "FEve", "FDiv", "FDis", "RaoQ") if c in fr.columns]
            _add_df_table(document, fr, [(c, functional_labels[c]) for c in functional_columns], max_rows=20, digits=3)
        _add_figure(document, run_root, [r"Figura_Diversidad_Funcional_por_Region", r"Figure_Functional_Diversity_by_Region"], "Figura. Diversidad funcional por región.")
        _add_figure(document, run_root, [r"Figura_Riqueza_Taxonomica_frente_a_Funcional", r"Figure_Taxonomic_vs_Functional_Richness"], "Figura. Relación entre diversidad taxonómica y funcional.")
    else:
        document.add_paragraph("La diversidad funcional no fue calculable en esta ejecución. Motivo: " + _clean_text(functional.get("reason"), "rasgos insuficientes o no disponibles") + ".")
    _add_interpretation(document, _functional_discussion(functional))

    LOGGER.info("    [8/8 · 3/4] Mapas y fichas de zonas prioritarias")
    # Conservation
    document.add_page_break()
    document.add_heading("11. Zonas prioritarias de conservación y medidas de protección", level=1)
    document.add_paragraph(
        "Este capítulo es una parte principal del informe. Distingue entre zonas prioritarias estratégicas, que conservan íntegramente la metodología científica de priorización y planificación, y zonas operativas de conservación, que restringen la huella de actuación a celdas oficiales MITECO de 1 km con evidencia observada dentro de cada zona estratégica. Integra prioridad ecológica, robustez, información temporal, hábitat, profundidad, especies presentes, abundancia y densidad por especie, y la cobertura de las figuras de protección disponibles. Las zonas operativas sirven para focalizar actuaciones y no deben interpretarse como límites completos de población o hábitat. Las medidas son propuestas técnicas a considerar: no sustituyen la evaluación normativa, la participación de administraciones/sectores ni la comprobación de presiones locales."
    )
    for map_path, caption in _render_priority_zone_maps_es(run_root, output_dir, conservation, zones):
        _add_picture(document, map_path, caption, width_cm=13.0)
    _add_figure(document, run_root, [r"Mapa_21_Zonas_Prioritarias_Seleccionadas", r"Mapa_21_Zonas_Prioritarias_Conservacion", r"Map_21_Priority_Conservation_Areas", r"Figure_21_Priority_Conservation_Areas", r"Figura_21_Zonas_Prioritarias_Conservacion"], "Figura. Zonas prioritarias de conservación identificadas en la ejecución.")
    _add_interpretation(document, _conservation_discussion(zones), title="Interpretación general de las zonas prioritarias estratégicas")
    if zones.empty:
        document.add_paragraph("No se formaron zonas de prioridad alta o muy alta en la ejecución actual.")
    else:
        summary_cols = [
            ("zone_id", "Zona"), ("ecological_priority_class_zone", "Prioridad ecológica"), ("ecological_priority_score_mean", "Índice ecológico medio"),
            ("area_zone_km2", "Área km²"), ("richness_max", "Riqueza máx."), ("abundance_sum", "Abundancia"),
            ("pct_zone_protected", "% protegido"),
        ]
        _add_df_table(document, zones, summary_cols, max_rows=100, sort_by="ecological_priority_score_mean", ascending=False, digits=1)

    document.add_heading("Zonas operativas de conservación", level=2)
    document.add_paragraph(
        "Estas subzonas se derivan después de la priorización estratégica mediante celdas oficiales MITECO de 1 km con observaciones. No añaden celdas vacías para conectar núcleos separados y no modifican la clase ni la puntuación de la zona estratégica progenitora."
    )
    if operational_zones.empty:
        document.add_paragraph("No se generaron zonas operativas de conservación en la ejecución actual.")
    else:
        _add_df_table(document, operational_zones, [
            ("operational_zone_id", "Zona operativa"), ("parent_zone_id", "Zona estratégica"),
            ("n_evidence_cells_1km", "Celdas con evidencia 1 km"), ("area_operational_km2", "Área operativa km²"),
            ("pct_parent_zone_evidence_footprint", "% de la zona estratégica"), ("n_records_sum", "Registros"),
            ("n_sampling_events_cell_sum", "Eventos proxy"), ("n_years_observed_max", "Máx. años"),
        ], max_rows=200, sort_by="parent_zone_id", ascending=True, digits=2)

    zone_species = _species_zone_table(conservation.get("selected_cells", pd.DataFrame()), assigned, zones)
    selected_cells = conservation.get("selected_cells", pd.DataFrame())
    temporal_changes = temporal.get("cell_changes", pd.DataFrame())
    all_measure_rows: list[dict[str, str]] = []
    if not zones.empty:
        for zone_index, (_, row) in enumerate(zones.sort_values(["ecological_priority_score_mean", "zone_id"], ascending=[False, True]).iterrows()):
            zone_id = str(row.get("zone_id"))
            if zone_index == 0:
                document.add_page_break()
            document.add_heading(f"11.{zone_id} · Zona prioritaria estratégica {zone_id}", level=2)
            _add_kv_table(document, [
                ("Prioridad ecológica", row.get("ecological_priority_class_zone")),
                ("Índice ecológico medio / máximo", f"{_fmt(row.get('ecological_priority_score_mean'),1)} / {_fmt(row.get('ecological_priority_score_max'),1)}"),
                ("Superficie marina", f"{_fmt(row.get('area_zone_km2'),2)} km²"),
                ("Número de celdas", row.get("n_cells")),
                ("Región MITECO dominante", row.get("Region_MITECO_dominante")),
                ("Riqueza máxima", row.get("richness_max")),
                ("Abundancia registrada", row.get("abundance_sum")),
                ("LCBD máximo", row.get("LCBD_max")),
                ("Hotspots multiescala", row.get("hotspot_cells_multiscale")),
                ("Hotspots persistentes en todas las escalas", row.get("hotspot_cells_persistent_all_scales")),
                ("Hábitat dominante", row.get("habitat_dominant_zone")),
                ("Profundidad mediana", f"{_fmt(row.get('depth_median_zone'),1)} m"),
                ("Suficiencia de datos", row.get("data_adequacy_class_zone")),
                ("Estabilidad entre escenarios", row.get("sensitivity_class_zone")),
                ("Zona protegida", _pct(row.get("pct_zone_protected"))),
                ("Figuras de protección solapadas", row.get("protected_area_names")),
                ("Tipos de protección", row.get("protected_area_types")),
                ("Distancia al área protegida más próxima", f"{_fmt(row.get('distance_to_protected_m'),0)} m"),
            ])
            document.add_heading("Especies presentes, abundancia y densidad", level=3)
            zsp = zone_species[zone_species["zone_id"].astype(str).eq(zone_id)].copy() if not zone_species.empty else pd.DataFrame()
            _add_df_table(document, zsp, [
                ("Species", "Especie"), ("records", "Registros"), ("occupied_cells", "Celdas"),
                ("abundance", "Abundancia"), ("density", "Densidad ind./km²"),
            ], max_rows=100, sort_by="abundance", ascending=False, digits=2)

            document.add_heading("Diagnóstico de conservación", level=3)
            temporal_summary = _zone_temporal_summary(zone_id, selected_cells, temporal_changes)
            document.add_paragraph(
                f"La zona combina una prioridad ecológica {_clean_text(row.get('ecological_priority_class_zone')).lower()} con un índice ecológico medio de {_fmt(row.get('ecological_priority_score_mean'),1)} y una superficie marina de {_fmt(row.get('area_zone_km2'),2)} km². "
                f"El máximo LCBD es {_fmt(row.get('LCBD_max'),4)}, se reconocen {_fmt(row.get('hotspot_cells_multiscale'),0)} celdas hotspot multiescala y {_fmt(row.get('hotspot_cells_persistent_all_scales'),0)} persistentes en todas las escalas. "
                f"La cobertura protegida estimada es {_pct(row.get('pct_zone_protected'))}. En los cruces temporales de las celdas de la zona se contabilizan {temporal_summary['Persistencia']} persistencias, {temporal_summary['Ganancia']} ganancias y {temporal_summary['Pérdida']} pérdidas."
            )
            document.add_paragraph(
                "La interpretación anterior no atribuye causalidad. Una pérdida temporal puede reflejar esfuerzo/detectabilidad; una cobertura alta de figuras de protección no demuestra por sí sola que las medidas de gestión sean suficientes; y una zona sin protección no implica automáticamente que deba declararse una categoría jurídica concreta."
            )

            document.add_heading("Medidas de protección a considerar", level=3)
            measures = _zone_measures(row, zsp, temporal_summary, bool(conservation.get("protected_areas_loaded")))
            for i, measure in enumerate(measures, 1):
                _add_measure_block(document, measure, i)
                all_measure_rows.append({"zone_id": zone_id, **measure})

            document.add_heading("Plan de seguimiento y revisión", level=3)
            document.add_paragraph(
                "Como mínimo, el seguimiento de esta zona debería conservar series comparables de ocupación, número de registros, abundancia/densidad estandarizada, riqueza, hábitat, profundidad y esfuerzo. Cuando sea posible deben incorporarse estado reproductivo, juveniles, presión de fondeo, pesca/bycatch, obras/dragados y calidad del agua. La periodicidad y los umbrales de revisión deben adaptarse al nivel de evidencia y a las presiones confirmadas localmente."
            )

    if all_measure_rows:
        document.add_heading("11.A. Matriz sintética de medidas por zona", level=2)
        measure_frame = pd.DataFrame(all_measure_rows)
        _add_df_table(document, measure_frame, [("zone_id", "Zona"), ("category", "Categoría"), ("timeframe", "Horizonte"), ("evidence", "Evidencia")], max_rows=300, digits=0)
        document.add_heading("11.B. Vacíos de conservación", level=2)
        unprotected = zones[pd.to_numeric(zones.get("pct_zone_protected"), errors="coerce").fillna(0).lt(5)] if not zones.empty else pd.DataFrame()
        partial = zones[pd.to_numeric(zones.get("pct_zone_protected"), errors="coerce").between(5, 50, inclusive="left")] if not zones.empty else pd.DataFrame()
        mostly = zones[pd.to_numeric(zones.get("pct_zone_protected"), errors="coerce").ge(50)] if not zones.empty else pd.DataFrame()
        document.add_paragraph(
            f"La ejecución identifica {len(unprotected)} zonas con protección prácticamente ausente (<5 %), {len(partial)} con protección parcial (5–<50 %) y {len(mostly)} con al menos 50 % de cobertura. Esta clasificación es solo el primer nivel del diagnóstico: debe comprobarse si las celdas de mayor score, LCBD, persistencia y hábitat sensible son precisamente las cubiertas por los límites actuales."
        )

    # Discussion & limitations
    document.add_heading("12. Discusión integrada, limitaciones y precauciones", level=1)
    document.add_paragraph(
        "Los resultados de Hispa-Syng describen el patrón contenido en la base de datos de la ejecución y no deben interpretarse como un censo exhaustivo. El esfuerzo puede variar entre años, regiones, especies y hábitats; la detectabilidad no es constante; la accesibilidad costera puede concentrar observaciones; y la ausencia de registros no demuestra ausencia real."
    )
    document.add_paragraph(
        "La densidad usada por el programa es una densidad de individuos registrados por superficie marina de la unidad espacial, útil para comparar la distribución del conjunto de datos, pero no equivale necesariamente a densidad poblacional estimada mediante un diseño de muestreo probabilístico."
    )
    document.add_paragraph(
        "Los análisis multivariantes y espaciales deben interpretarse en conjunto. Un LCBD alto puede reflejar singularidad por composición; un hotspot puede reflejar riqueza o abundancia; la persistencia multiescala aporta robustez espacial; y la señal temporal aporta dinámica. La coincidencia de componentes independientes aumenta la base técnica de una prioridad, mientras que una señal aislada requiere mayor cautela."
    )
    document.add_paragraph(
        "Las medidas de protección propuestas son un sistema de apoyo a la decisión. Deben contrastarse con información local sobre usos, presión pesquera, fondeo, obras, calidad del agua, estado del hábitat, competencias administrativas, planes de gestión y viabilidad socioeconómica antes de su aplicación."
    )
    document.add_heading("Integración de evidencias", level=2)
    integrated = []
    if report_effort is not None and not report_effort.empty:
        intensity_col = "n_sampling_events" if ("n_sampling_events" in report_effort.columns and report_effort["n_sampling_events"].notna().any()) else "n_records"
        observed_effort = report_effort[pd.to_numeric(report_effort[intensity_col], errors="coerce").fillna(0).gt(0)]
        if not observed_effort.empty:
            max_year = observed_effort.sort_values(intensity_col, ascending=False, kind="stable").iloc[0]
            if intensity_col == "n_sampling_events":
                integrated.append(
                    f"La intensidad temporal basada en eventos proxy alcanza su máximo en {int(max_year['Year'])} con {_fmt(max_year['n_sampling_events'],0)} eventos ({_fmt(max_year.get('n_records'),0)} registros). Esta concentración obliga a interpretar los patrones temporales junto con la cobertura espacial, las fuentes de datos y la comparabilidad entre periodos; los eventos proxy no equivalen a esfuerzo de muestreo verdadero."
                )
            else:
                integrated.append(
                    f"El mayor volumen anual de datos se registra en {int(max_year['Year'])} con {_fmt(max_year['n_records'],0)} registros. Al no estar disponible el proxy de eventos en esta tabla, este volumen no se interpreta como esfuerzo de muestreo."
                )
    perm = community.get("permanova", {})
    decay = community.get("distance_decay_summary", {})
    if isinstance(perm, dict) and _num(perm.get("p_value")) is not None:
        p_perm = _num(perm.get("p_value"))
        r2_perm = _num(perm.get("R2"))
        rho_decay = _num(decay.get("mantel_rho")) if isinstance(decay, dict) else None
        integrated.append(
            f"La composición comunitaria se contrasta principalmente mediante PERMANOVA Hellinger–Euclídea (p={_fmt(p_perm,4)}, R²={_fmt(r2_perm,3) if r2_perm is not None else 'N.D.'}); el distance-decay se evalúa inferencialmente mediante Mantel-Spearman Hellinger (ρ={_fmt(rho_decay,3) if rho_decay is not None else 'N.D.'}). Jaccard aporta el contraste de incidencia y Bray–Curtis bruto se conserva como sensibilidad."
        )
    lcbd_frame = community.get("lcbd", pd.DataFrame())
    if lcbd_frame is not None and not lcbd_frame.empty:
        sig_col = "significant_FDR" if "significant_FDR" in lcbd_frame else "LCBD_significant_FDR" if "LCBD_significant_FDR" in lcbd_frame else None
        n_sig_lcbd = int(lcbd_frame[sig_col].fillna(False).astype(bool).sum()) if sig_col else 0
        n_concordant = int(lcbd_frame.get("LCBD_FDR_concordant", pd.Series(False, index=lcbd_frame.index)).fillna(False).astype(bool).sum())
        integrated.append(
            f"Se identifican {n_sig_lcbd} celdas con LCBD-Jaccard significativo tras BH-FDR y {n_concordant} con señal FDR concordante Jaccard–Hellinger. La singularidad se informa separadamente del soporte de muestreo y no se interpreta como una evidencia independiente adicional cuando posteriormente se combine con hotspots o persistencia derivados del mismo LCBD."
        )
    if not zones.empty:
        pct = pd.to_numeric(zones.get("pct_zone_protected"), errors="coerce")
        integrated.append(
            f"Las {len(zones)} zonas prioritarias estratégicas constituyen la síntesis espacial de estas evidencias. {_fmt(pct.fillna(0).lt(5).sum(),0)} tienen <5 % de cobertura protegida y {_fmt(pct.fillna(0).between(5,50,inclusive='left').sum(),0)} presentan cobertura parcial. La respuesta de gestión debe distinguir entre vacío espacial, insuficiencia de gestión dentro de una figura existente, necesidad de restauración y necesidad de mejorar la evidencia."
        )
    changes_frame = temporal.get("cell_changes", pd.DataFrame())
    if changes_frame is not None and not changes_frame.empty and "status" in changes_frame:
        counts = changes_frame["status"].astype(str).value_counts()
        integrated.append(
            f"La señal temporal incluye {int(counts.get('Persistencia',0))} persistencias, {int(counts.get('Ganancia',0))} ganancias y {int(counts.get('Pérdida',0))} pérdidas. Las pérdidas en zonas de alta prioridad justifican verificación dirigida, mientras que persistencias multiescala y temporales aportan una base más robusta para conservación preventiva."
        )
    for paragraph in integrated:
        p_int = document.add_paragraph(paragraph)
        p_int.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    document.add_heading("Implicaciones para seguimiento y gestión", level=2)
    document.add_paragraph(
        "El diseño de seguimiento debería concentrarse en reducir las principales fuentes de incertidumbre detectadas por la propia ejecución: desigualdad temporal del esfuerzo, regiones o hábitats con baja cobertura, celdas prioritarias con soporte limitado y zonas donde la señal temporal no es comparable. La repetición estandarizada en las mismas unidades espaciales es necesaria para separar cambios de observación de cambios ecológicos."
    )
    document.add_paragraph(
        "Para las zonas prioritarias estratégicas y sus huellas operativas, la secuencia técnica recomendada es: (1) confirmar valores y presiones en campo; (2) comprobar si el núcleo ecológico está cubierto por figuras de protección y por medidas de gestión efectivas; (3) seleccionar medidas proporcionales al diagnóstico; (4) asociar cada medida a indicadores cuantificables; y (5) revisar periódicamente la zona con nuevas ejecuciones de Hispa-Syng usando criterios comparables."
    )

    # Conclusions
    document.add_heading("13. Conclusiones", level=1)
    conclusions = [
        f"La ejecución integra {total_records} registros y {_fmt(total_individuals,0)} individuos de {n_species} especies en una malla marina oficial de {selected_grid_km} km.",
        f"Se han delimitado {n_zones} zonas prioritarias estratégicas y {n_operational_zones} zonas operativas de conservación. Las primeras sintetizan múltiples componentes ecológicos y de robustez; las segundas focalizan la huella observada de 1 km sin recalcular prioridad.",
    ]
    if n_zones:
        conclusions.append(f"{n_unprotected} zonas no presentan solapamiento con las figuras de protección disponibles y {n_low_protection} tienen menos del 50 % de cobertura; estas zonas requieren una evaluación detallada del vacío espacial y de la efectividad de gestión.")
    if temporal.get("cell_changes") is not None and len(temporal.get("cell_changes", [])):
        conclusions.append("Los cambios temporales deben interpretarse conjuntamente con esfuerzo y detectabilidad; las zonas con pérdidas requieren verificación dirigida antes de atribuir declive o plantear restauración.")
    conclusions.extend([
        "Las recomendaciones de conservación se han adaptado a las características de cada zona y separan protección espacial, efectividad de gestión, hábitat, presiones potenciales, restauración, conectividad, incertidumbre y seguimiento.",
        "El valor principal del informe es integrar resultados ecológicos, espaciales, temporales y de protección en una síntesis trazable; no sustituye la validación de campo ni la evaluación normativa de las administraciones competentes.",
    ])
    for conclusion in conclusions:
        document.add_paragraph(conclusion, style="List Bullet")

    # Traceability
    document.add_heading("14. Trazabilidad y anexos", level=1)
    document.add_paragraph(
        "Las tablas completas, figuras, GeoPackages, modelos, mapas interactivos, manifiestos y controles de calidad permanecen en las carpetas de resultados de esta misma ejecución. El informe resume e interpreta esos productos sin sustituirlos."
    )
    document.add_paragraph(
        "Todas las rutas que siguen parten de la raíz del programa Hispa-Syng. No se incluye ninguna ruta absoluta ni referencia al ordenador concreto en el que se ejecutó el análisis."
    )
    program_run = f"Resultados/{run_root.name}"
    _add_kv_table(document, [
        ("Raíz de referencia", "<raíz_del_programa_Hispa-Syng>/"),
        ("Resultados de esta ejecución", program_run + "/"),
        ("Carpeta del informe técnico", program_run + "/10_informe_tecnico/"),
        ("Control de calidad", program_run + "/07_control_calidad/"),
        ("Resultados de zonas prioritarias", program_run + "/09_zonas_prioritarias_conservacion/"),
        ("Visores interactivos", program_run + "/08_visores/"),
    ])
    document.add_heading("14.A. Localización de los archivos del análisis", level=2)
    folder_locations = _folder_locations_es(run_root, output_dir).copy()
    if not folder_locations.empty:
        folder_locations["ruta"] = folder_locations["ruta"].map(lambda x: program_run + "/" + str(x).lstrip("/"))
    _add_df_table(document, folder_locations, [("tipo", "Bloque"), ("ruta", "Ruta desde la raíz del programa"), ("contenido", "Contenido principal")], max_rows=30, digits=0)
    document.add_paragraph(
        "Fin del informe. Todos los valores deben poder rastrearse a los productos de la ejecución actual."
    )

    _add_footer(document)
    LOGGER.info("    [8/8 · 4/4] Guardado del informe técnico integral")
    document.save(path)
    return path
