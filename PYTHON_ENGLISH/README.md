# Hispa-Syng v1.0 — English edition (Hippo-DEC project)

**Licence for this guide:** [Creative Commons Attribution–NonCommercial 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/). The source code is governed by the [PolyForm Noncommercial License 1.0.0](../LICENSE).

This application provides the Hispa-Syng v1.0 cartographic and ecological
workflow in English, developed within the Hippo-DEC project. It reads the original `Ingesta_provisional.xlsx` workbook
without changing its sheet, headings or values. Spanish input headings are
recognised as aliases and converted only inside the program.

## Main products

- three interactive distribution maps, the priority conservation map and a
  single four-tab web viewer;
- complete-information downloads in the integrated viewer's top toolbar only:
  Word, Excel and a reusable data ZIP;
- an upload-ready static `Web_Publication` folder and comprehensive user manual;
- descriptive summaries of observation intensity, richness, abundance, recorded-detection frequency/relative detection breadth and dominance;
- habitat, depth and sex-composition analyses;
- community matrices, beta diversity, PERMANOVA, betadisper, NMDS and PCoA;
- IndVal, SIMPER, co-occurrence, rank-abundance and distance-decay analyses;
- LCBD, rarity, coldspots and integrated biogeographical singularity;
- community: proxy-event support; Hellinger–Euclidean and Jaccard as primary views; Jaccard/Hellinger LCBD with BH-FDR; Bray–Curtis PCoA with Lingoes; Mantel–Spearman distance decay; regional IndVal with BH-FDR; Louvain clusters treated as exploratory/post-hoc;
- relative recorded-detection classification, latitudinal gradients and optional functional diversity (selected observed species only, explicit trait schema, Gower/PCoA functional space, common FRic/FDiv dimensionality, incidence-based principal metrics and abundance-weighted sensitivity);
- similarity networks, Louvain clusters and threshold-sensitivity analyses;
- 10, 5 and 1 km multiscale analyses, hotspots and persistence;
- advanced temporal models, comparisons, maps, rankings and narratives;
- separate ecological-priority, temporal-monitoring-priority and data-adequacy products;
- **strategic priority areas** produced by the existing scientific method: High/Very-high cores, one optional direct ring of adjacent Medium supporting extensions with minimum support, and isolated strong Medium validation candidates. When 1 km is requested, the viewer retains 1-km descriptive priority while 5-km planning units delineate these strategic areas;
- **operational conservation areas** derived afterwards without recalculating priority: official MITECO 1-km cells containing observations inside each strategic area, merged only by rook contiguity and never connected through empty bridge cells. A strategic area may therefore yield several operational subareas. These evidence-anchored footprints focus practical action but are not complete population boundaries or habitat-suitability models;
- three explicit ecological pathways (convergent evidence, persistent occurrence, and diversity cores), so an isolated record cannot define a High/Very high unit; explicit field-validation flags, multi-select priority/spatial-role filtering, protection gaps, management recommendations, an interactive map, GeoPackages and Word reports;
- quality-control files and SHA-256 output manifests.

All user-facing console text, HTML maps, popups, legends, figures, reports,
tables, exported column names, categories, folders and output filenames are in
English. Scientific names, official MITECO codes and original metadata values
are preserved.

## Basemaps

The main viewers offer **Satellite — Esri World Imagery** (default), **Marine bathymetry — EMODnet Bathymetry World Base Layer**, and **Physical — OpenTopoMap**, in that order. `Spatial_Assignment_QC_Map.html` uses **Satellite** (default) and **Physical** only and does not request tiles from the standard OpenStreetMap tile server. All are online context basemaps: Internet access is required, no API key or subscription is required, and they are not used in scientific calculations.

## Required input data

Keep `Ingesta_provisional.xlsx` (or a numbered copy) and `traits.xlsx` in `Datos_data/`, and keep the institutional logo PNG in the project root. Place these cartographic resources inside `Resources/`:

