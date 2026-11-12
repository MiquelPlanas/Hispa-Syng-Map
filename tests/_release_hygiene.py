from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
allowed_root_files={
    ".gitattributes",
    ".gitignore","CITATION.cff","Hispa-Syng.bat","INSTALLATION_AND_WEB_PUBLICATION.docx",
    "LEEME.md","LICENSE","MANUAL_INSTALACION_PUBLICACION.docx",
    "Manual_Hispa_Syng_v1_0_EN.docx","Manual_Hispa_Syng_v1_0_ES.docx","README.md",
    "REPARAR_ENTORNO_HISPA_SYNG.bat","RUN_REGRESSION_TESTS.bat","THIRD_PARTY_NOTICES.md",
    "SEGURIDAD_Y_CONTRASENAS_HISPA_SYNG.docx",
    "SECURITY_PASSWORDS_AND_ACCESS_HISPA_SYNG_EN.docx",
    "logos.png","requirements-lock-py313-win64.txt","requirements.txt",
}
root_files={p.name for p in ROOT.iterdir() if p.is_file()}
unexpected=sorted(root_files-allowed_root_files)
missing=sorted((allowed_root_files-{".gitattributes"})-root_files)
data_dir=ROOT/"Datos_data"
expected_data_files={"Ingesta_provisional.xlsx","traits.xlsx"}
data_files={p.name for p in data_dir.iterdir() if p.is_file()} if data_dir.is_dir() else set()
data_unexpected=sorted(data_files-expected_data_files)
data_missing=sorted(expected_data_files-data_files)
resources_dir=ROOT/"Resources"
resource_checks=[
    resources_dir/"areas_protegidas",
    resources_dir/"demarcaciones_miteco"/"Demarcaciones_Marinas_20220909_ModeloDatosINSPIRE.shp",
    resources_dir/"GSHHS"/"GSHHS_h_L1.shp",
    resources_dir/"Mallas_marinas_MITECO.zip",
]
resource_missing=[str(p.relative_to(ROOT)) for p in resource_checks if not p.exists()] if resources_dir.exists() or __import__("os").environ.get("HISPA_REQUIRE_RESOURCES") == "1" else []
print("Resources: present (validated below)" if resources_dir.exists() else "Resources: excluded; core SIN_RESOURCES package validation only")
compiled=[p for p in ROOT.rglob('*') if p.is_file() and p.suffix in {'.pyc','.pyo'}]
compiled += list(ROOT.rglob('__pycache__'))
security_tools=[ROOT/"herramientas"/"hispa_security.py", ROOT/"herramientas"/"seguridad_proyecto.py", ROOT/"herramientas"/"secure_execution.py"]
security_missing=[str(p.relative_to(ROOT)) for p in security_tools if not p.is_file()]
cache_dirs=[p for p in (ROOT/'.cache',) if p.exists()]
if unexpected or missing or data_unexpected or data_missing or resource_missing or security_missing or compiled or cache_dirs:
    raise AssertionError(f'Distribution hygiene failed: unexpected={unexpected}; missing={missing}; data_unexpected={data_unexpected}; data_missing={data_missing}; resource_missing={resource_missing}; security_missing={security_missing}; compiled={len(compiled)}; cache={len(cache_dirs)}')
print('PASS distribution hygiene')

# cmd.exe launchers must keep Windows line endings in the distributed bytes.
for path in ROOT.rglob('*.bat'):
    content = path.read_bytes()
    remainder = content.replace(b'\r\n', b'')
    assert content.startswith(b'@echo off\r\n'), path
    assert b'\r' not in remainder and b'\n' not in remainder, path
print('PASS Windows BAT byte format (CRLF, no BOM)')
