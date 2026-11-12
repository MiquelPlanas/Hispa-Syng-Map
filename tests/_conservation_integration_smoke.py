from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault('MPLBACKEND','Agg')
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box, Point

edition=Path(sys.argv[1]).resolve(); sys.path.insert(0,str(edition/'src'))
from hippodec_maps.conservation import run_conservation_analysis
from hippodec_maps.analysis_io import OutputRegistry
from hippodec_maps.cartography import MapContext

# Synthetic official 5-km planning units. g1 is an extreme-LCBD singleton and must never be selected.
geoms=[box(i*5000,0,(i+1)*5000,5000) for i in range(4)]
planning=gpd.GeoDataFrame({
    'grid_id':['g1','g2','g3','g4'], 'scale_km':[5]*4,
    'n_records':[1,4,10,20], 'n_sampling_events':[1,4,10,20],
    'n_years_observed':[0,0,0,0], 'LCBD':[9.0,0.03,0.11,0.30],
    'LCBD_p_value':[0.001,0.4,0.04,0.005], 'LCBD_significant_raw':[True,False,True,True],
    'LCBD_significant_FDR':[True,False,True,True], 'richness':[1,2,3,4], 'abundance':[1,4,12,30],
    'hotspot':[True,False,True,True], 'hotspot_significant_fdr':[True,False,True,True],
    'depth_median':[3.,4.,5.,6.], 'n_depth_valid':[1,3,8,15],
    'habitat_dominant':['sand','seagrass','seagrass','macroalgae'],
    'Area_mar_km2':[20.,20.,20.,20.], 'Area_geometria_marina_km2':[25.,25.,25.,25.],
    'Region_MITECO':['R1','R1','R2','R2'], 'geometry':geoms,
},geometry='geometry',crs='EPSG:3035')

rows=[]
specs={'g1':(1,[2026]),'g2':(4,[2025,2026]),'g3':(10,[2024,2025,2026]),'g4':(20,[2022,2023,2024,2025,2026])}
for gi,(gid,(n,years)) in enumerate(specs.items()):
    for j in range(n):
        rows.append({
            'grid_id':f'fine_{gi}_{j%3}', 'grid_id_scale':gid,
            'Species':('Rare species' if gid=='g4' and j<5 else {
                'g1':['Common species 1'],
                'g2':['Common species 1','Common species 2'],
                'g3':['Common species 1','Common species 2','Common species 3'],
                'g4':['Common species 1','Common species 2','Common species 3'],
            }[gid][j%len({
                'g1':['Common species 1'],
                'g2':['Common species 1','Common species 2'],
                'g3':['Common species 1','Common species 2','Common species 3'],
                'g4':['Common species 1','Common species 2','Common species 3'],
            }[gid])]),
            'N_total':1+(j%2), 'Observer':f'obs{j%3}', 'Depth':float(2+j%7) if j%5 else np.nan,
            'Habitat':'seagrass' if j%4 else pd.NA, 'sampling_event_id':f'{gid}_e{j}',
            'Date of observation':f'15-06-{years[j%len(years)]}',
            'geometry':Point(gi*5000+2500,2500),
        })
planning_points=gpd.GeoDataFrame(rows,geometry='geometry',crs='EPSG:3035')
assigned=planning_points.copy(); assigned['grid_id']=assigned['grid_id'].astype(str)

# Synthetic 1-km descriptive cells matching the selected-resolution observation IDs.
fine_rows=[]
for fine_id in sorted(assigned['grid_id'].unique()):
    _,gi_text,sub_text=fine_id.split('_')
    gi=int(gi_text); sub=int(sub_text)
    x0=gi*5000+sub*1000
    fine_rows.append({
        'grid_id':fine_id,'grid_id_scale':fine_id,'scale_km':1,
        'Area_mar_km2':1.0,'Area_geometria_marina_km2':1.0,
        'geometry':box(x0,0,x0+1000,1000),
    })
fine_grid=gpd.GeoDataFrame(fine_rows,geometry='geometry',crs='EPSG:3035')

# Fallback 1-km master exists but must not replace the 5-km planning units.
fallback=planning.copy(); fallback['master_id']=fallback['grid_id']; fallback['scale_km']=1

