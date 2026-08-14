@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_CONSOLE=python"
set "PYTHON_WINDOW=python"
set "URL_FILE=data\logs\server.url"

where python >nul 2>nul
if errorlevel 1 (
  echo 未检测到 Python。
  echo 请安装 Python 后重试。
  pause
  exit /b 1
)

where pythonw >nul 2>nul
if not errorlevel 1 set "PYTHON_WINDOW=pythonw"

if not exist "data\logs" mkdir "data\logs"

"%PYTHON_CONSOLE%" -c "import requests, docx" >nul 2>nul
if errorlevel 1 (
  echo 缺少运行依赖。
  echo 请执行：python -m pip install -r requirements.txt
  pause
  exit /b 1
)

call :shutdown_running_servers

del /q "%URL_FILE%" >nul 2>nul
start "" "%PYTHON_WINDOW%" main_web.py --no-browser

for /l %%i in (1,1,60) do (
  if exist "%URL_FILE%" (
    set /p URL=<"%URL_FILE%"
    if defined URL goto open_url
  )
  ping -n 2 127.0.0.1 >nul
)

call :find_running_server
if defined URL goto open_url

echo Hi Story 启动失败。
echo 请查看日志：data\logs\startup.log
pause
exit /b 1

:open_url
start "" "%URL%"
exit /b 0

:shutdown_running_servers
powershell -NoProfile -ExecutionPolicy Bypass -Command "$lines=if(Test-Path 'data/logs/server.url'){ Get-Content 'data/logs/server.url' }else{ @() }; $url=($lines | Where-Object { $_ -match '^https?://' } | Select-Object -First 1); $token=(($lines | Where-Object { $_ -like 'token=*' } | Select-Object -First 1) -replace '^token=',''); if($url -and $token){ try { $health=Invoke-RestMethod -Uri ($url.TrimEnd('/') + '/api/health') -TimeoutSec 1; if($health.ok){ Invoke-RestMethod -Uri ($url.TrimEnd('/') + '/api/shutdown') -Method Post -Headers @{ 'X-HiStory-Token'=$token } -TimeoutSec 1 | Out-Null } } catch {} }" >nul 2>nul
ping -n 2 127.0.0.1 >nul
exit /b 0

:find_running_server
set "URL="
for /f "usebackq delims=" %%U in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "if(Test-Path 'data/logs/server.url'){ Get-Content 'data/logs/server.url' | Where-Object { $_ -match '^https?://' } | Select-Object -First 1 }"`) do (
  set "URL=%%U"
)
exit /b 0
