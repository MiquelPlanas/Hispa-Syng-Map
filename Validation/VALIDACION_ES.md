# Hispa-Syng v1.0 — alcance de la validación

Esta revisión identifica las evidencias incluidas en el código distribuido, su entorno y su relación con el ZIP aportado el 21 de octubre de 2026. La validación general registra 32 comprobaciones finales PASS del 14 de octubre; no se ha vuelto a ejecutar esa suite durante esta actualización documental. Los resultados conservan su alcance original.

## Paquete y documentos de referencia

El ZIP revisado es `Hispa-Syng-Map-main.zip`, sin `Resources/` ni el libro operativo `Datos_data/Ingesta_provisional.xlsx`. Incluye `examples/Ingesta_ejemplo.xlsx` y `Datos_data/traits.xlsx`. Su hash y los hashes del código se registran en [REVISION_EVIDENCIAS_20261021.json](REVISION_EVIDENCIAS_20261021.json). El archivo identifica la descarga aportada, no un commit obtenido directamente de GitHub ni el futuro ZIP final.

Los hashes de paquetes que aparecen en `scientific_reference_validation.json`, `menu_validation.json` y `SELECCION_ESPECIES_VALIDACION.json` identifican referencias de comparación diferentes. No se dispone aquí de nombres inequívocos ni de los ZIP originales de todas esas referencias. No se atribuye a ninguno de esos hashes la identidad del ZIP actual.

## Relación entre los registros y el código revisado

| Evidencia | Resultado registrado y alcance | Comparación por hash con el ZIP aportado |
| --- | --- | --- |
| [validation.json](validation.json) | Suite general: 32 comprobaciones finales PASS; 33 procesos, incluido un primer intento fallido de `_release_hygiene` seguido de repetición PASS. | 81 de 90 archivos Python coinciden; nueve difieren. |
| [SELECCION_ESPECIES_VALIDACION.json](SELECCION_ESPECIES_VALIDACION.json) | Selección de especies con autoridades taxonómicas, configuración y paridad de 16 campos; no ejecuta el análisis cartográfico completo. | Coinciden los seis archivos identificados. |
| [CREDITOS_CARTOGRAFICOS_VALIDACION.json](CREDITOS_CARTOGRAFICOS_VALIDACION.json) | Créditos y atribuciones cartográficas, presentación y paridad de 16 campos; no repite el flujo completo en Windows. | Coinciden los 14 archivos identificados. |
| [scientific_reference_validation.json](scientific_reference_validation.json) | Comparación previa de 52 módulos y 750 funciones/clases; no demuestra por sí sola equivalencia científica del ZIP actual. | 46 de los 52 módulos coinciden con los hashes registrados; seis difieren. |
| [menu_validation.json](menu_validation.json) | Declara 44 escenarios ES/EN y menús abiertos ejecutados; Windows nativo no ejecutado en ese registro. | No contiene un inventario hash suficiente para identificar todo el estado probado. |
| [CAPAS_PROTEGIDAS_VALIDACION.json](CAPAS_PROTEGIDAS_VALIDACION.json) | Revisión de archivos y capas protegidas; no valida toda la ejecución científica. | Coinciden los dos módulos de conservación identificados; las capas externas no están en este ZIP. |
| [grid_reading_benchmark.json](grid_reading_benchmark.json) | Ensayo fechado de lectura de 15 archivos de malla con ubicaciones de prueba; no es un análisis operativo completo. | Sus fuentes cartográficas externas no se adjuntan en este ZIP. |

Los nueve archivos distintos respecto a la suite general están cubiertos por hashes coincidentes de las comprobaciones posteriores de selección de especies o créditos. Esto permite relacionar los cambios con esas evidencias; no equivale a repetir la suite general sobre el estado actual.

## Entorno y ejecuciones de Windows

El registro general declara Python 3.12.14 en Linux. Comenzó el 2026-10-14T12:22:31.520636+00:00 y finalizó el 2026-10-14T12:31:11.627308+00:00 (UTC). Ambos informes de esta revisión usan estas fechas del mismo JSON. El texto inglés original indicaba otra hora; se conserva sin modificar en `evidencias_20261014/`.

