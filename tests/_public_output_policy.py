"""Public generators reject individual metadata; unregistered outputs are private."""
import copy,json,os,shutil,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];edition=Path(sys.argv[1]);sys.path.insert(0,str(edition/'src'));sys.path.insert(0,str(ROOT/'herramientas'))
from hippodec_maps.maps import render_map2,render_map3,render_viewer,render_conservation_map,common_context,rewrite_language_switch
from hippodec_maps.config import RunParameters
from hippodec_maps.output_policy import public_product,register_public_output,copy_public_registration,REGISTRY_NAME
import hispa_security as sec
empty={'type':'FeatureCollection','features':[]}
cells={'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Polygon','coordinates':[[[-8,42],[-7.99,42],[-7.99,42.01],[-8,42]]]},'properties':{'grid_id':'g1','area':.5,'abundance':2,'density':4,'richness':1,'species_metrics':[{'Species':'Hippocampus guttulatus','N_sum':2,'Densidad_ajustada':4}]}}]}
context=common_context(RunParameters(2024,2025,10,'all',('Hippocampus guttulatus',)),'')
with tempfile.TemporaryDirectory() as td:
    root=Path(td)/'project';root.mkdir();run=root/'Resultados'/'run_policy_EN';run.mkdir(parents=True)
    cfg,key=sec.create_security_config(root,'Synthetic-password-123!');ctx=sec.AccessContext(cfg['project_id'],key,'access')
    with patch.dict(os.environ,{'HISPA_SYNG_SECURITY_MODE':'protected'}):
        m2=render_map2(run/'Map2_safe.html',cells,['Hippocampus guttulatus'],empty,empty,context,False)
        m3=render_map3(run/'Map3_safe.html',cells,{},[],empty,empty,context,False)
        viewer=render_viewer(run/'index.html','Map1_private.html',m2.name,m3.name,None,{},context,False)
        priority=render_conservation_map(run/'priority.html',cells,empty,empty,empty,empty,empty,(-8,42,-7,43),context)
    for p in [m2,m3,viewer,priority]:assert public_product(p),(p.name,p.read_text()[:100])
    for field in ['Observer','Comments','Link_observation','source_row','sampling_event_id','Latitude','Longitude']:
        bad=copy.deepcopy(cells);bad['features'][0]['properties'][field]='PRIVATE_CANARY_9283'
        path=run/('bad_'+field+'.html')
        try:render_map2(path,bad,[],empty,empty,context,False)
        except ValueError:pass
        else:raise AssertionError('Individual field accepted: '+field)
        assert not path.exists()
    bad=copy.deepcopy(cells);bad['features'][0]['geometry']={'type':'Point','coordinates':[-8,42]}
    try:render_map2(run/'bad_point.html',bad,[],empty,empty,context,False)
    except ValueError:pass
    else:raise AssertionError('Individual point geometry accepted')
    print('PASS real aggregate maps/viewer registration; individual metadata and points rejected')
    clone=run/'published';clone.mkdir();copied=clone/m2.name;shutil.copy2(m2,copied);copy_public_registration(m2,copied)
    switch={'enabled':True,'current':'EN','links':{'EN':str(copied),'ES':str(m2)}}
    rewrite_language_switch(copied,switch)
    assert public_product(copied)=='aggregate_map2'
    # Name and extension alone never authorize publication.
    for name in ['Map2_probe.html','unexpected_index.html','data.js','figure.png']:
        (run/name).write_bytes(b'PRIVATE_CANARY_9283')
    assert not public_product(run/'Map2_probe.html')
    altered=run/'changed.html';shutil.copy2(m2,altered);copy_public_registration(m2,altered)
    altered.write_text(altered.read_text()+'PRIVATE_CANARY_9283',encoding='utf-8');assert public_product(altered) is None
    # Exercise the real web builder and link-copy path; document bytes are synthetic fixtures.
    import pandas as pd
    import hippodec_maps.web_publication as web
    def document_fixture(path,*args,**kwargs):
        Path(path).write_bytes(b'PRIVATE_CANARY_9283');return Path(path)
    private=run/'Map1_private.html';private.write_bytes(b'PRIVATE_CANARY_9283')
    with patch.object(web,'_density_tables',return_value=(pd.DataFrame(),pd.DataFrame())), \
         patch.object(web,'_with_cell_reference',return_value=pd.DataFrame()), \
         patch.object(web,'_write_excel',side_effect=document_fixture), \
         patch.object(web,'_write_word',side_effect=document_fixture), \
         patch.object(web,'_write_data_package',side_effect=document_fixture):
        publication=web.build_web_publication(run,context,{'map1':private,'map2':m2,'map3':m3},
            pd.DataFrame({'Observer':['PRIVATE_CANARY_9283']}),pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),None,None)
    webroot=publication['root']
    public_copies=[p for p in webroot.rglob('*.html') if p.name in {m2.name,m3.name,'index.html'}]
    assert len(public_copies)==3 and all(public_product(p) for p in public_copies)
    audit=sec.protect_all_existing_outputs(root,ctx)
    for name in ['Map2_probe.html','unexpected_index.html','data.js','figure.png','changed.html']:
        original=(run/(name+'.hse'));assert original.is_file(),name
        assert b'PRIVATE_CANARY_9283' in sec.decrypt_bytes(original.read_bytes(),key,cfg['project_id'])[0]
    assert all(public_product(p) for p in [m2,m3,viewer,priority,copied]+public_copies)
    inventory=json.loads(Path(audit['audit']).read_text())['inventory']
    actual={p.relative_to(root/'Resultados').as_posix() for p in (root/'Resultados').rglob('*') if p.is_file()}
    assert {i['file'] for i in inventory}==actual
    assert {'public','encrypted','locked_placeholder'} <= {i['classification'] for i in inventory}
    assert all(i['reason'] and i['sha256'] for i in inventory)
    # Public static HTML must contain no individual canary after protection.
    for p in (root/'Resultados').rglob('*'):
        if p.is_file() and (public_product(p) or p.suffix=='.html'):assert b'PRIVATE_CANARY_9283' not in p.read_bytes(),p
    sec.protect_all_existing_outputs(root,ctx)
    assert all(public_product(p) for p in [m2,m3,viewer,priority,copied]+public_copies)
    print('PASS filename/extension bypass closed; real web-copy classification; mutation detection; complete inventory; idempotence')
assert (ROOT/'herramientas/output_policy.py').read_bytes()==(edition/'src/hippodec_maps/output_policy.py').read_bytes()
