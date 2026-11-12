from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd, numpy as np, geopandas as gpd
from shapely.geometry import box, Point

edition=Path(sys.argv[1]).resolve(); sys.path.insert(0,str(edition/'src'))
from hippodec_maps.conservation import (
    _build_priority_products, _connected_zones, _zone_spatial_roles, _protection_gap,
    _conservation_planning_inputs, _operational_conservation_zones,
)
from hippodec_maps.multiscale import _build_official_conservation_master


def base_priority():
    geoms=[box(i*5000,0,(i+1)*5000,5000) for i in range(5)]
    return gpd.GeoDataFrame({
        'master_id':['a','b','c','d','e'], 'grid_id':['a','b','c','d','e'],
        'planning_grid_km':[5]*5, 'scale_km':[5]*5,
        # a deliberately has extreme LCBD but only one biological record.
        'LCBD':[9.0,0.2,0.3,0.4,0.5],
        'richness':[1,2,3,3,4], 'abundance':[1,4,12,14,30],
        'n_sampling_events':[1,4,10,10,20], 'n_records':[1,4,10,10,20],
        'n_years_observed':[1,2,3,4,5], 'n_scales_evaluable':[1]*5,
        'multiscale_support_evaluable':[True]*5,
        'hotspot_lcbd':[True,False,False,False,False],
        'hotspot_persistence':[0]*5, 'is_hotspot_any_scale':[True,False,False,False,False],
        'is_hotspot_multiscale':[False]*5, 'is_hotspot_persistent_all_scales':[False]*5,
        'hotspot_type':['LCBD high','none','none','none','none'], 'hotspot_cluster':[0]*5,
        'n_depth_valid':[1,2,8,8,15], 'depth_mediana_grid':[3.,4.,5.,5.,6.],
        'habitat_dominante_grid':['h']*5, 'temporal_signal_raw':[0.9,0.1,0.3,0.7,0.8],
        'n_temporal_records':[1,4,10,10,20], 'Area_mar_km2':[20.]*5,
        'geometry':geoms,
    }, geometry='geometry', crs='EPSG:3035')


def assigned():
    rows=[]
    specs={
        'a':(1,[2026]),
        'b':(4,[2025,2026]),
        'c':(10,[2024,2025,2026]),
        'd':(10,[2023,2024,2025,2026]),
        'e':(20,[2022,2023,2024,2025,2026]),
    }
    centers={'a':2500,'b':7500,'c':12500,'d':17500,'e':22500}
    for gid,(n,years) in specs.items():
        for i in range(n):
            species_sets={
                'a':['Common species 1'],
                'b':['Common species 1','Common species 2'],
                'c':['Common species 1','Common species 2','Common species 3'],
                'd':['Common species 1','Common species 2','Common species 3'],
                'e':['Common species 1','Common species 2','Common species 3'],
            }
            species='Rare species' if gid=='e' and i<5 else species_sets[gid][i%len(species_sets[gid])]
            year=years[i%len(years)]
            rows.append({
                'grid_id':gid,'Species':species,'N_total':1,'Observer':f'o{i%3}',
                'Depth':float(2+i%5) if i%4 else np.nan,'Habitat':'h',
                'sampling_event_id':f'{gid}_e{i}','Date of observation':f'15-06-{year}',
                'geometry':Point(centers[gid],2500),
            })
    return gpd.GeoDataFrame(rows,geometry='geometry',crs='EPSG:3035')


priority=base_priority(); obs=assigned()
out,diag=_build_priority_products(priority,obs)
# Observation-derived temporal coverage is authoritative: stale intermediate year counts cannot alter conservation classes.
priority_stale=priority.copy(); priority_stale['n_years_observed']=0
out_stale,_=_build_priority_products(priority_stale,obs)
pd.testing.assert_series_equal(out['n_years_observed'],out_stale['n_years_observed'],check_names=False)
pd.testing.assert_series_equal(out['ecological_priority_class'],out_stale['ecological_priority_class'],check_names=False)
assert out.loc[out.master_id.eq('b'),'n_years_observed'].iloc[0]==2
assert out.loc[out.master_id.eq('e'),'n_years_observed'].iloc[0]==5