1. `Mallas_marinas_MITECO.zip` or the extracted MITECO-grid folder;
2. `demarcaciones_miteco`, containing the MITECO marine-subdivision shapefile
   and its companion files;
3. `GSHHS`, containing `GSHHS_h_L1.shp` and its companion files, or a GSHHS
   ZIP;
4. `areas_protegidas`, containing readable `.shp` or `.gpkg` layers when
   available.

Recommended optional inputs:

- `areas_protegidas` supports overlap and conservation-gap assessment;
- `Datos_data/traits.xlsx` enables functional diversity;
- the institutional logo PNG is shown in headers.

GEBCO is not required. The observed `Depth` field is used for depth analyses.
Unclipped official MITECO geometry is authoritative for observation assignment. GSHHS is required and is the primary source for subtracting land in EPSG:3035 and deriving effective marine geometry and area. If GSHHS produces a coastal false zero but MITECO confirms valid official marine surface, the fallback geometry is the actual intersection between the cell and the official MITECO marine subdivision; `Area_mar_km2` is calculated from that same geometry and the cartographic display uses the identical clipped geometry. Only still-unresolved points proceed to `nearest`, exclusively among cells with positive GSHHS marine surface and within the configured tolerance. GSHHS is never embedded as a custom land/coastline layer in the static HTML publication.

## Windows quick start

1. Extract the ZIP to a writable path such as `C:\Hispa-Syng`.
2. Place the observation and trait workbooks in `Datos_data/` and the cartographic resources in `Resources/`, as listed above.
3. Double-click `install_and_run_windows.bat`.
4. Select the period, 1/5/10 km grid, MITECO subdivision and species.
5. When launched through the root `Hispa-Syng.bat`, open the files created inside the root-level `Resultados` directory.

During execution, the console shows stages 1/8–8/8, every analytical substep,
and elapsed `[HH:MM:SS]` time for each edition and the complete bilingual run.

The first run creates `.venv` and downloads the validated dependencies. Later
runs reuse it. If Windows blocks the BAT file, unblock the downloaded ZIP in
Properties before extracting it. Use `repair_windows_environment.bat` if the
environment becomes incomplete or blocked.

Supported runtime: 64-bit Python 3.10–3.13. For Hispa-Syng
v1.0, the distributed dependency configuration targets Python 3.13 on Windows
x64; the installer prefers Python 3.13 without forcing a rebuild of an already
working compatible environment. Run the bilingual regression suite from the
project root with `RUN_REGRESSION_TESTS.bat`.

The included automated validation records correspond to Linux/Python 3.12.14. The separately reviewed Windows run of 19 October 2026 records Python 3.13.15, pandas 2.3.3 and GeoPandas 1.2.0, with matching principal ES/EN QA values; see [Windows run evidence](../Validation/EJECUCION_WINDOWS_20261019.md) and [validation scope](../Validation/VALIDACION_EN.md).

## Output structure

Each run creates a new folder and never overwrites an earlier run:

| Folder | Contents |
|---|---|
| `00_logs` | complete execution log |
| `01_parameters` | resolved configuration and paths |
| `02_intermediate` | analysis grids and GeoPackages |
| `03_maps` | interactive maps 1–3 |
| `04_tables` | semicolon CSV and XLSX tables |
| `05_figures` | high-resolution PNG and PDF figures |
| `06_models` | model summaries, methods and narratives |
| `07_quality_control` | audits, checks and output manifests |
| `08_viewers` | unified cartographic viewer |
| `09_priority_conservation_areas` | priority tables, GIS, maps and the specific priority-area Word report |
| `10_technical_report` | automatic integrated technical report for the run, including synthesis, discussion, labelled maps and traceability |
| `Web_Publication` | integrated four-map viewer, twelve map-specific downloads, reusable data packages, manuals and integrity manifest |

`Web_Publication/index.html` is the entry point intended for institutional
hosting.

