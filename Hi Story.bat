@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "URL_FILE=data\logs\server.url"
set "VENV_DIR=.venv"
set "PYTHON_CONSOLE=%VENV_DIR%\Scripts\python.exe"
set "PYTHON_WINDOW=%VENV_DIR%\Scripts\pythonw.exe"

call :ensure_runtime
if errorlevel 1 (
  pause
  exit /b 1
)

call :shutdown_running_servers

del /q "%URL_FILE%" >nul 2>nul
start "" "%PYTHON_WINDOW%" main_web.py --no-browser

set "URL="
for /l %%i in (1,1,60) do (
  call :find_running_server
  if not "!URL!"=="" goto open_url
  ping -n 2 127.0.0.1 >nul
)

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
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '.').Path.TrimEnd('\'); $ports=@(); foreach($line in (netstat -ano -p tcp)){ if($line -match '^\s*TCP\s+127\.0\.0\.1:(\d+)\s+\S+\s+LISTENING\s+\d+\s*$'){ $port=[int]$matches[1]; if($port -ge 8765 -and $port -le 8814 -and -not $ports.Contains($port)){ $ports += $port } } }; foreach($port in $ports){ try { $health=Invoke-RestMethod -Uri ('http://127.0.0.1:' + $port + '/api/health') -TimeoutSec 1; if($health.ok -and $health.data.service -eq 'hi-story' -and ([string]$health.data.root).TrimEnd('\') -ieq $root -and [int]$health.data.pid -gt 0){ Stop-Process -Id ([int]$health.data.pid) -Force -ErrorAction SilentlyContinue } } catch {} }" >nul 2>nul
ping -n 2 127.0.0.1 >nul
exit /b 0

:find_running_server
set "URL="
if exist "%URL_FILE%" (
  for /f "usebackq delims=" %%U in ("%URL_FILE%") do if not defined URL set "URL=%%U"
)
exit /b 0

:ensure_runtime
if not exist "requirements.txt" (
  echo 启动失败：项目目录缺少 requirements.txt。
  exit /b 1
)

if not exist "%PYTHON_CONSOLE%" (
  set "BOOTSTRAP_PYTHON="
  for /f "delims=" %%P in ('where python 2^>nul') do call :consider_python "%%P"
  if not defined BOOTSTRAP_PYTHON (
    echo 启动失败：未找到 Python 3.10 或更高版本。
    echo 请安装 Python 后重新双击此文件。
    exit /b 1
  )
  echo 正在创建项目运行环境，请稍候...
  "!BOOTSTRAP_PYTHON!" -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo 启动失败：无法创建项目运行环境。
    exit /b 1
  )
)

if not exist "%PYTHON_WINDOW%" set "PYTHON_WINDOW=%PYTHON_CONSOLE%"
"%PYTHON_CONSOLE%" -c "import requests, docx" >nul 2>nul
if errorlevel 1 (
  echo 正在安装项目依赖，首次运行可能需要几分钟...
  "%PYTHON_CONSOLE%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo 启动失败：项目依赖安装失败，请检查网络后重试。
    exit /b 1
  )
)
exit /b 0

:consider_python
if defined BOOTSTRAP_PYTHON exit /b 0
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info ^>= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "BOOTSTRAP_PYTHON=%~1"
exit /b 0
