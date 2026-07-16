@echo off
REM Scanner Mégane II Universal - Instalador
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ====================================================
echo   SCANNER MEGANE II UNIVERSAL - INSTALADOR v3.2
echo ====================================================
echo.

REM Detectar arquitectura
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    set ARCH=64-bit
) else (
    set ARCH=32-bit
)
echo [INFO] Sistema detectado: Windows %ARCH%

REM Detectar Python
echo [INFO] Buscando Python 3.8+...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python no encontrado en el sistema.
    echo Por favor instala Python 3.8+ desde: https://www.python.org/
    echo Asegúrate de marcar "Add Python to PATH" durante la instalación.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python %PYTHON_VERSION% encontrado

REM Definir ruta de instalación
set INSTALL_DIR=C:\megane2_scanner
if exist "%PROGRAMFILES(X86)%\nul" (
    set INSTALL_DIR=%PROGRAMFILES%\megane2_scanner
)

echo.
echo [INFO] Ruta de instalación: %INSTALL_DIR%

REM Crear directorio si no existe
if not exist "%INSTALL_DIR%" (
    echo [INFO] Creando directorio: %INSTALL_DIR%
    mkdir "%INSTALL_DIR%"
)

REM Buscar ZIP en el mismo directorio del script
set ZIP_FILE=%~dp0megane2_scanner_installer.zip
if not exist "%ZIP_FILE%" (
    echo [ERROR] No se encontró: %ZIP_FILE%
    echo Por favor coloca megane2_scanner_installer.zip en la misma carpeta que install.bat
    pause
    exit /b 1
)

REM Extraer ZIP
echo.
echo [INFO] Extrayendo archivos (esto puede tardar unos segundos)...
cd /d "%INSTALL_DIR%"
python -m zipfile -e "%ZIP_FILE%" .

if errorlevel 1 (
    echo [ERROR] Fallo al extraer. Intenta manualmente:
    echo   1. Abre %ZIP_FILE% con 7-Zip o WinRAR
    echo   2. Extrae a %INSTALL_DIR%
    pause
    exit /b 1
)
echo [OK] Archivos extraídos correctamente

REM Buscar carpeta megane2_f4r dentro del ZIP
if exist "%INSTALL_DIR%\megane2_f4r" (
    cd /d "%INSTALL_DIR%\megane2_f4r"
) else if exist "%INSTALL_DIR%\sistemasq24\megane2_f4r" (
    cd /d "%INSTALL_DIR%\sistemasq24\megane2_f4r"
) else (
    cd /d "%INSTALL_DIR%"
)

REM Crear acceso directo en Desktop
echo.
echo [INFO] Creando acceso directo en Desktop...
set DESKTOP=%USERPROFILE%\Desktop

REM Crear archivo VBS para el atajo (funciona mejor que mklink)
set VBS_FILE=%TEMP%\create_shortcut.vbs
(
    echo Set oWS = WScript.CreateObject("WScript.Shell"^)
    echo Set oLink = oWS.CreateShortcut("%DESKTOP%\Scanner Mégane II.lnk"^)
    echo oLink.TargetPath = "%~dp0INICIAR_SCANNER.bat"
    echo oLink.WorkingDirectory = "%CD%"
    echo oLink.Description = "Scanner OBD Mégane II Universal"
    echo oLink.IconLocation = "%CD%\app\web\favicon.ico", 0
    echo oLink.Save
) > "%VBS_FILE%"

if exist "%VBS_FILE%" (
    cscript.exe "%VBS_FILE%" //nologo
    del "%VBS_FILE%"
)

REM Ejecutar setup_y_correr.ps1
echo.
echo [INFO] Configurando entorno de Python...
if exist "setup_y_correr.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "setup_y_correr.ps1"
    if errorlevel 1 (
        echo [WARNING] Setup completó con código de error (esto puede ser normal)
    )
) else (
    echo [WARNING] No se encontró setup_y_correr.ps1
)

REM Crear log de instalación
echo. > "%INSTALL_DIR%\INSTALL_LOG.txt"
echo Scanner Mégane II Universal - Log de Instalación >> "%INSTALL_DIR%\INSTALL_LOG.txt"
echo Fecha: %date% %time% >> "%INSTALL_DIR%\INSTALL_LOG.txt"
echo Ruta: %INSTALL_DIR% >> "%INSTALL_DIR%\INSTALL_LOG.txt"
echo Python: %PYTHON_VERSION% >> "%INSTALL_DIR%\INSTALL_LOG.txt"

REM Resumen final
echo.
echo ====================================================
echo   ✅ INSTALACIÓN COMPLETADA EXITOSAMENTE
echo ====================================================
echo.
echo Próximos pasos:
echo   1. Conecta el adaptador ELM327 al OBD del auto
echo   2. Haz doble clic en "Scanner Mégane II" en tu Desktop
echo   3. Abre http://localhost:8000 en tu navegador
echo.
echo Ubicación de instalación:
echo   %INSTALL_DIR%
echo.
echo Para reiniciar el scanner en el futuro:
echo   Doble clic en INICIAR_SCANNER.bat
echo.
pause

REM Iniciar el scanner automáticamente (opcional - comentar si no quieres)
REM call "%INSTALL_DIR%\INICIAR_SCANNER.bat"

exit /b 0