The integrated report is written to `10_technical_report/Hispa-Syng_v1.0_Integrated_Technical_Report_EN.docx`. When the English edition is launched by the bilingual root launcher, its complete path is `Resultados/run_<id>_EN/10_technical_report/...`. All file references inside the report are relative to the Hispa-Syng program root; no machine-specific absolute paths are written. When priority areas exist, Chapter 11 includes a labelled overview map and a geographic detail map. Conservation popups also report species composition: each cell lists the species present with cell-level abundance and density, and each zone provides the equivalent area-level summary, always in ind./km² of marine area. Visible and exported density values are limited to at most two decimal places; analytical calculations retain full precision.

In Maps 2 and 3, density colour scaling is deliberately separated from extreme numerical values. With at least 20 positive-density cells, the colour ceiling uses the empirical P95 and is rounded to a readable legend value; higher densities retain their exact numerical value and use the darkest colour. With fewer than 20 positive cells, the full observed maximum is used. Map 2 recalculates the robust P95 scale whenever the active species selection changes. Popups and exports always retain exact densities.
 The publication remains static for non-sensitive products. When the project is protected, Map 1 and controlled downloads are encrypted as `.hse` containers after the run finishes; no password is embedded in HTML and no plaintext password file is distributed. Access is authorized from `Hispa-Syng.bat > Security and access` using the project password, an `.hsk` credential, or Windows-DPAPI remembered access. Sensitive files are opened with `Open protected .hse file`.

In protected mode, products are generated in a private temporary area outside Resultados, restricted to the operating-system user. They are encrypted and verified before being placed in Resultados or the web publication. Computation may require plaintext temporary files inside that private area; this protection does not provide continuous encryption of all local storage. Before starting a protected analysis, the program automatically checks pending recovery and existing results. A run interrupted during computation is recovered as incomplete, with protected products; it is not presented as a completed scientific run. If verification or recovery fails, the program blocks the new analysis and retains the pending journal. Review and protect existing outputs also performs this review from the menu.

Only one interactive conservation map is produced. Its filename contains the
selected resolution, for example:

`Interactive_Priority_Conservation_Areas_Map_10km.html`

In this viewer, official MITECO geometries are used for assignment. The analytical marine geometry and display copy come from GSHHS clipping or, when GSHHS creates a MITECO-confirmed coastal false zero, from the MITECO cell–marine-subdivision fallback. Mixed coastal cells remain eligible even when `MARINO=0`; GSHHS is not published as a custom HTML geometry layer.
The optional `Priority areas` layer uses the same class
colours as the legend, and `Priority-area labels` can be enabled separately.
Protected areas are restricted to their marine intersection with the official
MITECO mask; their popups report designation name, protection type, available
protection level and source file.

## Resolution integrity

At `[2/8 · 5/7]`, the similarity network is adaptive and sparse: each cell
contributes at most 12 neighbours. Raw Louvain communities remain in audit
outputs, while analysis and figures use no more than eight merged clusters.
IndVal is calculated for individual clusters, not exponential combinations.

The grid selected at the start is propagated to the master hotspot grid,
temporal signal, conservation scoring, selected cells, contiguous areas,
GeoPackages, maps and reports. Automated tests verify areas of 1, 25 and
100 km² for selections of 1, 5 and 10 km respectively.

Total and species-level reported densities always use `Marine_area_km2`. The primary route is MITECO geometry clipped by GSHHS land in EPSG:3035. If that route produces a coastal false zero but MITECO confirms valid official marine surface, the actual MITECO cell–marine-subdivision intersection is used as the fallback geometry. `Area_mar_km2` is calculated from that geometry, the same geometry is displayed, and `Area_mar_source` records the provenance. Before the web publication is written, both density tables are recalculated and checked; a mismatch stops publication.

GSHHS clipping is stored persistently in `.cache/marine_areas`. Each entry keeps the `grid_id`, a MITECO-geometry fingerprint and the marine area calculated by GSHHS; it does not store GSHHS geometry. A value is reused only when the exact cell geometry matches and the GSHHS content signature is unchanged. Cells that require the MITECO fallback are identified at runtime from official marine information. Spanish and English editions share this cache. It may be deleted safely and will be rebuilt automatically on the next run.

