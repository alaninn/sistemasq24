# SISTEMASQ24 — Instrucciones del proyecto

## Regla de trabajo OBLIGATORIA en cada cambio
Cada vez que se modifica algo del sistema (código, fix, feature), SIEMPRE:
1. **Actualizar `CHANGELOG.md`** — agregar una entrada arriba con la fecha (AAAA-MM-DD) y qué
   cambió, para no perder información entre pruebas/sesiones.
2. **Commit** con mensaje claro en español.
3. **Push a GitHub**: `git push origin main` (repo: https://github.com/alaninn/sistemasq24).

El usuario borra y re-descarga la carpeta en su notebook para probar, así que **el repo
siempre debe tener la última versión funcional**.

## Qué NO se sube (ya en `.gitignore`)
- `vendor/**/ecu.zip` — la base de ECUs (142 MB); el usuario la carga a mano.
- `dist/` — el instalador (artefacto pesado).
- `.venv/`, `__pycache__/`, `log/` — entorno, cache y logs.

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
