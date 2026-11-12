from pathlib import Path
from zipfile import ZipFile
import re

ROOT=Path(__file__).resolve().parents[1]

for edition in ('PYTHON_ESP','PYTHON_ENGLISH'):
    base=ROOT/edition/'src'/'hippodec_maps'
    community=(base/'community.py').read_text(encoding='utf-8')
    temporal=(base/'temporal.py').read_text(encoding='utf-8')
    template=(base/'templates'/'conservation.html').read_text(encoding='utf-8')
    assert re.search(r'markersize\s*=\s*56', community), edition
    assert re.search(r'markersize\s*=\s*48', temporal), edition
    assert 'marker_sizes = {' in temporal, edition
    assert '"No comparable": 18' in temporal, edition
    assert '"Ausencia en ambos": 32' in temporal, edition
    for status in ('"Persistencia": 64','"Pérdida": 64','"Ganancia": 64'):
        assert status in temporal, (edition,status)
    assert 'plot_order = [' in temporal, edition
    assert 'width_ratios=(0.16, 0.84)' in temporal, edition
    assert 'legend_ax = fig.add_subplot(grid[0, 0])' in temporal, edition
    assert 'ax = fig.add_subplot(grid[0, 1])' in temporal, edition
    assert 'fontsize=7' in temporal and 'title_fontsize=8' in temporal, edition
    assert 'selectedPriorityClasses' in template
    assert 'rebuildPriorityCells' in template
    assert 'input[data-priority-class]' in template
    assert 'data-filter-action="all"' in template
    assert 'data-filter-action="none"' in template
    assert "collapsed:false,position:'topright'" in template, edition
    assert 'priority-layer-control' in template, edition
    assert '.priority-layer-control {' in template, edition
    if edition=='PYTHON_ESP':
        assert 'CAPAS / MAPAS BASE' in template, edition
        assert 'Zonas prioritarias estratégicas · {{ planning_grid_km }} km' in template, edition
        assert 'Zonas operativas de conservación · evidencia 1 km' in template, edition
    else:
        assert 'LAYERS / BASE MAPS' in template, edition
        assert 'Strategic priority areas · {{ planning_grid_km }} km' in template, edition
        assert 'Operational conservation areas · 1-km evidence' in template, edition
    internal_classes=(
        'No evaluable / evidencia ecológica insuficiente','Sin capacidad de discriminación',
        'Baja','Media','Alta','Muy alta',
    )
    for token in internal_classes:
        assert token in template, (edition,token)
    visible_classes=(
        ('No evaluable / evidencia ecológica insuficiente','Sin capacidad de discriminación','Baja','Media','Alta','Muy alta')
        if edition=='PYTHON_ESP' else
        ('Not evaluable / insufficient ecological evidence','No discriminatory capacity','Low','Medium','High','Very high')
    )
    for token in visible_classes:
        assert token in template, (edition,token)
    viewer=(base/'templates'/'viewer.html').read_text(encoding='utf-8')
    assert 'data-map="priority"' in viewer, edition
    assert 'priority_map_name' in viewer, edition
    assert '<iframe id="map-frame"' in viewer, edition

for filename in ('Manual_Hispa_Syng_v1_0_ES.docx','Manual_Hispa_Syng_v1_0_EN.docx'):
    with ZipFile(ROOT/filename) as z:
        xml=z.read('word/document.xml').decode('utf-8')
    for chapter in range(1,29):
        anchor=f"chap_{chapter:02d}"
        assert xml.count(f'w:name="{anchor}"') == 1, (filename,anchor)
        assert xml.count(f'w:anchor="{anchor}"') >= 2, (filename,anchor)
    if filename.endswith('_ES.docx'):
        assert 'Conceptos esenciales antes de empezar' in xml, filename
        assert 'No evaluable / evidencia ecológica insuficiente' in xml, filename
        assert 'No evaluable / datos insuficientes' not in xml, filename
        assert 'sujeta a suficiencia de datos y contexto' not in xml, filename
        assert 'no existe evidencia ecológica estimable para asignar una clase' in xml.lower(), filename
    else:
        assert 'Not evaluable / insufficient ecological evidence' in xml, filename
        assert 'Not evaluable / insufficient data' not in xml, filename
        assert 'subject to data adequacy and context' not in xml, filename
        assert 'no estimable ecological evidence is available to assign a class' in xml.lower(), filename

# Conservation wording must never re-introduce data-adequacy gating of ecological priority.
for edition in ('PYTHON_ESP','PYTHON_ENGLISH'):
    base=ROOT/edition/'src'/'hippodec_maps'
    conservation=(base/'conservation.py').read_text(encoding='utf-8')
    report=(base/'technical_report.py').read_text(encoding='utf-8')
    if edition=='PYTHON_ESP':
        assert 'Aumentar soporte de datos antes de asignar prioridad ecológica' not in conservation
        assert 'puede reflejar soporte insuficiente' not in report
        assert 'la suficiencia de datos se informa por separado' in conservation.lower()
        assert 'la suficiencia de datos se informa de forma independiente' in report.lower()
    else:
        assert 'Increase data support before assigning ecological priority' not in conservation
        assert 'it may reflect insufficient support' not in report
        assert 'data adequacy is reported separately' in conservation.lower()
        assert 'data adequacy is reported independently' in report.lower()

# Distribution text must describe only the current software state.
def _w(*codes):
    return ''.join(chr(c) for c in codes)
patterns=[
    _w(50,66)+r'\.[0-9]',
    _w(70,65,83,69,50,66),
    r'\b'+_w(104,111,116,102,105,120)+r'\b',
    r'\b'+_w(100,101,112,114,101,99,97,116,101,100)+r'\b',
    r'\b'+_w(108,101,103,97,99,121)+r'\b',
    _w(112,114,101,118,105,111,117,115,32,118,101,114,115,105,111,110),
    _w(118,101,114,115,105)+r'[oó]'+_w(110,32,97,110,116,101,114,105,111,114),
    _w(80,104,97,115,101,95,51,95,50),
]
skip_suffixes={'.docx','.xlsx','.png','.jpg','.jpeg','.pdf','.zip'}
for p in ROOT.rglob('*'):
    rel=p.relative_to(ROOT)
    if not p.is_file() or p.name=='LICENSE' or p.suffix.lower() in skip_suffixes:
        continue
    if 'vendor' in rel.parts or (rel.parts and rel.parts[0] == 'Resources'):
        continue
    try: text=p.read_text(encoding='utf-8',errors='ignore')
    except Exception: continue
    for pattern in patterns:
        assert not re.search(pattern,text,re.I), (p.relative_to(ROOT),pattern)

print('PASS presentation and distribution')
