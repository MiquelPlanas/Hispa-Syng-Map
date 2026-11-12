# Hispa-Syng v1.0 — validation scope

This review identifies the evidence included with the distributed source, its environment and its relationship to the ZIP supplied on 21 October 2026. The general validation record contains 32 final PASS checks from 14 October; that suite was not rerun during this documentation update. Recorded results retain their original scope.

## Package and reference documents

The reviewed ZIP is `Hispa-Syng-Map-main.zip`, without `Resources/` or the operational `Datos_data/Ingesta_provisional.xlsx` workbook. It includes `examples/Ingesta_ejemplo.xlsx` and `Datos_data/traits.xlsx`. Its hash and source-code hashes are recorded in [REVISION_EVIDENCIAS_20261021.json](REVISION_EVIDENCIAS_20261021.json). That file identifies the supplied download, not a commit fetched directly from GitHub or the future final ZIP.

The archive hashes in `scientific_reference_validation.json`, `menu_validation.json` and `SELECCION_ESPECIES_VALIDACION.json` identify different comparison references. Unambiguous names and original ZIP bytes are not available here for every reference. None of those hashes is presented as the identity of the current ZIP.

## Relationship between records and reviewed code

| Evidence | Recorded result and scope | Hash comparison with the supplied ZIP |
| --- | --- | --- |
| [validation.json](validation.json) | General suite: 32 final PASS checks; 33 processes, including an initial failed `_release_hygiene` attempt followed by a PASS retry. | 81 of 90 Python files match; nine differ. |
| [SELECCION_ESPECIES_VALIDACION.json](SELECCION_ESPECIES_VALIDACION.json) | Species selection with taxonomic authorities, configuration and 16-field parity; no complete cartographic analysis. | All six identified files match. |
| [CREDITOS_CARTOGRAFICOS_VALIDACION.json](CREDITOS_CARTOGRAFICOS_VALIDACION.json) | Cartographic attribution, presentation and 16-field parity; no full Windows workflow rerun. | All 14 identified files match. |
| [scientific_reference_validation.json](scientific_reference_validation.json) | Earlier comparison of 52 modules and 750 functions/classes; it does not itself demonstrate scientific equivalence of the current ZIP. | 46 of 52 modules match their recorded hashes; six differ. |
| [menu_validation.json](menu_validation.json) | Reports 44 ES/EN scenarios and open-menu subprocess runs; native Windows was not run in that record. | It lacks a sufficient hash inventory to identify the entire tested state. |
| [CAPAS_PROTEGIDAS_VALIDACION.json](CAPAS_PROTEGIDAS_VALIDACION.json) | Review of protected-area files and layers; it does not validate the entire scientific workflow. | Both identified conservation modules match; external layers are absent from this ZIP. |
| [grid_reading_benchmark.json](grid_reading_benchmark.json) | Dated reading benchmark for 15 grid files with test locations; not a complete operational analysis. | Its external cartographic sources are not included in this ZIP. |

All nine files differing from the general-suite record are covered by matching hashes in the later species-selection or cartographic-credit records. This links those changes to specific evidence; it is not a rerun of the general suite on the current state.

## Environment and Windows runs

The general record declares Python 3.12.14 on Linux. It started at 2026-10-14T12:22:31.520636+00:00 and finished at 2026-10-14T12:31:11.627308+00:00 (UTC). Both reports in this review use those dates from the same JSON. The original English prose stated a different time; it is retained unchanged under `evidencias_20261014/`.

That environment belongs to automated preparation tests. Separately, the manifest and ES/EN summaries of Windows operational run `20261019_094827_65e45b50`, dated 19 October, have been reviewed: both editions record completion, Python 3.13.15 and matching principal QA values. See [the run report](EJECUCION_WINDOWS_20261019.md) and [structured comparisons](EJECUCION_WINDOWS_20261019.json). The run uses operational data, 1 km, 12 species and open mode. It does not establish DPAPI, ACL or cross-account checks, or identify the exact executable source commit or ZIP. The historical report identifies translation of `Resultados` to `Results` in English-summary paths. Current JSON presentation preserves recorded references in both English QA writers. The separate [reference-integrity report](REFERENCIAS_JSON_VALIDACION.md) identifies the current source hashes, ten focused tests and their limits. The original October records remain unchanged; this is not a rerun of that Windows analysis.

The `requirements-lock-py313-win64.txt` file identifies a dependency configuration intended for Python 3.13 on Windows. Its existence does not demonstrate that the included general validation ran there.

The dependency-file header declares Windows x64, Python 3.13.15 and generation from a working environment on 17 September 2026. That declaration is retained as file metadata; the October run summary confirms that Python version without providing a complete dependency inventory.

The supplied console record for `tests/_security_lifecycle.py` reports PASS for nine scenario groups and for the DPAPI encryption/decryption roundtrip under the current Windows user. Full-disk and locked-destination failures are injected by the test code; rotation interruptions terminate test subprocesses. Cross-account isolation is explicitly not executed. Independent ACL inspection and an external-process exclusive-file-lock test have not been supplied. The log does not record Windows/Python versions, dependencies, a commit or executed-source hashes; metadata from the 19 October analysis is not assigned to this test. See [the Windows security report](SEGURIDAD_WINDOWS_20261021.md), [the structured record](SEGURIDAD_WINDOWS_20261021.json) and [the original console output](Hispa-Syng_seguridad_Windows.txt).