## Excel compatibility

The source workbook is read-only. Headings such as `N hembra`, `N macho`,
`N_indeterminado` and `Captura incidental` remain unchanged in the workbook.
English output uses names such as `female_count`, `male_count`,
`indeterminate_count` and `bycatch`.

Habitat values are translated only in English presentation outputs: `Arena` is
`Sand`, `Pradera marina` is `Seagrass/Macroalgae`, `Rocas` is `Rock`, `No
determinado` is `Undetermined`, `Antrópico` is `Anthropogenic` and `Pelágico`
is `Pelagic`. The source workbook remains unchanged. Regional membership is fixed before analytical cell assignment. A direct point-to-subdivision intersection is used first; observations without one receive a canonical MITECO region from the official 10-km reference grid, independently of whether the analytical run uses 1, 5 or 10 km cells. The selected analytical grid is used only afterwards for cell assignment, marine area, density and spatial analyses. The regional-assignment audit records the method, reference cell and distance where applicable. Empty regional metrics are marked as not calculable rather than producing an unexplained empty statistic.

Duplicate registered outputs are removed after analysis, retaining the first
canonical file for each normalized content signature. The priority-area
complete popup is represented once by the multi-sheet
`Table_21_Priority_Conservation_Areas.xlsx` workbook. Runtime warnings are
captured in `runtime_warning_control.csv` with the affected stage and action.

In `Figure_Taxonomic_vs_Functional_Richness`, every MITECO region in the regional summary remains visible. Regions whose relative FRic is not estimable are shown with an `X` marker in the `N.E.` band rather than being removed or assigned a false zero. Points with identical taxonomic richness and FRic are moved very slightly along the X axis only for display; calculations and tables retain the unmodified values. Functional outputs are stored in `functional_diversity`, separately from `community_biogeography`.

The source `Id` is retained as metadata. It is not used as an analytical
variable, spatial key or deduplication criterion. Each valid row receives a
separate internal `obs_id`.

## Production settings

The recommended inferential setting is 999 permutations. Lower values such as
49 are intended only for installation checks. A run is declared successful
only after its analytical and spatial quality controls pass.

See `../Manual_Hispa_Syng_v1_0_EN.docx`,
`FULL_ANALYSIS_MANUAL.md` and `VALIDATION.md` for additional detail.

Spatial assignment follows an explicit hierarchy: direct intersection with a cell of validated marine surface; retention of the original MITECO cell through the official fallback when GSHHS produces a coastal false zero consistent with the marine subdivision; and only then `nearest` among cells with positive GSHHS marine surface within the configured tolerance. `nearest` and unassigned cases are documented in `07_quality_control` through `spatial_assignment_audit_nearest_and_unassigned.csv`, `spatial_assignment_audit_summary.csv` and `Spatial_Assignment_QC_Map.html`. The QC map shows direct assignments in green, `nearest` in orange and unassigned observations in red; it also displays implicated MITECO cells and nearby GSHHS land context, with Satellite active by default and Physical as the alternative basemap. Valid observations that cannot be assigned safely to a grid cell remain in Map 1 and complete observation downloads but are excluded from cell-based metrics. The audit does not change the tolerance or force assignments.

## Shared observation-event proxy

Each valid projected observation receives a deterministic `sampling_event_id` built from date + normalized observer + EPSG:3035 position rounded to 1 m. Species, abundance, `Id` and grid resolution are not part of the key. The temporal block uses `n_sampling_events` as its primary observation-intensity proxy and retains `n_records` as a descriptive/sensitivity field. The primary temporal model is a Poisson count GLM with `log(n_sampling_events)` offset and Pearson overdispersion correction constrained to `phi >= 1`; inference requires at least 8 detection years, 20 detection events and a 10-year detection span. The canonical temporal signal is calculated directly on official MITECO `grid_id` and uses unit-invariant symmetric relative changes. Community, multiscale and conservation support use the shared proxy-event infrastructure; `n_records` remains descriptive data volume rather than measured sampling effort.

