@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

pushd "%~dp0" >nul
if errorlevel 1 goto :root_error
set "HIPPODEC_ROOT=%CD%"

echo ============================================================
echo          HISPA-SYNG v1.0 - REPARAR / REPAIR
echo ============================================================
echo.
echo 1 - Español
echo 2 - English
echo.
choice /C 12 /N /M "Seleccione el idioma / Select the language [1/2]: "
if errorlevel 2 goto :language_en
goto :language_es

:language_es
set "HIPPODEC_UI_LANG=ES"
goto :repair

:language_en
set "HIPPODEC_UI_LANG=EN"
goto :repair

:repair
call "%HIPPODEC_ROOT%\herramientas\asegurar_entorno_windows.bat" "%HIPPODEC_UI_LANG%" --force
if errorlevel 1 goto :repair_error
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo El entorno común ha sido reconstruido y verificado correctamente.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo The shared environment was rebuilt and verified successfully.
echo.
pause
popd
exit /b 0

:repair_error
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo ERROR: no se pudo reconstruir el entorno común.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo ERROR: the shared environment could not be rebuilt.
echo.
pause
popd
exit /b 1

:root_error
echo ERROR: Hispa-Syng v1.0 cannot access its main folder.
pause
exit /b 1
