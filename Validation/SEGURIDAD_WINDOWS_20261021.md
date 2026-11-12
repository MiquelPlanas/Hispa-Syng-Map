# Hispa-Syng — evidencia de seguridad en Windows / Windows security evidence

## Español

Se ha revisado el registro aportado `Hispa-Syng_seguridad_Windows.txt`. Contiene nueve grupos de escenarios superados y un ciclo DPAPI de cifrado/descifrado superado bajo el usuario actual de Windows. La comprobación con una segunda cuenta consta expresamente como no ejecutada. La tabla reproduce los grupos del registro; no suma cada afirmación interna como una prueba independiente.

| Grupo de escenarios / Scenario group | Registro / Log |
| --- | --- |
| Generación privada fuera de los resultados compartidos / private generation outside shared results | PASS |
| Restricción de salida de la ejecución directa y separación de autoridad del propietario / direct CLI staging guard and owner-role isolation | PASS |
| Bloqueo de publicación tras un fallo de verificación / verification failure blocks publication | PASS |
| Recuperación automática y protección repetible / automatic recovery and idempotent protection | PASS |
| Incorporación de resultados protegidos verificados / verified successful publication | PASS |
| Migración de autoridad del propietario con autenticación por contraseña / owner migration requires password authentication | PASS |
| Conservación del estado recuperable ante fallos simulados de espacio y escritura / full disk and locked-file failures preserve recoverable old state | PASS |
| Restauración tras interrupción abrupta de una rotación en curso / abrupt rotation interruption rolls back all files | PASS |
| Persistencia de una rotación confirmada y acceso a copias antiguas con sus claves / committed rotation survives termination; old copies stay readable | PASS |
| Ciclo DPAPI bajo el usuario actual / Current-user DPAPI roundtrip | PASS |
| Aislamiento entre cuentas de Windows / Cross-Windows-user isolation | NOT EXECUTED |

El código de prueba disponible utiliza un proyecto temporal con contenido ficticio. Los fallos de falta de espacio y destino bloqueado se inyectan sustituyendo la función de escritura; no se llenó físicamente el disco ni se aportó un bloqueo exclusivo mantenido por otro proceso. Las interrupciones de rotación terminan abruptamente subprocesos del ensayo. Un resultado DPAPI correcto con el usuario creador no acredita por sí solo el rechazo bajo una segunda cuenta.

No se ha aportado inspección independiente de las ACL ni una comprobación del acceso recordado/olvidado mediante el menú. El registro tampoco contiene versión de Windows, Python, dependencias, marcas temporales, código de salida del proceso, commit ni hashes del código ejecutado. No se completan esos campos usando datos de otra ejecución. El hash del código de prueba disponible sirve para identificar la fuente consultada al interpretar los escenarios, no para certificar qué copia ejecutó el usuario.

La consola original se conserva byte a byte en UTF-16 con BOM en [Hispa-Syng_seguridad_Windows.txt](Hispa-Syng_seguridad_Windows.txt). Su hash, las líneas de evidencia y los límites están en [SEGURIDAD_WINDOWS_20261021.json](SEGURIDAD_WINDOWS_20261021.json). Las [comprobaciones pendientes de Windows](COMPROBACION_WINDOWS.md) conservan su estado individual. Esta revisión incorpora evidencia existente y no ejecuta pruebas ni repite análisis cartográficos.

Por separado, el usuario ha aportado en la conversación la salida `Ran 10 tests in 0.058s` y `OK` para la prueba de integridad de referencias JSON ejecutada en Windows. Esa salida no forma parte del archivo de seguridad adjunto y no aporta un inventario del código ejecutado.

## English

The supplied `Hispa-Syng_seguridad_Windows.txt` console record reports nine scenario groups passed and a successful DPAPI encryption/decryption roundtrip under the current Windows user. Cross-account isolation is explicitly not executed. The table reproduces scenario groups, not a count of every internal assertion.

The available test uses a temporary project with fictitious content. Disk-full and locked-destination failures are injected by replacing the write function; this is not evidence of physical disk exhaustion or an exclusive lock held by another process. Rotation-interruption scenarios abruptly terminate test subprocesses. A successful creator-account DPAPI roundtrip does not establish second-account rejection.

Independent ACL inspection, external exclusive-file-lock recovery and interactive remember/forget-access checks have not been supplied. The console record lacks Windows/Python versions, dependency versions, timestamps, a process exit code, a commit and executed-source hashes. Metadata from another execution is not assigned to this one. The available test-source hash identifies the file consulted to interpret scenarios; it does not prove the identity of the code run by the user.

The [original UTF-16 console file](Hispa-Syng_seguridad_Windows.txt) is preserved byte for byte. Its hash, evidence lines and limits are recorded in [the structured record](SEGURIDAD_WINDOWS_20261021.json). [Pending Windows checks](COMPROBACION_WINDOWS.md) retain their individual status. This review incorporates existing evidence without executing tests or repeating cartographic analyses.

Separately, the user pasted `Ran 10 tests in 0.058s` and `OK` for the Windows JSON-reference test in the conversation. That report is distinct from the uploaded security log and includes no executed-source inventory.
