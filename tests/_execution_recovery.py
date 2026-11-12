"""Real-process exclusion and crash recovery at publication boundaries."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'herramientas'))
import hispa_security as sec
import secure_execution as life

BOOT = '''import sys, os, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import hispa_security as sec, secure_execution as life
root=Path(sys.argv[2]); cfg=sec.load_security_config(root)
key=sec.unwrap_project_key(cfg, 'Regression-Password-123!')
ctx=sec.AccessContext(cfg['project_id'], key, 'access')
'''
def command(root, code):
    return [sys.executable, '-c', BOOT + code, str(ROOT/'herramientas'), str(root)]

with tempfile.TemporaryDirectory() as td:
    root=Path(td)/'project'; root.mkdir()
    cfg,key=sec.create_security_config(root, 'Regression-Password-123!')
    ctx=sec.AccessContext(cfg['project_id'],key,'access')
    with patch.dict(os.environ, {'LOCALAPPDATA':str(Path(td)/'private')}):
        code='''import ejecutar_bilingue as coordinator
def work(argv):
    out=life.begin_protected_execution(root,'active',ctx)
    run=out/'ejecucion_active_ESP'; run.mkdir(); (run/'sample.csv').write_bytes(b'original')
    print(str(run),flush=True)
    sys.stdin.readline()
    return 0
coordinator._main=work
raise SystemExit(coordinator.main(['--project-root',str(root)]))
'''
        process=subprocess.Popen(command(root,code),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            run=Path(process.stdout.readline().strip())
            assert run.is_dir()
            for operation in (lambda:sec.protect_all_existing_outputs(root,ctx),lambda:life.recover_pending_executions(root,ctx)):
                try: operation()
                except sec.SecurityError: pass
                else: raise AssertionError('Active execution recovered concurrently')
            assert (run/'sample.csv').read_bytes()==b'original'
            assert not (root/'Resultados').exists()
        finally:
            process.kill(); process.communicate(timeout=20)
        assert life.recover_pending_executions(root,ctx)==1
        assert life.recover_pending_executions(root,ctx)==0
        assert (root/'Resultados/incompleta_ejecucion_active_ESP/sample.csv.hse').is_file()
        with sec._project_activity_lock(root):
            with sec._project_activity_lock(root):
                sec.protect_all_existing_outputs(root,ctx)
        print('PASS concurrent coordinator exclusion, nested lock and release after process death')
        for execution, boundary in [('cleanup','stage'),('commit','source')]:
            out=life.begin_protected_execution(root,execution,ctx)
            run=out/f'ejecucion_{execution}_ESP';run.mkdir();(run/'sample.csv').write_bytes(b'original')
            code=f'''journal=sec.security_dir(root)/'pending/{execution}.json'
stage=Path(json.loads(journal.read_text())['stage'])
stop=stage if {boundary!r}=='stage' else stage/'results'/'ejecucion_{execution}_ESP'
original=life.shutil.rmtree
def crash(path,*args,**kwargs):
    result=original(path,*args,**kwargs)
    if Path(path)==stop: os._exit(79)
    return result
life.shutil.rmtree=crash
life.finish_protected_execution(root,{execution!r},ctx)
'''
            result=subprocess.run(command(root,code),capture_output=True,text=True)
            assert result.returncode==79,result.stderr
            target=root/'Resultados'/run.name
            container=target/'sample.csv.hse'; original=container.read_bytes()
            # A committed but altered output must not be silently accepted.
            if boundary=='stage':
                container.write_bytes(original[:-1]+bytes([original[-1]^1]))
                try: life.recover_pending_executions(root,ctx)
                except sec.SecurityError: pass
                else: raise AssertionError('Corrupt committed output accepted')
                container.write_bytes(original)
            assert life.recover_pending_executions(root,ctx)==1
            assert life.recover_pending_executions(root,ctx)==0
            assert sec.decrypt_bytes(container.read_bytes(),key,cfg['project_id'])[0]==b'original'
        print('PASS recovery after directory commit and staging deletion; corrupt output rejected')
        out=life.begin_protected_execution(root,'missing',ctx)
        import shutil
        shutil.rmtree(out.parent)
        try: life.recover_pending_executions(root,ctx)
        except sec.SecurityError: pass
        else: raise AssertionError('Uncommitted missing stage accepted')
        probe=Path(td)/'sync';probe.mkdir();(probe/'content').write_bytes(b'unchanged')
        fsync=os.fsync
        def writable_sync(fd):
            # Directory descriptors are intentionally read-only on POSIX.
            import stat
            if stat.S_ISREG(os.fstat(fd).st_mode): os.write(fd,b'')
            fsync(fd)
        with patch.object(life.os,'fsync',side_effect=writable_sync):life._sync_tree(probe)
        assert (probe/'content').read_bytes()==b'unchanged'
        print('PASS missing uncommitted stage fails closed; fsync file descriptor is writable')
