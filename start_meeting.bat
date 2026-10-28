@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing project Python environment.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m meeting_agent.ui
if errorlevel 1 pause
