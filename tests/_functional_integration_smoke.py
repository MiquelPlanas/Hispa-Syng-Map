from __future__ import annotations
import sys, tempfile
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import Point

edition=Path(sys.argv[1]).resolve(); sys.path.insert(0,str(edition/'src'))
from hippodec_maps.optional_analysis import run_functional_diversity
from hippodec_maps.analysis_io import OutputRegistry
from hippodec_maps.technical_report import _functional_discussion


def make_dirs(root: Path):
    dirs={k:root/k for k in ['04_tablas','05_figuras','06_modelos']}
    for p in dirs.values(): p.mkdir(parents=True,exist_ok=True)
    return dirs


def run_case(root: Path, extra: bool):
    rows=[]
    # R1 and R2 have enough characterised species; R3 deliberately has only two.
    composition={
        'R1': {'Species alpha':8,'Species beta':2,'Species gamma':1,'Species delta':1,'Species epsilon':3},
        'R2': {'Species alpha':1,'Species beta':1,'Species gamma':5,'Species delta':7},
        'R3': {'Species alpha':4,'Species beta':2},
    }
    idx=0
    for r_i,(region,spp) in enumerate(composition.items()):
        for s_i,(sp,n) in enumerate(spp.items()):
            idx+=1
            rows.append({
                'Species':sp,'N_total':float(n),'Region_MITECO':region,
                'sampling_event_id':f'{region}_{s_i}','geometry':Point(r_i*1000+s_i*5, r_i*1000),
            })
    assigned=gpd.GeoDataFrame(rows,geometry='geometry',crs='EPSG:3035')
    trait_rows=[
        ['Species alpha',5,1,3,3,2,3],
        # beta is deliberately functionally redundant with alpha: zero Gower distance.
        ['Species beta',5,1,3,3,2,3],
        ['Species gamma',15,2,2,2,8,1],
        ['Species delta',30,3,1,1,18,0],
        # epsilon is observed but incomplete and must be diagnosed/excluded.
        ['Species epsilon',20,2,2,2,np.nan,1],
    ]
    if extra:
        trait_rows.append(['Species zeta',60,3,1,1,40,0])
    traits=pd.DataFrame(trait_rows,columns=[
        'Species','body_size_cm','mobility','benthic_affinity','habitat_complexity','depth_mean_m','holdfast'
    ])
    traits_path=root/'traits.csv'; traits.to_csv(traits_path,index=False)
    reg=OutputRegistry(root)
    out=run_functional_diversity(assigned,traits_path,make_dirs(root),reg)
    assert out['available'] is True
    return out,reg

