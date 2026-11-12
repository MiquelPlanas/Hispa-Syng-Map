# Revisión de capas de áreas protegidas / Protected-area layer review

Archivo inspeccionado / Inspected archive: `areas_protegidas(2).zip`.
SHA-256: `0dfecfad91c2e618939ea378eeccf694a6ea523e9e25faece9e83d3e2cec5d7c`.

## Inventario / Inventory

| Capa / Layer | Registros / Records | CRS | Sin geometría / Null geometry | Geometrías no válidas / Invalid geometry |
| --- | ---: | --- | ---: | ---: |
| `ENP/Enp2024.shp` | 1934 | EPSG:4258 | 0 | 18 |
| `Natura2000/Es_Lic_SCI_Zepa_SPA_Mac_202412.shp` | 226 | EPSG:32628 | 0 | 1 |
| `Natura2000/Es_Lic_SCI_Zepa_SPA_Medalpatl_202412.shp` | 1636 | EPSG:25830 | 0 | 11 |
| `RAMPE/Rampe_2025.shp` | 86 | EPSG:4258 | 0 | 3 |

## Comprobaciones y alcance

El ZIP supera la comprobación CRC. Los archivos utilizados en el análisis coinciden byte a byte con sus entradas en el ZIP original. Las cuatro capas pueden leerse y tienen sistema de referencia identificado. No se han modificado los archivos cartográficos.

Se ejecutaron el cargador real de áreas protegidas y la limpieza geométrica existentes en las ediciones española e inglesa de Hispa-Syng v1.0, con destino EPSG:3035 y una extensión de búsqueda que abarca España. Las cuatro capas se cargaron en ambas ediciones. El resultado de limpieza no contiene geometrías nulas, vacías o inválidas. El detalle de esta ejecución figura en `CAPAS_PROTEGIDAS_VALIDACION.json`.

Los polígonos inválidos detectados son incidencias geométricas en los datos de entrada. La reparación existente con `make_valid` actúa sobre la copia de trabajo; no sustituye ni reescribe los originales. Esta comprobación no demuestra igualdad de áreas antes y después de reparar ni valida todos los cálculos científicos.

Los XML y el diccionario ENP se conservan. Algunos títulos y fechas de los XML están heredados o no completados; la nota de procedencia distingue esos campos de los nombres de archivo y de la ficha oficial actual. La carpeta OSPAR está vacía y no se considera una capa suministrada.

No se ejecutó la cadena científica completa ni una intersección con la máscara marina real en esta revisión. Tampoco se cotejaron estos archivos con una descarga nueva de MITECO. Los totales del inventario incluyen registros terrestres y no constituyen un recuento de áreas protegidas marinas.

## Checks and scope

ZIP CRC validation passed. Analysed source files match their original archive entries byte for byte. All four layers are readable and have identified coordinate reference systems. Cartographic files were not modified.

The existing protected-area loader and geometry cleanup were executed in both Hispa-Syng v1.0 language editions, targeting EPSG:3035 with a search extent covering Spain. All four layers loaded in both editions. Cleanup produced no null, empty or invalid geometries. Execution details are retained in `CAPAS_PROTEGIDAS_VALIDACION.json`.

Invalid input polygons are geometry issues in the source data. Existing `make_valid` processing acts on the working copy; it does not replace or rewrite originals. This check does not establish area equality before and after repair or validate all scientific calculations.

XML files and the ENP dictionary are preserved. Some XML titles and dates are inherited or incomplete; the provenance note distinguishes these fields from filenames and current official catalogue dates. OSPAR is empty and is not treated as a supplied layer.

This review did not run the full scientific pipeline or intersect layers with the actual marine mask. Files were not matched against a new MITECO download. Inventory totals include terrestrial records and are not counts of marine protected areas.
