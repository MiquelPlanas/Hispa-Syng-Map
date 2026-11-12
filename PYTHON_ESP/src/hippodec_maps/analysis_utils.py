"""Utilidades estadísticas reproducibles para los bloques analíticos.

Las implementaciones evitan dependencias científicas poco habituales y hacen
explícitas las fórmulas. Cada permutación recibe una semilla.
"""

from __future__ import annotations

import math
import inspect
import itertools
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import pdist, squareform
from sklearn.manifold import MDS


EPS = np.finfo(float).eps


def numeric(series: pd.Series, fill: float | None = None) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce")
    return out.fillna(fill) if fill is not None else out


def safe_divide(numerator: object, denominator: object) -> np.ndarray:
    num = np.asarray(numerator, dtype=float)
    den = np.asarray(denominator, dtype=float)
    out = np.full(np.broadcast_shapes(num.shape, den.shape), np.nan, dtype=float)
    np.divide(num, den, out=out, where=np.isfinite(den) & (den != 0))
    return out


def rescale(values: Iterable[float], low: float = 0.0, high: float = 1.0) -> np.ndarray:
    # pandas 3 usa pd.NA en sus dtypes anulables; convertir mediante Series evita
    # que np.asarray(..., dtype=float) falle ante esos valores.
    arr = pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(
        dtype=float, na_value=np.nan
    )
    out = np.full(arr.shape, np.nan, dtype=float)
    valid = np.isfinite(arr)
    if not valid.any():
        return out
    minimum = float(np.min(arr[valid]))
    maximum = float(np.max(arr[valid]))
    if math.isclose(minimum, maximum):
        out[valid] = (low + high) / 2.0
    else:
        out[valid] = low + (arr[valid] - minimum) * (high - low) / (maximum - minimum)
        # Evita residuos de coma flotante como 100.00000000000001, que no
        # cambian el resultado científico pero sí pueden hacer fallar el
        # Control estricto del intervalo de prioridad.
        out[valid] = np.clip(out[valid], min(low, high), max(low, high))
    return out


def shannon(values: Iterable[float]) -> float:
    x = np.asarray(list(values), dtype=float)
    x = x[np.isfinite(x) & (x > 0)]
    if x.size == 0:
        return 0.0
    p = x / x.sum()
    return float(-(p * np.log(p)).sum())


def simpson(values: Iterable[float]) -> float:
    x = np.asarray(list(values), dtype=float)
    x = x[np.isfinite(x) & (x > 0)]
    if x.size == 0:
        return 0.0
    p = x / x.sum()
    return float(1.0 - np.square(p).sum())


