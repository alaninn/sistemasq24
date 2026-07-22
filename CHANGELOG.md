# Changelog — SISTEMASQ24

Todos los cambios importantes del scanner se anotan acá. El más reciente arriba.
Formato de fecha: AAAA-MM-DD.

Repo: https://github.com/alaninn/sistemasq24

---

## [2026-07-22] — Los fuel trim OBD ahora SÍ se actualizan en el tablero en vivo (ECUs secundarias)

- Problema: en el tablero en vivo del F4R, los sensores del motor F4R se actualizaban pero los
  que agregamos por OBD (ajuste corto/largo, lazo) quedaban **congelados**. Causa: el WebSocket
  leía **una sola ECU** (la del motor, que tiene más sensores); rotar entre ECUs se había
  evitado porque reabría sesión CAN en cada refresco.
- Fix: la suscripción ahora manda una ECU **primaria** (se lee en cada ciclo, 0.15s) y las
  **secundarias** en `extra` (`index.html` `subscribeLive`). El backend (`server.py`, WS) lee
  las secundarias **cada ~2s** y cachea el último valor, mezclándolo en cada refresco. Los fuel
  trim (que cambian lento) se actualizan sin la penalidad de reabrir sesión en cada ciclo.

## [2026-07-22] — El chequeo F4R lee las RPM por OBD 010C (arranca de verdad) + fin del flood de puerto muerto

**1) El chequeo F4R ahora SÍ lee las RPM** (`chequeo.py`):
- Problema real en el auto: el régimen del F4R está en una respuesta **multiframe** (21A0…) que
  falla el flow-control a 38400 (`received first frame only — FC failed`), así que el chequeo
  nunca leía las RPM y las etapas de aceleración no arrancaban.
- Fix: el chequeo lee las RPM por el **PID OBD-II estándar 010C**, que es una respuesta de UN
  frame (sin flow-control) y funciona aunque el enhanced del F4R falle. Usa la ECU virtual
  'obd' que ya está en el perfil F4R. `_leer_rpm` prueba OBD 010C primero y cae al régimen
  enhanced. Además, cada captura de etapa registra las RPM por OBD, así el reporte tiene el
  régimen aunque los reads del F4R fallen.

**2) Fin del flood de log cuando se desconecta el cable** (`port.py`):
- Al desenchufar el cable, cada lectura fallaba con `PermissionError/ClearCommError` y se
  imprimían **decenas de miles de líneas idénticas** (un log llegó a 2.4 MB), porque `expect()`
  seguía girando 5 s por comando y `read_byte` avisaba en cada intento.
- Fix: bandera `_port_dead` — se avisa UNA sola vez y `expect()` abandona enseguida en vez de
  girar hasta el timeout. Se limpia al reabrir el puerto (reconexión OK).

## [2026-07-21] — Grabar sesión: solo sensores, NUNCA DTCs (que pueden tildar la ECU)

- El barrido de sensores de la grabación (`_sweep_sensores_sesion`) lee **solo sensores**
  (`readable_params → read_request`) y **nunca DTCs**: leer códigos de falla en algunas ECUs
  (servicio 19/17 multiframe) puede dejar el módulo "tildado". Se dejó explícito en el código
  para que no se agregue por error. Los DTC se leen **únicamente** cuando el usuario los pide
  desde la pantalla de códigos (entrar a la pantalla no lee nada; hay que tocar el botón).
- Además, la lectura de DTC (`/api/dtc/leer`) ahora toma el lock del adaptador **por ECU** en
  vez de en un solo bloque para las 6: si un módulo tarda o se cuelga, solo retiene el
  adaptador durante SU lectura (acotada por el timeout), y las lecturas en vivo / el barrido de
  sesión pueden intercalarse — no se congela todo el sistema.

## [2026-07-21] — Grabar sesión captura TODOS los sensores + reporte de chequeo mucho más exhaustivo

**1) Grabación de sesión ahora barre TODO** (`server.py`):
- Antes, al grabar sesión, solo se logueaban los sensores del TABLERO y solo mientras estabas
  en la pantalla en vivo. Ahora, mientras la grabación está activa y hay conexión real, un
  barrido en background (`_sweep_sensores_sesion`, cada ~8 s) lee **todos los sensores legibles
  del motor** y los registra, estés donde estés en la app. La sesión queda con el panorama
  completo. Serializado con `ELM_LOCK`; corre uno solo a la vez.

