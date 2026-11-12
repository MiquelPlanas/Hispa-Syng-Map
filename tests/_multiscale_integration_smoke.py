from __future__ import annotations
import sys,tempfile
from pathlib import Path
import pandas as pd, numpy as np, geopandas as gpd
from shapely.geometry import Point,Polygon
edition=Path(sys.argv[1]).resolve(); sys.path.insert(0,str(edition/'src'))
from hippodec_maps.multiscale import run_multiscale_analysis
from hippodec_maps.analysis_utils import AnalysisSettings
from hippodec_maps.analysis_io import OutputRegistry
from hippodec_maps.cartography import MapContext

def grid(scale, specs):
    rows=[]
    for i,(gid,x0,x1) in enumerate(specs):
        area=((x1-x0)*(x1-x0))/1e6
        rows.append({'grid_id':gid,'official_cell_code':gid,'Area_mar_km2':area,'Area_celda_km2':area,'Area_mar_source':'gshhs_clipped_geometry','official_marine_flag':True,'grid_order':i,'Region_slug':'r','Region_MITECO':'R','geometry':Polygon([(x0,0),(x1,0),(x1,x1-x0),(x0,x1-x0)])})
    return gpd.GeoDataFrame(rows,geometry='geometry',crs='EPSG:3035')

g1=grid(1,[('f1',0,1000),('f2',4000,5000),('f3',10000,11000),('f4',14000,15000)])
g5=grid(5,[('m1',0,5000),('m2',10000,15000)])
g10=grid(10,[('c1',0,10000),('c2',10000,20000)])
rows=[]; oid=0
patterns={'f1':['A','B'],'f2':['A','C'],'f3':['B','C'],'f4':['A','B']}
for gid,geom in zip(g1.grid_id,g1.geometry):
    c=geom.centroid
    for ev,sp in enumerate(patterns[gid]):
        oid+=1
        rows.append({'obs_id':oid,'Species':sp,'N_total':float(ev+1),'Depth':3+ev,'Habitat':'h1','year':2024+ev,'sampling_event_id':f'{gid}_e{ev}','Region_slug':'r','Region_MITECO':'R','geometry':Point(c.x,c.y)})
assigned=gpd.GeoDataFrame(rows,geometry='geometry',crs='EPSG:3035')
# community data on selected 5-km grid
community={
 'environment_grid': pd.DataFrame({'grid_id':['m1','m2'],'n_records':[4,4],'n_sampling_events':[4,4],'n_years_observed':[2,2],'depth_median':[3.5,3.5],'n_depth_valid':[4,4],'habitat_dominant':['h1','h1']}),
 'indices_cells': pd.DataFrame({'grid_id':['m1','m2'],'richness':[3,3],'abundance':[6.,6.]}),
 'lcbd': pd.DataFrame({'grid_id':['m1','m2'],'LCBD':[0.5,0.5],'LCBD_p_value':[0.1,0.1],'LCBD_p_adjust_BH':[0.2,0.2],'LCBD_significant_raw':[False,False],'LCBD_significant_FDR':[False,False],'hotspot_lcbd':[False,False],'hotspot_lcbd_fdr':[False,False]}),
 'clusters': pd.DataFrame({'grid_id':['m1','m2'],'community_cluster':[1,2]}),
}
with tempfile.TemporaryDirectory(prefix='ms_smoke_') as td:
    root=Path(td); dirs={k:root/k for k in ['02_intermedios','04_tablas','05_figuras','06_modelos','07_debug']}
    for p in dirs.values(): p.mkdir(parents=True,exist_ok=True)
    empty=gpd.GeoDataFrame({'geometry':[]},geometry='geometry',crs='EPSG:3035')
    context=MapContext(land=empty,coastline=empty,bounds=(0,0,20000,10000),qa={})
    out=run_multiscale_analysis(assigned,dirs,AnalysisSettings(permutations=9,random_seed=7,min_records_cell=2),OutputRegistry(root),context,5,g5,community,official_multiscale_grids={1:g1,5:g5,10:g10})
    print('statuses', {k:v['status'] for k,v in out['scale_results'].items()})
    print('canonical',out['canonical_support_scale_km'])
    print(out['summary'][['scale_km','analysis_status','n_cells_evaluable','distance_decay_mantel_p_value']].to_string(index=False))
    print(out['master_hotspots'][['master_id','hotspot_persistence','n_scales_evaluable']].to_string(index=False))
    assert out['canonical_support_scale_km']==1
    assert all(v['status']=='estimable' for v in out['scale_results'].values())
    assert not out['master_hotspots'].empty
    assert out['spatial_qa']['status'].isin(['PASS','WARN']).all()
    expected_folder='multiescala' if edition.name=='PYTHON_ESP' else 'multiscale'
    for parent in ('04_tablas','05_figuras','06_modelos'):
        assert (root/parent/expected_folder).is_dir(), (parent,expected_folder)
    print('PASS',edition.name)
