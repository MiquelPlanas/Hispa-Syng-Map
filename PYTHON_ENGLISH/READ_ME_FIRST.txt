HISPA-SYNG v1.0 — ENGLISH EDITION

1. Keep the original Excel workbook unchanged.
2. Keep the observation workbook and `traits.xlsx` inside `Datos_data/`.
3. Place MITECO grids, MITECO subdivisions, GSHHS and, when available,
   `areas_protegidas` inside `Resources/`.
4. GSHHS is required and is the primary route for land clipping in EPSG:3035. If it produces a MITECO-confirmed coastal false zero, the fallback geometry is the actual intersection between the cell and the official MITECO marine subdivision, and `Area_mar_km2` is calculated from that same geometry. Densities are expressed in ind./km², with no ×1,000 scaling, and are shown/exported with at most two decimal places.
5. Double-click `Hispa-Syng.bat` from the project root.
6. Type 1 or 2 for the language and press Enter; then select the period, grid
   resolution, region, species and comparison periods (0 or 2 or more).
   Regional membership is fixed independently of analytical resolution: first by
   direct MITECO-subdivision intersection and, when absent, by the official 10-km
   reference grid; the selected 1/5/10-km grid is used afterwards for analysis.
7. When using the root bilingual launcher, results are written under the root-level `Resultados` directory; the English integrated report is in `Resultados/run_<id>_EN/10_technical_report/`.
8. After a complete successful bilingual run, publish
   `Resultados/Publicacion_Web_Bilingue_<id>/` intact and share its index.html address.
9. The console reports every stage and substep with elapsed `[HH:MM:SS]` time.

The program recognises the original Spanish Excel headings internally but all
user-facing outputs are written in English.

Licence for this guide: Creative Commons Attribution–NonCommercial 4.0 International (CC BY-NC 4.0). https://creativecommons.org/licenses/by-nc/4.0/
