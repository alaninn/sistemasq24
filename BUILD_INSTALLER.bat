@echo off
REM Script para generar el instalador comprimido

setlocal enabledelayedexpansion

echo.
echo ====================================================
echo   GENERADOR DE INSTALADOR - Scanner Mégane II
echo ====================================================
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado
    echo Por favor instala Python 3.8+ antes de continuar
    pause
    exit /b 1
)

echo [INFO] Ejecutando create_installer.py...
echo.

python create_installer.py

if errorlevel 1 (
    echo.
    echo [ERROR] Fallo al crear el instalador
    pause
    exit /b 1
)

echo.
echo ====================================================
echo   ✅ INSTALADOR CREADO EXITOSAMENTE
echo ====================================================
echo.
echo Los archivos están listos en la carpeta: dist/
echo.
echo Para instalar en otra computadora:
echo   1. Copia la carpeta "dist" completa
echo   2. Haz doble clic en install.bat
echo   3. ¡Listo!
echo.
pause
