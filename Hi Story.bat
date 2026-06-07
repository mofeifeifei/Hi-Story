@echo off
cd /d "%~dp0"
set "PYTHON_CMD=python"
where pythonw >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=pythonw"
if not exist "data\logs" mkdir "data\logs"
"%PYTHON_CMD%" -c "import requests, docx" >nul 2>nul
if errorlevel 1 (
  echo Missing dependencies.
  echo Please run: python -m pip install -r requirements.txt
  pause
  exit /b 1
)
start "" "%PYTHON_CMD%" main_web.py 1>>"data\logs\startup.log" 2>>&1
exit /b
