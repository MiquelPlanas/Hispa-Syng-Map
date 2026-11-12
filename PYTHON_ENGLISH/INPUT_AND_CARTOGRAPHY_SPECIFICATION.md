# Input and cartography audit — Hispa-Syng v1.0

**Licence for this guide:** [Creative Commons Attribution–NonCommercial 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).

The program reads the worksheet `BD depurada` from the original workbook and
checks required fields, dates, coordinates, abundance, depth and sex counts.
It does not modify, deduplicate or resave the workbook. Repeated source `Id`
values are allowed because `Id` is metadata rather than an analytical key.

Required spatial inputs are the MITECO marine grids, MITECO marine subdivisions and GSHHS. Regional membership is fixed first by direct subdivision intersection and, when absent, from the official 10-km MITECO reference grid; this regional reference is independent of the analytical resolution selected by the user. The selected 1/5/10-km grid is used afterwards for analytical cell assignment. MITECO supplies the unclipped official geometry for observation assignment. GSHHS is the primary route for subtracting land in EPSG:3035 and deriving effective marine geometry and area. If GSHHS returns a coastal false zero but MITECO confirms valid official marine surface, the original cell is retained through the actual intersection between the cell and the official MITECO marine subdivision; the analytical area is calculated from that geometry and therefore matches the displayed geometry. Only still-unresolved points proceed to `nearest`, among cells with positive GSHHS marine surface and within the configured tolerance. Densities are expressed in ind./km², with no ×1,000 scaling, and visible/exported values use at most two decimal places. `MARINO` is audited and does not automatically filter mixed coastal cells. GSHHS is not embedded as a layer in the static HTML publication.

The optional `Resources/areas_protegidas` folder is used for overlap, distance and
conservation-gap assessment. `Datos_data/traits.xlsx` activates functional
diversity. GEBCO is not required and does not replace observed depth or GSHHS.

Quality-control outputs document invalid coordinates, unassigned observations,
field completeness, canonical regional assignment (`regional_assignment_audit.csv`), spatial assignment, grid inventory, marine-flag retention,
analytical/display geometry equality, effective-area provenance and map context. Observations that cannot be assigned safely to a grid cell are written to `points_outside_grid.csv`, retained as valid observations in Map 1 and complete observation downloads, and are not silently treated as marine cells or included in cell-based metrics. Spatial review is also supported by `spatial_assignment_audit_nearest_and_unassigned.csv`, `spatial_assignment_audit_summary.csv`, and `Spatial_Assignment_QC_Map.html`; the latter uses Satellite as the default basemap and Physical as the alternative.
