# Hispa-Syng v1.0

This source package includes the software, manuals, `Datos_data/traits.xlsx` and the example workbook `examples/Ingesta_ejemplo.xlsx`. The operational observation workbook and the `Resources/` cartography folder are supplied separately. Prepare both before running an analysis, as explained below.

**Bilingual spatial, temporal and ecological analysis software for Syngnathidae records in Spanish marine waters.**  
**Software bilingüe para el análisis espacial, temporal y ecológico de registros de Syngnathidae en aguas marinas españolas.**

Hispa-Syng v1.0 was developed within the **Hippo-DEC project** at **IIM-CSIC (Vigo, Spain)**. The distribution includes Spanish and English editions that share a common launcher, Python environment, data selection and analysis parameters.

Hispa-Syng was developed with funding for the Hippo-DEC project provided by the Ministry for the Ecological Transition and the Demographic Challenge (MITECO) of the Government of Spain.

> Version: **v1.0**  
> Software licence: **PolyForm Noncommercial License 1.0.0**  
> User manuals and guides: **CC BY-NC 4.0**  
> Zenodo DOI: [10.5281/zenodo.24157711](https://doi.org/10.5281/zenodo.24157711)

[Leer en español](https://github.com/MiquelPlanas/Hispa-Syng-Map/blob/main/LEEME.md) · [Documentation index](https://github.com/MiquelPlanas/Hispa-Syng-Map/blob/main/README.md#documentation)

## Quick start

1. Extract the complete Hispa-Syng source package into a Windows folder with write permission.
2. For a demonstration, **copy** [examples/Ingesta_ejemplo.xlsx](examples/Ingesta_ejemplo.xlsx) into `Datos_data/` and rename the copy to **`Ingesta_provisional.xlsx`**. Keep the original example in `examples/`. For your own analysis, use a compatible observation workbook instead; do not overwrite an existing workbook without first saving it elsewhere.
3. Download `Resources.zip` from **Assets** on the [Releases page](https://github.com/MiquelPlanas/Hispa-Syng-Map/releases). Extract the ZIP so that the `Resources/` folder sits next to `Hispa-Syng.bat`.
4. Run `Hispa-Syng.bat`.
5. Type `1` or `2` to select the language for installation and execution messages, then press Enter. Choose **Run Hispa-Syng** in the main menu.
6. Select the analysis period, MITECO grid resolution, region, species and temporal comparison periods. The same selection is used by both editions.

Use example results only to learn and check the workflow; they are not scientific evidence about real occurrences. Local operational workbooks are excluded from version control by `.gitignore`.

The console reports every main stage and analytical substep, with an elapsed
`[HH:MM:SS]` timer for each edition and for the complete bilingual run.

The project root may be moved or renamed. Do not separate or rename the `PYTHON_ESP` and `PYTHON_ENGLISH` directories.

The recommended shared layout is:

```text
Datos_data/
├── Ingesta_provisional.xlsx
└── traits.xlsx

Resources/
├── areas_protegidas/
├── demarcaciones_miteco/
├── GSHHS/
└── Mallas_marinas_MITECO.zip
```

Internal bilingual run configurations and manifests are stored automatically under `.ejecuciones/<id>/`; analytical products remain under `Resultados/`.


## Main capabilities

Hispa-Syng integrates:

- Observation/validation maps with complete record metadata.
- Abundance-point maps.
- Grid-based richness, density, abundance and dominant-species maps.
- Heatmaps.
- Separate ecological-priority, temporal-monitoring-priority and data-adequacy products, plus protection-gap summaries and two explicitly different conservation geometries. **Strategic priority areas** retain the scientific planning methodology: they are anchored by High/Very-high cores and may include one direct ring of adjacent Medium supporting extensions with minimum recurrence; strong isolated Medium units remain separate validation candidates. **Operational conservation areas** are then delineated without recalculating or reclassifying priority: official MITECO 1-km cells containing observations inside each strategic area are clipped to the strategic geometry and merged only when they share an edge (rook contiguity). Empty cells are never inserted to bridge separated evidence clusters, so one strategic area may contain several operational subareas. These evidence-anchored operational footprints are intended to focus feasible field or management action; they are not inferred population boundaries or habitat-suitability envelopes. When the requested analytical grid is 1 km, the viewer additionally keeps the 1-km ecological classification as a separate **descriptive-priority layer**, while strategic-area delineation uses a minimum 5-km planning unit. At 5 or 10 km, descriptive and planning resolutions coincide, while the operational evidence footprint still uses the official 1-km multiscale grid. Conservation uses three explicit ecological pathways: convergent evidence, persistent occurrence, and diversity cores; an isolated record can never define a High/Very high conservation unit. Within planning units, years, events, richness and abundance are recalculated directly from assigned observations rather than inherited from intermediate temporal summaries.
- Spatial and temporal analyses.
- Community and beta-diversity analyses. The community core uses Hellinger–Euclidean as the primary relative-composition view and Jaccard as the incidence view; raw Bray–Curtis is retained as sensitivity/exploratory network input. LCBD is exported for Jaccard and Hellinger with BH-FDR and observation-event support, PCoA applies Lingoes when needed, and distance-decay inference uses permutation Mantel–Spearman tests.
- Biogeographical clustering, LCBD and multiscale analyses. At 1 km, the similarity network is adaptively sparsified to at most 12 neighbours per cell; raw Louvain communities remain auditable while analytical presentation is capped at eight merged clusters. Tests performed on clusters built from the same community composition are treated as post-hoc descriptive characterization, not independent confirmation.
- Habitat, depth and sex-related summaries.
- Taxonomic and functional analyses based on the included trait database. Functional diversity uses only species present in the selected run, an explicit six-trait Gower schema, the resulting Gower/PCoA functional space and a common dimensionality across comparable regions. Principal FRic/FEve/FDiv/FDis/RaoQ results are incidence-based; observation-abundance weighting is retained only as a sensitivity analysis, with explicit trait-coverage and excluded-species diagnostics.
- Tables, figures, GIS outputs, Word reports and reusable data exports.
- Automatic integrated technical reports in Spanish and English, with equivalent structure, scientific interpretation, labelled priority-area maps and root-relative output traceability.
- Bilingual static web publication of the generated interactive products.

## Bilingual editions

```text
PYTHON_ESP/       Spanish edition
PYTHON_ENGLISH/   English edition
```

The two editions are coordinated by the root launcher and use a common selection of parameters.

## Results and integrated technical report

A bilingual run writes both editions under the root-level `Resultados/` directory:

- `Resultados/ejecucion_<id>_ESP/` — Spanish run;
- `Resultados/run_<id>_EN/` — English run;
- `Resultados/Publicacion_Web_Bilingue_<id>/` — bilingual static web publication.

At the end of a complete run, the integrated technical reports are created at:

- `Resultados/ejecucion_<id>_ESP/10_informe_tecnico/Informe_Tecnico_Integral_Hispa-Syng_v1.0_ES.docx`
- `Resultados/run_<id>_EN/10_technical_report/Hispa-Syng_v1.0_Integrated_Technical_Report_EN.docx`

The two reports use the same scientific structure and analytical content. They include developed interpretation of the run outputs, labelled priority-area overview/detail maps when priority areas are available, and a final file-location section expressed only as paths relative to the Hispa-Syng program root.

Conservation popups include species-level abundance and density: each prioritised cell lists the species present with cell-level abundance and density, while each priority area provides the corresponding area-level summary (individuals per km² of marine area). Displayed and exported density values use at most two decimal places, while analytical calculations retain full precision. `Area_mar_km2` is obtained primarily from MITECO geometry after subtracting GSHHS land in EPSG:3035. If GSHHS produces a coastal false zero but MITECO confirms valid official marine surface, the fallback geometry is the actual intersection between the cell and the official MITECO marine subdivision. `Area_mar_km2` is calculated from that same geometry, and the marine geometry displayed in maps is identical to the geometry used as the density denominator.

Density colour scales in Maps 2 and 3 are visual aids only. When at least 20 cells have positive density, the colour ceiling is based on the empirical 95th percentile (P95) and rounded to a readable legend limit; cells above that limit retain their exact density but use the darkest colour. With fewer than 20 positive cells, the full observed maximum is used. Map 2 recalculates this robust scale whenever the active species selection changes. Numerical values in popups, tables, downloads and analyses are never clipped or winsorised.

To avoid repeating the expensive GSHHS clipping step, Hispa-Syng maintains a validated persistent cache in `.cache/marine_areas`. The first use of a grid resolution calculates the required GSHHS marine areas; later runs reuse only cells whose exact MITECO geometry fingerprint matches and only while the content signature of GSHHS is unchanged. Spanish and English editions share the same cache. MITECO-fallback cells are identified at runtime from the official marine information and are not silently converted into ordinary GSHHS cells. The cache can be deleted safely and will be rebuilt automatically.

## Spatial assignment and coastal marine area

Regional membership and analytical cell assignment are separated deliberately. Hispa-Syng first uses direct point-to-subdivision intersection; when that is unavailable, it fixes a canonical region from the official 10-km MITECO reference grid, independently of whether the analytical run uses 1, 5 or 10 km cells. The selected analytical grid is then used for cell assignment, marine area, density and spatial analyses. The regional audit is written to the edition-specific quality-control folder.

Observation assignment uses the official MITECO grid as the spatial reference. Marine area is derived primarily from GSHHS clipping. When GSHHS produces a coastal false zero but MITECO confirms valid official marine surface, Hispa-Syng retains the original MITECO cell through a marine-subdivision fallback whose geometry is the actual cell–marine-subdivision intersection and whose area is therefore identical to the geometry used for display and density. Only observations still unresolved after that step are eligible for `nearest`, and only against cells with positive GSHHS marine surface within the configured tolerance. Valid observations that still cannot be assigned safely remain visible in Map 1 and complete observation downloads but are excluded from cell-based spatial metrics. `nearest` and unassigned cases are documented in the edition-specific quality-control folder through the detailed assignment audit, its summary and the interactive spatial-assignment QC map.

## Documentation

**Suggested reading:** start with this README, then the installation/publication guide. Consult the full manual for scientific interpretation and the security guide before enabling protection or preparing a copy to share. You do not need to read every file before starting.

The Spanish and English documents below serve matching purposes. The root README describes the whole bilingual project; the README inside each edition provides edition-specific instructions.

| What you need | Spanish | English |
| --- | --- | --- |
| Start and understand the layout | [LEEME.md](LEEME.md) | [README.md](README.md) |
| Install, run, repair and publish the website | [MANUAL_INSTALACION_PUBLICACION.docx](MANUAL_INSTALACION_PUBLICACION.docx) | [INSTALLATION_AND_WEB_PUBLICATION.docx](INSTALLATION_AND_WEB_PUBLICATION.docx) |
| Understand analyses, metrics and results; examples and glossary | [Manual_Hispa_Syng_v1_0_ES.docx](Manual_Hispa_Syng_v1_0_ES.docx) | [Manual_Hispa_Syng_v1_0_EN.docx](Manual_Hispa_Syng_v1_0_EN.docx) |
| Understand passwords, credentials, copies and folders through seven practical cases | [SEGURIDAD_Y_CONTRASENAS_HISPA_SYNG.docx](SEGURIDAD_Y_CONTRASENAS_HISPA_SYNG.docx) | [SECURITY_PASSWORDS_AND_ACCESS_HISPA_SYNG_EN.docx](SECURITY_PASSWORDS_AND_ACCESS_HISPA_SYNG_EN.docx) |
| Consult execution and outputs for one edition | [PYTHON_ESP/LEEME.md](PYTHON_ESP/LEEME.md) | [PYTHON_ENGLISH/README.md](PYTHON_ENGLISH/README.md) |
| Consult the workflow and analysis blocks in Markdown | [PYTHON_ESP/MANUAL_ANALISIS_COMPLETO.md](PYTHON_ESP/MANUAL_ANALISIS_COMPLETO.md) | [PYTHON_ENGLISH/FULL_ANALYSIS_MANUAL.md](PYTHON_ENGLISH/FULL_ANALYSIS_MANUAL.md) |
| Prepare input columns and understand cartographic requirements | [PYTHON_ESP/ESPECIFICACION_ENTRADAS_Y_CARTOGRAFIA.md](PYTHON_ESP/ESPECIFICACION_ENTRADAS_Y_CARTOGRAFIA.md) | [PYTHON_ENGLISH/INPUT_AND_CARTOGRAPHY_SPECIFICATION.md](PYTHON_ENGLISH/INPUT_AND_CARTOGRAPHY_SPECIFICATION.md) |
| Consult a short setup guide for one edition | [PYTHON_ESP/LEEME_PRIMERO.txt](PYTHON_ESP/LEEME_PRIMERO.txt) | [PYTHON_ENGLISH/READ_ME_FIRST.txt](PYTHON_ENGLISH/READ_ME_FIRST.txt) |
| Move the installation to another folder or computer | [PYTHON_ESP/TRASLADO_Y_EJECUCION.md](PYTHON_ESP/TRASLADO_Y_EJECUCION.md) | [PYTHON_ENGLISH/RELOCATION_AND_EXECUTION.md](PYTHON_ENGLISH/RELOCATION_AND_EXECUTION.md) |
| Consult edition-specific validation criteria | [PYTHON_ESP/VALIDACION.md](PYTHON_ESP/VALIDACION.md) | [PYTHON_ENGLISH/VALIDATION.md](PYTHON_ENGLISH/VALIDATION.md) |
| Consult dated package validation reports | [Validation/VALIDACION_ES.md](Validation/VALIDACION_ES.md) | [Validation/VALIDACION_EN.md](Validation/VALIDACION_EN.md) |

Other shared reference files:

| File | Purpose |
| --- | --- |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Sources and notices for cartography, online basemaps and third-party components. |
| [CITATION.cff](CITATION.cff) | Software citation metadata. |
| [LICENSE](LICENSE) | Licence terms for the Hispa-Syng source code. |
| [tests/README.md](tests/README.md) | Scope, commands and families of regression tests. |
| [Validation/COMPROBACION_WINDOWS.md](Validation/COMPROBACION_WINDOWS.md) | Native Windows checklist; this is not a report of passed checks. |
| [Validation/LECTURA_ESPACIAL.md](Validation/LECTURA_ESPACIAL.md) | Dated MITECO grid-reading benchmark. |
| [Validation/REVISION_CAPAS_PROTEGIDAS.md](Validation/REVISION_CAPAS_PROTEGIDAS.md) | Review of protected-area cartographic layers; this does not validate the whole analysis. |

The JSON files under `Validation/` retain structured results from specific checks. Their dates, environments and scope belong to those checks. The included reports describe automated tests on Linux; native Windows checks and a complete operational run require their own evidence. Later file changes do not automatically update those records or `Validation/CONTENIDO_SHA256.txt`.

## Environment and reproducibility

The normal installation uses the project `requirements.txt`. The installer accepts **64-bit Python 3.10–3.13** and prefers Python 3.13 when available. The `requirements-lock-py313-win64.txt` file records a dependency configuration intended for Python 3.13 on Windows x64; it does not replace the normal installation requirements.

The historical general-suite validation records were produced on Linux with Python 3.12.14. The separately reviewed Windows operational run of 19 October 2026 records Python 3.13.15, pandas 2.3.3 and GeoPandas 1.2.0 in both editions, with matching principal QA values. See [the Windows run evidence](Validation/EJECUCION_WINDOWS_20261019.md) for its recorded scope. Current JSON reports retain the exact recorded file paths; see [the reference-integrity checks](Validation/REFERENCIAS_JSON_VALIDACION.md) for tests and limits. See [Validation/VALIDACION_EN.md](Validation/VALIDACION_EN.md) for evidence, package identity and remaining native checks.

A separately supplied [Windows security-test log](Validation/SEGURIDAD_WINDOWS_20261021.md) reports nine scenario groups and a current-user DPAPI roundtrip passed. Cross-account isolation and independent ACL checks remain unverified; see that report for the recorded scope.

Generated environments, caches and run products are not part of the source distribution and should not be version-controlled.

### Observation-event proxy infrastructure

Each valid projected observation receives a deterministic technical field named `sampling_event_id`. In v1.0 the identifier is defined from the parsed observation date, normalized observer name and EPSG:3035 position rounded to 1 m. Species, abundance, the source `Id` field and selected grid resolution are deliberately excluded. If observer information is missing, the source spreadsheet row is used as a conservative fallback so separate records are not merged without evidence.

In Hispa-Syng v1.0, the **temporal analysis uses `n_sampling_events` as its primary observation-intensity proxy** while retaining `n_records` as a descriptive/sensitivity field. Primary species trends are Poisson count models with a `log(n_sampling_events)` offset and a conservative Pearson overdispersion correction; species with insufficient temporal support remain descriptive only. Cell-level temporal change is calculated on the official selected-resolution MITECO `grid_id` with unit-invariant symmetric relative-change components. The same proxy-event infrastructure is used by the community, official-MITECO multiscale and conservation-support calculations. Every run writes explicit QA for event support and analytical status.

### Regression tests

A lightweight bilingual regression suite is included in `tests/`. After the normal `.venv` has been created, run `RUN_REGRESSION_TESTS.bat` from the project root. The suite uses synthetic temporary geometries and does not modify operational data or analytical results. It checks critical regressions in density calculation, marine-cell assignment, the GSHHS cache, conservation popup enrichment, export rounding, source syntax and required packaged templates.

## Data and external resources

Hispa-Syng expects the required observation data and cartographic resources to be available in the project structure. Some large geospatial resources may be distributed separately from the GitHub source repository.

The project includes `Datos_data/traits.xlsx`, which provides the trait information used by the relevant analyses.

### Interactive basemaps

The main interactive maps offer three online basemaps, in this order: **Satellite — Esri World Imagery** (active by default), **Marine bathymetry — EMODnet Bathymetry World Base Layer**, and **Physical — OpenTopoMap**. The spatial-assignment quality-control map uses **Satellite** (default) and **Physical** only; it does not request tiles from the standard OpenStreetMap tile server. All basemaps provide visual context only and are not used in scientific calculations. They require an Internet connection but no API key or subscription.

The bilingual taxonomic-versus-functional richness figures display taxonomic
richness against **relative FRic** (regional FRic divided by the global selected-species
functional hull) for each region with valid results. If regions have identical
values on both axes, their markers are shifted slightly in X for visibility only;
exported metrics and tables keep the original analytical values.

## Web publication

After a successful bilingual run, Hispa-Syng can create a static bilingual publication folder containing the interactive products. A web server only needs to serve the generated static files; Python is not required to view maps that have already been generated.

See the installation/publication manuals for deployment details.

## Input data in the public distribution

The public source package **does not include** the real `Ingesta_provisional.xlsx` occurrence workbook. Operational occurrence data must remain outside the repository. For a demonstration, copy `examples/Ingesta_ejemplo.xlsx` to `Datos_data/Ingesta_provisional.xlsx`, as described in Quick start. For your own analysis, place a compatible workbook at that path or configure its path. Keep real operational data outside version control.

## Security, passwords, and credentials

Hispa-Syng can operate as an **open project** or a **protected project**. The password belongs to the project rather than to an individual run: after protection is enabled, subsequent runs of that same project use the same security configuration until the owner changes the password or rotates the key. The password is never stored in plaintext or embedded in source code.

After language selection, `Hispa-Syng.bat` offers `Run Hispa-Syng`, `Security and access`, and `Exit`. The security menu can enable protection, show status, change the password, create/import `.hsk` credentials, open `.hse` files, create open/protected copies, forget remembered access, clean decrypted temporary copies, review existing outputs, and rotate the project key.

Enabling protection encrypts `Datos_data/Ingesta_provisional.xlsx` as `Datos_data/Ingesta_provisional.hse`; the plaintext workbook is removed only after the encrypted container is cryptographically verified. During protected runs, the workbook is decrypted **in memory** for analysis. In protected mode, products are generated in a private temporary area outside Resultados, restricted to the operating-system user. They are encrypted and verified before being placed in Resultados or the web publication. Computation may require plaintext temporary files inside that private area; this protection does not provide continuous encryption of all local storage. Map 1 and the QC map, tables, documents, packages, logs and every product lacking explicit public classification are encrypted. Registered aggregate maps 2 and 3, viewers, aggregate conservation maps and institutional assets are verified and remain available. Names and extensions do not grant public access. Individual-observation fields and points are rejected. The official protection layer permits catalog points. Cells and zones display only polygon components, without changing analytical geometry. Unregistered figures and auxiliary files are encrypted by default. Sensitive HTML displays an informational page and retains the original in .html.hse. The audit records every file, its classification, reason and SHA-256. Hashes support integrity comparison, not owner authentication.

On Windows, **Remember access for this Windows user** stores the project key with Windows DPAPI for the current Windows user. Later runs of the same project under that Windows user can proceed without re-entering the password. Remembered access does not travel with a copied project folder and must be authorized again on another computer or Windows account.

`.hsk` files are **bearer credentials** and must be handled as secrets. An `access` credential contains the material needed to decrypt the project but **does not carry owner authority**. Owner/recovery authority is protected by an additional independent owner token, so an access credential cannot be promoted to `owner_recovery` merely by editing the file. An `owner_recovery` credential carries both data access and that independent owner authority. Changing the password does **not** revoke issued access credentials. `Withdraw previous access to the current project (rotate key)` creates a new project key and owner authority, re-encrypts `.hse` files, and requires a new recovery credential.

A **fully open copy** is deliberately created without project-security configuration and with a plaintext input workbook; it is intended for a fully trusted collaborator. A **protected copy** receives its own project ID, password, and key, independent from the source project. Project copies exclude `Resultados`, `.ejecuciones`, `.venv`, `.git`, and execution caches, so the original project is not modified.

In protected mode, products are generated in a private temporary area outside Resultados, restricted to the operating-system user. They are encrypted and verified before being placed in Resultados or the web publication. Computation may require plaintext temporary files inside that private area; this protection does not provide continuous encryption of all local storage. Before starting a protected analysis, the program automatically checks pending recovery and existing results. A run interrupted during computation is recovered as incomplete, with protected products; it is not presented as a completed scientific run. If verification or recovery fails, the program blocks the new analysis and retains the pending journal. Review and protect existing outputs also performs this review from the menu.

The protected-project menu also includes `Manage password and access > Save or renew owner recovery`, which is useful whenever the owner needs another recovery file. Hispa-Syng distributes neither a universal password nor plaintext password files. Open an `.hse` through `Hispa-Syng.bat > Security and access > Open protected .hse file`. The file is decrypted to a local temporary folder and can be removed with `Clean temporary decrypted copies`. Ordinary deletion is not forensic secure erasure on SSDs or storage managed by the operating system.

A protected project's web publication remains static for non-sensitive products, but encrypted `.hse` products are **not decrypted in the browser**. A web publication for authorized users therefore requires server-side authentication/authorization, or an intentionally open copy published only in an environment with suitable access controls.

## Licences

The Hispa-Syng source code is licensed under the **PolyForm Noncommercial License 1.0.0**. See [LICENSE](LICENSE) for the full terms.

The user manuals and guides bearing a CC BY-NC 4.0 notice, including this README, are licensed under [Creative Commons Attribution–NonCommercial 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).

Third-party components, cartographic resources, services and marks are subject to their respective terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Citation

Citation metadata are provided in:

```text
CITATION.cff
```

Cite Hispa-Syng Map v1.0 using its Zenodo DOI [10.5281/zenodo.24157711](https://doi.org/10.5281/zenodo.24157711).

## Author

**Miquel Planas Oliver**  
IIM-CSIC

Additional software authors or contributors can be added to the citation metadata before the public release if appropriate.

## Project

Hispa-Syng was developed within the **Hippo-DEC project**.

The public software name is **Hispa-Syng v1.0** and **Hippo-DEC** identifies the framework project. Internal package identifiers such as `hippodec_maps` are technical implementation names.

---

## Resumen en español

**Hispa-Syng v1.0** es un software científico bilingüe desarrollado en el marco del proyecto **Hippo-DEC** para integrar análisis espaciales, temporales, ecológicos y de conservación de registros de signátidos en aguas marinas españolas.

Para comenzar, ejecute `Hispa-Syng.bat` desde la raíz del proyecto. La selección de parámetros se realiza una sola vez y se aplica a las ediciones española e inglesa. Consulte `LEEME.md` y `Manual_Hispa_Syng_v1_0_ES.docx` para la documentación en español.

## Protected results and credential scope

In protected mode, products are generated in a private temporary area outside Resultados, restricted to the operating-system user. They are encrypted and verified before being placed in Resultados or the web publication. Computation may require plaintext temporary files inside that private area; this protection does not provide continuous encryption of all local storage.

Before starting a protected analysis, the program automatically checks pending recovery and existing results. A run interrupted during computation is recovered as incomplete, with protected products; it is not presented as a completed scientific run. If verification or recovery fails, the program blocks the new analysis and retains the pending journal. Review and protect existing outputs also performs this review from the menu.

Map 1 and the QC map, tables, documents, packages, logs and every product lacking explicit public classification are encrypted. Registered aggregate maps 2 and 3, viewers, aggregate conservation maps and institutional assets are verified and remain available. Names and extensions do not grant public access. Individual-observation fields and points are rejected. The official protection layer permits catalog points. Cells and zones display only polygon components, without changing analytical geometry. Unregistered figures and auxiliary files are encrypted by default. Sensitive HTML displays an informational page and retains the original in .html.hse. The audit records every file, its classification, reason and SHA-256. Hashes support integrity comparison, not owner authentication.

Key rotation prepares and verifies new containers and the recovery credential before replacing active files. It keeps a durable journal and recovery backups until the change is committed. After interruption, the next access restores the previous state if the operation was not committed, or finishes cleanup after a completed commit. Rotation cannot start while private runs await recovery.

Rotation prevents old credentials from opening re-encrypted files in the updated project. It cannot withdraw access to retained old copies with their old keys or information already exported. Changing the password or reissuing a recovery credential with the same key and token does not invalidate existing credentials. Forget access removes the local DPAPI record; it does not revoke other retained copies of that record.

DPAPI uses the current Windows-user scope without enabling machine-wide scope. The secret owner token is protected with the password and included only in the recovery credential and, when administrative authority is remembered, the DPAPI material. Configuration stores its verification hash. An access credential does not include that token; an environment role does not grant administration. This separation assumes that an attacker controlling the computer has not replaced the code or local configuration. A user authorized to decrypt can retain or export the data.

## Grid reading and preparation timings

A full analysis uses the official 1, 5 and 10 km grids regardless of the selected resolution and temporal comparisons. Spatial windows near observations are combined into one query per source file, without simplifying their boundaries or changing the selected cells. Original source-cell order is retained. A compatible per-window read is used when the driver has no GEOS support or an edge window is degenerate.

The console reports the source file, query windows, loaded cells and read/preparation timings. The multiscale block separately reports marine-area time and total time per scale. The GSHHS area cache remains reusable; do not delete it. This cache avoids repeated area clipping but does not eliminate source geometry reads. Spatial querying adds no observation-location files or cache of selected geometries.

The project permits one active analysis or maintenance operation. Before creating an open or protected copy, it requires owner authority and recovers pending runs. Recovery failure blocks the copy and its credential while retaining the private area and journal. Incomplete results remain labelled and are excluded from software copies.

Exports preserve original identifiers, comments, observers, links and source filenames in both editions. Presentation labels and habitat categories are localized; internal calculations retain their precision.

## Using protection simply

For ordinary analysis, choose **Run Hispa-Syng** in the main menu. The current folder keeps its open or protected state between runs.

Within **Security and access**, **Protect my current project** encrypts data in this same folder. **Prepare a copy to share** opens a separate section: a protected copy creates another folder with its own password and key; an open copy creates another folder with readable data and no password. Neither copy includes previous results.

In a protected project, **Open protected .hse file** allows you to view results. **Manage password and access** groups password changes, owner recovery, key rotation, output review and management of remembered access and temporary files. To issue an ordinary credential, use **Prepare a copy to share > Create an access file for this project (.hsk)**. For an independent copy, issue the credential from that copy.

Changing the password does not invalidate existing credentials. **Withdraw previous access to the current project (rotate key)** requires new credentials for re-encrypted files; old copies with their old keys remain readable.

**SECURITY_PASSWORDS_AND_ACCESS_HISPA_SYNG_EN.docx** explains folders and the seven practical cases.
