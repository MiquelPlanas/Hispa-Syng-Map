@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

set "HIPPODEC_UI_LANG=%~1"
if /I "%HIPPODEC_UI_LANG%"=="EN" goto :language_ok
set "HIPPODEC_UI_LANG=ES"

:language_ok
pushd "%~dp0.." >nul
if errorlevel 1 goto :root_error
set "HIPPODEC_ROOT=%CD%"
set "HIPPODEC_ACTIVE_ROOT=%CD%"
set "HIPPODEC_PYTHON=%CD%\.venv\Scripts\python.exe"
set "HIPPODEC_REQUIREMENTS=%CD%\requirements.txt"
set "HIPPODEC_CHECK_ES=%CD%\PYTHON_ESP\comprobar_entorno.py"
set "HIPPODEC_CHECK_EN=%CD%\PYTHON_ENGLISH\check_environment.py"
set "HIPPODEC_CODE_ES=%CD%\PYTHON_ESP"
set "HIPPODEC_CODE_EN=%CD%\PYTHON_ENGLISH"
set "HIPPODEC_TOOLS=%CD%\herramientas"
set "HIPPODEC_MAIN_BATCH=%CD%\Hispa-Syng.bat"
set "HIPPODEC_REPAIR_BATCH=%CD%\REPARAR_ENTORNO_HISPA_SYNG.bat"
set "HIPPODEC_OLD_ENV_NAME="

call :check_layout
if errorlevel 1 goto :failure
call :unblock_code

if /I "%~2"=="--force" goto :rebuild_forced
if not exist "%HIPPODEC_PYTHON%" goto :rebuild_missing

rem Virtual environments retain installation paths. The marker detects a renamed
rem or relocated main folder before scientific libraries are loaded.
"%HIPPODEC_PYTHON%" -c "import os,sys; from pathlib import Path; marker=Path(sys.prefix)/'hippodec_root.txt'; expected=str(Path(os.environ['HIPPODEC_ACTIVE_ROOT']).resolve()).casefold(); actual=marker.read_text(encoding='utf-8').strip().casefold() if marker.is_file() else ''; raise SystemExit(0 if actual == expected else 1)" >nul 2>&1
if errorlevel 1 goto :rebuild_relocated

call :check_quiet
set "HIPPODEC_CHECK_RESULT=%ERRORLEVEL%"
if "%HIPPODEC_CHECK_RESULT%"=="0" goto :ready_existing
if "%HIPPODEC_CHECK_RESULT%"=="5" goto :repair_gdal
goto :rebuild_invalid

:ready_existing
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Entorno común comprobado: no es necesario reinstalar bibliotecas.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo Shared environment checked: the libraries do not need to be reinstalled.
popd
exit /b 0

:repair_gdal
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Se reparará únicamente pyogrio y el GDAL incluido en su paquete.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo Only pyogrio and the GDAL bundled with it will be repaired.
"%HIPPODEC_PYTHON%" -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: --force-reinstall --no-deps pyogrio==0.11.1
if errorlevel 1 goto :rebuild_invalid
call :unblock_code
call :check_full
if errorlevel 1 goto :rebuild_invalid
goto :ready_existing

:rebuild_forced
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Se ha solicitado la reconstrucción completa del entorno común.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo A complete rebuild of the shared environment was requested.
goto :archive_old_environment

:rebuild_missing
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo El entorno común todavía no está instalado.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo The shared environment has not been installed yet.
goto :archive_old_environment

:rebuild_relocated
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Se ha detectado que la carpeta principal fue trasladada o renombrada.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo El entorno Python se reconstruirá; los datos y resultados no se modificarán.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo The main folder has been moved or renamed.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo The Python environment will be rebuilt; data and results will not be modified.
goto :archive_old_environment

:rebuild_invalid
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo El entorno común está incompleto o alguna biblioteca no puede cargarse.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo The shared environment is incomplete or a library cannot be loaded.
goto :archive_old_environment

:archive_old_environment
if not exist ".venv" goto :create_environment
set "HIPPODEC_OLD_ENV_NAME=.venv_respaldo_temporal"
set "HIPPODEC_OLD_ENV_INDEX=1"

:find_backup_name
if not exist "%HIPPODEC_ROOT%\%HIPPODEC_OLD_ENV_NAME%" goto :move_old_environment
set /a HIPPODEC_OLD_ENV_INDEX+=1
set "HIPPODEC_OLD_ENV_NAME=.venv_respaldo_temporal_%HIPPODEC_OLD_ENV_INDEX%"
goto :find_backup_name

