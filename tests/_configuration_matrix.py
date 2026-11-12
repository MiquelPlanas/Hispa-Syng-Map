from __future__ import annotations
import sys
from pathlib import Path
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon
edition=Path(sys.argv[1]).resolve(); sys.path.insert(0,str(edition/'src'))
from hippodec_maps.config import RunParameters
from hippodec_maps.data import filter_observations, parse_species_argument
from hippodec_maps.regions import filter_region
from hippodec_maps.metrics import calculate_metrics
from hippodec_maps.temporal import Period, _official_temporal_signal

# all/common/rare species filters on the same normal multiespecies dataset.
rows=[]
for i in range(6): rows.append({'Species':'Common species','Fecha_aux':pd.Timestamp('2024-06-01'),'Longitude':-5.,'Latitude':43.,'X':0.,'Y':0.,'EPSG':4326})
rows.append({'Species':'Rare species','Fecha_aux':pd.Timestamp('2024-06-01'),'Longitude':-5.,'Latitude':43.,'X':0.,'Y':0.,'EPSG':4326})
data=pd.DataFrame(rows)
available=['Common species','Rare species']
for token in ('all','todos','todas','0'):
    assert parse_species_argument([token],available)==tuple(available)
for selected,expected in [(('Common species','Rare species'),7),(('Common species',),6),(('Rare species',),1)]:
 p=RunParameters(2024,2024,5,'all',selected)
 got,_,_=filter_observations(data,p)
 assert len(got)==expected,(selected,len(got),expected)

# global and isolated-region paths.
points=gpd.GeoDataFrame({'Region_slug':['cantabrica','alboran'],'geometry':[Point(0,0),Point(1,1)]},geometry='geometry',crs='EPSG:3035')
assert len(filter_region(points,'all'))==2
assert len(filter_region(points,'cantabrica'))==1

# 1/5/10 km configuration: density formula remains N / marine km² at every requested resolution.
for km in (1,5,10):
 geom=Polygon([(0,0),(1000,0),(1000,500),(0,500)])
 grid=gpd.GeoDataFrame({'grid_id':['g1'],'Area_mar_km2':[0.5],'official_cell_code':['g1'],'Region_MITECO':['T'],'Region_slug':['t'],'geometry':[geom]},crs='EPSG:3857')
 assigned=gpd.GeoDataFrame({'obs_id':[1,2],'grid_id':['g1','g1'],'Species':['A','A'],'N_total':[1.,2.],'Fecha_aux':['2024-01-01','2024-02-01'],'Area_mar_km2':[0.5,0.5],'Area_celda_km2':[0.5,0.5],'Area_mar_source':['gshhs_clipped_geometry']*2,'dist_to_cell_m':[0.,0.],'N hembra':[0,0],'N macho':[0,0],'N_indeterminado':[1,2],'Region_MITECO':['T','T'],'geometry':[Point(100,100),Point(200,100)]},crs='EPSG:3857')
 _,cells,_,_,qa=calculate_metrics(assigned,grid,km)
 assert abs(float(cells.loc[0,'Densidad_total'])-6.)<1e-12

# 0 comparative periods gives no signal; >=2 gives an estimable signal.
tab=pd.DataFrame([
 {'grid_id':'g1','Species':'A','period':'P1','year':2020,'N_aux':1.,'sampling_event_id':'e1','Area_mar_km2':1.},
 {'grid_id':'g1','Species':'A','period':'P1','year':2021,'N_aux':2.,'sampling_event_id':'e2','Area_mar_km2':1.},
 {'grid_id':'g1','Species':'A','period':'P2','year':2022,'N_aux':4.,'sampling_event_id':'e3','Area_mar_km2':1.},
 {'grid_id':'g1','Species':'A','period':'P2','year':2023,'N_aux':8.,'sampling_event_id':'e4','Area_mar_km2':1.},
])
zero,_=_official_temporal_signal(tab,[]); assert zero.empty
two=[Period('P1',pd.Timestamp('2020-01-01'),pd.Timestamp('2021-12-31')),Period('P2',pd.Timestamp('2022-01-01'),pd.Timestamp('2023-12-31'))]
signal,_=_official_temporal_signal(tab,two); assert len(signal)==1 and pd.notna(signal.loc[0,'temporal_signal_raw'])
print('PASS configuration matrix',edition.name)
