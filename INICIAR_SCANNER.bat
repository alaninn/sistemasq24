@echo off
chcp 65001 >nul
title Scanner Megane II - F4R  (cerra esta ventana para detenerlo)

rem --- Limpia cualquier scanner viejo que haya quedado ocupando el puerto 8073 ---
powershell -NoProfile -Command ^
  "Get-NetTCPConnection -LocalPort 8073 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {} }" >nul 2>&1

rem --- Verifica/instala Python + dependencias y arranca (todo automatico) ---
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_y_correr.ps1"

echo.
echo   El scanner se detuvo.
pause
