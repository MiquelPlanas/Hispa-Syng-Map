@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Hispa-Syng virtual environment was not found.
  echo Run Hispa-Syng once or repair the environment before running the regression suite.
  exit /b 1
)

set "PYTHONDONTWRITEBYTECODE=1"
".venv\Scripts\python.exe" "tests\run_regression_tests.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo REGRESSION TESTS FAILED.
  exit /b %RC%
)

echo.
echo REGRESSION TESTS PASSED.
exit /b 0