temporal_official=pd.DataFrame({'grid_id':['g1','g2','g3','g4'],'temporal_signal_raw':[0.1,0.9,0.2,0.8],'n_temporal_records':[1,4,10,20],'n_temporal_sampling_events':[1,4,10,20]})
empty=gpd.GeoDataFrame({'geometry':[]},geometry='geometry',crs='EPSG:4326')
bounds=tuple(planning.to_crs(4326).total_bounds)
context=MapContext(land=empty,coastline=empty,bounds=bounds,qa={})

with tempfile.TemporaryDirectory(prefix='hispa_cons_integration_') as td:
    root=Path(td); dirs={'09_zonas_prioritarias_conservacion':root/'09_priority','07_debug':root/'07_debug'}
    for p in dirs.values(): p.mkdir(parents=True,exist_ok=True)
    registry=OutputRegistry(root)
    html_context={
        'priority_download_password_hash':'testhash','included_species':['Common species','Rare species'],
        'species_list':['Common species','Rare species'],'map_downloads':{'priority':{}},'language_switch':{'enabled':False},
        'brand_label':'Hispa-Syng v1.0','product':'Conservation integration smoke','project':'Hippo-DEC','institution':'IIM-CSIC',
        'author':'test','creation_date':'2026-09-24','grid_km':1,'region_label':'Synthetic','year_min':2021,'year_max':2026,'logo_uri':'',
    }
    # Synthetic GSHHS land strip removes the upper 1 km from every 5x5-km cell.
    # This reproduces the real pipeline distinction between full official MITECO
    # geometry (25 km²) and marine surface (20 km²). Conservation must use the
    # clipped 20-km² geometry, not merely trust the stored area column.
    land_path=root/'synthetic_gshhs.gpkg'
    land=gpd.GeoDataFrame({'geometry':[box(0,4000,20000,5000)]},geometry='geometry',crs='EPSG:3035')
    land.to_file(land_path,layer='land',driver='GPKG',engine='pyogrio')
    out=run_conservation_analysis(
        multiscale={'master_hotspots':fallback,'scale_results':{
            1:{'grid':fine_grid,'grid_all':fine_grid,'grid_with_records':fine_grid,'points':assigned},
            5:{'grid':planning,'grid_all':planning,'grid_with_records':planning,'points':planning_points},
        }},
        temporal={'temporal_signal_official':temporal_official}, protected_path=None, demarcations_path=None, logo_path=None,
        directories=dirs, registry=registry, cartographic_context=context, html_context=html_context,
        selected_grid_km=1, assigned=assigned, marine_mask=None, gshhg_path=land_path,
    )
    pg=out['priority_grid']
    descriptive=out['descriptive_priority_grid']
    assert not descriptive.empty
    assert descriptive['planning_grid_km'].eq(1).all()
    assert descriptive['selected_grid_km'].eq(1).all()
    assert descriptive['grid_purpose'].eq('descriptive').all()
    assert descriptive['zone_role_code'].eq('descriptive_only').all()
    assert set(descriptive['master_id'])==set(fine_grid['grid_id'])
    assert pg['planning_grid_km'].eq(5).all()
    assert pg['grid_purpose'].eq('planning').all()
    assert pg['selected_grid_km'].eq(1).all()
    assert pg['conservation_grid_source'].eq('official_miteco_5km_minimum_planning_unit').all()
    assert np.allclose(pg.geometry.area/1_000_000,20.0,rtol=1e-10,atol=1e-9)
    assert np.allclose(pd.to_numeric(pg['Area_geometria_marina_km2']),pd.to_numeric(pg['Area_mar_km2']),rtol=1e-10,atol=1e-9)
    assert pg['marine_geometry_status'].eq('validated_against_Area_mar_km2').all()
    assert pg.set_index('master_id').loc['g2','n_years_observed']==2
    assert pg.set_index('master_id').loc['g4','n_years_observed']==5
    # Singleton/high-LCBD safeguard and multi-evidence positive controls.
    assert pg.loc[pg.master_id.eq('g1'),'ecological_priority_class'].iloc[0] not in {'Alta','Muy alta'}
    assert pg.loc[pg.master_id.eq('g3'),'ecological_priority_class'].iloc[0]=='Alta'
    assert pg.loc[pg.master_id.eq('g4'),'ecological_priority_class'].iloc[0]=='Muy alta'
    assert int(pg.loc[pg.ecological_priority_class.isin(['Alta','Muy alta']),'n_years_observed'].min()) >= 2
    assert pg['n_independent_ecological_families_active'].max() <= 4
    # Temporal signal remains a separate product.
    assert np.isclose(pg.loc[pg.master_id.eq('g2'),'monitoring_priority_score'].iloc[0],90.0)
    assert not pg['ecological_priority_score'].equals(pg['monitoring_priority_score'])
    assert not out['selected_cells'].empty and not out['zones'].empty
    assert not out['operational_zones'].empty and not out['operational_evidence_cells'].empty
    assert set(out['operational_zones']['parent_zone_id'].astype(str)).issubset(set(out['zones']['zone_id'].astype(str)))
    assert pd.to_numeric(out['operational_zone_summary']['area_operational_km2'],errors='coerce').sum() < pd.to_numeric(out['zone_summary']['area_zone_km2'],errors='coerce').sum()
    # Spatial conservation roles are propagated independently of ecological class.
    assert 'zone_role_code' in pg.columns and 'zone_role' in pg.columns
    assert pg.loc[pg.master_id.eq('g2'),'zone_role_code'].iloc[0]=='supporting_extension', pg.loc[pg.master_id.eq('g2')]
    assert not out['zone_extensions'].empty and set(out['zone_extensions']['master_id'])=={'g2'}
    assert out['zone_extensions']['ecological_priority_class'].eq('Media').all()
    assert out['zone_cells']['zone_role_code'].isin({'priority_core','supporting_extension'}).all()
    assert int(out['zone_summary']['n_extension_cells'].sum())==1
    assert out['selected_cells']['ecological_priority_pathway_code'].isin({'convergence','persistent_occurrence','diversity_core','exceptional_diversity','persistent_occurrence_and_diversity'}).all()
    assert out['selected_cells'].loc[out['selected_cells'].ecological_priority_class.eq('Muy alta'),'ecological_priority_pathway_code'].eq('convergence').all()
    assert 'main_priority_pathway_code' in out['zone_summary'].columns and 'priority_pathway_counts' in out['zone_summary'].columns
    # If zonal spatial overlay is unavailable/misses a coast-clipped polygon,
    # the MITECO region must fall back to the priority-core planning units.
    assert out['zone_summary']['Region_MITECO_dominante'].eq('R2').all(), out['zone_summary'][['zone_id','Region_MITECO_dominante','Region_MITECO_lista']]
    assert out['zone_summary']['Region_MITECO_lista'].eq('R2').all(), out['zone_summary'][['zone_id','Region_MITECO_dominante','Region_MITECO_lista']]
    assert out['zone_summary']['protection_evaluation_status'].eq('not_evaluated').all()
    assert out['zone_summary']['pct_zone_protected'].isna().all()
    assert out['spatial_qa']['status'].eq('PASS').all(), out['spatial_qa']
    assert Path(out['interactive_map']).exists() and Path(out['interactive_map']).stat().st_size>0
    assert Path(out['report']).exists() and Path(out['report']).stat().st_size>0
    selected_n=len(out['selected_cells']); zones_n=len(out['zones'])
    assert selected_n==int(pg.ecological_priority_class.isin(['Alta','Muy alta']).sum())
    assert zones_n==len(out['zone_summary'])
    assert out['selected_cells']['zone_id'].nunique()==zones_n
    html_text=Path(out['interactive_map']).read_text(encoding='utf-8')
    assert 'selectedPriorityClasses' in html_text and 'data-filter-action="all"' in html_text and 'data-filter-action="none"' in html_text
    assert 'selectedSpatialRoles' in html_text and 'data-spatial-role' in html_text and "'supporting_extension'" in html_text and "'validation_candidate'" in html_text
    assert ('Filtrar prioridad y papel' in html_text and 'Papel espacial' in html_text) or ('Filter priority and role' in html_text and 'Spatial role' in html_text)
    assert ('unidad mínima de conservación <b>5 km</b>' in html_text) or ('minimum conservation unit <b>5 km</b>' in html_text)
    assert ('Prioridad descriptiva · 1 km' in html_text and 'Unidades de planificación · 5 km' in html_text) or ('Descriptive priority · 1 km' in html_text and 'Planning units · 5 km' in html_text)
    assert 'const descriptiveCells=' in html_text and 'hasSeparateDescriptiveGrid' in html_text
    assert 'const operationalZones=' in html_text and 'operationalZoneLayer' in html_text
    assert ('Zonas operativas de conservación · evidencia 1 km' in html_text) or ('Operational conservation areas · 1-km evidence' in html_text)
    assert ('Una observación aislada nunca basta' in html_text) or ('A single isolated observation can never' in html_text)
    assert ('tres vías' in html_text and 'núcleo de diversidad' in html_text) or ('three pathways' in html_text and 'diversity core' in html_text)
    assert ('Vía causal principal' in html_text and 'Vía causal dominante' in html_text) or ('Primary causal pathway' in html_text and 'Dominant causal pathway' in html_text)
    assert ('extensiones de apoyo' in html_text and 'candidatas para validación' in html_text) or ('supporting extensions' in html_text and 'validation candidates' in html_text)
    # When Node.js is available, also syntax-check the fully rendered inline JavaScript.
    import re, shutil, subprocess
    node=shutil.which('node')
    if node:
        scripts='\n'.join(re.findall(r'<script(?:[^>]*)>(.*?)</script>',html_text,flags=re.S))
        js_path=root/'conservation_rendered_check.js'; js_path.write_text(scripts,encoding='utf-8')
        checked=subprocess.run([node,'--check',str(js_path)],capture_output=True,text=True)
        assert checked.returncode==0, checked.stderr
    import zipfile
    with zipfile.ZipFile(out['report']) as zf:
        docxml=zf.read('word/document.xml').decode('utf-8',errors='ignore')
    assert ('Vía causal dominante' in docxml) or ('Dominant causal pathway' in docxml)
    assert ('Extensiones Media de apoyo' in docxml and 'candidatas para validación' in docxml) or ('Medium supporting extensions' in docxml and 'validation candidates' in docxml)
    # Major output families remain generated.
    assert list(root.rglob('*.xlsx')) and list(root.rglob('*.gpkg')) and list(root.rglob('*.png')) and list(root.rglob('*.csv'))
    # New spatial-role products must be present even when one of the role tables is empty.
    if edition.name=='PYTHON_ENGLISH':
        expected_role_csvs={
            'Table_21_Selected_Priority_Area_Cells.csv',
            'Table_21_Supporting_Area_Extensions.csv',
            'Table_21_Validation_Candidate_Units.csv',
        }
    else:
        expected_role_csvs={
            'Tabla_21_Celdas_Zonas_Prioritarias_Seleccionadas.csv',
            'Tabla_21_Extensiones_Apoyo_Zonas.csv',
            'Tabla_21_Unidades_Candidatas_Validacion.csv',
        }
    generated_csv_names={p.name for p in root.rglob('*.csv')}
    assert expected_role_csvs.issubset(generated_csv_names), (expected_role_csvs-generated_csv_names)
    qa_csv = next(root.rglob('*Conservation_Geometry.csv'), None) if edition.name=='PYTHON_ENGLISH' else next(root.rglob('*Geometria_Conservacion.csv'), None)
    assert qa_csv is not None
    qa_df=pd.read_csv(qa_csv,sep=';')
    check_col='check' if edition.name=='PYTHON_ENGLISH' else 'control'
    status_col='status' if edition.name=='PYTHON_ENGLISH' else 'estado'
    required_checks={
        'spatial_role_counts_consistent',
        'supporting_extensions_remain_medium',
        'validation_candidates_remain_medium_and_outside_zones',
        'every_priority_zone_contains_core',
    }
    assert required_checks.issubset(set(qa_df[check_col].astype(str))), required_checks-set(qa_df[check_col].astype(str))
    expected_pass='PASS' if edition.name=='PYTHON_ENGLISH' else 'SUPERADO'
    assert qa_df.loc[qa_df[check_col].isin(required_checks),status_col].eq(expected_pass).all(), qa_df
    if edition.name=='PYTHON_ENGLISH':
        priority_csv=next(root.rglob('Table_21_All_Conservation_Priority_Cells.csv'))
        public=pd.read_csv(priority_csv,sep=';')
        values=set(public.get('ecological_priority_class',pd.Series(dtype=str)).dropna().astype(str))
        assert not values.intersection({'Alta','Muy alta','Media','Baja','No evaluable / evidencia ecológica insuficiente','Sin capacidad de discriminación'}),values
        assert values.issubset({'High','Very high','Medium','Low','Not evaluable / insufficient ecological evidence','No discriminatory capacity'}),values
    print('PASS integration',edition.name,'selected',selected_n,'zones',zones_n,'outputs',len(registry.records))