**2) Reporte del Chequeo General mucho más completo** (`reporte.py`) — para que un experto o una
IA pueda diagnosticar de una:
- **"Datos clave para el diagnóstico"**: los ~13 sensores que importan (RPM, temp, ajustes de
  combustible STFT/LTFT, estado de lazo, sonda lambda, batería, MAP, avance, TPS, tiempo de
  inyección, MAF, boost) con su valor medido **y qué esperar de cada uno** (rangos sanos +
  qué significa si está mal). Lo que no se leyó queda marcado como "no se leyó".
- **Detalle por etapa (mín / prom / máx / σ)**: además del promedio por RPM, ahora se ve la
  variabilidad bajo carga y si el sensor oscila — clave para juzgar sondas, ralentí, etc.
- **Módulos presentes / sin respuesta** listados en el resumen.
- **Notas de captura honestas**: si no se leyeron las RPM o una etapa no llegó a banda estable,
  el reporte lo dice (los valores de esa etapa son aproximados).
- **Bloque `para_experto` en el JSON**: todo lo esencial junto (módulos, DTCs, sensores en
  atención, datos clave, evolución completa por RPM, advertencias) — listo para pegarle a un
  mecánico o a una IA.

## [2026-07-21] — Log de consola: se saca el spam "Unknown address" que tapaba los errores

El log de consola (que grabamos justo para cazar errores) venía inundado con miles de líneas
`Unknown address: 7DF 01xx` / `7E0 21xx` idénticas — un `print` cosmético de `elm.py:722` que
se disparaba en CADA request cuya dirección no está en las tablas `dnat` globales (o sea,
siempre: las ECUs del F4R usan 7E0, el OBD genérico usa 7DF). Ahora esa info se escribe al log
dedicado de ECU (`ecu_*.txt`) con la dirección cruda, en vez de a la consola. Los logs de
consola quedan legibles y los errores reales dejan de quedar sepultados.

## [2026-07-21] — FIX F4R: el chequeo ya no se cuelga + ajustes de combustible % estándar en F4R

Dos problemas reportados en el auto real (F4R, cable ELM327 por COM3): el chequeo/ensayo
"no hacía nada y se colgaba", y los ajustes de combustible seguían sin verse en vivo.

**1) El chequeo se colgaba esperando RPM para siempre** (`chequeo.py`):
- Causa raíz: el `while True` que espera que el motor llegue a 1500/2000/3000 RPM **no salía
  nunca por timeout** — al vencer `TIMEOUT_ETAPA` solo cambiaba el mensaje pero seguía
  girando. En F4R, como el régimen a veces no se lee (respuestas multiframe que fallan el
  flow-control a 38400), `rpm` era siempre `None`, nunca entraba en banda → espera infinita =
  "no pasa nada". (El análisis del log real confirmó una tormenta de reintentos, no un cuelgue
  del puerto: `expect()` ya tiene timeout para serie en `port.py:440`.)
- Fix: (a) **salida dura por timeout** — al vencer, captura lo que haya y sigue, marcando
  `alcanzo_banda=False`; (b) **prueba previa `_probar_rpm`** — si las RPM no se pueden leer,
  **saltea las etapas de aceleración** y genera el reporte igual con paneo + ralentí, en vez de
  colgarse. El chequeo ahora SIEMPRE termina y produce reporte.
- **Nota de hardware**: esos reads multiframe del F4R que fallan a 38400 son justo lo que un
  cable con chip **STN + STPX** (el Renlink/OBDLink) resuelve — conectá con adaptador AUTO.

**2) Ajustes de combustible % estándar ahora visibles en F4R** (`ecu_registry.py`, `index.html`):
- Un agente confirmó, leyendo los datos reales del F4R (Sagem S3000), que el ECU enhanced
  **NO expone** el ajuste corto/largo como % ± igual que el OBD genérico: usa "factor de
  enriquecimiento" (0-100%) y "corrección adaptativa por zonas" (−50..+50), otra escala. Por eso
  el usuario nunca veía el % que sí muestra el escáner universal.
- Fix: el perfil **F4R ahora incluye una ECU virtual "OBD-II estándar"** (los PIDs 0106/0107/03),
  así se ven los **mismos %** que en el modo genérico, además de los valores enhanced del F4R.
