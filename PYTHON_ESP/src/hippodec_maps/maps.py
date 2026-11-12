"""Preparación de datos y renderizado de mapas HTML."""

from __future__ import annotations

import base64
import html
import json
import math
import os
import re
import webbrowser
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from shapely.geometry import mapping

from .output_policy import register_public_output, public_product, polygonal_public_features
from .config import RunParameters
from .localization import (
    is_habitat_field,
    is_preserved_text_field,
    translate_habitat_value,
    translate_text,
)


SET1 = [
    "#E41A1C",
    "#377EB8",
    "#4DAF4A",
    "#984EA3",
    "#FF7F00",
    "#FFFF33",
    "#A65628",
    "#F781BF",
]


_LEAFLET_LAYER_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 26 26"><path d="M3 8 13 3l10 5-10 5Z" fill="#fff" stroke="#333" stroke-width="1.4" stroke-linejoin="round"/><path d="m3 12 10 5 10-5M3 16l10 5 10-5" fill="none" stroke="#333" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
_LEAFLET_MARKER_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="25" height="41" viewBox="0 0 25 41"><path d="M12.5 1C6.15 1 1 6.15 1 12.5 1 21.13 12.5 40 12.5 40S24 21.13 24 12.5C24 6.15 18.85 1 12.5 1Z" fill="#2a81cb" stroke="#fff" stroke-width="1.5"/><circle cx="12.5" cy="12.5" r="4.5" fill="#fff"/></svg>"""
_LEAFLET_MARKER_SHADOW_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="41" height="41" viewBox="0 0 41 41"><ellipse cx="22" cy="31" rx="15" ry="4.5" transform="rotate(-12 22 31)" fill="#000" opacity=".28"/></svg>"""


def _svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(
        svg.encode("utf-8")
    ).decode("ascii")


def _color_ramp(base: list[str], count: int) -> list[str]:
    """Interpolación RGB equivalente a colorRampPalette de R."""
    count = max(1, count)
    if count == 1:
        return [base[0]]
    positions = np.linspace(0, len(base) - 1, count)
    output: list[str] = []
    for position in positions:
        left = int(math.floor(position))
        right = min(left + 1, len(base) - 1)
        fraction = position - left
        rgb_left = tuple(
            int(base[left][offset : offset + 2], 16) for offset in (1, 3, 5)
        )
        rgb_right = tuple(
            int(base[right][offset : offset + 2], 16) for offset in (1, 3, 5)
        )
        rgb = tuple(round(a + (b - a) * fraction) for a, b in zip(rgb_left, rgb_right))
        output.append("#" + "".join(f"{channel:02X}" for channel in rgb))
    return output