:move_old_environment
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Conservando temporalmente el entorno anterior como %HIPPODEC_OLD_ENV_NAME%...
if /I "%HIPPODEC_UI_LANG%"=="EN" echo Temporarily preserving the previous environment as %HIPPODEC_OLD_ENV_NAME%...
ren ".venv" "%HIPPODEC_OLD_ENV_NAME%"
if errorlevel 1 goto :archive_error

:create_environment
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Buscando Python de 64 bits compatible ^(3.10 a 3.13^) ...
if /I "%HIPPODEC_UI_LANG%"=="EN" echo Looking for compatible 64-bit Python ^(3.10 to 3.13^) ...

:try_python_313
call :clear_partial_environment
if errorlevel 1 goto :delete_error
py -3.13 -c "import struct,sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,14) and struct.calcsize('P')*8 == 64 else 1)" >nul 2>&1
if errorlevel 1 goto :try_python_312
py -3.13 -m venv ".venv"
if not errorlevel 1 goto :environment_created

:try_python_312
call :clear_partial_environment
if errorlevel 1 goto :delete_error
py -3.12 -c "import struct,sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,14) and struct.calcsize('P')*8 == 64 else 1)" >nul 2>&1
if errorlevel 1 goto :try_python_311
py -3.12 -m venv ".venv"
if not errorlevel 1 goto :environment_created

:try_python_311
call :clear_partial_environment
if errorlevel 1 goto :delete_error
py -3.11 -c "import struct,sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,14) and struct.calcsize('P')*8 == 64 else 1)" >nul 2>&1
if errorlevel 1 goto :try_python_310
py -3.11 -m venv ".venv"
if not errorlevel 1 goto :environment_created

:try_python_310
call :clear_partial_environment
if errorlevel 1 goto :delete_error
py -3.10 -c "import struct,sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,14) and struct.calcsize('P')*8 == 64 else 1)" >nul 2>&1
if errorlevel 1 goto :try_python_default
py -3.10 -m venv ".venv"
if not errorlevel 1 goto :environment_created

:try_python_default
call :clear_partial_environment
if errorlevel 1 goto :delete_error
python -c "import struct,sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,14) and struct.calcsize('P')*8 == 64 else 1)" >nul 2>&1
if errorlevel 1 goto :python_error
python -m venv ".venv"
if errorlevel 1 goto :python_error

:environment_created
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Actualizando las herramientas de instalación...
if /I "%HIPPODEC_UI_LANG%"=="EN" echo Updating the installation tools...
"%HIPPODEC_PYTHON%" -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
if errorlevel 1 goto :installation_error

if /I "%HIPPODEC_UI_LANG%"=="ES" echo Instalando una sola vez las dependencias comunes de las dos versiones...
if /I "%HIPPODEC_UI_LANG%"=="EN" echo Installing the dependencies shared by both versions once...
"%HIPPODEC_PYTHON%" -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: -r "%HIPPODEC_REQUIREMENTS%"
if errorlevel 1 goto :installation_error

call :unblock_code
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Verificando las bibliotecas y realizando una prueba geoespacial...
if /I "%HIPPODEC_UI_LANG%"=="EN" echo Checking the libraries and running a geospatial test...
call :check_full
if errorlevel 1 goto :verification_error

"%HIPPODEC_PYTHON%" -c "import os,sys; from pathlib import Path; Path(sys.prefix,'hippodec_root.txt').write_text(str(Path(os.environ['HIPPODEC_ACTIVE_ROOT']).resolve()),encoding='utf-8')"
if errorlevel 1 goto :marker_error

if not defined HIPPODEC_OLD_ENV_NAME goto :installation_success
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Eliminando el respaldo temporal del entorno anterior...
if /I "%HIPPODEC_UI_LANG%"=="EN" echo Removing the temporary backup of the previous environment...
rmdir /s /q "%HIPPODEC_ROOT%\%HIPPODEC_OLD_ENV_NAME%"
if exist "%HIPPODEC_ROOT%\%HIPPODEC_OLD_ENV_NAME%" goto :backup_cleanup_warning

:installation_success
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Instalación común finalizada correctamente.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo Shared installation completed successfully.
popd
exit /b 0