Ese entorno corresponde a las pruebas automatizadas de preparación. Por separado, se han revisado el manifiesto y los resúmenes ES/EN de la ejecución operativa en Windows `20261019_094827_65e45b50`, del 19 de octubre: ambas ediciones registran finalización correcta, Python 3.13.15 y coincidencia de los controles principales. Véanse [el informe de la ejecución](EJECUCION_WINDOWS_20261019.md) y [sus comparaciones estructuradas](EJECUCION_WINDOWS_20261019.json). La ejecución usa datos operativos, 1 km, 12 especies y modo abierto. No acredita los controles específicos de DPAPI, ACL o aislamiento entre cuentas, ni identifica por sí sola el commit o ZIP exacto ejecutado. El informe histórico identifica la traducción de `Resultados` a `Results` en rutas del resumen inglés. La presentación JSON actual conserva las referencias registradas en los dos generadores ingleses de control de calidad. El [informe de integridad de referencias](REFERENCIAS_JSON_VALIDACION.md) identifica por separado los hashes actuales, diez pruebas específicas y sus límites. Los registros originales de octubre se conservan sin modificar; estas pruebas no repiten aquel análisis en Windows.

El archivo `requirements-lock-py313-win64.txt` identifica una configuración de dependencias destinada a Python 3.13 en Windows. Su existencia no demuestra que la validación general incluida se ejecutara allí.

La cabecera de ese archivo de dependencias declara Windows x64, Python 3.13.15 y generación desde un entorno de trabajo el 17 de septiembre de 2026. Se conserva esa declaración como metadato del archivo; el resumen de la ejecución de octubre confirma esa versión de Python, sin aportar un inventario completo de dependencias.

El registro de consola aportado para `tests/_security_lifecycle.py` contiene PASS para nueve grupos de escenarios y para el ciclo DPAPI de cifrado y descifrado bajo el usuario actual de Windows. Los fallos de espacio y bloqueo de destino de esos escenarios se simulan en el código de prueba; las interrupciones de rotación terminan subprocesos de prueba. El aislamiento entre cuentas figura como no ejecutado. No se ha aportado una inspección independiente de ACL ni un ensayo con un bloqueo exclusivo mantenido por otro proceso. El registro no contiene versión de Windows/Python, dependencias, commit ni hashes del código ejecutado; no se le atribuyen los del análisis del 19 de octubre. Véanse [el informe de seguridad de Windows](SEGURIDAD_WINDOWS_20261021.md), [el registro estructurado](SEGURIDAD_WINDOWS_20261021.json) y [la consola original](Hispa-Syng_seguridad_Windows.txt).

## Disponibilidad y límites de las evidencias

`validation.json` conserva comandos, estados, duraciones, entorno y hashes. Los 33 archivos `.log` que referencia, incluido el intento inicial, no están en el ZIP aportado. Se conservan las declaraciones registradas, pero no se ha reconstruido su salida ni certificado la ejecución a partir de los hashes. El código de los ensayos está disponible en `tests/`; algunas comprobaciones de distribución requieren los recursos externos.

`CONTENIDO_SHA256.txt` se conserva como inventario de la entrega histórica, no del ZIP actual ni de este parche. `INVENTARIO_REVISION_DOCUMENTAL_SHA256.txt` corresponde a la entrega documental previa. La evidencia operativa del 19 de octubre tiene su inventario en `INVENTARIO_EVIDENCIAS_WINDOWS_SHA256.txt`; esta incorporación de seguridad se identifica en `INVENTARIO_SEGURIDAD_WINDOWS_SHA256.txt`. El inventario y hash de la distribución completa se generarán al cerrar esa distribución.

