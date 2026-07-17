# SISTEMASQ24 — Instrucciones del proyecto

## Regla de trabajo OBLIGATORIA en cada cambio
Cada vez que se modifica algo del sistema (código, fix, feature), SIEMPRE:
1. **Actualizar `CHANGELOG.md`** — agregar una entrada arriba con la fecha (AAAA-MM-DD) y qué
   cambió, para no perder información entre pruebas/sesiones.
2. **Commit** con mensaje claro en español.
3. **Push a GitHub**: `git push origin main` (repo: https://github.com/alaninn/sistemasq24).

El usuario borra y re-descarga la carpeta en su notebook para probar, así que **el repo
siempre debe tener la última versión funcional**.

## Flujo de logs (IMPORTANTE)
El usuario prueba en la notebook (en el auto), y con el botón **"☁ Subir logs"** sube los
logs a GitHub (endpoint `POST /api/logs/subir` → los copia a `debug-logs/` y hace commit +
push a `main`). Después vuelve y me dice **"revisá los logs desde acá"**: eso significa que
yo debo hacer `git pull` y **leer los archivos de `debug-logs/`** (los `sesion_*.txt`) para
depurar. Esto es **temporal** (solo mientras debuggeamos); después se saca el push automático
y quedan solo en una carpeta local `log/`.

## Qué NO se sube (ya en `.gitignore`)
- `dist/` — el instalador (artefacto pesado).
- `.venv/`, `__pycache__/`, `log/` — entorno, cache y logs de sesión locales.
- `ecu.zip` NO se sube entero (142 MB > límite de GitHub); se sube **partido** en
  `vendor/sistemasq24/ecu.zip.part*` (cada parte <100 MB) y `run.py` lo re-arma solo al
  arrancar si falta. `debug-logs/` SÍ se sube (logs de prueba para revisar).

## Arquitectura (resumen)
- **Backend**: `app/server.py` (FastAPI + WebSocket), `app/ecu_registry.py` (perfiles de ECU
  y traducción), `app/sq24_scanner.py` (autodetección). Motor de comunicación reutilizado en
  `vendor/sistemasq24/core/` (base de ddt4all, GPL-3.0, rebrandeado).
- **Frontend**: `app/web/index.html` (todo en un archivo, offline) + `app/web/chart.umd.js`.
- **Perfiles**: `ninguno` (sin auto) → `f4r` (Mégane II curado, usa `original/` + `es/`) o
  `detectado` (otros autos, cargados del `ecu.zip`).
- **Arrancar/probar en simulación**: `options.simulation_mode = True`, luego levantar
  `server:app` con uvicorn. Verificar el JS con `node --check`.

## Verificación mínima antes de pushear
- `node --check` del script grande de `index.html` (sin errores de sintaxis).
- Importar `server` en modo simulación sin errores.
- El F4R curado sigue funcionando (6 ECUs, 11 procedimientos).
