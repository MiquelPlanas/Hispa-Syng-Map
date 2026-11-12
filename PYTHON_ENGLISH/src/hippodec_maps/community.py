"""Blocks 10–19: community, LCBD, rarity, networks, and biogeography."""

from __future__ import annotations

import itertools
import logging
import math
import warnings
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.api as sm
from statsmodels.tools.sm_exceptions import PerfectSeparationWarning
from scipy import stats
from scipy.spatial import ConvexHull
from matplotlib.lines import Line2D
from matplotlib.patches import Ellipse, Patch, Wedge
from sklearn.metrics import adjusted_rand_score

from .analysis_io import OutputRegistry, csv2, excel_book, finite_quantile, mode_or_na, save_figure, table_pair, text_file
from .analysis_utils import (
    AnalysisSettings,
    beta_partition_groups,
    beta_partition_multi,
    betadisper,
    betadisper_anova_table,
    bray_curtis_matrix,
    community_indices,
    euclidean_matrix,
    envfit,
    hellinger,
    indicator_values,
    jaccard_matrix,
    lcbd,
    mantel_spearman,
    nmds,
    pairwise_permanova,
    pcoa,
    pcoa_lingoes,
    permanova,
    simper,
)
from .cartography import MapContext, add_map_context
from .localization import translate_geodataframe


LOGGER = logging.getLogger("hippodec_maps")


def _is_missing_region(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip().str.casefold()
    return series.isna() | values.isin(
        {"", "nan", "none", "no data", "sin datos", "sin_datos", "no region"}
    )


def _plot_nmds_regions(
    ax: plt.Axes,
    figure: plt.Figure,
    ordination: pd.DataFrame,
) -> pd.DataFrame:
    """Plot regional envelopes, centroids and labels for a readable NMDS."""

    working = ordination.copy()
    working["NMDS1"] = pd.to_numeric(working["NMDS1"], errors="coerce")
    working["NMDS2"] = pd.to_numeric(working["NMDS2"], errors="coerce")
    usable = working.loc[
        np.isfinite(working["NMDS1"])
        & np.isfinite(working["NMDS2"])
        & ~_is_missing_region(working["Region_MITECO"])
    ].copy()
    regions = sorted(usable["Region_MITECO"].astype(str).unique())
    palette = dict(
        zip(
            regions,
            sns.color_palette("colorblind", n_colors=max(len(regions), 1)),
        )
    )
    handles: list[Line2D] = []
    control_rows: list[dict[str, Any]] = []
    labelled_centroids: list[np.ndarray] = []
    for region in regions:
        subset = usable.loc[usable["Region_MITECO"].astype(str).eq(region)]
        xy = subset[["NMDS1", "NMDS2"]].to_numpy(dtype=float)
        color = palette[region]
        ax.scatter(
            xy[:, 0],
            xy[:, 1],
            s=48,
            color=color,
            alpha=0.86,
            edgecolors="white",
            linewidths=0.45,
            zorder=3,
        )
        centroid = xy.mean(axis=0)
        envelope = "none"
        if len(xy) >= 3:
            covariance = np.cov(xy, rowvar=False)
            if np.isfinite(covariance).all():
                eigenvalues, eigenvectors = np.linalg.eigh(covariance)
                order = np.argsort(eigenvalues)[::-1]
                eigenvalues = np.maximum(eigenvalues[order], 0)
                vector = eigenvectors[:, order[0]]
                spans = np.ptp(xy, axis=0)
                fallback_size = max(float(np.nanmax(spans)) * 0.12, 0.025)
                width = max(4.0 * float(np.sqrt(eigenvalues[0])), fallback_size)
                height = max(4.0 * float(np.sqrt(eigenvalues[1])), fallback_size)
                angle = float(np.degrees(np.arctan2(vector[1], vector[0])))
                ax.add_patch(
                    Ellipse(
                        xy=centroid,
                        width=width,
                        height=height,
                        angle=angle,
                        facecolor=color,
                        edgecolor=color,
                        linewidth=0.9,
                        alpha=0.14,
                        zorder=1,
                    )
                )
                envelope = "95% covariance ellipse"
            else:
                try:
                    hull = ConvexHull(xy)
                    vertices = xy[hull.vertices]
                    ax.fill(
                        vertices[:, 0],
                        vertices[:, 1],
                        facecolor=color,
                        edgecolor=color,
                        linewidth=0.9,
                        alpha=0.14,
                        zorder=1,
                    )
                    envelope = "convex hull"
                except Exception:
                    envelope = "none"
        elif len(xy) == 2:
            ax.plot(xy[:, 0], xy[:, 1], color=color, alpha=0.35, linewidth=0.9, zorder=1)
            envelope = "two-point segment"
        ax.scatter(
            [centroid[0]],
            [centroid[1]],
            marker="X",
            s=82,
            color=color,
            edgecolor="white",
            linewidth=0.7,
            zorder=4,
        )
        if len(xy) >= 2:
            label_offset = (5, 5)
            close_labels = sum(
                float(np.linalg.norm(centroid - previous))
                <= max(float(np.ptp(usable[["NMDS1", "NMDS2"]].to_numpy(dtype=float))), 1.0) * 0.04
                for previous in labelled_centroids
            )
            if close_labels:
                label_offset = (5, 5 + 16 * close_labels)
            ax.annotate(
                region,
                tuple(centroid),
                xytext=label_offset,
                textcoords="offset points",
                fontsize=8,
                color="#243342",
                bbox={"boxstyle": "round,pad=0.18", "facecolor": "white", "alpha": 0.72, "edgecolor": "none"},
                zorder=5,
            )
            labelled_centroids.append(centroid)
        handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=color,
                markeredgecolor="white",
                markersize=7,
                label=region,
            )
        )
        control_rows.append(
            {
                "Region_MITECO": region,
                "n_ordination_points": len(xy),
                "centroid_NMDS1": centroid[0],
                "centroid_NMDS2": centroid[1],
                "envelope": envelope,
                "plot_status": "shown",
            }
        )
    if handles:
        figure.subplots_adjust(right=0.73)
        ax.legend(handles=handles, title="MITECO region", bbox_to_anchor=(1.02, 1), loc="upper left")
    return pd.DataFrame(control_rows)