def _environment() -> Environment:
    template_dir = Path(__file__).resolve().parent / "templates"
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=("html",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _leaflet_assets() -> tuple[str, str]:
    """Carga Leaflet y convierte sus imágenes auxiliares en recursos internos."""

    vendor = Path(__file__).resolve().parent / "vendor" / "leaflet"
    css_path = vendor / "leaflet.css"
    js_path = vendor / "leaflet.js"
    if not css_path.exists() or not js_path.exists():
        raise FileNotFoundError(
            "Faltan los recursos locales de Leaflet necesarios para crear el mapa."
        )
    layer_icon = _svg_data_uri(_LEAFLET_LAYER_ICON_SVG)
    marker_icon = _svg_data_uri(_LEAFLET_MARKER_ICON_SVG)
    marker_shadow = _svg_data_uri(_LEAFLET_MARKER_SHADOW_SVG)
    leaflet_css = css_path.read_text(encoding="utf-8")
    leaflet_css = leaflet_css.replace(
        "url(images/layers.png)", f'url("{layer_icon}")'
    ).replace(
        "url(images/layers-2x.png)", f'url("{layer_icon}")'
    ).replace(
        "url(images/marker-icon.png)", f'url("{marker_icon}")'
    )
    leaflet_js = js_path.read_text(encoding="utf-8")
    icon_options = json.dumps(
        {
            "iconRetinaUrl": marker_icon,
            "iconUrl": marker_icon,
            "shadowUrl": marker_shadow,
        },
        separators=(",", ":"),
    )
    leaflet_js += f"\nL.Icon.Default.mergeOptions({icon_options});\n"
    return leaflet_css, leaflet_js


def _json_for_script(value: object) -> str:
    def localize(item: object, field_name: object | None = None) -> object:
        if isinstance(item, str):
            if is_habitat_field(field_name):
                return translate_habitat_value(item)
            if is_preserved_text_field(field_name):
                return item
            return translate_text(item)
        if isinstance(item, list):
            return [localize(element, field_name) for element in item]
        if isinstance(item, tuple):
            return [localize(element, field_name) for element in item]
        if isinstance(item, dict):
            return {
                key: localize(element, key)
                for key, element in item.items()
            }
        return item
    return json.dumps(
        localize(value), ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).replace("</", "<\\/")


def _finite(value: object, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _display(value: object, digits: int | None = None) -> str:
    number = _finite(value)
    if number is None:
        return "N.D."
    if digits is None:
        digits = 0
    formatted = f"{number:,.{digits}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def _display_unit(value: object, digits: int, unit: str) -> str:
    shown = _display(value, digits)
    return shown if shown == "N.D." else f"{shown} {unit}"


def _text(value: object, default: str = "N.D.", max_chars: int | None = None) -> str:
    """Devuelve texto seguro para una ventana HTML, incluidos los ausentes."""

    try:
        missing = bool(pd.isna(value))
    except (TypeError, ValueError):
        missing = value is None
    if missing:
        return default
    text = str(value).strip()
    if not text:
        return default
    if max_chars is not None and len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return html.escape(text)


def _identifier(value: object) -> str:
    """Conserva identificadores y evita el sufijo .0 en los valores numéricos."""

    if isinstance(value, (int, float, np.integer, np.floating)):
        number = _finite(value)
        if number is None:
            return "N.D."
        if number.is_integer():
            return str(int(number))
    return _text(value)


def _safe_link(value: object) -> str:
    """Crea un enlace de observación únicamente para direcciones HTTP(S)."""

    if value is None or pd.isna(value):
        return "N.D."
    url = str(value).strip()
    source_match = re.fullmatch(
        r"https?:--www\.observadoresdelmar\.es-Observations-([0-9-]+)",
        url,
        flags=re.IGNORECASE,
    )
    if source_match:
        url = (
            "https://www.observadoresdelmar.es/Observations/"
            + source_match.group(1).replace("-", "/")
        )
    if not url.lower().startswith(("http://", "https://")):
        return _text(url, max_chars=180)
    safe_url = html.escape(url, quote=True)
    return (
        f'<a class="popup-link" href="{safe_url}" target="_blank" '
        'rel="noopener noreferrer">Abrir registro externo</a>'
    )


def _popup_rows(rows: list[tuple[str, str]]) -> str:
    return "<dl class=\"popup-kv\">" + "".join(
        f"<dt>{html.escape(label)}</dt><dd>{value}</dd>" for label, value in rows
    ) + "</dl>"


def logo_data_uri(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def common_context(params: RunParameters, logo_uri: str) -> dict[str, object]:
    return {
        "product": "Hispa-Syng v1.0",
        "brand_label": "Hispa-Syng v1.0 (Proyecto Hippo-DEC)",
        "project": "Hippo-DEC",
        "author": "Miquel Planas Oliver",
        "institution": "Instituto de Investigaciones Marinas (IIM-CSIC)",
        "year_min": params.year_min,
        "year_max": params.year_max,
        "grid_km": params.grid_km,
        "region_label": params.region_label,
        "creation_date": date.today().strftime("%d-%m-%Y"),
        "logo_uri": logo_uri,
        "project_security_protected": os.environ.get("HISPA_SYNG_SECURITY_MODE", "open").casefold() == "protected",
        "download_password_hash": "",
        "priority_download_password_hash": "",
    }


def build_map1_observations(
    data: pd.DataFrame,
) -> tuple[list[dict[str, object]], list[str], dict[str, str]]:
    out = data.copy()
    counts = out.groupby(["Longitude", "Latitude", "Species_clean"], dropna=False)[
        "source_row"
    ].transform("size")
    out["N_observaciones"] = counts
    rng = np.random.default_rng(42)
    out["Longitude_map"] = out["Longitude"] + rng.uniform(-0.0001, 0.0001, len(out))
    out["Latitude_map"] = out["Latitude"] + rng.uniform(-0.0001, 0.0001, len(out))
    species = sorted(out["Species_clean"].dropna().astype(str).unique().tolist())
    palette = _color_ramp(SET1, max(8, len(species)))
    colors = {name: palette[index] for index, name in enumerate(species)}
    records: list[dict[str, object]] = []
    for _, row in out.iterrows():
        n_total = _finite(row.get("N_total"), 0.0)
        n_obs = int(row["N_observaciones"])
        base = max(3.0, math.sqrt(max(n_total, 0) + 1) * 2)
        radius = max(base * math.log1p(n_obs) * 1.3, 3.0)
        species_name = str(row["Species_clean"])
        fecha = row.get("Fecha_aux")
        date_text = fecha.strftime("%d-%m-%Y") if pd.notna(fecha) else "N.D."
        complete_taxon = _text(row.get("Species"))
        original_id = _identifier(row.get("Id"))
        observation_id = _identifier(row.get("obs_id"))
        source_row = _identifier(row.get("source_row"))
        region = _text(row.get("Region_MITECO"))
        latitude = _display(row.get("Latitude"), 6)
        longitude = _display(row.get("Longitude"), 6)
        x_coord = _display(row.get("X"), 1)
        y_coord = _display(row.get("Y"), 1)
        epsg = _text(row.get("EPSG"))
        sex_rows = _popup_rows(
            [
                ("N total", _display(n_total)),
                ("Hembras", _display(row.get("N hembra"))),
                ("Machos", _display(row.get("N macho"))),
                ("Indeterminados", _display(row.get("N_indeterminado"))),
                ("Presencia / ausencia", _identifier(row.get("P_A"))),
            ]
        )
        environment_rows = _popup_rows(
            [
                ("Profundidad", _display_unit(row.get("Depth"), 1, "m")),
                (
                    "Temperatura",
                    _display_unit(row.get("Temperatura_gC"), 1, "°C"),
                ),
                    (
                        "Hábitat",
                        _text(
                            translate_habitat_value(row.get("Habitat")),
                            max_chars=260,
                        ),
                    ),
                ("Captura incidental", _text(row.get("Captura incidental"))),
            ]
        )
        record_rows = _popup_rows(
            [
                ("Fecha", date_text),
                ("Id de origen (metadato)", original_id),
                ("Id interno de observación", observation_id),
                ("Fila de origen", source_row),
                ("Región MITECO", region),
                ("Observaciones coincidentes", str(n_obs)),
            ]
        )
        provenance_rows = _popup_rows(
            [
                ("Observador/a", _text(row.get("Observer"), max_chars=160)),
                ("Enlace", _safe_link(row.get("Link observation"))),
                # Mantiene intacto el comentario de origen en los datos
                # descargables, pero traduce las categorías de hábitat en la
                # ventana emergente para que el HTML independiente no oculte
                # categorías sin traducir dentro del texto libre.
                (
                    "Comentarios",
                    _text(
                        translate_habitat_value(row.get("Comments")),
                        max_chars=600,
                    ),
                ),
            ]
        )
        coordinate_rows = _popup_rows(
            [
                ("Latitud original", f"{latitude}°"),
                ("Longitud original", f"{longitude}°"),
                ("X / Y de origen", f"{x_coord} / {y_coord}"),
                ("EPSG de origen", epsg),
            ]
        )
        popup = (
            '<div class="popup-card">'
            f'<div class="popup-title"><i>{html.escape(species_name)}</i></div>'
            f'<div class="popup-subtitle">{complete_taxon}</div>'
            '<div class="popup-section-title">Registro</div>'
            f"{record_rows}"
            '<div class="popup-section-title">Abundancia y composición sexual</div>'
            f"{sex_rows}"
            '<div class="popup-section-title">Ambiente y captura</div>'
            f"{environment_rows}"
            '<div class="popup-section-title">Procedencia y observaciones</div>'
            f"{provenance_rows}"
            '<div class="popup-section-title">Coordenadas originales</div>'
            f"{coordinate_rows}"
            '<div class="popup-note">La posición dibujada puede estar desplazada hasta '
            "0,0001° para separar registros coincidentes.</div></div>"
        )
        records.append(
            {
                "lat": float(row["Latitude_map"]),
                "lon": float(row["Longitude_map"]),
                "species": species_name,
                # Este es el campo de hábitat explícitamente visible que usa
                # el validador HTML. El campo de texto libre Comentarios conserva
                # el origen en las exportaciones; solo se localiza su ventana.
                "habitat": translate_habitat_value(row.get("Habitat")),
                "color": colors[species_name],
                "radius": round(radius, 3),
                "popup": popup,
            }
        )
    return records, species, colors


def _lookup_by_grid(
    table: pd.DataFrame, value_columns: list[str]
) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for grid_id, subset in table.groupby("grid_id", sort=False):
        rows: list[dict[str, object]] = []
        for record in subset[value_columns].to_dict("records"):
            clean = {
                key: _finite(value, value if isinstance(value, str) else None)
                for key, value in record.items()
            }
            rows.append(clean)
        result[str(grid_id)] = rows
    return result


def _rename_map_record_fields(
    lookup: dict[str, list[dict[str, object]]],
    field_map: dict[str, str],
) -> dict[str, list[dict[str, object]]]:
    """Expone nombres estables para los campos JSON de los mapas.

    Las tablas analíticas conservan sus nombres internos porque los utiliza el
    flujo estadístico. El JSON del navegador constituye una interfaz separada.
    """

    return {
        grid_id: [
            {field_map.get(key, key): value for key, value in record.items()}
            for record in records
        ]
        for grid_id, records in lookup.items()
    }


def cells_feature_collection(
    occupied: gpd.GeoDataFrame,
    species_metrics: pd.DataFrame,
    sex_metrics: pd.DataFrame,
    simplify_m: float = 0,
) -> tuple[dict, list[str], dict[str, str], list[str]]:
    cells = occupied.copy()
    if simplify_m > 0:
        cells.geometry = cells.geometry.simplify(simplify_m, preserve_topology=True)
    cells = cells.to_crs(4326)
    species_lookup = _lookup_by_grid(
        species_metrics,
        ["Species", "N_sum", "Densidad_ajustada", "pct_rel"],
    )
    species_lookup = _rename_map_record_fields(
        species_lookup,
        {
            "N_sum": "abundance",
            "Densidad_ajustada": "density",
            "pct_rel": "relative_abundance_pct",
        },
    )
    sex_lookup = _lookup_by_grid(
        sex_metrics,
        [
            "Species",
            "N_hembras",
            "N_machos",
            "N_indeterminados",
            "N_sexados",
            "ratio_HM",
            "prop_hembras",
            "sesgo_sexual",
        ],
    )
    sex_lookup = _rename_map_record_fields(
        sex_lookup,
        {
            "N_hembras": "female_count",
            "N_machos": "male_count",
            "N_indeterminados": "indeterminate_count",
            "N_sexados": "sexed_count",
            "ratio_HM": "female_male_ratio",
            "prop_hembras": "female_proportion",
            "sesgo_sexual": "sex_bias",
        },
    )
    all_species = sorted(
        species_metrics["Species"].dropna().astype(str).unique().tolist()
    )
    dominant_species = sorted(
        cells["Species_dom"].dropna().astype(str).unique().tolist()
    )
    dominant_palette = _color_ramp(SET1, max(8, len(dominant_species)))
    dominant_colors = {
        name: dominant_palette[index] for index, name in enumerate(dominant_species)
    }
    sex_species = sorted(sex_metrics["Species"].dropna().astype(str).unique().tolist())
    features = []
    for row in cells.itertuples(index=False):
        grid_id = str(getattr(row, "grid_id"))
        species_rows = species_lookup.get(grid_id, [])
        sex_rows = sex_lookup.get(grid_id, [])
        properties = {
            "grid_id": grid_id,
            "official_cell_code": str(getattr(row, "official_cell_code")),
            "area": _finite(getattr(row, "Area_mar_km2"), 0),
            "region": str(getattr(row, "Region_MITECO")),
            "abundance": _finite(getattr(row, "N_total_celda"), 0),
            "richness": int(getattr(row, "n_especies")),
            "density": _finite(getattr(row, "Densidad_total"), 0),
            "n_obs": int(getattr(row, "n_obs_cell")),
            "n_years": int(getattr(row, "n_years_cell")),
            "q_total": _finite(getattr(row, "Q_total"), 0),
            "quality": str(getattr(row, "calidad")),
            "dominant": str(getattr(row, "Species_dom")),
            "dominant_n": _finite(getattr(row, "N_sum_dom"), 0),
            "dominant_color": dominant_colors.get(
                str(getattr(row, "Species_dom")), "#d9d9d9"
            ),
            "species_metrics": species_rows,
            "sex_metrics": {
                str(item["Species"]): item for item in sex_rows if item.get("Species")
            },
        }
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(getattr(row, "geometry")),
                "properties": properties,
            }
        )
    return (
        {"type": "FeatureCollection", "features": features},
        all_species,
        dominant_colors,
        sex_species,
    )


def render_html(
    template_name: str,
    destination: Path,
    context: dict[str, object],
    open_browser: bool = False,
    page_key: str | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(context)
    payload["language_switch"] = _prepare_language_switch(
        context.get("language_switch"), destination, page_key
    )
    public_templates = {"map2.html": "aggregate_map2", "map3.html": "aggregate_map3",
                        "conservation.html": "aggregate_conservation", "viewer.html": "viewer"}
    if template_name in public_templates:
        from .output_policy import validate_public_data
        validate_public_data(payload, allow_official_protection=template_name == "conservation.html")
    rendered = _environment().get_template(template_name).render(**payload)
    destination.write_text(rendered, encoding="utf-8")
    if template_name in public_templates:
        register_public_output(destination, public_templates[template_name], payload)
    if open_browser:
        webbrowser.open(destination.resolve().as_uri())
    # Las plantillas estáticas están en español en esta edición. Traducir todo
    # el HTML después de renderizarlo también alteraría identificadores
    # JavaScript y atributos data-*, por lo que aquí solo se localizan valores
    # dinámicos antes de la renderización.
    return destination


def _prepare_language_switch(
    value: object,
    destination: Path,
    page_key: str | None,
) -> dict[str, object]:
    """Convierte los destinos lógicos en enlaces relativos al HTML actual."""

    if not isinstance(value, dict) or not value.get("enabled") or not page_key:
        return {"enabled": False}
    targets = value.get("targets", {})
    page_targets = targets.get(page_key, {}) if isinstance(targets, dict) else {}
    if not isinstance(page_targets, dict):
        return {"enabled": False}
    links: dict[str, str] = {}
    for code in ("ES", "EN"):
        target = page_targets.get(code)
        if target:
            links[code] = os.path.relpath(
                Path(str(target)).expanduser().resolve(),
                start=destination.parent.expanduser().resolve(),
            ).replace(os.sep, "/")
    if not links.get("ES") or not links.get("EN"):
        return {"enabled": False}
    labels = value.get("labels", {})
    if not isinstance(labels, dict):
        labels = {}
    return {
        "enabled": True,
        "current": str(value.get("current", "ES")).upper(),
        "labels": {
            "ES": str(labels.get("ES", "Español")),
            "EN": str(labels.get("EN", "English")),
        },
        "control_label": str(value.get("control_label", "Idioma / Language")),
        "links": links,
    }


def rewrite_language_switch(
    path: Path,
    switch: object,
    destination: Path | None = None,
    page_key: str | None = None,
) -> Path:
    """Recalcula los enlaces del selector después de copiar un HTML."""

    destination = destination or path
    prepared = _prepare_language_switch(switch, destination, page_key)
    if not prepared.get("enabled"):
        return path
    product = public_product(path)
    text = path.read_text(encoding="utf-8")
    for code in ("ES", "EN"):
        link = html.escape(str(prepared["links"][code]), quote=True)
        text = re.sub(
            rf'(data-{code.lower()}-url=")[^"]*(")',
            rf"\g<1>{link}\g<2>",
            text,
            count=1,
        )
    path.write_text(text, encoding="utf-8")
    if product:
        register_public_output(path, product)
    return path


def render_map1(
    destination: Path,
    observations: list[dict[str, object]],
    species: list[str],
    colors: dict[str, str],
    boundaries: dict,
    coastline: dict,
    context: dict[str, object],
    open_browser: bool,
    downloads: dict[str, str] | None = None,
) -> Path:
    payload = dict(context)
    leaflet_css, leaflet_js = _leaflet_assets()
    payload.update(
        observations_json=_json_for_script(observations),
        species_json=_json_for_script(species),
        colors_json=_json_for_script(colors),
        leaflet_css=leaflet_css,
        leaflet_js=leaflet_js,
        downloads=downloads or {},
    )
    return render_html("map1.html", destination, payload, open_browser, "map1")


def render_map2(
    destination: Path,
    cells: dict,
    species: list[str],
    boundaries: dict,
    coastline: dict,
    context: dict[str, object],
    open_browser: bool,
    downloads: dict[str, str] | None = None,
) -> Path:
    payload = dict(context)
    leaflet_css, leaflet_js = _leaflet_assets()
    payload.update(
        cells_json=_json_for_script(polygonal_public_features(cells)),
        species_json=_json_for_script(species),
        leaflet_css=leaflet_css,
        leaflet_js=leaflet_js,
        downloads=downloads or {},
    )
    return render_html("map2.html", destination, payload, open_browser, "map2")


def render_map3(
    destination: Path,
    cells: dict,
    dominant_colors: dict[str, str],
    sex_species: list[str],
    boundaries: dict,
    coastline: dict,
    context: dict[str, object],
    open_browser: bool,
    downloads: dict[str, str] | None = None,
) -> Path:
    payload = dict(context)
    leaflet_css, leaflet_js = _leaflet_assets()
    payload.update(
        cells_json=_json_for_script(polygonal_public_features(cells)),
        dominant_colors_json=_json_for_script(dominant_colors),
        sex_species_json=_json_for_script(sex_species),
        leaflet_css=leaflet_css,
        leaflet_js=leaflet_js,
        downloads=downloads or {},
    )
    return render_html("map3.html", destination, payload, open_browser, "map3")


def render_conservation_map(
    destination: Path,
    cells: dict,
    descriptive_cells: dict,
    zones: dict,
    operational_zones: dict,
    protected: dict,
    coastline: dict,
    bounds: tuple[float, float, float, float],
    context: dict[str, object],
    downloads: dict[str, str] | None = None,
) -> Path:
    """Crea el mapa 21 autocontenido sin Folium ni dependencia de CDN de Leaflet."""

    payload = dict(context)
    leaflet_css, leaflet_js = _leaflet_assets()
    payload.update(
        cells_json=_json_for_script(polygonal_public_features(cells)),
        descriptive_cells_json=_json_for_script(polygonal_public_features(descriptive_cells)),
        zones_json=_json_for_script(polygonal_public_features(zones)),
        operational_zones_json=_json_for_script(polygonal_public_features(operational_zones)),
        protected_json=_json_for_script(protected),
        map_bounds_json=_json_for_script(list(bounds)),
        leaflet_css=leaflet_css,
        leaflet_js=leaflet_js,
        downloads=downloads or {},
    )
    return render_html("conservation.html", destination, payload, False, "priority")


def render_viewer(
    destination: Path,
    map1_name: str,
    map2_name: str,
    map3_name: str,
    priority_map_name: str | None,
    downloads: dict[str, dict[str, str]] | None,
    context: dict[str, object],
    open_browser: bool,
) -> Path:
    payload = dict(context)
    payload.update(
        map1_name=map1_name,
        map2_name=map2_name,
        map3_name=map3_name,
        priority_map_name=priority_map_name,
        downloads=downloads or {},
    )
    return render_html("viewer.html", destination, payload, open_browser, "viewer")