:backup_cleanup_warning
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo AVISO: no se pudo eliminar %HIPPODEC_OLD_ENV_NAME%; puede borrarlo manualmente.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo WARNING: %HIPPODEC_OLD_ENV_NAME% could not be removed; it may be deleted manually.
goto :installation_success

:check_layout
if not exist "%HIPPODEC_REQUIREMENTS%" goto :check_layout_error
if not exist "%HIPPODEC_CHECK_ES%" goto :check_layout_error
if not exist "%HIPPODEC_CHECK_EN%" goto :check_layout_error
exit /b 0

:check_layout_error
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo ERROR: faltan archivos de instalación o una de las carpetas PYTHON_ESP/PYTHON_ENGLISH.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo ERROR: installation files or one of the PYTHON_ESP/PYTHON_ENGLISH folders are missing.
exit /b 1

:check_quiet
if /I "%HIPPODEC_UI_LANG%"=="EN" "%HIPPODEC_PYTHON%" "%HIPPODEC_CHECK_EN%" --quiet
if /I "%HIPPODEC_UI_LANG%"=="ES" "%HIPPODEC_PYTHON%" "%HIPPODEC_CHECK_ES%" --quiet
exit /b %ERRORLEVEL%

:check_full
if /I "%HIPPODEC_UI_LANG%"=="EN" "%HIPPODEC_PYTHON%" "%HIPPODEC_CHECK_EN%" --full
if /I "%HIPPODEC_UI_LANG%"=="ES" "%HIPPODEC_PYTHON%" "%HIPPODEC_CHECK_ES%" --full
exit /b %ERRORLEVEL%

:unblock_code
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ext=@('.py','.pyc','.pyd','.dll','.exe','.bat','.ps1','.toml','.yaml','.yml'); $roots=@($env:HIPPODEC_CODE_ES,$env:HIPPODEC_CODE_EN,$env:HIPPODEC_TOOLS,($env:HIPPODEC_ACTIVE_ROOT+'\.venv')); foreach($root in $roots){if(Test-Path -LiteralPath $root){Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue | Where-Object {$ext -contains $_.Extension.ToLowerInvariant()} | Unblock-File -ErrorAction SilentlyContinue}}; @($env:HIPPODEC_MAIN_BATCH,$env:HIPPODEC_REPAIR_BATCH) | ForEach-Object {if(Test-Path -LiteralPath $_){Unblock-File -LiteralPath $_ -ErrorAction SilentlyContinue}}" >nul 2>&1
exit /b 0

:clear_partial_environment
if not exist ".venv" exit /b 0
rmdir /s /q ".venv"
if exist ".venv" exit /b 1
exit /b 0

:recover_previous_environment
if exist ".venv" rmdir /s /q ".venv"
if not defined HIPPODEC_OLD_ENV_NAME exit /b 0
if not exist "%HIPPODEC_ROOT%\%HIPPODEC_OLD_ENV_NAME%" exit /b 0
ren "%HIPPODEC_OLD_ENV_NAME%" ".venv"
exit /b 0

:archive_error
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo ERROR: no se pudo conservar temporalmente el entorno anterior. Cierre Python e inténtelo de nuevo.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo ERROR: the previous environment could not be preserved temporarily. Close Python and try again.
goto :failure

:delete_error
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo ERROR: no se pudo retirar un entorno parcial. Cierre Python e inténtelo de nuevo.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo ERROR: a partial environment could not be removed. Close Python and try again.
call :recover_previous_environment
goto :failure

:python_error
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo ERROR: no se encontró Python de 64 bits en una versión compatible ^(3.10 a 3.13^).
if /I "%HIPPODEC_UI_LANG%"=="EN" echo ERROR: compatible 64-bit Python ^(3.10 to 3.13^) was not found.
call :recover_previous_environment
goto :failure

:installation_error
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo ERROR: no se pudieron descargar o instalar las bibliotecas. Compruebe la conexión a Internet.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo ERROR: the libraries could not be downloaded or installed. Check the Internet connection.
call :recover_previous_environment
goto :failure

:verification_error
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo ERROR: una biblioteca no superó la comprobación final.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo ERROR: a library failed the final check.
call :recover_previous_environment
goto :failure

:marker_error
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo ERROR: no se pudo registrar la ubicación de la instalación.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo ERROR: the installation location could not be recorded.
call :recover_previous_environment
goto :failure

:root_error
echo ERROR: Hispa-Syng v1.0 cannot access its main folder.
exit /b 1

:failure
popd
exit /b 1