def _matrices(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    abundance = table.assign(N_aux=pd.to_numeric(table["N_total"], errors="coerce").fillna(0).clip(lower=0)).pivot_table(
        index="grid_id", columns="Species", values="N_aux", aggfunc="sum", fill_value=0
    )
    abundance.index = abundance.index.astype(str)
    abundance = abundance.loc[abundance.sum(axis=1) > 0]
    return abundance, (abundance > 0).astype(int)


def _regional_matrices(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    valid = table.loc[~_is_missing_region(table["Region_MITECO"])].copy()
    abundance = valid.assign(
        N_aux=pd.to_numeric(valid["N_total"], errors="coerce").fillna(0).clip(lower=0)
    ).pivot_table(
        index="Region_MITECO", columns="Species", values="N_aux", aggfunc="sum", fill_value=0
    )
    return abundance, (abundance > 0).astype(int)


def _community_distances(
    abundance: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    raw = abundance.to_numpy(dtype=float)
    raw_bray = bray_curtis_matrix(raw)
    hellinger_euclidean = euclidean_matrix(hellinger(raw))
    incidence_jaccard = jaccard_matrix(raw > 0)
    return raw_bray, hellinger_euclidean, incidence_jaccard

def _regional_inference_groups(metadata: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, set[str]]:
    groups_series = metadata["Region_MITECO"].astype("string").str.strip()
    groups = groups_series.fillna("No data").astype(str).to_numpy()
    available = ~_is_missing_region(metadata["Region_MITECO"]).to_numpy()
    counts = pd.Series(groups[available]).value_counts()
    valid_names = set(counts[counts >= 2].index)
    keep = available & np.asarray([group in valid_names for group in groups])
    return groups, keep, valid_names


def _environmental_depth(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.where(values.between(0, 200, inclusive="both"))


def _abbreviate_species(value: object) -> str:
    words = str(value).strip().split()
    return f"{words[0][0]}. {words[1]}" if len(words) >= 2 and words[0] else str(value).strip()


def _annual_occupancy(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    work = table.dropna(subset=["Species", "year", "grid_id"]).copy()
    if "sampling_event_id" not in work.columns:
        work["sampling_event_id"] = [f"record_{index}" for index in work.index]
    effort = (
        work.groupby("year", observed=True)
        .agg(
            n_records=("grid_id", "size"),
            n_sampling_events=("sampling_event_id", "nunique"),
            sampled_cells=("grid_id", "nunique"),
            species_richness=("Species", "nunique"),
        )
        .reset_index()
    )
    # Internal convenience field; it is not interpreted as sampling effort.
    effort["records"] = effort["n_records"]
    annual = (
        work.groupby(["Species", "year"], observed=True)["grid_id"]
        .nunique()
        .rename("occupied_cells")
        .reset_index()
        .merge(effort, on="year", how="left")
    )
    annual["unoccupied_cells"] = (annual["sampled_cells"] - annual["occupied_cells"]).clip(lower=0)
    annual["occupancy"] = annual["occupied_cells"] / annual["sampled_cells"].replace(0, np.nan)
    annual["occupancy_pct"] = 100 * annual["occupancy"]
    annual["detection_frequency_sampled_cells"] = annual["occupancy"]
    columns = ["Species", "Species_short", "estimate_year", "se_year", "z_year", "p_year", "n_years", "grids_occupied_total"]
    rows: list[dict[str, Any]] = []
    occupied_total = work.groupby("Species", observed=True)["grid_id"].nunique()
    if work["year"].nunique() >= 5:
        for species, total_cells in occupied_total[occupied_total >= 10].items():
            frame = annual.loc[annual["Species"].eq(species)].copy()
            frame = frame.loc[frame["occupied_cells"].notna() & frame["unoccupied_cells"].notna() & frame["sampled_cells"].gt(0)]
            if (
                len(frame) < 5
                or frame["year"].nunique() < 5
                or frame["occupancy"].nunique(dropna=True) < 2
            ):
                continue
            try:
                design = sm.add_constant(frame["year"].astype(float), has_constant="add")
                with warnings.catch_warnings():
                    warnings.simplefilter("error", PerfectSeparationWarning)
                    model = sm.GLM(
                        frame["occupancy"].astype(float),
                        design,
                        family=sm.families.Binomial(),
                        freq_weights=frame["sampled_cells"].astype(float),
                    ).fit()
                rows.append({
                    "Species": species,
                    "Species_short": _abbreviate_species(species),
                    "estimate_year": float(model.params["year"]),
                    "se_year": float(model.bse["year"]),
                    "z_year": float(model.tvalues["year"]),
                    "p_year": float(model.pvalues["year"]),
                    "n_years": int(len(frame)),
                    "grids_occupied_total": int(total_cells),
                })
            except Exception:
                continue
    trends = pd.DataFrame(rows, columns=columns)
    if not trends.empty:
        trends = trends.sort_values("p_year", na_position="last").reset_index(drop=True)
    return effort, annual, trends

def _cooccurrence_tables(presence: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    matrix = presence.T @ presence
    columns = ["Species_1", "Species_1_short", "Species_2", "Species_2_short", "cooccurrence_grids", "only_species_1_grids", "only_species_2_grids", "union_grids", "jaccard"]
    rows: list[dict[str, Any]] = []
    for first, second in itertools.combinations(presence.columns, 2):
        first_present, second_present = presence[first].eq(1), presence[second].eq(1)
        shared = int((first_present & second_present).sum())
        only_first = int((first_present & ~second_present).sum())
        only_second = int((~first_present & second_present).sum())
        union = shared + only_first + only_second
        rows.append({
            "Species_1": first, "Species_1_short": _abbreviate_species(first),
            "Species_2": second, "Species_2_short": _abbreviate_species(second),
            "cooccurrence_grids": shared, "only_species_1_grids": only_first,
            "only_species_2_grids": only_second, "union_grids": union,
            "jaccard": shared / union if union else np.nan,
        })
    pairs = pd.DataFrame(rows, columns=columns)
    if not pairs.empty:
        pairs = pairs.sort_values(["jaccard", "cooccurrence_grids"], ascending=False).reset_index(drop=True)
    return matrix, pairs


def _regional_endemism_vulnerability(abundance: pd.DataFrame, presence: pd.DataFrame, metadata: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    region = metadata["Region_MITECO"].reindex(presence.index)
    valid_cells = region.index[~_is_missing_region(region)]
    presence_valid, abundance_valid, region_valid = presence.loc[valid_cells], abundance.loc[valid_cells], region.loc[valid_cells]
    occupied = presence_valid.reset_index(names="grid_id").melt(id_vars="grid_id", var_name="Species", value_name="present")
    occupied = occupied.loc[occupied["present"].eq(1)].drop(columns="present")
    occupied["Region_MITECO"] = occupied["grid_id"].map(region_valid)
    if occupied.empty:
        return (
            pd.DataFrame(columns=["Region_MITECO", "weighted_endemism"]),
            pd.DataFrame(columns=["Region_MITECO", "vulnerability", "richness", "occupied_grid_species", "weighted_endemism", "vulnerability_index"]),
            pd.DataFrame(columns=["Species", "grids", "abundance", "Species_short", "rarity_index", "occupancy", "rarity"]),
        )
    abundance_long = abundance_valid.reset_index(names="grid_id").melt(id_vars="grid_id", var_name="Species", value_name="abundance_cell")
    occupied = occupied.merge(abundance_long, on=["grid_id", "Species"], how="left")
    ranges = occupied.groupby("Species", observed=True).agg(grids=("grid_id", "nunique"), abundance=("abundance_cell", "sum")).reset_index()
    ranges["Species_short"] = ranges["Species"].map(_abbreviate_species)
    ranges["rarity_index"] = 1 / ranges["grids"].replace(0, np.nan)
    ranges["occupancy"] = ranges["grids"] / max(len(presence_valid), 1)
    ranges["rarity"] = 1 - ranges["occupancy"]
    occupied = occupied.merge(ranges[["Species", "rarity_index"]], on="Species", how="left")
    endemism = occupied.groupby("Region_MITECO", observed=True)["rarity_index"].sum(min_count=1).rename("weighted_endemism").reset_index()
    vulnerability = occupied.groupby("Region_MITECO", observed=True).agg(
        vulnerability=("rarity_index", "mean"), richness=("Species", "nunique"),
        occupied_grid_species=("grid_id", "size"),
    ).reset_index().merge(endemism, on="Region_MITECO", how="left")
    vulnerability["vulnerability_index"] = vulnerability["vulnerability"]
    return endemism, vulnerability, ranges


def _grid_environment(table: pd.DataFrame, cells: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    work = table.copy()
    work["Depth_environment"] = _environmental_depth(work["Depth"])
    work["Temperatura_gC"] = pd.to_numeric(work["Temperatura_gC"], errors="coerce")
    work["Habitat_clean"] = work.get("Habitat", pd.Series(pd.NA, index=work.index)).astype("string").str.strip()
    if "sampling_event_id" not in work.columns:
        work["sampling_event_id"] = [f"record_{index}" for index in work.index]
    environment = (
        work.groupby("grid_id", observed=True)
        .agg(
            Region_MITECO=("Region_MITECO", mode_or_na),
            habitat_dominante_grid=("Habitat_clean", mode_or_na),
            depth_mediana_grid=("Depth_environment", "median"),
            depth_media_grid=("Depth_environment", "mean"),
            n_depth_valid=("Depth_environment", "count"),
            temperatura_media_grid=("Temperatura_gC", "mean"),
            n_records=("grid_id", "size"),
            n_sampling_events=("sampling_event_id", "nunique"),
            n_years_observed=("year", "nunique"),
            latitude=("Latitude", "mean"),
            longitude=("Longitude", "mean"),
        )
        .reset_index()
    )
    environment["records_per_sampling_event"] = (
        environment["n_records"] / environment["n_sampling_events"].replace(0, np.nan)
    )
    environment["grid_id"] = environment["grid_id"].astype(str)
    geometry = cells[["grid_id", "geometry"]].copy()
    geometry["grid_id"] = geometry["grid_id"].astype(str)
    result = geometry.drop_duplicates("grid_id").merge(environment, on="grid_id", how="right")
    return gpd.GeoDataFrame(result, geometry="geometry", crs=cells.crs)

def _zscore(values: pd.Series) -> pd.Series:
    x = pd.to_numeric(values, errors="coerce")
    sd = x.std(ddof=0)
    return (x - x.mean()) / sd if pd.notna(sd) and sd > 0 else pd.Series(0.0, index=x.index)


def _similarity_betweenness(
    graph: nx.Graph,
    seed: int,
    exact_limit: int = 250,
    sample_size: int = 64,
) -> tuple[dict[str, float], str, int]:
    """Reproducible betweenness that does not stall on large dense networks."""
    distance_graph = nx.Graph()
    distance_graph.add_nodes_from(graph.nodes)
    for source, target, attributes in graph.edges(data=True):
        similarity = float(attributes.get("weight", np.nan))
        if np.isfinite(similarity) and similarity > 0:
            distance_graph.add_edge(source, target, distance=1.0 / similarity)
    n_nodes = distance_graph.number_of_nodes()
    sources = n_nodes if n_nodes <= exact_limit else min(sample_size, n_nodes)
    method = "exact" if sources == n_nodes else "approximate_reproducible"
    values = nx.betweenness_centrality(
        distance_graph,
        k=None if sources == n_nodes else sources,
        weight="distance",
        normalized=False,
        seed=seed,
    )
    return values, method, sources


def _merge_louvain_clusters(
    matrix: pd.DataFrame,
    raw_labels: np.ndarray,
    max_clusters: int = 8,
) -> np.ndarray:
    """Merge complete Louvain communities into an interpretable maximum.

    Louvain is retained as a network diagnostic. Its largest communities are
    retained and each complete minor community —none are split— is assigned to
    the retained community with the nearest Bray-Curtis compositional profile.
    """
    labels = np.asarray(raw_labels, dtype=int)
    if matrix.shape[1] < 2:
        return np.ones(len(labels), dtype=int)
    unique = np.asarray(sorted(np.unique(labels)))
    if len(unique) <= max_clusters:
        return labels
    abundance = matrix.to_numpy(dtype=float)
    row_totals = abundance.sum(axis=1, keepdims=True)
    relative = np.divide(
        abundance,
        row_totals,
        out=np.zeros_like(abundance, dtype=float),
        where=row_totals > 0,
    )
    profiles = np.vstack(
        [relative[labels == cluster].mean(axis=0) for cluster in unique]
    )
    profile_distance = bray_curtis_matrix(profiles)
    counts = {cluster: int(np.count_nonzero(labels == cluster)) for cluster in unique}
    retained = sorted(unique, key=lambda cluster: (-counts[cluster], int(cluster)))[
        :max_clusters
    ]
    profile_index = {cluster: index for index, cluster in enumerate(unique)}
    raw_to_merged = {
        cluster: (
            cluster
            if cluster in retained
            else min(
                retained,
                key=lambda target: (
                    float(profile_distance[profile_index[cluster], profile_index[target]]),
                    int(target),
                ),
            )
        )
        for cluster in unique
    }
    provisional = np.asarray([raw_to_merged[label] for label in labels], dtype=int)
    order = sorted(
        np.unique(provisional),
        key=lambda group: (
            -int(np.count_nonzero(provisional == group)),
            int(group),
        ),
    )
    renumber = {group: index + 1 for index, group in enumerate(order)}
    return np.asarray([renumber[group] for group in provisional], dtype=int)


def _assign_visual_macroclusters(
    cluster_summary: pd.DataFrame,
    minor_label: str,
    min_cells: int = 3,
    max_macroclusters: int = 8,
) -> pd.DataFrame:
    """Assign stable display labels to the analytical clusters."""
    summary = cluster_summary.copy()
    summary = summary.sort_values(
        ["n_cells", "community_cluster"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)
    retained = summary.loc[
        pd.to_numeric(summary["n_cells"], errors="coerce").ge(min_cells),
        "community_cluster",
    ].head(max_macroclusters).tolist()
    if not retained:
        retained = summary["community_cluster"].head(max_macroclusters).tolist()
    retained_set = set(retained)
    summary["macrocluster"] = summary["community_cluster"].map(
        lambda value: f"Cluster {value}" if value in retained_set else minor_label
    )
    summary["macro_cluster"] = summary["macrocluster"]
    return summary


def _valid_region_cluster_rows(
    clusters: pd.DataFrame,
    environment: pd.DataFrame,
) -> pd.DataFrame:
    """Return the shared valid cell set for region–cluster concordance."""
    membership = clusters[["grid_id", "community_cluster"]].copy()
    regional = environment[["grid_id", "Region_MITECO"]].copy()
    for frame in (membership, regional):
        frame["grid_id"] = frame["grid_id"].astype("string").str.strip()
    membership = membership.loc[
        membership["grid_id"].notna()
        & membership["grid_id"].ne("")
        & membership["community_cluster"].notna()
    ].drop_duplicates("grid_id", keep="first")
    regional = regional.loc[
        regional["grid_id"].notna()
        & regional["grid_id"].ne("")
        & ~_is_missing_region(regional["Region_MITECO"])
    ].drop_duplicates("grid_id", keep="first")
    return (
        membership.merge(regional, on="grid_id", how="inner", validate="one_to_one")
        .sort_values("grid_id", kind="stable")
        .reset_index(drop=True)
    )


def _region_cluster_concordance(
    cluster_region: pd.DataFrame,
) -> dict[str, float | pd.DataFrame]:
    """Build the complete R-compatible region–cluster tabular products."""
    if cluster_region.empty:
        absolute = pd.DataFrame(columns=["Region_MITECO"])
        long = pd.DataFrame(
            columns=[
                "Region_MITECO",
                "community_cluster",
                "n_cells",
                "prop_within_region",
                "prop_within_cluster",
            ]
        )
        dominant = pd.DataFrame(
            columns=["Region_MITECO", "dominant_cluster", "n_cells", "prop_within_region"]
        )
        ari = np.nan
        return {
            "ari": ari,
            "absolute": absolute,
            "row_proportions": absolute.copy(),
            "column_proportions": absolute.copy(),
            "long": long,
            "dominant": dominant,
            "ari_table": pd.DataFrame([{"metric": "Adjusted Rand Index", "value": ari}]),
        }

    matrix = pd.crosstab(
        cluster_region["Region_MITECO"],
        cluster_region["community_cluster"],
        dropna=False,
    ).sort_index(axis=0).sort_index(axis=1)
    matrix.index.name = "Region_MITECO"
    matrix.columns.name = "community_cluster"
    absolute = matrix.reset_index()
    row_proportions = matrix.div(matrix.sum(axis=1).replace(0, np.nan), axis=0).round(4).reset_index()
    column_proportions = matrix.div(matrix.sum(axis=0).replace(0, np.nan), axis=1).round(4).reset_index()
    long = absolute.melt(
        id_vars="Region_MITECO",
        var_name="community_cluster",
        value_name="n_cells",
    )
    long["prop_within_region"] = long["n_cells"] / long.groupby(
        "Region_MITECO", observed=True
    )["n_cells"].transform("sum").replace(0, np.nan)
    long["prop_within_cluster"] = long["n_cells"] / long.groupby(
        "community_cluster", observed=True
    )["n_cells"].transform("sum").replace(0, np.nan)
    dominant = (
        long.loc[long["n_cells"].gt(0)]
        .sort_values(
            ["Region_MITECO", "n_cells", "community_cluster"],
            ascending=[True, False, True],
            kind="stable",
        )
        .drop_duplicates("Region_MITECO", keep="first")
        .rename(columns={"community_cluster": "dominant_cluster"})[
            ["Region_MITECO", "dominant_cluster", "n_cells", "prop_within_region"]
        ]
        .reset_index(drop=True)
    )
    ari = float(
        adjusted_rand_score(
            cluster_region["Region_MITECO"],
            cluster_region["community_cluster"],
        )
    )
    return {
        "ari": ari,
        "absolute": absolute,
        "row_proportions": row_proportions,
        "column_proportions": column_proportions,
        "long": long,
        "dominant": dominant,
        "ari_table": pd.DataFrame([{"metric": "Adjusted Rand Index", "value": ari}]),
    }


def _distance_decay(
    matrix: pd.DataFrame,
    environment: gpd.GeoDataFrame,
    hellinger_distance: np.ndarray,
    jaccard_distance: np.ndarray,
    bray_distance: np.ndarray,
    permutations: int,
    seed: int,
) -> tuple[pd.DataFrame, dict[str, float | int | str]]:
    env = environment.set_index("grid_id").loc[matrix.index]
    centroids = env.geometry.centroid
    n = len(matrix)
    geographic = np.zeros((n, n), dtype=float)
    rows: list[dict[str, Any]] = []
    max_hellinger = math.sqrt(2.0)
    for i, first in enumerate(matrix.index):
        for j in range(i + 1, n):
            distance_m = float(centroids.iloc[i].distance(centroids.iloc[j]))
            geographic[i, j] = geographic[j, i] = distance_m / 1000.0
            hdist = float(hellinger_distance[i, j])
            jdist = float(jaccard_distance[i, j])
            bdist = float(bray_distance[i, j])
            rows.append(
                {
                    "grid_id_1": first,
                    "grid_id_2": matrix.index[j],
                    "distance_m": distance_m,
                    "distance_km": distance_m / 1000.0,
                    "hellinger_distance": hdist,
                    "hellinger_similarity": float(np.clip(1.0 - hdist / max_hellinger, 0.0, 1.0)),
                    "jaccard_distance": jdist,
                    "jaccard_similarity": float(1.0 - jdist),
                    "bray_distance": bdist,
                    "bray_similarity": float(1.0 - bdist),
                    # Internal field used by the exploratory network; primary visual similarity is Hellinger based.
                    "similarity": float(np.clip(1.0 - hdist / max_hellinger, 0.0, 1.0)),
                }
            )
    pairs = pd.DataFrame(rows)
    primary = mantel_spearman(geographic, hellinger_distance, permutations, seed)
    incidence = mantel_spearman(geographic, jaccard_distance, permutations, seed + 1)
    sensitivity = mantel_spearman(geographic, bray_distance, permutations, seed + 2)
    summary: dict[str, float | int | str] = {
        "method_primary": "Mantel Spearman: geographic distance vs Hellinger-Euclidean community distance",
        "mantel_rho": primary["mantel_rho"],
        "mantel_p_value": primary["mantel_p_value"],
        "mantel_rho_jaccard": incidence["mantel_rho"],
        "mantel_p_value_jaccard": incidence["mantel_p_value"],
        "mantel_rho_bray_sensitivity": sensitivity["mantel_rho"],
        "mantel_p_value_bray_sensitivity": sensitivity["mantel_p_value"],
        "permutations": int(permutations),
        "n_cells": int(n),
        "n_pairs": int(len(pairs)),
        "spearman_rho_pairwise_descriptive": np.nan,
        "intercept": np.nan,
        "slope": np.nan,
        "r_squared": np.nan,
        "adj_r_squared": np.nan,
        "p_value_slope": np.nan,
        "linear_inference_status": "descriptive_only_nonindependent_pairs",
    }
    valid = pairs[["distance_km", "similarity"]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(valid) >= 3 and valid["distance_km"].nunique() > 1 and valid["similarity"].nunique() > 1:
        rho = stats.spearmanr(valid["distance_km"], valid["similarity"])
        summary["spearman_rho_pairwise_descriptive"] = float(rho.statistic)
        model = sm.OLS(
            valid["similarity"].to_numpy(dtype=float),
            sm.add_constant(valid["distance_km"].to_numpy(dtype=float), has_constant="add"),
        ).fit()
        summary.update(
            {
                "intercept": float(model.params[0]),
                "slope": float(model.params[1]),
                "r_squared": float(model.rsquared),
                "adj_r_squared": float(model.rsquared_adj),
            }
        )
    return pairs, summary

def _network_clusters(
    matrix: pd.DataFrame, distance: np.ndarray, settings: AnalysisSettings
) -> tuple[pd.DataFrame, pd.DataFrame, nx.Graph, float]:
    similarity = 1 - distance
    upper = similarity[np.triu_indices(len(similarity), 1)]
    valid = upper[np.isfinite(upper)]
    threshold = float(np.quantile(valid, 0.90)) if valid.size else settings.similarity_threshold
    # A complete graph above the 90th percentile can still contain millions
    # of edges at 1 km and stall Louvain. Retain the threshold, but allow each
    # cell to contribute at most its 12 closest neighbours and at least its
    # two strongest positive links. Edge count becomes O(n), while every cell
    # remains represented.
    max_neighbors = min(12, max(0, len(similarity) - 1))
    min_neighbors = min(2, max_neighbors)
    edge_weights: dict[tuple[int, int], float] = {}
    for i in range(len(similarity)):
        row = np.asarray(similarity[i], dtype=float).copy()
        row[i] = np.nan
        finite = np.flatnonzero(np.isfinite(row) & (row > 0))
        if not finite.size:
            continue
        qualified = finite[row[finite] >= threshold]
        nearest = finite[np.argsort(-row[finite], kind="stable")[:min_neighbors]]
        candidates = np.unique(np.concatenate([qualified, nearest]))
        candidates = candidates[
            np.lexsort((candidates, -row[candidates]))[:max_neighbors]
        ]
        for j in candidates:
            first, second = sorted((int(i), int(j)))
            edge_weights[(first, second)] = max(
                edge_weights.get((first, second), -np.inf), float(row[j])
            )
    edges = [
        {"from": matrix.index[i], "to": matrix.index[j], "weight": weight}
        for (i, j), weight in sorted(edge_weights.items())
    ]
    graph = nx.Graph()
    graph.add_nodes_from(matrix.index.astype(str))
    graph.add_weighted_edges_from((row["from"], row["to"], row["weight"]) for row in edges)
    if graph.number_of_edges():
        communities = nx.community.louvain_communities(graph, weight="weight", seed=settings.random_seed)
    else:
        communities = [{node} for node in graph.nodes]
    ordered = sorted(communities, key=lambda group: (-len(group), sorted(group)[0]))
    membership = {node: index + 1 for index, group in enumerate(ordered) for node in group}
    raw_labels = np.asarray([membership[str(node)] for node in matrix.index], dtype=int)
    analysis_labels = _merge_louvain_clusters(matrix, raw_labels)
    degrees = dict(graph.degree())
    weighted_degree = dict(graph.degree(weight="weight"))
    betweenness, betweenness_method, betweenness_sources = _similarity_betweenness(
        graph, settings.random_seed
    )
    clusters = pd.DataFrame(
        {
            "grid_id": matrix.index.astype(str),
            "louvain_cluster": raw_labels,
            "community_cluster": analysis_labels,
            "degree": [degrees[str(node)] for node in matrix.index],
            "weighted_degree": [weighted_degree[str(node)] for node in matrix.index],
            "betweenness": [betweenness[str(node)] for node in matrix.index],
            "betweenness_method": betweenness_method,
            "betweenness_sources": betweenness_sources,
        }
    )
    clusters["transition_node"] = clusters["betweenness"] >= finite_quantile(clusters["betweenness"], 0.90, np.inf)
    return pd.DataFrame(edges), clusters, graph, threshold


def run_community_analysis(
    assigned: gpd.GeoDataFrame,
    occupied_cells: gpd.GeoDataFrame,
    cell_metrics: pd.DataFrame,
    directories: dict[str, Path],
    settings: AnalysisSettings,
    registry: OutputRegistry,
    cartographic_context: MapContext,
) -> dict[str, Any]:
    table = pd.DataFrame(assigned.drop(columns="geometry")).copy()
    table["grid_id"] = table["grid_id"].astype(str)
    table["year"] = pd.to_datetime(table["Fecha_aux"], errors="coerce").dt.year.astype("Int64")
    abundance, presence = _matrices(table)
    multi_species = abundance.shape[1] >= 2
    LOGGER.info(
        "  [2/8 · 1/7] Community matrices: %d occupied cells and %d species",
        abundance.shape[0],
        abundance.shape[1],
    )
    environment = _grid_environment(table, occupied_cells)
    environment = environment[environment["grid_id"].isin(abundance.index)].copy()
    environment = environment.set_index("grid_id").loc[abundance.index].reset_index()

    table_dir = directories["04_tablas"] / "community_biogeography"
    figure_dir = directories["05_figuras"] / "community_biogeography"
    model_dir = directories["06_modelos"] / "community_biogeography"

    abundance_export = abundance.reset_index().rename(columns={"index": "grid_id"})
    presence_export = presence.reset_index().rename(columns={"index": "grid_id"})
    regional_abundance, regional_presence = _regional_matrices(table)
    beta_region = beta_partition_groups(regional_presence)

    # Three complementary views of composition: Hellinger-Euclidean as the
    # primary relative-composition contrast, Jaccard for incidence, and raw
    # Bray-Curtis as sensitivity/exploratory network structure.
    distance_bray, distance_hellinger, distance_jaccard = _community_distances(abundance)
    # Internal field retained for network and sensitivity calculations. # phase is rebuilt; inferential regional tests no longer rely on raw counts alone.
    distance = distance_bray
    nmds_distance = distance_hellinger
    metadata = environment.set_index("grid_id").loc[abundance.index]
    groups, keep, valid_names = _regional_inference_groups(metadata)
    LOGGER.info("  [2/8 · 2/7] Regional community contrasts: Hellinger, Jaccard and raw-Bray sensitivity")
    if multi_species and len(valid_names) >= 2 and keep.sum() >= 4:
        perm_hellinger = permanova(distance_hellinger[np.ix_(keep, keep)], groups[keep], settings.permutations, settings.random_seed + 10)
        perm_hellinger["analysis_method"] = "primary_hellinger_euclidean"
        dispersion_hellinger, dispersion_hellinger_detail = betadisper(distance_hellinger[np.ix_(keep, keep)], groups[keep], settings.permutations, settings.random_seed + 11)
        dispersion_hellinger["analysis_method"] = "primary_hellinger_euclidean"
        pairwise_hellinger = pairwise_permanova(distance_hellinger[np.ix_(keep, keep)], groups[keep], settings.permutations, settings.random_seed + 12)
        if not pairwise_hellinger.empty:
            pairwise_hellinger["analysis_method"] = "primary_hellinger_euclidean"
        perm_jaccard = permanova(distance_jaccard[np.ix_(keep, keep)], groups[keep], settings.permutations, settings.random_seed + 13)
        perm_jaccard["analysis_method"] = "incidence_jaccard"
        dispersion_jaccard, dispersion_jaccard_detail = betadisper(distance_jaccard[np.ix_(keep, keep)], groups[keep], settings.permutations, settings.random_seed + 14)
        dispersion_jaccard["analysis_method"] = "incidence_jaccard"
        pairwise_jaccard = pairwise_permanova(distance_jaccard[np.ix_(keep, keep)], groups[keep], settings.permutations, settings.random_seed + 15)
        if not pairwise_jaccard.empty:
            pairwise_jaccard["analysis_method"] = "incidence_jaccard"
        perm_bray = permanova(distance_bray[np.ix_(keep, keep)], groups[keep], settings.permutations, settings.random_seed + 16)
        perm_bray["analysis_method"] = "sensitivity_raw_bray_curtis"
        dispersion_bray, dispersion_bray_detail = betadisper(distance_bray[np.ix_(keep, keep)], groups[keep], settings.permutations, settings.random_seed + 17)
        dispersion_bray["analysis_method"] = "sensitivity_raw_bray_curtis"
        pairwise_bray = pairwise_permanova(distance_bray[np.ix_(keep, keep)], groups[keep], settings.permutations, settings.random_seed + 18)
        if not pairwise_bray.empty:
            pairwise_bray["analysis_method"] = "sensitivity_raw_bray_curtis"
    else:
        empty_perm = {"pseudo_F": np.nan, "p_value": np.nan, "R2": np.nan, "permutations": settings.permutations}
        empty_disp = {"F": np.nan, "p_value": np.nan, "permutations": settings.permutations}
        perm_hellinger = {**empty_perm, "analysis_method": "primary_hellinger_euclidean"}
        perm_jaccard = {**empty_perm, "analysis_method": "incidence_jaccard"}
        perm_bray = {**empty_perm, "analysis_method": "sensitivity_raw_bray_curtis"}
        dispersion_hellinger = {**empty_disp, "analysis_method": "primary_hellinger_euclidean"}
        dispersion_jaccard = {**empty_disp, "analysis_method": "incidence_jaccard"}
        dispersion_bray = {**empty_disp, "analysis_method": "sensitivity_raw_bray_curtis"}
        dispersion_hellinger_detail = pd.DataFrame()
        dispersion_jaccard_detail = pd.DataFrame()
        dispersion_bray_detail = pd.DataFrame()
        pairwise_hellinger = pd.DataFrame()
        pairwise_jaccard = pd.DataFrame()
        pairwise_bray = pd.DataFrame()
        registry.skip("10", "Regional PERMANOVA", "Community analysis requires at least two species" if not multi_species else "Fewer than two regions have at least two cells")
    perm_result = perm_hellinger
    dispersion_result = dispersion_hellinger
    dispersion_detail = dispersion_hellinger_detail
    pairwise = pairwise_hellinger

    LOGGER.info("  [2/8 · 3/7] NMDS and PCoA ordinations")
    nmds_coords, stress = nmds(nmds_distance, settings.random_seed + 20)
    pcoa_coords, eigenvalues, pcoa_lingoes_diag = pcoa_lingoes(distance_bray, 2)
    ordination = metadata.reset_index()[["grid_id", "Region_MITECO"]].copy()
    ordination[["NMDS1", "NMDS2"]] = nmds_coords
    ordination[["PCoA1", "PCoA2"]] = pcoa_coords
    positive = eigenvalues[eigenvalues > 0]
    pcoa_explained = 100 * positive[:2] / max(positive.sum(), np.finfo(float).eps)
    ordination_diagnostics = pd.DataFrame(
        [
            {"method": "NMDS Hellinger-Euclidean", "diagnostic": "normalized_stress", "value_1": stress, "value_2": np.nan},
            {"method": "PCoA Bray-Curtis + Lingoes", "diagnostic": "variance_positive_axes_pct", "value_1": pcoa_explained[0] if len(pcoa_explained) else np.nan, "value_2": pcoa_explained[1] if len(pcoa_explained) > 1 else np.nan},
            {"method": "PCoA Bray-Curtis + Lingoes", "diagnostic": "negative_eigen_pct_before_lingoes", "value_1": pcoa_lingoes_diag["negative_to_positive_pct_before"], "value_2": pcoa_lingoes_diag["lingoes_constant"]},
        ]
    )
    environment_numeric = metadata[["depth_mediana_grid", "depth_media_grid", "temperatura_media_grid", "n_sampling_events"]]
    fitted_environment = envfit(nmds_coords, environment_numeric, settings.permutations, settings.random_seed + 21)

    if multi_species and len(valid_names) >= 2:
        indicators_region = indicator_values(
            presence.loc[keep],
            groups[keep],
            settings.permutations,
            settings.random_seed + 30,
            combinations=True,
        )
        simper_region = simper(abundance.loc[keep], groups[keep])
    else:
        indicators_region, simper_region = pd.DataFrame(), pd.DataFrame()

    indices_cells = community_indices(abundance).reset_index().rename(columns={"id": "grid_id"})
    metrics = cell_metrics.copy()
    metrics["grid_id"] = metrics["grid_id"].astype(str)
    hotspots = indices_cells.merge(metrics[["grid_id", "Densidad_total"]], on="grid_id", how="left")
    hotspots["hotspot_richness"] = hotspots["richness"] >= finite_quantile(hotspots["richness"], 0.90, np.inf)
    hotspots["hotspot_abundance"] = hotspots["abundance"] >= finite_quantile(hotspots["abundance"], 0.90, np.inf)
    hotspots["hotspot_density"] = hotspots["Densidad_total"] >= finite_quantile(hotspots["Densidad_total"], 0.90, np.inf)

    effort_year, occupancy_year, occupancy_trends = _annual_occupancy(table)
    cooccurrence, cooccurrence_export = _cooccurrence_tables(presence)
    cooccurrence_matrix_export = cooccurrence.reset_index().rename(columns={"Species": "Species_1", "index": "Species_1"})
    LOGGER.info("  [2/8 · 4/7] Spatial distance decay and LCBD")
    distance_pairs, decay_summary = _distance_decay(
        abundance, environment, distance_hellinger, distance_jaccard, distance_bray,
        settings.permutations, settings.random_seed + 35,
    )
    distance_decay_model = pd.DataFrame(
        [
            {
                "intercept": decay_summary["intercept"],
                "slope": decay_summary["slope"],
                "r_squared": decay_summary["r_squared"],
                "adj_r_squared": decay_summary["adj_r_squared"],
                "p_value_slope": decay_summary["p_value_slope"],
                "inference_status": decay_summary["linear_inference_status"],
            }
        ]
    )

    weighted_endemism, region_vulnerability, vulnerability_species = _regional_endemism_vulnerability(abundance, presence, metadata)
    if "weighted_endemism" in weighted_endemism.columns:
        weighted_endemism["range_weighted_rarity"] = weighted_endemism["weighted_endemism"]
    if "weighted_endemism" in region_vulnerability.columns:
        region_vulnerability["range_weighted_rarity"] = region_vulnerability["weighted_endemism"]

    lcbd_jaccard = lcbd(abundance, settings.permutations, settings.random_seed + 40, method="jaccard")
    lcbd_hellinger = lcbd(abundance, settings.permutations, settings.random_seed + 41, method="hellinger").rename(
        columns={
            "LCBD": "LCBD_hellinger",
            "LCBD_p_value": "LCBD_hellinger_p_value",
            "LCBD_p_adjust_BH": "LCBD_hellinger_p_adjust_BH",
            "LCBD_significant": "LCBD_hellinger_significant_raw",
            "LCBD_significant_FDR": "LCBD_hellinger_significant_FDR",
            "LCBD_method": "LCBD_hellinger_method",
        }
    )
    lcbd_table = lcbd_jaccard.rename(columns={"LCBD_significant": "LCBD_significant_raw"}).merge(
        lcbd_hellinger, on="grid_id", how="left", validate="one_to_one"
    )
    lcbd_threshold = finite_quantile(lcbd_table["LCBD"], 0.90, np.inf)
    lcbd_hellinger_threshold = finite_quantile(lcbd_table["LCBD_hellinger"], 0.90, np.inf)
    lcbd_table = lcbd_table.merge(
        metadata.reset_index()[["grid_id", "n_records", "n_sampling_events", "n_years_observed"]],
        on="grid_id", how="left", validate="one_to_one"
    )
    lcbd_table["support_events_ge2"] = pd.to_numeric(lcbd_table["n_sampling_events"], errors="coerce").ge(2)
    lcbd_table["p_value"] = lcbd_table["LCBD_p_value"]
    lcbd_table["p_adjust_BH"] = lcbd_table["LCBD_p_adjust_BH"]
    # Internal calculation fields are retained for module integration.
    lcbd_table["significant"] = lcbd_table["LCBD_significant_raw"]
    lcbd_table["significant_FDR"] = lcbd_table["LCBD_significant_FDR"]
    lcbd_table["hotspot"] = lcbd_table["LCBD"] >= lcbd_threshold
    lcbd_table["hotspot_lcbd"] = lcbd_table["hotspot"] & lcbd_table["significant"]
    lcbd_table["hotspot_lcbd_fdr"] = lcbd_table["hotspot"] & lcbd_table["significant_FDR"] & lcbd_table["support_events_ge2"]
    lcbd_table["hotspot_hellinger"] = lcbd_table["LCBD_hellinger"] >= lcbd_hellinger_threshold
    lcbd_table["hotspot_lcbd_hellinger_fdr"] = (
        lcbd_table["hotspot_hellinger"]
        & lcbd_table["LCBD_hellinger_significant_FDR"]
        & lcbd_table["support_events_ge2"]
    )
    lcbd_table["LCBD_high_concordant"] = lcbd_table["hotspot"] & lcbd_table["hotspot_hellinger"]
    lcbd_table["LCBD_FDR_concordant"] = lcbd_table["hotspot_lcbd_fdr"] & lcbd_table["hotspot_lcbd_hellinger_fdr"]
    occupancy_species = presence.mean(axis=0)
    rarity_species = pd.DataFrame({"Species": presence.columns, "occupancy": occupancy_species.values})
    rarity_species["rarity"] = 1 - rarity_species["occupancy"]
    cell_rarity_long = presence.reset_index().melt(id_vars="grid_id", var_name="Species", value_name="present")
    cell_rarity = (
        cell_rarity_long[cell_rarity_long["present"] > 0]
        .merge(rarity_species, on="Species", how="left")
        .groupby("grid_id")["rarity"].mean().rename("mean_rarity").reset_index()
    )
    singularity = lcbd_table.merge(cell_rarity, on="grid_id", how="left")
    singularity["LCBD_scaled"] = _zscore(singularity["LCBD"])
    singularity["rarity_scaled"] = _zscore(singularity["mean_rarity"])
    singularity["biogeo_uniqueness"] = singularity["LCBD_scaled"] + singularity["rarity_scaled"]
    singularity["hotspot_uniqueness"] = singularity["biogeo_uniqueness"] >= finite_quantile(singularity["biogeo_uniqueness"], 0.90, np.inf)

    LOGGER.info("  [2/8 · 5/7] Similarity network and biogeographic clusters")
    LOGGER.info("    [5/7 · 1/5] Network construction and Louvain communities")
    edges, clusters, graph, similarity_threshold = _network_clusters(abundance, distance, settings)
    LOGGER.info(
        "    Adaptive sparse network: %d nodes and %d edges (maximum 12 neighbours per cell)",
        graph.number_of_nodes(), graph.number_of_edges(),
    )
    cluster_groups = clusters.set_index("grid_id").loc[abundance.index, "community_cluster"].to_numpy()
    raw_cluster_groups = clusters.set_index("grid_id").loc[abundance.index, "louvain_cluster"].to_numpy()
    n_clusters_indicator = int(len(np.unique(cluster_groups)))
    n_clusters_raw = int(len(np.unique(raw_cluster_groups)))
    LOGGER.info(
        "    [5/7 · 2/5] Clusters: %d Louvain communities merged into %d analytical groups",
        n_clusters_raw,
        n_clusters_indicator,
    )
    if multi_species and n_clusters_indicator >= 2:
        # The reference R workflow computes IndVal by region, not across every
        # combination of Louvain communities. This extension evaluates each
        # analytical cluster separately, avoiding 2^k growth and retaining a
        # direct ecological interpretation.
        LOGGER.info("    [5/7 · 3/5] Indicator species for individual clusters")
        indicators_cluster = indicator_values(
            abundance,
            cluster_groups,
            settings.permutations,
            settings.random_seed + 50,
            combinations=False,
        )
        indicators_cluster["IndVal_cluster_mode"] = "single_cluster_only_bounded"
        indicators_cluster["inference_scope"] = "post_hoc_descriptive_non_independent"
        indicators_cluster["confirmatory_inference"] = False
        registry.skip(
            "18",
            "Combinatorial cluster IndVal",
            f"The {n_clusters_raw} Louvain communities are retained as a diagnostic and {n_clusters_indicator} analytical clusters are used. IndVal is calculated for individual clusters to avoid 2^k combinations; the reference R workflow does not apply IndVal to Louvain clusters.",
        )
    else:
        indicators_cluster = pd.DataFrame()
    cluster_summary = (
        clusters.merge(environment.drop(columns="geometry"), on="grid_id", how="left")
        .groupby("community_cluster", observed=True)
        .agg(
            n_cells=("grid_id", "size"),
            n_louvain_communities=("louvain_cluster", "nunique"),
            depth_median=("depth_mediana_grid", "median"),
            habitat_dominant=("habitat_dominante_grid", mode_or_na),
            region_dominant=("Region_MITECO", mode_or_na),
            betweenness_mean=("betweenness", "mean"),
        )
        .reset_index()
    )
    cluster_summary = _assign_visual_macroclusters(
        cluster_summary, "Other minor clusters", min_cells=1, max_macroclusters=8
    )
    clusters = clusters.merge(
        cluster_summary[["community_cluster", "macrocluster", "macro_cluster"]],
        on="community_cluster",
        how="left",
    )
    cluster_region = _valid_region_cluster_rows(clusters, environment)
    concordance_products = _region_cluster_concordance(cluster_region)
    ari = float(concordance_products["ari"])
    concordance = pd.DataFrame(concordance_products["absolute"])
    concordance_row = pd.DataFrame(concordance_products["row_proportions"])
    concordance_column = pd.DataFrame(concordance_products["column_proportions"])
    concordance_long = pd.DataFrame(concordance_products["long"])
    dominant_cluster_by_region = pd.DataFrame(concordance_products["dominant"])
    ari_table = pd.DataFrame(concordance_products["ari_table"])
    network_metrics = pd.DataFrame(
        {
            "metric": ["nodes", "edges", "clusters_louvain_raw", "clusters", "density", "transitivity", "similarity_threshold", "network_edge_strategy", "max_neighbors_per_cell", "analytical_cluster_cap", "betweenness_method", "betweenness_sources", "ARI_region_cluster"],
            "value": [graph.number_of_nodes(), graph.number_of_edges(), n_clusters_raw, n_clusters_indicator, nx.density(graph), nx.transitivity(graph), similarity_threshold, "adaptive_sparse_threshold_plus_knn", 12, 8, clusters["betweenness_method"].iloc[0], clusters["betweenness_sources"].iloc[0], ari],
        }
    )

    LOGGER.info("    [5/7 · 4/5] Complementary biogeographic descriptors")

    # Block 14: occupancy-abundance relationship and relative quartile classification.
    core_satellite = pd.DataFrame(
        {
            "Species": abundance.columns,
            "occupancy": presence.mean(axis=0).to_numpy(dtype=float),
            "mean_abundance_occupied_cells": abundance.where(abundance > 0).mean(axis=0).to_numpy(dtype=float),
            "total_abundance": abundance.sum(axis=0).to_numpy(dtype=float),
        }
    )
    habitat_breadth = (
        table.dropna(subset=["Habitat"])
        .groupby("Species")["Habitat"].nunique().rename("n_habitats").reset_index()
        if "Habitat" in table
        else pd.DataFrame(columns=["Species", "n_habitats"])
    )
    species_depth_work = table[["Species", "Depth"]].copy()
    species_depth_work["Depth_environment"] = _environmental_depth(species_depth_work["Depth"])
    species_depth = (
        species_depth_work.groupby("Species")["Depth_environment"]
        .median()
        .rename("depth_median")
        .reset_index()
    )
    core_satellite = core_satellite.merge(habitat_breadth, on="Species", how="left").merge(species_depth, on="Species", how="left")
    q25_occ, q75_occ = core_satellite["occupancy"].quantile([0.25, 0.75])
    core_satellite["species_type"] = np.select(
        [core_satellite["occupancy"] >= q75_occ, core_satellite["occupancy"] <= q25_occ],
        ["Core", "Satellite"],
        default="Intermedia",
    )
    core_satellite["occupancy_class"] = core_satellite["species_type"].replace(
        {"Core": "High-occupancy", "Satellite": "Low-occupancy", "Intermedia": "Intermediate", "Intermediate": "Intermediate"}
    )
    core_satellite["occupancy_class_display"] = core_satellite["occupancy_class"].replace({'High-occupancy': 'High occupancy', 'Intermediate': 'Intermediate occupancy', 'Low-occupancy': 'Low occupancy'})
    core_satellite_summary = (
        core_satellite.groupby("occupancy_class", observed=True)
        .agg(
            n_species=("Species", "size"),
            occupancy_mean=("occupancy", "mean"),
            abundance_mean=("mean_abundance_occupied_cells", "mean"),
            abundance_total=("total_abundance", "sum"),
            n_habitats_median=("n_habitats", "median"),
            depth_median=("depth_median", "median"),
        )
        .reset_index()
    )

    # Bloque 11.5 y 11.7: gradiente latitudinal y coldspots.
    latitudinal = indices_cells.merge(environment[["grid_id", "latitude"]], on="grid_id", how="left")
    valid_latitude = latitudinal[["latitude", "richness"]].dropna()
    if len(valid_latitude) >= 3 and valid_latitude["latitude"].nunique() > 1:
        lat_model = stats.linregress(valid_latitude["latitude"], valid_latitude["richness"])
        latitudinal_model = pd.DataFrame(
            [{"slope_richness_per_degree": lat_model.slope, "intercept": lat_model.intercept, "R2": lat_model.rvalue**2, "p_value": lat_model.pvalue, "n_cells": len(valid_latitude)}]
        )
    else:
        latitudinal_model = pd.DataFrame([{"slope_richness_per_degree": np.nan, "intercept": np.nan, "R2": np.nan, "p_value": np.nan, "n_cells": len(valid_latitude)}])
    coldspots = indices_cells.merge(lcbd_table, on="grid_id", how="left")
    low_richness = finite_quantile(coldspots["richness"], 0.10, -np.inf)
    high_abundance = finite_quantile(coldspots["abundance"], 0.75, np.inf)
    coldspots["coldspot_type"] = np.select(
        [
            coldspots["richness"].le(low_richness) & coldspots["abundance"].ge(high_abundance),
            coldspots["richness"].le(low_richness),
        ],
        ["High-abundance coldspot", "Low-diversity coldspot"],
        default="Not a coldspot",
    )

    LOGGER.info("    [5/7 · 5/5] Network sensitivity at thresholds 85, 90, and 95")
    # Block 18.11: network sensitivity at percentiles 85, 90, and 95.
    similarity = 1 - distance
    similarity_values = similarity[np.triu_indices(len(similarity), 1)]
    sensitivity_rows: list[dict[str, Any]] = []
    sensitivity_memberships: list[pd.DataFrame] = []
    for threshold_quantile in (0.85, 0.90, 0.95):
        threshold_value = float(np.quantile(similarity_values, threshold_quantile)) if len(similarity_values) else np.nan
        threshold_graph = nx.Graph()
        threshold_graph.add_nodes_from(abundance.index.astype(str))
        for i, j in zip(*np.triu_indices(len(similarity), 1)):
            if similarity[i, j] >= threshold_value:
                threshold_graph.add_edge(str(abundance.index[i]), str(abundance.index[j]), weight=float(similarity[i, j]))
        if threshold_graph.number_of_edges():
            groups_threshold = nx.community.louvain_communities(threshold_graph, weight="weight", seed=settings.random_seed)
            modularity = nx.community.modularity(threshold_graph, groups_threshold, weight="weight")
        else:
            groups_threshold = [{node} for node in threshold_graph.nodes]
            modularity = np.nan
        groups_threshold = sorted(groups_threshold, key=lambda group: (-len(group), sorted(group)[0]))
        sizes = [len(group) for group in groups_threshold]
        sensitivity_rows.append(
            {
                "threshold_quantile": threshold_quantile,
                "threshold_similarity": threshold_value,
                "n_vertices": threshold_graph.number_of_nodes(),
                "n_edges": threshold_graph.number_of_edges(),
                "n_clusters": len(groups_threshold),
                "min_cluster_size": min(sizes) if sizes else np.nan,
                "max_cluster_size": max(sizes) if sizes else np.nan,
                "mean_cluster_size": float(np.mean(sizes)) if sizes else np.nan,
                "modularity": modularity,
            }
        )
        sensitivity_memberships.append(
            pd.DataFrame(
                [
                    {"grid_id": node, "community_cluster": cluster_index + 1, "threshold_quantile": threshold_quantile, "threshold_similarity": threshold_value}
                    for cluster_index, group in enumerate(groups_threshold)
                    for node in group
                ]
            )
        )
    threshold_sensitivity = pd.DataFrame(sensitivity_rows)
    threshold_membership = pd.concat(sensitivity_memberships, ignore_index=True)

    LOGGER.info("  [2/8 · 6/7] Contrasts among clusters")
    # Bloque 18.13: beta-diversidad entre clusters y contraste multivariante.
    cluster_presence = presence.copy()
    cluster_presence["community_cluster"] = cluster_groups
    cluster_presence = cluster_presence.groupby("community_cluster").max()
    cluster_presence = cluster_presence.loc[:, cluster_presence.sum(axis=0) > 0]
    beta_clusters = beta_partition_groups(cluster_presence)
    cluster_species_presence = cluster_presence.reset_index()
    empty_beta_multi = pd.DataFrame(columns=["metric", "value"])
    empty_beta_pair = pd.DataFrame(
        columns=["cluster_1", "cluster_2", "beta_total_sor", "beta_turnover_sim", "beta_nested_sne"]
    )
    empty_beta_component = pd.DataFrame(
        columns=[
            "comparison",
            "dominant_component",
            "beta_total_sorensen",
            "beta_turnover_simpson",
            "beta_nestedness_sorensen",
        ]
    )
    if cluster_presence.shape[0] >= 2 and cluster_presence.shape[1] >= 2:
        beta_multi_values = beta_partition_multi(cluster_presence)
        beta_multi_table = pd.DataFrame(
            [
                {"metric": "beta_total_sorensen", "value": beta_multi_values["beta_total"]},
                {"metric": "beta_turnover_simpson", "value": beta_multi_values["beta_turnover"]},
                {"metric": "beta_nestedness_sorensen", "value": beta_multi_values["beta_nestedness"]},
            ]
        )
        beta_pair_table = (
            beta_clusters.rename(
                columns={
                    "group_1": "cluster_1",
                    "group_2": "cluster_2",
                    "beta_sorensen": "beta_total_sor",
                    "beta_turnover_simpson": "beta_turnover_sim",
                    "beta_nestedness": "beta_nested_sne",
                }
            )
            .sort_values("beta_total_sor", ascending=False)
            .reset_index(drop=True)
        )
        if beta_multi_values["beta_turnover"] > beta_multi_values["beta_nestedness"]:
            dominant_component = "turnover"
        elif beta_multi_values["beta_turnover"] < beta_multi_values["beta_nestedness"]:
            dominant_component = "nestedness"
        else:
            dominant_component = "equal"
        beta_component_summary = pd.DataFrame(
            [
                {
                    "comparison": "all_clusters",
                    "dominant_component": dominant_component,
                    "beta_total_sorensen": beta_multi_values["beta_total"],
                    "beta_turnover_simpson": beta_multi_values["beta_turnover"],
                    "beta_nestedness_sorensen": beta_multi_values["beta_nestedness"],
                }
            ]
        )
    else:
        beta_multi_table = empty_beta_multi
        beta_pair_table = empty_beta_pair
        beta_component_summary = empty_beta_component
    cluster_valid_counts = pd.Series(cluster_groups).value_counts()
    cluster_valid_names = set(cluster_valid_counts[cluster_valid_counts >= 2].index)
    keep_cluster = np.asarray([value in cluster_valid_names for value in cluster_groups])
    cluster_sizes_all = (
        cluster_valid_counts.sort_index()
        .rename_axis("community_cluster")
        .rename("n_cells")
        .reset_index()
    )
    cluster_sizes_valid = cluster_sizes_all.loc[cluster_sizes_all["n_cells"] >= 2].reset_index(drop=True)
    empty_betadisper_detail = pd.DataFrame(
        columns=["grid_id", "community_cluster", "distance_to_centroid"]
    )
    empty_betadisper_summary = pd.DataFrame(
        columns=["community_cluster", "n_cells", "mean_distance", "sd_distance"]
    )
    empty_betadisper_anova = pd.DataFrame(
        columns=["term", "Df", "Sum Sq", "Mean Sq", "F value", "Pr(>F)"]
    )
    empty_betadisper_permutest = pd.DataFrame(
        columns=["method", "F_value", "p_value"]
    )
    if multi_species and len(cluster_valid_names) >= 2 and keep_cluster.sum() >= 4:
        permanova_clusters = permanova(
            distance[np.ix_(keep_cluster, keep_cluster)],
            cluster_groups[keep_cluster],
            settings.permutations,
            settings.random_seed + 60,
        )
        cluster_distance = distance[np.ix_(keep_cluster, keep_cluster)]
        cluster_labels_valid = cluster_groups[keep_cluster]
        betadisper_clusters, betadisper_detail_raw = betadisper(
            cluster_distance,
            cluster_labels_valid,
            settings.permutations,
            settings.random_seed + 61,
        )
        betadisper_cluster_detail = betadisper_detail_raw.rename(
            columns={"group": "community_cluster"}
        )
        betadisper_cluster_detail.insert(
            0, "grid_id", abundance.index[keep_cluster].astype(str).to_numpy()
        )
        betadisper_cluster_summary = (
            betadisper_cluster_detail.groupby("community_cluster", sort=True, observed=True)
            .agg(
                n_cells=("grid_id", "size"),
                mean_distance=("distance_to_centroid", "mean"),
                sd_distance=("distance_to_centroid", "std"),
            )
            .reset_index()
        )
        betadisper_cluster_anova = betadisper_anova_table(
            betadisper_cluster_detail["distance_to_centroid"].to_numpy(dtype=float),
            betadisper_cluster_detail["community_cluster"].to_numpy(),
        )
        betadisper_cluster_permutest = pd.DataFrame(
            [
                {
                    "method": "permutest_betadisper",
                    "F_value": betadisper_clusters.get("F", np.nan),
                    "p_value": betadisper_clusters.get("p_value", np.nan),
                }
            ]
        )
    else:
        permanova_clusters = {"pseudo_F": np.nan, "p_value": np.nan, "R2": np.nan, "permutations": settings.permutations}
        betadisper_clusters = {"F": np.nan, "p_value": np.nan, "permutations": settings.permutations}
        betadisper_cluster_detail = empty_betadisper_detail
        betadisper_cluster_summary = empty_betadisper_summary
        betadisper_cluster_anova = empty_betadisper_anova
        betadisper_cluster_permutest = empty_betadisper_permutest

    permanova_clusters["inference_scope"] = "post_hoc_descriptive_non_independent"
    permanova_clusters["confirmatory_inference"] = False
    betadisper_clusters["inference_scope"] = "post_hoc_descriptive_non_independent"

    # Composición y dominancia por cluster/macrocluster (bloques 18.17–18.18).
    cluster_lookup = clusters.set_index("grid_id")
    cluster_link_meta = clusters[
        ["grid_id", "community_cluster", "macrocluster", "macro_cluster"]
    ].drop_duplicates("grid_id")
    grid_link_metrics = environment.drop(columns="geometry").copy()
    grid_link_metrics = grid_link_metrics.merge(
        indices_cells[["grid_id", "richness", "abundance"]],
        on="grid_id",
        how="left",
        suffixes=("", "_indices"),
    )
    grid_link_metrics = grid_link_metrics.merge(
        singularity[["grid_id", "LCBD", "hotspot_lcbd"]],
        on="grid_id",
        how="left",
    )
    if "Habitat" in table.columns:
        habitat_counts = (
            table.assign(_habitat=table["Habitat"].astype("string").str.strip())
            .groupby("grid_id", observed=True)["_habitat"]
            .nunique()
            .rename("n_habitats_grid")
            .reset_index()
        )
        grid_link_metrics = grid_link_metrics.merge(habitat_counts, on="grid_id", how="left")
    if "n_habitats_grid" not in grid_link_metrics.columns:
        grid_link_metrics["n_habitats_grid"] = pd.NA
    grid_link_metrics["fuente_habitat_depth"] = "assigned_observations"
    for missing_column in ["n_registros_depth"]:
        if missing_column not in grid_link_metrics.columns:
            grid_link_metrics[missing_column] = pd.NA
    obs_cluster_link = (
        table.drop_duplicates()
        .merge(cluster_link_meta, on="grid_id", how="left", validate="many_to_one")
        .merge(
            grid_link_metrics[
                [
                    "grid_id",
                    "LCBD",
                    "richness",
                    "abundance",
                    "hotspot_lcbd",
                    "depth_mediana_grid",
                    "depth_media_grid",
                    "n_depth_valid",
                    "n_registros_depth",
                    "n_habitats_grid",
                    "habitat_dominante_grid",
                    "fuente_habitat_depth",
                ]
            ],
            on="grid_id",
            how="left",
            suffixes=("", "_grid"),
        )
    )
    link_group_cols = ["grid_id", "community_cluster"]
    if "macro_cluster" in obs_cluster_link.columns:
        link_group_cols.append("macro_cluster")
    link_grouped = obs_cluster_link.groupby(link_group_cols, dropna=False, sort=True, observed=True)
    cluster_link_summary = link_grouped.size().rename("n_observations").to_frame()
    if "Species" in obs_cluster_link.columns:
        cluster_link_summary["n_species"] = link_grouped["Species"].nunique()
        species_list = link_grouped["Species"].agg(
            lambda values: " | ".join(sorted(values.dropna().astype(str).unique()))
        )
        cluster_link_summary["species_list"] = species_list
    for summary_column in [
        "LCBD",
        "richness",
        "abundance",
        "hotspot_lcbd",
        "depth_mediana_grid",
        "depth_media_grid",
        "n_depth_valid",
        "n_registros_depth",
        "n_habitats_grid",
        "habitat_dominante_grid",
        "fuente_habitat_depth",
    ]:
        if summary_column in obs_cluster_link.columns:
            cluster_link_summary[summary_column] = link_grouped[summary_column].first()
    cluster_link_summary = cluster_link_summary.reset_index().sort_values("grid_id", kind="stable")
    composition_base = obs_cluster_link.copy()
    abundance_source = next(
        (column for column in ["N_total", "Abundance", "n"] if column in composition_base.columns),
        None,
    )
    if abundance_source is None:
        composition_base["abund_dom"] = 1.0
    else:
        composition_base["abund_dom"] = pd.to_numeric(
            composition_base[abundance_source], errors="coerce"
        ).fillna(0)
    composition_base["Species_short"] = composition_base["Species"].map(_abbreviate_species)

    def _species_composition(group_column: str) -> pd.DataFrame:
        valid = composition_base.loc[
            composition_base[group_column].notna()
            & composition_base["Species"].notna()
            & composition_base["Species"].astype(str).str.strip().ne("")
        ].copy()
        if valid.empty:
            return pd.DataFrame(
                columns=[
                    group_column,
                    "Species",
                    "Species_short",
                    "total_abundance",
                    "n_observations",
                    "n_grids",
                    "rel_abundance",
                ]
            )
        result = (
            valid.groupby([group_column, "Species", "Species_short"], dropna=False, observed=True)
            .agg(
                total_abundance=("abund_dom", "sum"),
                n_observations=("grid_id", "size"),
                n_grids=("grid_id", "nunique"),
            )
            .reset_index()
        )
        result["rel_abundance"] = result["total_abundance"] / result.groupby(
            group_column, observed=True
        )["total_abundance"].transform("sum").replace(0, np.nan)
        return result.sort_values(
            [group_column, "total_abundance", "n_grids"],
            ascending=[True, False, False],
            kind="stable",
        ).reset_index(drop=True)

    species_cluster_original = _species_composition("community_cluster")
    species_macrocluster = _species_composition("macro_cluster")
    dominant_cluster_species_original = (
        species_cluster_original.groupby("community_cluster", observed=True, sort=False).head(1)
        .rename(
            columns={
                "Species": "dominant_species",
                "Species_short": "dominant_species_short",
                "total_abundance": "dominant_abundance",
                "rel_abundance": "dominant_rel_abundance",
            }
        )
        .reset_index(drop=True)
    )
    dominant_macrocluster_species = (
        species_macrocluster.groupby("macro_cluster", observed=True, sort=False).head(1)
        .rename(
            columns={
                "Species": "dominant_species",
                "Species_short": "dominant_species_short",
                "total_abundance": "dominant_abundance",
                "rel_abundance": "dominant_rel_abundance",
            }
        )
        .reset_index(drop=True)
    )
    top10_cluster_species = species_cluster_original.groupby(
        "community_cluster", observed=True, sort=False
    ).head(10).reset_index(drop=True)
    top10_macrocluster_species = species_macrocluster.groupby(
        "macro_cluster", observed=True, sort=False
    ).head(10).reset_index(drop=True)
    pie_group_column = "macro_cluster" if composition_base["macro_cluster"].notna().any() else "community_cluster"
    pie_species_cluster = _species_composition(pie_group_column).rename(
        columns={pie_group_column: "cluster_plot"}
    )
    if pie_species_cluster.empty:
        pie_species_grouped = pd.DataFrame(
            columns=["cluster_plot", "Species_grouped", "total_abundance", "n_observations", "n_grids"]
        )
        pie_wide = pd.DataFrame(columns=["cluster_plot"])
    else:
        pie_n_top_species = 4
        top_species = (
            pie_species_cluster.groupby(["Species", "Species_short"], observed=True)["total_abundance"]
            .sum()
            .sort_values(ascending=False)
            .head(pie_n_top_species)
            .index.get_level_values("Species")
        )
        pie_species_cluster["Species_grouped"] = np.where(
            pie_species_cluster["Species"].isin(top_species),
            pie_species_cluster["Species_short"],
            "Other",
        )
        pie_species_grouped = (
            pie_species_cluster.groupby(["cluster_plot", "Species_grouped"], observed=True)
            .agg(
                total_abundance=("total_abundance", "sum"),
                n_observations=("n_observations", "sum"),
                n_grids=("n_grids", "sum"),
            )
            .reset_index()
        )
        pie_wide = pie_species_grouped.pivot(
            index="cluster_plot", columns="Species_grouped", values="total_abundance"
        ).fillna(0).reset_index()
    abundance_with_clusters = abundance.join(cluster_lookup[["community_cluster", "macrocluster"]])
    cluster_composition = abundance_with_clusters.groupby(["community_cluster", "macrocluster"])[abundance.columns].sum().reset_index()
    cluster_composition_long = cluster_composition.melt(
        id_vars=["community_cluster", "macrocluster"], var_name="Species", value_name="abundance"
    )
    cluster_composition_long["cluster_total"] = cluster_composition_long.groupby("community_cluster")["abundance"].transform("sum")
    cluster_composition_long["relative_abundance_pct"] = 100 * cluster_composition_long["abundance"] / cluster_composition_long["cluster_total"].replace(0, np.nan)
    dominant_cluster_species = (
        cluster_composition_long.sort_values(["community_cluster", "abundance"], ascending=[True, False])
        .drop_duplicates("community_cluster")
        .reset_index(drop=True)
    )

    spatial = environment.merge(indices_cells, on="grid_id", how="left").merge(singularity, on="grid_id", how="left").merge(clusters, on="grid_id", how="left")
    spatial = gpd.GeoDataFrame(spatial, geometry="geometry", crs=environment.crs)
    spatial_path = directories["02_intermedios"] / "Community_Biogeography_Analysis.gpkg"
    translate_geodataframe(spatial).to_file(spatial_path, layer="community_cells", driver="GPKG", engine="pyogrio")
    registry.add(spatial_path, "10-19", "GeoPackage of cells with community metrics, LCBD, and clusters")
    pie_centers_table = pd.DataFrame(columns=["cluster_plot", "x", "y", "total_abundance"])
    pie_map_df = pd.DataFrame()
    spatial_pies = spatial.to_crs(4326)
    if not pie_wide.empty and pie_group_column in spatial_pies.columns:
        spatial_pies["cluster_plot"] = spatial_pies[pie_group_column].astype("string")
        spatial_pies = spatial_pies.loc[
            spatial_pies["cluster_plot"].notna()
            & spatial_pies["cluster_plot"].isin(pie_wide["cluster_plot"])
        ].copy()
        if not spatial_pies.empty:
            centers = spatial_pies.dissolve(by="cluster_plot").representative_point()
            pie_centers_table = pd.DataFrame(
                {
                    "cluster_plot": centers.index.astype(str),
                    "x": centers.x.to_numpy(dtype=float),
                    "y": centers.y.to_numpy(dtype=float),
                }
            ).merge(pie_wide, on="cluster_plot", how="left")
            species_columns = [column for column in pie_wide.columns if column != "cluster_plot"]
            pie_centers_table["total_abundance"] = pie_centers_table[species_columns].sum(axis=1)
            pie_map_df = pie_centers_table.loc[pie_centers_table["total_abundance"].gt(0)].copy()

    LOGGER.info("  [2/8 · 7/7] Writing tables, models, and figures")
    tables: dict[str, pd.DataFrame] = {
        "Matriz_abundancia": abundance_export,
        "Matriz_presencia": presence_export,
        "Beta_regional": beta_region,
        "PERMANOVA": pd.DataFrame([perm_result]),
        "Betadisper": pd.DataFrame([dispersion_result]),
        "Betadisper_detalle": dispersion_detail,
        "PERMANOVA_pairwise": pairwise,
        "PERMANOVA_Hellinger": pd.DataFrame([perm_hellinger]),
        "Betadisper_Hellinger": pd.DataFrame([dispersion_hellinger]),
        "Betadisper_Hellinger_detalle": dispersion_hellinger_detail,
        "PERMANOVA_pairwise_Hellinger": pairwise_hellinger,
        "PERMANOVA_Jaccard": pd.DataFrame([perm_jaccard]),
        "Betadisper_Jaccard": pd.DataFrame([dispersion_jaccard]),
        "Betadisper_Jaccard_detalle": dispersion_jaccard_detail,
        "PERMANOVA_pairwise_Jaccard": pairwise_jaccard,
        "PERMANOVA_Bray_sensibilidad": pd.DataFrame([perm_bray]),
        "Betadisper_Bray_sensibilidad": pd.DataFrame([dispersion_bray]),
        "Betadisper_Bray_sensibilidad_detalle": dispersion_bray_detail,
        "PERMANOVA_pairwise_Bray_sensibilidad": pairwise_bray,
        "Ordenacion": ordination,
        "Diagnostico_ordenacion": ordination_diagnostics,
        "Envfit": fitted_environment,
        "IndVal_region": indicators_region,
        "SIMPER_region": simper_region,
        "Indices_celda": indices_cells,
        "Soporte_muestreo_celda": environment.drop(columns="geometry", errors="ignore"),
        "Hotspots": hotspots,
        "Esfuerzo_anual": effort_year,
        "Ocupacion_anual": occupancy_year,
        "Tendencias_ocupacion": occupancy_trends,
        "Coocurrencia": cooccurrence_export,
        "Coocurrencia_matriz": cooccurrence_matrix_export,
        "Distance_decay": distance_pairs,
        "Distance_decay_resumen": pd.DataFrame([decay_summary]),
        "Distance_decay_modelo_lineal": distance_decay_model,
        "Observed_range_weighted_rarity": weighted_endemism,
        "Vulnerabilidad": region_vulnerability,
        "Rareza_vulnerabilidad": vulnerability_species,
        "LCBD": lcbd_table,
        "Rareza_especies": rarity_species,
        "Rareza_celdas": cell_rarity,
        "Singularidad": singularity,
        "Aristas_red": edges,
        "Clusters": clusters,
        "Resumen_clusters": cluster_summary,
        "IndVal_clusters": indicators_cluster,
        "Concordancia_region_cluster": concordance,
        "Concordancia_region_cluster_prop_region": concordance_row,
        "Concordancia_region_cluster_prop_cluster": concordance_column,
        "Concordancia_region_cluster_larga": concordance_long,
        "ARI_region_cluster": ari_table,
        "Cluster_dominante_por_region": dominant_cluster_by_region,
        "Metricas_red": network_metrics,
        "Relative_recorded_detection_classification": core_satellite,
        "Relative_recorded_detection_summary": core_satellite_summary,
        "Gradiente_latitudinal": latitudinal,
        "Modelo_gradiente_latitudinal": latitudinal_model,
        "Coldspots": coldspots,
        "Sensibilidad_umbral_red": threshold_sensitivity,
        "Membership_por_umbral": threshold_membership,
        "Beta_clusters": beta_clusters,
        "Matriz_cluster_species_PA": cluster_species_presence,
        "Beta_clusters_multi": beta_multi_table,
        "Beta_clusters_pair": beta_pair_table,
        "Beta_clusters_component_summary": beta_component_summary,
        "Tamano_clusters_todos": cluster_sizes_all,
        "Tamano_clusters_validos_n2": cluster_sizes_valid,
        "PERMANOVA_clusters": pd.DataFrame([permanova_clusters]),
        "Betadisper_clusters": pd.DataFrame([betadisper_clusters]),
        "Betadisper_clusters_detalle": betadisper_cluster_detail,
        "Betadisper_clusters_resumen": betadisper_cluster_summary,
        "Betadisper_clusters_anova": betadisper_cluster_anova,
        "Betadisper_clusters_permutest": betadisper_cluster_permutest,
        "Composicion_clusters": cluster_composition_long,
        "Dominantes_clusters": dominant_cluster_species,
        "Pie_Composicion_Larga": pie_species_grouped,
        "Pie_Composicion_Ancha": pie_wide,
        "Especies_Cluster_Original_Completa": species_cluster_original,
        "Top10_Cluster_Original": top10_cluster_species,
        "Dominante_Cluster_Original": dominant_cluster_species_original,
        "Especies_Macrocluster_Completa": species_macrocluster,
        "Top10_Macrocluster": top10_macrocluster_species,
        "Dominante_Macrocluster": dominant_macrocluster_species,
        "Centros_PieCharts_Clusters": pie_centers_table,
        "Observacion_Grid_Cluster": obs_cluster_link,
        "Resumen_Grid_Cluster": cluster_link_summary,
    }
    book_path = excel_book(tables, table_dir / "Tables_10_19_Community_LCBD_Biogeography.xlsx")
    registry.add(book_path, "10-19", "Community, singularity, and biogeography workbook")
    for name, frame in tables.items():
        path = csv2(frame, table_dir / f"Table_{name}.csv")
        registry.add(path, "10-19", f"Table {name.replace('_', ' ')}")

    method_note = (
        "COMMUNITY AND BIOGEOGRAPHIC ANALYSIS\n"
        "Matrices: accumulated abundance and presence-absence by cell and species.\n"
        "Observation support: n_sampling_events is the primary observation-intensity proxy; n_records is retained as descriptive data volume.\n"
        "Primary regional contrasts: PERMANOVA/Betadisper with Hellinger-Euclidean (relative composition) and Jaccard (incidence). Raw-abundance Bray-Curtis is retained as a sensitivity analysis.\n"
        "NMDS: Hellinger-Euclidean. PCoA: Bray-Curtis with Lingoes correction when negative eigenvalues occur.\n"
        f"Normalized NMDS stress: {stress:.6f}. PCoA correction: {pcoa_lingoes_diag['correction']}; Lingoes constant={float(pcoa_lingoes_diag['lingoes_constant']):.8g}.\n"
        f"PERMANOVA: {settings.permutations} permutations per contrast; pairwise comparisons use Benjamini-Hochberg adjustment.\n"
        "LCBD: both Jaccard and Hellinger versions are calculated. Raw and BH-FDR adjusted p-values are exported; support of at least two observation events is reported per cell. LCBD magnitude, raw significance, and BH-FDR support are exported as distinct fields; primary hotspot support uses BH-FDR and observation-event support.\n"
        "Distance decay: inference uses a permutation Mantel-Spearman test on distance matrices. Pairwise linear regression is retained only as a descriptor and no conventional p-value is used.\n"
        "Regional IndVal: raw p and BH-FDR adjustment. SIMPER is descriptive.\n"
        "Louvain network: exploratory on Bray-Curtis similarity. Cluster PERMANOVA, Betadisper and IndVal are labelled as non-independent post-hoc characterization, not confirmatory validation.\n"
        f"Effective network threshold: {similarity_threshold:.6f}.\n"
    )
    note_path = text_file(method_note, model_dir / "Methodological_Note_Community_LCBD_Biogeography.txt")
    registry.add(note_path, "10-19", "Community and biogeography methodological note")

    fig, ax = plt.subplots(figsize=(10.5, 7))
    nmds_region_control = _plot_nmds_regions(ax, fig, ordination)
    excluded = ordination.loc[_is_missing_region(ordination["Region_MITECO"])]
    if not excluded.empty:
        nmds_region_control = pd.concat(
            [
                nmds_region_control,
                pd.DataFrame(
                    [
                        {
                            "Region_MITECO": "No data",
                            "n_ordination_points": len(excluded),
                            "centroid_NMDS1": np.nan,
                            "centroid_NMDS2": np.nan,
                            "envelope": "none",
                            "plot_status": "excluded_missing_region",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    control_path = csv2(
        nmds_region_control,
        table_dir / "Table_10_NMDS_Region_Envelope_Control.csv",
    )
    registry.add(control_path, "10", "NMDS regional envelope and centroid control")
    ax.set_title(f"Community NMDS (stress = {stress:.3f})")
    for path in save_figure(fig, figure_dir / "Figure_10_Community_NMDS"):
        registry.add(path, "10", "Community NMDS ordination")

    rank = table.groupby("Species")["N_total"].sum(min_count=1).fillna(0).sort_values(ascending=False).rename("abundance").reset_index()
    rank["rank"] = np.arange(1, len(rank) + 1)
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.plot(rank["rank"], rank["abundance"].clip(lower=np.finfo(float).eps), marker="o", color="#287271")
    ax.set_yscale("log")
    ax.set(xlabel="Rank", ylabel="Total abundance (log)", title="Rank-abundance curve")
    for path in save_figure(fig, figure_dir / "Figure_10_Rank_Abundance"):
        registry.add(path, "10", "Rank-abundance curve")

    plot_spatial = spatial.to_crs(4326)
    lcbd_points = spatial.copy()
    lcbd_points.geometry = lcbd_points.geometry.representative_point()
    lcbd_points = lcbd_points.to_crs(4326)
    fig, ax = plt.subplots(figsize=(10, 8))
    add_map_context(ax, cartographic_context)
    lcbd_values = pd.to_numeric(plot_spatial["LCBD"], errors="coerce").dropna()
    lcbd_ticks = np.linspace(float(lcbd_values.min()), float(lcbd_values.max()), 3)
    lcbd_min, lcbd_max = float(lcbd_values.min()), float(lcbd_values.max())
    plot_spatial.plot(column="LCBD", cmap="magma_r", vmin=lcbd_min, vmax=lcbd_max, legend=True, legend_kwds={"ticks": lcbd_ticks, "format": "%.3g"}, linewidth=0.1, edgecolor="white", ax=ax, zorder=2)
    lcbd_points.plot(column="LCBD", cmap="magma_r", vmin=lcbd_min, vmax=lcbd_max, markersize=56, marker="o", edgecolor="#333333", linewidth=0.35, ax=ax, zorder=3)
    ax.set(title="Local community singularity (LCBD)", xlabel="Longitude", ylabel="Latitude")
    for path in save_figure(fig, figure_dir / "Figure_11_Cell_LCBD"):
        registry.add(path, "11", "LCBD map by cell")

    fig, ax = plt.subplots(figsize=(10, 8))
    add_map_context(ax, cartographic_context)
    cluster_values = sorted(plot_spatial["community_cluster"].dropna().unique().tolist())
    cluster_cmap = plt.get_cmap("tab20", max(len(cluster_values), 1))
    plot_spatial.plot(
        column="community_cluster",
        categorical=True,
        cmap=cluster_cmap,
        legend=False,
        linewidth=0.08,
        edgecolor="white",
        ax=ax,
        zorder=2,
    )
    cluster_handles = [
        Patch(facecolor=cluster_cmap(index), edgecolor="white", label=f"Cluster {value}")
        for index, value in enumerate(cluster_values)
    ]
    if cluster_handles:
        fig.legend(
            handles=cluster_handles,
            title="Community cluster",
            loc="center left",
            bbox_to_anchor=(0.015, 0.5),
            frameon=True,
        )
        fig.subplots_adjust(left=0.22, right=0.98)
    ax.set(title="Biogeographical community clusters", xlabel="Longitude", ylabel="Latitude")
    for path in save_figure(fig, figure_dir / "Figure_18_Biogeographic_Clusters"):
        registry.add(path, "18", "Biogeographical-cluster map")

    # Multivariate dispersion by cluster (R block 18.10).
    # The plotted values are the same distances to the spatial median exported
    # in Betadisper_clusters_detail; the analysis is not recalculated here.
    if not betadisper_cluster_detail.empty:
        plot_dispersion = betadisper_cluster_detail.copy()
        plot_dispersion["community_cluster"] = plot_dispersion["community_cluster"].astype(str)
        cluster_labels_dispersion = list(plot_dispersion["community_cluster"].drop_duplicates())
        dispersion_palette = dict(
            zip(
                cluster_labels_dispersion,
                sns.color_palette("tab20", n_colors=max(len(cluster_labels_dispersion), 1)),
            )
        )
        fig, ax = plt.subplots(figsize=(9, 6))
        sns.boxplot(
            data=plot_dispersion,
            x="community_cluster",
            y="distance_to_centroid",
            hue="community_cluster",
            order=cluster_labels_dispersion,
            hue_order=cluster_labels_dispersion,
            palette=dispersion_palette,
            dodge=False,
            legend=False,
            ax=ax,
        )
        ax.set_title("Multivariate dispersion by biogeographical cluster", pad=24)
        ax.text(
            0.5,
            1.01,
            "Distance to spatial median in Bray–Curtis space",
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=10,
        )
        ax.set_xlabel("Cluster")
        ax.set_ylabel("Distance to spatial median")
        for path in save_figure(fig, figure_dir / "Figure_18_10_Betadisper_Clusters"):
            registry.add(path, "18.10", "Multivariate dispersion by biogeographical cluster")

    # Distance–decay of community similarity (R block 18.12).
    decay_plot = distance_pairs[["distance_km", "similarity"]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(decay_plot) >= 3 and decay_plot["distance_km"].nunique() > 1:
        fig, ax = plt.subplots(figsize=(8.5, 6.5))
        sns.regplot(
            data=decay_plot,
            x="distance_km",
            y="similarity",
            ci=None,  # descriptive line only; cell pairs are not independent
            scatter_kws={"alpha": 0.22, "s": 28, "color": "#287271"},
            line_kws={"color": "#287271", "linewidth": 1.4},
            ax=ax,
        )
        ax.set(
            title="Distance–decay of community similarity",
            xlabel="Geographic distance (km)",
            ylabel="Normalised Hellinger similarity",
        )
        for path in save_figure(fig, figure_dir / "Figure_18_12_Distance_Decay_Similarity"):
            registry.add(path, "18.12", "Distance–decay of community similarity")

    # Concordance between MITECO regions and clusters (R block 18.14).
    if not concordance_long.empty:
        concordance_values = concordance_long.pivot(
            index="Region_MITECO", columns="community_cluster", values="prop_within_region"
        )
        concordance_counts = concordance_long.pivot(
            index="Region_MITECO", columns="community_cluster", values="n_cells"
        ).fillna(0)
        fig, ax = plt.subplots(figsize=(10, 7))
        sns.heatmap(
            concordance_values,
            cmap=sns.light_palette("#F0BC7A", as_cmap=True),
            annot=concordance_counts,
            fmt=".0f",
            linewidths=0.3,
            linecolor="white",
            cbar_kws={"label": "Proportion within region"},
            ax=ax,
        )
        ax.set_title("Concordance between MITECO regions and biogeographical clusters", pad=24)
        ax.text(
            0.5,
            1.01,
            "Numbers = cells per combination | Colour = proportion within each region",
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=10,
        )
        ax.set_xlabel("Biogeographical cluster")
        ax.set_ylabel("MITECO region")
        for path in save_figure(fig, figure_dir / "Figure_18_14_Region_Cluster_Concordance"):
            registry.add(path, "18.14", "Concordance between MITECO regions and biogeographical clusters")

    # Cluster-composition pie charts (size proportional to total abundance).
    # Centres and values come from the exported tables; no community analysis
    # is recalculated here.
    if not pie_map_df.empty:
        pie_species_columns = [
            column
            for column in pie_map_df.columns
            if column not in {"cluster_plot", "x", "y", "total_abundance"}
        ]
        if pie_species_columns:
            pie_palette = dict(
                zip(
                    pie_species_columns,
                    sns.color_palette("tab10", n_colors=max(len(pie_species_columns), 1)),
                )
            )
            pie_cluster_values = sorted(pie_map_df["cluster_plot"].astype(str).unique().tolist())
            pie_cluster_cmap = plt.get_cmap("tab20", max(len(pie_cluster_values), 1))
            cluster_handles = [
                Patch(facecolor=pie_cluster_cmap(index), edgecolor="white", label=f"Macrocluster {value}")
                for index, value in enumerate(pie_cluster_values)
            ]
            pie_max_total = float(pie_map_df["total_abundance"].max())
            fig, ax = plt.subplots(figsize=(10, 8))
            add_map_context(ax, cartographic_context)
            spatial_pies.plot(
                column="cluster_plot",
                categorical=True,
                cmap=pie_cluster_cmap,
                legend=False,
                linewidth=0.08,
                edgecolor="white",
                ax=ax,
                zorder=1,
            )
            for _, pie_row in pie_map_df.iterrows():
                total = float(pie_row["total_abundance"])
                if not np.isfinite(total) or total <= 0:
                    continue
                radius = 0.16 + 0.34 * np.sqrt(total / max(pie_max_total, np.finfo(float).eps))
                start_angle = 90.0
                for species in pie_species_columns:
                    value = pd.to_numeric(pie_row[species], errors="coerce")
                    value = 0.0 if pd.isna(value) else float(value)
                    if value <= 0:
                        continue
                    end_angle = start_angle + 360.0 * value / total
                    ax.add_patch(
                        Wedge(
                            (float(pie_row["x"]), float(pie_row["y"])),
                            radius,
                            start_angle,
                            end_angle,
                            facecolor=pie_palette[species],
                            edgecolor="white",
                            linewidth=0.4,
                            zorder=4,
                        )
                    )
                    start_angle = end_angle
            species_handles = [
                Patch(facecolor=pie_palette[species], edgecolor="white", label=species)
                for species in pie_species_columns
            ]
            # Fixed layout: map on the left and a dedicated legend column on the right.
            fig.set_size_inches(11.5, 8.0, forward=True)
            fig.subplots_adjust(left=0.08, right=0.72, bottom=0.09, top=0.82)
            legend_ax = fig.add_axes([0.75, 0.10, 0.23, 0.70])
            legend_ax.set_axis_off()
            if cluster_handles:
                cluster_legend = legend_ax.legend(
                    handles=cluster_handles,
                    title="Macroclusters",
                    loc="upper left",
                    bbox_to_anchor=(0.0, 1.0),
                    borderaxespad=0.0,
                    frameon=True,
                    fontsize=9,
                    title_fontsize=10,
                )
                legend_ax.add_artist(cluster_legend)
            if species_handles:
                legend_ax.legend(
                    handles=species_handles,
                    title="Main species",
                    loc="upper left",
                    bbox_to_anchor=(0.0, 0.47),
                    borderaxespad=0.0,
                    frameon=True,
                    fontsize=9,
                    title_fontsize=10,
                )
            ax.set(xlabel="Longitude", ylabel="Latitude")
            fig.suptitle(
                "Macrocluster map with composition of the main species",
                y=0.965,
                fontsize=13,
            )
            fig.text(
                0.40,
                0.905,
                "Pie-chart size is proportional to total abundance",
                ha="center",
                va="top",
                fontsize=10,
            )
            for path in save_figure(fig, figure_dir / "Figure_18_17_Macrocluster_Map_PieCharts_TopSpecies"):
                registry.add(path, "18.17", "Macrocluster map with proportional composition pie charts")

            # Fixed-size comparison variant: it keeps exactly the same
            # composition (top 4 + Other) and changes only the radius.
            fixed_radius = 0.28
            fig, ax = plt.subplots(figsize=(10, 8))
            add_map_context(ax, cartographic_context)
            spatial_pies.plot(
                column="cluster_plot",
                categorical=True,
                cmap=pie_cluster_cmap,
                legend=False,
                linewidth=0.08,
                edgecolor="white",
                ax=ax,
                zorder=1,
            )
            for _, pie_row in pie_map_df.iterrows():
                total = float(pie_row["total_abundance"])
                if not np.isfinite(total) or total <= 0:
                    continue
                start_angle = 90.0
                for species in pie_species_columns:
                    value = pd.to_numeric(pie_row[species], errors="coerce")
                    value = 0.0 if pd.isna(value) else float(value)
                    if value <= 0:
                        continue
                    end_angle = start_angle + 360.0 * value / total
                    ax.add_patch(
                        Wedge(
                            (float(pie_row["x"]), float(pie_row["y"])),
                            fixed_radius,
                            start_angle,
                            end_angle,
                            facecolor=pie_palette[species],
                            edgecolor="white",
                            linewidth=0.4,
                            zorder=4,
                        )
                    )
                    start_angle = end_angle
            # Same layout as Figure 18.17: map on the left and aligned legends on the right.
            fig.set_size_inches(11.5, 8.0, forward=True)
            fig.subplots_adjust(left=0.08, right=0.72, bottom=0.09, top=0.82)
            legend_ax = fig.add_axes([0.75, 0.10, 0.23, 0.70])
            legend_ax.set_axis_off()
            if cluster_handles:
                cluster_legend = legend_ax.legend(
                    handles=cluster_handles,
                    title="Macroclusters",
                    loc="upper left",
                    bbox_to_anchor=(0.0, 1.0),
                    borderaxespad=0.0,
                    frameon=True,
                    fontsize=9,
                    title_fontsize=10,
                )
                legend_ax.add_artist(cluster_legend)
            if species_handles:
                legend_ax.legend(
                    handles=species_handles,
                    title="Main species",
                    loc="upper left",
                    bbox_to_anchor=(0.0, 0.47),
                    borderaxespad=0.0,
                    frameon=True,
                    fontsize=9,
                    title_fontsize=10,
                )
            ax.set(xlabel="Longitude", ylabel="Latitude")
            fig.suptitle(
                "Macrocluster map with fixed-size pie charts",
                y=0.965,
                fontsize=13,
            )
            fig.text(
                0.40,
                0.905,
                "All pie charts have the same size; composition shows relative abundance",
                ha="center",
                va="top",
                fontsize=10,
            )
            for path in save_figure(fig, figure_dir / "Figure_18_18_Macrocluster_Map_PieCharts_FixedSize"):
                registry.add(path, "18.18", "Macrocluster map with fixed-size composition pie charts")

    if not indicators_region.empty:
        top = indicators_region.head(20).copy()
        fig, ax = plt.subplots(figsize=(9, max(5, 0.35 * len(top))))
        sns.barplot(data=top, x="IndVal", y="Species", hue="indicator_group", dodge=False, ax=ax)
        ax.set(title="Indicator species by region", xlabel="IndVal", ylabel="Species")
        ax.legend(title="Group", bbox_to_anchor=(1.02, 1), loc="upper left")
        for path in save_figure(fig, figure_dir / "Figure_13_Indicator_Species"):
            registry.add(path, "13", "Indicator species by region")

    fig, ax = plt.subplots(figsize=(9, 6))
    sns.scatterplot(data=singularity, x="LCBD", y="mean_rarity", hue="hotspot_uniqueness", palette={False: "#9aa0a6", True: "#d73027"}, ax=ax)
    ax.set(title="Integrated singularity: LCBD and rarity", xlabel="LCBD", ylabel="Mean rarity")
    for path in save_figure(fig, figure_dir / "Figure_15_LCBD_Rarity"):
        registry.add(path, "15", "Relationship between LCBD and mean rarity")

    fig, ax = plt.subplots(figsize=(9, 6))
    sns.scatterplot(
        data=core_satellite,
        x="occupancy",
        y="mean_abundance_occupied_cells",
        hue="occupancy_class_display",
        palette={"High occupancy": "#d95f02", "Intermediate occupancy": "#7570b3", "Low occupancy": "#1b9e77"},
        s=75,
        ax=ax,
    )
    ax.set_yscale("log")
    for _, row in core_satellite.iterrows():
        ax.annotate(str(row["Species"]), (row["occupancy"], row["mean_abundance_occupied_cells"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set(title="Occupancy–abundance relationship", xlabel="Proportion of occupied cells", ylabel="Mean abundance in occupied cells (log)")
    for path in save_figure(fig, figure_dir / "Figure_14_Core_Satellite"):
        registry.add(path, "14", "Relative occupancy classification")

    fig, ax = plt.subplots(figsize=(8, 5.5))
    sns.regplot(data=valid_latitude, x="latitude", y="richness", scatter_kws={"s": 25, "alpha": 0.6}, line_kws={"color": "#d73027"}, ax=ax)
    ax.set(title="Latitudinal richness gradient", xlabel="Latitude", ylabel="Richness per cell")
    for path in save_figure(fig, figure_dir / "Figure_11_Latitudinal_Gradient"):
        registry.add(path, "11", "Latitudinal richness gradient")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    sns.lineplot(data=threshold_sensitivity, x="threshold_quantile", y="n_clusters", marker="o", ax=axes[0], color="#2a9d8f")
    sns.lineplot(data=threshold_sensitivity, x="threshold_quantile", y="modularity", marker="o", ax=axes[1], color="#e76f51")
    axes[0].set(title="Number of clusters", xlabel="Similarity percentile", ylabel="Clusters")
    axes[1].set(title="Modularity", xlabel="Similarity percentile", ylabel="Modularity")
    fig.suptitle("Clustering sensitivity to the network threshold")
    for path in save_figure(fig, figure_dir / "Figure_18_Network_Threshold_Sensitivity"):
        registry.add(path, "18", "Sensitivity of clusters and modularity to the threshold")

    # Separate versions equivalent to R's two threshold-sensitivity figures.
    if {"threshold_quantile", "n_clusters", "modularity"}.issubset(threshold_sensitivity.columns):
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.lineplot(
            data=threshold_sensitivity,
            x="threshold_quantile",
            y="n_clusters",
            marker="o",
            color="#2a9d8f",
            ax=ax,
        )
        ax.set(
            title="Sensitivity of the number of clusters to the threshold",
            xlabel="Similarity percentile",
            ylabel="Number of clusters",
        )
        for path in save_figure(fig, figure_dir / "Figure_18_11_Threshold_Sensitivity_Number_Clusters"):
            registry.add(path, "18.11", "Sensitivity of the number of clusters to the threshold")

        fig, ax = plt.subplots(figsize=(8, 6))
        sns.lineplot(
            data=threshold_sensitivity,
            x="threshold_quantile",
            y="modularity",
            marker="o",
            color="#e76f51",
            ax=ax,
        )
        ax.set(
            title="Sensitivity of modularity to the threshold",
            xlabel="Similarity percentile",
            ylabel="Modularity",
        )
        for path in save_figure(fig, figure_dir / "Figure_18_11_Threshold_Sensitivity_Modularity"):
            registry.add(path, "18.11", "Sensitivity of modularity to the threshold")

    cluster_heat = cluster_composition_long.pivot(index="Species", columns="community_cluster", values="relative_abundance_pct").fillna(0).astype(float)
    fig, ax = plt.subplots(figsize=(max(9, 0.8 * cluster_heat.shape[1]), max(6, 0.42 * cluster_heat.shape[0])))
    sns.heatmap(cluster_heat, cmap="viridis_r", ax=ax, cbar_kws={"label": "% of cluster abundance"})
    ax.set(title="Species composition by biogeographical cluster", xlabel="Cluster", ylabel="Species")
    for path in save_figure(fig, figure_dir / "Figure_18_Cluster_Composition"):
        registry.add(path, "18", "Percentage composition by biogeographical cluster")

    # Figure equivalent to R's Figura_Top_Especies_por_Macrocluster in block
    # 18.18. It uses only the already calculated Top10 table.
    if not top10_macrocluster_species.empty:
        dominance_plot = top10_macrocluster_species.copy()
        dominance_plot["macro_cluster_plot"] = dominance_plot["macro_cluster"].astype(str)
        dominance_groups = sorted(dominance_plot["macro_cluster_plot"].dropna().unique().tolist())
        if dominance_groups:
            ncols = min(3, len(dominance_groups))
            nrows = int(np.ceil(len(dominance_groups) / ncols))
            fig, axes = plt.subplots(
                nrows,
                ncols,
                figsize=(12, max(5.5, 3.2 * nrows)),
                squeeze=False,
            )
            axes_flat = axes.ravel()
            dominance_cmap = plt.get_cmap("tab20", max(len(dominance_groups), 1))
            for index, group in enumerate(dominance_groups):
                axis = axes_flat[index]
                group_rows = dominance_plot.loc[
                    dominance_plot["macro_cluster_plot"].eq(group)
                ].sort_values("total_abundance", kind="stable")
                axis.barh(
                    group_rows["Species_short"].astype(str),
                    group_rows["total_abundance"].astype(float),
                    color=dominance_cmap(index),
                    edgecolor="#4a4a4a",
                    linewidth=0.5,
                )
                axis.set_title(f"Macrocluster {group}")
                axis.set_xlabel("Total abundance")
                axis.set_ylabel("Species")
            for axis in axes_flat[len(dominance_groups):]:
                axis.axis("off")
            fig.suptitle("Top dominant species by biogeographical macrocluster")
            fig.tight_layout(rect=(0, 0, 1, 0.96))
            for path in save_figure(fig, figure_dir / "Figure_Top_Species_by_Macrocluster"):
                registry.add(path, "18.18", "Top dominant species by biogeographical macrocluster")

    LOGGER.info("[2/8] Community, beta diversity, LCBD, and biogeography: complete")
    return {
        "abundance_matrix": abundance,
        "presence_matrix": presence,
        "environment_grid": environment,
        "community_spatial": spatial,
        "indices_cells": indices_cells,
        "hotspots": hotspots,
        "lcbd": lcbd_table,
        "singularity": singularity,
        "clusters": clusters,
        "cluster_summary": cluster_summary,
        "ordination": ordination,
        "nmds_region_control": nmds_region_control,
        "permanova": perm_result,
        "betadisper": dispersion_result,
        "permanova_hellinger": perm_hellinger,
        "betadisper_hellinger": dispersion_hellinger,
        "permanova_jaccard": perm_jaccard,
        "betadisper_jaccard": dispersion_jaccard,
        "permanova_bray_sensitivity": perm_bray,
        "betadisper_bray_sensitivity": dispersion_bray,
        "pcoa_lingoes_diagnostics": pcoa_lingoes_diag,
        "network_metrics": network_metrics,
        "core_satellite": core_satellite,
        "coldspots": coldspots,
        "threshold_sensitivity": threshold_sensitivity,
        "beta_clusters": beta_clusters,
        "cluster_species_presence": cluster_species_presence,
        "beta_clusters_multi": beta_multi_table,
        "beta_clusters_pair": beta_pair_table,
        "beta_clusters_component_summary": beta_component_summary,
        "species_cluster_original": species_cluster_original,
        "species_macrocluster": species_macrocluster,
        "top10_cluster_species": top10_cluster_species,
        "top10_macrocluster_species": top10_macrocluster_species,
        "dominant_macrocluster_species": dominant_macrocluster_species,
        "dominant_cluster_species_original": dominant_cluster_species_original,
        "observation_grid_cluster": obs_cluster_link,
        "grid_cluster_summary": cluster_link_summary,
        "permanova_clusters": permanova_clusters,
        "betadisper_clusters": betadisper_clusters,
        "betadisper_cluster_detail": betadisper_cluster_detail,
        "betadisper_cluster_summary": betadisper_cluster_summary,
        "betadisper_cluster_anova": betadisper_cluster_anova,
        "betadisper_cluster_permutest": betadisper_cluster_permutest,
        "indicators_region": indicators_region,
        "simper_region": simper_region,
        "indicators_cluster": indicators_cluster,
        "distance_decay_summary": decay_summary,
    }
