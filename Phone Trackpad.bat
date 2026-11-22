@echo off
rem Double-click to start Phone Trackpad. The first run sets up a private Python environment.
setlocal
title Phone Trackpad
cd /d "%~dp0desktop"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3 is not installed. Get it from https://www.python.org/downloads/
  echo During setup, tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  rem Same minimum as MIN_PYTHON in desktop\version.py.
  %PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" || (
    echo Phone Trackpad needs Python 3.10 or newer. Get it from https://www.python.org/downloads/
    goto fail
  )
  echo Setting up Phone Trackpad for the first time, this takes a minute...
  %PY% -m venv .venv || goto fail
)

rem Install dependencies on the first run and again whenever requirements.txt changes.
rem The marker lives in .venv\Scripts (macOS uses .venv/bin), so a folder that was also set up
rem on a Mac still gets the Windows packages installed.
rem Ignore personal pip config, so a broken extra index elsewhere can't stall the install.
set "PIP_CONFIG_FILE=nul"
fc /b requirements.txt ".venv\Scripts\requirements.installed" >nul 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto fail
  copy /y requirements.txt ".venv\Scripts\requirements.installed" >nul
)

".venv\Scripts\python.exe" main.py %*
if errorlevel 1 goto fail
exit /b 0

:fail
echo.
echo Phone Trackpad stopped with an error.
pause
exit /b 1
