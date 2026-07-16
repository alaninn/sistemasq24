@echo off
REM Lanza el CLI de debug interactivo
REM Asume que el venv está en ..\.venv

setlocal enabledelayedexpansion

REM Detectar venv
set VENV_PATH=..\\.venv\Scripts\python.exe

if not exist "%VENV_PATH%" (
    echo [ERROR] Virtual env not found at %VENV_PATH%
    echo Run INICIAR_SCANNER.bat first to set up the environment.
    pause
    exit /b 1
)

echo ╔════════════════════════════════════════════════════════════╗
echo ║   DEBUG CLI - Acceso directo al auto                       ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"
"%VENV_PATH%" -m debug_cli.cli

pause
