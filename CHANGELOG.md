# Changelog — SISTEMASQ24

Todos los cambios importantes del scanner se anotan acá. El más reciente arriba.
Formato de fecha: AAAA-MM-DD.

Repo: https://github.com/alaninn/sistemasq24

---

## [2026-07-19] — Analizador de ondas: grabar y REPRODUCIR sesiones (record/replay)

Roadmap de investigación en GitHub, punto #5 (idea de AndrOBD). El export CSV ya existía
(tablero y ondas); lo nuevo es el **replay visual**:
- **`app/web/index.html`** — botones **💾 Guardar** y **📂 Reproducir** en el analizador de
  ondas. "Guardar" vuelca los buffers + metadata (etiquetas/unidades) a un `.json`;
  "Reproducir" abre esa grabación, inyecta la metadata (aunque sea de otro auto), carga las
  ondas y las muestra con zoom para revisarlas **sin el auto**. Banner de replay + salir.
  Iniciar captura en vivo sale del replay automáticamente.

## [2026-07-19] — OBD-II genérico: Freeze Frame + Monitores (readiness) + VIN decodificado offline

Roadmap de investigación en GitHub, puntos #3 y #4 (features nuevas del scanner genérico).
- **Freeze Frame (Modo 02)** — `obd_generico.leer_freeze_frame()`: lee el DTC que disparó la
  falla y la **foto de los sensores en ese instante** (RPM, carga, temp, MAP, fuel trims,
  velocidad, etc.). Es lo más pedido en un scan y no lo teníamos.
- **Monitores de emisiones / readiness (Modo 01 PID 01)** — `leer_readiness()`: estado del
  testigo **MIL**, nº de DTC confirmados, y los monitores continuos/no-continuos con
  "Listo/Incompleto" (sirve para saber si el auto pasaría una VTV de emisiones).
- **Decodificador de VIN offline (ISO 3779/3780)** — `decodificar_vin()`: del VIN saca
  **fabricante (tabla WMI, foco Alianza + comunes), región y año de modelo**, 100% sin
  internet. Endpoint que además lee el VIN por Modo 09.
- **`app/server.py`** — endpoints `/api/obd/{freeze-frame,readiness,vin}`.
- **`app/web/index.html`** — 3 botones nuevos en el panel del modo genérico (📸 Freeze Frame,
  ✅ Monitores, 🔎 VIN decodificado) con sus modales.
- Verificado en simulación: freeze frame (13 sensores + P0133), readiness (MIL + monitores),
  VIN (Renault/Dacia/Nissan bien decodificados). `node --check` OK, `import server` OK.

## [2026-07-19] — Base de DTC genéricos ampliada 107 → ~9.500 (SAE J2012 completa, en español)

Roadmap de investigación en GitHub, punto #1 y #2 (DTCs).
- **`app/dtc_generico.json`** (NUEVO) — base completa de **9.415 códigos** OBD-II genéricos
  (P/B/C/U) importada de `Wal33D/dtc-database` (MIT, verificada: P0300/P0420/P0171 correctos).
- **`app/dtc_db.py`** — `describir()` ahora resuelve por calidad: (1) los **107 curados a mano**
  en español perfecto (los de taller), (2) la base completa **traducida al español por un
  traductor de términos** del vocabulario OBD (muy formulaico: circuit→circuito, bank→banco,
  range/performance→rango/rendimiento, misfire→fallo de encendido, etc.), (3) fallback por
  familia → letra. Nuevo `es_conocido(codigo)`.
  - Honestidad: los códigos comunes quedan en español perfecto; la cola larga (~9.400) queda
    en español entendible pero no siempre perfectamente gramatical (traducción automática por
    términos). Es un salto enorme de cobertura sin depender de datasets mal alineados.
