# Revisión documental de Hispa-Syng — 21 de octubre de 2026

## Alcance

Revisión del contenido y de la navegación documental del ZIP `Hispa-Syng-Map-main.zip` aportado por el usuario.

SHA-256 del ZIP revisado: `8f3d6d5fd848eafd6be6ba3a3d4e0083e57270860777aed106b33260f7d96a12`.

Se inspeccionaron los textos de los seis manuales Word, los README y guías Markdown/TXT de las dos ediciones, los documentos de validación y las rutas de entrada pertinentes. No se modificaron los Word, el código, los Excel, los resultados ni la licencia. Esta revisión no ejecuta el programa ni certifica sus cálculos o su seguridad.

## Qué se cambia

- `README.md` y `LEEME.md`: índices enlazados con las mismas funciones documentales, orden de lectura y referencia expresa a las dos guías de seguridad.
- Inicio rápido: copia del ejemplo como `Datos_data/Ingesta_provisional.xlsx`, conservación de `traits.xlsx`, incorporación de `Resources/` y prevención de una carpeta `Resources/Resources/` anidada.
- Identificación del alcance de los informes de validación y de la lista de comprobaciones nativas de Windows.
- Este informe se añade a `Validation/`. Los registros anteriores se conservan como evidencias fechadas.

## Inventario y decisión

| Qué necesita hacer | Español | Inglés |
| --- | --- | --- |
| Empezar y conocer la estructura | [LEEME.md](../LEEME.md) | [README.md](../README.md) |
| Instalar, ejecutar, reparar y publicar la web | [MANUAL_INSTALACION_PUBLICACION.docx](../MANUAL_INSTALACION_PUBLICACION.docx) | [INSTALLATION_AND_WEB_PUBLICATION.docx](../INSTALLATION_AND_WEB_PUBLICATION.docx) |
| Entender los análisis, las métricas y los resultados; ejemplos y glosario | [Manual_Hispa_Syng_v1_0_ES.docx](../Manual_Hispa_Syng_v1_0_ES.docx) | [Manual_Hispa_Syng_v1_0_EN.docx](../Manual_Hispa_Syng_v1_0_EN.docx) |
| Entender contraseñas, credenciales, copias y carpetas con siete casos prácticos | [SEGURIDAD_Y_CONTRASENAS_HISPA_SYNG.docx](../SEGURIDAD_Y_CONTRASENAS_HISPA_SYNG.docx) | [SECURITY_PASSWORDS_AND_ACCESS_HISPA_SYNG_EN.docx](../SECURITY_PASSWORDS_AND_ACCESS_HISPA_SYNG_EN.docx) |
| Consultar la ejecución y las salidas de una edición | [PYTHON_ESP/LEEME.md](../PYTHON_ESP/LEEME.md) | [PYTHON_ENGLISH/README.md](../PYTHON_ENGLISH/README.md) |
| Consultar el flujo y los bloques de análisis en formato Markdown | [PYTHON_ESP/MANUAL_ANALISIS_COMPLETO.md](../PYTHON_ESP/MANUAL_ANALISIS_COMPLETO.md) | [PYTHON_ENGLISH/FULL_ANALYSIS_MANUAL.md](../PYTHON_ENGLISH/FULL_ANALYSIS_MANUAL.md) |
| Preparar las columnas de entrada y entender los requisitos cartográficos | [PYTHON_ESP/ESPECIFICACION_ENTRADAS_Y_CARTOGRAFIA.md](../PYTHON_ESP/ESPECIFICACION_ENTRADAS_Y_CARTOGRAFIA.md) | [PYTHON_ENGLISH/INPUT_AND_CARTOGRAPHY_SPECIFICATION.md](../PYTHON_ENGLISH/INPUT_AND_CARTOGRAPHY_SPECIFICATION.md) |
| Consultar una guía breve de puesta en marcha de una edición | [PYTHON_ESP/LEEME_PRIMERO.txt](../PYTHON_ESP/LEEME_PRIMERO.txt) | [PYTHON_ENGLISH/READ_ME_FIRST.txt](../PYTHON_ENGLISH/READ_ME_FIRST.txt) |
| Mover la instalación a otra carpeta u ordenador | [PYTHON_ESP/TRASLADO_Y_EJECUCION.md](../PYTHON_ESP/TRASLADO_Y_EJECUCION.md) | [PYTHON_ENGLISH/RELOCATION_AND_EXECUTION.md](../PYTHON_ENGLISH/RELOCATION_AND_EXECUTION.md) |
| Consultar los criterios de validación propios de una edición | [PYTHON_ESP/VALIDACION.md](../PYTHON_ESP/VALIDACION.md) | [PYTHON_ENGLISH/VALIDATION.md](../PYTHON_ENGLISH/VALIDATION.md) |
| Consultar los informes fechados de validación del paquete | [Validation/VALIDACION_ES.md](../Validation/VALIDACION_ES.md) | [Validation/VALIDACION_EN.md](../Validation/VALIDACION_EN.md) |

Otros archivos de referencia compartidos:

