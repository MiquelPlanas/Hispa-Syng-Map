# Hispa-Syng v1.0 — SIN_RESOURCES validation

Completion UTC: 2026-10-14T10:21:19.812381+00:00. Environment: Python 3.12.14, Linux x86_64. Result: 32 PASS subprocesses with exit code 0.

## Behavior and tests

Protected runs generate products in a private area and encrypt and verify them before publication. A project lock covers the operation. A durable journal survives interruption; computation interrupted before verification is recovered as incomplete. Published hashes support interrupted cleanup and reject altered outputs.

Open/protected copy creation authenticates owner authority and recovers pending source runs first. Recovery failure creates no destination or credential and retains pending material. Software copies exclude results. The menu reports pending states.

Public products require explicit generator registration with product type and file-byte SHA-256. Filenames and extensions do not authorize exceptions. Structured public JSON rejects individual-observation fields and points. Official protection catalog points are admitted only in their explicitly typed layer with four catalog fields and source. Aggregate geometry collections display polygon components without modifying analytical geometry. Tests exercise real conservation preparation in open/protected modes for both editions. Altered files lose their public classification. Unregistered products, including figures and auxiliary files, are encrypted. Locked HTML requires its authenticated encrypted container.

Both editions render real aggregate maps/viewers and exercise copy/link rewriting through the web builder. Tests reject observers, comments, observation links, source rows, event identifiers and individual latitude/longitude. Download-document bytes in the web-builder test are synthetic fixtures. Protection audits record all files, classification, reason, size and SHA-256; tests require exact inventory coverage.

Owner authority requires a token independent of the data key. Tests cover manipulated ordinary credentials, authenticated migration and administration rejection without the token. Rotation prepares, verifies and backs up before replacement; tests include actual termination before/after commit and injected disk/write/lock failures. Revocation concerns re-encrypted project files; old copies and exported data remain accessible with their corresponding credentials.

## Evidence and scientific calculations

validation.json records commands, exit codes, durations, environment, loaded dependency versions and source SHA-256. Individual .log files retain output. CONTENIDO_SHA256.txt covers included files except itself. The final ZIP SHA-256 is provided externally to avoid circular identification.

scientific_reference_validation.json identifies the reference ZIP by SHA-256, compares 52 modules and records 750 unchanged function/class syntax trees. Identified changes concern rendering, links and publication; calculation modules remain byte-identical. This is not certification of every operational combination. ES/EN parity requires exact equality of 16 serialized snapshot fields after numerical rounding to 12 decimals. Both input workbooks remain byte-identical.

Public policy is identical in both editions and the coordinator. The ES/EN security guides are rendered and every page is reviewed visually. Scientific manuals retain their content. Both editions’ README instructions describe the menu routes.

## Scope and limits

Resources is excluded. Partial Resources directories fail distribution checks; HISPA_REQUIRE_RESOURCES=1 requires all resources. The separately dated benchmark in LECTURA_ESPACIAL.md/grid_reading_benchmark.json was not repeated here. resources_reference_sha256.json describes external resources.

No complete operational-workbook/cartography analysis was run. Native Windows, DPAPI/ACL, cross-account isolation and the full BAT workflow remain untested. Python 3.10 was not executed here. Injected failures do not cover every physical power-loss scenario.

Classification assumes trusted code, generators, configuration and institutional assets. Structured-field checks are not a universal sensitive-content detector for arbitrary prose, images or deliberately concealed data. Unregistered products are encrypted by default. Plaintext temporary files can exist inside the private area; forensic erasure is not guaranteed. Hashes do not authenticate the owner.

Reproduce: `python tests/run_regression_tests.py --report-dir ../Hispa-Syng_validation`.

## Security menus

Navigation separates protecting the current project, sharing copies and managing access. The independent tests/_security_menu.py check exercises 44 cases across ES and EN: routing, open/protected states, state transition and cancellation without file creation. Open menus also run in real processes in both languages. menu_validation.json and _security_menu.log record the check.

Byte comparison with the reference package identified in menu_validation.json confirms that 84 src files and both input workbooks are preserved. Encryption and analysis-coordination files also remain byte-identical; executable changes are limited to the menu coordinator. Records retain the initial attempt and repeat of the package-content check; its 32 checks have a final PASS result. Native Windows execution was not performed.

| Test | Status | Seconds |
|---|---|---:|
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

| Dependency | Loaded version |
|---|---|
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
