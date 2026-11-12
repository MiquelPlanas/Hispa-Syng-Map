# Ejecución bilingüe en Windows del 19 de octubre de 2026

## Español

Los tres archivos aportados identifican la ejecución `20261019_094827_65e45b50`. El manifiesto registra ambas ediciones completadas y los dos resúmenes registran el control general y el análisis completo como superados. La revisión contrasta estos registros existentes; no vuelve a ejecutar el programa. La evidencia de Windows combina la confirmación del usuario con las rutas de los archivos; los JSON no identifican la versión exacta de Windows.

Se seleccionaron 1992–2026, todas las demarcaciones, 12 especies, malla de 1 km, análisis completo y 999 permutaciones. Los periodos comparados fueron 2006–2014, 2015–2021 y 2022–2026. Ambos resúmenes registran Python 3.13.15, pandas 2.3.3 y GeoPandas 1.2.0. El proyecto estaba abierto, sin protección activada.

| Comprobación | Español | Inglés | Comparación |
| --- | ---: | ---: | --- |
| Registros leídos | 2492 | 2492 | Iguales |
| Registros asignados a celdas | 2461 | 2461 | Iguales |
| Registros sin asignación segura | 31 | 31 | Iguales |
| Asignación directa, incluido respaldo MITECO | 2428 | 2428 | Iguales |
| Asignación por proximidad | 33 | 33 | Iguales |
| Eventos proxy tras la selección regional | 1867 | 1867 | Iguales |
| Celdas ocupadas de 1 km | 576 | 576 | Iguales |
| Individuos registrados asignados | 2828 | 2828 | Iguales |
| Individuos agregados en las celdas | 2828 | 2828 | Iguales |
| Fechas inválidas | 0 | 0 | Iguales |
| Coordenadas inválidas | 0 | 0 | Iguales |
| Discordancias entre N_total y suma por sexos | 0 | 0 | Iguales |
| HTML con controles de tokens superados | 5 | 5 | Cada idioma supera sus controles |

Coinciden exactamente los recuentos de entrada y las secciones de filtros, asignación, métricas, versiones, recorte de tierra y contexto cartográfico. La auditoría de columnas coincide tras separar los nombres de campo traducidos. En superficie marina coincide el contenido tras reconocer `superado` y `passed` como estados equivalentes. En el inventario de mallas coinciden los campos restantes al separar las denominaciones regionales traducidas. Coinciden también los 17 productos duplicados retirados según los resúmenes. Esto compara los resúmenes de control; no sustituye una comparación de todas las tablas o valores individuales.

Los 31 registros sin asignación segura no entran en las métricas por celda. La asignación directa incluye 29 casos con respaldo MITECO; no deben sumarse otra vez. La identidad de abundancia asignada y agregada se cumple. Ambos resúmenes declaran verificada la densidad con superficie marina y excluyendo tierra; la diferencia máxima registrada entre el área de densidad y la geometría representada es 2,6368 × 10⁻¹⁴ km². Esta revisión no recalcula esas geometrías.

La creación del manifiesto a las 09:48:27 y su cierre a las 10:03:38, con zona +02:00, delimitan 911.359 segundos, aproximadamente 15 min 11 s. Las ediciones registran 475,635 s y 431,775 s. El total del coordinador, 4439,192 s, usa un cronómetro iniciado antes de seleccionar los parámetros. Se conservan como medidas distintas; no se presenta el total como tiempo exclusivo del análisis.

Hay un punto de trazabilidad pendiente: el manifiesto sitúa la edición inglesa en `Resultados/run_20261019_094827_65e45b50_EN`, mientras el resumen inglés cambia ese componente a `Results`. En el código aportado se reproduce esa sustitución mediante la traducción de cadenas de presentación. No se ha modificado el registro original ni se han reinterpretado sus rutas como verificadas. Los recuentos comparados coinciden, pero las rutas de auditoría deben preservarse antes del cierre definitivo. No se modifica código en esta actualización.

La ejecución documenta el funcionamiento completo declarado para esta configuración con datos operativos, separadamente de las pruebas automatizadas históricas en Linux. No identifica el commit o ZIP exacto del código ejecutado. Tampoco acredita DPAPI, ACL, aislamiento entre usuarios, protección de resultados o recuperación de rotaciones, porque se ejecutó en modo abierto. La consulta sobre licencia sigue siendo independiente.

Los nombres y hashes de los tres originales y las comparaciones están en [EJECUCION_WINDOWS_20261019.json](EJECUCION_WINDOWS_20261019.json). Ese registro derivado omite las rutas personales de Windows y el listado de resultados anteriores que figuraba en el manifiesto. Los originales aportados se conservan sin modificar fuera del repositorio.

## English

The three supplied files identify run `20261019_094827_65e45b50`. The manifest records both editions as completed, and both summaries record general and complete-analysis quality control as passed. This review compares existing records without rerunning the program. Windows evidence combines the user’s confirmation with the file paths; the JSON files do not identify the exact Windows version.

The selection was 1992–2026, all marine subdivisions, 12 species, a 1 km grid, complete analysis and 999 permutations. Comparison periods were 2006–2014, 2015–2021 and 2022–2026. Both summaries record Python 3.13.15, pandas 2.3.3 and GeoPandas 1.2.0. The project was open, with protection disabled.

Both editions record 2492 input rows, 2461 assigned records, 31 unassigned records, 2428 direct assignments including MITECO fallback, 33 nearest assignments, 1867 proxy events after regional selection, 576 occupied cells and 2828 recorded individuals in both assigned and aggregated totals. Invalid dates, invalid coordinates and sex-total mismatches are zero. All five HTML files in each edition pass their recorded token checks.

Input counts, filters, assignment, metrics, versions, land clipping and cartographic-context sections match exactly. Input-column audits match after separating localized field names. Marine-area content matches after recognizing the translated passed status; grid-inventory fields match after separating localized region names. Both summaries record 17 duplicate products removed. These checks compare QA summaries, not every exported table or individual value. The 29 MITECO-fallback direct assignments are already included in the 2428 direct assignments. The 31 unassigned records are excluded from cell metrics. Both summaries declare the marine-area density formula verified, with land excluded and a maximum density/display-area difference of 2.6368 × 10⁻¹⁴ km²; those geometries were not recalculated here.

Manifest creation to completion spans 911.359 seconds, approximately 15 min 11 s. Edition durations are 475.635 s and 431.775 s. The coordinator total, 4439.192 s, starts before parameter selection. These distinct elapsed-time measures are retained without describing the coordinator total as analysis-only time.

An open traceability item remains: the manifest places the English run under `Resultados/run_20261019_094827_65e45b50_EN`, whereas the English summary changes the root component to `Results`. Presentation-string translation reproduces this substitution in the supplied source. Original records are unchanged and their paths have not been treated as verified filesystem locations. Compared counts match, but audit paths need preservation before the final release. No source-code change is included here.

This evidence documents the recorded complete workflow for this operational-data configuration separately from historical automated Linux tests. It does not identify the executable source commit or ZIP. Open-mode execution does not verify DPAPI, ACL enforcement, cross-user isolation, output encryption or rotation recovery. Original file hashes and comparisons are recorded in [EJECUCION_WINDOWS_20261019.json](EJECUCION_WINDOWS_20261019.json); the derived record excludes personal Windows directory paths and the inventory of earlier results. Supplied originals remain unchanged outside the repository.
