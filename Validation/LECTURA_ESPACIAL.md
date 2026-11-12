# Hispa-Syng v1.0 — Lectura espacial / Spatial reading

Fecha / Date (UTC): 2026-10-14T08:19:08.533233+00:00

La lectura espacial conserva las ventanas originales y consulta cada archivo una sola vez cuando GEOS está disponible. No se altera la resolución analítica, la geometría oficial, el recorte GSHHS ni los cálculos científicos. / Spatial reading retains the original windows and queries each file once when GEOS is available. Analytical resolution, official geometry, GSHHS clipping and scientific calculations are unchanged.

## Evidencia / Evidence

Se han comparado los 15 archivos oficiales MITECO (cinco demarcaciones × tres resoluciones) con hasta 40 ubicaciones sintéticas deterministas por archivo. Coinciden exactamente atributos, orden y bytes WKB de geometría. / All 15 official MITECO files (five regions × three scales) were compared using up to 40 deterministic synthetic locations per file. Attributes, order and geometry WKB match exactly.

| Escala / Scale | Lecturas por ventanas / Window reads (s) | Consulta única / Single query (s) |
|---|---:|---:|
| 1 km | 8.785 | 5.030 |
| 5 km | 1.329 | 0.403 |
| 10 km | 0.892 | 0.162 |

Tiempos de lectura sumados sobre cinco archivos por escala, en Linux y con ubicaciones de prueba; no representan la configuración del usuario ni el tiempo de un análisis completo. La lectura de referencia precedió a la consulta única en los archivos oficiales y el estado de las cachés del sistema puede influir. La prueba sintética adicional alternó ambos métodos. No se garantiza un factor de aceleración en Windows. / Read times summed over five files per scale on Linux with test locations; not the user configuration or full-analysis time. Reference reads preceded single queries on official files and OS cache state can affect timings. The additional synthetic benchmark alternated methods. No Windows speedup factor is guaranteed.

Las pruebas sintéticas de ambas ediciones verifican mallas preparadas, áreas marinas y asignaciones idénticas, reutilización de caché, bordes, solapamientos, huecos, multipolígonos, CRS distinto, ausencia de observaciones, extensión desconocida y compatibilidad sin GEOS. / Both editions verify identical prepared grids, marine areas and assignments, cache reuse, boundaries, overlaps, holes, multipart geometry, differing CRS, no observations, unknown extent and compatibility without GEOS.

Prueba reproducible / Reproducible test: `python tests/_grid_reading.py PYTHON_ESP` y / and `python tests/_grid_reading.py PYTHON_ENGLISH`. Incluida en / Included in `RUN_REGRESSION_TESTS.bat`.

Este documento conserva el ensayo espacial fechado arriba. No se ha repetido el ensayo con cartografía oficial durante la validación SIN_RESOURCES. La suite sintética completa de esta entrega consta en validation.json y VALIDACION_ES.md. / This document retains the spatial benchmark dated above. The official-cartography benchmark was not repeated during SIN_RESOURCES validation. The complete synthetic suite for this package is recorded in validation.json and VALIDACION_EN.md.
