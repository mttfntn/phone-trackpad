@echo off
rem Double-click to start PhonePad. The first run sets up a private Python environment.
setlocal
title PhonePad
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
  echo Setting up PhonePad for the first time, this takes a minute...
  %PY% -m venv .venv || goto fail
)

rem Install dependencies on the first run and again whenever requirements.txt changes.
rem Ignore personal pip config, so a broken extra index elsewhere can't stall the install.
set "PIP_CONFIG_FILE=nul"
fc /b requirements.txt ".venv\requirements.installed" >nul 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto fail
  copy /y requirements.txt ".venv\requirements.installed" >nul
)

".venv\Scripts\python.exe" main.py %*
if errorlevel 1 goto fail
exit /b 0

:fail
echo.
echo PhonePad stopped with an error.
pause
exit /b 1