# 1. Core scientific safeguard: an extreme LCBD singleton can never become a conservation priority.
a=out.loc[out.master_id.eq('a')].iloc[0]
assert a['ecological_priority_class'] not in {'Alta','Muy alta'}, a
assert float(a['ecological_lcbd_context_score']) >= 75
assert int(a['n_independent_ecological_families_active']) == 0

# 2. Multi-evidence behaviour: moderate evidence remains Medium; convergent evidence becomes High.
b=out.loc[out.master_id.eq('b')].iloc[0]
c=out.loc[out.master_id.eq('c')].iloc[0]
e=out.loc[out.master_id.eq('e')].iloc[0]
assert b['ecological_priority_class']=='Media', b
assert c['ecological_priority_class']=='Alta', c
assert e['ecological_priority_class']=='Muy alta', e
assert c['n_years_observed'] >= 2
assert c['n_independent_ecological_families_active'] >= 3
assert e['n_low_occupancy_species_repeated'] >= 1
# Very high can only be caused by strong convergence, even when an alternative route also happens to be present.
assert 'converg' in str(e['cell_justification']).lower(), e['cell_justification']
assert 'presence persistente' not in str(e['conservation_priority_type']).lower() and 'occurrence core' not in str(e['conservation_priority_type']).lower(), e['conservation_priority_type']
assert e['ecological_priority_pathway_code']=='convergence', e['ecological_priority_pathway_code']

# 2b. A persistent single-species occurrence core is a valid alternative conservation pathway.
# It must be repeatedly occupied; low richness alone must not exclude a genuine stronghold.
mono=priority.copy(); mono.loc[mono.master_id.eq('d'),'richness']=1
obs_mono=obs.copy(); obs_mono.loc[obs_mono.grid_id.eq('d'),'Species']='Common species 1'
out_mono,_=_build_priority_products(mono,obs_mono)
d_mono=out_mono.loc[out_mono.master_id.eq('d')].iloc[0]
assert d_mono['ecological_priority_class']=='Alta', d_mono
assert bool(d_mono['population_core_pathway'])
assert int(d_mono['n_population_core_species']) >= 1
assert int(d_mono['max_population_core_years']) >= 3
assert int(d_mono['max_population_core_events']) >= 8
assert d_mono['ecological_priority_pathway_code']=='persistent_occurrence', d_mono['ecological_priority_pathway_code']

# 2c. Diversity-core pathways recover important multi-species sites without admitting weak one-off signals.
q_geoms=[box(i*5000,10000,(i+1)*5000,15000) for i in range(4)]
q_priority=gpd.GeoDataFrame({
    'master_id':['q_multi','q_exceptional','q_burst','q_sparse'],
    'grid_id':['q_multi','q_exceptional','q_burst','q_sparse'],
    'planning_grid_km':[5]*4, 'scale_km':[5]*4,
    'LCBD':[0.1,0.2,0.3,0.4],
    'richness':[4,5,3,4], 'abundance':[5,12,100,4],
    'n_sampling_events':[5,12,20,2], 'n_records':[5,12,20,4],
    'n_years_observed':[2,1,1,1], 'n_scales_evaluable':[1]*4,
    'multiscale_support_evaluable':[True]*4,
    'hotspot_lcbd':[False]*4, 'hotspot_persistence':[0]*4,
    'is_hotspot_any_scale':[False]*4, 'is_hotspot_multiscale':[False]*4,
    'is_hotspot_persistent_all_scales':[False]*4,
    'hotspot_type':['none']*4, 'hotspot_cluster':[0]*4,
    'n_depth_valid':[5,12,20,4], 'depth_mediana_grid':[5.]*4,
    'habitat_dominante_grid':['h']*4, 'temporal_signal_raw':[0.]*4,
    'n_temporal_records':[5,12,20,2], 'Area_mar_km2':[20.]*4,
    'geometry':q_geoms,
},geometry='geometry',crs='EPSG:3035')

q_rows=[]
q_centers={'q_multi':2500,'q_exceptional':7500,'q_burst':12500,'q_sparse':17500}
def addq(gid,species,event,year,n=1):
    q_rows.append({
        'grid_id':gid,'Species':species,'N_total':n,'Observer':'qa',
        'Depth':5.0,'Habitat':'h','sampling_event_id':event,
        'Date of observation':f'15-06-{year}','geometry':Point(q_centers[gid],12500),
    })
