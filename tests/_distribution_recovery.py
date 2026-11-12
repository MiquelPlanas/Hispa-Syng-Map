"""No distribution is created before authenticated recovery succeeds."""
import os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'herramientas'))
import hispa_security as sec,secure_execution as life
with tempfile.TemporaryDirectory() as td:
    base=Path(td);root=base/'source';(root/'Datos_data').mkdir(parents=True)
    (root/'Datos_data/Ingesta_provisional.xlsx').write_bytes(b'synthetic workbook')
    cfg,key=sec.create_security_config(root,'Synthetic-password-123!')
    owner=sec.AccessContext(cfg['project_id'],key,'owner',owner_token=sec.unwrap_owner_token(cfg,'Synthetic-password-123!'))
    sec.encrypt_project_input(root,cfg,key)
    with patch.dict(os.environ,{'LOCALAPPDATA':str(base/'private')}):
        for mode in ['open','protected']:
            execution='before_'+mode;out=life.begin_protected_execution(root,execution,owner)
            run=out/f'ejecucion_{execution}_ESP';run.mkdir();(run/'sample.csv').write_bytes(b'synthetic individual data')
            dest=base/mode;credential=base/(mode+'.hsk')
            if mode=='open':sec.create_open_copy(root,dest,owner)
            else:sec.create_protected_copy(root,dest,'Second-password-123!',credential,owner)
            assert not (sec.security_dir(root)/'pending'/f'{execution}.json').exists()
            target=root/'Resultados'/('incompleta_'+run.name)/'sample.csv.hse'
            assert sec.decrypt_bytes(target.read_bytes(),key,cfg['project_id'])[0]==b'synthetic individual data'
            assert not (dest/'Resultados').exists()
            assert not any(p.is_dir() for p in (dest/'.ejecuciones').iterdir()) if (dest/'.ejecuciones').exists() else True
        print('PASS open and protected copies recover pending runs before creation')
        out=life.begin_protected_execution(root,'blocked',owner)
        run=out/'ejecucion_blocked_ESP';run.mkdir();(run/'sample.csv').write_bytes(b'pending')
        for mode in ['open','protected']:
            dest=base/('blocked_'+mode);credential=base/('blocked_'+mode+'.hsk')
            with patch.object(life,'verify_protected_tree',side_effect=sec.SecurityError('injected recovery failure')):
                try:
                    if mode=='open':sec.create_open_copy(root,dest,owner)
                    else:sec.create_protected_copy(root,dest,'Second-password-123!',credential,owner)
                except sec.SecurityError:pass
                else:raise AssertionError('Copy accepted failed recovery')
            assert not dest.exists() and not credential.exists()
            assert (sec.security_dir(root)/'pending/blocked.json').exists() and out.exists()
        print('PASS recovery failures retain staging/journal and create no copy or credential')
        access=sec.AccessContext(cfg['project_id'],key,'access')
        for mode in ['open','protected']:
            dest=base/('unauthorized_'+mode)
            try:
                if mode=='open':sec.create_open_copy(root,dest,access)
                else:sec.create_protected_copy(root,dest,'Second-password-123!',base/'unauthorized.hsk',access)
            except sec.SecurityError:pass
            else:raise AssertionError('Ordinary access authorized a copy')
            assert not dest.exists()
        assert (sec.security_dir(root)/'pending/blocked.json').exists()
        assert life.recover_pending_executions(root,owner)==1
        print('PASS owner authentication precedes source recovery; later authenticated recovery succeeds')