## Evidence availability and limits

`validation.json` retains commands, status, durations, environment and hashes. Its 33 referenced `.log` files, including the initial attempt, are absent from the supplied ZIP. Recorded declarations are retained, but their output has not been reconstructed and file hashes do not certify that a test ran. Test code is available under `tests/`; some distribution checks require external resources.

`CONTENIDO_SHA256.txt` is retained as the historical delivery inventory, not an inventory of the current ZIP or this patch. `INVENTARIO_REVISION_DOCUMENTAL_SHA256.txt` belongs to the previous documentation delivery. The 19 October operational-evidence delivery has its inventory in `INVENTARIO_EVIDENCIAS_WINDOWS_SHA256.txt`; this security-evidence delivery is identified by `INVENTARIO_SEGURIDAD_WINDOWS_SHA256.txt`. The full-distribution inventory and archive hash will be generated when that distribution is finalized.

The procedures in [COMPROBACION_WINDOWS.md](COMPROBACION_WINDOWS.md) allow DPAPI checks for the current and another user, private-area ACL checks, interruption, file locks and rotation recovery to be documented. Each check retains its status until supported by its own evidence. Test-data parity on 16 fields does not certify equivalence across every configuration or operational dataset.

To produce a new regression report from the project root with the environment installed: `.venv\Scripts\python.exe tests\run_regression_tests.py --report-dir ..\Hispa-Syng_validation_Windows`. Keep the resulting records outside the repository and exclude passwords or credentials. This command is a procedure; it was not executed in this review.

The historical documentation review did not rerun the general suite. The current reference-integrity checks are recorded separately in REFERENCIAS_JSON_VALIDACION.json. They do not repeat the full-cartography analysis or convert unrelated pending checks into PASS.

## Retained general-suite results

The table is generated from `validation.json`; timings belong to the historical run.

| Test | Status | Seconds |
| --- | --- | ---: |
| _grid_reading_PYTHON_ESP | PASS | 1.481 |
| _edition_regressions_PYTHON_ESP | PASS | 7.581 |
| _conservation_smoke_PYTHON_ESP | PASS | 5.209 |
| _community_integration_smoke_PYTHON_ESP | PASS | 34.108 |
| _multiscale_integration_smoke_PYTHON_ESP | PASS | 32.141 |
| _conservation_integration_smoke_PYTHON_ESP | PASS | 8.986 |
| _functional_integration_smoke_PYTHON_ESP | PASS | 35.517 |
| _configuration_matrix_PYTHON_ESP | PASS | 26.044 |
| _output_folder_localization_PYTHON_ESP | PASS | 0.033 |
| _metadata_exports_PYTHON_ESP | PASS | 0.948 |
| _public_output_policy_PYTHON_ESP | PASS | 2.436 |
| _public_geometry_PYTHON_ESP | PASS | 7.362 |
| _grid_reading_PYTHON_ENGLISH | PASS | 2.376 |
| _edition_regressions_PYTHON_ENGLISH | PASS | 5.916 |
| _conservation_smoke_PYTHON_ENGLISH | PASS | 6.636 |
| _community_integration_smoke_PYTHON_ENGLISH | PASS | 17.985 |
| _multiscale_integration_smoke_PYTHON_ENGLISH | PASS | 6.112 |
| _conservation_integration_smoke_PYTHON_ENGLISH | PASS | 9.175 |
| _functional_integration_smoke_PYTHON_ENGLISH | PASS | 17.954 |
| _configuration_matrix_PYTHON_ENGLISH | PASS | 7.593 |
| _output_folder_localization_PYTHON_ENGLISH | PASS | 0.087 |
| _metadata_exports_PYTHON_ENGLISH | PASS | 0.653 |
| _public_output_policy_PYTHON_ENGLISH | PASS | 2.324 |
| _public_geometry_PYTHON_ENGLISH | PASS | 5.782 |
| _bilingual_parity | PASS | 34.436 |
| _presentation_and_distribution | PASS | 0.546 |
| _security_regressions | PASS | 2.311 |
| _security_lifecycle | PASS | 4.453 |
| _coordinator_security | PASS | 0.633 |
| _execution_recovery | PASS | 1.453 |
| _distribution_recovery | PASS | 0.849 |
| _release_hygiene | PASS | 0.037 |

| Dependency | Recorded version |
| --- | --- |
| numpy | 2.3.5 |
| pandas | 2.3.3 |
| geopandas | 1.2.0 |
| shapely | 2.1.2 |
| pyproj | 3.8.0 |
| pyogrio | 0.11.1 |
| scipy | 1.17.0 |
| matplotlib | 3.10.8 |
| seaborn | 0.13.2 |
| scikit-learn | 1.8.0 |
| statsmodels | 0.14.6 |
| cryptography | 46.0.0 |
| python-docx | 1.2.0 |
