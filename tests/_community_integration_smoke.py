from __future__ import annotations
import sys, tempfile
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import Point, Polygon

edition=Path(sys.argv[1]).resolve(); sys.path.insert(0,str(edition/'src'))
from hippodec_maps.community import run_community_analysis
from hippodec_maps.analysis_utils import AnalysisSettings
from hippodec_maps.analysis_io import OutputRegistry
from hippodec_maps.cartography import MapContext

with tempfile.TemporaryDirectory(prefix='community_smoke_') as td:
    root=Path(td)
    dirs={k:root/k for k in ['02_intermedios','04_tablas','05_figuras','06_modelos']}
    for p in dirs.values(): p.mkdir(parents=True,exist_ok=True)
    polys=[]; cell_ids=[]; regions=[]
    for i in range(8):
        x=(i%4)*2000; y=(i//4)*2000
        polys.append(Polygon([(x,y),(x+1000,y),(x+1000,y+1000),(x,y+1000)]))
        cell_ids.append(f'g{i+1}'); regions.append('R1' if i<4 else 'R2')
    cells=gpd.GeoDataFrame({'grid_id':cell_ids,'Region_MITECO':regions,'geometry':polys},crs='EPSG:3035')
    rows=[]
    patterns={
      'g1':{'spA':5,'spB':1}, 'g2':{'spA':4,'spB':2}, 'g3':{'spA':2,'spC':3}, 'g4':{'spA':1,'spC':5},
      'g5':{'spB':5,'spD':1}, 'g6':{'spB':3,'spD':3}, 'g7':{'spC':2,'spD':5}, 'g8':{'spC':1,'spD':6},
    }
    for i,(gid,reg,geom) in enumerate(zip(cell_ids,regions,polys)):
        c=geom.centroid
        for j,(sp,n) in enumerate(patterns[gid].items()):
            rows.append({
                'grid_id':gid,'Species':sp,'N_total':float(n),'Fecha_aux':pd.Timestamp(f'202{j}-06-{i+1:02d}'),
                'Depth':float(3+i),'Temperatura_gC':16.0+i/10,'Habitat':'h1' if i%2==0 else 'h2',
                'Region_MITECO':reg,'Latitude':42+i/100,'Longitude':-8+i/100,
                'sampling_event_id':f'{gid}_event_{j}', 'geometry':Point(c.x+10*j,c.y+10*j),
            })
    assigned=gpd.GeoDataFrame(rows,geometry='geometry',crs='EPSG:3035')
    metrics=pd.DataFrame({'grid_id':cell_ids,'Densidad_total':np.linspace(1,8,8)})
    empty=gpd.GeoDataFrame({'geometry':[]},geometry='geometry',crs='EPSG:3035')
    context=MapContext(land=empty,coastline=empty,bounds=(0,0,8000,4000),qa={})
    reg=OutputRegistry(root)
    out=run_community_analysis(assigned,cells,metrics,dirs,AnalysisSettings(permutations=49,random_seed=123,bootstrap_iterations=20),reg,context)
    assert 'lcbd' in out and not out['lcbd'].empty
    lc=out['lcbd']
    for col in ['LCBD_p_adjust_BH','LCBD_hellinger','LCBD_hellinger_p_adjust_BH','n_sampling_events','hotspot_lcbd_fdr']:
        assert col in lc.columns, col
    dd=out['distance_decay_summary']
    assert 'mantel_rho' in dd and 'mantel_p_value' in dd
    assert np.isnan(float(dd['p_value_slope']))
    assert out['pcoa_lingoes_diagnostics']['correction'] in {'none','lingoes'}
    assert 'hellinger' in str(out['permanova']['analysis_method']).casefold()
    if isinstance(out.get('permanova_clusters'),dict) and out['permanova_clusters']:
        assert out['permanova_clusters'].get('confirmatory_inference') is False
    print('PASS community integration', edition.name, 'outputs', len(reg.records))
