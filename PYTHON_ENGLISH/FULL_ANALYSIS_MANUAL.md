# Full analysis manual — Hispa-Syng v1.0

**Licence for this guide:** [Creative Commons Attribution–NonCommercial 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).

## Workflow

1. Read and audit the original Excel workbook.
2. Filter species and observation dates.
3. Transform valid observations to EPSG:3035.
4. fix canonical MITECO regional membership first (direct subdivision intersection, otherwise the official 10-km reference grid) and then assign observations to the selected 1/5/10-km analytical grid;
5. calculate cell metrics and maps 1–3;
6. run analytical blocks 8–21;
7. generate **documentary Block 22**, which builds the integrated technical report exclusively from outputs of the current run;
8. apply final analytical, spatial, and documentary quality controls.

English presentation is applied at export time. Habitat values are mapped to
`Sand`, `Seagrass/Macroalgae`, `Rock`, `Undetermined`, `Anthropogenic` and
`Pelagic`; the ingestion workbook is never rewritten. The regional-assignment audit distinguishes direct subdivision intersections, canonical 10-km reference-grid assignments and unresolved cases, and records the reference cell and distance when applicable. Regional membership is therefore independent of the analytical resolution. Records that belong to the selected canonical regional scope but cannot be assigned safely to a cell at the chosen resolution are retained in `points_outside_grid.csv`, Map 1 and complete observation downloads, but are excluded from cell-based density and spatial analyses.

When present, `MARINO` is retained as audit metadata and is not used by itself to discard mixed coastal cells. For every cell, effective marine surface is obtained primarily in EPSG:3035 as MITECO geometry minus GSHHS land. If GSHHS produces a coastal false zero but MITECO confirms valid official marine surface, the fallback is the actual intersection between the cell and the official MITECO marine subdivision; `Area_mar_km2` is calculated from that same geometry and the cartographic copy is identical. Assignment first uses direct intersection; fallback cells additionally require agreement between the point marine region and the official cell region. Only points still unresolved proceed to `nearest`, among cells with positive GSHHS marine surface and within the configured tolerance. Densities are calculated as `N / Area_mar_km2` and expressed in ind./km², with no ×1,000 scaling. Visible and exported values are presented with at most two decimal places; analytical calculations retain full precision.

Density colour rendering does not alter that formula. To prevent a coastal cell with a very small marine fraction from compressing the entire colour range, Maps 2 and 3 use a robust visual ceiling based on P95 whenever at least 20 cells have positive density. The ceiling is rounded to a readable legend value; higher values saturate only in colour and keep their exact density in popups and exports. With fewer than 20 positive cells, the full maximum is used.

`nearest` and unassigned cases are documented in `spatial_assignment_audit_nearest_and_unassigned.csv`, summarised in `spatial_assignment_audit_summary.csv`, and displayed in `Spatial_Assignment_QC_Map.html`. The QC map shows direct assignments in green, proximity assignments in orange and unassigned observations in red, and adds implicated MITECO cells plus nearby GSHHS land context. It uses Satellite — Esri World Imagery as the default basemap and Physical — OpenTopoMap as the alternative, without requesting tiles from the standard OpenStreetMap tile server. Valid observations without a safe grid assignment remain in Map 1 and complete observation downloads but do not enter cell-based analyses. This is diagnostic only: it does not change the tolerance or force additional assignments.

The launcher reports stages 1/8–8/8, every analytical substep and elapsed
`[HH:MM:SS]` time, as well as per-edition and total bilingual elapsed time.

## Analytical blocks

- **8–9:** observation-intensity proxies, richness, abundance, recorded-detection frequency/relative detection breadth, coastal detection, dominance, habitat, depth classes and statistical contrasts.
- **10–11:** abundance and presence matrices, Bray–Curtis/Jaccard beta
  diversity, PERMANOVA, betadisper, NMDS/PCoA, LCBD and environmental context.
- **12:** direct analyses on the official MITECO 10/5/1 km grids, event-supported Jaccard LCBD, BH-FDR, symmetric 1→5→10 km persistence, Mantel distance-decay, Moran Monte Carlo and descriptive fixed-radius hotspot clusters.
- **Functional:** Gower distance and PCoA-based FRic, FEve, FDiv, FDis and RaoQ.
- **Sex:** global and regional summaries, exact binomial tests, chi-squared
  tests, standardised residuals and a quasi-binomial regional model.
- **13–19:** IndVal with BH-FDR, SIMPER, observed-range-weighted rarity, relative recorded-detection classes, networks, community
  clusters, biogeographical composition and threshold sensitivity. The
  adaptive network retains at most 12 neighbours per cell; raw Louvain
  communities remain auditable and are merged into at most eight analytical
  clusters. IndVal is limited to individual clusters.
- **20:** annual effort-corrected series, Poisson models, flexible splines,
  period comparisons, cell changes, change maps, rankings and narratives.
- **21:** separate ecological priority, temporal-monitoring priority and data adequacy; when 1 km is requested, the viewer presents 1-km descriptive priority separately from 5-km strategic planning units. Strategic priority areas retain the High/Very-high core, eligible Medium-extension, and rook-contiguity methodology. Afterwards, without recalculating priority, operational conservation areas are delineated from observed official MITECO 1-km cells inside each strategic area: only edge-sharing evidence cells are merged and empty bridge cells are never added. One strategic area can therefore split into several operational subareas. These footprints are intended to focus action and do not represent complete population or habitat boundaries. The block retains the three ecological pathways (convergence, persistent occurrence, and diversity core), ecological-weight sensitivity, isolated Medium validation candidates, protected-area gaps, management action, and validation need.
- **22 (documentary; no analytical recalculation):** creates `10_technical_report/Hispa-Syng_v1.0_Integrated_Technical_Report_EN.docx`. It integrates outputs from the preceding blocks, develops scientific interpretation, includes temporal/regional/sex-composition tables, adds two labelled priority-area maps when areas are available, and ends with file locations expressed relative to the Hispa-Syng program root.

