"""Optional blocks that depend on non-mandatory external files."""

from __future__ import annotations

from pathlib import Path
import logging
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.spatial import ConvexHull
from scipy.stats import spearmanr

from .analysis_io import OutputRegistry, csv2, save_figure, table_pair, text_file
from .analysis_status import CALCULABLE, INSUFFICIENT_DATA, NOT_ESTIMABLE
from .config import REGIONS
from .data import species_without_authority

LOGGER = logging.getLogger("hippodec_maps")

LANGUAGE = "EN"

_MESSAGES = {
    "EN": {
        "missing_traits": "No functional-traits file was found (traits in CSV or XLSX format)",
        "missing_species": "The traits file has no Species/Especie/Taxon column",
        "missing_columns": "The traits file is missing one or more required functional-trait columns",
        "too_few": "Fewer than two observed species have a complete usable functional-trait profile",
        "no_variable": "No functional trait varies among the observed species with complete profiles",
        "omit_title": "Functional diversity",
        "omit_file": "FUNCTIONAL DIVERSITY OMITTED",
        "omit_hint": "To enable it, provide the distributed trait schema with a Species/Especie/Taxon column and the required functional traits.",
        "no_species_region": "No observed species with a complete usable trait profile was recorded in this region.",
        "partial_region": "Some indices are not estimable because the region has too few functionally characterised species for the common functional-space dimensionality.",
        "full_region": "The principal incidence-based functional indices are estimable in the common functional space.",
        "method_note": (
            "FUNCTIONAL DIVERSITY\n"
            "The functional space is built only from species actually present in the selected run. "
            "Six predefined semiquantitative/numeric traits are used with equal weight after range standardisation in a Gower distance. "
            "Constant traits within the selected species are excluded because they carry no discriminatory information. "
            "Non-Euclidean Gower space is corrected first by square-rooting distances when sufficient and otherwise by Lingoes correction. "
            "A single global number of PCoA axes is then used for every comparable region. "
            "FRic and FDiv therefore use the same dimensionality in all regions; FRic is also reported relative to the global selected-species hull. "
            "FEve is computed on a complete minimum-spanning-tree graph that retains zero-distance links between functionally redundant species. "
            "FDiv uses the centroid of convex-hull vertices. FDis uses the Anderson positive-minus-negative PCoA correction on the original Gower matrix. "
            "RaoQ is calculated directly from the original Gower distances. "
            "The principal results are incidence-based (equal species weights); abundance-weighted variants using recorded N_total are exported only as a sensitivity analysis because observation abundance is effort-sensitive. "
            "Species with incomplete required traits are not silently imputed: they are documented as excluded, and regional trait coverage is reported.\n"
        ),
        "figure_title": "Functional diversity by region — incidence-based principal analysis",
        "sensitivity_title": "Functional diversity by region — observation-abundance-weighted sensitivity",
        "tax_fun_title": "Taxonomic richness and relative functional richness",
        "region": "MITECO region",
        "relative_fric": "Relative FRic (global selected-species hull = 1)",
        "tax_rich": "Taxonomic richness",
        "not_calculable_figure": "No principal functional-diversity metric is estimable for any region.",
        "not_calculable_fric": "Relative FRic is not estimable for any region with sufficient trait coverage.",
        "not_estimable_short": "N.E.",
        "not_estimable_note": "N.E. = relative FRic is not estimable with the number of functionally characterised species available in that region.",
    },
    "ES": {
        "missing_traits": "No se encontró un fichero de rasgos funcionales (CSV o XLSX)",
        "missing_species": "El fichero de rasgos no contiene una columna Species/Especie/Taxon",
        "missing_columns": "Al fichero de rasgos le faltan una o más columnas funcionales obligatorias",
        "too_few": "Menos de dos especies observadas tienen un perfil funcional completo y utilizable",
        "no_variable": "Ningún rasgo funcional varía entre las especies observadas con perfiles completos",
        "omit_title": "Diversidad funcional",
        "omit_file": "DIVERSIDAD FUNCIONAL OMITIDA",
        "omit_hint": "Para activarla, utilice el esquema de rasgos distribuido, con una columna Species/Especie/Taxon y los rasgos funcionales obligatorios.",
        "no_species_region": "No se registraron en esta región especies observadas con un perfil de rasgos completo y utilizable.",
        "partial_region": "Algunos índices no son estimables porque la región contiene pocas especies caracterizadas funcionalmente para la dimensionalidad común del espacio funcional.",
        "full_region": "Los índices funcionales principales basados en incidencia son estimables en el espacio funcional común.",
        "method_note": (
            "DIVERSIDAD FUNCIONAL\n"
            "El espacio funcional se construye únicamente con especies realmente presentes en la ejecución seleccionada. "
            "Se utilizan seis rasgos numéricos/semi-cuantitativos predefinidos con el mismo peso tras estandarización por rango en una distancia de Gower. "
            "Los rasgos constantes dentro del subconjunto seleccionado se excluyen porque no aportan capacidad discriminante. "
            "Si el espacio Gower no es euclídeo, primero se prueba la raíz cuadrada de las distancias y, si no basta, se aplica una corrección de Lingoes. "
            "A continuación se usa un único número global de ejes PCoA para todas las regiones comparables. "
            "FRic y FDiv usan así la misma dimensionalidad en todas las regiones; FRic se expresa además de forma relativa al casco global de las especies seleccionadas. "
            "FEve se calcula sobre un grafo completo de árbol de expansión mínima que conserva enlaces de distancia cero entre especies funcionalmente redundantes. "
            "FDiv usa el centroide de los vértices del casco convexo. FDis utiliza la corrección de Anderson positivo-menos-negativo de la PCoA sobre la matriz Gower original. "
            "RaoQ se calcula directamente con las distancias Gower originales. "
            "Los resultados principales se basan en incidencia (igual peso por especie); las variantes ponderadas por N_total se exportan solo como análisis de sensibilidad porque la abundancia observada depende del esfuerzo. "
            "Las especies con rasgos obligatorios incompletos no se imputan silenciosamente: se documentan como excluidas y se informa la cobertura regional de rasgos.\n"
        ),
        "figure_title": "Diversidad funcional por región — análisis principal basado en incidencia",
        "sensitivity_title": "Diversidad funcional por región — sensibilidad ponderada por abundancia observada",
        "tax_fun_title": "Riqueza taxonómica y riqueza funcional relativa",
        "region": "Región MITECO",
        "relative_fric": "FRic relativo (casco global de especies seleccionadas = 1)",
        "tax_rich": "Riqueza taxonómica",
        "not_calculable_figure": "Ningún índice principal de diversidad funcional es estimable para ninguna región.",
        "not_calculable_fric": "FRic relativo no es estimable para ninguna región con cobertura de rasgos suficiente.",
        "not_estimable_short": "N.E.",
        "not_estimable_note": "N.E. = FRic relativo no estimable con el número de especies funcionalmente caracterizadas disponible en esa región.",
    },
}


