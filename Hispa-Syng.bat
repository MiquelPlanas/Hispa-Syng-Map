@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

pushd "%~dp0" >nul
if errorlevel 1 goto :root_error
set "HIPPODEC_ROOT=%CD%"

cls
echo ============================================================
echo          HISPA-SYNG v1.0 - HIPPO-DEC / HIPPO-DEC PROJECT
echo ============================================================
echo.
echo 1 - Español
echo 2 - English
echo.
:select_language
setlocal EnableDelayedExpansion
set "HISPA_SYNG_LANGUAGE_CHOICE="
set /p "HISPA_SYNG_LANGUAGE_CHOICE=Seleccione el idioma / Select the language [1/2]: "
if "!HISPA_SYNG_LANGUAGE_CHOICE!"=="1" (endlocal & goto :language_es)
if "!HISPA_SYNG_LANGUAGE_CHOICE!"=="2" (endlocal & goto :language_en)
echo Seleccione 1 o 2 / Enter 1 or 2.
endlocal
goto :select_language

:language_es
set "HIPPODEC_UI_LANG=ES"
goto :ensure_environment

:language_en
set "HIPPODEC_UI_LANG=EN"
goto :ensure_environment

:ensure_environment
call "%HIPPODEC_ROOT%\herramientas\asegurar_entorno_windows.bat" "%HIPPODEC_UI_LANG%"
if errorlevel 1 goto :environment_error

if exist "%HIPPODEC_ROOT%\herramientas\seguridad_proyecto.py" goto :run_workflow
if /I "%HIPPODEC_UI_LANG%"=="ES" echo El entorno común ha quedado instalado y verificado correctamente.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo The shared environment was installed and verified successfully.
goto :success

:run_workflow
"%HIPPODEC_ROOT%\.venv\Scripts\python.exe" "%HIPPODEC_ROOT%\herramientas\seguridad_proyecto.py" --ui-language "%HIPPODEC_UI_LANG%" --project-root "%HIPPODEC_ROOT%"
if errorlevel 1 goto :execution_error
goto :success

:environment_error
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo ERROR: no se pudo preparar el entorno común de Hispa-Syng v1.0.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo ERROR: the shared Hispa-Syng v1.0 environment could not be prepared.
goto :failure

:execution_error
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo ERROR: la ejecución bilingüe no ha finalizado correctamente.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo ERROR: the bilingual run did not finish successfully.
goto :failure

:success
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Puede cerrar esta ventana.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo You may close this window.
echo.
pause
popd
exit /b 0

:failure
echo.
if /I "%HIPPODEC_UI_LANG%"=="ES" echo Revise los mensajes anteriores antes de intentarlo de nuevo.
if /I "%HIPPODEC_UI_LANG%"=="EN" echo Review the preceding messages before trying again.
echo.
pause
popd
exit /b 1

:root_error
echo ERROR: Hispa-Syng v1.0 cannot access its main folder.
pause
exit /b 1
