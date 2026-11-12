# Validation — Hispa-Syng v1.0 — English edition

This document describes the English edition’s validation criteria and check families. The status and package identity supported by available records are described in [the validation scope report](../Validation/VALIDACION_EN.md). This description does not certify that every check was repeated on the current ZIP.

Validation covers syntax, unit tests, input aliasing, numerical invariance,
HTML integrity, PNG/PDF integrity, XLSX opening, DOCX opening and GeoPackage
layers. The selected resolution is checked at 1, 5 and 10 km, corresponding to
cell areas of 1, 25 and 100 km².

The English presentation layer must not change analytical inputs or formulae.
Numerical tables are compared against the Spanish edition after matching
translated columns and categories. A run is accepted only when the final
quality-control status is `PASS`.

The recorded reference validation reports passing automated checks within its stated scope. The rendered JavaScript for maps 1,
2, 3 and the conservation map also passes `node --check`; an English-language
scanner is applied to the rendered map controls and popups. A regression test
covers output registration in folder structures containing spaces, and a
dedicated assertion protects the map-3 cell-visibility syntax.

The publication regressions verify the four integrated tabs, protected
Word, Excel and reusable-data-ZIP links on every map, relative static-server
paths, package manifests, habitat localization scoped to generated habitat
fields, source-workbook immutability, canonical MITECO regional assignment independent of 1/5/10-km analytical resolution, duplicate
removal and independent total/species marine-area density checks. They also
verify that custom land, coastline and MITECO-subdivision geometries are absent
from the static HTML, that `MARINO` retention and the out-of-grid audit are
recorded. Spatial regressions cover canonical regional assignment from the official 10-km MITECO reference grid for points without a direct subdivision intersection, invariance of regional scope across 1/5/10-km analytical resolutions, fully marine cells, mixed coastal `MARINO=0` cells, GSHHS clipping, analytical/display geometry equality, official assignment-geometry retention and the MITECO fallback for coastal GSHHS false zeros. They verify that a fallback cell may retain its observation directly when the official marine subdivision is coherent, that `nearest` is attempted only afterwards and only against cells with positive GSHHS marine surface within the configured tolerance, and that observations without a safe assignment remain documented and preserved in Map 1 without entering cell-based metrics. DOCX and XLSX products are opened structurally;
affected figures are rendered for visual review. Regional completeness and
runtime-warning control tables document which results are calculable.

The integrated technical report is also validated as a final run product: ES/EN structural equivalence is checked; temporal, regional and sex-composition tables must be populated when calculable; the two labelled priority-area views must be embedded when areas exist; machine-specific absolute paths are prohibited; and all reported locations must resolve from `Resultados/<run>/...` under the Hispa-Syng program root. DOCX files are rendered for visual review of tables, figures, captions and page breaks.

Density-output regressions additionally verify ind./km² units and a maximum of two decimal places in user-facing/exported values while retaining full internal precision.

Earlier 3.1.2 regressions verify per-species density recalculation in map 2,
priority-area class styling and optional labels, coastline clipping without
mutating source geometries, marine-only protected-area geometry, and retention
of designation name, protection type and protection level in protected-area
popups.

No scientific program can guarantee successful execution with a corrupt file,
an unknown schema or an operating-system security block. This edition fails
explicitly and records diagnostics rather than silently accepting invalid data.

## Operational conservation-area regression

Validation checks that operational delineation does not alter scores, classes, selected cells, or strategic priority areas. A synthetic geometry with two groups of observed official MITECO 1-km cells separated by empty cells must produce two independent operational areas, with no empty bridges and always contained within their strategic parent area. Existing cell, strategic-area, and protected-area popup fields are also checked for preservation.
## Robust density-colour-scale regression

Map 2 and Map 3 regressions verify that density remains numerically unclipped in calculations and exports while the colour scale uses the empirical 95th percentile whenever at least 20 cells have positive density. Values above the visual ceiling must retain their exact density and saturate only in colour. With fewer than 20 positive cells the full observed maximum is required, and Map 2 must recalculate the scale after every active-species change.

