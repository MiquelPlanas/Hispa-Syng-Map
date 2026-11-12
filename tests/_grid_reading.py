"""Compare single-query spatial reads against the per-window reference."""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import Point, Polygon, MultiPolygon, box

edition = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(edition / 'src'))
from hippodec_maps import grids


def reference(path, info, points, region, scale, factor):
    if info.get('total_bounds') is None:
        bbox = grids._bbox_for_points(points, info['crs'], region, scale * 1000 * factor)
        if bbox is None:
            return None, [], 'single_bbox_fallback'
        return gpd.read_file(path, bbox=bbox, engine='pyogrio'), [bbox], 'single_bbox_fallback'
    windows = grids._tiled_bboxes_for_points(points, info['crs'], region, scale * 1000 * factor, info['total_bounds'])
    chunks = [gpd.read_file(path, bbox=b, engine='pyogrio', fid_as_index=True) for b in windows]
    chunks = [c for c in chunks if not c.empty]
    if not chunks:
        return None, windows, 'reference'
    result = gpd.GeoDataFrame(pd.concat(chunks), geometry='geometry', crs=chunks[0].crs)
    return result.loc[~result.index.duplicated(keep='first')].sort_index().reset_index(drop=True), windows, 'reference'


def identical(a, b):
    if a is None or b is None:
        assert a is None and b is None
        return
    assert_geodataframe_equal(a, b, check_like=False)
    assert a.geometry.to_wkb().tolist() == b.geometry.to_wkb().tolist()


with tempfile.TemporaryDirectory(prefix='hispa_grid_read_') as td:
    root = Path(td)
    geometry = [box(4000000 + x * 1000, 3000000 + y * 1000, 4001000 + x * 1000, 3001000 + y * 1000)
                for x in range(160) for y in range(4)]
    geometry += [Polygon([(4010000,3000000),(4015000,3000000),(4015000,3005000),(4010000,3005000)],
                         holes=[[(4011000,3001000),(4014000,3001000),(4014000,3004000),(4011000,3004000)]]),
                 MultiPolygon([box(4020000,3005000,4021000,3006000),box(4120000,3005000,4121000,3006000)])]
    raw = gpd.GeoDataFrame({'id':np.arange(len(geometry)), 'MARINO':np.ones(len(geometry),dtype=int)},geometry=geometry,crs=3035)
    points = gpd.GeoDataFrame({'Region_slug':['noratlantica']*4},geometry=[Point(4001000,3001000),Point(4050500,3001500),Point(4100500,3001500),Point(4159500,3001500)],crs=3035)
    # Derive the package's actual normalized region code from the filename.
    for scale in (1,5,10):
        path = root / f'Malla{scale}x{scale}km_noratlantica.shp'
        raw.to_file(path,engine='pyogrio')
        region = grids.region_from_grid_path(path)
        points['Region_slug'] = region
        info = pyogrio.read_info(path)
        expected, windows, _ = reference(path,info,points,region,scale,1.25)
        with patch.object(gpd,'read_file',wraps=gpd.read_file) as reads:
            actual, actual_windows, strategy = grids._read_grid_near_points(path,info,points,region,scale,1.25)
            expected_reads = 1 if pyogrio.__gdal_geos_version__ is not None else len(windows)
            assert reads.call_count == expected_reads, reads.call_count
        assert windows == actual_windows
        assert strategy == (f'union_windows_{scale}km' if pyogrio.__gdal_geos_version__ is not None else f'tiled_bbox_{scale}km')
        identical(expected,actual)
        prepared, _ = grids.load_grids(root,scale,'all',points)
        with patch.object(grids,'_read_grid_near_points',side_effect=reference):
            prepared_reference, _ = grids.load_grids(root,scale,'all',points)
        identical(prepared_reference,prepared)
        with patch.object(pyogrio,'__gdal_geos_version__',None):
            compatible, _, _ = grids._read_grid_near_points(path,info,points,region,scale,1.25)
        identical(expected,compatible)
        no_bounds = dict(info,total_bounds=None)
        identical(reference(path,no_bounds,points,region,scale,1.25)[0],
                  grids._read_grid_near_points(path,no_bounds,points,region,scale,1.25)[0])
        empty_points = points.iloc[:0]
        assert grids._read_grid_near_points(path,info,empty_points,region,scale,1.25)[0] is None
        # Identical polygons/areas must also give identical direct/nearest assignments.
        from hippodec_maps.spatial import prepare_marine_grid_areas, assign_points_to_grid
        land_path = root/'GSHHS_h_L1.shp'
        gpd.GeoDataFrame(geometry=[box(4000000,3000000,4000500,3004000)],crs=3035).to_file(land_path,engine='pyogrio')
        clipped_ref, qa_ref = prepare_marine_grid_areas(prepared_reference,land_path,cache_dir=root/'cache',resolution_km=scale)
        clipped_new, qa_new = prepare_marine_grid_areas(prepared,land_path,cache_dir=root/'cache',resolution_km=scale)
        identical(clipped_ref,clipped_new)
        observations = points.copy()
        observations['obs_id'] = np.arange(len(observations))
        a_ref, u_ref, q_ref = assign_points_to_grid(observations,clipped_ref,1500)
        a_new, u_new, q_new = assign_points_to_grid(observations,clipped_new,1500)
        identical(a_ref,a_new)
        identical(u_ref,u_new)
        assert q_ref == q_new
        assert qa_new['marine_area_cache_cells_computed']==0
        print(f'PASS {edition.name}: {scale}km; {len(windows)} windows -> one read; {len(actual)} cells; exact IDs, attributes, WKB, areas and warm area cache')
    # A projected source CRS different from the analysis CRS.
    path=root/'projected.shp'
    raw.to_crs(25830).to_file(path,engine='pyogrio')
    info=pyogrio.read_info(path)
    identical(reference(path,info,points,region,1,1.25)[0],grids._read_grid_near_points(path,info,points,region,1,1.25)[0])
    # Degenerate edge window must retain the original driver semantics.
    with patch.object(grids,'_tiled_bboxes_for_points',return_value=[(4000000,3000000,4000000,3004000)]):
        path=root/'Malla1x1km_noratlantica.shp';info=pyogrio.read_info(path)
        identical(reference(path,info,points,region,1,1.25)[0],grids._read_grid_near_points(path,info,points,region,1,1.25)[0])
print('PASS spatial read equivalence and compatibility')
