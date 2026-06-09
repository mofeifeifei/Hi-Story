@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_CONSOLE=python"
set "PYTHON_WINDOW=python"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not available.
  echo Please install Python and try again.
  pause
  exit /b 1
)

where pythonw >nul 2>nul
if not errorlevel 1 set "PYTHON_WINDOW=pythonw"

if not exist "data\logs" mkdir "data\logs"
set "URL_FILE=data\logs\server.url"
del /q "%URL_FILE%" >nul 2>nul

"%PYTHON_CONSOLE%" -c "import requests, docx" >nul 2>nul
if errorlevel 1 (
  echo Missing dependencies.
  echo Please run: python -m pip install -r requirements.txt
  pause
  exit /b 1
)

start "" "%PYTHON_WINDOW%" main_web.py --no-browser 1>>"data\logs\startup.log" 2>>&1

for /l %%i in (1,1,20) do (
  if exist "%URL_FILE%" (
    set /p URL=<"%URL_FILE%"
    if defined URL goto open_url
  )
  ping -n 2 127.0.0.1 >nul
)

echo Hi Story failed to start.
echo Please check: data\logs\startup.log
pause
exit /b 1

:open_url
start "" "%URL%"
exit /b 0
