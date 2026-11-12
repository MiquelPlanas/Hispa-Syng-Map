"""Original observation metadata survives both presentation/export pipelines."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'src'))
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from hippodec_maps.localization import translate_frame,translate_geodataframe,translate_column_name
from hippodec_maps.pipeline import _csv2,_presentation_json
row={'Id':'Alta','grid_id':'region:Alta','sampling_event_id':'Alta:observaciones',
     'Comments':'Alta abundancia en praderas marinas','Observer':'Alta Mar',
     'Link_observation':'https://example.org/litoral/observaciones',
     'source_file':'litoral/observaciones.csv','Species':'Hippocampus guttulatus',
     'density':1.23456,'metric':0.123456789}
frame=pd.DataFrame([row]);original=frame.copy(deep=True)
with tempfile.TemporaryDirectory() as td:
    path=Path(td)/'export.csv';_csv2(frame,path)
    csv=pd.read_csv(path,sep=';',decimal=',',encoding='utf-8-sig')
    spatial=translate_geodataframe(gpd.GeoDataFrame(frame,geometry=[Point(-3,40)],crs='EPSG:4326'))
    attributes=json.loads(spatial.to_json())['features'][0]['properties']
    presented=_presentation_json(row)
    for field,value in row.items():
        if isinstance(value,str):
            label=translate_column_name(field)
            assert csv.loc[0,label]==value,(field,csv.loc[0,label])
            assert attributes[label]==value,(field,attributes[label])
            assert presented[field]==value,(field,presented[field])
    assert csv.loc[0,translate_column_name('density')]==1.23
    assert csv.loc[0,translate_column_name('metric')]==row['metric']
    pd.testing.assert_frame_equal(frame,original)
print('PASS CSV, GeoJSON and JSON metadata integrity; density formatting and input immutability')