with tempfile.TemporaryDirectory(prefix='functional_smoke_') as td:
    base_root=Path(td)/'base'; extra_root=Path(td)/'extra'; base_root.mkdir(); extra_root.mkdir()
    base,reg1=run_case(base_root,False)
    extra,reg2=run_case(extra_root,True)
    d1=base['space_diagnostics'].iloc[0]; d2=extra['space_diagnostics'].iloc[0]
    assert int(d1['n_species_with_complete_traits'])==4
    assert int(d2['n_species_with_complete_traits'])==4
    assert int(d1['functional_dimensions_common'])==int(d2['functional_dimensions_common'])
    assert str(d1['pcoa_correction']) in {'none','sqrt','lingoes'}
    assert float(d1['min_eigenvalue_after']) >= -1e-9
    used=set(base['traits_used']['Species_clean'].astype(str))
    assert 'Species epsilon' not in used and 'Species zeta' not in used
    diag=base['trait_diagnostics'].set_index('Species')
    assert diag.loc['Species epsilon','trait_status']=='incomplete_required_traits'
    metrics=['FRic','FRic_relative','FEve','FDiv','FDis','RaoQ',
             'FEve_abundance_weighted','FDiv_abundance_weighted','FDis_abundance_weighted','RaoQ_abundance_weighted']
    a=base['results'].set_index('Region_MITECO').loc[['R1','R2'],metrics].astype(float)
    b=extra['results'].set_index('Region_MITECO').loc[['R1','R2'],metrics].astype(float)
    assert np.allclose(a.to_numpy(),b.to_numpy(),equal_nan=True,atol=1e-12,rtol=1e-12)
    r3=base['results'].set_index('Region_MITECO').loc['R3']
    assert r3['calculation_status']=='partial'
    if int(d1['functional_dimensions_common'])>=2:
        assert pd.isna(r3['FRic'])
    assert np.isfinite(float(base['results'].set_index('Region_MITECO').loc['R1','FEve']))
    # Principal incidence and abundance-weighted sensitivity should not be silently conflated.
    r1=base['results'].set_index('Region_MITECO').loc['R1']
    assert not np.isclose(float(r1['RaoQ']),float(r1['RaoQ_abundance_weighted']))
    assert len(reg1.records)>10 and len(reg2.records)>10
    # The taxonomic-vs-functional figure must retain regions with non-estimable FRic
    # instead of silently dropping them. R3 is deliberately partial in this fixture.
    plot_data=base['taxonomic_functional_plot_data'].set_index('Region_MITECO')
    richness_data=base['richness_functional'].set_index('Region_MITECO')
    invalid_regions=richness_data.index[pd.to_numeric(richness_data['FRic_relative'],errors='coerce').isna()].tolist()
    assert invalid_regions, 'fixture must contain at least one region with non-estimable FRic'
    assert set(invalid_regions).issubset(set(plot_data.index))
    assert (~plot_data.loc[invalid_regions,'FRic_estimable'].astype(bool)).all()
    assert (pd.to_numeric(plot_data.loc[invalid_regions,'FRic_relative_display'],errors='coerce') < 0.0).all()
    expected_folder='diversidad_funcional' if edition.name=='PYTHON_ESP' else 'functional_diversity'
    for parent in ('04_tablas','05_figuras','06_modelos'):
        assert (base_root/parent/expected_folder).is_dir(), (parent,expected_folder)
    # Functional outputs must not create the community folder in an isolated run.
    wrong_community='community_biogeography' if edition.name=='PYTHON_ESP' else 'community_biogeography'
    assert not (base_root/'04_tablas'/wrong_community).exists()
    assert not (base_root/'05_figuras'/wrong_community).exists()
    discussion=_functional_discussion(base)
    assert discussion and any('incid' in paragraph.casefold() for paragraph in discussion)
    print('PASS functional integration',edition.name,'outputs',len(reg1.records),'dims',int(d1['functional_dimensions_common']),'correction',d1['pcoa_correction'])

# Package-level regression: the distributed trait workbook contains an additional
# species not present in the current 12-species observation set. It must not
# alter the functional space.
package_traits = edition.parent / "Datos_data" / "traits.xlsx"
if package_traits.exists():
    current_species = [
        "Entelurus aequoreus", "Hippocampus algiricus", "Hippocampus guttulatus",
        "Hippocampus hippocampus", "Minyichthys sentus", "Nerophis lumbriciformis",
        "Nerophis maculatus", "Nerophis ophidion", "Syngnathus abaster",
        "Syngnathus acus", "Syngnathus rostellatus", "Syngnathus typhle",
    ]
    with tempfile.TemporaryDirectory(prefix="functional_package_traits_") as td2:
        root2=Path(td2)
        assigned2=gpd.GeoDataFrame([
            {"Species":sp,"N_total":1.0,"Region_MITECO":"R1","sampling_event_id":f"e{i}","geometry":Point(i*10,0)}
            for i,sp in enumerate(current_species)
        ],geometry="geometry",crs="EPSG:3035")
        reg3=OutputRegistry(root2)
        out3=run_functional_diversity(assigned2,package_traits,make_dirs(root2),reg3)
        assert out3["available"] is True
        d3=out3["space_diagnostics"].iloc[0]
        assert int(d3["n_species_observed_selected"])==12
        assert int(d3["n_species_with_complete_traits"])==12
        assert len(out3["traits_used"])==12
        assert "Syngnathus tenuirostris" not in set(out3["traits_used"]["Species_clean"].astype(str))
        print("PASS distributed traits filtering",edition.name,"used",len(out3["traits_used"]),"correction",d3["pcoa_correction"])
