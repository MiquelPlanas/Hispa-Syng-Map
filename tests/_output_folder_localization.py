from __future__ import annotations
import re, sys
from pathlib import Path

edition=Path(sys.argv[1]).resolve()
base=edition/'src'/'hippodec_maps'
expected = {
    'PYTHON_ESP': {
        '04_tablas': {'manifiestos','comunidad_biogeografia','descriptivo_habitat_profundidad','diversidad_funcional','multiescala','base_espacial','sexo','temporal'},
        '05_figuras': {'comunidad_biogeografia','descriptivo_habitat_profundidad','diversidad_funcional','multiescala','sexo','temporal'},
        '06_modelos': {'comunidad_biogeografia','descriptivo_habitat_profundidad','diversidad_funcional','multiescala','sexo','temporal'},
    },
    'PYTHON_ENGLISH': {
        '04_tablas': {'manifests','community_biogeography','descriptive_habitat_depth','functional_diversity','multiscale','spatial_base','sex','temporal'},
        '05_figuras': {'community_biogeography','descriptive_habitat_depth','functional_diversity','multiscale','sex','temporal'},
        '06_modelos': {'community_biogeography','descriptive_habitat_depth','functional_diversity','multiscale','sex','temporal'},
    },
}[edition.name]
found={k:set() for k in expected}
pat=re.compile(r'directories\["(04_tablas|05_figuras|06_modelos)"\]\s*/\s*"([^"]+)"')
for p in base.glob('*.py'):
    text=p.read_text(encoding='utf-8',errors='ignore')
    for parent,child in pat.findall(text):
        found[parent].add(child)
for parent in expected:
    unexpected=found[parent]-expected[parent]
    missing=expected[parent]-found[parent]
    assert not unexpected, f'{edition.name} {parent} unexpected analysis folders: {sorted(unexpected)}'
    assert not missing, f'{edition.name} {parent} missing expected analysis folders: {sorted(missing)}'
print('PASS output folder localization',edition.name)