## Protected results and credential scope

In protected mode, products are generated in a private temporary area outside Resultados, restricted to the operating-system user. They are encrypted and verified before being placed in Resultados or the web publication. Computation may require plaintext temporary files inside that private area; this protection does not provide continuous encryption of all local storage.

Before starting a protected analysis, the program automatically checks pending recovery and existing results. A run interrupted during computation is recovered as incomplete, with protected products; it is not presented as a completed scientific run. If verification or recovery fails, the program blocks the new analysis and retains the pending journal. Review and protect existing outputs also performs this review from the menu.

Map 1 and the QC map, tables, documents, packages, logs and every product lacking explicit public classification are encrypted. Registered aggregate maps 2 and 3, viewers, aggregate conservation maps and institutional assets are verified and remain available. Names and extensions do not grant public access. Individual-observation fields and points are rejected. The official protection layer permits catalog points. Cells and zones display only polygon components, without changing analytical geometry. Unregistered figures and auxiliary files are encrypted by default. Sensitive HTML displays an informational page and retains the original in .html.hse. The audit records every file, its classification, reason and SHA-256. Hashes support integrity comparison, not owner authentication.

The project permits one active analysis or maintenance operation. Before creating an open or protected copy, it requires owner authority and recovers pending runs. Recovery failure blocks the copy and its credential while retaining the private area and journal. Incomplete results remain labelled and are excluded from software copies.

Key rotation prepares and verifies new containers and the recovery credential before replacing active files. It keeps a durable journal and recovery backups until the change is committed. After interruption, the next access restores the previous state if the operation was not committed, or finishes cleanup after a completed commit. Rotation cannot start while private runs await recovery.

Rotation prevents old credentials from opening re-encrypted files in the updated project. It cannot withdraw access to retained old copies with their old keys or information already exported. Changing the password or reissuing a recovery credential with the same key and token does not invalidate existing credentials. Forget access removes the local DPAPI record; it does not revoke other retained copies of that record.

DPAPI uses the current Windows-user scope without enabling machine-wide scope. The secret owner token is protected with the password and included only in the recovery credential and, when administrative authority is remembered, the DPAPI material. Configuration stores its verification hash. An access credential does not include that token; an environment role does not grant administration. This separation assumes that an attacker controlling the computer has not replaced the code or local configuration. A user authorized to decrypt can retain or export the data.

## Grid reading and preparation timings

A full analysis uses the official 1, 5 and 10 km grids regardless of the selected resolution and temporal comparisons. Spatial windows near observations are combined into one query per source file, without simplifying their boundaries or changing the selected cells. Original source-cell order is retained. A compatible per-window read is used when the driver has no GEOS support or an edge window is degenerate.

The console reports the source file, query windows, loaded cells and read/preparation timings. The multiscale block separately reports marine-area time and total time per scale. The GSHHS area cache remains reusable; do not delete it. This cache avoids repeated area clipping but does not eliminate source geometry reads. Spatial querying adds no observation-location files or cache of selected geometries.

## Using protection simply

For ordinary analysis, choose **Run Hispa-Syng** in the main menu. The current folder keeps its open or protected state between runs.

Within **Security and access**, **Protect my current project** encrypts data in this same folder. **Prepare a copy to share** opens a separate section: a protected copy creates another folder with its own password and key; an open copy creates another folder with readable data and no password. Neither copy includes previous results.

In a protected project, **Open protected .hse file** allows you to view results. **Manage password and access** groups password changes, owner recovery, key rotation, output review and management of remembered access and temporary files. To issue an ordinary credential, use **Prepare a copy to share > Create an access file for this project (.hsk)**. For an independent copy, issue the credential from that copy.

Changing the password does not invalidate existing credentials. **Withdraw previous access to the current project (rotate key)** requires new credentials for re-encrypted files; old copies with their old keys remain readable.

**SECURITY_PASSWORDS_AND_ACCESS_HISPA_SYNG_EN.docx** explains folders and the seven practical cases.