def _m(key: str) -> str:
    return _MESSAGES[LANGUAGE][key]


# Explicit schema: these columns are the biological traits. Metadata columns
# added to the workbook in the future cannot accidentally become traits.
TRAIT_SCHEMA: dict[str, tuple[str, ...]] = {
    "body_size_cm": ("body_size_cm",),
    "mobility": ("mobility",),
    "benthic_affinity": ("benthic_affinity",),
    "habitat_complexity": ("habitat_complexity",),
    # Accepted input synonym. The standardised analytical name makes
    # clear that the value is a representative/typical depth score.
    "representative_depth_m": ("representative_depth_m", "depth_mean_m"),
    "holdfast": ("holdfast",),
}


def _gower_numeric(frame: pd.DataFrame) -> np.ndarray:
    """Equal-weight Gower distance for complete numeric/semiquantitative traits."""

    values = frame.to_numpy(dtype=float)
    if values.ndim != 2 or values.shape[1] == 0:
        raise ValueError("At least one functional trait is required")
    if not np.isfinite(values).all():
        raise ValueError("Gower input must be complete after trait-quality filtering")
    ranges = np.ptp(values, axis=0)
    variable = ranges > np.finfo(float).eps
    if not variable.any():
        return np.zeros((len(values), len(values)), dtype=float)
    values = values[:, variable]
    ranges = ranges[variable]
    scaled = np.abs(values[:, None, :] - values[None, :, :]) / ranges
    return np.mean(scaled, axis=2)


