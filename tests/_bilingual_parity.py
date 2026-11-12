from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
helper=Path(__file__).with_name('_parity_snapshot.py')
env=os.environ.copy(); env['PYTHONDONTWRITEBYTECODE']='1'; env.setdefault('MPLBACKEND','Agg')
def snap(edition):
 r=subprocess.run([sys.executable,str(helper),str(ROOT/edition)],check=True,capture_output=True,text=True,env=env)
 return json.loads(r.stdout.strip().splitlines()[-1])
es=snap('PYTHON_ESP'); en=snap('PYTHON_ENGLISH')
if es != en:
 keys=sorted(k for k in set(es)|set(en) if es.get(k)!=en.get(k))
 raise AssertionError('Bilingual mathematical parity failed for: '+', '.join(keys))
print('PASS bilingual mathematical parity',len(es),'snapshot fields')