- **`PRECARGADOS_VER` 2 → 3**: los tableros ya guardados (localStorage con `meg_sel_ver=2` de
  builds previas) no recibían los sensores nuevos porque `_migrarPrecargados()` cortaba temprano.
  Al subir la versión, se agregan solos el ajuste corto/largo y el estado de lazo estándar.

## [2026-07-21] — OBD-II genérico: muchos más sensores + ajustes de combustible y estado de lazo en el tablero

**Motivo**: en el auto real el modo genérico anduvo bien, pero (a) el tablero en vivo NO
mostraba por defecto los ajustes corto/largo de combustible ni el estado de lazo, y (b) faltaban
sensores estándar que el auto puede reportar.

- **Ajustes de combustible y lazo en el tablero por defecto**: se agregaron a `PRECARGADOS`
  (`obd_generico.py`) el PID **06** (ajuste corto B1), **07** (ajuste largo B1), **03** (estado
  del sistema de combustible = **lazo cerrado/abierto**) y **44** (relación lambda comandada).
  Antes 06/07 solo aparecían en el reporte del chequeo, no en la pantalla en vivo.
- **PID 03 (estado de lazo)**: nuevo, con texto claro ("Lazo cerrado usando sonda lambda",
  "Lazo abierto por temperatura", etc.) — lo que el usuario venía pidiendo ver.
- **Tabla de PIDs ampliada de 32 a 55**: sondas lambda B1S2/B2S1/B2S2, sondas de **banda ancha**
  (λ, PID 24/25/34), **temperatura de catalizador** (3C-3F), presión de riel relativa (22),
  purga EVAP (2E), error de EGR (2D), norma OBD del auto (1C), calentamientos desde borrado (30),
  tiempo con MIL / desde borrado (4D/4E), etanol (52), pedal E (4A). Todas fórmulas SAE J1979.
- El tablero ya distingue valores numéricos de texto (`index.html:1805`) y el analizador de
  ondas saltea los no numéricos (`:2744`), así que los estados de texto no rompen gráficos.
- Simulador (`_SIM`) actualizado con los PIDs nuevos para poder probar sin auto.

## [2026-07-20] — Soporte real de adaptadores STN (OBDLink / Renolink): detección de chip y 115200 baudios

**Motivo**: se consiguió un cable "Renlink". La investigación mostró que "Renlink" es
casi seguro una variante ortográfica de **Renolink**, que NO es un clon de CAN Clip ni un
J2534: es un **software propietario** de codificación (ECU/UCH, llaves, airbag) más un cable
con chip **STN11xx/STN22xx** — el mismo silicio del OBDLink SX/EX, que es un **superset del
ELM327** (mismos comandos AT + comandos ST + hasta 1 Mbps). O sea: la ventaja aprovechable
del cable es de **transporte**, no de protocolo.

- **El problema**: el frontend hardcodeaba `adaptador:'ELM327'` (`index.html`), así que todo
  se abría a **38400 baudios** aunque el cable soportara 115200. Consecuencia concreta y
  medible: con `opt_stpx_full` en falso, `elm.py:796` **recorta la lectura de DTC**
  (`1902` → `1902AF`) justamente por el límite de baudios.
- **Selector de tipo de adaptador** en la pantalla de conexión: `AUTO` (default) | ELM327 |
  OBDLINK/STN | VLINKER | VGATE | ELS27. Nuevo `GET /api/adaptadores/tipos`. La elección se
  recuerda en `localStorage` (`meg_adaptador`).
- **Modo AUTO**: abre con el perfil genérico (el más tolerante), identifica el chip con
  `ATI`/`STI` (`_detectar_chip`) y, si es un chip rápido, **reabre** la conexión al baudrate
  óptimo. Se **reabre en vez de conmutar en caliente**: si el cambio de baudios fallara a
  mitad, el adaptador queda en un baudrate y el puerto en otro y la sesión muere; reabriendo,
  el peor caso es volver a la velocidad anterior, que ya sabemos que funciona (y eso está
  implementado como fallback).
- **Se informa al usuario** qué chip se detectó y qué habilitó: toast al conectar, ficha en la
  vista "Adaptador" (STN extendido / STPX completo) y detalle en el test del adaptador.
  Nuevo campo `adaptador_info` en `GET /api/estado` y en la respuesta de `/api/conectar`.
- El test de adaptador ahora usa `AUTO` y suma dos pruebas: identificación del chip y STPX.
- Consejo de la vista "Adaptador" actualizado: el mejor cable ya no es un ELM327 sino uno STN.

