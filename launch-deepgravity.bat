@echo off
title DeepGravity
cd /d "%~dp0"

echo.
echo    ____             __
echo   / __ \___  ____ _/ /____  _____
echo  / / / / _ \/ __ '/ __/ _ \/ ___/
echo / /_/ /  __/ /_/ / /_/  __/ /__
echo/_____/\___/\__, /\__/\___/\___/
echo           /____/
echo   Sovereign Agentic Coding Harness
echo.

set "BINARY=%~dp0codium-fork\vscodium-bin\deepgravity.exe"


powershell -ExecutionPolicy Bypass -File "%~dp0codium-fork\vscodium-bin\merge-exe.ps1" 2>&1 >nul

if not exist "%BINARY%" (
    echo ERROR: Editor binary not found at:
    echo %BINARY%
    echo.
    pause
    exit /b 1
)

rem --- Load configuration dynamically from config.json ---
set "PORT=19850"
set "HOST=127.0.0.1"
set "WORKSPACE=%~dp0"

if exist "config.json" (
    for /f "usebackq tokens=*" %%F in (`powershell -Command "$c = (Get-Content config.json -Raw | ConvertFrom-Json); if ($c.server.port) { $c.server.port }" 2^>nul`) do set "PORT=%%F"
    for /f "usebackq tokens=*" %%F in (`powershell -Command "$c = (Get-Content config.json -Raw | ConvertFrom-Json); if ($c.server.host) { $c.server.host }" 2^>nul`) do set "HOST=%%F"
    for /f "usebackq tokens=*" %%F in (`powershell -Command "$c = (Get-Content config.json -Raw | ConvertFrom-Json); if ($c.workspace.root_path) { $c.workspace.root_path } elseif ($c.editor.workspaceRoot) { $c.editor.workspaceRoot }" 2^>nul`) do set "WORKSPACE=%%F"
)

if "%HOST%"=="0.0.0.0" set "HOST=127.0.0.1"
set "DEEPGRAVITY_BACKEND_URL=http://%HOST%:%PORT%"

echo  Workspace:   %WORKSPACE%
echo  Extensions:  %~dp0extensions
echo.

rem Convert backslashes to forward slashes for folder URI
set "URI_PATH=%WORKSPACE:\=/%"
if "%URI_PATH:~0,1%"=="/" set "URI_PATH=%URI_PATH:~1%"

start "" "%BINARY%" ^
  --extensions-dir "%~dp0extensions" ^
  --folder-uri "file:///%URI_PATH%"

echo DeepGravity is starting...

