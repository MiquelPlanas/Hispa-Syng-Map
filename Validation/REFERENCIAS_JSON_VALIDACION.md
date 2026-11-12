# Hispa-Syng — integridad de referencias JSON / JSON reference integrity

## Español

Los dos generadores ingleses de control de calidad conservan las rutas de archivo, los enlaces y los metadatos de origen al presentar informes JSON. Las etiquetas y las categorías de hábitat siguen su traducción habitual. Una ruta registrada conserva exactamente su texto, incluidos nombres de carpetas como `Resultados`; no se cambia el nombre ni la ubicación del archivo al redactar el informe.

Se ejecutaron diez casos de prueba específicos el 21 de octubre de 2026, todos superados. Cubren rutas de Windows, UNC, POSIX y relativas, nombres de archivo en campos de referencia, enlaces, metadatos, estructuras anidadas, valores numéricos y ausencia de modificación de la entrada. Un caso escribe un JSON y abre el archivo mediante la ruta recuperada. También se comprueba que la traducción intencionada del nombre de un producto nuevo sigue disponible por separado.

La prueba importa el módulo real de localización y compila las definiciones reales de las dos funciones de presentación JSON, con sus importaciones de localización, desde su árbol de sintaxis. Así prueba esta frontera sin cargar el conjunto de dependencias cartográficas. No constituye una importación completa ni una ejecución de las canalizaciones científicas. Se ejecutaron además los controles existentes de organización de carpetas de ambas ediciones y de presentación/distribución. Se comprobó la sintaxis de todos los archivos Python y la igualdad del código de orquestación fuera de las funciones e importaciones de presentación modificadas.

El entorno de estas pruebas es Linux con Python 3.12.14; sus versiones, comandos, resultados y hashes están en [el registro JSON](REFERENCIAS_JSON_VALIDACION.json), y la salida completa en [el registro de ejecución](REFERENCIAS_JSON_VALIDACION.log). La nueva prueba forma parte del ejecutor general, sin atribuir a esta revisión una ejecución completa de esa batería.

Los registros de Windows del 19 de octubre conservan su contenido y su alcance histórico. Estas pruebas no reescriben sus rutas ni demuestran que se haya repetido aquel análisis con este código. No se han ejecutado aquí pruebas nativas de Windows, DPAPI, ACL o recuperación. Para repetir únicamente los diez casos desde la raíz del proyecto, con el entorno instalado:

```powershell
.venv\Scripts\python.exe tests\_json_reference_integrity.py
```

## English

Both English quality-control JSON writers retain recorded file paths, links and source metadata. Labels and habitat categories continue to use their established translations. A recorded reference keeps its exact text, including folder names such as `Resultados`; writing the report does not rename or relocate the file.

Ten focused test cases ran on 21 October 2026 and all passed. They cover Windows, UNC, POSIX and relative paths, basenames in reference fields, URLs, metadata, nested structures, numerical values and input immutability. One case writes a JSON report and opens the original file through the recorded path. Deliberate filename translation for newly generated products is also checked separately.

The test imports the real localization module and compiles the actual definitions of both JSON presentation functions, with their localization imports, from the source syntax tree. This exercises the presentation boundary without loading the GIS dependency graph; it is not a full pipeline import or scientific execution. Existing folder-organization checks for both editions and the presentation/distribution check also passed. All Python files were syntax-checked. Orchestration code outside the changed presentation functions and imports retains the same syntax tree.

These tests ran on Linux with Python 3.12.14. Environment versions, commands, results and source hashes are in [the JSON record](REFERENCIAS_JSON_VALIDACION.json); full output is in [the execution log](REFERENCIAS_JSON_VALIDACION.log). The focused test is registered with the general runner, but the complete suite was not rerun here.

The 19 October Windows records retain their original content and historical scope. These tests do not rewrite their paths or establish that the Windows analysis was rerun with this code. Native Windows, DPAPI, ACL and recovery checks were not executed here. The command above runs only the ten focused cases in an installed Windows environment.
