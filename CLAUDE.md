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
- **Setup del token (una vez por notebook):** ya NO hace falta crear el archivo a mano. Si la
  subida falla, la app abre un diálogo con dos salidas:
  1. **📦 Bajar logs en ZIP** (`GET /api/logs/descargar`) — funciona SIEMPRE (sin token, sin
     git, sin internet). Es la vía rápida para que el usuario mande los logs por otro medio.
  2. **🔑 Pegar un token** (`POST /api/logs/token`) — se valida contra la API (que exista y
     tenga permiso de push) y se guarda en `github_token.txt` (gitignoreado). De ahí en
     adelante la notebook sube sola.
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
- `app/dtc_db.py` + `app/dtc_generico.json` — `describir(codigo)` resuelve por calidad:
  (1) ~107 curados a mano en español perfecto, (2) base completa de ~9.400 códigos (SAE J2012,
  de Wal33D/dtc-database MIT) traducida por un **traductor de términos** EN→ES (`_TERMINOS`),
  (3) fallback por familia → letra. La usan el modo OBD-II genérico y, como fallback, el
  F4R/enhanced. Para mejorar una traducción fea, agregá el término a `_TERMINOS` (frases largas
  primero). `es_conocido(codigo)` dice si está en la base (no solo fallback).

## OBD-II genérico — features estándar (SAE J1979)
- `app/obd_generico.py`: Modo 01 (sensores), 02 (**freeze frame** `leer_freeze_frame`),
  03/07 (DTC), 04 (borrar), 09 (**VIN**). `leer_readiness()` = monitores de emisiones + MIL.
  `decodificar_vin()` = fabricante/región/año **offline** (tabla WMI ISO 3779). Endpoints
  `/api/obd/{freeze-frame,readiness,vin}`. Botones en el panel del modo genérico.

## Roadmap pendiente (de la investigación en GitHub, jul-2026)
Ver el CHANGELOG para lo YA hecho (DTC 9.5k, freeze frame, readiness, VIN, record/replay).
Queda pendiente, por orden de valor:
- **ecu.zip oct-2022 (~3086 ECUs vs. 1973)**: única mejora de datos grande, mismo formato
  GPL-3.0, +~1100 autos (Dacia/Clio/Captur/Zoe 2020-22). Links oficiales caídos → hay que
  conseguir el mirror comunitario (discusiones de cedricp/ddt4all). Cuando se tenga el archivo:
  `python tools/importar_ecu_zip.py RUTA_al_nuevo_ecu.zip` (valida, re-parte y deja listo para
  commitear). Post-2022 Renault cerró DDT2000: no hay base pública más nueva.
- **DTCs por UDS servicio 19** (estados presente/pendiente/histórico) con la lógica de
  `pylessard/python-udsoncan` (MIT) — para F4R y ECUs modernas.
- **Sniffing pasivo de CAN** con `cantools` + DBCs de Renault/Nissan (leer sensores sin
  diagnóstico). Requiere adaptador CAN nativo (SLCAN/SocketCAN), no solo ELM327.
- **Security access seed-key de Renault** (rutinas/actuadores protegidos) — lo más difícil,
  necesita el algoritmo específico. Ref: CaringCaribou, ludwig-v/psa-seedkey-algorithm.
- Rebasar mejoras de protocolo/adaptadores del upstream `cedricp/ddt4all` (Vlinker, VGate,
  OBDLink SX, ELS27).

## Verificación mínima antes de pushear
- `node --check` del script grande de `index.html` (sin errores de sintaxis).
- Importar `server` en modo simulación sin errores.
- El F4R curado sigue funcionando (6 ECUs, 11 procedimientos).
