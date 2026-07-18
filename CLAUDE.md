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
logs a GitHub, a la carpeta `debug-logs/`. El endpoint `POST /api/logs/subir` sube por la
**API de GitHub con un token** (`github_token.txt` en la raíz, o env `GITHUB_TOKEN`) — así
funciona **sin git ni .git** en la notebook (que bajó el ZIP). Si no hay token, cae al git
CLI (solo sirve en una PC con el repo clonado + credenciales).
- **Setup del token (una vez por notebook):** crear un Personal Access Token en GitHub con
  permiso de escritura de contenido del repo, y guardarlo en `megane2_f4r/github_token.txt`.
  Ese archivo está gitignoreado (nunca se sube).
Cuando el usuario dice **"revisá los logs desde acá"**: hago `git pull` y **leo los
`sesion_*.txt` de `debug-logs/`** (tienen fecha en el nombre) para depurar. Es **temporal**;
después se saca y quedan solo en `log/` local.

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

## Probar SIN auto real (emulador ELM327)
- `tools/emulador_elm.bat` levanta el emulador ELM327 (paquete `ELM327-emulator`) en modo TCP
  en `socket://localhost:35000`. En el scanner: "Conectar al auto" → puerto → "Escribir puerto
  manual" → `socket://localhost:35000`. Sirve para probar el modo OBD-II genérico y el flujo
  real sin hardware.
- La conexión ahora acepta puertos tipo URL (`socket://…`), lo que también habilita
  **adaptadores ELM327 WiFi** (`socket://192.168.0.10:35000`), no solo USB.
- Para probar SOLO la lógica del software sin ELM, sigue estando `options.simulation_mode`.

## Base de descripciones de DTC
- `app/dtc_db.py` — descripciones en español de los DTC genéricos (SAE J2012) curadas a mano.
  `describir(codigo)` da match exacto → familia → letra. La usan el modo OBD-II genérico y,
  como fallback, la lectura de DTC del F4R/enhanced cuando la ECU no trae descripción.

## Verificación mínima antes de pushear
- `node --check` del script grande de `index.html` (sin errores de sintaxis).
- Importar `server` en modo simulación sin errores.
- El F4R curado sigue funcionando (6 ECUs, 11 procedimientos).