# Multi-year diversity core: 4 spp, 2 years, 5 events. Convergence alone scores below High.
for i,(sp,yr) in enumerate([('A',2025),('B',2025),('C',2026),('D',2026),('A',2026)]):
    addq('q_multi',sp,f'm{i}',yr)
# Exceptional one-year concentration: 5 spp, 12 events; two low-occupancy spp are repeated.
for i,sp in enumerate(['X1','X1','X1','X2','X2','X2','X3','X4','X5','X3','X4','X5']):
    addq('q_exceptional',sp,f'x{i}',2026)
# One-year abundance burst: many events/individuals but only 3 widespread species.
for i in range(20):
    addq('q_burst',['A','B','C'][i%3],f'b{i}',2026,5)
# Richness reported from four records compressed into two sampling events; only one year.
for i,sp in enumerate(['A','B','C','D']):
    addq('q_sparse',sp,f's{i%2}',2026)
q_obs=gpd.GeoDataFrame(q_rows,geometry='geometry',crs='EPSG:3035')
q_out,q_diag=_build_priority_products(q_priority,q_obs)
q_multi=q_out.loc[q_out.master_id.eq('q_multi')].iloc[0]
q_exc=q_out.loc[q_out.master_id.eq('q_exceptional')].iloc[0]
q_burst=q_out.loc[q_out.master_id.eq('q_burst')].iloc[0]
q_sparse=q_out.loc[q_out.master_id.eq('q_sparse')].iloc[0]
assert q_multi['ecological_priority_class']=='Alta', q_multi
assert bool(q_multi['diversity_core_pathway']) and not bool(q_multi['exceptional_diversity_core_pathway'])
assert q_multi['ecological_priority_pathway_code']=='diversity_core', q_multi['ecological_priority_pathway_code']
assert q_multi['ecological_convergent_evidence_score'] < 62.5
assert q_exc['ecological_priority_class']=='Alta', q_exc
assert bool(q_exc['exceptional_diversity_core_pathway'])
assert q_exc['ecological_priority_pathway_code']=='exceptional_diversity', q_exc['ecological_priority_pathway_code']
assert int(q_exc['n_low_occupancy_species_repeated']) >= 2
assert str(q_exc['validation_need']).startswith('Validación temporal prioritaria') or str(q_exc['validation_need']).startswith('Priority temporal validation')
# High abundance in a single year is not enough, and neither is sparse one-year richness.
assert q_burst['ecological_priority_class'] not in {'Alta','Muy alta'}, q_burst
assert q_sparse['ecological_priority_class'] not in {'Alta','Muy alta'}, q_sparse
assert not bool(q_burst['diversity_core_pathway'])
assert not bool(q_sparse['diversity_core_pathway'])
assert q_diag['diversity_core_min_species']==4
assert q_diag['diversity_core_min_years']==2
assert q_diag['diversity_core_min_events']==5
assert q_diag['exceptional_diversity_min_species']==5
assert q_diag['exceptional_diversity_min_events']==12
assert q_diag['exceptional_diversity_min_low_occupancy_species']==2

# 3. LCBD and temporal monitoring are context/separate products: changing them cannot change ecological class.
alt=priority.copy(); alt['LCBD']=alt['LCBD'][::-1].to_numpy(); alt['temporal_signal_raw']=[0,1,1,0,0]
out_alt,_=_build_priority_products(alt,obs)
pd.testing.assert_series_equal(out['ecological_priority_score'],out_alt['ecological_priority_score'],check_names=False)
pd.testing.assert_series_equal(out['ecological_priority_class'],out_alt['ecological_priority_class'],check_names=False)
assert not out['monitoring_priority_score'].fillna(-1).equals(out_alt['monitoring_priority_score'].fillna(-1))

# 4. Data-adequacy score itself never gates ecological priority.
obs_sparse=obs.copy(); obs_sparse['Observer']=pd.NA; obs_sparse['Depth']=np.nan; obs_sparse['Habitat']=pd.NA
out_sparse,_=_build_priority_products(priority,obs_sparse)
pd.testing.assert_series_equal(out['ecological_priority_class'],out_sparse['ecological_priority_class'],check_names=False)
assert out_sparse.loc[out_sparse.master_id.eq('c'),'data_adequacy_score'].iloc[0] < out.loc[out.master_id.eq('c'),'data_adequacy_score'].iloc[0]

