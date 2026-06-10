@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_CONSOLE=python"
set "PYTHON_WINDOW=python"
set "URL_FILE=data\logs\server.url"

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

"%PYTHON_CONSOLE%" -c "import requests, docx" >nul 2>nul
if errorlevel 1 (
  echo Missing dependencies.
  echo Please run: python -m pip install -r requirements.txt
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

echo Hi Story failed to start.
echo Please check: data\logs\startup.log
pause
exit /b 1

:open_url
start "" "%URL%"
exit /b 0

:shutdown_running_servers
powershell -NoProfile -ExecutionPolicy Bypass -Command "$urls=@(); if(Test-Path 'data/logs/server.url'){ $saved=(Get-Content 'data/logs/server.url' -Raw).Trim(); if($saved){ $urls += $saved } }; $urls += 8765..8814 | ForEach-Object { 'http://127.0.0.1:' + $_ + '/' }; function OpenPort($u){ try { $uri=[Uri]$u; $tcp=New-Object Net.Sockets.TcpClient; $ar=$tcp.BeginConnect($uri.Host,$uri.Port,$null,$null); if(-not $ar.AsyncWaitHandle.WaitOne(120,$false)){ $tcp.Close(); return $false }; $tcp.EndConnect($ar); $tcp.Close(); return $true } catch { return $false } }; foreach($u in ($urls | Select-Object -Unique)){ if(-not $u.EndsWith('/')){ $u += '/' }; if(-not (OpenPort $u)){ continue }; try { $health = Invoke-RestMethod -Uri ($u + 'api/health') -TimeoutSec 1; if($health.ok){ Invoke-RestMethod -Uri ($u + 'api/shutdown') -Method Post -TimeoutSec 1 | Out-Null } } catch {} }" >nul 2>nul
ping -n 2 127.0.0.1 >nul
exit /b 0

:find_running_server
set "URL="
for /f "usebackq delims=" %%U in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$urls=@(); if(Test-Path 'data/logs/server.url'){ $saved=(Get-Content 'data/logs/server.url' -Raw).Trim(); if($saved){ $urls += $saved } }; $urls += 8765..8814 | ForEach-Object { 'http://127.0.0.1:' + $_ + '/' }; function OpenPort($u){ try { $uri=[Uri]$u; $tcp=New-Object Net.Sockets.TcpClient; $ar=$tcp.BeginConnect($uri.Host,$uri.Port,$null,$null); if(-not $ar.AsyncWaitHandle.WaitOne(120,$false)){ $tcp.Close(); return $false }; $tcp.EndConnect($ar); $tcp.Close(); return $true } catch { return $false } }; foreach($u in ($urls | Select-Object -Unique)){ if(-not $u.EndsWith('/')){ $u += '/' }; if(-not (OpenPort $u)){ continue }; try { $health = Invoke-RestMethod -Uri ($u + 'api/health') -TimeoutSec 1; if($health.ok){ Write-Output $u; exit 0 } } catch {} }; exit 1"`) do (
  set "URL=%%U"
)
exit /b 0
