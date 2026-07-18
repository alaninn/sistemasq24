@echo off
chcp 65001 >nul
title Emulador ELM327 - probar el scanner sin auto

rem Emulador de ELM327 (Ircama/ELM327-emulator) en modo TCP, para probar el scanner
rem SIN un auto real. Simula un ELM327 y responde OBD-II estándar.

echo Instalando/actualizando el emulador ELM327 (necesita internet la primera vez)...
python -m pip install --quiet --upgrade ELM327-emulator 2>nul
if errorlevel 1 py -m pip install --quiet --upgrade ELM327-emulator

echo.
echo ================================================================
echo   EMULADOR ELM327 escuchando en:  socket://localhost:35000
echo.
echo   En el scanner: elegi "Conectar al auto", en el puerto elegi
echo   "Escribir puerto manual" y escribi:
echo        socket://localhost:35000
echo.
echo   (cerra esta ventana o Ctrl+C para detener el emulador)
echo ================================================================
echo.

python -m elm -n 35000 2>nul
if errorlevel 1 py -m elm -n 35000

pause