# 5. The four explicit biological-evidence families are bounded and auditable.
assert out['n_independent_ecological_families_active'].max() <= 4
assert out['n_independent_ecological_families_strong'].max() <= 4
assert diag['richness_strong_threshold_species']==3
assert diag['persistence_strong_threshold_years']==3
assert diag['low_occupancy_species_fraction']==0.10
assert diag['population_core_moderate_min_years']==3
assert diag['population_core_moderate_min_events']==8
assert diag['population_core_moderate_min_abundance']==8
assert diag['convergence_high_min_events']==6
assert diag['convergence_high_min_abundance']==6
assert diag['convergence_very_high_min_events']==12
assert diag['convergence_very_high_min_abundance']==12

# 6. Rook connectivity: corner contact does not connect; area-dominant class is retained.
proto=out.loc[out.master_id.eq('c')].iloc[0]
rows=[]
for gid,geom,klass,score,area in [
    ('r1',box(0,0,2000,2000),'Alta',70.,4.0),
    ('r2',box(-1000,2000,0,3000),'Muy alta',95.,1.0),
    ('r3',box(2000,0,3000,2000),'Muy alta',90.,2.0),
]:
    row=proto.copy(); row['master_id']=gid; row['geometry']=geom; row['ecological_priority_class']=klass; row['ecological_priority_score']=score; row['Area_mar_km2']=area
    rows.append(row)
sel=gpd.GeoDataFrame(rows,geometry='geometry',crs='EPSG:3035').reset_index(drop=True)
zones,summary,cells=_connected_zones(sel)
assert len(zones)==2
z1=cells.loc[cells.master_id.eq('r1'),'zone_id'].iloc[0]
assert z1==cells.loc[cells.master_id.eq('r3'),'zone_id'].iloc[0]
assert z1!=cells.loc[cells.master_id.eq('r2'),'zone_id'].iloc[0]
row=summary.loc[summary.zone_id.eq(z1)].iloc[0]
assert row['ecological_priority_class_zone']=='Alta'
assert row['ecological_priority_class_zone_max']=='Muy alta'
assert row['main_priority_pathway_code']=='convergence'
assert int(row['n_cells_pathway_convergence'])==2

# 6b. Spatial roles: Medium units can support a core, but cannot create a priority zone.
role_rows=[]
for gid,geom,klass,score,years,events,families in [
    ('core',box(0,0,5000,5000),'Alta',75.,3,8,3),
    ('ext',box(5000,0,10000,5000),'Media',50.,2,4,2),
    ('corner',box(5000,5000,10000,10000),'Media',55.,2,5,2),
    ('isolated',box(20000,0,25000,5000),'Media',55.,3,6,3),
    ('weak',box(-5000,0,0,5000),'Media',25.,3,8,3),
]:
    row=proto.copy(); row['master_id']=gid; row['geometry']=geom
    row['ecological_priority_class']=klass; row['ecological_priority_score']=score
    row['n_years_observed']=years; row['n_sampling_events']=events
    row['n_independent_ecological_families_active']=families
    role_rows.append(row)
role_frame=gpd.GeoDataFrame(role_rows,geometry='geometry',crs='EPSG:3035').reset_index(drop=True)
cores,extensions,candidates=_zone_spatial_roles(role_frame)
assert set(cores.master_id)=={'core'}
assert set(extensions.master_id)=={'ext'}
# Corner-only contact is not a supporting extension; strong isolated Medium units remain candidates.
assert set(candidates.master_id)=={'corner','isolated'}
assert 'weak' not in set(extensions.master_id) | set(candidates.master_id)
zone_input=gpd.GeoDataFrame(pd.concat([cores,extensions]),geometry='geometry',crs=role_frame.crs)
role_zones,role_summary,role_cells=_connected_zones(zone_input)
assert len(role_zones)==1 and len(role_summary)==1
assert int(role_summary.iloc[0]['n_core_cells'])==1
assert int(role_summary.iloc[0]['n_extension_cells'])==1
assert role_summary.iloc[0]['ecological_priority_class_zone']=='Alta'
assert role_cells.loc[role_cells.master_id.eq('ext'),'ecological_priority_class'].iloc[0]=='Media'

