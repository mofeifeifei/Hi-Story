@echo off
cd /d "%~dp0"
python -c "import requests, docx" >nul 2>nul
if errorlevel 1 (
  echo Missing dependencies.
  echo Please run: python -m pip install -r requirements.txt
  pause
  exit /b 1
)
where pythonw >nul 2>nul
if errorlevel 1 (
  start "" python main_web.py
) else (
  start "" pythonw main_web.py
)
exit /b
