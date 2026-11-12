"""Capa de presentación española de la edición completa de Hippo-DEC.

El libro de entrada se conserva sin cambios. La traducción se aplica solamente
a los textos visibles y a los productos exportados.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


EXACT: dict[str, str] = {
    "Baja": "Low", "Media": "Medium", "Alta": "High", "Muy alta": "Very high",
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
}

# Habitat values are deliberately kept out of ``EXACT`` and ``PHRASES``.
# Those dictionaries are used for general labels and free text; translating a
# un valor como ``Arena`` también modificaría metadatos parecidos al origen
# que no son campos de hábitat. La capa de exportación consciente del campo es
# el único lugar donde se traducen estas seis categorías.
HABITAT_VALUES: dict[str, str] = {
    "Sand": "Arena",
    "Seagrass/Macroalgae": "Pradera marina",
    "Rock": "Rocas",
    "Undetermined": "No determinado",
    "Anthropogenic": "Antrópico",
    "Pelagic": "Pelágico",
}


# La edición inglesa de referencia se construyó sobre un núcleo analítico
# español y una capa de presentación inglesa. La edición española utiliza el
# mismo núcleo en sentido inverso: las etiquetas inglesas de la referencia se
# muestran en español y las que ya están en español pasan sin cambios. Esta
# conversión evita tocar claves científicas, sinónimos de origen, fórmulas, semillas,
# permutaciones e identificadores espaciales.
_ENGLISH_EXACT: dict[str, str] = {
    target: source for source, target in EXACT.items()
}
_ENGLISH_EXACT.update(
    {
        "No data": "Sin datos",
        "No region": "Sin región",
        "Canary Islands": "Islas Canarias",
        "North-western Cantabrian subregion": "Subregión Cantábrica Noroccidental",
        "South Atlantic subregion": "Subregión Sudatlántica",
        "Levantine-Balear subregion": "Subregión Levantino-Balear",
        "Strait of Gibraltar and Alboran Sea": "Estrecho de Gibraltar y Mar de Alborán",
        "All MITECO marine subdivisions": "Todas las demarcaciones marinas (MITECO)",
        "No protection information": "Sin información de protección",
        "No protected-area layer": "Sin capa de áreas protegidas",
        "Not calculated": "No calculado",
        "Not assessed": "No evaluado",
        "Not available": "No disponible",
        "Not prioritised": "No prioritaria",
        "Unclassified": "No clasificado",
        "Very high": "Muy alta",
        "Medium-high": "Media-alta",
        "High": "Alta",
        "Medium": "Media",
        "Low": "Baja",
        "Very low": "Muy baja",
        "Presence": "Presencia",
        "Absence": "Ausencia",
        "Gain": "Ganancia",
        "Loss": "Pérdida",
        "Persistence": "Persistencia",
        "Absent": "Ausente",
        "Increase": "Aumento",
        "Decline": "Descenso",
        "Stable": "Estable",
        "Intermediate": "Intermedia",
        "Linear regression": "Regresión lineal",
        "Chi-square": "Chi-cuadrado",
        "Trend not estimable": "Sin tendencia estimable",
        "Not a hotspot": "No hotspot",
        "No overlap": "Sin solape",
        "Core": "Núcleo",
        "Satellite": "Satélite",
        "High-abundance coldspot": "Coldspot de alta abundancia",
        "Low-diversity coldspot": "Coldspot de baja diversidad",
        "Not a coldspot": "No es un coldspot",
        "calculable": "calculable",
        "not_calculable": "no_calculable",
        "created": "creado",
        "skipped": "omitido",
        "passed": "superado",
        "failed": "fallido",
        "written": "escrito",
        "none_emitted": "ninguna_emitida",
        "captured_and_documented": "capturada_y_documentada",
        "disabled": "desactivado",
        "not_available_optional": "no_disponible_opcional",
        "loaded_empty_bbox": "extensión_vacía_cargada",
        "official_miteco_selected_grid_marine_geometry": "geometría_marina_de_la_malla_MITECO_oficial_seleccionada",
        "point_on_surface_within": "punto_interior_dentro_del_polígono",
        "polygon_intersection_fallback": "intersección_de_polígonos_de_respaldo",
        "GSHHS_difference_marine_geometry": "diferencia_GSHHS_para_geometría_marina",
        "official_grid_unique_ids": "identificadores_únicos_de_la_malla_oficial",
        "official_marine_geometries_valid": "geometrías_marinas_oficiales_válidas",
        "partially_marine_cells_retained": "celdas_parcialmente_marinas_conservadas",
        "official_to_multiscale_crosswalk": "correspondencia_malla_oficial_multiescala",
        "conservation_resolution_km": "resolución_conservación_km",
        "conservation_geometry_source": "fuente_geometría_conservación",
        "official_miteco_conservation_grid": "malla_MITECO_oficial_de_conservación",
        "official_cell_identifiers_unique": "identificadores_únicos_de_celdas_oficiales",
        "priority_marine_geometries_valid": "geometrías_marinas_de_prioridad_válidas",
        "cell_marine_geometry_area_reproducible": "área_reproducible_de_geometría_marina_por_celda",
        "zone_marine_geometry_area_reproducible": "área_reproducible_de_geometría_marina_por_zona",
        "protected_percentage_same_denominator": "porcentaje_protegido_con_el_mismo_denominador",
        "protected_area_not_greater_than_zone": "área_protegida_no_superior_al_área_de_la_zona",
        "official_multiscale_hierarchy": "jerarquía_oficial_multiescala",
        "conservation_geometry": "geometría_de_conservación",
    }
)


_ENGLISH_PHRASES: dict[str, str] = {
    target: source for source, target in PHRASES
}
_ENGLISH_PHRASES.update(
    {
        "Map": "Mapa",
        "Maps": "Mapas",
        "Map 1": "Mapa 1",
        "Map 2": "Mapa 2",
        "Map 3": "Mapa 3",
        "Clean map": "Mapa limpio",
        "Static map": "Mapa estático",
        "Interactive map": "Mapa interactivo",
        "Priority conservation areas": "Zonas prioritarias de conservación",
        "Priority areas": "Zonas prioritarias",
        "Priority area": "Zona prioritaria",
        "Protected areas": "Áreas protegidas",
        "Protected area": "Área protegida",
        "Observed species": "Especies observadas",
        "Filter species": "Filtrar especies",
        "Mapping variable": "Variable cartografiada",
        "Variable options": "Opciones de la variable",
        "Map information": "Información del mapa",
        "Information": "Información",
        "Legend": "Leyenda",
        "Panel": "Panel",
        "Visible panels": "Paneles visibles",
        "Expand panel": "Expandir panel",
        "Minimise panel": "Minimizar panel",
        "Minimize panel": "Minimizar panel",
        "Show, hide or minimise panels": "Mostrar, ocultar o minimizar paneles",
        "Show, hide or minimize panels": "Mostrar, ocultar o minimizar paneles",
        "Minimise": "Minimizar",
        "Minimize": "Minimizar",
        "Show all": "Mostrar todos",
        "All": "Todas",
        "None": "Ninguna",
        "Yes": "Sí",
        "No": "No",
        "N.D.": "N.D.",
        "Record": "Registro",
        "Records": "Registros",
        "Date": "Fecha",
        "Observer": "Observador/a",
        "Observers": "Observadores/as",
        "Comments": "Comentarios",
        "Comment": "Comentario",
        "Link": "Enlace",
        "Open external record": "Abrir registro externo",
        "Provenance": "Procedencia",
        "Original coordinates": "Coordenadas originales",
        "Original latitude": "Latitud original",
        "Original longitude": "Longitud original",
        "Source X / Y": "X / Y de origen",
        "Source EPSG": "EPSG de origen",
        "Source row": "Fila de origen",
        "Source ID (metadata)": "Id de origen (metadato)",
        "Internal observation ID": "Id interno de observación",
        "Coincident observations": "Observaciones coincidentes",
        "Total count": "N total",
        "Abundance": "Abundancia",
        "Total abundance": "Abundancia total",
        "Selected abundance": "Abundancia seleccionada",
        "Density": "Densidad",
        "Total density": "Densidad total",
        "Selected density": "Densidad seleccionada",
        "Richness": "Riqueza",
        "Richness total": "Riqueza total",
        "Species richness": "Riqueza específica",
        "Species": "Especie",
        "Species composition": "Composición de especies",
        "Species present in the cell": "Especies presentes en la celda",
        "Species active in the viewer": "Especies activas en el visor",
        "Environment": "Ambiente",
        "Environment and capture": "Ambiente y captura",
        "Temperature": "Temperatura",
        "Depth": "Profundidad",
        "Depth records": "Registros con profundidad",
        "Habitat": "Hábitat",
        "Dominant habitat": "Hábitat dominante",
        "Reported habitat": "Hábitat registrado",
        "Bycatch": "Captura incidental",
        "Females": "Hembras",
        "Males": "Machos",
        "Indeterminate": "Indeterminados",
        "Indeterminate individuals": "Individuos indeterminados",
        "Presence / absence": "Presencia / ausencia",
        "Abundance and sex": "Abundancia y sexo",
        "Abundance and sex composition": "Abundancia y composición sexual",
        "Sex composition": "Composición sexual",
        "Sexed individuals": "Individuos sexados",
        "Female:male ratio": "Proporción hembras:machos",
        "Female proportion": "Proporción de hembras",
        "Sex bias": "Sesgo sexual",
        "Minimum sexed individuals": "Mínimo de individuos sexados",
        "Threshold applied": "Umbral aplicado",
        "Official code": "Código oficial",
        "Internal cell ID": "Id interno de celda",
        "MITECO region": "Región MITECO",
        "Official area": "Área oficial",
        "Area": "Área",
        "Selected area": "Área seleccionada",
        "Number of records": "Número de registros",
        "Records / years": "Registros / años",
        "Spatial quality": "Calidad espacial",
        "Dominant species": "Especie dominante",
        "Dominant abundance": "Abundancia dominante",
        "Percentage of abundance": "Porcentaje de la abundancia",
        "Displayed value": "Valor mostrado",
        "Abundance used": "Abundancia utilizada",
        "Area used": "Área utilizada",
        "Current selection": "Selección actual",
        "Complete cell information": "Información completa de la celda",
        "Selection composition": "Composición de la selección",
        "Density recalculated for the active selection": "Densidad recalculada para la selección activa",
        "Each density value is recalculated from abundance and the cell's actual GSHHS-clipped marine area, excluding land, and is expressed per km².": "Cada valor de densidad se recalcula a partir de la abundancia y de la superficie marina real de la celda recortada con GSHHS, excluyendo la tierra, y se expresa por km².",
        "Analytical resolution": "Resolución analítica",
        "Selected variable": "Variable seleccionada",
        "Complete cell": "Celda completa",
        "Composition": "Composición",
        "Variable": "Variable",
        "Variables": "Variables",
        "Mapping variable": "Variable cartografiada",
        "Density total": "Densidad total",
        "Variable by cell": "Variable por celda",
        "Density by cell": "Densidad por celda",
        "Priority by cell": "Prioridad por celda",
        "Overview symbols": "Símbolos de resumen",
        "Priority-area labels": "Etiquetas de zonas prioritarias",
        "Protected areas": "Áreas protegidas",
        "Priority summary": "Resumen de prioridad",
        "Prioritisation result": "Resultado de priorización",
        "Final class": "Clase final",
        "Initial class": "Clase inicial",
        "Priority index": "Índice de prioridad",
        "Priority type": "Tipo de prioridad",
        "Strong ecological criterion": "Criterio ecológico sólido",
        "Evidence confidence": "Confianza de la evidencia",
        "Information sufficiency": "Suficiencia de información",
        "Stability across scenarios": "Estabilidad entre escenarios",
        "Fine-scale LCBD p-value": "Valor p de LCBD a escala fina",
        "Significant LCBD": "LCBD significativo",
        "Hotspot type": "Tipo de hotspot",
        "Hotspot at any scale": "Hotspot en alguna escala",
        "Multiscale hotspot": "Hotspot multiescala",
        "Persistent across all scales": "Persistente en todas las escalas",
        "Hotspot LCBD": "LCBD del hotspot",
        "Hotspot cluster": "Clúster del hotspot",
        "Median depth": "Profundidad mediana",
        "Temporal signal": "Señal temporal",
        "Temporal index": "Índice temporal",
        "Temporal records": "Registros temporales",
        "Balanced scenario": "Escenario equilibrado",
        "Ecological scenario": "Escenario ecológico",
        "Monitoring scenario": "Escenario de seguimiento",
        "Strong / total evidence": "Evidencia sólida / total",
        "Area class": "Clase del área",
        "Mean index": "Índice medio",
        "Maximum index": "Índice máximo",
        "Number of cells": "Número de celdas",
        "Very-high / high cells": "Celdas de prioridad muy alta / alta",
        "Estimated area": "Área estimada",
        "Dominant MITECO subdivision": "Demarcación MITECO dominante",
        "MITECO subdivisions": "Demarcaciones MITECO",
        "Mean / maximum richness": "Riqueza media / máxima",
        "Mean / maximum LCBD": "LCBD medio / máximo",
        "Hotspots at any scale": "Hotspots en alguna escala",
        "Multiscale hotspots": "Hotspots multiescala",
        "Persistent across all scales": "Hotspots persistentes en todas las escalas",
        "Mean confidence": "Confianza media",
        "Mean data support": "Soporte medio de datos",
        "Cells stable under 3 scenarios": "Celdas estables en 3 escenarios",
        "Cells stable under ≥2 scenarios": "Celdas estables en ≥2 escenarios",
        "Validation priority": "Prioridad de validación",
        "Gap status": "Estado de la brecha",
        "Protected surface area": "Superficie protegida",
        "Area protected": "Área protegida",
        "Distance to protection": "Distancia a la protección",
        "Overlapping protected areas": "Áreas protegidas solapadas",
        "Protection designations": "Figuras de protección",
        "Protection levels": "Niveles de protección",
        "Sources": "Fuentes",
        "Related protected areas": "Áreas protegidas relacionadas",
        "Ecological indicators": "Indicadores ecológicos",
        "Ecological indicators and hotspots": "Indicadores ecológicos y hotspots",
        "Environmental and temporal context": "Contexto ambiental y temporal",
        "Weighting sensitivity": "Sensibilidad a la ponderación",
        "Scientific justification": "Justificación científica",
        "Ecological justification": "Justificación ecológica",
        "Management interpretation": "Interpretación de gestión",
        "Recommended action": "Acción recomendada",
        "Validation needs": "Necesidades de validación",
        "Included cells": "Celdas incluidas",
        "Field": "Campo",
        "Meaning": "Significado",
        "Dataset": "Conjunto de datos",
        "Step": "Paso",
        "Description": "Descripción",
        "Methodology": "Metodología",
        "Results": "Resultados",
        "Results and discussion": "Resultados y discusión",
        "Method and interpretation": "Método e interpretación",
        "Run scope": "Ámbito de la ejecución",
        "Complete information appendix": "Apéndice de información completa",
        "How to use this workbook": "Cómo utilizar este libro",
        "No records were available for this dataset.": "No había registros disponibles para este conjunto de datos.",
        "No data": "Sin datos",
        "Not calculable": "No calculable",
        "Not calculable": "No calculable",
        "No functional diversity": "Sin diversidad funcional",
        "Functional diversity": "Diversidad funcional",
        "Functional traits": "Rasgos funcionales",
        "Taxonomic richness": "Riqueza taxonómica",
        "Functional richness": "Riqueza funcional",
        "Standardised value/index": "Valor/índice estandarizado",
        "MITECO region": "Región MITECO",
        "Number of records": "Número de registros",
        "Temporal observation effort": "Esfuerzo de observación temporal",
        "Observed richness": "Riqueza observada",
        "Species richness by MITECO subdivision": "Riqueza específica por demarcación MITECO",
        "Occupancy (% of sampled cells)": "Ocupación (% de celdas muestreadas)",
        "Overall spatial occupancy": "Ocupación espacial global",
        "Regional %": "% regional",
        "Relative dominance by region": "Dominancia relativa por región",
        "Bathymetric distribution by species": "Distribución batimétrica por especie",
        "% of species records": "% de los registros de la especie",
        "Relative species × habitat frequency": "Frecuencia relativa especie × hábitat",
        "Overall distribution of observed depth": "Distribución global de la profundidad observada",
        "Density of observed depth": "Densidad de la profundidad observada",
        "Frequency by depth class": "Frecuencia por clase batimétrica",
        "Annual trend in observed depth": "Tendencia anual de la profundidad observada",
        "Observed depth and abundance": "Profundidad observada y abundancia",
        "Frequency of observed habitats": "Frecuencia de los hábitats observados",
        "Depth by habitat": "Profundidad por hábitat",
        "Depth and habitat by species": "Profundidad y hábitat por especie",
        "Rank-abundance curve": "Curva rango-abundancia",
        "Total abundance (log)": "Abundancia total (log)",
        "Local community singularity (LCBD)": "Singularidad comunitaria local (LCBD)",
        "LCBD map by cell": "Mapa de LCBD por celda",
        "Biogeographical community clusters": "Clústeres comunitarios biogeográficos",
        "Biogeographical-cluster map": "Mapa de clústeres biogeográficos",
        "Indicator species by region": "Especies indicadoras por región",
        "Integrated singularity: LCBD and rarity": "Singularidad integrada: LCBD y rareza",
        "Mean rarity": "Rareza media",
        "Relationship between LCBD and mean rarity": "Relación entre LCBD y rareza media",
        "Mean abundance in occupied cells (log)": "Abundancia media en celdas ocupadas (log)",
        "Occupancy–abundance relationship": "Relación ocupación–abundancia",
        "Proportion of occupied cells": "Proporción de celdas ocupadas",
        "Core, intermediate, and satellite classification": "Clasificación núcleo, intermedia y satélite",
        "Latitudinal richness gradient": "Gradiente latitudinal de riqueza",
        "Richness per cell": "Riqueza por celda",
        "Clustering sensitivity to the network threshold": "Sensibilidad del agrupamiento al umbral de la red",
        "Sensitivity of clusters and modularity to the threshold": "Sensibilidad de los clústeres y la modularidad al umbral",
        "Species composition by biogeographical cluster": "Composición de especies por clúster biogeográfico",
        "Percentage composition by biogeographical cluster": "Composición porcentual por clúster biogeográfico",
        "Multiscale hotspot persistence": "Persistencia de hotspots multiescala",
        "Persistence (number of scales)": "Persistencia (número de escalas)",
        "Mean richness by spatial scale": "Riqueza media por escala espacial",
        "Mean richness per cell": "Riqueza media por celda",
        "Scale (km)": "Escala (km)",
        "High and significant hotspots by scale": "Hotspots altos y significativos por escala",
        "Number of hotspots": "Número de hotspots",
        "Multiscale-persistence map": "Mapa de persistencia multiescala",
        "Moran I": "I de Moran",
        "Persistence autocorrelation: Monte Carlo distribution": "Autocorrelación de la persistencia: distribución de Monte Carlo",
        "Effort-corrected annual abundance": "Abundancia anual corregida por esfuerzo",
        "Individuals per 100 total records": "Individuos por cada 100 registros totales",
        "Abundance change (%)": "Cambio de abundancia (%)",
        "Abundance change between periods": "Cambio de abundancia entre periodos",
        "Temporal-priority ranking": "Clasificación de prioridad temporal",
        "Score (0–100)": "Puntuación (0–100)",
        "Aggregated spatial abundance change": "Cambio espacial agregado de abundancia",
        "Aggregated temporal-abundance-change map": "Mapa agregado del cambio temporal de abundancia",
        "Status": "Estado",
        "Gain = absence in the first period and presence in the second; loss = the reverse pattern; persistence = presence in both periods.": "Ganancia = ausencia en el primer periodo y presencia en el segundo; pérdida = el patrón inverso; persistencia = presencia en ambos periodos.",
        "No duplicates found": "No se encontraron duplicados",
        "Every registered output has a unique content signature.": "Cada salida registrada tiene una firma de contenido única.",
        "Quality control": "Control de calidad",
        "Integrity check": "Control de integridad",
        "PASS": "SUPERADO",
        "FAIL": "FALLIDO",
        "Environment OK": "Entorno correcto",
        "Run completed successfully.": "La ejecución ha finalizado correctamente.",
        "Run cancelled by the user.": "La ejecución ha sido cancelada por el usuario.",
        "The map displays syngnathid abundance and relative density by MITECO marine grid cell.": "El mapa muestra la abundancia de signátidos y la densidad relativa por celda de la malla marina MITECO.",
        "Complete advanced temporal-analysis workbook": "Libro completo del análisis temporal avanzado",
        "Complete descriptive, habitat, and depth analysis workbook": "Libro completo del análisis descriptivo, de hábitat y de profundidad",
        "Complete community, LCBD, and biogeography analysis workbook": "Libro completo del análisis comunitario, LCBD y biogeografía",
        "Field group": "Grupo de campos",
        "complete records": "registros completos",
        "The map": "El mapa",
        "This map": "Este mapa",
        "No selected species is present in this cell.": "No hay ninguna especie seleccionada presente en esta celda.",
        "No sex information is available": "No hay información sexual disponible",
        "The taxonomic list is unavailable in this viewer.": "La lista taxonómica no está disponible en este visor.",
        "Viewer initialisation failed": "Ha fallado la inicialización del visor",
        "convex hull": "envolvente convexa",
        "two-point segment": "segmento de dos puntos",
        "No external coastline supplied; official MITECO marine cells retained.": "No se ha suministrado litoral externo; se conservan las celdas marinas oficiales MITECO.",
        "GSHHG returned no coastline geometry for the study extent.": "GSHHG no devolvió geometría de litoral para la extensión del estudio.",
        "Distance from cell centroid to GSHHG coastline boundary.": "Distancia desde el centroide de la celda al límite de litoral GSHHG.",
        "incomplete PDF header or trailer": "cabecera o final PDF incompletos",
    }
)


_ENGLISH_WORDS: dict[str, str] = {
    "analysis": "análisis", "analyses": "análisis", "analytical": "analítico",
    "annual": "anual", "annual": "anual", "area": "área", "areas": "áreas",
    "available": "disponible", "abundance": "abundancia", "bias": "sesgo",
    "by": "por", "cell": "celda", "cells": "celdas", "change": "cambio",
    "class": "clase", "classes": "clases", "coastal": "costero", "coastline": "línea de costa",
    "community": "comunidad", "composition": "composición", "complete": "completo",
    "confidence": "confianza", "conservation": "conservación", "control": "control",
    "corrected": "corregido", "coverage": "cobertura", "current": "actual",
    "data": "datos", "date": "fecha", "density": "densidad", "depth": "profundidad",
    "dominance": "dominancia", "dominant": "dominante", "effort": "esfuerzo",
    "environment": "ambiente", "evidence": "evidencia", "female": "hembra", "females": "hembras",
    "field": "campo", "figure": "figura", "figures": "figuras", "filter": "filtro",
    "global": "global", "habitat": "hábitat", "high": "alta", "hotspot": "hotspot",
    "information": "información", "indicator": "indicador", "individuals": "individuos",
    "initial": "inicial", "integrated": "integrado", "local": "local", "low": "baja",
    "maximum": "máximo", "mean": "media", "median": "mediana", "method": "método",
    "minimum": "mínimo", "multiscale": "multiescala", "number": "número", "observed": "observado",
    "observations": "observaciones", "occupancy": "ocupación", "optional": "opcional",
    "original": "original", "period": "periodo", "periods": "periodos", "priority": "prioridad",
    "protected": "protegido", "quality": "calidad", "records": "registros", "region": "región",
    "relative": "relativa", "resolution": "resolución", "results": "resultados", "richness": "riqueza",
    "scale": "escala", "selected": "seleccionado", "selection": "selección", "sex": "sexo",
    "significant": "significativo", "singularity": "singularidad", "species": "especies",
    "spatial": "espacial", "status": "estado", "summary": "resumen", "temporal": "temporal",
    "total": "total", "trend": "tendencia", "variable": "variable", "variables": "variables",
    "very": "muy", "weighted": "ponderado", "year": "año", "years": "años",
    # No se traducen los artículos ingleses aislados. Pueden formar parte de
    # nombres científicos o de identificadores de origen (por ejemplo, ``A a``)
    # y una sustitución ciega los corrompería.
    "and": "y", "or": "o", "of": "de", "the": "el",
    "displays": "muestra", "display": "visualización", "displayed": "mostrado",
    "syngnathids": "signátidos", "syngnathid": "signátido", "marine": "marina",
    "grid": "malla", "workbook": "libro", "group": "grupo", "groups": "grupos",
    "official": "oficial", "effective": "efectiva", "terrestrial": "terrestre",
    "land": "tierra", "denominator": "denominador", "recalculated": "recalculada",
    "recalculates": "recalcula", "colour": "color", "colours": "colores",
    "transparent": "transparente", "selector": "selector", "allows": "permite",
    "several": "varias", "current": "actual", "scale": "escala", "scales": "escalas",
    "used": "utilizada", "using": "utilizando", "unit": "unidad", "units": "unidades",
    "individual": "individuo", "individuals": "individuos", "species": "especies",
    "present": "presente", "selected": "seleccionada", "selection": "selección",
    "colour": "color", "colouring": "coloreado", "normalised": "normalizado",
    "normalised": "normalizado", "retained": "conservado", "excluded": "excluida",
    "coastal": "costera", "coast": "costa", "open": "abrir", "opens": "abre",
    "information": "información", "contents": "contenido", "content": "contenido",
    "purpose": "finalidad", "scope": "alcance", "new": "novedades", "what": "qué",
    "application": "aplicación", "program": "programa", "produces": "produce",
    "produced": "producido", "reads": "lee", "read": "leído", "without": "sin",
    "changing": "cambiar", "changed": "cambiado", "headings": "cabeceras",
    "heading": "cabecera", "values": "valores", "value": "valor",
    "recognised": "reconocidos", "recognizes": "reconoce", "converted": "convertidos",
    "inside": "dentro", "interface": "interfaz", "folders": "carpetas", "folder": "carpeta",
    "filenames": "nombres de archivo", "filename": "nombre de archivo", "tables": "tablas",
    "table": "tabla", "reports": "informes", "report": "informe", "labels": "etiquetas",
    "label": "etiqueta", "preserved": "conservado", "scientific": "científicos",
    "names": "nombres", "codes": "códigos", "metadata": "metadatos", "required": "obligatorio",
    "recommended": "recomendado", "place": "coloque", "items": "elementos",
    "anywhere": "en cualquier lugar", "extracted": "extraída", "searches": "busca",
    "subfolders": "subcarpetas", "dates": "fechas", "plus": "más", "companion": "acompañante",
    "layers": "capas", "layer": "capa", "uses": "utiliza", "supply": "suministrado",
    "supplied": "suministrado", "derived": "derivado", "fallback": "alternativa",
    "publish": "publicar", "published": "publicado", "hosting": "alojamiento",
    "static": "estática", "server": "servidor", "servers": "servidores",
    "download": "descarga", "downloads": "descargas", "unlock": "desbloquear",
    "locked": "bloqueado", "unlocked": "desbloqueado", "password": "contraseña",
    "sensitive": "sensible", "protect": "proteger", "directory": "directorio",
    "direct": "directa", "requesting": "solicitar", "only": "solo", "one": "una",
    "single": "único", "four": "cuatro", "three": "tres", "twelve": "doce",
    "each": "cada", "every": "cada", "controls": "controles", "behaviour": "comportamiento",
    "behavior": "comportamiento", "meaning": "significado", "calculation": "cálculo",
    "formula": "fórmula", "example": "ejemplo", "correct": "correcta", "incorrect": "incorrecta",
    "rather": "en lugar", "than": "que", "because": "porque", "where": "donde",
    "when": "cuando", "if": "si", "then": "entonces", "from": "desde", "into": "en",
    "with": "con", "for": "para", "not": "no", "does": "hace", "is": "es", "are": "son",
    "be": "ser", "can": "puede", "may": "puede", "must": "debe", "should": "debería",
    "will": "será", "contains": "contiene", "contain": "contener", "includes": "incluye",
    "include": "incluir", "provides": "proporciona", "provide": "proporcionar",
    "numbers": "números", "distinct": "distintas", "largest": "mayor", "below": "por debajo",
    "above": "por encima", "between": "entre", "both": "ambos", "first": "primer",
    "second": "segundo", "last": "último", "true": "verdadero", "false": "falso",
    "none": "ninguno", "all": "todos", "also": "también", "however": "sin embargo",
    "more": "más", "less": "menos", "significance": "significación", "persistent": "persistente",
    "identified": "identificada", "assigned": "asignada", "excluded": "excluido",
    "removed": "eliminado", "missing": "ausente", "empty": "vacío", "failure": "fallo",
    "error": "error", "warning": "advertencia", "quick": "rápida", "final": "final",
    "internal": "interno", "external": "externo", "full": "completa", "nominal": "nominal",
    "square": "cuadrada", "surface": "superficie", "formulae": "fórmulas",
    "recalculate": "recalcular", "checked": "comprobado", "mismatch": "discordancia",
    "stops": "detiene", "instead": "en lugar", "silently": "silenciosamente",
    "observation": "observación", "taxa": "taxones", "taxon": "taxón", "capture": "captura",
    "incidental": "incidental", "observer": "observador/a", "comment": "comentario",
    "link": "enlace", "row": "fila", "active": "activa", "species-specific": "específica de cada especie",
    "specific": "específico", "ratio": "proporción", "proportion": "proporción", "applied": "aplicado",
    "dataset": "conjunto de datos", "datasets": "conjuntos de datos", "workbook": "libro",
    "sheet": "hoja", "sheets": "hojas", "field": "campo", "fields": "campos",
    "popup": "ventana emergente", "popups": "ventanas emergentes", "viewer": "visor",
    "viewers": "visores", "responsive": "adaptable", "tab": "pestaña", "tabs": "pestañas",
    "button": "botón", "buttons": "botones", "load": "cargar", "loads": "carga",
    "loading": "cargando", "close": "cerrar", "show": "mostrar", "hide": "ocultar",
    "reset": "restablecer", "save": "guardar", "access": "acceso", "installation": "instalación",
    "install": "instalar", "installed": "instalado", "move": "mover", "moving": "traslado",
    "update": "actualizar", "troubleshooting": "solución de problemas", "privacy": "privacidad",
    "licensing": "licencias", "review": "revisión", "institutional": "institucional",
    "upload": "subir", "deployment": "despliegue", "authentication": "autenticación",
    "accessibility": "accesibilidad", "browser": "navegador", "browsers": "navegadores",
    "dependencies": "dependencias", "provider": "proveedor", "providers": "proveedores",
    "background": "fondo", "blank": "en blanco", "offline": "sin conexión", "tile": "tesela",
    "tiles": "teselas", "vector": "vectorial", "vectors": "vectores", "geometry": "geometría",
    "geometries": "geometrías", "recommendation": "recomendación", "recommendations": "recomendaciones",
    "needs": "necesidades", "responsible": "responsable", "decision": "decisión", "support": "apoyo",
    "legal": "legal", "designation": "designación", "designations": "designaciones",
    "automatic": "automática", "expert": "experto", "experts": "expertos", "knowledge": "conocimiento",
    "pressures": "presiones", "existing": "existente", "summaries": "resúmenes",
    "glossary": "glosario", "term": "término", "terms": "términos", "cryptographic": "criptográfica",
    "checksum": "suma de comprobación", "verify": "verificar", "included": "incluido",
    "read-only": "solo lectura", "reproducibility": "reproducibilidad", "reproducible": "reproducible",
    "signature": "firma", "signatures": "firmas", "size": "tamaño", "file": "archivo",
    "files": "archivos", "path": "ruta", "paths": "rutas", "retaining": "conservando",
    "retains": "conserva", "retain": "conservar", "canonical": "canónico", "normalized": "normalizada",
    "permutation": "permutación", "permutations": "permutaciones", "seed": "semilla",
    "seeds": "semillas", "statistical": "estadístico", "statistics": "estadísticos",
    "causality": "causalidad", "population": "población", "priority": "prioridad",
    "priorities": "prioridades", "biogeography": "biogeografía", "biogeographical": "biogeográfica",
    "traits": "rasgos", "trait": "rasgo", "taxonomic": "taxonómica", "sexual": "sexual",
    "multiscale": "multiescala", "scales": "escalas", "ranking": "clasificación", "rank": "rango",
    "aggregated": "agregado", "effort-corrected": "corregida por esfuerzo", "quality-control": "control de calidad",
    "integrity": "integridad", "audit": "auditoría", "audits": "auditorías", "manifest": "manifiesto",
    "manifests": "manifiestos", "duplicate": "duplicado", "duplicates": "duplicados",
    "captured": "capturada", "documented": "documentada", "unresolved": "sin resolver",
    "outside": "fuera", "invalid": "inválidas", "coordinate": "coordenada", "assignment": "asignación",
    "regional": "regional", "regions": "regiones", "inherit": "heredar", "inherited": "heredada",
    "marine-area": "área marina",
}


_ENGLISH_PATH_EXACT: dict[str, str] = {
    "Web_Publication": "Publicacion_Web",
    "Manual_Hispa_Syng_v1_0_EN": "Manual_Hispa_Syng_v1_0_ES",
    "DOWNLOAD_PASSWORD": "CONTRASENA_DESCARGAS",
    "FULL_ANALYSIS_MANUAL": "MANUAL_ANALISIS_COMPLETO",
    "INPUT_AND_CARTOGRAPHY_AUDIT": "AUDITORIA_ENTRADAS_Y_CARTOGRAFIA",
    "R_PYTHON_PARITY": "PARIDAD_R_PYTHON",
    "READ_ME_FIRST": "LEEME_PRIMERO",
    "RELOCATION_AND_EXECUTION": "TRASLADO_Y_EJECUCION",
    "VALIDATION": "VALIDACION",
    "Map1_Complete_Information": "Mapa1_Informacion_Completa",
    "Map2_Complete_Information": "Mapa2_Informacion_Completa",
    "Map3_Complete_Information": "Mapa3_Informacion_Completa",
    "Priority_Conservation_Areas_Complete_Information": "Zonas_Prioritarias_Conservacion_Informacion_Completa",
    "Data_Package": "Paquete_Datos",
    "run": "ejecucion",
    "run_info": "informacion_ejecucion",
    "input_audit": "auditoria_entrada",
    "excel_field_audit": "auditoria_campos_excel",
    "discarded_invalid_coordinates": "coordenadas_invalidas_descartadas",
    "points_outside_grid": "puntos_fuera_malla",
    "region_assignment_quality_control": "control_calidad_asignacion_regional",
    "Table_20_temporal_quality_control": "Tabla_20_Control_Calidad_Temporal",
    "assigned_observations": "observaciones_asignadas",
    "Filtered_Master_Database": "Base_Maestra_Filtrada",
    "cell_metrics": "metricas_celdas",
    "cell_species_metrics": "metricas_celdas_especies",
    "cell_species_sex_metrics": "metricas_celdas_especies_sexo",
    "cell_quality_index": "indice_calidad_celda",
    "occupied_cells": "celdas_ocupadas",
    "complete_analysis_quality_control": "control_calidad_analisis_completo",
    "analysis_output_manifest": "manifiesto_salidas_analisis",
    "regional_data_quality_control": "control_calidad_datos_regionales",
    "runtime_warning_control": "control_advertencias_ejecucion",
    "duplicate_output_control": "control_salidas_duplicadas",
    "qa_summary": "resumen_control_calidad",
    "Community_Biogeography_Analysis": "Analisis_Comunidad_Biogeografia",
    "Cell_Sex_Composition": "Composicion_Sexual_Celdas",
    "Temporal_Cell_Species_Changes": "Cambios_Temporales_Especie_Celda",
    "Multiscale_Hotspot_Master_Grid": "Malla_Maestra_Hotspot_Multiescala",
    "Moran_MC_High_Significant_Hotspot_Autocorrelation_Test": "Prueba_Autocorrelacion_Monte_Carlo_Hotspot_Alto_Significativo",
}


_ENGLISH_COLUMNS: dict[str, str] = {
    target: source for source, target in COLUMN_NAMES.items()
}
_ENGLISH_COLUMNS.update(
    {
        "grid_id": "id_celda",
        "official_cell_code": "codigo_celda_oficial",
        "Region_MITECO": "Region_MITECO",
        "Species": "Especie",
        "Species_clean": "Especie_limpia",
        "Species_1": "Especie_1",
        "Species_2": "Especie_2",
        "female_count": "N_hembra",
        "male_count": "N_macho",
        "indeterminate_count": "N_indeterminado",
        "sexed_count": "N_sexados",
        "bycatch": "Captura_incidental",
        "source_row": "fila_origen",
        "observation_date_parsed": "Fecha_observacion_parseada",
        "depth_m": "profundidad_m",
        "habitat": "Hábitat",
        "habitat_clean": "Habitat_limpio",
        "abundance": "abundancia",
        "abundance_aux": "abundancia_aux",
        "N_sum": "N_suma",
        "n_records": "n_registros",
        "n_years": "n_anios",
        "n_obs": "n_observaciones",
        "occupied_cells": "celdas_ocupadas",
        "sampled_cells": "celdas_muestreadas",
        "occupied_cells": "celdas_ocupadas",
        "richness": "riqueza",
        "relative_abundance_pct": "abundancia_relativa_pct",
        "relative_frequency_pct": "frecuencia_relativa_pct",
        "occupancy_pct": "ocupacion_pct",
        "occupancy_pct_sampled_cells": "ocupacion_pct_celdas_muestreadas",
        "distance_to_coast_m": "distancia_costa_m",
        "calculation_status": "estado_calculo",
        "calculation_note": "nota_calculo",
        "method": "metodo",
        "zone_id": "id_zona",
        "zone_justification": "justificacion_zona",
        "cell_justification": "justificacion_celda",
        "management_interpretation": "interpretacion_gestion",
        "zone_management_action": "accion_gestion_zona",
        "validation_need": "necesidad_validacion",
        "validation_needs": "necesidades_validacion",
        "conservation_gap_status": "estado_brecha_conservacion",
        "protected_area_names": "nombres_areas_protegidas",
        "protected_area_types": "tipos_areas_protegidas",
        "protected_area_levels": "niveles_areas_protegidas",
        "protected_area_sources": "fuentes_areas_protegidas",
        "protected_name": "nombre_protegido",
        "protected_type": "tipo_proteccion",
        "protected_level": "nivel_proteccion",
        "protected_source": "fuente_proteccion",
        "marine_protected_areas": "areas_protegidas_marinas",
        "Marine_area_km2": "Area_marina_km2",
        "Density_per_marine_km2": "Densidad_por_km2_marino",
        "depth_class": "clase_batimetrica",
        "cell_median_depth_m": "profundidad_mediana_celda_m",
        "cell_dominant_habitat": "habitat_dominante_celda",
        "cell_dominant_species": "especie_dominante_celda",
        "area": "area",
        "region": "region",
        "quality": "calidad",
        "dominant": "dominante",
        "dominant_n": "N_dominante",
        "sex_bias": "sesgo_sexual",
        "female_male_ratio": "proporcion_hembras_machos",
        "female_proportion": "proporcion_hembras",
        "Habitat": "Hábitat",
        "Habitat_clean": "Hábitat_limpio",
        "bias_sex": "sesgo_sexual",
        "Observations_outside_marine_grid": "Observaciones_fuera_malla_marina",
        "observations_outside_marine_grid": "observaciones_fuera_malla_marina",
        "Observations_outside_marine_gri": "Observaciones_fuera_malla_marina",
        "observations_outside_marine_gri": "observaciones_fuera_malla_marina",
        "n_scenarios_priority_high": "n_escenarios_prioridad_alta",
        "synthetic_master_id": "id_malla_maestra_sintetica",
        "selected_grid_km": "resolucion_seleccionada_km",
        "conservation_grid_source": "fuente_malla_conservacion",
        "marine_geometry_method": "metodo_geometria_marina",
        "marine_geometry_status": "estado_geometria_marina",
        "official_master_id": "id_malla_maestra_oficial",
        "official_geometry_area_km2": "area_geometria_oficial_km2",
        "overlap_area_km2": "area_solape_km2",
        "overlap_pct_official_geometry": "porcentaje_solape_geometria_oficial",
        "mapping_method": "metodo_correspondencia",
        "mapping_order": "orden_correspondencia",
        "validated_marine_area_cells_sum_km2": "suma_area_marina_validada_celdas_km2",
        "marine_geometry_area_cells_sum_km2": "suma_area_geometria_marina_celdas_km2",
        "area_union_minus_cell_geometries_km2": "diferencia_area_union_geometrias_celdas_km2",
        "detail": "detalle",
        "year": "anio",
        "period": "periodo",
        "comparison": "comparacion",
        "status": "estado",
        "n_records_period": "n_registros_periodo",
        "total_abundance_period": "abundancia_total_periodo",
        "n_years_period": "n_anios_periodo",
        "n_months_period": "n_meses_periodo",
        "species_richness_period": "riqueza_especies_periodo",
        "sampled_cells_period": "celdas_muestreadas_periodo",
        "sampled_area_period_km2": "area_muestreada_periodo_km2",
        "occupied_area_period_km2": "area_ocupada_periodo_km2",
        "effective_duration_days": "duracion_efectiva_dias",
        "effective_duration_years": "duracion_efectiva_anios",
        "requested_start": "inicio_solicitado",
        "requested_end": "fin_solicitado",
        "effective_start": "inicio_efectivo",
        "effective_end": "fin_efectivo",
        "clipped_at_data_start": "recortado_al_inicio_datos",
        "clipped_at_data_end": "recortado_al_fin_datos",
        "requested_interval_fully_covered": "intervalo_solicitado_cubierto_completo",
        "first_observation": "primera_observacion",
        "last_observation": "ultima_observacion",
        "n_years_with_records": "n_anios_con_registros",
        "n_months_with_records": "n_meses_con_registros",
        "months_with_records": "meses_con_registros",
        "latest_data_year_incomplete": "ultimo_anio_datos_incompleto",
        "effort_records": "registros_esfuerzo",
        "n_sampling_events": "n_eventos_proxy",
        "n_sampling_events_period": "n_eventos_proxy_periodo",
        "species_sampling_events": "eventos_proxy_con_registro_especie",
        "sampling_events_1": "eventos_proxy_1",
        "sampling_events_2": "eventos_proxy_2",
        "sampling_events_cell_1": "eventos_proxy_celda_1",
        "sampling_events_cell_2": "eventos_proxy_celda_2",
        "n_temporal_sampling_events": "n_eventos_proxy_temporales",
        "total_abundance": "abundancia_total",
        "sampled_area_km2": "area_muestreada_km2",
        "occupied_area_km2": "area_ocupada_km2",
        "abundance_per_sampling_event": "abundancia_por_evento_proxy",
        "abundance_per_100_sampling_events": "abundancia_por_100_eventos_proxy",
        "abundance_per_sampling_event_global_period": "abundancia_por_evento_proxy_global_periodo",
        "abundance_per_sampling_event_1": "abundancia_por_evento_proxy_1",
        "abundance_per_sampling_event_2": "abundancia_por_evento_proxy_2",
        "abundance_per_sampling_event_cell_1": "abundancia_por_evento_proxy_celda_1",
        "abundance_per_sampling_event_cell_2": "abundancia_por_evento_proxy_celda_2",
        "delta_abundance_per_sampling_event_cell": "delta_abundancia_por_evento_proxy_celda",
        "delta_abundance_event_rate": "delta_tasa_observacion_evento",
        "abundance_per_record_global": "abundancia_por_registro_global",
        "abundance_per_record_global_period": "abundancia_por_registro_global_periodo",
        "abundance_per_calendar_year_period": "abundancia_por_anio_calendario_periodo",
        "abundance_per_sampled_year_period": "abundancia_por_anio_muestreado_periodo",
        "abundance_per_sampled_cell": "abundancia_por_celda_muestreada",
        "abundance_per_sampled_cell_period": "abundancia_por_celda_muestreada_periodo",
        "abundance_per_100_records": "abundancia_por_100_registros",
        "records_per_100_records": "registros_por_100_registros",
        "detection_frequency_sampled_cells_pct": "frecuencia_deteccion_celdas_muestreadas_pct",
        "detection_frequency_sampled_cells": "frecuencia_deteccion_celdas_muestreadas",
        "detection_frequency_sampled_cells_period": "frecuencia_deteccion_celdas_muestreadas_periodo",
        "detection_frequency_1": "frecuencia_deteccion_1",
        "detection_frequency_2": "frecuencia_deteccion_2",
        "delta_detection_frequency": "delta_frecuencia_deteccion",
        "detection_frequency_norm": "frecuencia_deteccion_normalizada",
        "detection_frequency_norm_period": "frecuencia_deteccion_normalizada_periodo",
        "occupancy_prop": "proporcion_ocupacion",
        "occupancy_prop_period": "proporcion_ocupacion_periodo",
        "occupancy_norm": "ocupacion_normalizada",
        "occupancy_norm_period": "ocupacion_normalizada_periodo",
        "abundance_effort_norm": "abundancia_esfuerzo_normalizada",
        "abundance_effort_norm_period": "abundancia_esfuerzo_normalizada_periodo",
        "observation_rate_norm": "tasa_observacion_normalizada",
        "observation_rate_norm_period": "tasa_observacion_normalizada_periodo",
        "annual_relative_observation_index": "indice_relativo_observacion_anual",
        "period_relative_observation_index": "indice_relativo_observacion_periodo",
        "annual_population_index": "indice_poblacion_anual_legado",
        "period_population_index": "indice_poblacion_periodo_legado",
        "density_occupied_area_km2": "densidad_area_ocupada_km2",
        "density_sampled_area_km2": "densidad_area_muestreada_km2",
        "density_occupied_area_period_km2": "densidad_area_ocupada_periodo_km2",
        "density_occupied_area_annualized_km2": "densidad_area_ocupada_anualizada_km2",
        "density_sampled_area_annualized_km2": "densidad_area_muestreada_anualizada_km2",
        "density_annualization_basis": "base_anualizacion_densidad",
        "relative_change_abundance_raw_pct": "cambio_relativo_abundancia_bruta_pct",
        "relative_change_abundance_pct": "cambio_relativo_abundancia_pct",
        "abundance_per_record_1": "abundancia_por_registro_1",
        "abundance_per_record_2": "abundancia_por_registro_2",
        "delta_abundance_effort": "delta_abundancia_esfuerzo",
        "occupied_cells_1": "celdas_ocupadas_1",
        "occupied_cells_2": "celdas_ocupadas_2",
        "delta_occupied_cells": "delta_celdas_ocupadas",
        "sampled_cells_1": "celdas_muestreadas_1",
        "sampled_cells_2": "celdas_muestreadas_2",
        "occupancy_prop_1": "proporcion_ocupacion_1",
        "occupancy_prop_2": "proporcion_ocupacion_2",
        "delta_occupancy": "delta_ocupacion",
        "pct_change_occupancy": "cambio_ocupacion_pct",
        "population_index_1": "indice_poblacion_1",
        "population_index_2": "indice_poblacion_2",
        "delta_population_index": "delta_indice_poblacion",
        "annualized_density_1": "densidad_anualizada_1",
        "annualized_density_2": "densidad_anualizada_2",
        "delta_annualized_density": "delta_densidad_anualizada",
        "duration_years_1": "duracion_anios_1",
        "duration_years_2": "duracion_anios_2",
        "sampled_years_1": "anios_muestreados_1",
        "sampled_years_2": "anios_muestreados_2",
        "effort_records_1": "registros_esfuerzo_1",
        "effort_records_2": "registros_esfuerzo_2",
        "period_1_clipped_at_data_end": "periodo_1_recortado_al_fin_datos",
        "period_2_clipped_at_data_end": "periodo_2_recortado_al_fin_datos",
        "statistical_unit": "unidad_estadistica",
        "primary_change_metric": "metrica_principal_cambio",
        "p_adjust_BH": "p_ajustada_BH",
        "sampled_years_cell_1": "anios_muestreados_celda_1",
        "sampled_years_cell_2": "anios_muestreados_celda_2",
        "sampled_1": "muestreada_1",
        "sampled_2": "muestreada_2",
        "sampled_union": "union_muestreada",
        "sampled_intersection": "interseccion_muestreada",
        "presence_1": "presencia_1",
        "presence_2": "presencia_2",
        "abundance_per_record_cell_1": "abundancia_por_registro_celda_1",
        "abundance_per_record_cell_2": "abundancia_por_registro_celda_2",
        "delta_abundance_per_record_cell": "delta_abundancia_por_registro_celda",
        "status_union_assumption": "estado_asumiendo_union",
        "comparison_valid": "comparacion_valida",
        "non_comparable_reason": "motivo_no_comparable",
        "sampled_intersection_grids": "celdas_interseccion_muestreada",
        "sampled_union_grids": "celdas_union_muestreada",
        "comparable_sampled_grids": "celdas_muestreadas_comparables",
        "persist_prop_union": "proporcion_persistencia_union",
        "gain_prop_union": "proporcion_ganancia_union",
        "loss_prop_union": "proporcion_perdida_union",
        "net_change_prop_union": "proporcion_cambio_neto_union",
        "persist_prop_comparable": "proporcion_persistencia_comparable",
        "gain_prop_comparable": "proporcion_ganancia_comparable",
        "loss_prop_comparable": "proporcion_perdida_comparable",
        "net_change_prop_comparable": "proporcion_cambio_neto_comparable",
        "observation_rate_component": "componente_tasa_observacion",
        "observation_rate_change_signed": "cambio_firmado_tasa_observacion",
        "detection_frequency_component": "componente_frecuencia_deteccion",
        "detection_frequency_change_signed": "cambio_firmado_frecuencia_deteccion",
        "marine_density_change_signed": "cambio_firmado_densidad_marina",
        "signal_formula": "formula_senal",
        "temporal_signal_raw": "senal_temporal_bruta",
        "n_temporal_records": "n_registros_temporales",
        "n_temporal_comparisons": "n_comparaciones_temporales",
        "n_temporal_component_rows": "n_filas_componentes_temporales",
        "inference_scope": "ambito_inferencia",
        "n_detection_years": "n_anios_deteccion",
        "n_detection_events": "n_eventos_deteccion",
        "detection_span_years": "extension_deteccion_anios",
        "support_reason": "motivo_soporte",
        "pearson_dispersion_raw": "dispersion_pearson_bruta",
        "pearson_dispersion_used": "dispersion_pearson_usada",
        "annual_change_ci_low_pct": "cambio_anual_ic95_inferior_pct",
        "annual_change_ci_high_pct": "cambio_anual_ic95_superior_pct",
        "alpha_nb2": "alpha_nb2",
        "offset_variable": "variable_offset",
        "spatial_key": "clave_espacial",
    }
)


_ENGLISH_IDENTIFIER: dict[str, str] = {
    source.casefold(): target for source, target in _ENGLISH_COLUMNS.items()
}
_ENGLISH_IDENTIFIER.update(
    {
        "map": "Mapa", "maps": "Mapas", "table": "Tabla", "tables": "Tablas",
        "figure": "Figura", "figures": "Figuras", "report": "Informe", "reports": "Informes",
        "document": "Documento", "documents": "Documentos", "note": "Nota",
        "methodological": "Metodologica", "analysis": "Analisis", "analyses": "Analisis",
        "descriptive": "Descriptivo", "community": "Comunidad", "communities": "Comunidades",
        "conservation": "Conservacion", "priority": "Prioridad", "prioritisation": "Priorizacion",
        "cells": "Celdas", "cell": "Celda", "species": "Especies", "richness": "Riqueza",
        "abundance": "Abundancia", "depth": "Profundidad", "habitat": "Habitat",
        "temporal": "Temporal", "change": "Cambio", "changes": "Cambios", "advanced": "Avanzado",
        "results": "Resultados", "output": "Salida", "outputs": "Salidas", "check": "Control",
        "integrity": "Integridad", "sensitivity": "Sensibilidad", "robustness": "Robustez",
        "management": "Gestion", "selected": "Seleccionadas", "functional": "Funcional",
        "diversity": "Diversidad", "composition": "Composicion", "sexual": "Sexual",
        "sex": "Sexo", "bias": "Sesgo", "high": "Alta", "low": "Baja", "very": "Muy",
        "n": "n", "scenario": "Escenario", "scenarios": "Escenarios",
        "observation": "Observacion", "observations": "Observaciones", "outside": "Fuera",
        "marine": "Marina", "grid": "Malla", "data": "Datos", "package": "Paquete",
        "download": "Descarga", "downloads": "Descargas", "web": "Web",
        "statistical": "Estadistico", "autocorrelation": "Autocorrelacion", "coverage": "Cobertura",
        "dominant": "Dominante", "diagnostics": "Diagnostico", "regional": "Regional",
        "biogeographic": "Biogeografico", "occupancy": "Ocupacion", "frequency": "Frecuencia",
        "trend": "Tendencia", "distribution": "Distribucion", "matrix": "Matriz",
        "correlation": "Correlacion", "protection": "Proteccion", "indicator": "Indicadora",
        "significant": "Significativos", "model": "Modelo", "models": "Modelos", "network": "Red",
        "nodes": "Nodos", "edges": "Aristas", "transition": "Transicion", "vulnerability": "Vulnerabilidad",
        "endemism": "Endemismo", "cooccurrence": "Coocurrencia", "ordination": "Ordenacion",
        "rarity": "Rareza", "singularity": "Singularidad", "status": "Estado", "year": "Anio",
        "coastal": "Litoral", "residuals": "residuos", "standardised": "estandarizados",
        "spatial": "Espaciales", "scenarios": "Escenarios", "signal": "Senal", "quality": "Calidad",
        "female": "Hembras", "males": "Machos", "indeterminate": "Indeterminados", "sexed": "Sexados",
        "distance": "Distancia", "coast": "Costa", "name": "Nombre", "source": "Fuente",
        "list": "Lista", "overlap": "Solape", "bathymetric": "Batimetrica", "centroid": "Centroide",
        "pairs": "Pares", "type": "Tipo", "trends": "Tendencias", "denominator": "Denominador",
        "bathymetry": "Batimetria", "scale": "Escala", "total": "total", "regions": "Regiones",
        "complete": "Completa", "periods": "periodos", "interactive": "Interactivo", "viewer": "Visor",
        "priority_conservation_areas": "Zonas_prioritarias_conservacion",
    }
)


_ENGLISH_PATH_TOKENS: tuple[tuple[str, str], ...] = ()


_ENGLISH_PHRASES_SORTED = tuple(
    sorted({**_ENGLISH_PHRASES, **_ENGLISH_EXACT}.items(), key=lambda item: len(item[0]), reverse=True)
)


def _case_match(target: str, original: str) -> str:
    if original.isupper():
        return target.upper()
    if original.islower():
        return target.lower()
    if original[:1].isupper():
        return target[:1].upper() + target[1:]
    return target


def _replace_terms(value: str, terms: Iterable[tuple[str, str]]) -> str:
    rendered = value
    for source, target in terms:
        rendered = re.sub(
            rf"(?<!\w){re.escape(source)}(?!\w)",
            lambda match: _case_match(target, match.group(0)),
            rendered,
            flags=re.IGNORECASE,
        )
    return rendered


def _normalised_token(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def is_habitat_field(value: object) -> bool:
    """Indica si un campo de origen o exportado contiene categorías de hábitat."""

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
    """Traduce categorías de hábitat solo para presentación y exportación."""

    if value is None or not isinstance(value, str):
        return value
    rendered = value.strip()
    if not rendered:
        return value
    for source, target in sorted(
        HABITAT_VALUES.items(), key=lambda item: len(item[0]), reverse=True
    ):
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


_ENGLISH_PATH_TOKENS = tuple(
    sorted(
        {
            **{target: source for source, target in PATH_TOKENS},
            **_ENGLISH_PATH_EXACT,
            # Vocabulario adicional de nombres de figuras, tablas y controles.
            "Envelope": "Envolvente",
            "Dominance": "Dominancia",
            "Histogram": "Histograma",
            "Heatmap": "Mapa_Calor",
            "Boxplot": "Diagrama_Caja",
            "Gradient": "Gradiente",
            "Rank": "Rango",
            "with": "con",
            "vs": "frente",
            "File": "Archivo",
            "Files": "Archivos",
            "Path": "Ruta",
            "Paths": "Rutas",
            "Folder": "Carpeta",
            "Folders": "Carpetas",
            "Source": "Fuente",
            "Sources": "Fuentes",
            "Input": "Entrada",
            "Inputs": "Entradas",
            "Coastal": "Litoral",
            "Quasibinomial": "Cuasibinomial",
            "quasibinomial": "cuasibinomial",
            "Maps": "Mapas", "Map": "Mapa", "Tables": "Tablas", "Table": "Tabla",
            "Figures": "Figuras", "Figure": "Figura", "Reports": "Informes", "Report": "Informe",
            "Documents": "Documentos", "Document": "Documento", "Notes": "Notas", "Note": "Nota",
            "Analysis": "Analisis", "Descriptive": "Descriptivo", "Community": "Comunidad",
            "Conservation": "Conservacion", "Priority": "Prioridad", "Areas": "Zonas", "Area": "Zona",
            "Cells": "Celdas", "Cell": "Celda", "Species": "Especies", "Richness": "Riqueza",
            "Abundance": "Abundancia", "Depth": "Profundidad", "Habitat": "Habitat", "Temporal": "Temporal",
            "Change": "Cambio", "Changes": "Cambios", "Advanced": "Avanzado", "Results": "Resultados",
            "Output": "Salida", "Outputs": "Salidas", "Quality": "Calidad", "Control": "Control",
            "Integrity": "Integridad", "Sensitivity": "Sensibilidad", "Robustness": "Robustez",
            "Management": "Gestion", "Selected": "Seleccionadas", "Diversity": "Diversidad",
            "Functional": "Funcional", "Composition": "Composicion", "Sex": "Sexo", "Statistical": "Estadistico",
            "Autocorrelation": "Autocorrelacion", "Coverage": "Cobertura", "Dominant": "Dominante",
            "Diagnostics": "Diagnostico", "Regional": "Regional", "Biogeographic": "Biogeografico",
            "Occupancy": "Ocupacion", "Frequency": "Frecuencia", "Trend": "Tendencia", "Distribution": "Distribucion",
            "Matrix": "Matriz", "Correlation": "Correlacion", "Protection": "Proteccion", "Indicator": "Indicadora",
            "Significant": "Significativos", "Model": "Modelo", "Models": "Modelos", "Network": "Red",
            "Nodes": "Nodos", "Edges": "Aristas", "Transition": "Transicion", "Vulnerability": "Vulnerabilidad",
            "Endemism": "Endemismo", "Cooccurrence": "Coocurrencia", "Ordination": "Ordenacion", "Rarity": "Rareza",
            "Singularity": "Singularidad", "Status": "Estado", "Year": "Anio", "Coastal": "Litoral",
            "Distance": "Distancia", "Coast": "Costa", "Name": "Nombre", "Source": "Fuente", "List": "Lista",
            "Overlap": "Solape", "Bathymetric": "Batimetrica", "Centroid": "Centroide", "Pairs": "Pares",
            "Type": "Tipo", "Trends": "Tendencias", "Denominator": "Denominador", "Bathymetry": "Batimetria",
            "Scale": "Escala", "Total": "Total", "Regions": "Regiones", "Complete": "Completa", "Periods": "Periodos",
            "Interactive": "Interactivo", "Viewer": "Visor", "Data": "Datos", "Package": "Paquete",
            "Effort": "Esfuerzo", "Year": "Anio", "Years": "Anos", "Depth": "Profundidad",
            "Biogeography": "Biogeografia", "Biogeographical": "Biogeografico",
            "Hotspot": "Hotspot", "Hotspots": "Hotspots", "Persistence": "Persistencia",
            "Density": "Densidad", "Variables": "Variables", "Variable": "Variable",
            "Observations": "Observaciones", "Observation": "Observacion", "Filtered": "Filtrada",
            "Master": "Maestra", "Database": "Base_Datos", "Metrics": "Metricas",
            "Quality": "Calidad", "Index": "Indice", "Official": "Oficial",
            "Outside": "Fuera", "Invalid": "Invalidas", "Coordinates": "Coordenadas",
            "Assignment": "Asignacion", "Regional": "Regional", "Warnings": "Advertencias",
            "Warning": "Advertencia", "Duplicate": "Duplicadas", "Duplicates": "Duplicados",
            "Manifest": "Manifiesto", "Complete": "Completa", "Information": "Informacion",
            "Sex": "Sexo", "Changes": "Cambios", "Change": "Cambio", "Adjusted": "Ajustada",
            "Annual": "Anual", "Series": "Series", "Between": "Entre", "Periods": "Periodos",
            "Ranking": "Clasificacion", "Aggregated": "Agregado", "Spatial": "Espacial",
            "Moran": "Moran", "Monte": "Monte", "Carlo": "Carlo", "Test": "Prueba",
            "High": "Alto", "Low": "Bajo", "Significant": "Significativo", "Autocorrelation": "Autocorrelacion",
            "Cells": "Celdas", "Cell": "Celda", "Species": "Especies", "Abundance": "Abundancia",
            "Richness": "Riqueza", "Depth": "Profundidad", "Habitat": "Habitat", "Coast": "Costa",
            "Coastal": "Litoral", "Global": "Global", "Regional": "Regional", "Summary": "Resumen",
            "Control": "Control", "Debug": "Control", "Priority": "Prioridad", "Areas": "Zonas",
            "Conservation": "Conservacion", "Protection": "Proteccion", "Protected": "Protegidas",
            "Management": "Gestion", "Sensitivity": "Sensibilidad", "Robustness": "Robustez",
            "Functional": "Funcional", "Diversity": "Diversidad", "Traits": "Rasgos", "Used": "Utilizados",
            "Taxonomic": "Taxonomica", "Versus": "Frente", "Diagnostics": "Diagnostico",
            "Regions": "Regiones", "Region": "Region", "Network": "Red", "Threshold": "Umbral",
            "MITECO": "MITECO", "And": "Y", "and": "y", "of": "de", "By": "Por",
        }.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )
)

# Reutiliza el vocabulario de nombres de archivo para cabeceras y etiquetas
# compuestas por guiones bajos. Así, por ejemplo, ``warning_type`` no llega a
# una tabla publicada como un identificador parcialmente inglés.
_ENGLISH_IDENTIFIER.update(
    {
        source.casefold(): target
        for source, target in _ENGLISH_PATH_TOKENS
        if "_" not in source
    }
)
_ENGLISH_IDENTIFIER.update(
    {
        "warning": "Advertencia",
        "warnings": "Advertencias",
        "message": "Mensaje",
        "messages": "Mensajes",
        "line": "Linea",
        "lines": "Lineas",
        "interpretation": "Interpretacion",
        "action": "Accion",
        "stage": "Fase",
        "description": "Descripcion",
        "meaning": "Significado",
        "reason": "Motivo",
        "term": "Termino",
        "estimate": "Estimacion",
        "model": "Modelo",
        "models": "Modelos",
        "valid": "Valido",
        "invalid": "Invalido",
        "available": "Disponible",
        "insufficient": "Insuficiente",
        "created": "Creado",
        "skipped": "Omitido",
        "passed": "Superado",
        "failed": "Fallido",
        "none": "Ninguno",
        "emitted": "Emitido",
        "actual": "Actual",
        "expected": "Esperado",
        "selected": "Seleccionado",
        "master": "Maestra",
        "source": "Fuente",
        "sources": "Fuentes",
        "file": "Archivo",
        "files": "Archivos",
        "path": "Ruta",
        "paths": "Rutas",
        "folder": "Carpeta",
        "folders": "Carpetas",
        "envelope": "Envolvente",
        "dominance": "Dominancia",
        "histogram": "Histograma",
        "heatmap": "MapaCalor",
        "boxplot": "DiagramaCaja",
        "gradient": "Gradiente",
        "rank": "Rango",
        "coastal": "Litoral",
        "vs": "Frente",
    }
)


# Las cadenas visibles que ya existen en el paquete español se conservan como
# catálogo estático. La edición española no necesita consultar ni volver a
# traducir cada celda desde el inglés: solo aplica búsquedas locales a los
# textos que aún llegan en inglés desde el núcleo compartido.
#
# Se mantienen las dos fases de la implementación original (frases/exactos y
# palabras) porque algunas traducciones exactas contienen vocabulario inglés
# que debe resolverse en la segunda fase. Las expresiones regulares se
# compilan una sola vez y la traducción final se almacena en caché.
_STATIC_PHRASE_PAIRS: tuple[tuple[str, str], ...] = _ENGLISH_PHRASES_SORTED
_STATIC_WORD_PAIRS: tuple[tuple[str, str], ...] = tuple(
    sorted(_ENGLISH_WORDS.items(), key=lambda item: len(item[0]), reverse=True)
)

_STATIC_PHRASE_TRANSLATIONS: dict[str, str] = {}
for _source, _target in _STATIC_PHRASE_PAIRS:
    _STATIC_PHRASE_TRANSLATIONS.setdefault(_source.casefold(), _target)

_STATIC_WORD_TRANSLATIONS: dict[str, str] = {}
for _source, _target in _STATIC_WORD_PAIRS:
    _STATIC_WORD_TRANSLATIONS.setdefault(_source.casefold(), _target)

_STATIC_PHRASE_TERMS: tuple[str, ...] = tuple(
    sorted(_STATIC_PHRASE_TRANSLATIONS, key=len, reverse=True)
)
_STATIC_WORD_TERMS: tuple[str, ...] = tuple(
    sorted(_STATIC_WORD_TRANSLATIONS, key=len, reverse=True)
)
_STATIC_PHRASE_PATTERN = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(term) for term in _STATIC_PHRASE_TERMS) + r")(?!\w)",
    flags=re.IGNORECASE,
)
_STATIC_WORD_PATTERN = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(term) for term in _STATIC_WORD_TERMS) + r")(?!\w)",
    flags=re.IGNORECASE,
)


def _replace_static_phrase(match: re.Match[str]) -> str:
    target = _STATIC_PHRASE_TRANSLATIONS.get(match.group(0).casefold())
    return _case_match(target, match.group(0)) if target is not None else match.group(0)


def _replace_static_word(match: re.Match[str]) -> str:
    target = _STATIC_WORD_TRANSLATIONS.get(match.group(0).casefold())
    return _case_match(target, match.group(0)) if target is not None else match.group(0)


@lru_cache(maxsize=65536)
def _translate_text_cached(value: str) -> str:
    translated = _STATIC_PHRASE_PATTERN.sub(_replace_static_phrase, value)
    return _STATIC_WORD_PATTERN.sub(_replace_static_word, translated)


def _path_token_fallback(value: str) -> str:
    """Calcula una vez el resultado de la cadena de sustituciones de rutas."""

    rendered = value
    for source, target in _ENGLISH_PATH_TOKENS:
        rendered = re.sub(
            rf"(?<![A-Za-z]){re.escape(source)}(?![A-Za-z])",
            target,
            rendered,
            flags=re.IGNORECASE,
        )
    return rendered


_PATH_TRANSLATIONS: dict[str, str] = {}
for _source, _ in _ENGLISH_PATH_TOKENS:
    # Hay entradas con la misma palabra en mayúsculas/minúsculas y destinos
    # distintos. El código anterior aplicaba todas secuencialmente; precalcular
    # ese resultado conserva exactamente los nombres de salida ya publicados.
    _PATH_TRANSLATIONS.setdefault(_source.casefold(), _path_token_fallback(_source))
_PATH_TERMS: tuple[str, ...] = tuple(sorted(_PATH_TRANSLATIONS, key=len, reverse=True))
_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:" + "|".join(re.escape(term) for term in _PATH_TERMS) + r")(?![A-Za-z])",
    flags=re.IGNORECASE,
)
_LABEL_IDENTIFIER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z0-9]+_)+[A-Za-z0-9]+"
)


def _replace_path_term(match: re.Match[str]) -> str:
    return _PATH_TRANSLATIONS.get(match.group(0).casefold(), match.group(0))


def _translate_unique_series(series: pd.Series, mapper) -> pd.Series:
    """Aplica una traducción una sola vez por valor distinto de la serie."""

    if series.empty:
        return series.astype(object) if series.dtype != object else series
    mapping: dict[Any, Any] = {}
    try:
        for value in pd.unique(series.dropna()):
            mapping[value] = mapper(value) if isinstance(value, str) else value
        if not mapping:
            return series.astype(object) if series.dtype != object else series
        translated = series.map(mapping).astype(object)
        # ``Series.map(dict)`` convierte los nulos en NaN; el mapa original
        # conservaba el marcador nulo concreto de cada dtype.
        null_mask = series.isna()
        if null_mask.any() and not isinstance(series.dtype, pd.CategoricalDtype):
            translated.loc[null_mask] = series.loc[null_mask].to_numpy(dtype=object)
        return translated
    except (TypeError, ValueError):
        # Respaldo para columnas con valores no hashables, poco habituales en
        # las tablas exportadas pero válidos en pandas.
        translated = series.map(
            lambda value: mapper(value) if isinstance(value, str) else value
        )
        return translated.astype(object) if translated.dtype != object else translated


def _preserve_value(value: Any) -> Any:
    return value


def translate_text(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    return _translate_text_cached(value)


def translate_identifier(value: str) -> str:
    """Traduce etiquetas separadas por guiones bajos usadas en las salidas españolas."""
    translated: list[str] = []
    for part in value.split("_"):
        target = _ENGLISH_IDENTIFIER.get(
            part.casefold(), _ENGLISH_WORDS.get(part.casefold(), part)
        )
        if part.islower() and target.isascii():
            target = target.lower()
        translated.append(target)
    return "_".join(translated)


def translate_column_name(value: str) -> str:
    if value in _ENGLISH_COLUMNS:
        return _ENGLISH_COLUMNS[value]
    # Las columnas de entrada se mantienen disponibles durante la normalización.
    # deliberadamente. Es importante porque el libro original se lee literalmente
    # y todas las funciones analíticas siguen utilizando internamente sus nombres internos.
    if value in COLUMN_NAMES:
        return value
    if "_" in value:
        return translate_identifier(value)
    target = _ENGLISH_IDENTIFIER.get(value.casefold())
    if target is None:
        target = translate_text(value)
    return target.lower() if value.islower() and target.isascii() else target


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
    preserved_columns = {
        renamed_columns[column]
        for column in source_columns
        if is_preserved_text_field(column)
        or is_preserved_text_field(renamed_columns[column])
    }
    result = result.rename(columns=renamed_columns)
    # Presentation/export rule: ecological density values are written with at most
    # two decimals. Internal analytical frames keep full precision; this function
    # is used only at the presentation/export boundary.
    for _column in result.columns:
        _token = str(_column).casefold()
        if ("density" in _token or "densidad" in _token) and pd.api.types.is_numeric_dtype(result[_column]):
            result[_column] = pd.to_numeric(result[_column], errors="coerce").round(2)
    for column in result.select_dtypes(include=["object", "string", "category"]).columns:
        if column in habitat_columns:
            result[column] = _translate_unique_series(result[column], translate_habitat_value)
        elif column in preserved_columns:
            result[column] = _translate_unique_series(result[column], _preserve_value)
        else:
            result[column] = _translate_unique_series(result[column], translate_text)
    return result


def translate_geodataframe(frame: Any) -> Any:
    """Traduce atributos conservando la geometría y el CRS del GeoDataFrame."""
    import geopandas as gpd

    geometry_name = frame.geometry.name
    attributes = translate_frame(pd.DataFrame(frame.drop(columns=geometry_name)))
    attributes["geometry"] = frame.geometry.to_numpy()
    return gpd.GeoDataFrame(attributes, geometry="geometry", crs=frame.crs)


def translate_path(path: Path) -> Path:
    """Traduce solo el nombre de archivo final y conserva su carpeta absoluta."""
    path = Path(path)
    translated = path.name
    suffix = path.suffix
    stem = translated[:-len(suffix)] if suffix else translated
    if stem in _ENGLISH_PATH_EXACT:
        return path.with_name(_ENGLISH_PATH_EXACT[stem] + suffix)
    translated = _PATH_PATTERN.sub(_replace_path_term, translated)
    return path.with_name(translated)


def translate_label(value: Any) -> Any:
    """Traduce etiquetas visibles que pueden contener nombres con guiones bajos."""

    if value is None or not isinstance(value, str):
        return value
    translated = translate_text(value)
    return _LABEL_IDENTIFIER_PATTERN.sub(
        lambda match: translate_path(Path(match.group(0))).name,
        translated,
    )
