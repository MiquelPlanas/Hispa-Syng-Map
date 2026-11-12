# Comprobaciones nativas de Windows / Native Windows checks

## Estado de esta lista / Checklist status

El análisis operativo bilingüe del 19 de octubre se documenta por separado en EJECUCION_WINDOWS_20261019.md y .json. El registro de seguridad aportado posteriormente contiene nueve grupos de escenarios PASS y un ciclo DPAPI del usuario actual PASS. Véanse [su informe](SEGURIDAD_WINDOWS_20261021.md) y [la consola original](Hispa-Syng_seguridad_Windows.txt). No se ha repetido aquí el análisis operativo ni la batería general.

The 19 October bilingual operational run is documented separately in EJECUCION_WINDOWS_20261019.md and .json. The subsequently supplied security log contains nine scenario-group PASS results and a current-user DPAPI roundtrip PASS. See [its report](SEGURIDAD_WINDOWS_20261021.md) and [the original console output](Hispa-Syng_seguridad_Windows.txt). Neither the operational analysis nor the general suite was rerun here.

| Comprobación / Check | Estado y alcance / Status and scope |
| --- | --- |
| Ciclo de seguridad / Security lifecycle | PASS en nueve grupos del registro aportado; fallos de espacio y escritura simulados / PASS for nine supplied-log groups; injected disk-space and write failures |
| DPAPI, usuario actual / Current-user DPAPI | PASS: cifrado y descifrado del contenido de prueba / Test-payload encryption/decryption roundtrip |
| DPAPI entre cuentas / Cross-account DPAPI | NO EJECUTADO / NOT EXECUTED |
| Inspección independiente de ACL / Independent ACL inspection | SIN EVIDENCIA APORTADA / NO SUPPLIED EVIDENCE |
| Bloqueo exclusivo por otro proceso / Another process holding an exclusive lock | SIN EVIDENCIA APORTADA; distinto del fallo simulado / NO SUPPLIED EVIDENCE; distinct from injected failure |
| Recordar y olvidar acceso mediante el menú / Remember and forget access through the menu | SIN EVIDENCIA APORTADA DE ESTE PROCEDIMIENTO / NO SUPPLIED EVIDENCE FOR THIS PROCEDURE |

Los procedimientos siguientes siguen disponibles para las comprobaciones pendientes. Use proyectos y cuentas de prueba. No convierta resultados no ejecutados en PASS. / The following procedures remain available for pending checks. Use test projects and accounts; do not mark unexecuted checks as PASS.

1. Instale con `Hispa-Syng.bat` en Windows de 64 bits y ejecute `RUN_REGRESSION_TESTS.bat`. Para conservar registros, ejecute `.venv\Scripts\python.exe tests\run_regression_tests.py --report-dir ..\Hispa-Syng_validation_Windows`. El ciclo de seguridad incluye una prueba nativa de ida y vuelta DPAPI bajo el usuario actual. Registre la versión de Windows, Python y dependencias.
2. Cree un proyecto protegido de prueba. Active Recordar acceso, cierre el programa y vuelva a entrar con la misma cuenta. Compruebe el acceso recordado; después use Olvidar acceso y confirme que vuelve a pedir autenticación. No introduzca contraseñas en líneas de comandos ni registros.
3. Durante un análisis protegido, identifique el área bajo `%LOCALAPPDATA%\Hispa-Syng-private`. Examine sus permisos con `icacls`. Una segunda cuenta ordinaria, sin elevación, no debe poder leer sus archivos. La cuenta administradora y el control local privilegiado quedan fuera de esta garantía.
4. Compruebe DPAPI entre dos cuentas con un contenido de prueba, sin credenciales reales, como se indica a continuación. Conceda a ambas cuentas lectura del archivo cifrado de prueba; así se evalúa DPAPI y no solamente la ACL. El usuario creador debe descifrarlo; el segundo debe recibir el rechazo de DPAPI. No muestre el contenido de ningún archivo de credenciales real.
5. En una copia de prueba, detenga el proceso durante la generación. Confirme que no hay salidas sensibles en claro en Resultados. Reinicie y compruebe la recuperación como ejecución incompleta. Repita la rotación con un archivo `.hse` bloqueado en modo exclusivo por otro proceso; compruebe que conserva el registro si no puede restaurar y que recupera el estado anterior después de liberar el bloqueo. El archivo de recuperación debe estar fuera del proyecto.
6. Complete un análisis real de prueba y abra los mapas públicos y un producto cifrado mediante el menú. Registre duración, configuración, salidas y resultado. Esta ejecución operativa no forma parte de la validación sintética incluida.

Desde la raíz del proyecto, bajo la primera cuenta, en una sesión de Python del entorno instalado:

```python
import hashlib, sys
from pathlib import Path
sys.path.insert(0, str(Path('herramientas').resolve()))
from hispa_security import _dpapi_protect, _dpapi_unprotect
entropy = hashlib.sha256(b'Hispa-Syng native isolation test').digest()
blob = _dpapi_protect(b'public synthetic DPAPI canary', entropy)
assert _dpapi_unprotect(blob, entropy) == b'public synthetic DPAPI canary'
Path(r'C:\Users\Public\hispa_dpapi_test.bin').write_bytes(blob)
```

Bajo la segunda cuenta ordinaria, con acceso al archivo de prueba y desde la raíz de la misma copia de código:

```python
import hashlib, sys
from pathlib import Path
sys.path.insert(0, str(Path('herramientas').resolve()))
from hispa_security import _dpapi_unprotect, SecurityError
entropy = hashlib.sha256(b'Hispa-Syng native isolation test').digest()
blob = Path(r'C:\Users\Public\hispa_dpapi_test.bin').read_bytes()
try:
    _dpapi_unprotect(blob, entropy)
except SecurityError:
    print('PASS: DPAPI rejects another ordinary Windows account')
else:
    raise AssertionError('FAIL: another account decrypted the test blob')
```

Si no se puede leer el archivo, no se ha probado el rechazo criptográfico de DPAPI: registre la denegación de lectura por separado. Elimine el archivo de prueba al terminar. / If reading the blob fails, DPAPI cryptographic rejection has not been tested: record the file-permission denial separately and delete the test file afterwards.