# 7. Missing protection remains explicitly not evaluated.
gap=_protection_gap(zones,summary,None)
assert gap['n_protected_areas_overlap'].isna().all()
assert gap['pct_zone_protected'].isna().all()
assert gap['protection_evaluation_status'].eq('not_evaluated').all()

# 8. 1-km descriptive runs must hand conservation to the 5-km official planning grid.
planning5=priority.copy(); planning5['grid_id']=planning5['master_id']; planning5['scale_km']=5
planning_points=obs.copy(); planning_points['grid_id_scale']=planning_points['grid_id']
master1=priority.copy(); master1['planning_grid_km']=1
p5,a5,km=_conservation_planning_inputs(
    {'master_hotspots':master1,'scale_results':{5:{'grid':planning5,'points':planning_points}}},
    1,obs,
)
assert km==5
assert p5['planning_grid_km'].eq(5).all()
assert p5['selected_grid_km'].eq(1).all()
assert a5['grid_id'].isin(set(priority.master_id)).all()

# 9. Conservation handoff retains occupied cells; low support is not silently deleted upstream.
official=gpd.GeoDataFrame({'grid_id':['m1','m2'],'Area_mar_km2':[1.,1.],'geometry':[box(0,0,1000,1000),box(1000,0,2000,1000)]},geometry='geometry',crs='EPSG:3035')
community={'environment_grid':pd.DataFrame({'grid_id':['m1','m2'],'n_records':[5,1],'n_sampling_events':[5,1],'n_years_observed':[3,1],'richness':[2,1],'abundance':[5,1]}),'indices_cells':pd.DataFrame(),'lcbd':pd.DataFrame({'grid_id':['m1'],'LCBD':[0.4]}),'clusters':pd.DataFrame()}
persistence=gpd.GeoDataFrame({'master_id':['m1','m2'],'n_scales_evaluable':[3,1],'is_hotspot_any_scale':[True,False],'is_hotspot_multiscale':[True,False],'is_hotspot_persistent_all_scales':[False,False],'hotspot_persistence':[2,0],'geometry':[box(0,0,1000,1000),box(1000,0,2000,1000)]},geometry='geometry',crs='EPSG:3035')
master,qa=_build_official_conservation_master(official,community,persistence,1,2)
assert set(master['master_id'])=={'m1','m2'}
assert not bool(master.loc[master.master_id.eq('m2'),'multiscale_support_evaluable'].iloc[0])

print('PASS',edition.name)


# 9. Operational footprints are evidence-anchored and never bridge empty 1-km cells.
parent_zones=gpd.GeoDataFrame({
    'zone_id':['ZP-001'], 'area_zone_km2':[50.0],
    'geometry':[box(0,0,10000,5000)],
}, geometry='geometry', crs='EPSG:3035')
parent_summary=pd.DataFrame({'zone_id':['ZP-001'],'area_zone_km2':[50.0]})
fine=gpd.GeoDataFrame({
    'grid_id':['f1','f2','f3'], 'grid_id_scale':['f1','f2','f3'],
    'n_records':[4,3,2], 'n_sampling_events':[3,2,2], 'n_years_observed':[2,2,1],
    'abundance':[5,4,2], 'richness':[2,2,1],
    'geometry':[box(0,0,1000,1000),box(1000,0,2000,1000),box(8000,0,9000,1000)],
}, geometry='geometry', crs='EPSG:3035')
op_zones,op_summary,op_cells=_operational_conservation_zones(
    parent_zones,parent_summary,{'scale_results':{1:{'grid_with_records':fine}}}
)
assert len(op_zones)==2, op_zones
assert len(op_cells)==3, op_cells
assert set(op_zones['parent_zone_id'].astype(str))=={'ZP-001'}
assert np.isclose(float(op_summary['area_operational_km2'].sum()),3.0)
assert np.isclose(float(op_summary['pct_parent_zone_evidence_footprint'].sum()),6.0)
for geom in op_zones.geometry:
    assert geom.difference(parent_zones.geometry.iloc[0]).area <= 1.0
assert sorted(op_summary['n_evidence_cells_1km'].astype(int).tolist())==[1,2]
