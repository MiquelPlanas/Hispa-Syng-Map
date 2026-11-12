"""English presentation layer for the international Hippo-DEC edition.

Input field aliases remain untouched so the original Spanish workbook can be
read verbatim. Translation is applied only to user-facing text and exports.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


EXACT: dict[str, str] = {
    "Baja": "Low", "Media": "Medium", "Alta": "High", "Muy alta": "Very high",
    "No evaluable / evidencia ecológica insuficiente": "Not evaluable / insufficient ecological evidence",
    "No evaluable / datos insuficientes": "Not evaluable / insufficient data", "Sin capacidad de discriminación": "No discriminatory capacity",
    "No aplicable": "Not applicable",
    "No alta en escenarios ecológicos": "Not high under ecological scenarios",
    "Sensible a ponderación ecológica": "Sensitive to ecological weighting",
    "Estable en 2 escenarios ecológicos": "Stable under 2 ecological scenarios",
    "Estable en 3 escenarios ecológicos": "Stable under 3 ecological scenarios",
    "Ganancia": "Gain", "Pérdida": "Loss", "Persistencia": "Persistence", "Ausente": "Absent",
    "Ausencia en ambos": "Absence in both", "No comparable": "Not comparable",
    "Aumento": "Increase", "Descenso": "Decline", "Estable": "Stable",
    "Intermedia": "Intermediate", "Sin región": "No region", "sin_datos": "No data",
    "canarias": "Canary Islands", "cantabrica": "North-western Cantabrian subregion",
    "sudatlantica": "South Atlantic subregion", "levantina": "Levantine-Balear subregion",
    "alboran": "Strait of Gibraltar and Alboran Sea",
    "Regresión lineal": "Linear regression", "Chi-cuadrado": "Chi-square", "sexo": "sex",
    "Sin tendencia estimable": "Trend not estimable", "No hotspot": "Not a hotspot",
    "No calculado": "Not calculated", "Sin solape": "No overlap",
    "Sin información de protección": "No protection information",
    "Sin capa de áreas protegidas": "No protected-area layer",
    "Todas las demarcaciones marinas (MITECO)": "All MITECO marine subdivisions",
    "Islas Canarias": "Canary Islands",
    "Demarcación marina noratlántica": "North Atlantic marine subdivision",
    "Demarcación marina sudatlántica": "South Atlantic marine subdivision",
    "Demarcación marina del Estrecho y Alborán": "Strait and Alboran marine subdivision",
    "Demarcación marina levantino-balear": "Levantine-Balearic marine subdivision",
    "Noratlántica": "North Atlantic", "Sudatlántica": "South Atlantic",
    "Subregión Cantábrica Noroccidental": "North-western Cantabrian subregion",
    "Subregión Sudatlántica": "South Atlantic subregion",
    "Subregión Levantino-Balear": "Levantine-Balearic subregion",
    "Estrecho de Gibraltar y Mar de Alborán": "Strait of Gibraltar and Alboran Sea",
    "Presencia": "Presence", "Ausencia": "Absence",
    "Zona de singularidad persistente multiescala": "Persistent multiscale singularity area",
    "Zona de singularidad multiescala": "Multiscale singularity area",
    "Zona de singularidad dependiente de escala": "Scale-dependent singularity area",
    "Zona de alta singularidad comunitaria": "High community-singularity area",
    "Zona núcleo de riqueza específica": "Core species-richness area",
    "Zona de alerta o seguimiento temporal": "Temporal alert or monitoring area",
    "Zona de interés complementario": "Complementary-interest area",
    "Hotspot alto y significativo persistente": "Persistent high and significant hotspot",
    "Hotspot alto y significativo multiescala": "Multiscale high and significant hotspot",
    "Hotspot alto y significativo dependiente de escala": "Scale-dependent high and significant hotspot",
    "Estable en 3 escenarios": "Stable under 3 scenarios",
    "Estable en 2 escenarios": "Stable under 2 scenarios",
    "Sensible a la ponderación": "Sensitive to weighting",
    "No prioritaria en escenarios": "Not prioritised under the scenarios",
    "No prioritaria": "Not prioritised",
    "Media-alta": "Medium-high",
    "No clasificado": "Unclassified", "No calculada": "Not calculated",
    "Figura de protección": "Protection designation",
    "Capa de áreas protegidas": "Protected-area layer",
    "Alta prioridad ya ampliamente protegida": "High-priority area already extensively protected",
    "Alta prioridad mayoritariamente protegida": "High-priority area mostly protected",
    "Alta prioridad parcialmente protegida": "High-priority area partially protected",
    "Alta prioridad próxima a protección existente": "High-priority area close to existing protection",
    "Alta prioridad no protegida": "Unprotected high-priority area",
    "Sin solape MITECO detectado": "No MITECO overlap detected",
    "Priority muy alta por hotspot alto y significativo persistente entre escalas, elevada riqueza y singularidad comunitaria.": "Very high priority due to a persistent high and significant hotspot across scales, high richness, and community singularity.",
    "Priority muy alta por hotspot alto y significativo en varias escalas espaciales.": "Very high priority due to a high and significant hotspot at several spatial scales.",
    "Priority muy alta por LCBD elevado, indicativo de composición comunitaria singular.": "Very high priority due to elevated LCBD, indicating a distinctive community composition.",
    "Priority alta por hotspot alto y significativo, aunque dependiente de la escala.": "High priority due to a high and significant hotspot, although scale-dependent.",
    "Priority alta por elevada riqueza específica dentro de la malla analizada.": "High priority due to elevated species richness within the analysed grid.",
    "Priority media por acumulación moderada de criterios de riqueza, abundancia o singularidad.": "Medium priority due to a moderate accumulation of richness, abundance, or singularity criteria.",
    "Prioridad baja o complementaria; no alcanza los umbrales ecológicos para formar una zona prioritaria principal.": "Low or complementary priority; ecological thresholds for forming a main priority area are not reached.",
    "Validación de campo prioritaria por soporte de datos limitado": "Priority field validation due to limited data support",
    "Contrastar la evidencia ecológica y ampliar el seguimiento": "Verify the ecological evidence and expand monitoring",
    "Revisar con escenarios alternativos y conocimiento experto": "Review using alternative scenarios and expert knowledge",
    "Validación ordinaria antes de decisiones de gestión": "Standard validation before management decisions",
    "Seguimiento complementario": "Complementary monitoring",
    "Priorizar validación, seguimiento específico y evaluación de protección o conectividad": "Prioritise validation, targeted monitoring, and assessment of protection or connectivity",
    "Evaluar presiones, hábitat y suficiencia de medidas existentes": "Assess pressures, habitat, and the adequacy of existing measures",
    "Contrastar la delimitación antes de proponer medidas": "Verify the delineation before proposing measures",
    "Mantener en seguimiento y evaluar integración en medidas de gestión": "Maintain monitoring and assess integration into management measures",
    "Conservar como área complementaria de vigilancia": "Retain as a complementary surveillance area",
    "Sin acción prioritaria; conservar como referencia": "No priority action; retain as a reference",
    "Coincidencia de hotspot persistente, elevada riqueza y alta singularidad comunitaria.": "Coincidence of a persistent hotspot, elevated richness, and high community singularity.",
    "Hotspots multiescala y LCBD elevado, indicativos de singularidad espacial robusta.": "Multiscale hotspots and elevated LCBD indicate robust spatial singularity.",
    "Hotspot significativo dependiente de la escala; requiere contraste complementario.": "Significant scale-dependent hotspot; complementary verification is required.",
    "Alta singularidad comunitaria aunque sin persistencia multiescala clara.": "High community singularity without clear multiscale persistence.",
    "Acumulación de criterios espaciales y señal temporal elevada.": "Accumulation of spatial criteria and a strong temporal signal.",
    "Acumulación de criterios de prioridad en celdas contiguas.": "Accumulation of priority criteria in contiguous cells.",
    "Atención preferente y validación detallada": "Preferential attention and detailed validation",
    "Seguimiento reforzado y contraste territorial": "Enhanced monitoring and spatial verification",
    "Interés complementario": "Complementary interest",
    "Validar en campo, revisar presiones y valorar protección o conectividad.": "Validate in the field, review pressures, and assess protection or connectivity.",
    "Asegurar seguimiento específico y comprobar suficiencia de medidas existentes.": "Ensure targeted monitoring and verify the adequacy of existing measures.",
    "Contrastar escenarios y conocimiento experto antes de delimitar medidas.": "Compare scenarios and expert knowledge before delineating measures.",
    "Mantener seguimiento y evaluar medidas de gestión adaptadas.": "Maintain monitoring and assess tailored management measures.",
    "Seguimiento complementario.": "Complementary monitoring.",
    "Revisar si las medidas actuales cubren hábitats, presiones y seguimiento específico de signátidos.": "Review whether current measures cover habitats, pressures, and targeted syngnathid monitoring.",
    "Evaluar el sector no cubierto y revisar conectividad con la figura de protección existente.": "Assess the uncovered sector and review connectivity with the existing protected designation.",
    "Analizar ampliación funcional, medidas de borde o coordinación con la figura protegida existente.": "Assess functional expansion, edge measures, or coordination with the existing protected designation.",
    "Valorar conectividad, ampliación de límites o seguimiento coordinado con el área protegida próxima.": "Assess connectivity, boundary expansion, or coordinated monitoring with the nearby protected area.",
    "Priorizar validación de campo, análisis de presiones y valoración de medidas de gestión o protección.": "Prioritise field validation, pressure analysis, and assessment of management or protection measures.",
    "Incorporar la carpeta de áreas protegidas para evaluar solape, proximidad y gap de conservación.": "Add the protected-areas folder to assess overlap, proximity, and conservation gaps.",
}

PHRASES: tuple[tuple[str, str], ...] = tuple(sorted({
    "Zonas prioritarias de conservación": "Priority conservation areas",
    "Zonas prioritarias": "Priority areas",
    "Zona prioritaria": "Priority area",
    "Áreas protegidas": "Protected areas",
    "Área protegida": "Protected area",
    "Mapa interactivo": "Interactive map",
    "Mapa estático": "Static map",
    "Mapa": "Map", "mapa": "map", "Mapas": "Maps", "mapas": "maps",
    "mapa interactivo": "interactive map",
    "mapa estático": "static map",
    "Análisis temporal avanzado": "Advanced temporal analysis",
    "Análisis temporal": "Temporal analysis",
    "Análisis multiescala": "Multiscale analysis",
    "Análisis descriptivo": "Descriptive analysis",
    "Análisis comunitario": "Community analysis",
    "Diversidad funcional": "Functional diversity",
    "Composición sexual": "Sex composition",
    "Prioridad de conservación": "Conservation priority",
    "prioridad de conservación": "conservation priority",
    "prioridad temporal": "temporal priority",
    "Señal temporal": "Temporal signal",
    "señal temporal": "temporal signal",
    "Cambio espacial": "Spatial change",
    "cambio espacial": "spatial change",
    "Cambio de abundancia": "Abundance change",
    "Abundancia total": "Total abundance",
    "abundancia total": "total abundance",
    "Abundancia": "Abundance", "abundancia": "abundance",
    "Riqueza específica": "Species richness", "riqueza específica": "species richness",
    "Riqueza": "Richness", "riqueza": "richness",
    "Profundidad": "Depth", "profundidad": "depth",
    "Hábitat": "Habitat", "hábitat": "habitat",
    "Especie": "Species", "especie": "species",
    "Especies": "Species", "especies": "species",
    "Región MITECO": "MITECO region", "Región": "Region", "región": "region",
    "Demarcación MITECO": "MITECO subdivision",
    "Demarcaciones MITECO": "MITECO subdivisions",
    "Celdas seleccionadas": "Selected cells", "celdas seleccionadas": "selected cells",
    "Número de celdas": "Number of cells", "Celdas": "Cells", "celdas": "cells",
    "Celda": "Cell", "celda": "cell",
    "Índice medio": "Mean index", "Índice máximo": "Maximum index",
    "Clase de prioridad": "Priority class", "Tipo de prioridad": "Priority type",
    "Acción recomendada": "Recommended action", "acción recomendada": "recommended action",
    "Justificación ecológica": "Ecological justification",
    "Necesidades de validación": "Validation needs",
    "Prioridad de validación": "Validation priority",
    "Gap de conservación": "Conservation gap",
    "Superficie protegida": "Protected area", "Zona protegida": "Area protected",
    "Distancia a protección": "Distance to protection",
    "Evidencia y estabilidad": "Evidence and stability",
    "Indicadores ecológicos": "Ecological indicators",
    "Contexto ambiental y temporal": "Environmental and temporal context",
    "Sensibilidad a la ponderación": "Weighting sensitivity",
    "Justificación científica": "Scientific justification",
    "Resultados y discusión": "Results and discussion",
    "Resultados": "Results", "resultados": "results",
    "Resumen": "Summary", "resumen": "summary",
    "Método": "Method", "método": "method",
    "Año": "Year", "año": "year", "Años": "Years", "años": "years",
    "Fecha": "Date", "Observador": "Observer", "Comentarios": "Comments",
    "Observaciones": "Observations", "observaciones": "observations",
    "Densidad": "Density", "densidad": "density",
    "Registros": "Records", "registros": "records", "Registro": "Record",
    "Opciones": "Options", "Variables": "Variables",
    "Tierra": "Land", "Costa": "Coastline",
    "Línea de costa": "Coastline", "Plano limpio": "Clean map",
    "Especies observadas": "Observed species", "Species observadas": "Observed species",
    "Proyecto": "Project", "Autor": "Author", "Cerrar": "Close",
    "Institución": "Institution", "Periodo": "Period", "Resolución": "Resolution",
    "Área": "Area", "Información": "Information",
    "Abundancia y sexo": "Abundance and sex",
    "hembras": "females", "machos": "males", "indeterminados": "indeterminate individuals",
    "presencia/ausencia": "presence/absence", "Procedencia": "Provenance",
    "enlace externo": "external link", "comentarios originales": "original comments",
    "Coordenadas": "Coordinates", "longitud originales": "original longitude",
    "sistema EPSG de origen": "source EPSG system",
    "Captura incidental": "Bycatch", "Hembras": "Females", "Machos": "Males",
    "Indeterminados": "Indeterminate", "Temperatura": "Temperature",
    "Longitud": "Longitude", "Latitud": "Latitude",
    "Frecuencia": "Frequency", "Ocupación": "Occupancy", "Dominancia": "Dominance",
    "Esfuerzo": "Effort", "Persistencia": "Persistence", "Singularidad": "Singularity",
    "Pérdida": "Loss", "Ganancia": "Gain", "Ausente": "Absent",
    "Alta": "High", "Baja": "Low", "Media": "Medium",
    "Muy alta": "Very high", "Muy baja": "Very low",
    "Todas": "All", "Todos": "All", "Ninguna": "None", "Ninguno": "None",
    "No disponible": "Not available", "Sin datos": "No data",
    "No evaluado": "Not assessed", "No calculado": "Not calculated",
    "Advertencia": "Warning", "ERROR": "ERROR",
}.items(), key=lambda item: len(item[0]), reverse=True))


# ``PHRASES`` was originally applied through one regular-expression pass per
# item. That is correct but needlessly expensive for the large self-contained
# HTML maps, because the whole document is revisited 153 times. The source-token
# ordering is descending by source length. Keeping one combined matcher for
# each exact length preserves that ordering (and the few legitimate cases in
# which a longer replacement enables a shorter phrase), while reducing the
# number of full-document passes from 153 to 25.
def _build_phrase_stages() -> tuple[tuple[re.Pattern[str], dict[str, str]], ...]:
    stages: list[tuple[re.Pattern[str], dict[str, str]]] = []
    for length in sorted({len(source) for source, _ in PHRASES}, reverse=True):
        translations = {
            source: target for source, target in PHRASES if len(source) == length
        }
        matcher = re.compile(
            r"(?<!\w)(?:"
            + "|".join(re.escape(source) for source in translations)
            + r")(?!\w)"
        )
        stages.append((matcher, translations))
    return tuple(stages)


_PHRASE_STAGES = _build_phrase_stages()
_TRANSLATION_CACHE_MAX_CHARS = 16_384


def _translate_text_staged(value: str) -> str:
    for matcher, translations in _PHRASE_STAGES:
        value = matcher.sub(
            lambda match, translations=translations: translations[match.group(0)],
            value,
        )
    return value


@lru_cache(maxsize=65_536)
def _translate_short_text(value: str) -> str:
    """Translate recurring UI/table text without retaining large map HTML."""

    return _translate_text_staged(value)

COLUMN_NAMES: dict[str, str] = {
    "N hembra": "female_count", "N macho": "male_count",
    "N_indeterminado": "indeterminate_count", "Captura incidental": "bycatch",
    "Area_mar_km2": "Marine_area_km2",
    "Area_mar_oficial_km2": "Official_marine_area_km2",
    "Area_mar_gshhs_km2": "GSHHS_marine_area_km2",
    "Area_celda_km2": "Cell_geometry_area_km2",
    "Area_geometria_marina_km2": "Marine_geometry_area_km2",
    "Area_mar_source": "Marine_area_source",
    "Densidad_total": "Density_per_marine_km2",
    "Densidad_ajustada": "Density_per_marine_km2",
    "pct_rel": "relative_abundance_pct",
    "Fecha_aux": "observation_date_parsed", "Region_MITECO": "MITECO_region",
    "Habitat_clean": "habitat_clean", "Depth_aux": "depth_m",
    "Habitat_aux": "habitat", "N_aux": "abundance",
    "clase_batimetrica": "depth_class", "depth_mediana_grid": "cell_median_depth_m",
    "habitat_dominante_grid": "cell_dominant_habitat",
    "cell_justification": "cell_justification", "zone_justification": "zone_justification",
    "management_interpretation": "management_interpretation",
    "zone_management_action": "zone_management_action",
    "validation_need": "validation_need", "validation_needs": "validation_needs",
    "estado_asignacion": "assignment_status",
    "metodo_asignacion": "assignment_method",
    "longitud_wgs84": "longitude_wgs84",
    "latitud_wgs84": "latitude_wgs84",
    "celda_miteco_original": "original_MITECO_cell",
    "codigo_celda_original": "original_cell_code",
    "area_mar_original_km2": "original_marine_area_km2",
    "area_mar_oficial_original_km2": "original_official_marine_area_km2",
    "area_mar_gshhs_original_km2": "original_GSHHS_marine_area_km2",
    "area_celda_original_km2": "original_cell_geometry_area_km2",
    "fuente_area_original": "original_marine_area_source",
    "region_slug_celda_original": "original_cell_region_slug",
    "region_miteco_celda_original": "original_cell_MITECO_region",
    "punto_sobre_tierra_gshhs": "point_on_GSHHS_land",
    "celda_asignada": "assigned_cell",
    "codigo_celda_asignada": "assigned_cell_code",
    "area_mar_celda_asignada_km2": "assigned_cell_marine_area_km2",
    "distancia_asignacion_m": "assignment_distance_m",
    "celda_marina_valida_mas_proxima": "nearest_valid_marine_cell",
    "codigo_celda_marina_mas_proxima": "nearest_valid_marine_cell_code",
    "area_mar_celda_mas_proxima_km2": "nearest_valid_cell_marine_area_km2",
    "distancia_celda_marina_mas_proxima_m": "nearest_valid_marine_cell_distance_m",
    "tolerancia_m": "tolerance_m",
    "celda_marina_mas_proxima_dentro_tolerancia": "nearest_valid_marine_cell_within_tolerance",
    "causa_diagnostica": "diagnostic_cause",
    "n_observaciones": "n_observations",
}

# Habitat values are deliberately kept out of ``EXACT`` and ``PHRASES``.
# Those dictionaries are used for general labels and free text; translating a
# value such as ``Arena`` there would also mutate source-like metadata that is
# not a habitat field.  The field-aware export layer below is the only place
# where these six source categories are translated.
HABITAT_VALUES: dict[str, str] = {
    "Arena": "Sand",
    "Pradera marina": "Seagrass/Macroalgae",
    "Rocas": "Rock",
    "No determinado": "Undetermined",
    "Antrópico": "Anthropogenic",
    "Pelágico": "Pelagic",
}


def _normalised_token(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def is_habitat_field(value: object) -> bool:
    """Return whether a source or exported field stores habitat categories."""

    token = _normalised_token(value)
    return "habitat" in token


_PRESERVED_TEXT_FIELDS = frozenset(
    {
        # Taxones y nombres oficiales.
        "species", "speciesclean", "species1", "species2", "speciesdom",
        "speciesname", "dominant", "dominantspecies", "celldominantspecies",
        "especie", "especielimpia", "especie1", "especie2", "especiedom",
        "especienombre", "especiedominante", "especiedominantecelda",
        "taxon", "taxa", "taxonname", "includedspecies", "specieslist",
        "protectedname", "protectedtype", "protectedlevel", "protectedsource",
        "nombreprotegido", "tipoproteccion", "nivelproteccion", "fuenteproteccion",
        # Trazabilidad, identificadores y enlaces.
        "observer", "observers", "observador", "observadores",
        "comments", "comment", "comentarios", "comentario",
        "linkobservation", "linkobservacion", "url", "enlace",
        "officialcellcode", "codigoceldaoficial", "gridid", "idcelda",
        "zoneid", "idzona", "obsid", "idobservacion", "id", "sourceid",
        "samplingeventid", "projectid", "executionid",
        "sourcerow", "filaorigen", "epsg", "popup", "sourcefile", "filename",
    }
)


def is_preserved_text_field(value: object) -> bool:
    """Indica si los valores de un campo deben permanecer fieles al origen."""

    return _normalised_token(value) in _PRESERVED_TEXT_FIELDS


def translate_habitat_value(value: Any) -> Any:
    """Translate habitat categories for presentation/export only."""

    if value is None or not isinstance(value, str):
        return value
    rendered = value.strip()
    if not rendered:
        return value
    for source, target in sorted(HABITAT_VALUES.items(), key=lambda item: len(item[0]), reverse=True):
        rendered = re.sub(
            rf"(?<!\w){re.escape(source)}(?!\w)",
            target,
            rendered,
            flags=re.IGNORECASE,
        )
    return rendered

PATH_TOKENS: tuple[tuple[str, str], ...] = tuple(sorted({
    "Mapa": "Map", "Mapas": "Maps", "Tabla": "Table", "Tablas": "Tables",
    "Figura": "Figure", "Figuras": "Figures", "Resumen": "Summary",
    "Informe": "Report", "Documento": "Document", "Nota_Metodologica": "Methodological_Note",
    "Analisis": "Analysis", "Descriptivo": "Descriptive", "Descriptiva": "Descriptive",
    "Comunidad": "Community", "Comunidades": "Communities",
    "Conservacion": "Conservation", "Zonas_Prioritarias": "Priority_Areas",
    "Prioridad": "Priority", "Priorizacion": "Prioritisation", "Celdas": "Cells", "Celda": "Cell",
    "Especies": "Species", "Especie": "Species", "Riqueza": "Richness",
    "Abundancia": "Abundance", "Profundidad": "Depth", "Habitat": "Habitat",
    "Temporal": "Temporal", "Cambio": "Change", "Cambios": "Changes", "Avanzado": "Advanced",
    "Resultados": "Results", "Salida": "Output", "Salidas": "Outputs",
    "Control": "Check", "Integridad": "Integrity", "Sensibilidad": "Sensitivity",
    "Robustez": "Robustness", "Gestion": "Management", "Seleccionadas": "Selected",
    "Seleccionados": "Selected", "Resumen": "Summary", "Informe": "Report",
    "Metodologica": "Methodological", "Narrativa": "Narrative", "Discusion": "Discussion",
    "Rasgos": "Traits", "Utilizados": "Used", "Diversidad": "Diversity", "Funcional": "Functional",
    "Composicion": "Composition", "Sexual": "Sex", "Estadistico": "Statistical",
    "Autocorrelacion": "Autocorrelation", "Altos": "High", "Significativos": "Significant",
    "Cobertura": "Coverage", "sin": "without", "salidas": "outputs", "completo": "complete",
    "Completo": "Complete", "Original": "Original", "Antes": "Before", "Historico": "Historical",
    "Pies": "Captions", "Cartografia": "Cartography", "Region": "Region",
    "Global": "Global", "Esfuerzo": "Effort", "Ocupacion": "Occupancy",
    "Frecuencia": "Frequency", "Tendencia": "Trend", "Batimetrica": "Bathymetric",
    "Clases": "Classes", "Distribucion": "Distribution", "Matriz": "Matrix",
    "Trazabilidad": "Traceability", "Cuadricula": "Grid", "Cuadriculas": "Grids",
    "Correlacion": "Correlation", "Correlaciones": "Correlations", "Candidatas": "Candidate",
    "Proteccion": "Protection", "Indicadoras": "Indicator", "Significativas": "Significant",
    "Regional": "Regional", "Regionales": "Regional", "Biogeograficos": "Biogeographic",
    "Biogeografica": "Biogeographic", "Dominante": "Dominant", "Tamano": "Size",
    "Diagnostico": "Diagnostics", "Ampliado": "Expanded", "Ampliada": "Expanded",
    "Sesgo": "Bias", "Observaciones": "Observations", "Mediana": "Median",
    "Limpio": "Cleaned", "Completitud": "Completeness", "Especializacion": "Specialisation",
    "Periodos": "Periods", "Periodo": "Period", "Definidos": "Defined", "Anual": "Annual",
    "Anuales": "Annual", "Modelos": "Models", "Por": "By", "por": "by",
    "Contrastes": "Contrasts", "Entre": "Between", "Indices": "Indices",
    "Espaciales": "Spatial", "Base": "Base", "Predicciones": "Predictions",
    "Interpretacion": "Interpretation", "Temporales": "Temporal", "Derivadas": "Derivatives",
    "Tramos": "Segments", "Puntos": "Points", "Fases": "Phases",
    "Complejidad": "Complexity", "Magnitud": "Magnitude", "Inestabilidad": "Instability",
    "Sintesis": "Synthesis", "Final": "Final", "CORREGIDA": "CORRECTED",
    "Automatica": "Automatic", "Conjunto": "Overall", "Texto": "Text", "Listo": "Ready",
    "Manuscrito": "Manuscript", "Detallado": "Detailed", "Poco": "Low",
    "Informativos": "Information", "Bloques": "Blocks", "Carpetas": "Folders",
    "Recomendacion": "Recommendation", "Indice": "Index", "Simplificado": "Simplified",
    "DeltaAbund": "Abundance_Delta", "Status": "Status", "Malla": "Grid",
    "Maestra": "Master", "Persistencia": "Persistence", "Parametros": "Parameters",
    "Nucleos": "Cores", "Todos": "All", "Ganancia": "Gain", "Perdida": "Loss",
    "Estabilidad": "Stability", "Clasificados": "Classified", "Umbral": "Threshold",
    "Similitud": "Similarity", "Contingencia": "Contingency", "Absoluta": "Absolute",
    "Larga": "Long", "Principal": "Main", "Aristas": "Edges", "Red": "Network",
    "Nodos": "Nodes", "Transicion": "Transition", "Vulnerabilidad": "Vulnerability",
    "Endemismo": "Endemism", "Coocurrencia": "Cooccurrence", "Ordenacion": "Ordination",
    "Rareza": "Rarity", "Singularidad": "Singularity", "Estado": "Status",
    "ChiCuadrado": "Chi_Square", "Anio": "Year", "Litoral": "Coastal",
    "residuos": "residuals", "estandarizados": "standardised", "De": "Of", "de": "of",
    "y": "and",
    "Zonas": "Areas", "Comunitario": "Community", "Multiescala": "Multiscale",
    "Media": "Mean", "Clave": "Key", "BetaDiversidad": "Beta_Diversity",
    "Comparacion": "Comparison", "Originales": "Original",
    "Porcentual": "Percentage", "Porcentaje": "Percentage",
    "Concordancia": "Concordance", "Contexto": "Context",
    "Escenarios": "Scenarios", "Senal": "Signal", "Calidad": "Quality",
    "Alta": "High", "Baja": "Low", "Muy": "Very",
    "Hembras": "Females", "Machos": "Males",
    "Indeterminados": "Indeterminate", "Sexados": "Sexed",
    "Distancia": "Distance", "Costa": "Coast", "Nombre": "Name",
    "Fuente": "Source", "Lista": "List", "Solape": "Overlap",
    "Batimetricas": "Bathymetric",
    "Biogeografico": "Biogeographic", "Distancias": "Distances",
    "Centroide": "Centroid", "Pares": "Pairs", "Modelo": "Model",
    "PropFila": "Row_Proportion", "PropColumna": "Column_Proportion",
    "Tipo": "Type", "Tendencias": "Trends", "Costera": "Coastal",
    "Denominador": "Denominator", "Batimetria": "Bathymetry",
    "ClassBatimetrica": "Bathymetric_Class", "Corregidos": "Corrected",
    "Bloque20": "Block20", "Cartograficas": "Cartographic", "Escala": "Scale",
    "escala": "scale", "celdas": "cells", "celda": "cell", "Sexo": "Sex",
    "especie": "species", "region": "region", "global": "global",
    "litoral": "coastal", "total": "total", "Regiones": "Regions",
    "Completa": "Complete", "periodos": "periods",
    "Informacion_Completa": "Complete_Information", "Interactivo": "Interactive",
    "sexo": "sex", "Composicion_Sexual": "Sex_Composition",
    "descriptivo_habitat_depth": "descriptive_habitat_depth",
    "comunidad_biogeografia": "community_biogeography", "diversidad_funcional": "functional_diversity", "multiescala": "multiscale",
    "temporal": "temporal", "modelos": "models", "mapas": "maps",
    "figuras": "figures", "tablas": "tables", "notas": "notes",
    "zonas_prioritarias_conservacion": "Priority_Conservation_Areas",
}.items(), key=lambda item: len(item[0]), reverse=True))

IDENTIFIER_TOKENS: dict[str, str] = {
    source.casefold(): target for source, target in PATH_TOKENS
}


def translate_text(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    if value in EXACT:
        return EXACT[value]
    if len(value) <= _TRANSLATION_CACHE_MAX_CHARS:
        return _translate_short_text(value)
    return _translate_text_staged(value)


_JSON_REFERENCE_FIELDS = frozenset({
    "file", "files", "path", "paths", "directory", "directories",
    "folder", "folders", "qa", "manifest", "manifests",
    "regionassignmentqualitycontrol", "regionaldataqualitycontrol",
    "runtimewarningcontrol", "duplicateoutputcontrol",
})


def _is_json_reference(value: str, field_name: object) -> bool:
    """Recognise recorded references without normalising or resolving them."""

    token = _normalised_token(field_name)
    if token in _JSON_REFERENCE_FIELDS or token.endswith(
        ("path", "paths", "file", "files", "filename", "directory", "directories")
    ):
        return True
    # Absolute Windows, UNC and POSIX paths; explicitly relative paths; URLs.
    if re.match(r"^(?:[A-Za-z]:[\\/]|[\\/]|\.{1,2}[\\/]|[A-Za-z][A-Za-z0-9+.-]*://)", value):
        return True
    # Relative file references may occur under generic keys such as 'source'.
    # A separator alone is insufficient: habitat labels also contain slashes.
    return bool(re.search(r"[\\/][^\\/]+\.[A-Za-z0-9]{1,12}(?:[?#].*)?$", value))


def translate_json_presentation(value: Any, field_name: object | None = None) -> Any:
    """Translate JSON labels while preserving recorded paths and source metadata.

    Paths describe existing files. Filename translation for newly generated
    products remains the separate responsibility of translate_path.
    """

    if isinstance(value, str):
        if is_preserved_text_field(field_name) or _is_json_reference(value, field_name):
            return value
        return translate_habitat_value(value) if is_habitat_field(field_name) else translate_text(value)
    if isinstance(value, dict):
        return {key: translate_json_presentation(item, key) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [translate_json_presentation(item, field_name) for item in value]
    return value


def translate_identifier(value: str) -> str:
    """Translate underscore-delimited labels used in exported tables."""
    translated: list[str] = []
    for part in value.split("_"):
        target = IDENTIFIER_TOKENS.get(part.casefold(), part)
        if part.islower():
            target = target.lower()
        translated.append(target)
    return "_".join(translated)


def translate_column_name(value: str) -> str:
    if value in COLUMN_NAMES:
        return COLUMN_NAMES[value]
    if "_" in value:
        return translate_identifier(value)
    target = IDENTIFIER_TOKENS.get(value.casefold(), translate_text(value))
    return target.lower() if value.islower() else target


def translate_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    source_columns = list(result.columns)
    renamed_columns = {
        column: translate_column_name(str(column)) for column in source_columns
    }
    habitat_columns = {
        renamed_columns[column]
        for column in source_columns
        if is_habitat_field(column) or is_habitat_field(renamed_columns[column])
    }
    preserved_columns = {renamed_columns[column] for column in source_columns
                         if is_preserved_text_field(column) or is_preserved_text_field(renamed_columns[column])}
    result = result.rename(columns=renamed_columns)
    # Presentation/export rule: ecological density values are written with at most
    # two decimals. Internal analytical frames keep full precision; this function
    # is used only at the presentation/export boundary.
    for _column in result.columns:
        _token = str(_column).casefold()
        if ("density" in _token or "densidad" in _token) and pd.api.types.is_numeric_dtype(result[_column]):
            result[_column] = pd.to_numeric(result[_column], errors="coerce").round(2)
    for column in result.select_dtypes(include=["object", "string", "category"]).columns:
        if column in preserved_columns and column not in habitat_columns:
            continue
        mapper = translate_habitat_value if column in habitat_columns else translate_text
        result[column] = result[column].map(mapper).astype(object)
    return result


def translate_geodataframe(frame: Any) -> Any:
    """Translate attributes while preserving a GeoDataFrame geometry and CRS."""
    import geopandas as gpd

    geometry_name = frame.geometry.name
    attributes = translate_frame(pd.DataFrame(frame.drop(columns=geometry_name)))
    attributes["geometry"] = frame.geometry.to_numpy()
    return gpd.GeoDataFrame(attributes, geometry="geometry", crs=frame.crs)


def translate_path(path: Path) -> Path:
    """Translate only the final filename and preserve its absolute parent.

    Reconstructing every component of an absolute Windows path can break later
    containment checks. Output directories are created with English names at
    source; this helper therefore translates only the final generated name.
    """
    path = Path(path)
    translated = path.name
    for source, target in PATH_TOKENS:
        translated = re.sub(
            rf"(?<![A-Za-z]){re.escape(source)}(?![A-Za-z])",
            target,
            translated,
            flags=re.IGNORECASE,
        )
    return path.with_name(translated)