def _pcoa_eigendecomposition(distance: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = len(distance)
    centering = np.eye(n) - np.ones((n, n)) / max(n, 1)
    matrix = -0.5 * centering @ (distance**2) @ centering
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    order = np.argsort(eigenvalues)[::-1]
    return eigenvalues[order], eigenvectors[:, order]


def _eigen_tolerance(eigenvalues: np.ndarray) -> float:
    if eigenvalues.size == 0:
        return 1e-12
    scale = max(float(np.max(np.abs(eigenvalues))), 1.0)
    return scale * 1e-10


def _coordinates_from_eigensystem(
    eigenvalues: np.ndarray, eigenvectors: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    tol = _eigen_tolerance(eigenvalues)
    positive = eigenvalues > tol
    negative = eigenvalues < -tol
    pos = (
        eigenvectors[:, positive] * np.sqrt(eigenvalues[positive])
        if positive.any()
        else np.zeros((len(eigenvectors), 0), dtype=float)
    )
    neg = (
        eigenvectors[:, negative] * np.sqrt(np.abs(eigenvalues[negative]))
        if negative.any()
        else np.zeros((len(eigenvectors), 0), dtype=float)
    )
    return pos, neg


def _functional_space(distance: np.ndarray) -> dict[str, Any]:
    """Build an auditable Euclidean PCoA space while preserving original axes for FDis."""

    original_eigs, original_vecs = _pcoa_eigendecomposition(distance)
    original_pos, original_neg = _coordinates_from_eigensystem(original_eigs, original_vecs)
    tol = _eigen_tolerance(original_eigs)
    min_before = float(original_eigs.min()) if original_eigs.size else 0.0
    positive_sum = float(original_eigs[original_eigs > tol].sum())
    negative_sum_abs = float(np.abs(original_eigs[original_eigs < -tol]).sum())
    negative_ratio = negative_sum_abs / positive_sum if positive_sum > 0 else np.nan

    correction = "none"
    correction_constant = 0.0
    corrected_distance = np.asarray(distance, dtype=float).copy()

    if min_before < -tol:
        sqrt_candidate = np.sqrt(np.clip(corrected_distance, 0.0, None))
        sqrt_eigs, _ = _pcoa_eigendecomposition(sqrt_candidate)
        if float(sqrt_eigs.min()) >= -_eigen_tolerance(sqrt_eigs):
            corrected_distance = sqrt_candidate
            correction = "sqrt"
        else:
            correction_constant = max(0.0, -min_before)
            squared = corrected_distance**2
            off_diagonal = ~np.eye(len(squared), dtype=bool)
            squared = squared.copy()
            squared[off_diagonal] += 2.0 * correction_constant
            squared[~off_diagonal] = 0.0
            corrected_distance = np.sqrt(np.clip(squared, 0.0, None))
            correction = "lingoes"

    corrected_eigs, corrected_vecs = _pcoa_eigendecomposition(corrected_distance)
    corrected_pos, _ = _coordinates_from_eigensystem(corrected_eigs, corrected_vecs)
    tol_after = _eigen_tolerance(corrected_eigs)
    min_after = float(corrected_eigs.min()) if corrected_eigs.size else 0.0
    if min_after < -tol_after:
        raise ValueError("Functional PCoA correction did not produce an effectively Euclidean space")

    positive_after = corrected_eigs[corrected_eigs > tol_after]
    if positive_after.size:
        cumulative = np.cumsum(positive_after) / positive_after.sum()
    else:
        cumulative = np.asarray([], dtype=float)

    return {
        "distance_original": np.asarray(distance, dtype=float),
        "distance_corrected": corrected_distance,
        "coordinates": corrected_pos,
        "original_positive_coordinates": original_pos,
        "original_negative_coordinates": original_neg,
        "eigenvalues_original": original_eigs,
        "eigenvalues_corrected": corrected_eigs,
        "correction": correction,
        "correction_constant": correction_constant,
        "min_eigenvalue_before": min_before,
        "min_eigenvalue_after": min_after,
        "negative_inertia_ratio_before": negative_ratio,
        "cumulative_positive_inertia": cumulative,
    }


def _select_global_dimensions(space: dict[str, Any], n_species: int) -> tuple[int, float]:
    eigenvalues = np.asarray(space["eigenvalues_corrected"], dtype=float)
    tol = _eigen_tolerance(eigenvalues)
    positive = eigenvalues[eigenvalues > tol]
    if positive.size == 0 or n_species < 2:
        return 0, np.nan
    cumulative = np.cumsum(positive) / positive.sum()
    dimensions = int(np.searchsorted(cumulative, 0.80) + 1)
    if n_species >= 3 and positive.size >= 2:
        dimensions = max(dimensions, 2)
    dimensions = min(dimensions, 4, int(positive.size), n_species - 1)
    explained = float(cumulative[dimensions - 1]) if dimensions > 0 else np.nan
    return dimensions, explained


def _convex_hull_vertices(points: np.ndarray) -> np.ndarray | None:
    if points.ndim != 2 or len(points) < 2:
        return None
    dimensions = points.shape[1]
    if dimensions == 1:
        values = points[:, 0]
        if np.ptp(values) <= np.finfo(float).eps:
            return None
        return np.asarray([int(np.argmin(values)), int(np.argmax(values))], dtype=int)
    if len(points) <= dimensions:
        return None
    if np.linalg.matrix_rank(points - points.mean(axis=0)) < dimensions:
        return None
    try:
        return np.asarray(ConvexHull(points).vertices, dtype=int)
    except Exception:
        return None


def _fric(points: np.ndarray) -> float:
    vertices = _convex_hull_vertices(points)
    if vertices is None:
        return np.nan
    if points.shape[1] == 1:
        return float(np.ptp(points[:, 0]))
    try:
        return float(ConvexHull(points).volume)
    except Exception:
        return np.nan


def _feve(subdist: np.ndarray, weights: np.ndarray) -> float:
    n = len(weights)
    if n < 3:
        return np.nan
    graph = nx.Graph()
    graph.add_nodes_from(range(n))
    # Add every edge explicitly, including distance == 0. NetworkX's
    # from_numpy_array treats zeros as absent edges and would therefore break
    # functional redundancy cases.
    for first in range(n):
        for second in range(first + 1, n):
            graph.add_edge(first, second, weight=float(subdist[first, second]))
    tree = nx.minimum_spanning_tree(graph, weight="weight")
    if tree.number_of_edges() != n - 1:
        return np.nan
    edge_values: list[float] = []
    for first, second, data in tree.edges(data=True):
        denominator = float(weights[first] + weights[second])
        edge_values.append(float(data["weight"]) / denominator if denominator > 0 else 0.0)
    edge = np.asarray(edge_values, dtype=float)
    total = float(edge.sum())
    if total <= np.finfo(float).eps:
        return np.nan
    edge /= total
    target = 1.0 / (n - 1)
    denominator = 1.0 - target
    if denominator <= 0:
        return np.nan
    return float((np.minimum(edge, target).sum() - target) / denominator)


def _fdiv(points: np.ndarray, weights: np.ndarray) -> float:
    if len(points) < 3:
        return np.nan
    vertices = _convex_hull_vertices(points)
    if vertices is None:
        return np.nan
    centroid = points[vertices].mean(axis=0)
    distances = np.linalg.norm(points - centroid, axis=1)
    mean_distance = float(np.mean(distances))
    if mean_distance <= np.finfo(float).eps:
        return np.nan
    deviations = distances - mean_distance
    numerator = float(np.sum(weights * deviations) + mean_distance)
    denominator = float(np.sum(weights * np.abs(deviations)) + mean_distance)
    if denominator <= np.finfo(float).eps:
        return np.nan
    return float(numerator / denominator)


def _fdis_anderson(
    positive_coordinates: np.ndarray,
    negative_coordinates: np.ndarray,
    indexes: list[int],
    weights: np.ndarray,
) -> tuple[float, int]:
    if not indexes:
        return np.nan, 0
    pos = positive_coordinates[indexes]
    neg = negative_coordinates[indexes]
    pos_centroid = np.average(pos, axis=0, weights=weights) if pos.shape[1] else np.zeros(0)
    neg_centroid = np.average(neg, axis=0, weights=weights) if neg.shape[1] else np.zeros(0)
    pos_sq = np.sum((pos - pos_centroid) ** 2, axis=1) if pos.shape[1] else np.zeros(len(indexes))
    neg_sq = np.sum((neg - neg_centroid) ** 2, axis=1) if neg.shape[1] else np.zeros(len(indexes))
    squared = pos_sq - neg_sq
    negative_count = int(np.sum(squared < -1e-12))
    # Anderson's correction for non-Euclidean principal-coordinate space:
    # when the negative-axis contribution exceeds the positive contribution,
    # retain the real distance magnitude using abs() rather than producing NaN.
    distances = np.sqrt(np.abs(squared))
    return float(np.average(distances, weights=weights)), negative_count


def _functional_metrics(
    space: dict[str, Any],
    indexes: list[int],
    weights: np.ndarray,
    dimensions: int,
    global_fric: float,
) -> dict[str, float | int]:
    if not indexes:
        return {
            "FRic": np.nan, "FRic_relative": np.nan, "FEve": np.nan,
            "FDiv": np.nan, "FDis": np.nan, "RaoQ": np.nan,
            "FDis_anderson_negative_species": 0,
        }
    weights = np.asarray(weights, dtype=float)
    if len(weights) != len(indexes) or not np.isfinite(weights).all() or float(weights.sum()) <= 0:
        return {
            "FRic": np.nan, "FRic_relative": np.nan, "FEve": np.nan,
            "FDiv": np.nan, "FDis": np.nan, "RaoQ": np.nan,
            "FDis_anderson_negative_species": 0,
        }
    weights = weights / weights.sum()
    original_distance = np.asarray(space["distance_original"], dtype=float)
    subdist = original_distance[np.ix_(indexes, indexes)]
    rao_q = float(weights @ subdist @ weights)
    fdis, fdis_negative = _fdis_anderson(
        np.asarray(space["original_positive_coordinates"], dtype=float),
        np.asarray(space["original_negative_coordinates"], dtype=float),
        indexes,
        weights,
    )

    if dimensions > 0:
        all_coordinates = np.asarray(space["coordinates"], dtype=float)[:, :dimensions]
        points = all_coordinates[indexes]
        fric = _fric(points) if len(indexes) > dimensions else np.nan
        fric_relative = (
            float(fric / global_fric)
            if np.isfinite(fric) and np.isfinite(global_fric) and global_fric > 0
            else np.nan
        )
        fdiv = _fdiv(points, weights) if len(indexes) >= 3 else np.nan
    else:
        fric = fric_relative = fdiv = np.nan
    feve = _feve(subdist, weights)
    return {
        "FRic": fric,
        "FRic_relative": fric_relative,
        "FEve": feve,
        "FDiv": fdiv,
        "FDis": fdis,
        "RaoQ": rao_q,
        "FDis_anderson_negative_species": fdis_negative,
    }


def _read_traits(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    first_line = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()[0]
    delimiter = ";" if ";" in first_line else ","
    return pd.read_csv(path, sep=delimiter, encoding="utf-8-sig")


def _resolve_trait_schema(traits: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    species_candidates = [
        column for column in traits.columns
        if str(column).strip().casefold() in {"species", "especie", "taxon", "taxón"}
    ]
    if not species_candidates:
        return pd.DataFrame(), [], ["Species/Especie/Taxon"]
    species_column = species_candidates[0]
    lookup = {str(column).strip().casefold(): column for column in traits.columns}
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    for canonical, aliases in TRAIT_SCHEMA.items():
        source = next((lookup[a.casefold()] for a in aliases if a.casefold() in lookup), None)
        if source is None:
            missing.append(canonical)
        else:
            resolved[canonical] = source
    if missing:
        return pd.DataFrame(), [species_column], missing
    out = pd.DataFrame({"Species_clean": traits[species_column].map(species_without_authority)})
    for canonical, source in resolved.items():
        out[canonical] = pd.to_numeric(traits[source], errors="coerce")
    out = out.loc[out["Species_clean"].notna() & out["Species_clean"].astype(str).str.strip().ne("")].copy()
    # Identical duplicate species rows are harmless; conflicting duplicates are
    # left as incomplete/ambiguous and excluded explicitly below.
    duplicates = out["Species_clean"].duplicated(keep=False)
    if duplicates.any():
        conflict_species: set[str] = set()
        for species_name, frame in out.loc[duplicates].groupby("Species_clean", observed=True):
            if any(frame[column].nunique(dropna=False) > 1 for column in TRAIT_SCHEMA):
                conflict_species.add(str(species_name))
        out["trait_row_conflict"] = out["Species_clean"].astype(str).isin(conflict_species)
        out = out.drop_duplicates("Species_clean", keep="first")
    else:
        out["trait_row_conflict"] = False
    return out.reset_index(drop=True), [species_column], []


def _trait_leave_one_out_sensitivity(complete: pd.DataFrame, trait_columns: list[str]) -> pd.DataFrame:
    if len(complete) < 3 or len(trait_columns) < 2:
        return pd.DataFrame(columns=["omitted_trait", "pairwise_distance_spearman_rho", "n_species", "n_traits_remaining"])
    full = _gower_numeric(complete[trait_columns])
    upper = np.triu_indices(len(full), k=1)
    rows: list[dict[str, Any]] = []
    for omitted in trait_columns:
        remaining = [trait for trait in trait_columns if trait != omitted]
        if not remaining:
            continue
        reduced = _gower_numeric(complete[remaining])
        rho = spearmanr(full[upper], reduced[upper]).statistic
        rows.append({
            "omitted_trait": omitted,
            "pairwise_distance_spearman_rho": float(rho) if np.isfinite(rho) else np.nan,
            "n_species": len(complete),
            "n_traits_remaining": len(remaining),
        })
    return pd.DataFrame(rows)


def _plot_metric_panels(
    result: pd.DataFrame,
    metrics: list[tuple[str, str]],
    title: str,
    base: Path,
) -> list[Path]:
    available = [(column, label) for column, label in metrics if column in result and pd.to_numeric(result[column], errors="coerce").notna().any()]
    if not available:
        return []
    ncols = 2
    nrows = int(np.ceil(len(available) / ncols))
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(13, 4.2 * nrows), squeeze=False)
    for axis in axes.ravel():
        axis.set_visible(False)
    for axis, (column, label) in zip(axes.ravel(), available):
        axis.set_visible(True)
        frame = result[["Region_MITECO", column]].copy()
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=[column])
        positions = np.arange(len(frame), dtype=float)
        axis.bar(positions, frame[column].to_numpy(dtype=float))
        axis.set_xticks(positions)
        axis.set_xticklabels(frame["Region_MITECO"].astype(str).tolist(), rotation=30, ha="right")
        axis.set(xlabel=_m("region"), ylabel=label, title=label)
    fig.suptitle(title, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    return save_figure(fig, base)


def run_functional_diversity(
    assigned: gpd.GeoDataFrame,
    traits_path: Path | None,
    directories: dict[str, Path],
    registry: OutputRegistry,
) -> dict[str, Any]:
    LOGGER.info("    [3/8 · 1/3] Checking and reading functional traits")
    functional_dir = directories["04_tablas"] / "functional_diversity"
    model_dir = directories["06_modelos"] / "functional_diversity"
    figure_dir = directories["05_figuras"] / "functional_diversity"

    if traits_path is None or not traits_path.exists():
        reason = _m("missing_traits")
        registry.skip("11.6", _m("omit_title"), reason)
        note = text_file(
            _m("omit_file") + "\n" + reason + ".\n" + _m("omit_hint") + "\n",
            model_dir / "Functional_Diversity_OMITTED.txt",
        )
        registry.add(note, "11.6", _m("omit_title"))
        return {"available": False, "reason": reason}

    traits_raw = _read_traits(traits_path)
    traits_resolved, species_meta, missing_columns = _resolve_trait_schema(traits_raw)
    if not species_meta:
        reason = _m("missing_species")
        registry.skip("11.6", _m("omit_title"), reason)
        return {"available": False, "reason": reason}
    if missing_columns:
        reason = _m("missing_columns") + ": " + ", ".join(missing_columns)
        registry.skip("11.6", _m("omit_title"), reason)
        return {"available": False, "reason": reason}

    table = pd.DataFrame(assigned.drop(columns="geometry", errors="ignore")).copy()
    table["Species_clean"] = table["Species"].map(species_without_authority)
    table["N_aux"] = pd.to_numeric(table.get("N_total", 0), errors="coerce").fillna(0).clip(lower=0)
    table["Region_MITECO"] = table["Region_MITECO"].fillna("No data").astype(str)
    observed_species = table["Species_clean"].dropna().astype(str).drop_duplicates().tolist()
    observed_set = set(observed_species)

    trait_columns = list(TRAIT_SCHEMA)
    traits_resolved["present_in_selected_data"] = traits_resolved["Species_clean"].astype(str).isin(observed_set)
    traits_resolved["required_traits_complete"] = traits_resolved[trait_columns].notna().all(axis=1)
    traits_resolved["traits_missing"] = traits_resolved[trait_columns].isna().apply(
        lambda row: ", ".join([column for column, missing in row.items() if bool(missing)]), axis=1
    )
    usable = traits_resolved.loc[
        traits_resolved["present_in_selected_data"]
        & traits_resolved["required_traits_complete"]
        & ~traits_resolved["trait_row_conflict"]
    ].copy()

    # Only traits that vary in the selected, observed species enter Gower. This
    # avoids diluting distances with a constant zero-contribution column.
    variable_traits = [
        column for column in trait_columns
        if pd.to_numeric(usable[column], errors="coerce").nunique(dropna=True) > 1
    ]
    constant_traits = [column for column in trait_columns if column not in variable_traits]

    trait_diagnostics_rows: list[dict[str, Any]] = []
    resolved_by_species = traits_resolved.set_index("Species_clean", drop=False)
    for species_name in observed_species:
        if species_name not in resolved_by_species.index:
            trait_diagnostics_rows.append({
                "Species": species_name, "trait_status": "missing_species_row",
                "traits_missing": ", ".join(trait_columns), "used_in_functional_space": False,
            })
            continue
        row = resolved_by_species.loc[species_name]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        if bool(row.get("trait_row_conflict", False)):
            status = "conflicting_duplicate_trait_rows"
        elif not bool(row.get("required_traits_complete", False)):
            status = "incomplete_required_traits"
        else:
            status = "used"
        trait_diagnostics_rows.append({
            "Species": species_name,
            "trait_status": status,
            "traits_missing": row.get("traits_missing", ""),
            "used_in_functional_space": status == "used",
        })
    trait_diagnostics = pd.DataFrame(trait_diagnostics_rows)
    not_used_traits = traits_resolved.loc[~traits_resolved["present_in_selected_data"]].copy()

    for name, frame in {
        "Table_Functional_Trait_Coverage_by_Species": trait_diagnostics,
        "Table_Functional_Traits_Not_Used": not_used_traits,
    }.items():
        csv_path, xlsx_path = table_pair(frame, functional_dir / name)
        registry.add(csv_path, "11.6", name)
        registry.add(xlsx_path, "11.6", name)

    if len(usable) < 2:
        reason = _m("too_few")
        registry.skip("11.6", _m("omit_title"), reason)
        return {"available": False, "reason": reason, "trait_diagnostics": trait_diagnostics}
    if not variable_traits:
        reason = _m("no_variable")
        registry.skip("11.6", _m("omit_title"), reason)
        return {"available": False, "reason": reason, "trait_diagnostics": trait_diagnostics}

    usable = usable[["Species_clean", *trait_columns]].drop_duplicates("Species_clean").reset_index(drop=True)
    species = usable["Species_clean"].astype(str).tolist()
    LOGGER.info("    [3/8 · 2/3] Gower distances, corrected PCoA, and functional indices")
    distances = _gower_numeric(usable[variable_traits])
    space = _functional_space(distances)
    dimensions, explained = _select_global_dimensions(space, len(species))
    if dimensions <= 0:
        reason = _m("no_variable")
        registry.skip("11.6", _m("omit_title"), reason)
        return {"available": False, "reason": reason, "trait_diagnostics": trait_diagnostics}
    coordinates = np.asarray(space["coordinates"], dtype=float)[:, :dimensions]
    global_fric = _fric(coordinates) if len(species) > dimensions else np.nan

    space_diagnostics = pd.DataFrame([{
        "n_species_observed_selected": len(observed_species),
        "n_species_with_complete_traits": len(species),
        "trait_coverage_global": len(species) / max(len(observed_species), 1),
        "traits_required": len(trait_columns),
        "traits_variable_used": len(variable_traits),
        "variable_traits": ", ".join(variable_traits),
        "constant_traits_excluded": ", ".join(constant_traits),
        "pcoa_correction": space["correction"],
        "pcoa_correction_constant": space["correction_constant"],
        "negative_inertia_ratio_before": space["negative_inertia_ratio_before"],
        "min_eigenvalue_before": space["min_eigenvalue_before"],
        "min_eigenvalue_after": space["min_eigenvalue_after"],
        "functional_dimensions_common": dimensions,
        "positive_inertia_explained_common_axes": explained,
        "global_FRic": global_fric,
    }])
    csv_path, xlsx_path = table_pair(space_diagnostics, functional_dir / "Table_Functional_Space_Diagnostics")
    registry.add(csv_path, "11.6", "Functional-space diagnostics")
    registry.add(xlsx_path, "11.6", "Functional-space diagnostics")

    traits_used = usable.copy()
    traits_used["used_variable_trait_count"] = len(variable_traits)
    traits_used_path = csv2(traits_used, functional_dir / "Table_11_6_Traits_Used.csv")
    registry.add(traits_used_path, "11.6", "Functional traits actually used")
    _, traits_used_xlsx = table_pair(traits_used, functional_dir / "Table_11_6_Traits_Used")
    registry.add(traits_used_xlsx, "11.6", "Functional traits actually used")

    correlation = usable[variable_traits].corr(method="pearson")
    correlation.insert(0, "trait", correlation.index)
    correlation = correlation.reset_index(drop=True)
    csv_path, xlsx_path = table_pair(correlation, functional_dir / "Table_Functional_Trait_Correlations")
    registry.add(csv_path, "11.6", "Functional-trait correlation diagnostics")
    registry.add(xlsx_path, "11.6", "Functional-trait correlation diagnostics")

    loo = _trait_leave_one_out_sensitivity(usable, variable_traits)
    csv_path, xlsx_path = table_pair(loo, functional_dir / "Table_Functional_Trait_Leave_One_Out_Sensitivity")
    registry.add(csv_path, "11.6", "Leave-one-trait-out functional-space sensitivity")
    registry.add(xlsx_path, "11.6", "Leave-one-trait-out functional-space sensitivity")

    official_regions = [details["label"] for slug, details in REGIONS.items() if slug != "all"]
    observed_regions = [
        value for value in table["Region_MITECO"].dropna().astype(str).drop_duplicates().tolist()
        if value.strip() and value.strip().casefold() not in {"no data", "sin datos", "sin_datos", "no region"}
    ]
    report_regions = official_regions + [value for value in observed_regions if value not in official_regions]
    if "No data" in table["Region_MITECO"].values:
        report_regions.append("No data")

    abundance = table.pivot_table(index="Region_MITECO", columns="Species_clean", values="N_aux", aggfunc="sum", fill_value=0)
    presence_by_region = table.groupby("Region_MITECO", observed=True)["Species_clean"].agg(
        lambda values: sorted({str(value) for value in values.dropna()})
    )

    rows: list[dict[str, Any]] = []
    for region in report_regions:
        observed_region_species = presence_by_region.get(region, []) if region in presence_by_region.index else []
        present = [name for name in species if name in set(observed_region_species)]
        observed_count = len(observed_region_species)
        coverage = len(present) / observed_count if observed_count else np.nan
        if not present:
            incidence = _functional_metrics(space, [], np.asarray([]), dimensions, global_fric)
            abundance_metrics = incidence.copy()
            analysis_status = INSUFFICIENT_DATA
            calculation_status = "not_calculable"
            calculation_note = _m("no_species_region")
        else:
            indexes = [species.index(name) for name in present]
            incidence_weights = np.ones(len(indexes), dtype=float)
            incidence = _functional_metrics(space, indexes, incidence_weights, dimensions, global_fric)
            abundance_values = abundance.loc[region] if region in abundance.index else pd.Series(dtype=float)
            abundance_weights = np.asarray([float(abundance_values.get(name, 0.0)) for name in present], dtype=float)
            abundance_metrics = _functional_metrics(space, indexes, abundance_weights, dimensions, global_fric)
            full_support = len(present) > dimensions and len(present) >= 3 and np.isfinite(incidence["FRic"])
            analysis_status = CALCULABLE if full_support else INSUFFICIENT_DATA
            calculation_status = "calculable" if full_support else "partial"
            calculation_note = _m("full_region") if full_support else _m("partial_region")

        row: dict[str, Any] = {
            "Region_MITECO": region,
            "taxonomic_species_observed": observed_count,
            "functional_species": len(present),
            "trait_coverage_fraction": coverage,
            "functional_dimensions_common": dimensions,
            "analysis_status": analysis_status,
            "calculation_status": calculation_status,
            "calculation_note": calculation_note,
        }
        # Principal incidence-based metrics use compact analytical names.
        for metric in ("FRic", "FRic_relative", "FEve", "FDiv", "FDis", "RaoQ"):
            row[metric] = incidence[metric]
            row[f"{metric}_incidence"] = incidence[metric]
        row["FDis_anderson_negative_species_incidence"] = incidence["FDis_anderson_negative_species"]
        # Abundance weighting is sensitivity only. FRic is geometrical and is
        # identical, but it is repeated with an explicit suffix for clarity.
        for metric in ("FRic", "FRic_relative", "FEve", "FDiv", "FDis", "RaoQ"):
            row[f"{metric}_abundance_weighted"] = abundance_metrics[metric]
        row["FDis_anderson_negative_species_abundance"] = abundance_metrics["FDis_anderson_negative_species"]
        rows.append(row)

    result = pd.DataFrame(rows)
    result_path = csv2(result, functional_dir / "Table_11_6_Functional_Diversity_by_Region.csv")
    registry.add(result_path, "11.6", "Functional diversity by region")

    diagnostics_columns = [
        "Region_MITECO", "taxonomic_species_observed", "functional_species", "trait_coverage_fraction",
        "functional_dimensions_common", "analysis_status", "calculation_status", "calculation_note",
    ]
    diagnostics = result[diagnostics_columns].copy()
    for metric in ("FRic", "FRic_relative", "FEve", "FDiv", "FDis", "RaoQ"):
        diagnostics[f"{metric}_valid"] = pd.to_numeric(result[metric], errors="coerce").map(np.isfinite)

    richness_counts = (
        table.groupby("Region_MITECO", observed=True)["Species_clean"]
        .nunique().rename("taxonomic_richness").reset_index()
    )
    richness_functional = (
        pd.DataFrame({"Region_MITECO": report_regions})
        .merge(richness_counts, on="Region_MITECO", how="left")
        .merge(result, on="Region_MITECO", how="left")
    )
    richness_functional["taxonomic_richness"] = richness_functional["taxonomic_richness"].fillna(0)

    for name, frame in {
        "Table_Functional_Diversity_Diagnostics_by_Region": diagnostics,
        "Table_Functional_Diversity_by_Region": result,
        "Table_Taxonomic_vs_Functional_Richness_by_Region": richness_functional,
        "Table_Regions_with_Invalid_FRic": diagnostics.loc[~diagnostics["FRic_valid"]],
    }.items():
        csv_path, xlsx_path = table_pair(frame, functional_dir / name)
        registry.add(csv_path, "11.6", name)
        registry.add(xlsx_path, "11.6", name)

    method_note = text_file(_m("method_note"), model_dir / "Methodological_Note_Functional_Diversity.txt")
    registry.add(method_note, "11.6", "Functional-diversity methodological note")

    principal_paths = _plot_metric_panels(
        result,
        [("FRic_relative", "FRic relative"), ("FEve", "FEve"), ("FDiv", "FDiv"), ("FDis", "FDis"), ("RaoQ", "RaoQ")],
        _m("figure_title"),
        figure_dir / "Figure_Functional_Diversity_by_Region",
    )
    if principal_paths:
        for path in principal_paths:
            registry.add(path, "11.6", "Functional diversity by region")
    else:
        registry.skip("11.6", "Functional diversity by region figure", _m("not_calculable_figure"))

    sensitivity_paths = _plot_metric_panels(
        result,
        [
            ("FRic_relative_abundance_weighted", "FRic relative"),
            ("FEve_abundance_weighted", "FEve"),
            ("FDiv_abundance_weighted", "FDiv"),
            ("FDis_abundance_weighted", "FDis"),
            ("RaoQ_abundance_weighted", "RaoQ"),
        ],
        _m("sensitivity_title"),
        figure_dir / "Figure_Functional_Abundance_Weighted_Sensitivity_by_Region",
    )
    for path in sensitivity_paths:
        registry.add(path, "11.6", "Abundance-weighted functional-diversity sensitivity")

    plot_richness = richness_functional.copy()
    plot_richness["taxonomic_richness"] = pd.to_numeric(plot_richness["taxonomic_richness"], errors="coerce")
    plot_richness["FRic_relative"] = pd.to_numeric(plot_richness["FRic_relative"], errors="coerce")
    # Keep every reported MITECO region in the figure. Regions where FRic cannot
    # be estimated must not disappear, and must not be converted to a false zero.
    plot_richness = plot_richness.loc[np.isfinite(plot_richness["taxonomic_richness"])].copy()
    if not plot_richness.empty:
        not_estimable_y = -0.10
        plot_richness["FRic_estimable"] = np.isfinite(plot_richness["FRic_relative"])
        plot_richness["FRic_relative_display"] = plot_richness["FRic_relative"].where(
            plot_richness["FRic_estimable"], not_estimable_y
        )
        plot_richness["taxonomic_richness_display"] = plot_richness["taxonomic_richness"].astype(float)
        for _, indexes in plot_richness.groupby(["taxonomic_richness", "FRic_relative_display"], sort=False).groups.items():
            indexes = list(indexes)
            if len(indexes) > 1:
                offsets = np.linspace(-0.025, 0.025, len(indexes))
                plot_richness.loc[indexes, "taxonomic_richness_display"] += offsets
        colors = dict(zip(
            plot_richness["Region_MITECO"].drop_duplicates().tolist(),
            sns.color_palette("colorblind", n_colors=max(plot_richness["Region_MITECO"].nunique(), 1)),
        ))
        fig, ax = plt.subplots(figsize=(11, 6.5))
        estimable = plot_richness.loc[plot_richness["FRic_estimable"]].copy()
        not_estimable = plot_richness.loc[~plot_richness["FRic_estimable"]].copy()
        if not estimable.empty:
            sns.scatterplot(
                data=estimable, x="taxonomic_richness_display", y="FRic_relative_display",
                hue="Region_MITECO", palette=colors, s=90, legend=False, ax=ax,
            )
        if not not_estimable.empty:
            sns.scatterplot(
                data=not_estimable, x="taxonomic_richness_display", y="FRic_relative_display",
                hue="Region_MITECO", palette=colors, marker="X", s=115, legend=False, ax=ax,
            )
        ax.set(title=_m("tax_fun_title"), xlabel=_m("tax_rich"), ylabel=_m("relative_fric"))
        ax.set_ylim(-0.15, 1.05)
        ax.set_yticks([not_estimable_y, 0.0, 0.25, 0.50, 0.75, 1.0])
        ax.set_yticklabels([_m("not_estimable_short"), "0.00", "0.25", "0.50", "0.75", "1.00"])
        handles = []
        for region, color in colors.items():
            region_rows = plot_richness.loc[plot_richness["Region_MITECO"] == region]
            marker = "o" if bool(region_rows["FRic_estimable"].any()) else "X"
            handles.append(
                plt.Line2D([0], [0], marker=marker, color="none", markerfacecolor=color,
                           markeredgecolor="white", markersize=8, label=region)
            )
        if handles:
            fig.legend(handles=handles, title=_m("region"), loc="center left", bbox_to_anchor=(0.75, 0.5), frameon=True)
        fig.text(0.02, 0.025, _m("not_estimable_note"), fontsize=9, ha="left", va="bottom")
        fig.subplots_adjust(right=0.71, bottom=0.18)
        for path in save_figure(fig, figure_dir / "Figure_Taxonomic_vs_Functional_Richness"):
            registry.add(path, "11.6", "Taxonomic richness versus relative functional richness")
    else:
        registry.skip("11.6", "Taxonomic versus functional richness figure", _m("not_calculable_fric"))

    LOGGER.info("    [3/8 · 3/3] Functional tables, diagnostics, sensitivity, and figures completed")
    return {
        "available": True,
        "results": result,
        "traits_used": traits_used,
        "trait_diagnostics": trait_diagnostics,
        "space_diagnostics": space_diagnostics,
        "diagnostics": diagnostics,
        "trait_sensitivity": loo,
        "richness_functional": richness_functional,
        "taxonomic_functional_plot_data": plot_richness,
    }
