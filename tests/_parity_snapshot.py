from __future__ import annotations
import json, sys
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, Polygon, box

edition=Path(sys.argv[1]).resolve(); sys.path.insert(0,str(edition/'src'))
from hippodec_maps.metrics import calculate_metrics
from hippodec_maps.sampling import add_sampling_event_ids
from hippodec_maps.temporal import _symmetric_relative_change, Period, _official_temporal_signal
from hippodec_maps.optional_analysis import _gower_numeric, _functional_space, _select_global_dimensions, _functional_metrics
from hippodec_maps.conservation import _build_priority_products

# Density snapshot.
geom=Polygon([(0,0),(1000,0),(1000,500),(0,500)])
grid=gpd.GeoDataFrame({'grid_id':['g1'],'Area_mar_km2':[0.5],'official_cell_code':['g1'],'Region_MITECO':['T'],'Region_slug':['t'],'geometry':[geom]},crs='EPSG:3857')
assigned=gpd.GeoDataFrame({'obs_id':[1,2],'grid_id':['g1','g1'],'Species':['Species alpha']*2,'N_total':[1.,2.],'Fecha_aux':['2024-01-01','2025-01-01'],'Area_mar_km2':[0.5,0.5],'Area_celda_km2':[0.5,0.5],'Area_mar_source':['gshhs_clipped_geometry']*2,'dist_to_cell_m':[0.,0.],'N hembra':[0,0],'N macho':[0,0],'N_indeterminado':[1,2],'Region_MITECO':['T','T'],'geometry':[Point(100,100),Point(200,100)]},crs='EPSG:3857')
_,cells,species,_,_=calculate_metrics(assigned,grid,1)

# Event identity snapshot.
events=gpd.GeoDataFrame({'source_row':[2,3,4],'Fecha_aux':pd.to_datetime(['2024-06-01']*3),'Observer':[' Alice  Smith ','alice smith','Bob'],'Species':['A','B','A'],'Id':['x','y','z'],'geometry':[Point(0,0),Point(.4,.4),Point(0,0)]},geometry='geometry',crs='EPSG:3035')
evented=add_sampling_event_ids(events)

# Temporal snapshot, including explicit zero-period and two-period states.
tab=pd.DataFrame([
 {'grid_id':'g1','Species':'A','period':'P1','year':2020,'N_aux':2.,'sampling_event_id':'e1','Area_mar_km2':1.0},
 {'grid_id':'g1','Species':'A','period':'P1','year':2021,'N_aux':4.,'sampling_event_id':'e2','Area_mar_km2':1.0},
 {'grid_id':'g1','Species':'A','period':'P2','year':2022,'N_aux':8.,'sampling_event_id':'e3','Area_mar_km2':1.0},
 {'grid_id':'g1','Species':'A','period':'P2','year':2023,'N_aux':4.,'sampling_event_id':'e4','Area_mar_km2':1.0},
])
p0,_=_official_temporal_signal(tab,[])
periods=[Period('P1',pd.Timestamp('2020-01-01'),pd.Timestamp('2021-12-31')),Period('P2',pd.Timestamp('2022-01-01'),pd.Timestamp('2023-12-31'))]
p2,_=_official_temporal_signal(tab,periods)
mag,signed=_symmetric_relative_change(pd.Series([10.]),pd.Series([20.]))

# Functional snapshot.
traits=pd.DataFrame({'t1':[0.,1.,0.5,0.2],'t2':[1.,0.,0.2,0.8],'t3':[0.1,0.6,1.,0.3]})
gower=_gower_numeric(traits); fspace=_functional_space(gower); dims,_=_select_global_dimensions(fspace,len(traits))
fm=_functional_metrics(fspace,list(range(len(traits))),np.ones(len(traits)),dims,1.0)

# Conservation snapshot.
pgrid=gpd.GeoDataFrame({
 'master_id':['a','b','c'],'LCBD':[0.1,0.3,0.9],'richness':[1,2,3],'abundance':[2,2,2],
 'hotspot_lcbd':[False,False,True],'hotspot_persistence':[0,1,3],'is_hotspot_any_scale':[False,True,True],
 'is_hotspot_multiscale':[False,False,True],'is_hotspot_persistent_all_scales':[False,False,True],
 'n_sampling_events':[3,5,10],'n_records':[3,5,10],'n_years_observed':[2,3,5],'n_scales_evaluable':[3,3,3],
 'multiscale_support_evaluable':[True,True,True],'n_depth_valid':[2,3,8],'depth_mediana_grid':[3.,4.,5.],
 'habitat_dominante_grid':['h']*3,'temporal_signal_raw':[0.1,0.5,0.9],'n_temporal_records':[3,5,10],
 'Area_mar_km2':[1.,1.,1.],'geometry':[box(0,0,1000,1000),box(1000,0,2000,1000),box(2000,0,3000,1000)]},geometry='geometry',crs='EPSG:3035')
rows=[]
for gid,x,n in [('a',500,3),('b',1500,5),('c',2500,10)]:
 for i in range(n): rows.append({'grid_id':gid,'Observer':f'o{i%3}','Depth':3+i if i%2==0 else np.nan,'Habitat':'h' if i%3 else pd.NA,'geometry':Point(x,500)})
a=gpd.GeoDataFrame(rows,geometry='geometry',crs='EPSG:3035')
priority,diag=_build_priority_products(pgrid,a)

def rnd(x):
 if x is None or pd.isna(x): return None
 return round(float(x),12)

snapshot={
 'density_cell':rnd(cells.loc[0,'Densidad_total']),
 'density_species':rnd(species.loc[0,'Densidad_ajustada']),
 'event_ids':evented.sort_values('source_row')['sampling_event_id'].astype(str).tolist(),
 'event_unique':int(evented['sampling_event_id'].nunique()),
 'temporal_zero_period_rows':int(len(p0)),
 'temporal_two_period_signal':[] if p2.empty else [rnd(x) for x in p2.sort_values('grid_id')['temporal_signal_raw']],
 'symmetric_change':[rnd(mag.iloc[0]),rnd(signed.iloc[0])],
 'gower':[[rnd(x) for x in row] for row in gower.tolist()],
 'functional_dims':int(dims),
 'functional':{k:rnd(v) for k,v in fm.items() if isinstance(v,(int,float,np.integer,np.floating))},
 'ecological_priority_score':[rnd(x) for x in priority['ecological_priority_score']],
 'monitoring_score':[rnd(x) for x in priority['monitoring_priority_score']],
 'data_adequacy_score':[rnd(x) for x in priority['data_adequacy_score']],
 'ecological_priority_class':priority['ecological_priority_class'].astype(str).tolist(),
 'lcbd_context_informative':bool(diag['lcbd_context_informative']),
 'abundance_context_informative':bool(diag['abundance_context_informative']),
}
print(json.dumps(snapshot,sort_keys=True,ensure_ascii=False))