| Archivo | Para qué sirve |
| --- | --- |
| [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) | Fuentes y avisos de los recursos cartográficos, fondos web y componentes de terceros. |
| [CITATION.cff](../CITATION.cff) | Metadatos para citar el software. |
| [LICENSE](../LICENSE) | Texto de la licencia incluida en esta copia. |
| [tests/README.md](../tests/README.md) | Alcance, comandos y familias de pruebas de regresión. |
| [Validation/COMPROBACION_WINDOWS.md](../Validation/COMPROBACION_WINDOWS.md) | Lista de comprobaciones nativas de Windows; no constituye un informe de pruebas superadas. |
| [Validation/LECTURA_ESPACIAL.md](../Validation/LECTURA_ESPACIAL.md) | Ensayo fechado de lectura de las mallas MITECO. |
| [Validation/REVISION_CAPAS_PROTEGIDAS.md](../Validation/REVISION_CAPAS_PROTEGIDAS.md) | Revisión de las capas cartográficas de espacios protegidos; no equivale a validar todo el análisis. |

Los JSON de `Validation/` conservan resultados estructurados de comprobaciones concretas. Sus fechas, entornos y alcance corresponden a esas comprobaciones. Los informes incluidos describen pruebas automatizadas en Linux; las comprobaciones nativas de Windows y una ejecución operativa completa requieren sus propias evidencias. Un cambio posterior en los archivos no actualiza automáticamente esos registros ni `Validation/CONTENIDO_SHA256.txt`.

Los seis Word son tres parejas por idioma: guía de instalación/publicación, manual completo y guía de seguridad. El manual completo contiene 28 capítulos; las guías especializadas facilitan tareas concretas. Existe contenido compartido, pero sus funciones justifican conservarlos. Los mensajes de commit que aparecen junto a ellos en GitHub no describen su contenido ni justifican borrarlos.

## Estado de la documentación revisada

Los seis Word incorporan la preparación del ejemplo en español e inglés: copiar `examples/Ingesta_ejemplo.xlsx` como `Datos_data/Ingesta_provisional.xlsx`, mantener la hoja `BD depurada`, conservar `traits.xlsx` e incorporar `Resources/`. Las instrucciones distinguen una instalación de demostración de un proyecto ya protegido. Se mantienen los capítulos, tablas, marcadores y demás contenido; se elimina un salto vacío que generaba una página en blanco tras el índice del manual español.

El usuario confirmó la actualización de `repository-code` en `CITATION.cff` a `https://github.com/MiquelPlanas/Hispa-Syng-Map`. Este parche no sustituye `CITATION.cff` y conserva esa edición ya realizada en el repositorio local.

Los informes [VALIDACION_ES.md](VALIDACION_ES.md) y [VALIDACION_EN.md](VALIDACION_EN.md) usan ahora las fechas y la tabla del mismo `validation.json`. Los textos originales se conservan en `evidencias_20261014/`. La identificación de paquetes, la comparación de hashes y la distinción entre pruebas automatizadas y ejecuciones de Windows se documentan en [REVISION_EVIDENCIAS_20261021.json](REVISION_EVIDENCIAS_20261021.json).

El código de análisis, los Excel, la cartografía y la licencia no se modifican. Las evidencias pendientes de Windows y los registros de proceso ausentes se explican en los informes; la actualización documental no acredita su ejecución. La consulta institucional sobre titularidad y licencia sigue pendiente. La identificación y validación del ZIP definitivo se cerrarán sobre ese archivo concreto.

## Archivos de esta actualización

Se entregan los seis Word, los README de la raíz y de las dos ediciones, las descripciones de validación de ambas ediciones, los informes revisados de Validation, sus tres textos originales archivados, este estado documental, un registro JSON de la revisión y el inventario de los archivos entregados. Se conserva el índice de documentación ya incorporado al repositorio.

Para aplicar la actualización, copie el contenido del ZIP sobre la raíz del repositorio local y combine las carpetas. No elimine los archivos que ya existen en `Validation/`. El inventario `INVENTARIO_REVISION_DOCUMENTAL_SHA256.txt` identifica el contenido de este parche; `CONTENIDO_SHA256.txt` sigue identificando la entrega histórica.

Summary sugerido: `Document example setup and reconcile validation evidence in both languages`.

## English note

All six Word manuals explain example preparation in equivalent Spanish and English instructions. Existing chapters, tables, bookmarks and other content are retained. Root and edition README files distinguish the dependency-lock declaration, automated Linux checks and separately reported Windows runs. Both validation reports use the same general-suite JSON; their original prose reports remain under `evidencias_20261014/`. Raw JSON test records are unchanged. No regression or full operational analysis was rerun. The user-confirmed citation URL change is preserved by excluding CITATION.cff from this patch. The license decision and final-release validation remain separate pending tasks.

## Evidencia operativa de Windows incorporada

Se revisaron el manifiesto y los resúmenes ES/EN de la ejecución del 19 de octubre. Ambos registran Python 3.13.15 y coinciden en entrada, filtros, asignación y métricas. El alcance y las limitaciones están en [EJECUCION_WINDOWS_20261019.md](EJECUCION_WINDOWS_20261019.md). Sigue pendiente la preservación de rutas de auditoría en el resumen inglés, donde `Resultados` aparece traducido a `Results`. No se ha modificado código ni se han repetido análisis.

The 19 October Windows manifest and ES/EN summaries have been reviewed, recording Python 3.13.15 and matching input, filters, assignment and metrics. See [the Windows run report](EJECUCION_WINDOWS_20261019.md). English QA path preservation remains an open traceability item; no code was changed or analysis rerun.
