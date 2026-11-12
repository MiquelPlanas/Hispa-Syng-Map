"""Regression for official context points and repaired aggregate polygons."""
import copy,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import geopandas as gpd
from shapely.geometry import Point,MultiPoint,Polygon,GeometryCollection,LineString,shape
ROOT=Path(__file__).resolve().parents[1];edition=Path(sys.argv[1]).resolve();sys.path.insert(0,str(edition/'src'));sys.path.insert(0,str(ROOT/'herramientas'))
from hippodec_maps.maps import common_context,render_map2,render_conservation_map
from hippodec_maps.config import RunParameters
from hippodec_maps.cartography import feature_collection,MapContext
from hippodec_maps.conservation import _interactive_map
from hippodec_maps.output_policy import public_product,polygonal_public_features,register_public_output
import hispa_security as sec
empty={'type':'FeatureCollection','features':[]}
polygon=Polygon([(-8,42),(-7.99,42),(-7.99,42.01),(-8,42.01),(-8,42)])
mixed=GeometryCollection([polygon,Point(-8.01,42),LineString([(-8,42),(-8.01,42)])])
frame=gpd.GeoDataFrame({'master_id':['g1'],'n_records':[5],'geometry':[mixed]},crs=4326)
collection=feature_collection(frame,['master_id','n_records']);before=copy.deepcopy(collection)
clean=polygonal_public_features(collection)
assert shape(clean['features'][0]['geometry']).area==mixed.area
assert collection==before and frame.geometry.iloc[0].equals_exact(mixed,0)
context=common_context(RunParameters(1992,2026,1,'all',('Hippocampus guttulatus',)),'')
protected=gpd.GeoDataFrame({'protected_name':['Official site','Official sites'],'protected_type':['Catalog','Catalog'],'protected_level':['National','National'],'protected_source':['official_source.shp','official_source.shp'],'geometry':[Point(-8,42),MultiPoint([(-8,42),(-7.99,42.01)])]},crs=4326)
fields=['protected_name','protected_type','protected_level','protected_source']
with tempfile.TemporaryDirectory() as td:
    root=Path(td);empty_frame=gpd.GeoDataFrame({'geometry':[]},crs=4326)
    for mode in ['open','protected']:
        with patch.dict(os.environ,{'HISPA_SYNG_SECURITY_MODE':mode}):
            path=root/(mode+'.html')
            # Actual conservation layer preparation and rendering, not a policy mock.
            _interactive_map(frame,frame,empty_frame,empty_frame,protected,path,
                MapContext(land=empty_frame,coastline=empty_frame,bounds=(-8.1,41.9,-7.8,42.2),qa={}),context)
            assert public_product(path)=='aggregate_conservation'
            assert 'official_source.shp' in path.read_text()
            register_public_output(path,'aggregate_conservation')  # Re-read embedded JSON independently.
            m2=render_map2(root/(mode+'_map2.html'),collection,[],empty,empty,context,False)
            assert public_product(m2)=='aggregate_map2'
    print('PASS open/protected conservation with official Point/MultiPoint context and mixed polygon geometry')
    assert frame.geometry.iloc[0].equals_exact(mixed,0)
    point_cells=copy.deepcopy(collection);point_cells['features'][0]['geometry']={'type':'Point','coordinates':[-8,42]}
    bad_protected=feature_collection(protected,fields);bad_protected['features'][0]['properties']['Observer']='INDIVIDUAL_CANARY'
    for label,cells,layer in [('observation',point_cells,empty),('metadata',collection,bad_protected)]:
        try:render_conservation_map(root/(label+'.html'),cells,empty,empty,empty,layer,empty,(-8.1,41.9,-7.8,42.2),context)
        except ValueError:pass
        else:raise AssertionError('Individual record accepted: '+label)
        assert not (root/(label+'.html')).exists()
    wrong_context=root/'wrong_context.html';wrong_context.write_text('<html><script>const protectedAreas='+json.dumps(feature_collection(protected,fields))+';</script></html>')
    try:register_public_output(wrong_context,'aggregate_map2')
    except ValueError:pass
    else:raise AssertionError('Official-point exception escaped conservation product')
    print('PASS individual points/metadata still rejected; official exception limited to typed conservation layer; geometry unchanged')