**Lo que este cable NO habilita** (para que quede documentado): la codificación de ECU/UCH,
el matching de llaves, el virginizado de airbag y la escritura de EEPROM/flash viven en el
software propietario cerrado de Renolink, no en el cable, y requieren el **seed-key de Renault
(servicio 27)**, que sigue sin implementarse. Además, una escritura de flash interrumpida
brickea la ECU de forma irreversible: el proyecto se mantiene en **solo lectura**.

## [2026-07-19] — El token de logs ahora se guarda en el perfil del usuario (sobrevive re-descargas)

- **Problema**: la notebook vuelve a bajar el ZIP del proyecto para probar, y eso borraba el
  `github_token.txt` (está dentro de la carpeta) → había que volver a configurarlo cada vez.
- **Fix**: el token ahora se guarda en **`~/.sistemasq24/github_token.txt`** (perfil del
  usuario, FUERA del repo). Se configura **una sola vez por notebook** y sobrevive a todas las
  re-descargas. `_github_token()` busca en orden: perfil → carpeta del proyecto → env
  `GITHUB_TOKEN`.
- **Por qué NO se commitea el token al repo** (se evaluó y se descartó): el repo es público y
  el *secret scanning* de GitHub **revoca automáticamente** cualquier token que aparezca en un
  commit, así que subirlo rompería la función a los minutos — además de quedar para siempre en
  el historial. La subida a GitHub requiere autenticación sí o sí (no hay escritura anónima),
  por eso la vía es un token propio + el ZIP como alternativa sin configuración.
- Agregados `GET /api/config` y `POST /api/config/debug` (modo prueba) para poder **ocultar
  más adelante** las herramientas de depuración al usuario común. **No se oculta nada por
  ahora**: seguimos en pruebas y todo queda a la vista.

## [2026-07-19] — FIX: subir logs desde la notebook (no tenía token ni git → callejón sin salida)

En la notebook la subida fallaba con "git no está instalado": no hay `github_token.txt`
(está gitignoreado, así que al bajar el ZIP no viene) NI git CLI → se quedaba sin las dos
vías y el usuario no podía hacer nada desde la app. Ahora hay dos salidas:
- **📦 Bajar logs en ZIP** — `GET /api/logs/descargar` arma un ZIP con todos los logs de
  sesión, los `consola_*` y los reportes de chequeo/ensayo. **Funciona siempre**: sin token,
  sin git y sin internet. Es la vía rápida para mandar los logs por cualquier medio.
- **🔑 Pegar el token desde la app** — `POST /api/logs/token` valida el token contra la API
  de GitHub (que exista y tenga permiso de escritura) y lo guarda en `github_token.txt`; si
  valida, sube los logs en el acto. Ya no hay que crear archivos a mano ni instalar git.
  `GET /api/logs/token-estado` dice si la máquina ya tiene token.
- El error ahora abre un **diálogo explicando ambas opciones** en vez de un toast rojo, con
  instrucciones de dónde sacar el token y qué permiso necesita.
- De paso: `subirLogs()` fallaba si se lo llamaba desde el chequeo/ensayo (buscaba un botón
  que no existe en esas pantallas). Arreglado.

## [2026-07-19] — FIX: el ajuste de combustible del F4R existía pero era imposible de encontrar

El usuario reportó que en el F4R seguía sin ver el ajuste corto/largo de combustible (que sí
aparece en el scanner genérico). Los sensores YA estaban en las listas curadas; el problema
eran **dos bugs de usabilidad**:
- **Los tableros ya guardados nunca recibían los sensores nuevos**: `_autoSelectDefault()`
  solo corre si el tablero está VACÍO, así que ampliar la lista curada no le servía a nadie
  que ya tuviera sensores elegidos. **Fix**: `PRECARGADOS_VER` + `_migrarPrecargados()` —
  suma al tablero los precargados que falten **sin tocar los que el usuario eligió a mano**,
  y avisa con un toast.
- **No se podían buscar**: las etiquetas del F4R son traducción literal del francés
  ("Factor de enriquecimiento de la regulación de riqueza"), así que buscar *"ajuste de
  combustible"*, *"fuel trim"* o *"lazo cerrado"* no devolvía NADA. **Fix**: tabla
  `SENSOR_ALIAS` (dato → alias de taller + términos de búsqueda). El buscador ahora matchea
  etiqueta **y** alias (en el selector de sensores **y** en el analizador de ondas), y la fila
  muestra el alias en cian al lado del nombre técnico.