- **DTCs propietarios Renault (#2) — hallazgo:** NO existe una tabla plana `P1xxx→texto` que
  extraer del `ecu.zip`. En las ECU Renault las fallas propietarias son **flags de 1 bit con
  nombre** (dataitem `{0:OK, 1:Panne}`, ej. "Panne présente Piste 1 potentiomètre pédale…"):
  la descripción ya está en el nombre y se muestra al leer ese request (y el F4R tiene su
  traducción curada en `es/`). Los pocos propietarios en formato estándar (59 códigos B1/C1)
  ya quedaron cubiertos por la base genérica. No se fabricó una tabla falsa.

## [2026-07-19] — NUEVO módulo: Ensayo de Aceleración (motor EN MOVIMIENTO, ~50/100 m)

Módulo hermano del Chequeo General, pero al revés: en vez de medir el auto DETENIDO subiendo
RPM en el lugar, mide el motor EN CARGA durante un tramo corto de aceleración. En movimiento
aparecen cosas que parado no se ven: enriquecimiento en carga, respuesta de la mariposa,
avance y boost bajo demanda, y los fuel trims reales.
- **`app/ensayo.py`** (NUEVO) — máquina de estados en background (reutiliza `ctx` y
  `estadisticas_de_muestras` de `chequeo.py`). Fases:
  1. **espera_arranque**: muestra velocidad/RPM en vivo y espera a que el auto se mueva
     (velocidad > 4 km/h sostenida) o a que el usuario fuerce el inicio.
  2. **grabando**: captura TODOS los sensores clave del motor a alta frecuencia (200 ms)
     mientras se acelera, **integrando la velocidad para estimar la distancia** recorrida.
     Corta al llegar a la distancia objetivo, al levantar el pie (desaceleración < 60% del
     pico), por timeout de seguridad (45 s) o manualmente.
  3. **reporte**: serie temporal + estadísticas por sensor + métricas derivadas
     (vel/RPM máx, tiempos 0→40/60/80/100 km/h, boost/MAP/avance/mariposa/fuel-trim máx).
- **`app/reporte.py`** — `generar_ensayo(datos)` (HTML/JSON/TXT, prefijo `ensayo_<fecha>`):
  tarjetas resumen, destacados bajo carga, stats por sensor y tabla temporal muestreada.
  Sin flags de rango (los rangos de ralentí no aplican en carga; van crudos para interpretar
  una persona o IA).
- **`app/server.py`** — `estado.ensayo` + `_CtxEnsayo` + `_run_ensayo`; endpoints
  `/api/ensayo/{iniciar,estado,ahora,cancelar,reporte/{tipo}}` (`iniciar` acepta `distancia`,
  50 o 100 m; `ahora` fuerza arranque o fin). Se aborta al desconectar y los `ensayo_*` se
  suben con "Subir a GitHub".
- **`app/web/index.html`** — vista `view-ensayo` (elegir 50/100 m, gauges de velocidad/RPM/
  distancia en vivo, barra de progreso del tramo, botones arrancar/terminar-ahora) + entrada
  de menú. Con aviso de seguridad (lugar habilitado, no vía pública).
- Verificado end-to-end en simulación (rampa de velocidad canned): flujo completo por los
  endpoints reales (iniciando→espera→grabando→reporte) y descarga de los 3 archivos. `node
  --check` OK, `import server` OK.

## [2026-07-19] — Curaduría de sensores en vivo del F4R: iguala y supera al OBD-II genérico

- **Problema:** el tablero en vivo del F4R mostraba MENOS que el modo OBD-II genérico
  (faltaban ajuste corto/largo de combustible y posición del acelerador), aunque la ECU
  tiene 521 parámetros legibles. Era un problema de curaduría de las listas destacadas.
- **`app/web/index.html`** — se reescribieron las dos listas (por `dato` original francés,
  verificadas 1:1 contra `motor.readable_params()`):
  - `SENSORES_RELEVANTES`: ampliada a **91 datos** curados (todos los equivalentes de los
    PIDs del genérico + extras del F4R: cliquetis/knock, VVT, adaptativos de riqueza por
    zona de presión, sondas amont/aval, ralentí, turbo/wastegate, potenciómetros de
    mariposa/pedal, par motor). Solo sensores observables; se descartan códigos/flags.
  - `SENSORES_PRECARGADOS`: **16 datos** por defecto. Ahora incluye sí o sí el ajuste de
    combustible corto (`Facteur enrichissement regulation richesse`) y largo
    (`Correction adaptative de la 1ère zone de pression`) y la posición de mariposa/pedal,
    que antes no aparecían.
- Verificado: 91/91 y 16/16 datos matchean parámetros reales; `node --check` del script OK.

## [2026-07-19] — FIX CRÍTICO autodetección: fallback KWP-sobre-CAN (F4R, Kangoo 2…)

- **Por qué no detectaba nada** (ni el F4R ni la Kangoo): el escáner solo probaba **UDS**
  (sesión 1003 + `22F1Ax`), que usan los Renault NUEVOS. Los Renault VIEJOS (F4R, Kangoo 2,
  etc.) tienen CAN pero hablan **KWP-sobre-CAN** ("Diag on CAN": sesión `10C0` + lectura
  `21 80`), y no responden a UDS → la detección probaba las 121 direcciones y no matcheaba
  ninguna.
- **Fix**: portado el `identify_old` de ddt4all. Ahora en cada dirección CAN, si UDS no
  responde, prueba KWP-sobre-CAN (`10C0` + `2180`) como fallback. Validado en simulación:
  matcheó ECUs reales X84/Mégane II (`S3000_...X84` motor, `Tdb_J84` tablero) que la vía UDS
  nunca encontraba. Las 6 ECUs CAN del F4R están en la tabla de direcciones, así que en el
  auto real ahora deberían detectarse.
- Parser de identificación `21 80` extraído a `_parse_ident_2180` (compartido K-line y CAN).

---

## [2026-07-19] — Chequeo General del Auto (reporte exhaustivo con captura por RPM)

Nueva función completa (etapas 1-4): un **chequeo guiado** que arma un reporte exhaustivo.
- **Paneo** de todas las ECUs del perfil activo: identificación + una lectura de cada sensor
  + códigos de falla (con descripción vía `dtc_db`).
- **Captura por RPM automática**: pide llevar el motor a ralentí / 1500 / 2000 / 3000 RPM;
  detecta cuando entra y se estabiliza en cada banda (±200 rpm, ~2.5s) y captura solo los
  sensores del motor. Botón "capturar ahora" de fallback + medidor de RPM en vivo con color.
- **Reporte en 3 formatos** (`log/reporte_<fecha>.html/json/txt`): HTML para leer, JSON/TXT
  para pegarle a una IA. Evalúa los sensores clave del F4R contra `rangos_f4r.json`
  (OK/atención/fuera), arma resumen (sensores OK, en atención, DTCs) y la evolución de cada
  sensor del motor a través de las RPM.
- Archivos: `app/chequeo.py` (orquestador, máquina de estados + `estadisticas_de_muestras`
  reutilizable), `app/reporte.py` (generador), `app/rangos_f4r.json` (rangos curados).
  Endpoints `/api/chequeo/{iniciar,estado,capturar-ahora,cancelar,reporte/{tipo}}`. Vista
  `view-chequeo` (asistente paso a paso) + entrada de menú. El botón "Subir a GitHub" ahora
  también sube los reportes del chequeo.
- Verificado end-to-end en simulación (flujo completo + los 3 archivos + descarga por HTTP).
  Los VALORES de sensores se llenan en el auto real (en simulación salen vacíos, es esperado).

---

## [2026-07-18] — Autodetección KWP2000 (módulos viejos, no solo CAN)

- El escáner ahora también sondea protocolo **KWP2000** (26 direcciones únicas, 198 ECUs
  de la base) además de CAN, cubriendo módulos más viejos de un solo hilo (ABS/airbag de
  generaciones anteriores, comunes en autos como la Kangoo 2). Portado fielmente de
  `scan_kwp`/`check_ecu` de ddt4all: sesión `10C0` + lectura de identificación (servicio 21,
  LID 0x80) por dirección, con la misma conversión de bytes que ddt4all.
- A diferencia de CAN, la dirección corta de `db.json` **es** la dirección KWP real (no
  necesita traducción vía `dnat`), así que no hizo falta un archivo de direcciones aparte.
- Validado con datos de simulación portados de ddt4all: matcheó una ECU **real** de la base
  (`EDC_15C_C..._IMA_evol1.json`, motor) que antes no se detectaba — confirma que la
  codificación decimal de `diagversion` es consistente con cómo está guardado `db.json`.
- Progreso combinado (CAN primero, después KWP) en la misma barra.
- **Pendiente (bajo impacto):** protocolo ISO8 — solo 21 ECUs (~1% de la base), autos muy
  viejos pre-CAN. Se deja para más adelante.

### Fix (agente de revisión encontró 2 bugs invisibles en simulación, reales en auto)
- **Caché de `elm.request` por comando, no por dirección**: el sondeo KWP usaba
  `cache=True` con el mismo comando `"2180"` para todas las direcciones → en el auto real,
  después de la primera ECU que respondiera, **todas las siguientes habrían recibido la
  misma respuesta cacheada** (misidentificación total del resto). Fix: `cache=False` +
  `elm.clear_cache()` antes de cada sondeo (igual que ya hacía el path CAN).
- **Faltaba `options.opt_si = True`**: sin ese flag, `set_iso_addr` salta el slow-init
  (5 baudios) y usa fast-init por defecto — las ECU KWP2000 monopoint viejas (el target
  de esta feature) probablemente no habrían direccionado en el auto real. Agregado.
- Ajustado el cálculo de `total` del progreso si `init_iso()` falla (evita que la barra
  quede trabada por debajo del 100%). Limpieza de una variable muerta.

---

## [2026-07-18] — Subir logs por API de GitHub (funciona desde la notebook)

- La subida de logs fallaba en la notebook porque el git CLI necesita `.git` + credenciales
  (la notebook bajó el ZIP, no un clone). Ahora `POST /api/logs/subir` sube por la **API de
  GitHub con un token** (`github_token.txt` o env `GITHUB_TOKEN`) → funciona sin git. Si no
  hay token, cae al git CLI (esta PC) con mensaje claro. `github_token.txt` está gitignoreado.
- Revisión de logs del 17/07 (notebook "omar", COM3): actuadores **funcionan** (respuestas
  positivas `70 02 01` con el fix de tempON), OBD genérico **funciona** (39 PIDs, DTC real
  P0301), autodetección fallaba (confirma el bug de direccionamiento CAN ya corregido).

---

## [2026-07-18] — FIX autodetección (direccionamiento CAN) + menú por perfil

### Autodetección: ahora SÍ encuentra otros autos (ej. Kangoo 2)
- **Bug raíz**: el escáner direccionaba por las direcciones cortas de `db.json`, que
  necesitan la tabla `dnat`/`snat` para mapear a IDs CAN — y esa tabla está **VACÍA** en el
  código. Resultado: `TXa='undefined'` → no direccionaba NINGUNA ECU en el auto real (en
  simulación andaba por respuestas canned). Por eso no detectaba la Kangoo (ni nada).
- **Fix**: se sondean los **121 pares CAN reales** (`send_id`/`recv_id`) de todas las ECUs de
  la base (precomputados en `app/direcciones_can.json`), pasando los IDs directos a
  `set_can_addr` (igual que hace el F4R). Ahora detecta los módulos CAN de cualquier auto de
  la base (motor, ABS, clima, dirección, airbag…). *Pendiente: KWP2000/ISO (198+21 ECUs)
  para módulos viejos que no son CAN.*

### Menú lateral por perfil
- El menú ya no muestra opciones que no aplican al auto activo: **Procedimientos** y
  **Memoria** solo en F4R; **Actuadores/Módulos/Escanear** en F4R y detectado; en **OBD
  genérico** solo lo que tiene sentido (Tablero, Ondas, DTC, Sensores, etc.).

---

## [2026-07-18] — Descripciones de DTC + soporte WiFi/emulador (investigación GitHub)

### Descripciones de códigos de falla (DTC)
- Nuevo `app/dtc_db.py`: descripciones **en español** de los DTC genéricos (SAE J2012),
  **curadas a mano y verificadas** (107 códigos comunes + fallback por familia/letra). Se
  descartaron las bases scrapeadas de GitHub (ej. mytrile) porque tenían descripciones
  **incorrectas** (P0300, P0420, P0133… mal). Ahora el modo OBD-II genérico muestra qué
  significa cada código, y el F4R/enhanced la usa como fallback.

### Adaptadores WiFi + emulador para probar sin auto
- La conexión ahora acepta puertos tipo URL (`socket://…`): habilita **adaptadores ELM327
  WiFi** (`socket://ip:puerto`) además de USB. En el gate hay opción de "puerto manual".
- `tools/emulador_elm.bat`: levanta el emulador ELM327 (paquete `ELM327-emulator`) en TCP
  (`socket://localhost:35000`) para **probar el scanner sin hardware** (útil para debug del
  modo genérico). Doc en CLAUDE.md.

### Investigación (repos GitHub útiles)
- Revisado `iDoka/awesome-canbus` + búsqueda de bases OBD-II. Referencias anotadas para más
  adelante: `renault/cananalyze` (oficial Renault), `pylessard/python-udsoncan`, `OBDb`.

---

## [2026-07-17] — Scanner OBD-II GENÉRICO (funciona en cualquier auto)

### Nuevo módulo: OBD-II genérico (`app/obd_generico.py`)
- Lee **cualquier auto** por el estándar mundial SAE J1979 (como ScanMaster/Torque), **sin
  necesitar el ecu.zip**: sensores estándar del Modo 01 (RPM, temps, MAP, MAF, sonda lambda,
  velocidad, batería, avance, mariposa…), **DTC** genéricos (Modo 03/07 + borrar 04), y **VIN**
  (Modo 09). Escanea qué PIDs soporta el auto (Modo 01 PID 00/20/40).
- Se integra como un **perfil más** del registry (`generico`), imitando la interfaz de
  `TranslatedECU`, así el **tablero en vivo, el analizador de ondas y la lectura de DTC ya
  existentes funcionan sin duplicar nada**.
- Dirección funcional de broadcast OBD `7DF`.
- Frontend: la vista **Scanner Universal** ahora ofrece 2 vías — "Genérico OBD-II" (cualquier
  marca) y "Detección Renault completa" (todos los módulos vía ecu.zip). Endpoint
  `POST /api/obd/conectar`.

---

## [2026-07-17] — Actuadores, analizador de ondas pro, auto-guardado y subida de logs

### Actuadores — AHORA ENCIENDEN
- Bug encontrado: el comando de servicio 30 mandaba `Output Control.tempON` en **0**, así
  que la ECU aceptaba el comando pero la salida no se energizaba. Ese byte (que enciende/
  mantiene la salida) es un dato "scaled" → se pasa en **decimal**. Ahora se manda `255`
  (`30 05 00 FF` para el A/C). Stop = `30 05 11 00`.
- **Keep-alive**: los actuadores encendidos se re-envían periódicamente (el "Start
  Temporary" expira solo), así la salida se mantiene activa hasta apagarla. Se corta al
  apagar o desconectar.

### Analizador de ondas — mejoras
- **Zoom** con la rueda del mouse + desplazar arrastrando (plugin `chartjs-plugin-zoom`
  vendorizado local, offline) + botón "Reset zoom".
- **Números más grandes** en ejes y leyenda.
- **Estadísticas por gráfico** (ya no se mezclan): en modo separado van en cada tarjeta;
  en modo solapado, tabla compacta por sensor (Actual/Min/Max/Prom/Hz).
- **Pantalla completa** y modos "separado" (de a uno) / "solapado" (unidos).

### Logs
- **Auto-guardado**: la grabación se vuelca a disco cada ~3 s, así aunque se cierre el
  navegador sin tocar "Finalizar" **no se pierde nada**.
- **Botón "☁ Subir logs"** + endpoint `POST /api/logs/subir`: copia los logs a
  `debug-logs/` y los sube a GitHub (temporal, para debug). Ver "flujo de logs" en CLAUDE.md.

### GitHub
- **ecu.zip subido partido** (`vendor/sistemasq24/ecu.zip.part00/01`, <100 MB c/u); `run.py`
  lo re-arma solo al arrancar. Así queda guardado y descargable sin superar el límite de
  GitHub.

---

## [2026-07-16] — Primera versión funcional en GitHub

### Arquitectura: scanner adaptativo por vehículo
- **Perfiles de ECU**: el sistema arranca **sin auto** (`perfil = ninguno`). Se carga un
  auto al **seleccionar Mégane II F4R** (perfil curado 100%) o al **autodetectar** otro
  vehículo (perfil detectado desde el `ecu.zip`).
- **Autodetección real** (`app/sq24_scanner.py`, nuevo): recorre las direcciones CAN del
  auto, lee la identificación UDS (`22F1A0/18A/194/195`) y matchea contra el índice
  `db.json` del `ecu.zip` (+1900 ECUs) para elegir la definición exacta. Con **barra de
  progreso** en tiempo real y timeout corto por dirección (rápido).
- **Retirado** el `ecu_loader.py` viejo (roto/huérfano).

### Rebrand
- Paquete `ddt4all` → `sistemasq24` (carpeta `vendor/` + todos los imports + app + run.py).

### Navegación
- **Sin auto cargado**: cada tarjeta del gateway abre su vista con el menú lateral enfocado
  (solo esa opción). **Con auto cargado**: aparece el menú de diagnóstico completo.
- **Seleccionar Vehículo**: solo Mégane II F4R está disponible; el resto figura como
  "Próximamente". Los demás autos entran por autodetección.
- **Desconectar** ahora limpia el perfil (vuelve a "sin auto").

### Sensores en tiempo real (tablero + analizador)
- La lista de sensores del F4R ahora son los **estándar de las Tramas 1–5** del motor
  (RPM, temp agua/aire, MAP, presión atmosférica, batería, velocidad, presión turbo,
  avance, mariposa, pedal, sondas lambda, tiempo de inyección, correcciones adaptativas…).
  Se acabaron los códigos internos sin sentido. Filtro "útiles" (con unidad/enum) para
  autos detectados.

### Analizador de Ondas
- **Chart.js vendorizado local** (`app/web/chart.umd.js`) → funciona **sin internet**.
- Corregido el bug que no dibujaba las ondas (`type:'scatter'` necesitaba `showLine:true`).
- **Buscador** de sensores, hasta 6 sensores, modo **solapado** (1 gráfico) o **separado**
  (grilla de gráficos). Exporta CSV.

### Correcciones de bugs (auditoría con agentes + revisión de ddt4all)
- **`ST.conectado` nunca se seteaba** → la autodetección nunca corría desde la UI. Corregido.
- **`dtcBadge` inexistente** → la lectura/borrado de DTC lanzaba error falso. Corregido.
- **Borrar DTC (servicio 14) mal clasificado como "solo lectura"** → ahora es peligroso
  (requiere modo avanzado); `SAFE_SERVICES` explícito, no reusa `options.safe_commands`.
- **Actuadores**: corregido el `KeyError '74D'` en el ELM (accesos `dnat[...]` sin guardia)
  que tapaba la respuesta real; `activate_actuator` ahora reporta el **código NRC** con su
  motivo (condiciones no correctas, valor fuera de rango, etc.).
- Endurecido el sondeo del escáner (rechaza respuestas negativas antes de parsear),
  quitado `init_can()` redundante, tester-present usa `3E00` (estándar UDS).

### Deploy
- Subido a GitHub sin `ecu.zip` (se carga a mano), sin instalador y sin `.venv`.
  `.gitignore` configurado. README (`LEEME.md`) con instrucciones de descarga-y-uso.
