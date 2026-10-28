@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.11 --version >nul 2>&1
  if not errorlevel 1 (
    py -3.11 scripts\bootstrap.py
    goto finished
  )
  python --version >nul 2>&1
  if not errorlevel 1 (
    python scripts\bootstrap.py
    goto finished
  )
  echo Please install 64-bit Python 3.11 from https://www.python.org/downloads/windows/
  echo Enable "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\bootstrap.py
:finished
if errorlevel 1 pause
