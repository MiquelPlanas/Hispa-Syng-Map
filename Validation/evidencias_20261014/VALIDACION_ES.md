# Hispa-Syng v1.0 — validación SIN_RESOURCES

Finalización UTC: 2026-10-14T12:31:11.627308+00:00. Entorno: Python 3.12.14, Linux. Resultado final: 32 comprobaciones PASS; 33 procesos, incluida una repetición registrada del control de contenido del paquete.

## Funcionamiento y pruebas

Las ejecuciones protegidas generan los productos en un área privada, con cifrado y verificación antes de publicar. Existe un bloqueo por proyecto durante la operación. Una interrupción conserva un registro persistente; los trabajos detenidos durante el cálculo se recuperan como incompletos. Los hashes de los resultados publicados permiten completar una limpieza interrumpida sin aceptar archivos alterados.

Antes de crear una copia abierta o protegida se valida la autoridad del propietario y se recuperan los trabajos pendientes del origen. Si falla la recuperación, no se crea destino ni credencial, y se conserva el material pendiente. Las copias del programa excluyen los resultados. El menú informa de estados pendientes.

Las salidas públicas deben estar registradas explícitamente por el generador, con producto y SHA-256 de los bytes. El nombre y la extensión no autorizan una excepción. Se verifican los datos JSON estructurados de los mapas públicos, rechazando campos y puntos de observaciones individuales. Los puntos oficiales de protección se admiten exclusivamente en la capa de catálogo con sus cuatro metadatos y fuente. Las colecciones geométricas de celdas y zonas se representan por sus componentes poligonales, sin modificar la geometría analítica. Las pruebas reproducen estos casos con la preparación real de conservación, en modo abierto y protegido, en ambos idiomas. Un archivo alterado pierde su clasificación pública. Todo producto no registrado se cifra, incluidas figuras y auxiliares. Las páginas informativas de bloqueo requieren el contenedor autenticado correspondiente.

Las pruebas de ambas ediciones renderizan mapas agregados y visores reales, comprueban copias y reescritura de enlaces mediante el constructor web, y verifican que los metadatos individuales de prueba no permanezcan en productos públicos. Se prueban observadores, comentarios, enlaces de observaciones, filas de origen, identificadores de eventos y latitud/longitud individuales. Los documentos descargables de esa prueba web son fixtures sintéticos. La auditoría de protección registra todos los archivos, clasificación, motivo, tamaño y SHA-256; se comprueba que su inventario coincide exactamente con los archivos resultantes.

La separación de autoridad usa un token independiente de la clave de datos. Se prueban credenciales ordinarias manipuladas, migración autenticada y rechazo de administración sin token. La rotación prepara, verifica y respalda antes de sustituir; las pruebas incluyen cierres reales antes y después del compromiso, fallos de escritura/disco y bloqueos simulados. La revocación se refiere a los archivos recifrados del proyecto; las copias antiguas y los datos exportados siguen accesibles con sus credenciales correspondientes.

## Evidencias y cálculo científico

validation.json registra cada comando, código de salida, duración, entorno, versiones cargadas y SHA-256 de las fuentes. Cada .log contiene la salida de un proceso. CONTENIDO_SHA256.txt cubre todos los archivos incluidos salvo el propio inventario. El SHA-256 del ZIP final se facilita externamente para evitar una identificación circular.

scientific_reference_validation.json identifica el paquete de referencia por su hash, compara 52 módulos y registra 750 funciones/clases sin cambios en su representación sintáctica. Los cambios identificados corresponden a renderizado, enlace y publicación; los módulos de cálculo permanecen idénticos. La comparación no es una certificación de todas las combinaciones operativas. La paridad ES/EN exige igualdad de 16 campos serializados tras redondeo numérico a 12 decimales. Los dos libros de entrada permanecen idénticos byte a byte.

Ambas ediciones incluyen la misma política de clasificación. Los cinco DOCX se han renderizado, sus páginas afectadas se han inspeccionado y sus capítulos/anclajes se comprueban en la suite. Se actualizan también las instrucciones y manuales Markdown de ambas ediciones.

## Alcance y límites

Resources no está incluido. Una carpeta Resources parcial provoca error de distribución; HISPA_REQUIRE_RESOURCES=1 exige todos los recursos. LECTURA_ESPACIAL.md y grid_reading_benchmark.json mantienen su ensayo cartográfico fechado y no repetido aquí; resources_reference_sha256.json describe recursos externos.

No se ha ejecutado un análisis completo con los datos operativos y toda la cartografía. Quedan pendientes Windows nativo, DPAPI/ACL, aislamiento entre cuentas y el recorrido completo con BAT. Python 3.10 no se ha ejecutado en este entorno. Las simulaciones no cubren todos los cortes físicos de corriente.

La clasificación presupone código, generadores, configuración y recursos institucionales fiables. La comprobación de campos estructurados no es un detector universal de información sensible en texto arbitrario, imágenes o contenido deliberadamente oculto. Los archivos no registrados se cifran por defecto. La protección admite temporales en claro dentro del área privada y no garantiza borrado forense. Los hashes no autentican al propietario.

Reproducción: `python tests/run_regression_tests.py --report-dir ../Hispa-Syng_validation`.

## Menús de seguridad

La navegación distingue proteger el proyecto actual, compartir copias y gestionar accesos. La prueba independiente tests/_security_menu.py comprueba 44 casos entre ES y EN: rutas, estados abiertos/protegidos, cambio de estado y cancelación sin crear archivos. Los menús abiertos también se ejecutan en procesos reales en ambos idiomas. menu_validation.json y _security_menu.log registran la comprobación.

La comparación por bytes con el paquete de referencia identificado en menu_validation.json confirma que se conservan 84 archivos de src y los dos libros de entrada. Los archivos de cifrado y coordinación del análisis también conservan sus bytes; los cambios del ejecutable se limitan al coordinador de menús. Los registros conservan el intento inicial y la repetición del control de contenido; el resultado final de sus 32 comprobaciones es PASS. Windows nativo no se ha ejecutado.

| Test | Status | Seconds |
|---|---|---:|
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

| Dependency | Loaded version |
|---|---|
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
