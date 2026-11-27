@echo off
setlocal
cd /d "%~dp0"

rem Prefer the Python bundled with DeepSeek Harness (it includes Pillow).
set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if exist "%PY%" goto run

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ was not found.
  pause
  exit /b 2
)
set "PY=python"

:run
"%PY%" -u "%~dp0scad_drop.py" --render-file "%~1" %2 %3 %4 %5
if errorlevel 1 pause
