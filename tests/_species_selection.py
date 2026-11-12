"""Check scientific names with author commas through the bilingual launcher."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
edition=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(edition/'src'))
sys.path.insert(0,str(ROOT/'herramientas'))
from hippodec_maps.data import parse_species_argument, read_and_clean_excel
from hippodec_maps import cli

species=(
 'Hippocampus guttulatus Cuvier, 1829',
 'Hippocampus hippocampus (Linnaeus, 1758)',
 'Nerophis ophidion (Linnaeus, 1758)',
 'Syngnathus acus Linnaeus, 1758',
 'Syngnathus typhle Linnaeus, 1758',
)
cases=[(None,species),(list(species),species),(species,species),
       (','.join(species),species),('; '.join(species),species),
       ([species[0]],(species[0],)),(species[1],(species[1],)),
       ([species[0],species[3]],(species[0],species[3])),
       (f' {species[0]} ; {species[3]} ',(species[0],species[3])),
       ([species[0],species[0]],(species[0],)),('',()),([],())]
for token in ['all','todos','todas','0','ALL','Todos']:
 cases.extend([(token,species),([token],species)])
for value,expected in cases:
 assert parse_species_argument(value,species)==expected,(value,expected)
plain=['Species alpha','Species beta']
assert parse_species_argument('Species alpha,Species beta',plain)==tuple(plain)
assert parse_species_argument(['Species beta;Species alpha'],plain)==tuple(reversed(plain))
for value in ['Unknown species',[species[0],'Unknown species']]:
 try:parse_species_argument(value,species)
 except ValueError:pass
 else:raise AssertionError('Unknown species accepted')

spec=importlib.util.spec_from_file_location('coordinator_selection',ROOT/'herramientas/ejecutar_bilingue.py')
coordinator=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=coordinator
spec.loader.exec_module(coordinator)
language='ES' if edition.name=='PYTHON_ESP' else 'EN'

if len(sys.argv)>2:
 data,summary=read_and_clean_excel(Path(sys.argv[2]),'BD depurada')
 available=tuple(summary['available_species'])
 assert len(data)==500 and set(available)==set(species)
 fixture_label='actual 500-row demo workbook'
else:
 data=pd.DataFrame({'Species':list(species)})
 available=species
 summary={'available_year_min':2021,'available_year_max':2026,'available_species':list(available)}
 fixture_label='synthetic scientific-name fixture'
captured=[]
cli.resolve_input_paths=lambda root,config:{'excel':Path('fixture.xlsx'),'sheet':'BD depurada'}
cli.read_and_clean_excel=lambda path,sheet:(data,summary)
def capture_pipeline(project_root,config,paths,raw,summary,params,**kwargs):
 captured.append((params.species_raw,len(raw)))
 return {'viewer':Path('fixture-viewer.html'),'qa':Path('fixture-qa.csv')}
cli.run_pipeline=capture_pipeline
for selection in [available,(available[0],),(available[1],available[4])]:
 config_path=edition/('configuracion.yaml' if language=='ES' else 'config.yaml')
 command=coordinator._child_command(ROOT,edition,language,config_path,ROOT/'Resultados',ROOT/'Resultados/selection_test','selection_test',2021,2026,10,'all',selection)
 assert command.count('--species')==len(selection),command
 transcript=io.StringIO()
 with contextlib.redirect_stdout(transcript),contextlib.redirect_stderr(transcript):
  code=cli.main(command[2:])
 assert code==0,(language,selection,code,transcript.getvalue())
 assert captured[-1]==(selection,len(data)),captured
print(f'PASS {edition.name}: {len(cases)+4} parsing scenarios and 3 launcher-to-CLI selections; {fixture_label}; scientific calculations not executed.')