When a regional group has no complete observations for a metric, its output is
retained with `calculation_status = not_calculable` and an explanation. Runtime
warnings are captured and reported in the quality-control outputs; they are not
silenced. The static publication exposes a Word report, Excel workbook and
reusable data ZIP for each of the four maps. Each data ZIP contains CSV data,
the corresponding Excel and Word products, GeoPackage layers where available,
parameters, methodology, a data dictionary and a manifest of checksums.

In `Figure_Taxonomic_vs_Functional_Richness`, every MITECO region included in the regional summary remains visible: taxonomic richness is shown on the X axis and relative FRic on the Y axis. If FRic cannot be estimated because too few functionally characterised species are available for the common dimensionality, the region is not dropped; it is shown with an `X` marker in the `N.E.` (not estimable) band outside the numerical FRic scale. When
two or more regions have exactly the same values on both axes, their symbols
are moved by at most 0.025 units to either side **only in the displayed X
position** so that all are visible. Actual taxonomic richness remains an
integer; neither FRic nor the exported tables change. The figure explicitly
explains this displacement. For exact figures, consult
`Table_Taxonomic_vs_Functional_Richness_by_Region` and the functional
diversity table, rather than reading the shifted marker positions. Functional outputs are stored separately under `04_tables\functional_diversity`, `05_figures\functional_diversity`, and `06_models\functional_diversity`; they are not mixed with `community_biogeography`.

When the project is protected, Map 1, the assignment-QC map, observation-level intermediate products, and controlled downloads are encrypted after the run as `.hse` containers. The password is a persistent property of the project rather than of each run. Access is managed from `Hispa-Syng.bat > Security and access` and can be authorized with the owner password, an `.hsk` credential, or a Windows-DPAPI remembered key. Encryption does not change analytical values, popups, or results. Open projects are not encrypted.

## Interpretation

Outputs describe the available database and are sensitive to observation
effort, spatial coverage and temporal coverage. Statistical significance does
not by itself establish causality, population trend or conservation status.
Ecological-priority classes are relative screening categories within the current run and do not force a fixed percentage of cells into High/Very high classes. Temporal monitoring and data adequacy are reported independently. Priority products support technical assessment and require field validation, expert review and the applicable regulatory process.


### Project security
In protected mode, products are generated in a private temporary area outside Resultados, restricted to the operating-system user. They are encrypted and verified before being placed in Resultados or the web publication. Computation may require plaintext temporary files inside that private area; this protection does not provide continuous encryption of all local storage. Before starting a protected analysis, the program automatically checks pending recovery and existing results. A run interrupted during computation is recovered as incomplete, with protected products; it is not presented as a completed scientific run. If verification or recovery fails, the program blocks the new analysis and retains the pending journal. Review and protect existing outputs also performs this review from the menu.

## Protected results and credential scope

In protected mode, products are generated in a private temporary area outside Resultados, restricted to the operating-system user. They are encrypted and verified before being placed in Resultados or the web publication. Computation may require plaintext temporary files inside that private area; this protection does not provide continuous encryption of all local storage.

Before starting a protected analysis, the program automatically checks pending recovery and existing results. A run interrupted during computation is recovered as incomplete, with protected products; it is not presented as a completed scientific run. If verification or recovery fails, the program blocks the new analysis and retains the pending journal. Review and protect existing outputs also performs this review from the menu.

Map 1 and the QC map, tables, documents, packages, logs and every product lacking explicit public classification are encrypted. Registered aggregate maps 2 and 3, viewers, aggregate conservation maps and institutional assets are verified and remain available. Names and extensions do not grant public access. Individual-observation fields and points are rejected. The official protection layer permits catalog points. Cells and zones display only polygon components, without changing analytical geometry. Unregistered figures and auxiliary files are encrypted by default. Sensitive HTML displays an informational page and retains the original in .html.hse. The audit records every file, its classification, reason and SHA-256. Hashes support integrity comparison, not owner authentication.

The project permits one active analysis or maintenance operation. Before creating an open or protected copy, it requires owner authority and recovers pending runs. Recovery failure blocks the copy and its credential while retaining the private area and journal. Incomplete results remain labelled and are excluded from software copies.

Key rotation prepares and verifies new containers and the recovery credential before replacing active files. It keeps a durable journal and recovery backups until the change is committed. After interruption, the next access restores the previous state if the operation was not committed, or finishes cleanup after a completed commit. Rotation cannot start while private runs await recovery.

Rotation prevents old credentials from opening re-encrypted files in the updated project. It cannot withdraw access to retained old copies with their old keys or information already exported. Changing the password or reissuing a recovery credential with the same key and token does not invalidate existing credentials. Forget access removes the local DPAPI record; it does not revoke other retained copies of that record.

DPAPI uses the current Windows-user scope without enabling machine-wide scope. The secret owner token is protected with the password and included only in the recovery credential and, when administrative authority is remembered, the DPAPI material. Configuration stores its verification hash. An access credential does not include that token; an environment role does not grant administration. This separation assumes that an attacker controlling the computer has not replaced the code or local configuration. A user authorized to decrypt can retain or export the data.