Las instrucciones de [COMPROBACION_WINDOWS.md](COMPROBACION_WINDOWS.md) permiten documentar DPAPI con el usuario actual y otro usuario, ACL del área privada, interrupciones, bloqueos y recuperación de rotación. Cada comprobación conserva su estado hasta contar con su propia evidencia. La paridad de 16 campos sobre datos de prueba no es una certificación de equivalencia en todas las configuraciones o datos operativos.

Para obtener un informe nuevo de regresión, desde la raíz y con el entorno instalado: `.venv\Scripts\python.exe tests\run_regression_tests.py --report-dir ..\Hispa-Syng_validation_Windows`. Conserve esos registros fuera del repositorio y no incluya contraseñas o credenciales. Esta orden se proporciona como procedimiento; no se ha ejecutado en esta revisión.

La revisión documental histórica no repitió la batería general. Las comprobaciones actuales de integridad de referencias se registran por separado en REFERENCIAS_JSON_VALIDACION.json. No repiten el análisis cartográfico completo ni convierten otras comprobaciones pendientes en PASS.

## Resultados conservados de la suite general

La tabla se genera de `validation.json`; los tiempos pertenecen a la ejecución histórica.

| Test | Status | Seconds |
| --- | --- | ---: |
| _grid_reading_PYTHON_ESP | PASS | 1.481 |
| _edition_regressions_PYTHON_ESP | PASS | 7.581 |
| _conservation_smoke_PYTHON_ESP | PASS | 5.209 |
| _community_integration_smoke_PYTHON_ESP | PASS | 34.108 |
| _multiscale_integration_smoke_PYTHON_ESP | PASS | 32.141 |
| _conservation_integration_smoke_PYTHON_ESP | PASS | 8.986 |
| _functional_integration_smoke_PYTHON_ESP | PASS | 35.517 |
| _configuration_matrix_PYTHON_ESP | PASS | 26.044 |
| _output_folder_localization_PYTHON_ESP | PASS | 0.033 |
| _metadata_exports_PYTHON_ESP | PASS | 0.948 |
| _public_output_policy_PYTHON_ESP | PASS | 2.436 |
| _public_geometry_PYTHON_ESP | PASS | 7.362 |
| _grid_reading_PYTHON_ENGLISH | PASS | 2.376 |
| _edition_regressions_PYTHON_ENGLISH | PASS | 5.916 |
| _conservation_smoke_PYTHON_ENGLISH | PASS | 6.636 |
| _community_integration_smoke_PYTHON_ENGLISH | PASS | 17.985 |
| _multiscale_integration_smoke_PYTHON_ENGLISH | PASS | 6.112 |
| _conservation_integration_smoke_PYTHON_ENGLISH | PASS | 9.175 |
| _functional_integration_smoke_PYTHON_ENGLISH | PASS | 17.954 |
| _configuration_matrix_PYTHON_ENGLISH | PASS | 7.593 |
| _output_folder_localization_PYTHON_ENGLISH | PASS | 0.087 |
| _metadata_exports_PYTHON_ENGLISH | PASS | 0.653 |
| _public_output_policy_PYTHON_ENGLISH | PASS | 2.324 |
| _public_geometry_PYTHON_ENGLISH | PASS | 5.782 |
| _bilingual_parity | PASS | 34.436 |
| _presentation_and_distribution | PASS | 0.546 |
| _security_regressions | PASS | 2.311 |
| _security_lifecycle | PASS | 4.453 |
| _coordinator_security | PASS | 0.633 |
| _execution_recovery | PASS | 1.453 |
| _distribution_recovery | PASS | 0.849 |
| _release_hygiene | PASS | 0.037 |

| Dependency | Recorded version |
| --- | --- |
| numpy | 2.3.5 |
| pandas | 2.3.3 |
| geopandas | 1.2.0 |
| shapely | 2.1.2 |
| pyproj | 3.8.0 |
| pyogrio | 0.11.1 |
| scipy | 1.17.0 |
| matplotlib | 3.10.8 |
| seaborn | 0.13.2 |
| scikit-learn | 1.8.0 |
| statsmodels | 0.14.6 |
| cryptography | 46.0.0 |
| python-docx | 1.2.0 |