def community_indices(matrix: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    for name, row in matrix.iterrows():
        x = np.asarray(row, dtype=float)
        richness = int(np.count_nonzero(x > 0))
        h = shannon(x)
        rows.append(
            {
                "id": str(name),
                "richness": richness,
                "abundance": float(np.nansum(x)),
                "shannon": h,
                "simpson": simpson(x),
                "pielou": h / math.log(richness) if richness > 1 else 0.0,
            }
        )
    return pd.DataFrame(rows).set_index("id")


def hellinger(matrix: np.ndarray) -> np.ndarray:
    x = np.asarray(matrix, dtype=float)
    totals = x.sum(axis=1, keepdims=True)
    relative = np.divide(x, totals, out=np.zeros_like(x), where=totals > 0)
    return np.sqrt(relative)


def bray_curtis_matrix(matrix: np.ndarray) -> np.ndarray:
    x = np.asarray(matrix, dtype=float)
    if len(x) < 2:
        return np.zeros((len(x), len(x)), dtype=float)
    distances = squareform(pdist(x, metric="braycurtis"))
    return np.nan_to_num(distances, nan=0.0, posinf=0.0, neginf=0.0)


def euclidean_matrix(matrix: np.ndarray) -> np.ndarray:
    """Matriz de distancias euclídeas, incluido el caso de una sola fila."""
    x = np.asarray(matrix, dtype=float)
    if len(x) < 2:
        return np.zeros((len(x), len(x)), dtype=float)
    return squareform(pdist(x, metric="euclidean"))


def jaccard_matrix(matrix: np.ndarray) -> np.ndarray:
    x = np.asarray(matrix, dtype=float) > 0
    if len(x) < 2:
        return np.zeros((len(x), len(x)), dtype=float)
    distances = squareform(pdist(x, metric="jaccard"))
    return np.nan_to_num(distances, nan=0.0)


def pcoa(distance: np.ndarray, dimensions: int = 2) -> tuple[np.ndarray, np.ndarray]:
    d = np.asarray(distance, dtype=float)
    n = d.shape[0]
    if n == 0:
        return np.empty((0, dimensions)), np.empty(0)
    centering = np.eye(n) - np.ones((n, n)) / n
    gower = -0.5 * centering @ np.square(d) @ centering
    eigenvalues, eigenvectors = np.linalg.eigh(gower)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    positive = eigenvalues > EPS
    vals = eigenvalues[positive][:dimensions]
    vecs = eigenvectors[:, positive][:, :dimensions]
    coords = vecs * np.sqrt(vals) if vals.size else np.empty((n, 0))
    if coords.shape[1] < dimensions:
        coords = np.pad(coords, ((0, 0), (0, dimensions - coords.shape[1])))
    return coords, eigenvalues


def pcoa_lingoes(
    distance: np.ndarray,
    dimensions: int = 2,
) -> tuple[np.ndarray, np.ndarray, dict[str, float | str]]:
    """PCoA with a Lingoes correction when the distance is non-Euclidean.

    The correction adds ``2*c`` to squared off-diagonal distances, where
    ``c`` is the absolute value of the most negative eigenvalue of the
    uncorrected principal-coordinate matrix. The diagonal remains zero.
    """
    d = np.asarray(distance, dtype=float)
    if d.ndim != 2 or d.shape[0] != d.shape[1]:
        raise ValueError("Distance matrix must be square.")
    _, eigen_before = pcoa(d, dimensions=max(dimensions, 1))
    positive_before = eigen_before[eigen_before > EPS]
    negative_before = eigen_before[eigen_before < -EPS]
    minimum_before = float(np.min(eigen_before)) if eigen_before.size else 0.0
    constant = max(0.0, -minimum_before)
    if constant > EPS and len(d):
        adjusted_sq = np.square(d) + 2.0 * constant
        np.fill_diagonal(adjusted_sq, 0.0)
        adjusted = np.sqrt(np.maximum(adjusted_sq, 0.0))
        np.fill_diagonal(adjusted, 0.0)
        coordinates, eigen_after = pcoa(adjusted, dimensions=dimensions)
        correction = "lingoes"
    else:
        coordinates, eigen_after = pcoa(d, dimensions=dimensions)
        correction = "none"
    positive_sum = float(np.sum(positive_before))
    negative_abs_sum = float(np.sum(np.abs(negative_before)))
    diagnostics: dict[str, float | str] = {
        "correction": correction,
        "lingoes_constant": float(constant),
        "min_eigenvalue_before": minimum_before,
        "min_eigenvalue_after": float(np.min(eigen_after)) if eigen_after.size else 0.0,
        "positive_eigen_sum_before": positive_sum,
        "negative_eigen_abs_sum_before": negative_abs_sum,
        "negative_to_positive_pct_before": (
            100.0 * negative_abs_sum / positive_sum if positive_sum > EPS else np.nan
        ),
    }
    return coordinates, eigen_after, diagnostics


def mantel_spearman(
    first_distance: np.ndarray,
    second_distance: np.ndarray,
    permutations: int,
    seed: int,
) -> dict[str, float | int | str]:
    """Two-sided Mantel test using Spearman correlation of upper triangles."""
    first = np.asarray(first_distance, dtype=float)
    second = np.asarray(second_distance, dtype=float)
    if first.shape != second.shape or first.ndim != 2 or first.shape[0] != first.shape[1]:
        raise ValueError("Mantel distance matrices must be square and have identical shape.")
    n = first.shape[0]
    upper = np.triu_indices(n, 1)
    x = first[upper]
    y = second[upper]
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    result: dict[str, float | int | str] = {
        "method": "Mantel Spearman",
        "mantel_rho": np.nan,
        "mantel_p_value": np.nan,
        "permutations": int(permutations),
        "n_objects": int(n),
        "n_pairs": int(valid.sum()),
    }
    if n < 3 or x.size < 3 or np.unique(x).size < 2 or np.unique(y).size < 2:
        return result
    observed = float(stats.spearmanr(x, y).statistic)
    if not np.isfinite(observed):
        return result
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(int(permutations)):
        order = rng.permutation(n)
        permuted = second[np.ix_(order, order)][upper]
        permuted = permuted[valid]
        rho = float(stats.spearmanr(x, permuted).statistic)
        if np.isfinite(rho) and abs(rho) >= abs(observed) - EPS:
            exceed += 1
    result["mantel_rho"] = observed
    result["mantel_p_value"] = float((exceed + 1) / (int(permutations) + 1))
    return result


def nmds(distance: np.ndarray, seed: int, max_iter: int = 500) -> tuple[np.ndarray, float]:
    d = np.asarray(distance, dtype=float)
    if len(d) < 3 or np.allclose(d, 0):
        return np.zeros((len(d), 2)), 0.0
    signature = inspect.signature(MDS).parameters
    common = {
        "n_components": 2,
        "random_state": seed,
        "n_init": 4,
        "max_iter": max_iter,
        "eps": 1e-6,
        "normalized_stress": "auto",
    }
    if "init" in signature:
        common["init"] = "random"
    if "metric_mds" in signature:
        model = MDS(metric_mds=False, metric="precomputed", **common)
    else:
        model = MDS(metric=False, dissimilarity="precomputed", **common)
    coordinates = model.fit_transform(d)
    return coordinates, float(model.stress_)


def _pseudo_f_from_squared_distance(
    squared_distance: np.ndarray,
    groups: np.ndarray,
) -> tuple[float, float, float, int, int]:
    """Calcula pseudo-F sin reconstruir matrices de proyección densas.

    La formulación por sumas de cuadrados dentro de grupos es algebraicamente
    equivalente a ``trace(H @ G)``. Evita crear y multiplicar dos matrices
    ``n × n`` en cada permutación, que era el principal cuello de botella con
    la malla de 1 km.
    """
    d2 = np.asarray(squared_distance, dtype=float)
    labels = np.asarray(groups)
    n = len(labels)
    unique = pd.unique(labels)
    k = len(unique)
    if n <= k or k < 2:
        return np.nan, np.nan, np.nan, max(k - 1, 0), max(n - k, 0)
    ss_total = float(d2.sum()) / (2.0 * n)
    ss_within = 0.0
    for group in unique:
        indices = np.flatnonzero(labels == group)
        ss_within += float(d2[np.ix_(indices, indices)].sum()) / (
            2.0 * len(indices)
        )
    ss_within = max(ss_within, 0.0)
    # Bray-Curtis is not always Euclidean; in those cases the projection
    # formulation can legitimately yield a small negative between-group sum.
    # Do not clip it, so the result remains identical to the previous method.
    ss_between = ss_total - ss_within
    df_between, df_within = k - 1, n - k
    statistic = (ss_between / df_between) / max(ss_within / df_within, EPS)
    return statistic, ss_between, ss_within, df_between, df_within


def _pseudo_f(distance: np.ndarray, groups: np.ndarray) -> tuple[float, float, float, int, int]:
    d = np.asarray(distance, dtype=float)
    return _pseudo_f_from_squared_distance(np.square(d), groups)


def permanova(
    distance: np.ndarray,
    groups: Iterable[object],
    permutations: int,
    seed: int,
) -> dict[str, float | int]:
    labels = np.asarray(list(groups))
    squared_distance = np.square(np.asarray(distance, dtype=float))
    observed, ss_b, ss_w, df_b, df_w = _pseudo_f_from_squared_distance(
        squared_distance, labels
    )
    if not np.isfinite(observed):
        return {
            "pseudo_F": np.nan,
            "p_value": np.nan,
            "R2": np.nan,
            "permutations": permutations,
            "df_between": df_b,
            "df_within": df_w,
        }
    rng = np.random.default_rng(seed)
    permuted = np.empty(permutations, dtype=float)
    for index in range(permutations):
        permuted[index] = _pseudo_f_from_squared_distance(
            squared_distance, rng.permutation(labels)
        )[0]
    p_value = (1.0 + np.count_nonzero(permuted >= observed - EPS)) / (permutations + 1.0)
    return {
        "pseudo_F": observed,
        "p_value": float(p_value),
        "R2": float(ss_b / max(ss_b + ss_w, EPS)),
        "permutations": permutations,
        "df_between": df_b,
        "df_within": df_w,
    }


def pairwise_permanova(
    distance: np.ndarray,
    groups: Iterable[object],
    permutations: int,
    seed: int,
) -> pd.DataFrame:
    labels = np.asarray(list(groups))
    unique = sorted(pd.unique(labels), key=str)
    rows: list[dict[str, object]] = []
    counter = 0
    for i, first in enumerate(unique):
        for second in unique[i + 1 :]:
            keep = np.isin(labels, [first, second])
            result = permanova(
                distance[np.ix_(keep, keep)], labels[keep], permutations, seed + counter
            )
            counter += 1
            rows.append({"group_1": first, "group_2": second, **result})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["p_adjust_BH"] = stats.false_discovery_control(
            out["p_value"].fillna(1).to_numpy(), method="bh"
        )
    return out


def _betadisper_pcoa(distance: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Coordenadas PCoA completas para reproducir ``vegan::betadisper``.

    A diferencia de :func:`pcoa`, esta representación conserva todos los ejes
    positivos y negativos distintos de cero. Los ejes negativos se escalan por
    la raíz del valor absoluto de su autovalor y se identifican con la máscara
    booleana devuelta.
    """
    d = np.asarray(distance, dtype=float)
    if d.ndim != 2 or d.shape[0] != d.shape[1]:
        raise ValueError("La matriz de distancias debe ser cuadrada.")
    n = d.shape[0]
    if n == 0:
        return np.empty((0, 0), dtype=float), np.empty(0, dtype=bool)

    centering = np.eye(n) - np.ones((n, n)) / n
    gower = -0.5 * centering @ np.square(d) @ centering
    eigenvalues, eigenvectors = np.linalg.eigh(gower)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    tolerance = math.sqrt(EPS)
    leading = float(eigenvalues[0]) if eigenvalues.size else 0.0
    keep = np.abs(eigenvalues) > max(tolerance, tolerance * leading)
    kept_values = eigenvalues[keep]
    coordinates = eigenvectors[:, keep] * np.sqrt(np.abs(kept_values))
    return coordinates, kept_values > 0


def _spatial_median(points: np.ndarray, max_iter: int = 1000) -> np.ndarray:
    """Mediana espacial no ponderada mediante Weiszfeld modificado.

    Minimiza la suma de distancias euclídeas, que es el mismo objetivo usado
    por ``vegan::ordimedian``. La modificación evita divisiones por cero cuando
    el estimador coincide exactamente con una observación.
    """
    values = np.asarray(points, dtype=float)
    if values.ndim != 2:
        raise ValueError("Las coordenadas deben formar una matriz bidimensional.")
    if values.shape[1] == 0:
        return np.empty(0, dtype=float)
    if len(values) == 0:
        return np.full(values.shape[1], np.nan, dtype=float)
    if len(values) == 1 or np.allclose(values, values[0], rtol=0.0, atol=EPS):
        return values[0].copy()

    centre = np.median(values, axis=0)
    tolerance = math.sqrt(EPS)
    scale = max(1.0, float(np.max(np.linalg.norm(values, axis=1))))

    for _ in range(max_iter):
        offsets = values - centre
        distances = np.linalg.norm(offsets, axis=1)
        coincident = distances <= tolerance * scale
        remaining = ~coincident
        if not remaining.any():
            return centre

        inverse = 1.0 / distances[remaining]
        weighted = np.sum(values[remaining] * inverse[:, None], axis=0) / np.sum(inverse)

        if coincident.any():
            residual = np.sum(offsets[remaining] / distances[remaining, None], axis=0)
            residual_norm = float(np.linalg.norm(residual))
            multiplicity = int(np.count_nonzero(coincident))
            if residual_norm <= multiplicity:
                candidate = centre
            else:
                ratio = multiplicity / residual_norm
                candidate = (1.0 - ratio) * weighted + ratio * centre
        else:
            candidate = weighted

        if np.linalg.norm(candidate - centre) <= tolerance * max(scale, np.linalg.norm(centre)):
            return candidate
        centre = candidate

    return centre


def _distances_to_spatial_medians(
    coordinates: np.ndarray,
    positive_axes: np.ndarray,
    groups: np.ndarray,
) -> np.ndarray:
    """Distancias a medianas de grupo con corrección de ejes PCoA negativos."""
    result = np.zeros(len(groups), dtype=float)
    for group in pd.unique(groups):
        idx = np.where(groups == group)[0]
        group_coordinates = coordinates[idx]

        positive = group_coordinates[:, positive_axes]
        positive_centre = _spatial_median(positive)
        positive_squared = np.square(positive - positive_centre).sum(axis=1)

        negative = group_coordinates[:, ~positive_axes]
        negative_centre = _spatial_median(negative)
        negative_squared = np.square(negative - negative_centre).sum(axis=1)

        result[idx] = np.sqrt(np.maximum(positive_squared - negative_squared, 0.0))
    return result


def _betadisper_residual_permutations(
    distances: np.ndarray,
    groups: np.ndarray,
    permutations: int,
    seed: int,
) -> np.ndarray:
    """Estadísticos F permutando residuos del modelo de un factor.

    Es la forma equivalente, para un factor categórico, al procedimiento de
    ``vegan::permutest.betadisper``. Los centros y las distancias observadas no
    se recalculan durante las permutaciones.
    """
    values = np.asarray(distances, dtype=float)
    labels, codes = np.unique(groups, return_inverse=True)
    n_groups = len(labels)
    if permutations <= 0 or n_groups < 2 or len(values) <= n_groups:
        return np.empty(0, dtype=float)

    counts = np.bincount(codes, minlength=n_groups).astype(float)
    group_means = np.bincount(codes, weights=values, minlength=n_groups) / counts
    residuals = values - group_means[codes]
    residual_df = len(values) - n_groups
    if residual_df <= 0:
        return np.empty(0, dtype=float)

    rng = np.random.default_rng(seed)
    statistics: list[float] = []
    for _ in range(permutations):
        permuted_residuals = residuals[rng.permutation(len(values))]
        fitted = np.bincount(
            codes, weights=permuted_residuals, minlength=n_groups
        ) / counts
        fitted_values = fitted[codes]
        model_ss = float(np.square(fitted_values - fitted_values.mean()).sum())
        residual_ss = float(np.square(permuted_residuals - fitted_values).sum())
        if residual_ss <= EPS:
            statistics.append(np.nan)
        else:
            statistics.append(
                (model_ss / (n_groups - 1)) / (residual_ss / residual_df)
            )
    return np.asarray(statistics, dtype=float)


def betadisper_anova_table(
    distances: np.ndarray, groups: Iterable[object]
) -> pd.DataFrame:
    """Tabla ANOVA paramétrica equivalente a ``anova.betadisper``."""
    values = np.asarray(distances, dtype=float)
    labels, codes = np.unique(np.asarray(list(groups)), return_inverse=True)
    n_groups = len(labels)
    columns = ["term", "Df", "Sum Sq", "Mean Sq", "F value", "Pr(>F)"]
    if n_groups < 2 or len(values) <= n_groups:
        return pd.DataFrame(columns=columns)

    counts = np.bincount(codes, minlength=n_groups).astype(float)
    means = np.bincount(codes, weights=values, minlength=n_groups) / counts
    overall = float(np.mean(values))
    ss_groups = float(np.sum(counts * np.square(means - overall)))
    ss_residual = float(np.sum(np.square(values - means[codes])))
    df_groups = n_groups - 1
    df_residual = len(values) - n_groups
    ms_groups = ss_groups / df_groups
    ms_residual = ss_residual / df_residual
    f_value = ms_groups / ms_residual if ms_residual > EPS else np.nan
    p_value = stats.f.sf(f_value, df_groups, df_residual) if np.isfinite(f_value) else np.nan
    return pd.DataFrame(
        [
            {"term": "Groups", "Df": df_groups, "Sum Sq": ss_groups, "Mean Sq": ms_groups, "F value": f_value, "Pr(>F)": p_value},
            {"term": "Residuals", "Df": df_residual, "Sum Sq": ss_residual, "Mean Sq": ms_residual, "F value": np.nan, "Pr(>F)": np.nan},
        ],
        columns=columns,
    )


def betadisper(
    distance: np.ndarray,
    groups: Iterable[object],
    permutations: int,
    seed: int,
) -> tuple[dict[str, float | int], pd.DataFrame]:
    labels = np.asarray(list(groups))
    coords, positive_axes = _betadisper_pcoa(distance)

    def distances_to_centres(current: np.ndarray) -> np.ndarray:
        return _distances_to_spatial_medians(coords, positive_axes, current)

    observed_dist = distances_to_centres(labels)
    samples = [observed_dist[labels == group] for group in pd.unique(labels)]
    observed_f = float(stats.f_oneway(*samples).statistic) if all(len(x) > 1 for x in samples) else np.nan
    perm_stats = (
        _betadisper_residual_permutations(
            observed_dist, labels, permutations, seed
        )
        if np.isfinite(observed_f)
        else np.empty(0, dtype=float)
    )
    p_value = (
        (1 + np.count_nonzero(perm_stats >= observed_f - math.sqrt(EPS)))
        / (len(perm_stats) + 1)
        if len(perm_stats)
        else np.nan
    )
    detail = pd.DataFrame({"group": labels, "distance_to_centroid": observed_dist})
    return (
        {
            "F": observed_f,
            "p_value": float(p_value),
            "permutations": permutations,
            "mean_distance": float(np.mean(observed_dist)),
        },
        detail,
    )


def beta_partition_pair(x: np.ndarray, y: np.ndarray) -> dict[str, float | int]:
    first, second = np.asarray(x) > 0, np.asarray(y) > 0
    a = int(np.count_nonzero(first & second))
    b = int(np.count_nonzero(first & ~second))
    c = int(np.count_nonzero(~first & second))
    beta_sor = (b + c) / max(2 * a + b + c, 1)
    beta_sim = min(b, c) / max(a + min(b, c), 1)
    return {
        "shared_species": a,
        "unique_first": b,
        "unique_second": c,
        "beta_sorensen": beta_sor,
        "beta_turnover_simpson": beta_sim,
        "beta_nestedness": max(beta_sor - beta_sim, 0.0),
    }


def beta_partition_groups(matrix: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    names = list(matrix.index)
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            rows.append(
                {
                    "group_1": first,
                    "group_2": second,
                    **beta_partition_pair(
                        matrix.loc[first].to_numpy(), matrix.loc[second].to_numpy()
                    ),
                }
            )
    return pd.DataFrame(rows)


def beta_partition_matrices(matrix: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Diversidad beta de Sørensen por pares y componentes de Simpson."""
    data = (matrix.fillna(0).to_numpy(dtype=float) > 0).astype(np.int8)
    names = matrix.index.astype(str)
    total = np.zeros((len(data), len(data)), dtype=float)
    turnover = np.zeros_like(total)
    nestedness = np.zeros_like(total)
    for first in range(len(data)):
        for second in range(first + 1, len(data)):
            values = beta_partition_pair(data[first], data[second])
            total[first, second] = total[second, first] = values["beta_sorensen"]
            turnover[first, second] = turnover[second, first] = values["beta_turnover_simpson"]
            nestedness[first, second] = nestedness[second, first] = values["beta_nestedness"]
    return {
        "beta_total": pd.DataFrame(total, index=names, columns=names),
        "beta_turnover": pd.DataFrame(turnover, index=names, columns=names),
        "beta_nestedness": pd.DataFrame(nestedness, index=names, columns=names),
    }


def beta_partition_multi(matrix: pd.DataFrame) -> dict[str, float]:
    """Partición Sørensen multisitio idéntica a ``betapart::beta.multi``."""
    data = (matrix.fillna(0).to_numpy(dtype=float) > 0).astype(np.int8)
    if data.shape[0] < 2 or data.shape[1] == 0:
        return {"beta_total": np.nan, "beta_turnover": np.nan, "beta_nestedness": np.nan}
    shared = data @ data.T
    richness = np.diag(shared).astype(float)
    total_richness = float(np.count_nonzero(data.sum(axis=0) > 0))
    shared_multisite = float(richness.sum() - total_richness)
    not_shared = richness[:, None] - shared
    sum_not_shared = not_shared + not_shared.T
    min_not_shared = np.minimum(not_shared, not_shared.T)
    lower = np.tril_indices(len(data), k=-1)
    sorensen_numerator = float(sum_not_shared[lower].sum())
    simpson_numerator = float(min_not_shared[lower].sum())
    sorensen_denominator = 2.0 * shared_multisite + sorensen_numerator
    simpson_denominator = shared_multisite + simpson_numerator
    beta_total = sorensen_numerator / sorensen_denominator if sorensen_denominator > 0 else 0.0
    beta_turnover = simpson_numerator / simpson_denominator if simpson_denominator > 0 else 0.0
    return {
        "beta_total": float(beta_total),
        "beta_turnover": float(beta_turnover),
        "beta_nestedness": float(max(beta_total - beta_turnover, 0.0)),
    }


def lcbd(
    matrix: pd.DataFrame,
    permutations: int,
    seed: int,
    method: str = "jaccard",
) -> pd.DataFrame:
    raw = matrix.to_numpy(dtype=float)
    comparison_tolerance = math.sqrt(EPS)

    def calculate(current: np.ndarray) -> np.ndarray:
        if len(current) == 0:
            return np.asarray([], dtype=float)
        if method == "jaccard":
            distance = jaccard_matrix(current > 0)
            row_mean = distance.mean(axis=1)
            contributions = np.clip(
                row_mean - 0.5 * float(row_mean.mean()), 0, None
            )
        elif method == "hellinger":
            transformed = hellinger(current)
            centered = transformed - transformed.mean(axis=0)
            contributions = np.square(centered).sum(axis=1)
        else:
            raise ValueError("LCBD method must be 'jaccard' or 'hellinger'.")
        total = float(contributions.sum())
        if total <= EPS:
            return np.zeros(len(current), dtype=float)
        return contributions / total

    observed = calculate(raw)
    if observed.size == 0 or float(np.nansum(observed)) <= EPS:
        p_values = np.ones(len(matrix), dtype=float)
        p_adjust = np.ones(len(matrix), dtype=float)
        return pd.DataFrame(
            {
                "grid_id": matrix.index.astype(str),
                "LCBD": observed,
                "LCBD_p_value": p_values,
                "LCBD_p_adjust_BH": p_adjust,
                "LCBD_significant": np.zeros(len(matrix), dtype=bool),
                "LCBD_significant_FDR": np.zeros(len(matrix), dtype=bool),
                "LCBD_method": method,
            }
        )
    exceed = np.zeros(len(matrix), dtype=int)
    rng = np.random.default_rng(seed)
    for _ in range(permutations):
        permuted = raw.copy()
        for column in range(permuted.shape[1]):
            permuted[:, column] = rng.permutation(permuted[:, column])
        values = calculate(permuted)
        exceed += values + comparison_tolerance >= observed
    p_values = (exceed + 1) / (permutations + 1)
    p_adjust = stats.false_discovery_control(
        np.where(np.isfinite(p_values), p_values, 1.0), method="bh"
    )
    return pd.DataFrame(
        {
            "grid_id": matrix.index.astype(str),
            "LCBD": observed,
            "LCBD_p_value": p_values,
            "LCBD_p_adjust_BH": p_adjust,
            "LCBD_significant": p_values < 0.05,
            "LCBD_significant_FDR": p_adjust < 0.05,
            "LCBD_method": method,
        }
    )

def indicator_values(
    matrix: pd.DataFrame,
    groups: Iterable[object],
    permutations: int,
    seed: int,
    *,
    combinations: bool = True,
    max_order: int | None = None,
) -> pd.DataFrame:
    x = (matrix.to_numpy(dtype=float) > 0).astype(float)
    labels = np.asarray(list(groups))
    unique = sorted(pd.unique(labels), key=str)
    if len(labels) != len(x):
        raise ValueError("El número de grupos debe coincidir con las filas de la matriz.")
    if not unique:
        return pd.DataFrame()
    maximum = min(max_order if max_order is not None else len(unique), len(unique))
    orders = range(1, maximum + 1) if combinations else range(1, 2)
    combinations_all = [
        combination
        for order in orders
        for combination in itertools.combinations(unique, order)
    ]
    combination_membership = np.asarray(
        [[group in combination for group in unique] for combination in combinations_all],
        dtype=float,
    )
    group_lookup = {group: index for index, group in enumerate(unique)}

    def calculate(current: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        one_hot = np.zeros((len(current), len(unique)), dtype=float)
        one_hot[np.arange(len(current)), [group_lookup[group] for group in current]] = 1.0
        group_counts = one_hot.sum(axis=0)[:, None]
        group_occurrence = np.divide(
            one_hot.T @ x,
            group_counts,
            out=np.zeros((len(unique), x.shape[1]), dtype=float),
            where=group_counts > 0,
        )
        specificity_all = np.divide(
            combination_membership @ group_occurrence,
            group_occurrence.sum(axis=0, keepdims=True),
            out=np.zeros((len(combinations_all), x.shape[1]), dtype=float),
            where=group_occurrence.sum(axis=0, keepdims=True) > 0,
        )
        site_in_combination = (one_hot @ combination_membership.T) > 0
        fidelity_all = np.divide(
            site_in_combination.T.astype(float) @ x,
            site_in_combination.sum(axis=0)[:, None],
            out=np.zeros((len(combinations_all), x.shape[1]), dtype=float),
            where=site_in_combination.sum(axis=0)[:, None] > 0,
        )
        values = np.sqrt(np.clip(specificity_all, 0.0, 1.0) * np.clip(fidelity_all, 0.0, 1.0))
        best = values.argmax(axis=0)
        columns = np.arange(values.shape[1])
        return values[best, columns], best, specificity_all[best, columns], fidelity_all[best, columns]

    observed, best, specificity, fidelity = calculate(labels)
    exceed = np.zeros(x.shape[1], dtype=int)
    rng = np.random.default_rng(seed)
    for _ in range(permutations):
        values, _, _, _ = calculate(rng.permutation(labels))
        exceed += values >= observed - EPS
    p_values = (exceed + 1) / (permutations + 1)
    p_adjust = stats.false_discovery_control(
        np.where(np.isfinite(p_values), p_values, 1.0), method="bh"
    )
    return pd.DataFrame(
        {
            "Species": matrix.columns,
            "indicator_group": [" + ".join(map(str, combinations_all[index])) for index in best],
            "group_order": [len(combinations_all[index]) for index in best],
            "A_specificity": specificity,
            "B_fidelity": fidelity,
            "IndVal": observed,
            "p_value": p_values,
            "p_adjust_BH": p_adjust,
            "significant": p_values < 0.05,
            "significant_FDR": p_adjust < 0.05,
        }
    ).sort_values(["p_adjust_BH", "p_value", "IndVal"], ascending=[True, True, False])


def simper(matrix: pd.DataFrame, groups: Iterable[object]) -> pd.DataFrame:
    x = matrix.to_numpy(dtype=float)
    labels = np.asarray(list(groups))
    unique = sorted(pd.unique(labels), key=str)
    rows: list[dict[str, object]] = []
    for i, first in enumerate(unique):
        idx_first = np.where(labels == first)[0]
        for second in unique[i + 1 :]:
            idx_second = np.where(labels == second)[0]
            contributions: list[np.ndarray] = []
            for a in idx_first:
                for b in idx_second:
                    denominator = np.sum(x[a] + x[b])
                    if denominator > 0:
                        contributions.append(np.abs(x[a] - x[b]) / denominator)
            if not contributions:
                continue
            mean = np.vstack(contributions).mean(axis=0)
            total = mean.sum()
            order = np.argsort(mean)[::-1]
            cumulative = 0.0
            for rank, column in enumerate(order, 1):
                percentage = 100 * mean[column] / max(total, EPS)
                cumulative += percentage
                rows.append(
                    {
                        "group_1": first,
                        "group_2": second,
                        "Species": matrix.columns[column],
                        "mean_contribution": mean[column],
                        "contribution_pct": percentage,
                        "cumulative_pct": cumulative,
                        "rank": rank,
                    }
                )
    return pd.DataFrame(rows)


def bootstrap_median_ci(
    values: Iterable[float], iterations: int, seed: int
) -> tuple[float, float]:
    x = np.asarray(list(values), dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    samples = rng.choice(x, size=(iterations, len(x)), replace=True)
    medians = np.median(samples, axis=1)
    low, high = np.quantile(medians, [0.025, 0.975])
    return float(low), float(high)


def envfit(
    coordinates: np.ndarray,
    environment: pd.DataFrame,
    permutations: int,
    seed: int,
) -> pd.DataFrame:
    coordinates = np.asarray(coordinates, dtype=float)
    if coordinates.ndim != 2 or coordinates.shape[1] < 2:
        return pd.DataFrame()
    finite_coordinates = np.isfinite(coordinates).all(axis=1)
    # Con una sola especie, la transformación de Hellinger suele producir una
    # ordenación NMDS constante. En ese caso envfit no está definido y llamar
    # repetidamente a pearsonr solo genera miles de advertencias sin aportar un
    # resultado estadístico.
    if finite_coordinates.sum() < 4 or np.all(
        np.nanstd(coordinates[finite_coordinates, :2], axis=0) <= EPS
    ):
        return pd.DataFrame()
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for name in environment.columns:
        values = numeric(environment[name]).to_numpy(dtype=float)
        keep = np.isfinite(values) & np.isfinite(coordinates).all(axis=1)
        if keep.sum() < 4 or np.nanstd(values[keep]) == 0:
            continue
        variable_coordinates = coordinates[keep, :2]
        active_axes = np.nanstd(variable_coordinates, axis=0) > EPS
        if not active_axes.any():
            continue
        r1 = (
            stats.pearsonr(values[keep], variable_coordinates[:, 0]).statistic
            if active_axes[0]
            else 0.0
        )
        r2 = (
            stats.pearsonr(values[keep], variable_coordinates[:, 1]).statistic
            if active_axes[1]
            else 0.0
        )
        observed = float(r1 * r1 + r2 * r2)
        exceed = 0
        for _ in range(permutations):
            shuffled = rng.permutation(values[keep])
            p1 = (
                stats.pearsonr(shuffled, variable_coordinates[:, 0]).statistic
                if active_axes[0]
                else 0.0
            )
            p2 = (
                stats.pearsonr(shuffled, variable_coordinates[:, 1]).statistic
                if active_axes[1]
                else 0.0
            )
            exceed += (p1 * p1 + p2 * p2) >= observed - EPS
        rows.append(
            {
                "variable": name,
                "axis_1": r1,
                "axis_2": r2,
                "r2": observed,
                "p_value": (exceed + 1) / (permutations + 1),
                "n": int(keep.sum()),
            }
        )
    return pd.DataFrame(rows).sort_values("p_value") if rows else pd.DataFrame()


def moran_i(
    values: Iterable[float],
    adjacency: np.ndarray,
    permutations: int,
    seed: int,
) -> dict[str, float | int]:
    x = np.asarray(list(values), dtype=float)
    w = np.asarray(adjacency, dtype=float)
    keep = np.isfinite(x)
    x, w = x[keep], w[np.ix_(keep, keep)]
    n, total_w = len(x), w.sum()
    if n < 3 or total_w <= 0 or np.allclose(x, x[0]):
        return {"Moran_I": np.nan, "p_value": np.nan, "permutations": permutations}

    def calculate(current: np.ndarray) -> float:
        centered = current - current.mean()
        return float((n / total_w) * np.sum(w * np.outer(centered, centered)) / np.sum(centered**2))

    observed = calculate(x)
    rng = np.random.default_rng(seed)
    permuted = np.asarray([calculate(rng.permutation(x)) for _ in range(permutations)])
    expected = -1.0 / (n - 1)
    p_value = (1 + np.count_nonzero(np.abs(permuted - expected) >= abs(observed - expected) - EPS)) / (permutations + 1)
    return {"Moran_I": observed, "expected_I": expected, "p_value": float(p_value), "permutations": permutations}


@dataclass(frozen=True)
class AnalysisSettings:
    permutations: int = 999
    random_seed: int = 20260501
    bootstrap_iterations: int = 1000
    min_records_cell: int = 2
    coastal_threshold_km: float = 10.0
    similarity_threshold: float = 0.55
    temporal_periods: tuple[tuple[str, str, str], ...] = ()
