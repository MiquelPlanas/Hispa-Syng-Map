from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, Polygon


def fail(message: str) -> None:
    raise AssertionError(message)


def assert_close(actual: float, expected: float, tol: float = 1e-9) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=tol):
        fail(f"Expected {expected!r}, got {actual!r}")


def run(edition_root: Path) -> None:
    src = edition_root / "src"
    sys.path.insert(0, str(src))

    from hippodec_maps.metrics import calculate_metrics
    from hippodec_maps.spatial import assign_points_to_grid, assign_regions_from_reference_grid, official_grid_relation, prepare_marine_grid_areas
    from hippodec_maps.conservation import _cells_with_species_summary_for_map
    from hippodec_maps.localization import translate_frame
    from hippodec_maps.sampling import add_sampling_event_ids, sampling_event_summary
    from hippodec_maps.regions import observations_to_points
    from hippodec_maps.analysis_status import (
        CALCULABLE, INSUFFICIENT_DATA, NOT_ESTIMABLE,
        analysis_status_record, is_calculable,
    )
    from hippodec_maps.temporal import (
        Period, _annual, _annual_period_metrics, _period_summary, _comparisons,
        _official_temporal_signal, _fit_models, _symmetric_relative_change,
    )
    from hippodec_maps.analysis_utils import (
        AnalysisSettings, bray_curtis_matrix, euclidean_matrix, hellinger,
        indicator_values, jaccard_matrix, lcbd, mantel_spearman, pcoa_lingoes,
    )
    from hippodec_maps.community import _distance_decay, _grid_environment
    from hippodec_maps.technical_report import _report_effort_frame, _effort_discussion
    from hippodec_maps.optional_analysis import (
        _feve, _fdiv, _fdis_anderson, _functional_metrics, _functional_space,
        _gower_numeric, _select_global_dimensions,
    )
    from hippodec_maps.multiscale import (
        _aggregate_persistence_to_selected, _build_canonical_persistence,
    )
    from hippodec_maps.analysis_pipeline import _validate_priority_range

    # 1) Core density regression: densities are individuals per marine km²,
    # never scaled by 1000. Internal values retain full precision.
    cell_geom = Polygon([(0, 0), (1000, 0), (1000, 500), (0, 500)])
    grid = gpd.GeoDataFrame(
        {
            "grid_id": ["g1"],
            "Area_mar_km2": [0.5],
            "official_cell_code": ["g1"],
            "Region_MITECO": ["Test"],
            "Region_slug": ["test"],
            "geometry": [cell_geom],
        },
        crs="EPSG:3857",
    )
    assigned = gpd.GeoDataFrame(
        {
            "obs_id": [1, 2],
            "grid_id": ["g1", "g1"],
            "Species": ["Species alpha", "Species alpha"],
            "N_total": [1.0, 2.0],
            "Fecha_aux": ["2024-01-01", "2025-01-01"],
            "Area_mar_km2": [0.5, 0.5],
            "Area_celda_km2": [0.5, 0.5],
            "Area_mar_source": ["gshhs_clipped_geometry", "gshhs_clipped_geometry"],
            "dist_to_cell_m": [0.0, 0.0],
            "N hembra": [0, 0],
            "N macho": [0, 0],
            "N_indeterminado": [1, 2],
            "Region_MITECO": ["Test", "Test"],
            "geometry": [Point(100, 100), Point(200, 100)],
        },
        crs="EPSG:3857",
    )
    occupied, cells, species, _, qa = calculate_metrics(assigned, grid, 1)
    assert_close(cells.loc[0, "Densidad_total"], 6.0)
    assert_close(species.loc[0, "Densidad_ajustada"], 6.0)
    if qa.get("density_scale_km2") != 1:
        fail("Density scale is not 1 km²")

    # 2) Invalid marine area must be rejected rather than replaced by nominal area.
    bad = assigned.copy()
    bad["Area_mar_km2"] = 0.0
    try:
        calculate_metrics(bad, grid, 1)
    except ValueError:
        pass
    else:
        fail("Zero marine area was not rejected")

    # 3) Assignment regression: zero-area cells are excluded; near points may
    # move only to a valid marine cell within tolerance; distant points remain unassigned.
    assignment_grid = gpd.GeoDataFrame(
        {
            "grid_id": ["invalid", "marine"],
            "official_cell_code": ["A", "B"],
            "Area_mar_km2": [0.0, 1.0],
            "grid_order": [0, 1],
            "Region_slug": ["test", "test"],
            "Region_MITECO": ["Test", "Test"],
            "geometry": [
                Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)]),
                Polygon([(1000, 0), (2000, 0), (2000, 1000), (1000, 1000)]),
            ],
        },
        crs="EPSG:3857",
    )
    points = gpd.GeoDataFrame(
        {
            "obs_id": [1, 2, 3],
            "Region_slug": [pd.NA, pd.NA, pd.NA],
            "Region_MITECO": [pd.NA, pd.NA, pd.NA],
            "geometry": [Point(1500, 500), Point(900, 500), Point(-1100, 500)],
        },
        crs="EPSG:3857",
    )
    got, missing, stats = assign_points_to_grid(points, assignment_grid, tolerance_m=1000.0)
    methods = dict(zip(got["obs_id"], got["assignment_method"]))
    if methods.get(1) != "intersects":
        fail("Direct marine assignment failed")
    if methods.get(2) != "nearest":
        fail("Nearest marine assignment failed")
    if 3 not in set(missing["obs_id"]):
        fail("Out-of-tolerance point was incorrectly assigned")
    if stats["grid_cells_excluded_no_marine_surface"] != 1:
        fail("Invalid marine cell was not counted as excluded")

    # 3b) Canonical regional assignment must be independent of the analytical
    # grid resolution. Points without a direct demarcation are assigned from a
    # fixed 10-km reference grid; direct intersection takes precedence and only
    # genuinely nearby points may use the reference-grid nearest fallback.
    reference_grid = gpd.GeoDataFrame(
        {
            "grid_id": ["r1", "r2"],
            "grid_order": [0, 1],
            "Region_slug": ["region_a", "region_b"],
            "Region_MITECO": ["Region A", "Region B"],
            "geometry": [
                Polygon([(0, 0), (10000, 0), (10000, 10000), (0, 10000)]),
                Polygon([(10000, 0), (20000, 0), (20000, 10000), (10000, 10000)]),
            ],
        },
        crs="EPSG:3857",
    )
    reference_points = gpd.GeoDataFrame(
        {
            "obs_id": [101, 102, 103],
            "geometry": [Point(5000, 5000), Point(-500, 5000), Point(-12000, 5000)],
        },
        crs="EPSG:3857",
    )
    ref = assign_regions_from_reference_grid(reference_points, reference_grid, tolerance_m=10000.0)
    ref_by_id = ref.set_index("obs_id")
    if ref_by_id.loc[101, "Region_slug_reference"] != "region_a":
        fail("Canonical 10-km regional intersection assignment failed")
    if ref_by_id.loc[101, "reference_region_method"] != "reference_grid_10km_intersects":
        fail("Canonical regional intersection method was not recorded")
    if ref_by_id.loc[102, "Region_slug_reference"] != "region_a":
        fail("Canonical 10-km nearest regional assignment failed")
    if ref_by_id.loc[102, "reference_region_method"] != "reference_grid_10km_nearest":
        fail("Canonical regional nearest method was not recorded")
    assert_close(ref_by_id.loc[102, "reference_region_distance_m"], 500.0)
    if 103 in ref_by_id.index:
        fail("Out-of-tolerance point received a canonical region")

    # 4) Conservation popup regression: assigned may already contain Area_mar_km2.
    # The display enrichment must not create _x/_y collisions and must use N/area.
    priority = gpd.GeoDataFrame(
        {
            "master_id": ["g1"],
            "Area_mar_km2": [0.5],
            "geometry": [cell_geom],
        },
        crs="EPSG:3857",
    )
    assigned_popup = gpd.GeoDataFrame(
        {
            "grid_id": ["g1", "g1"],
            "Species": ["Species alpha", "Species alpha"],
            "N_total": [1.0, 2.0],
            "Area_mar_km2": [0.5, 0.5],
            "geometry": [Point(100, 100), Point(200, 100)],
        },
        crs="EPSG:3857",
    )
    enriched = _cells_with_species_summary_for_map(priority, assigned_popup)
    payload = json.loads(enriched.loc[0, "species_cell_summary"])
    if len(payload) != 1:
        fail("Species summary did not aggregate the cell correctly")
    assert_close(payload[0][1], 3.0)
    assert_close(payload[0][2], 6.0)

    # 5) Export boundary regression: visible/exported density columns max 2 decimals.
    translated = translate_frame(pd.DataFrame({"Densidad_total": [1.23456], "x": [1.23456]}))
    density_col = next(c for c in translated.columns if "density" in str(c).casefold() or "densidad" in str(c).casefold())
    assert_close(translated.loc[0, density_col], 1.23)
    if not math.isclose(float(translated.loc[0, "x"]), 1.23456, rel_tol=0, abs_tol=1e-12):
        fail("Non-density numeric data were unexpectedly rounded")

    # 6) Persistent marine-area cache: miss -> hit -> partial hit when one geometry changes.
    with tempfile.TemporaryDirectory(prefix="hispa_syng_regression_") as tmp:
        tmp = Path(tmp)
        shp = tmp / "gshhs_test.shp"
        land = gpd.GeoDataFrame(
            {"geometry": [Polygon([(0, 0), (500, 0), (500, 1000), (0, 1000)])]},
            crs="EPSG:3857",
        )
        land.to_file(shp, engine="pyogrio")
        test_grid = gpd.GeoDataFrame(
            {
                "grid_id": ["a", "b"],
                "Area_mar_oficial_km2": [1.0, 1.0],
                "geometry": [
                    Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)]),
                    Polygon([(1000, 0), (2000, 0), (2000, 1000), (1000, 1000)]),
                ],
            },
            crs="EPSG:3857",
        )
        cache_dir = tmp / "cache"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            first, qa1 = prepare_marine_grid_areas(test_grid, shp, cache_dir=cache_dir, resolution_km=1)
        if any("GeoSeries.notna" in str(w.message) for w in caught):
            fail("GeoSeries.notna warning reappeared")
        if qa1["marine_area_cache_status"] != "miss" or qa1["marine_area_cache_cells_computed"] != 2:
            fail(f"Unexpected first cache state: {qa1}")
        assert_close(first.loc[first["grid_id"].eq("a"), "Area_mar_km2"].iloc[0], 0.5)
        assert_close(first.loc[first["grid_id"].eq("b"), "Area_mar_km2"].iloc[0], 1.0)

        second, qa2 = prepare_marine_grid_areas(test_grid, shp, cache_dir=cache_dir, resolution_km=1)
        if qa2["marine_area_cache_status"] != "hit" or qa2["marine_area_cache_cells_reused"] != 2:
            fail(f"Unexpected cache hit state: {qa2}")

        changed = test_grid.copy()
        changed.loc[changed["grid_id"].eq("b"), "geometry"] = [
            Polygon([(1000, 0), (1900, 0), (1900, 1000), (1000, 1000)])
        ]
        _, qa3 = prepare_marine_grid_areas(changed, shp, cache_dir=cache_dir, resolution_km=1)
        if qa3["marine_area_cache_status"] != "partial_hit":
            fail(f"Geometry change did not produce partial cache hit: {qa3}")
        if qa3["marine_area_cache_cells_reused"] != 1 or qa3["marine_area_cache_cells_computed"] != 1:
            fail(f"Partial cache hit counts are wrong: {qa3}")

    # 6b) Coastal MITECO fallback must use the actual fallback geometry area.
    with tempfile.TemporaryDirectory(prefix="hispa_syng_fallback_") as tmp:
        tmp = Path(tmp)
        shp = tmp / "gshhs_full_land.shp"
        full_land = gpd.GeoDataFrame({"geometry": [Polygon([(0,0),(1000,0),(1000,1000),(0,1000)])]}, crs="EPSG:3857")
        full_land.to_file(shp, engine="pyogrio")
        fallback_grid = gpd.GeoDataFrame({
            "grid_id": ["fallback"], "official_cell_code": ["fallback"],
            "Area_mar_oficial_km2": [1.0], "Region_slug": ["test"],
            "Region_MITECO": ["Test"],
            "geometry": [Polygon([(0,0),(1000,0),(1000,1000),(0,1000)])],
        }, crs="EPSG:3857")
        marine_regions = gpd.GeoDataFrame({
            "Region_slug": ["test"], "Region_MITECO": ["Test"],
            "geometry": [Polygon([(0,0),(200,0),(200,1000),(0,1000)])],
        }, crs="EPSG:3857")
        fallback_result, fallback_qa = prepare_marine_grid_areas(
            fallback_grid, shp, marine_regions=marine_regions, resolution_km=1
        )
        assert_close(fallback_result.loc[0, "Area_mar_gshhs_km2"], 0.0)
        assert_close(fallback_result.loc[0, "Area_mar_miteco_fallback_km2"], 0.2)
        assert_close(fallback_result.loc[0, "Area_mar_km2"], 0.2)
        if fallback_result.loc[0, "Area_mar_source"] != "miteco_demarcation_fallback_geometry":
            fail("MITECO fallback source was not recorded")
        if fallback_qa["cells_using_miteco_demarcation_fallback"] != 1:
            fail(f"MITECO fallback QA count is wrong: {fallback_qa}")

    # 7) Observation-event identity is stable, species-independent and does not
    # merge missing-observer rows. It is infrastructure only in the event-identification infrastructure.
    event_points = gpd.GeoDataFrame(
        {
            "source_row": [2, 3, 4, 5, 6, 7],
            "Fecha_aux": pd.to_datetime([
                "2024-06-01", "2024-06-01", "2024-06-01",
                "2024-06-01", "2024-06-01", "2024-06-01",
            ]),
            "Observer": [" Alice  Smith ", "alice smith", "Alice Smith", "Bob", pd.NA, pd.NA],
            "Species": ["sp1", "sp2", "sp3", "sp1", "sp1", "sp2"],
            "geometry": [
                Point(1000.10, 2000.10),
                Point(1000.20, 2000.20),
                Point(1001.20, 2000.20),
                Point(1000.10, 2000.10),
                Point(1000.10, 2000.10),
                Point(1000.10, 2000.10),
            ],
        },
        crs="EPSG:3035",
    )
    evented = add_sampling_event_ids(event_points)
    ids = evented["sampling_event_id"].tolist()
    if ids[0] != ids[1]:
        fail("Equivalent observer/date/~1 m rows were not grouped into one sampling event")
    if ids[0] == ids[2]:
        fail("Rows separated by >1 m quantization were incorrectly grouped")
    if ids[0] == ids[3]:
        fail("Different observers were incorrectly grouped into one event")
    if ids[4] == ids[5]:
        fail("Missing-observer rows were incorrectly merged")
    reordered = add_sampling_event_ids(event_points.iloc[::-1].copy()).sort_values("source_row")
    original = evented.sort_values("source_row")
    if original["sampling_event_id"].tolist() != reordered["sampling_event_id"].tolist():
        fail("sampling_event_id changed when row order changed")
    changed_species = event_points.copy()
    changed_species["Species"] = "other species"
    if add_sampling_event_ids(changed_species)["sampling_event_id"].tolist() != ids:
        fail("Species unexpectedly participates in sampling_event_id")
    summary = sampling_event_summary(evented)
    if summary["n_records"] != 6 or summary["n_sampling_events"] != 5:
        fail(f"Unexpected observation-event summary: {summary}")

    point_input = pd.DataFrame({
        "X": [1000.1, 1000.2],
        "Y": [2000.1, 2000.2],
        "EPSG": [3035, 3035],
        "Fecha_aux": pd.to_datetime(["2024-06-01", "2024-06-01"]),
        "Observer": ["Alice Smith", "alice smith"],
        "source_row": [2, 3],
    })
    projected = observations_to_points(point_input, 3035)
    if "sampling_event_id" not in projected.columns or projected["sampling_event_id"].nunique() != 1:
        fail("observations_to_points did not attach the shared sampling_event_id")

    # 8) Analytical states keep non-estimability distinct from a numeric zero.
    ok = analysis_status_record(CALCULABLE, value=0.0)
    if not is_calculable(ok["analysis_status"]) or ok["value"] != 0.0:
        fail("Calculable zero was not preserved")
    insufficient = analysis_status_record(INSUFFICIENT_DATA, "too_few_events")
    if is_calculable(insufficient["analysis_status"]):
        fail("Insufficient-data status was treated as calculable")
    not_estimable = analysis_status_record(NOT_ESTIMABLE, "constant_metric")
    if not_estimable["analysis_status_reason"] != "constant_metric":
        fail("Analytical-status reason was not preserved")
    try:
        analysis_status_record("zero")
    except ValueError:
        pass
    else:
        fail("Unknown analytical status was accepted")

    # 9) Temporal-analysis regression: records remain descriptive, while the
    # primary effort proxy is the number of unique sampling events.
    temporal_rows = []
    for year in range(2010, 2022):
        for event_no in range(10):
            event_id = f"E{year}_{event_no}"
            period = "P1" if year <= 2015 else "P2"
            if event_no < 2:
                abundance = (1 if year % 3 else 12) + (1 if event_no == 1 else 0)
                temporal_rows.append({
                    "Species": "Species temporal", "year": year,
                    "Fecha_aux": pd.Timestamp(f"{year}-06-01"), "period": period,
                    "grid_id": "g1", "Area_mar_km2": 2.0, "N_aux": float(abundance),
                    "Depth_aux": 5.0, "Habitat_aux": "h",
                    "sampling_event_id": event_id, "coord_x": 100.0, "coord_y": 100.0,
                    "Region_MITECO": "Test",
                })
            if event_no == 5 and year in (2012, 2016, 2020):
                temporal_rows.append({
                    "Species": "Species rare", "year": year,
                    "Fecha_aux": pd.Timestamp(f"{year}-06-01"), "period": period,
                    "grid_id": "g1", "Area_mar_km2": 2.0, "N_aux": 1.0,
                    "Depth_aux": 5.0, "Habitat_aux": "h",
                    "sampling_event_id": event_id, "coord_x": 100.0, "coord_y": 100.0,
                    "Region_MITECO": "Test",
                })
            # Filler observations ensure all ten events are represented each year.
            temporal_rows.append({
                "Species": "Species filler", "year": year,
                "Fecha_aux": pd.Timestamp(f"{year}-06-01"), "period": period,
                "grid_id": "g1", "Area_mar_km2": 2.0, "N_aux": 1.0,
                "Depth_aux": 5.0, "Habitat_aux": "h",
                "sampling_event_id": event_id, "coord_x": 100.0, "coord_y": 100.0,
                "Region_MITECO": "Test",
            })
    temporal_table = pd.DataFrame(temporal_rows)
    annual_temporal = _annual(temporal_table)
    focal = annual_temporal[annual_temporal["Species"].eq("Species temporal")]
    if not focal["n_sampling_events"].eq(10).all():
        fail("Temporal effort did not use unique sampling events")
    if not focal["effort_records"].gt(focal["n_sampling_events"]).all():
        fail("Record count was not preserved as a distinct descriptive metric")
    if not np.allclose(focal["abundance_per_sampling_event"], focal["abundance"] / 10):
        fail("Primary annual observation rate is not abundance / sampling events")

    temporal_periods = [
        Period("P1", pd.Timestamp("2010-01-01"), pd.Timestamp("2015-12-31")),
        Period("P2", pd.Timestamp("2016-01-01"), pd.Timestamp("2021-12-31")),
    ]
    annual_period = _annual_period_metrics(temporal_table, temporal_periods)
    period_summary = _period_summary(temporal_table, temporal_periods, annual_period)
    comparisons = _comparisons(temporal_table, temporal_periods, period_summary, annual_period)
    if not comparisons["primary_change_metric"].eq("abundance_per_sampling_event_global_period").all():
        fail("Period comparison still uses records as the primary effort denominator")

    magnitude, signed = _symmetric_relative_change(
        pd.Series([1.0, 0.0, 2.0]), pd.Series([2.0, 0.0, 1.0])
    )
    if not np.allclose(magnitude, [1 / 3, 0, 1 / 3]) or not np.allclose(signed, [1 / 3, 0, -1 / 3]):
        fail("Symmetric temporal change magnitude/direction is incorrect")
    scaled_magnitude, _ = _symmetric_relative_change(pd.Series([1000.0]), pd.Series([2000.0]))
    assert_close(scaled_magnitude.iloc[0], 1 / 3)

    official_signal, official_detail = _official_temporal_signal(temporal_table, temporal_periods)
    if official_signal.empty or "grid_id" not in official_signal.columns:
        fail("Official MITECO temporal signal was not created")
    if not official_signal["temporal_signal_raw"].between(0, 1).all():
        fail("Official temporal signal escaped the 0-1 interval")
    if not official_signal["signal_formula"].eq(
        "equal_weights_symmetric_observation_rate_detection_frequency_marine_density_v3"
    ).all():
        fail("Official temporal signal is not using the unit-invariant v3 formula")
    no_comparison_signal, no_comparison_detail = _official_temporal_signal(
        temporal_table,
        [Period("all", pd.Timestamp("2010-01-01"), pd.Timestamp("2021-12-31"))],
    )
    if not no_comparison_signal.empty or not no_comparison_detail.empty:
        fail("A temporal change signal was created without at least two periods")

    models, predictions = _fit_models(annual_temporal, AnalysisSettings())
    primary = models[(models["Species"].eq("Species temporal")) & models["model"].eq("Poisson-Pearson observation-rate trend")].iloc[0]
    if primary["inference_scope"] != "inferential" or primary["status"] != "ok":
        fail(f"Well-supported temporal species was not fitted inferentially: {primary.to_dict()}")
    if float(primary["pearson_dispersion_used"]) < 1.0:
        fail("Pearson dispersion correction used phi < 1")
    rare = models[(models["Species"].eq("Species rare")) & models["model"].eq("Poisson-Pearson observation-rate trend")].iloc[0]
    if rare["inference_scope"] != "descriptive_only" or rare["status"] != "descriptive_only":
        fail("Rare temporal species was incorrectly given inferential trend status")
    if predictions[predictions["Species"].eq("Species temporal")].empty:
        fail("Supported species did not receive count+offset spline predictions")
    if not predictions[predictions["Species"].eq("Species rare")].empty:
        fail("Rare species unexpectedly received inferential/smoothed predictions")

    # The integrated technical report must describe proxy events as observation
    # intensity and keep record count as data volume, rather than relabelling rows as effort.
    report_input = pd.DataFrame({
        "Species": ["sp1", "sp2", "sp1"],
        "Fecha_aux": pd.to_datetime(["2020-01-01", "2020-01-01", "2021-01-01"]),
        "N_total": [1.0, 1.0, 2.0],
        "sampling_event_id": ["event_a", "event_a", "event_b"],
    })
    report_effort = _report_effort_frame(report_input, "Species", {"year_min": 2020, "year_max": 2021})
    y2020 = report_effort[report_effort["Year"].eq(2020)].iloc[0]
    if int(y2020["n_records"]) != 2 or int(y2020["n_sampling_events"]) != 1:
        fail("Technical-report temporal coverage did not preserve records versus proxy events")
    discussion = " ".join(_effort_discussion(report_effort)).casefold()
    if "proxy" not in discussion:
        fail("Technical report does not describe the event proxy")
    if "true sampling effort" not in discussion and "esfuerzo de muestreo verdadero" not in discussion:
        fail("Technical report does not state that proxy events are not true sampling effort")

    # 10) Community-analysis regression: event-based support, dual LCBD,
    # BH-FDR, Lingoes PCoA, Mantel inference, and descriptive pairwise regression.
    community_rows = pd.DataFrame({
        "grid_id": ["c1", "c1", "c1"],
        "sampling_event_id": ["ev1", "ev1", "ev2"],
        "Depth": [5.0, 6.0, 7.0],
        "Temperatura_gC": [16.0, 16.5, 17.0],
        "Habitat": ["h1", "h1", "h2"],
        "Region_MITECO": ["R1", "R1", "R1"],
        "year": [2020, 2020, 2021],
        "Latitude": [42.0, 42.0, 42.0],
        "Longitude": [-8.0, -8.0, -8.0],
    })
    community_cells = gpd.GeoDataFrame(
        {"grid_id": ["c1"], "geometry": [Polygon([(0,0),(1000,0),(1000,1000),(0,1000)])]},
        crs="EPSG:3857",
    )
    support = _grid_environment(community_rows, community_cells).iloc[0]
    if int(support["n_records"]) != 3 or int(support["n_sampling_events"]) != 2:
        fail("Community support does not distinguish records from sampling events")
    if int(support["n_years_observed"]) != 2:
        fail("Community cell support did not preserve temporal coverage")

    community_matrix = pd.DataFrame(
        [[5,0,0],[0,5,0],[0,0,5],[5,5,0],[5,0,5]],
        index=["c1","c2","c3","c4","c5"],
        columns=["sp1","sp2","sp3"],
        dtype=float,
    )
    # Hellinger composition must be invariant to row-wise total-abundance scaling.
    h_base = np.asarray([[1.0, 3.0, 0.0], [2.0, 1.0, 5.0], [4.0, 2.0, 1.0]])
    h_scaled = h_base * np.asarray([10.0, 0.5, 7.0])[:, None]
    if not np.allclose(
        euclidean_matrix(hellinger(h_base)),
        euclidean_matrix(hellinger(h_scaled)),
        atol=1e-12, rtol=1e-12,
    ):
        fail("Hellinger-Euclidean distances changed after row-wise abundance scaling")
    for method in ("jaccard", "hellinger"):
        lc = lcbd(community_matrix, permutations=49, seed=11, method=method)
        required = {"LCBD", "LCBD_p_value", "LCBD_p_adjust_BH", "LCBD_significant_FDR", "LCBD_method"}
        if not required.issubset(lc.columns):
            fail(f"LCBD {method} is missing FDR/method fields: {set(lc.columns)}")
        assert_close(lc["LCBD"].sum(), 1.0, tol=1e-8)
        if not lc["LCBD_method"].eq(method).all():
            fail(f"LCBD method label is wrong for {method}")
        fdr_rows = lc[lc["LCBD_significant_FDR"]]
        if not fdr_rows.empty and not fdr_rows["LCBD_p_adjust_BH"].lt(0.05).all():
            fail("LCBD FDR flag is inconsistent with BH-adjusted p-values")

    indicators = indicator_values(
        community_matrix.iloc[:4], ["A", "A", "B", "B"],
        permutations=49, seed=13, combinations=True,
    )
    if not {"p_adjust_BH", "significant_FDR"}.issubset(indicators.columns):
        fail("Regional IndVal does not expose BH-FDR fields")
    if not indicators[indicators["significant_FDR"]]["p_adjust_BH"].lt(0.05).all():
        fail("IndVal FDR flag is inconsistent with BH-adjusted p-values")

    non_euclidean = bray_curtis_matrix(np.asarray(
        [[5,0,0],[0,5,0],[0,0,5],[5,5,0]], dtype=float
    ))
    pcoa_coords, pcoa_eigs, pcoa_diag = pcoa_lingoes(non_euclidean, dimensions=2)
    if pcoa_diag["correction"] != "lingoes" or float(pcoa_diag["lingoes_constant"]) <= 0:
        fail(f"Non-Euclidean Bray-Curtis was not corrected with Lingoes: {pcoa_diag}")
    if float(pcoa_diag["min_eigenvalue_before"]) >= 0:
        fail("PCoA test matrix unexpectedly lacked a negative eigenvalue before Lingoes")
    if float(pcoa_diag["min_eigenvalue_after"]) < -1e-10:
        fail("Lingoes-corrected PCoA still has a material negative eigenvalue")
    if pcoa_coords.shape != (4, 2):
        fail("Lingoes PCoA did not return the requested coordinate dimensions")

    line = np.arange(4, dtype=float)
    geo = np.abs(line[:, None] - line[None, :])
    mantel = mantel_spearman(geo, geo.copy(), permutations=49, seed=17)
    assert_close(mantel["mantel_rho"], 1.0, tol=1e-12)
    if not (0 < float(mantel["mantel_p_value"]) <= 1):
        fail("Mantel test returned an invalid permutation p-value")
    mantel_repeat = mantel_spearman(geo, geo.copy(), permutations=49, seed=17)
    if mantel_repeat != mantel:
        fail("Mantel permutation result is not reproducible for a fixed seed")

    dd_matrix = pd.DataFrame(
        [[8,0,0],[6,2,0],[2,6,0],[0,8,0]],
        index=["d1","d2","d3","d4"], columns=["sp1","sp2","sp3"], dtype=float,
    )
    transformed = hellinger(dd_matrix.to_numpy(dtype=float))
    hdist = euclidean_matrix(transformed)
    jdist = jaccard_matrix(dd_matrix.to_numpy(dtype=float) > 0)
    bdist = bray_curtis_matrix(dd_matrix.to_numpy(dtype=float))
    dd_env = gpd.GeoDataFrame({
        "grid_id": ["d1","d2","d3","d4"],
        "geometry": [Point(0,0), Point(1000,0), Point(2000,0), Point(3000,0)],
    }, crs="EPSG:3857")
    pairs, dd_summary = _distance_decay(
        dd_matrix, dd_env, hdist, jdist, bdist, permutations=49, seed=19
    )
    if len(pairs) != 6 or not {"hellinger_distance","jaccard_distance","bray_distance"}.issubset(pairs.columns):
        fail("Distance-decay export does not preserve the three community-distance views")
    if not np.isfinite(float(dd_summary["mantel_rho"])):
        fail("Distance-decay did not produce the primary Mantel statistic")
    if not math.isnan(float(dd_summary["p_value_slope"])):
        fail("Non-independent pairwise OLS slope still exposes an inferential p-value")
    if dd_summary["linear_inference_status"] != "descriptive_only_nonindependent_pairs":
        fail("Distance-decay linear fit is not labelled descriptive-only")

    # 11) Functional-diversity regressions: corrected functional space,
    # fixed dimensionality, zero-distance FEve, hull-centroid FDiv, and Anderson FDis.
    trait_frame = pd.DataFrame({
        "body_size_cm": [5.0, 10.0, 20.0, 30.0, 15.0],
        "mobility": [1.0, 1.0, 2.0, 3.0, 2.0],
        "benthic_affinity": [3.0, 3.0, 2.0, 1.0, 2.0],
        "habitat_complexity": [3.0, 3.0, 2.0, 1.0, 2.0],
        "representative_depth_m": [2.0, 4.0, 8.0, 16.0, 10.0],
        "holdfast": [3.0, 3.0, 1.0, 0.0, 1.0],
    })
    gower = _gower_numeric(trait_frame)
    if not np.allclose(gower, gower.T) or not np.allclose(np.diag(gower), 0.0):
        fail("Functional Gower matrix is not symmetric with a zero diagonal")
    fspace = _functional_space(gower)
    if fspace["correction"] not in {"none", "sqrt", "lingoes"}:
        fail("Unexpected functional-space correction label")
    if float(fspace["min_eigenvalue_after"]) < -1e-9:
        fail("Corrected functional PCoA retains a material negative eigenvalue")
    fdims, fexpl = _select_global_dimensions(fspace, len(trait_frame))
    if not (1 <= fdims <= min(4, len(trait_frame)-1)) or not (0 < fexpl <= 1):
        fail("Global functional dimensionality selection is invalid")

    # Zero-distance links between redundant species must remain in the MST.
    duplicate_dist = np.asarray([[0.0,0.0,1.0],[0.0,0.0,1.0],[1.0,1.0,0.0]])
    feve_zero = _feve(duplicate_dist, np.asarray([1.0,1.0,1.0]) / 3.0)
    assert_close(feve_zero, 0.0, tol=1e-12)

    # FDiv must use the unweighted centroid of hull vertices, not a weighted centroid.
    fdiv_points = np.asarray([[0.0,0.0],[2.0,0.0],[0.0,2.0],[0.5,0.5]])
    fdiv_weights = np.asarray([0.1,0.1,0.1,0.7])
    hull_centroid = np.asarray([2.0/3.0, 2.0/3.0])
    distances_manual = np.linalg.norm(fdiv_points - hull_centroid, axis=1)
    mean_manual = float(np.mean(distances_manual))
    expected_fdiv = (float(np.sum(fdiv_weights*(distances_manual-mean_manual))) + mean_manual) / (float(np.sum(fdiv_weights*np.abs(distances_manual-mean_manual))) + mean_manual)
    assert_close(_fdiv(fdiv_points, fdiv_weights), expected_fdiv, tol=1e-12)

    # Anderson-style FDis must remain finite when negative-axis contribution dominates.
    pos_test = np.asarray([[0.0],[0.1],[0.2]])
    neg_test = np.asarray([[0.0],[1.0],[2.0]])
    fdis_value, fdis_negative = _fdis_anderson(pos_test, neg_test, [0,1,2], np.asarray([1/3,1/3,1/3]))
    if not np.isfinite(fdis_value) or fdis_negative <= 0:
        fail("Anderson FDis correction did not handle negative-axis dominance")

    full_indexes = list(range(len(trait_frame)))
    full_metrics = _functional_metrics(fspace, full_indexes, np.ones(len(full_indexes)), fdims, 1.0)
    if not np.isfinite(float(full_metrics["FDis"])) or not np.isfinite(float(full_metrics["RaoQ"])):
        fail("Functional metrics are not finite for a supported full assemblage")
    sparse_metrics = _functional_metrics(fspace, [0,1], np.ones(2), fdims, 1.0)
    if fdims >= 2 and np.isfinite(float(sparse_metrics["FRic"])):
        fail("FRic was estimated with fewer species than required by the common dimensionality")

    # 12) Multiscale regressions: official MITECO geometry only,
    # event-supported LCBD semantics, symmetric persistence, and no centroid
    # sampling of finer hotspots.
    fine_grid = gpd.GeoDataFrame(
        {
            "grid_id": ["f1", "f2"],
            "Region_slug": ["r", "r"],
            "geometry": [
                Polygon([(0,0),(1000,0),(1000,1000),(0,1000)]),
                Polygon([(4000,0),(5000,0),(5000,1000),(4000,1000)]),
            ],
        }, crs="EPSG:3035",
    )
    grid_5 = gpd.GeoDataFrame(
        {"grid_id": ["m1"], "Region_slug": ["r"],
         "geometry": [Polygon([(0,0),(5000,0),(5000,5000),(0,5000)])]},
        crs="EPSG:3035",
    )
    grid_10 = gpd.GeoDataFrame(
        {"grid_id": ["c1"], "Region_slug": ["r"],
         "geometry": [Polygon([(0,0),(10000,0),(10000,10000),(0,10000)])]},
        crs="EPSG:3035",
    )
    relation = official_grid_relation(fine_grid, grid_5)
    if set(relation["coarse_grid_id"].astype(str)) != {"m1"} or relation["fine_grid_id"].nunique() != 2:
        fail("Official fine-to-coarse MITECO relation lost a displaced fine cell")
    if not relation["mapping_method"].isin({"representative_point_within", "maximum_geometric_overlap_fallback"}).all():
        fail("Official hierarchy used an unexpected/ecological mapping method")

    def ms_result(grid, lcbd_rows):
        grid_records = grid.copy()
        grid_records["Area_mar_km2"] = grid_records.geometry.area / 1_000_000
        return {"grid_with_records": grid_records, "lcbd": pd.DataFrame(lcbd_rows)}

    scale_results = {
        1: ms_result(fine_grid, [
            {"grid_id_scale":"f1","LCBD":0.2,"LCBD_p_adjust_BH":0.01,"hotspot":False,"hotspot_significant_raw":False,"hotspot_significant_fdr":False},
            {"grid_id_scale":"f2","LCBD":0.8,"LCBD_p_adjust_BH":0.01,"hotspot":True,"hotspot_significant_raw":True,"hotspot_significant_fdr":True},
        ]),
        5: ms_result(grid_5, [
            {"grid_id_scale":"m1","LCBD":1.0,"LCBD_p_adjust_BH":0.01,"hotspot":True,"hotspot_significant_raw":True,"hotspot_significant_fdr":True},
        ]),
        10: ms_result(grid_10, [
            {"grid_id_scale":"c1","LCBD":1.0,"LCBD_p_adjust_BH":0.01,"hotspot":True,"hotspot_significant_raw":True,"hotspot_significant_fdr":True},
        ]),
    }
    official_grids = {1:fine_grid, 5:grid_5, 10:grid_10}
    canonical, hierarchy, canonical_scale = _build_canonical_persistence(scale_results, official_grids)
    if canonical_scale != 1:
        fail("Canonical persistence support is not the finest available official grid")
    c = canonical.set_index("master_id")
    if int(c.loc["f2","hotspot_persistence"]) != 3 or not bool(c.loc["f2","is_hotspot_persistent_all_scales"]):
        fail("Three-scale persistence was not preserved on the displaced fine hotspot")
    if int(c.loc["f1","hotspot_persistence"]) != 2 or bool(c.loc["f1","is_hotspot_persistent_all_scales"]):
        fail("Fine-scale non-hotspot was incorrectly promoted to persistent at all scales")

    selected_5 = grid_5.copy()
    selected_5["Area_mar_km2"] = selected_5.geometry.area / 1_000_000
    aggregated_5 = _aggregate_persistence_to_selected(canonical, canonical_scale, 5, selected_5, official_grids).iloc[0]
    if int(aggregated_5["hotspot_1km"]) != 1:
        fail("A displaced 1-km hotspot was lost when aggregated to the selected 5-km official cell")
    assert_close(float(aggregated_5["hotspot_1km_fraction"]), 0.5, tol=1e-12)
    if not bool(aggregated_5["is_hotspot_persistent_all_scales"]):
        fail("All-scale fine support was lost during official polygon aggregation")

    missing_scale_results = {1: scale_results[1], 5: scale_results[5]}
    missing_grids = {1:fine_grid, 5:grid_5}
    canonical_missing, _, missing_scale = _build_canonical_persistence(missing_scale_results, missing_grids)
    if missing_scale != 1 or canonical_missing["n_scales_evaluable"].max() != 2:
        fail("Missing official scale was not retained as explicitly non-evaluable")
    if canonical_missing["is_hotspot_persistent_all_scales"].any():
        fail("Missing scale incorrectly redefined persistence across all requested scales")

    scale_results_partial = dict(scale_results)
    scale_results_partial[1] = ms_result(fine_grid, [
        {"grid_id_scale":"f2","LCBD":0.8,"LCBD_p_adjust_BH":0.01,"hotspot":True,"hotspot_significant_raw":True,"hotspot_significant_fdr":True},
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        canonical_partial, _, _ = _build_canonical_persistence(scale_results_partial, official_grids)
    partial_idx = canonical_partial.set_index("master_id")
    if pd.notna(partial_idx.loc["f1", "hotspot_1km"]):
        fail("A non-evaluable canonical cell was silently converted to a zero hotspot flag")

    multiscale_source = (edition_root / "src" / "hippodec_maps" / "multiscale.py").read_text(encoding="utf-8")
    if "def _grid_table" in multiscale_source or "def _official_hotspot_crosswalk" in multiscale_source:
        fail("Synthetic Cartesian grid/ecological crosswalk code remains in the multiscale implementation")
    if "bray_curtis_matrix(transformed)" in multiscale_source:
        fail("The invalid Hellinger-to-Bray-Curtis multiscale path has reappeared")
    if "mantel_spearman(jaccard" not in multiscale_source:
        fail("Multiscale distance-decay is not using Mantel-Spearman on Jaccard incidence")

    # 13) Conservation QA regression: NA is valid only for cells that are not
    # evaluable; calculated values must remain in 0..100.  This reproduces the
    # national 1-km failure discovered during full national 1-km validation.
    qa_priority = pd.DataFrame({
        "ecological_priority_score": [0.0, 50.0, 100.0, np.nan],
        "ecological_priority_evaluable": [True, True, True, False],
    })
    ok, detail = _validate_priority_range(qa_priority)
    if not ok or detail["evaluable_missing_values"] != 0:
        fail(f"Priority QA rejected a legitimate non-evaluable NA: {detail}")

    qa_bad_range = qa_priority.copy()
    qa_bad_range.loc[1, "ecological_priority_score"] = 100.1
    ok, _ = _validate_priority_range(qa_bad_range)
    if ok:
        fail("Priority QA accepted a value above 100")

    qa_bad_missing = qa_priority.copy()
    qa_bad_missing.loc[0, "ecological_priority_score"] = np.nan
    ok, _ = _validate_priority_range(qa_bad_missing)
    if ok:
        fail("Priority QA accepted a missing score in an evaluable cell")

    # 14) UI regression checks for density units/formatting and previous font warning.
    templates = edition_root / "src" / "hippodec_maps" / "templates"
    template_text = "\n".join(p.read_text(encoding="utf-8") for p in templates.glob("*.html"))
    lowered = template_text.casefold()
    for obsolete in ("ind./1.000 km", "ind/1.000 km", "ind./1000 km", "ind/1000 km"):
        if obsolete.casefold() in lowered:
            fail(f"Obsolete density unit remains in templates: {obsolete}")
    if "semibold" in "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in (edition_root / "src" / "hippodec_maps").glob("*.py")
    ).casefold():
        fail("Obsolete semibold font request remains in Python source")

    # 15) FASE 9: visible conservation layer control and precise regional/conservation logs.
    pipeline_text = (edition_root / "src" / "hippodec_maps" / "pipeline.py").read_text(encoding="utf-8")
    conservation_text = (edition_root / "src" / "hippodec_maps" / "conservation.py").read_text(encoding="utf-8")
    map2_template = (templates / "map2.html").read_text(encoding="utf-8")
    map3_template = (templates / "map3.html").read_text(encoding="utf-8")
    for template_name, density_template in (("map2.html", map2_template), ("map3.html", map3_template)):
        for token in ("function percentile(values,q)", "function densityLegendScale(values)", "positive.length>=20", "percentile(positive,0.95)"):
            if token not in density_template:
                fail(f"Robust P95 density legend missing from {template_name}: {token}")
    if "currentScale=densityLegendScale(values)" not in map2_template:
        fail("Map 2 does not recalculate the robust density scale after species filtering")
    if "variable==='density'" not in map3_template or "scaleState=densityLegendScale(values)" not in map3_template:
        fail("Map 3 density variable does not use the robust density scale")

    conservation_template = (templates / "conservation.html").read_text(encoding="utf-8")
    if "collapsed:false,position:'topright'" not in conservation_template:
        fail("Conservation layer control is not permanently visible")
    if edition_root.name == "PYTHON_ESP":
        if "Registros en el ámbito regional canónico" not in pipeline_text:
            fail("Canonical regional-scope log is missing in Spanish")
        if "Resolución descriptiva de prioridad" not in conservation_text:
            fail("Explicit descriptive conservation resolution is missing in Spanish")
        if "CAPAS / MAPAS BASE" not in conservation_template:
            fail("Visible Spanish layer-control heading is missing")
    else:
        if "Records in canonical regional scope" not in pipeline_text:
            fail("Canonical regional-scope log is missing in English")
        if "Descriptive priority resolution" not in conservation_text:
            fail("Explicit descriptive conservation resolution is missing in English")
        if "LAYERS / BASE MAPS" not in conservation_template:
            fail("Visible English layer-control heading is missing")

    print(f"PASS: {edition_root.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("edition_root", type=Path)
    args = parser.parse_args()
    run(args.edition_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