- **Agregado el estado de LAZO CERRADO** (`Etat stratégie régulation richesse`) a los
  precargados, como pidió el usuario. Ahora son 17.
- Verificado: 17/17 precargados y todos los alias matchean parámetros reales; las búsquedas
  "ajuste corto de combustible", "ajuste largo", "fuel trim", "lazo cerrado", "sonda lambda"
  y "acelerador" encuentran el sensor correcto. `node --check` OK.

## [2026-07-19] — FIX de los 2 módulos nuevos probados en el auto real (ensayo y chequeo)

### Ensayo de aceleración: nunca detectaba el movimiento
- **Bug raíz**: el request de la VELOCIDAD podía no estar entre los que se capturaban
  (`_requests_captura` filtra por la lista de sensores clave), así que `vel` salía siempre
  `None` → la condición de arranque nunca se cumplía y quedaba esperando para siempre.
- **Fix**: los requests de **velocidad y RPM se fuerzan SÍ o SÍ** en la captura.
- **Fix 2 (ECUs que no dan velocidad)**: al iniciar se **prueba si la velocidad se lee**
  (`_probar_velocidad`). Si no, el ensayo pasa a modo **por tiempo**: avisa en pantalla, el
  botón **«Arrancar grabación ahora»** está **siempre visible** (antes solo aparecía tras 2
  min de timeout) y el tramo se corta con «Terminar tramo». Además, sin velocidad, arranca
  solo si las RPM suben >800 sobre el ralentí. El reporte marca `velocidad_disponible`.

### Chequeo general: se tildaba leyendo ECUs innecesarias
- **Bug raíz**: el paneo leía **todas las ECUs y cada request de cada una**. En el auto real
  el ELM lee de a una y `_seleccionar_ecu` reabre sesión → cientos de lecturas seriadas:
  parecía colgado.
- **Fix**: el paneo lee **SOLO la ECU del motor** (`SOLO_MOTOR_EN_PANEO`), que es lo que
  importa para el chequeo. Además: **presupuesto de tiempo** (90 s; si el auto responde
  lento corta y sigue con DTC + etapas de RPM en vez de colgarse), corte si la ECU deja de
  responder (8 fallos seguidos) y **progreso por sensor** ("sensor 12/80") para que se vea
  que avanza. Verificado: pasó de leer 6 ECUs a 1.
- Textos de la pantalla actualizados para reflejar que es solo el motor.

## [2026-07-19] — Log de consola: captura TODO lo que sale por la pantalla de CMD

- **`app/consola_log.py`** (NUEVO) — en cada arranque crea `log/consola_<fecha>.txt` que
  **duplica stdout y stderr** (prints, warnings, tracebacks, logs de uvicorn/FastAPI, errores
  de importación). Con flush inmediato (si el proceso se cae no se pierde nada), `faulthandler`
  para crashes duros (segfault/deadlock) y un `excepthook` para excepciones no manejadas.
  Conserva los últimos 20 logs y borra los viejos.
- **`app/run.py`** — llama a `consola_log.iniciar()` como lo primero, antes de importar uvicorn,
  para capturar también los mensajes de inicio.
- **`app/server.py`** — "Subir logs" ahora también sube los `consola_*.txt`, así esos errores
  de consola (que no aparecían en ningún otro lado) se pueden revisar desde acá.

## [2026-07-19] — Importador de ecu.zip nuevo + roadmap documentado (#6 y estratégicos)

- **`tools/importar_ecu_zip.py`** (NUEVO) — deja la mejora #6 lista para un solo comando: toma
  un `ecu.zip` nuevo (ej. la base comunitaria de oct-2022, ~3086 ECUs vs. 1973), lo valida,
  compara la cantidad de ECUs contra la base actual, lo copia a `vendor/sistemasq24/ecu.zip` y
  lo **re-parte** en `ecu.zip.part*` (<95 MB) para GitHub. `app/run.py` lo re-arma solo.
  Falta conseguir el archivo (links oficiales caídos; hay que rastrear el mirror comunitario).
- **`CLAUDE.md`** — documentado el roadmap pendiente (ecu.zip oct-2022, DTCs por UDS svc 19,
  sniffing pasivo de CAN con cantools+DBC, seed-key de Renault, rebase del upstream ddt4all)
  para no perderlo entre sesiones.

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
