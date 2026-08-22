# Changelog — SISTEMASQ24

Todos los cambios importantes del scanner se anotan acá. El más reciente arriba.
Formato de fecha: AAAA-MM-DD.

## [2026-08-22] — Comparadas las 15 variantes de S3000 de la base contra la nuestra curada

Pedido del usuario: revisar en detalle si las otras ECUs S3000 que detectó con Renolink (más
completas que la nuestra) tienen algo útil para sumar. Comparación sistemática de los 617
datos de nuestro `S3000_AD_CAN_3_X84ph2_S.json` contra los ~753-654 de las variantes más
ricas (`S3000_26_55_CAN_91`, `S3000_AD_CAN_3_X61`, etc.): 321 datos legibles y con unidad/
lista que ellas tienen y nosotros no. La mayoría no aplica al F4R estándar (flex-fuel/etanol,
GLP, bomba de vacío de mastervac — cosas de otras versiones del motor) o son duplicados con
otro nombre del mismo byte que ya leemos.

**Hallazgo verificado y agregado**: comparando byte a byte la Trame 02 (misma
`sentbytes`/`minbytes`/layout en ambas variantes — confirma que Renault reusa el mismo
layout de trama entre revisiones de software del S3000), el byte 21 — donde ya leíamos
"Panne calculateur injection" (bit 2) — tiene 6 bits más decodificados en `S3000_A774_Can_1_X84`
que la nuestra no traía: avería de memoria de respaldo, avería de la zona de bloqueo lógico,
avería del microcontrolador secundario (presente/memorizada) y avería del enlace SPI interno
(presente/memorizada) — autodiagnóstico de HARDWARE del propio ECU (no del motor), útil para
fallas intermitentes raras. Se agregaron a `original/S3000_AD_CAN_3_X84ph2_S.json` (data +
receivebyte_dataitems de la Trame 02, con el `bitoffset` correcto verificado 1/3/4/5/6/7) y a
`es/S3000_AD_CAN_3_X84ph2_S.es.json` (traducción) — **mismo byte que ya leíamos, sin costo
extra de red**. Verificado: `readable_params()` pasa de 524 a 530 (exactos +6), sin romper
nada existente. Agregados a `SENSORES_RELEVANTES` en `index.html` (buscables, no en el
tablero por defecto — son diagnóstico interno raro, no algo para mirar todos los días).

Otros hallazgos NO implementados por baja confianza (byte layout diverge más allá de cierto
punto entre variantes, o son renombres del mismo dato, no info nueva real): posiciones de
mariposa "piste 1/2" sin filtrar (mismo byte que la versión filtrada que ya tenemos), avance
de encendido post-corrección anti-cliquetis (podría ser útil pero requiere verificar mejor el
layout antes de sumarlo), y decenas de flags de inhibición de A/A muy específicos (bajo valor
para un scanner genérico).

## [2026-08-21] — Confirmado: el reset de mezcla NO reinicia offset/ganancia de aprendizaje

El usuario probó el fix de sesión del reset (commit anterior) y reportó que el problema
seguía: el offset de aprendizaje se queda con el valor viejo AUNQUE se cierre y reabra el
programa de cero. Eso descarta el caché de sesión como causa (una app nueva no tiene ese
caché) — confirma que es el propio ECU el que no toca ese valor con el reset modo 82, no un
bug de nuestro software. Actualizada la documentación (`ayudas.json`, `reporte.py`) para
reflejar esto como CONFIRMADO en la práctica (antes decía "hipótesis, no confirmado" sobre
el punto neutro, ahora agrega que el reset directamente no lo mueve). Corregido también el
texto de la pantalla de reset en `index.html`, que había quedado sobre-prometiendo que el
reset tocaba "el offset/ganancia de aprendizaje" — eso era incorrecto, se aclara que esos dos
valores NO se reinician con este comando (solo el ajuste corto y las 5 zonas de ajuste largo).

## [2026-08-21] — Fix: el reset de mezcla parecía "solo tocar el OBD", no las tramas nativas

El usuario reportó: el reaprendizaje de ajustes de combustible reinicia el ajuste corto/largo
(el que se lee por OBD), pero deja igual las 5 zonas nativas y el offset/ganancia de
aprendizaje del F4R. Investigado:
1. **El modo `82` que ya usábamos SÍ es correcto** — confirmado directamente en la definición
   del ECU (`ResetMode` en el JSON del F4R): `0x82 = "adaptatifs de richesse"`, el código real
   de Renault para resetear TODO el sistema nativo de mezcla (no un valor inventado).
2. **La causa real era otra**: después de mandar el `ECUReset` (servicio 11), el ECU cierra la
   sesión de diagnóstico extendida y vuelve a la default — pero `elm.startSession` (la variable
   que `ensure_session()` usa para decidir si hace falta reabrir sesión) seguía diciendo que
   estábamos en la sesión de antes del reset. Resultado: TODAS las lecturas nativas del F4R
   después del reset se salteaban el reabrir-sesión y volvían viejas/vacías, mientras que los
   PID OBD estándar (van por broadcast 7DF, sin sesión) sí se actualizaban con normalidad —
   dando la falsa impresión de que el reset "solo tocaba el OBD".
Fix en `_intentar_reset_en_sesion` (`server.py`): fuerza `elm.startSession = ""` justo después
de mandar el reset, para que la próxima lectura reabra la sesión de verdad. También se corrigió
el texto de la opción "Ajustes de combustible" en `index.html` (antes decía "borra el ajuste
corto/largo (STFT/LTFT)"; ahora explica que resetea el sistema nativo completo, del cual el
STFT/LTFT es solo el reflejo por OBD).

## [2026-08-21] — Se sube al repo la copia archivada de ddt4all original (partida)

Pedido del usuario: subir `ddt4all.rar` (179 MB, el proyecto ddt4all original completo que
había dejado en la carpeta) junto con la última versión. GitHub bloquea archivos de más de
100 MB en un push normal, así que se aplicó el mismo truco que ya usa `ecu.zip`: partido en
`upstream/ddt4all.rar.part00`/`part01` (90 MB y 89 MB, con margen bajo el límite) con el
nuevo `tools/repartir_ddt4all_rar.py`. Integridad verificada por hash SHA-256 (partes
re-armadas en memoria = hash idéntico al original) y también reconstruyendo el archivo real
con el nuevo `tools/rearmar_ddt4all_rar.py` (mismo hash, confirmado). A diferencia de
`ecu.zip`, este `.rar` NO se re-arma solo al arrancar (`run.py` no lo toca) porque no hace
falta para correr el scanner — el código de ddt4all ya está vendoreado/rebrandeado en
`vendor/sistemasq24/core`; esto es solo una copia de referencia histórica. `.gitignore` y
`CLAUDE.md` actualizados con la misma nota que ya tenía `ecu.zip`.

## [2026-08-12] — Corrige interpretación de "Offset/Gain de aprendizaje": no son ±0%-neutro

El usuario trajo una info (de origen incierto) sobre códigos "PR009/PR624/PR625/ET037" de
CAN Clip y una escala de byte 0-255 con 128=neutro. Investigado con un agente contra
documentación RTA real (Revue Technique Automobile) y ddt4all: los códigos exactos que
pegó el usuario (PR009, PR624, PR625, ET037, ET055) y los rangos "115-140"/"110-145" **no
se encontraron en ninguna fuente verificable** — probablemente inventados/mezclados por una
IA. PERO el concepto de fondo (escala de byte 0-255, 128=neutro) **sí es real**: confirmado
en la RTA de un Vel Satis con el MISMO motor F4R (parámetros PR173/174), consistente con lo
que ya teníamos confirmado para las 5 zonas de ajuste largo (offset=-50 en su fórmula → 0%
en nuestra escala = byte crudo 128). Hallazgo accionable: "Offset apprentissage regulation
richesse" y "Gain apprentissage regulation richesse" (parámetros DISTINTOS a las 5 zonas) NO
tienen ese offset=-50 en su fórmula — por lo que es razonable (no confirmado) que SU neutro
esté en ~50% y no en 0%, a diferencia de lo que asumía el código hasta ahora. Se corrigió
`DIAG_CLAVE` en `reporte.py` (antes agrupaba "apprentissage regulation" junto con
"correction adaptative" bajo el mismo criterio ±0%-neutro de las 5 zonas — eran cosas
distintas) y se agregaron textos de ayuda propios en `ayudas.json` con la salvedad explícita
de que el neutro en 50% es una hipótesis razonada, no un hecho confirmado por Renault.

## [2026-08-12] — Fix: valores con basura de precisión de punto flotante (se veían "rotos")

El usuario mandó fotos del auto real: las 3 primeras zonas de ajuste largo mostraban el
MISMO valor "0.00396800 0000000416" (número cortado en dos líneas). Investigado: NO es un
bug de lectura cruzada entre zonas (los `firstbyte` de las 5 zonas están bien definidos y
sin superposición: 26/28/30/32/34, 2 bytes cada una) — que las 3 primeras coincidan es
esperable, es el valor NEUTRO por defecto (raw≈32768 → ~0%) tras el reset de aprendizajes
reciente: las zonas todavía no divergieron porque el auto no anduvo lo suficiente en cada
rango de carga para que cada una aprenda su propia corrección. El problema real es de
REDONDEO: esos 5 dataitems no tienen un `"format"` propio en la base del ECU (a diferencia
de otros como el ajuste corto, que sí lo tiene y por eso se ve "50.00%" limpio), así que el
motor de ddt4all devuelve el float crudo con basura de precisión de Python
(`32768*0.001526-50 = 0.003968000000000416`, confirmado calculándolo a mano). Fix en
`ecu_registry.py:read_request()`: cualquier valor float sin la conversión especial de
µs→ms ahora se redondea a 2 decimales antes de salir — mismo criterio que ya usa el resto
de la app (batería, temperaturas). Este fix corre en el mismo lugar que usan TODAS las
lecturas (tablero, chequeos, grabaciones), así que corrige el problema en todos lados de
una sola vez.

## [2026-08-12] — Chequeo de mezcla: agrega panel de valores EN VIVO

Pedido del usuario: la pantalla tenía el chequeo guiado (botón "Chequear mezcla") pero
faltaban los valores en tiempo real — son dos cosas separadas. Se agregó un panel `📡 En
vivo` (arriba del botón, siempre visible, independiente de si el chequeo guiado está
corriendo) con los mismos 11 sensores que lee el backend (`DATOS_MEZCLA_LIVE` en
`index.html`, espejo de `chequeo_mezcla.DATOS_MEZCLA_F4R`). Usa una suscripción WebSocket
propia (`subscribeLiveMezcla()`) independiente de la del Tablero en vivo — no toca
`ST.selected` (la selección del usuario en el tablero principal), así que entrar a esta
pantalla no cambia lo que el usuario tiene armado en su tablero. Al salir de la pantalla se
desuscribe (`go()` ya llamaba `unsubscribeLive()` al cambiar de vista; se ajustó para no
hacerlo también al ENTRAR a mezcla, ya que esta pantalla arma su propia suscripción).

## [2026-08-12] — Nueva pantalla "⚗️ Chequeo de mezcla" (F4R)

Pedido del usuario: una pantalla exclusiva para diagnosticar mezcla rica/pobre, rápida (sin
barrer otras ECUs), con veredicto textual tipo bot. Nuevo módulo `app/chequeo_mezcla.py`
(hermano de `chequeo.py`, reutiliza sus constantes y helpers genéricos): lee SOLO 11 sensores
(RPM, MAP, las 5 zonas nativas de ajuste largo, ajuste corto, lazo abierto/cerrado, sondas
lambda amont/aval) en 2 etapas — ralentí y ~2500 RPM sostenidas (mismo criterio de banda/
estabilidad/timeout/captura-manual que Chequeo General, funciona con el auto detenido o
andando). Nuevo en `reporte.py`: `_evaluar_zona_mezcla` (evaluador propio de 3 niveles —
normal ±5%/sospechoso ±5-8%/problema >±8%, con dirección rica/pobre — separado del `_evaluar`
de 2 niveles que ya existía), `_mezcla_analizar`/`_txt_mezcla`/`_html_mezcla`/`generar_mezcla`
(mismo patrón que `_conduccion_analizar`/`generar_conduccion`). Nuevo en `server.py`:
`estado.mezcla` + `_CtxMezcla` + endpoints `/api/mezcla/{iniciar,estado,capturar-ahora,
cancelar,reporte/{tipo}}` (mismo patrón que Chequeo General), con **exclusión mutua** (409 si
ya hay un chequeo general o una grabación de conducción corriendo) para no competir por el
ELM. El loop de captura de mezcla, a diferencia del de Chequeo General, SÍ respeta
`estado.pausar_lecturas` (se autopausa en pantallas silenciosas como reaprendizajes). Nueva
vista `⚗️ Chequeo de mezcla` en `index.html` (perfil F4R únicamente — depende de las 5 zonas
nativas, que no existen en OBD genérico), con el mismo patrón de polling/gauge de RPM que
Chequeo General. Verificado en simulación end-to-end (todas las fases, exclusión mutua,
capturar-ahora, cancelar) — las zonas salen `sin_dato` en pura simulación porque el harness
de sim no tiene canned data para esos datos nativos (mismo comportamiento preexistente que
Chequeo General con datos F4R en simulación); con el auto real van a traer valores.

## [2026-08-12] — Valores de referencia (ayuda) para diagnosticar el ajuste de combustible

Pedido del usuario: cómo sabe si el valor de cada zona es correcto/alto/bajo para poder
diagnosticar. Investigación (agente con búsqueda web/GitHub) sobre el estándar SAE J1979
(PID 06/07) y cómo lo maneja Renault internamente. Confirmado: fórmula estándar
`%=(byte-128)×100/128`, 0%=neutro; referencias de industria: ±5% normal, ±8% sospechoso, más
de ±25% sostenido = problema real; positivo=mezcla pobre (agrega nafta), negativo=mezcla
rica (saca nafta). La documentación técnica de Renault (manual RTA del F4R) confirma que el
ajuste largo nativo usa la misma escala centrada en 0%, dividida en zonas de carga (nuestra
base tiene 5). No se encontró documentación de cómo la ECU resume esas zonas en el único valor
del PID 07 estándar — dato marcado explícitamente como no confirmado. Se agregaron estas
referencias como texto de ayuda (botón "?") en `ayudas.json` para: las 5 zonas nativas, el
"Facteur enrichissement" (corto nativo, con nota de incertidumbre sobre su punto neutro real,
ya que no es una escala ± como el resto), y los "Ajuste corto/largo de combustible B1" (PID
06/07 estándar), con nota de que ese resumen puede no reflejar bien una sola zona con problema.

## [2026-08-12] — Se agregan las 5 zonas del ajuste largo nativo del F4R al tablero

El F4R no tiene un solo "ajuste largo" como el PID 07 estándar: Renault lo modela con 5
correcciones adaptativas independientes, una por zona de presión/carga del motor
(`Correction adaptative de la 1ère...5ème zone de pression`, cada una ±50% centrada en 0).
Antes solo se mostraba la zona 1 por defecto; se agregan las 5 a `SENSORES_PRECARGADOS`
(`index.html`) — ya estaban en `SENSORES_RELEVANTES` y `SENSOR_ALIAS` (buscables), solo
faltaba que aparecieran solas en el tablero. Se pueden sacar del tablero desde "Elegir
sensores" igual que cualquier otro, por si no se quieren ver las 5. Ya se leían automático en
Grabar sesión/chequeo (están en la misma Trame 04 que otros datos ya capturados, no hacía
falta tocar `chequeo.py`). `PRECARGADOS_VER` 6→7.

## [2026-08-12] — Autodetección: bug de timeout que impedía detectar hasta el F4R propio

El usuario reportó que "Auto detectar" no encontraba ni la Kangoo NI el F4R (auto conocido,
siempre presente y probado antes). Encontrado: `TIMEOUT_SONDEO_MS=200` (`sq24_scanner.py`) no
solo se usaba para descartar rápido direcciones muertas — también se aplicaba al PEDIDO DE
SESIÓN mismo (`10C0`/`1003`, en `_identificar`/`_identificar_old_can`), porque
`start_session_can()` corre bajo el timeout activo en ese momento. `AT ST` (lo que fija ese
valor en el ELM327) es el tiempo que el CHIP espera la respuesta antes de devolver "NO DATA";
con un clon lento, o justo después de reabrir el protocolo/direccionar, 200ms puede cortar la
sesión antes de que conteste una ECU viva. Se sube `TIMEOUT_SONDEO_MS` a 350ms y
`TIMEOUT_IDENT_MS` a 1000ms. Sigue siendo rápido para las ~110 direcciones muertas de un
escaneo típico, pero da margen real a las que sí tienen algo. Verificado en simulación (sigue
detectando las 6 ECUs sin regresión); falta confirmar en el auto real.

## [2026-08-12] — VVT: encontrado el campo que SÍ es en vivo (estaba en otra pantalla)

El usuario comparó con un Clip CAN real sobre el mismo mapa del F4R: a ralentí "VVT" aparece
desactivada, y con una acelerada fuerte (>3000rpm) pasa a activada y vuelve a desactivarse.
Antes dijimos que el campo VVT que el usuario veía era solo informativo — y es CORRECTO para
"Config VVT" (en la pantalla "Trame 05 Ralentí y VVT"): es una lista fija que dice el TIPO de
VVT que tiene el auto ("sans VVT"/"VVT on-off"/"VVT continu"), no cambia nunca. Pero existe
OTRO campo, "Commande décaleur VVT" (Actif/Inactif) — el comando real al actuador del VVT —
que vive en una pantalla sin "VVT" en el nombre ("Trame 02 États et paramètres secondaires"),
por eso nunca se había encontrado. Se agregó a `SENSORES_RELEVANTES` (`index.html`) y a
`DATOS_CLAVE_F4R` (`chequeo.py`) para que aparezca en el tablero y se capture en las
grabaciones/chequeos.

## [2026-08-12] — Presión atmosférica: se reincorpora "Depresión altimétrica"

Reconsiderado tras la comparación con el Clip real: el Clip muestra una presión atmosférica
~1000mb, casi fija, para el mismo mapa — coincide en comportamiento (valor chico y estable) con
lo que ya leíamos acá. La hipótesis: nuestro valor es una DESVIACIÓN (delta) respecto a una
referencia interna del ECU, no la presión absoluta directa — de ahí el nombre "depresión" y por
qué el delta nunca superaría los ~943mb de tope. El Clip probablemente suma su propia
constante de referencia (no documentada en la base abierta) para mostrar el absoluto. Se
reincorpora el dato crudo (sin inventar una conversión que no podemos verificar); si en algún
test se anota la presión atmosférica real (de un reporte del clima) junto a este valor, se
puede calibrar la referencia. `PRECARGADOS_VER` 5→6.

## [2026-08-09] — Tiempo de inyección (y otros datos en µs) ahora se muestran en ms

Pedido del usuario: los µs son difíciles de leer a simple vista (ej. "4775.96 µs"). Se agregó
conversión automática en `TranslatedECU._unit_of()`/`read_request()` (`ecu_registry.py`): CUALQUIER
dataitem cuya unidad cruda sea µs/us se muestra en ms (÷1000, redondeado a 3 decimales) — no es
una lista hardcodeada de nombres, así que cubre las 4 variables del F4R que usan esa unidad
("Temps injection réel" y sus 3 históricos) y cualquier otra que aparezca en el futuro. Se
actualizó también el rango curado de `rangos_f4r.json` (1500-5000µs → 1.5-5.0ms). Verificado en
simulación: 4775.96µs → 4.776ms, unidad "ms".

## [2026-08-09] — Se saca info de turbo/wastegate: el F4R es atmosférico

Pedido del usuario: "quita información inútil de la pantalla en vivo como por ejemplo lo del
turbo. el f4r no tiene turbo". Confirmado con logs reales: "Presión de sobrealimentación
(turbo)" y "Consigna RCO wastegate" quedan clavados en un valor fijo toda la sesión (103.00
mbar y 1.17% en las 123/123 lecturas del log) — son canales del ECU sin sensor/actuador físico
conectado en la variante atmosférica. Se sacaron de: sensores relevantes/precargados y del
diccionario de búsqueda manual (`index.html`), de la lista de captura del Chequeo General
(`chequeo.py`), de la lista de captura y de los "destacados" de Grabar ensayo (`ensayo.py`),
de las notas de diagnóstico del informe (`reporte.py`), y del rango curado (`rangos_f4r.json`).
Se dejaron sin tocar las traducciones genéricas de DTC de turbo/wastegate en `dtc_db.py` (son
compartidas con otros perfiles de auto que sí puedan tener turbo).

## [2026-08-08] — Se saca "Depresión altimétrica": dato mal escalado, no confiable

El usuario notó que nunca coincide con el MAP a auto en contacto (debería ser ~igual a la
presión atmosférica real, ~1000-1013 mbar). Revisando la definición del ECU: el dato usa
1 solo byte sin offset (`valor = crudo × 3.7`), con tope matemático de 943.5 mbar — **nunca
puede alcanzar la presión atmosférica real**, así que jamás iba a coincidir con el MAP. En
los logs reales se confirmó que queda clavado en 3.70 mbar (crudo=1) durante toda la sesión.
No es una falla del sensor ni del auto: es un dato mal escalado en la base de definiciones
del ECU. Se sacó de `SENSORES_RELEVANTES` y `SENSORES_PRECARGADOS` (`index.html`) y del
archivo de rangos curados (`rangos_f4r.json`). Se agregó migración (`PRECARGADOS_VER` 4→5,
`SENSORES_DESCARTADOS`) para sacarlo también de los tableros que el usuario ya tenía guardados
en su notebook. De paso: se confirmó que el S3000 NO expone el voltaje crudo del MAP como dato
de diagnóstico (solo el valor ya convertido a mbar) — a diferencia del TPS y las sondas lambda,
que sí exponen su tensión analógica.

## [2026-08-08] — Gráfico de conducción: el RPM es la referencia (área de fondo), no la velocidad

Pedido del usuario: "las rpm son las que nos dicen en qué estado está el auto" — en sus pruebas
el F4R casi nunca se mueve (acelera en el lugar), así que la velocidad no sirve de contexto visual
pero el régimen sí.
- `_bloque_grafico()` (`reporte.py`) ahora identifica el **Régimen del motor** entre las series y
  lo dibuja SIEMPRE como **área de fondo** (relleno, más grosor, `order:99` para quedar detrás),
  con el resto de los sensores (ajuste corto/largo, temperatura, avance, velocidad si hay…) como
  líneas finas encima — sus oscilaciones ("picos") quedan bien visibles sobre el fondo del RPM.
  Si no hay RPM en las muestras, cae a Velocidad como fondo.
- El checkbox del RPM queda destacado (fondo propio + etiqueta "(referencia)").
- **Textos dinámicos** según el eje real (`resumen.eje`): el subtítulo, la tarjeta de arriba (antes
  mostraba "0.0–0.0 km/h" cuando el auto no se movía — ahora muestra "RPM · eje: régimen") y el
  título de la tabla de bandas se adaptan a "velocidad" o "régimen" según corresponda.
- Verificado visualmente (Edge headless + captura) en los dos escenarios: auto detenido
  (acelerando en el lugar, eje=rpm) y auto en movimiento (eje=velocidad) — en ambos el RPM queda
  de fondo y el resto de los sensores se leen encima con sus picos bien marcados.


## [2026-08-06] — FIX: el ajuste corto/largo no se capturaba en "Grabar conducción" + gráfico de evolución con scroll

Revisando el informe `conduccion_20260806_195254`: "ajuste corto"/"ajuste largo" salían como NO
leídos, y en las muestras crudas ni aparecían (0 de 76 sensores capturados los mencionaba).
- **Causa**: `_conduccion_setup()` (`server.py`) arma la lista de requests a partir de
  `chequeo.DATOS_CLAVE_F4R`, que son nombres NATIVOS en francés de la ECU. Los PIDs OBD "extra"
  del motor (`motor.obd_extra` = ajuste corto/largo ±%, lazo, RPM de respaldo — ver
  `ecu_registry.py`) tienen su `dato` en español (viene de `obd_generico.PIDS`) y nunca estaban
  en esa lista, así que sus requests (`0106`/`0107`/`010C`) nunca se agregaban a la captura.
- **Fix**: `_conduccion_setup()` ahora agrega explícitamente los requests de `motor.obd_extra`
  a la captura, sin depender de que su nombre esté en `DATOS_CLAVE_F4R`. Verificado: ahora
  `0106`/`0107`/`010C` están en la lista de requests capturados.

**Gráfico de evolución temporal en el informe de conducción** (`reporte.py`): el HTML de
"Grabar conducción" solo tenía tablas — nunca tuvo gráfico real (lo que el usuario vio antes
eran demos armadas aparte, no algo generado por el sistema). Ahora:
- `_bloque_grafico()` arma un gráfico Chart.js (embebido INLINE — el informe es un archivo
  suelto, sin servidor detrás) con series de tiempo de los sensores clave (velocidad, RPM,
  ajuste corto/largo, temperatura, avance, MAP, sondas, mariposa/pedal, par, inyección — los
  que aparezcan en las muestras).
- **Checkboxes** para elegir qué sensores mostrar (por defecto: velocidad, RPM, ajuste corto,
  ajuste largo).
- **Scroll horizontal en vez de achicarse**: el canvas es ANCHO (~14 px/segundo de manejo, con
  techo de 24000px) dentro de un contenedor `overflow-x:auto` — grabaciones largas se recorren
  desplazando, nunca se comprimen hasta quedar ilegibles.
- Bug encontrado y corregido en el camino: con `parsing:false`, Chart.js necesita puntos
  `{x,y}`, no arrays `[t,v]` (con arrays el gráfico quedaba vacío). Verificado visualmente
  (Edge headless + captura): las series se dibujan bien.


Repo: https://github.com/alaninn/sistemasq24

---

## [2026-07-31] — Autodetección: el timeout de 200 ms cortaba la identificación (por eso ni el F4R se detectaba)

El usuario probó el auto-escaneo **en su propio F4R** (que sabemos que responde perfecto) y no
encontró nada. Rastreado con una respuesta REAL capturada en un log viejo:

    61 80 82 00 87 89 38 54 32 31 33 82 00 50 95 16 00 AD 89 00 40 06 46 01 00 00

- Pasada por `_parse_ident_2180` da `supplier=213, soft=00AD, version=8900` y **matchea
  exactamente `S3000_AD_CAN_3_X84ph2_S`** — el archivo curado del F4R. O sea: **el match y la
  base están bien**; el problema es que la identificación **nunca se llegaba a leer**.
- Causa: `escanear()` baja el timeout CAN a **200 ms** para descartar rápido las 121 direcciones
  muertas, pero esa respuesta son **26 bytes = multiframe** (con flow control) y no entra en
  200 ms. Se cortaba, `_parse_ident_2180` recibía basura → `None` → sin identificación → sin
  match → "no se detectaron ECUs".
- **Fix**: el timeout corto queda solo para el sondeo; en cuanto una dirección **contesta la
  sesión** (`10C0`), se sube a **900 ms** para leer la identificación y se vuelve a bajar.
  Constantes `TIMEOUT_SONDEO_MS` / `TIMEOUT_IDENT_MS`.
- **Además, el escaneo ahora deja rastro en la grabación** (`_log`): inicio (direcciones a
  sondear, targets de la base), cada dirección que responde con su identificación cruda, y el
  resultado final. Antes no registraba NADA, por eso los logs no servían para diagnosticarlo.

## [2026-07-31] — FIX: los actuadores del MOTOR no funcionaban (canister, VVT, bomba…)

Del log de las 20:53: todos los actuadores del motor fallaban con
`Ecurequest::build_data_stream : Data item Output Control.tempON does not exist`, mientras que
los de la UCH (luces, electroventilador…) andaban bien.
- Causa: `activate_actuator` **hardcodeaba el campo `Output Control.tempON`**, que existe en la
  UCH pero **no en el motor**. El request `Output Control` del motor F4R usa
  **`Nombre de cycle de pilotage`** (número de ciclos, 8 bits). Pasar un campo que la ECU no
  declara hace fallar el armado del comando, así que nunca se enviaba nada.
- Fix: el comando se arma **según los campos que el request declara realmente**
  (`req.sendbyte_dataitems`): siempre Command + lista de salida, y la duración se pone en
  `tempON` o en `Nombre de cycle de pilotage` según cuál exista; se descarta cualquier campo
  que la ECU no tenga.
- Verificado: motor ID35 (Vanne Purge canister) → `30 23 00 FF`; apagar → `30 23 11 0A`;
  UCH ID8 sigue armando `30 08 00 FF`.

## [2026-07-30] — El informe de conducción se adapta si el auto no se movió (eje = RPM)

Verificado en el log de hoy que el fix del sensor de velocidad **funciona** (ya elige
`Velocidad del vehículo` y no devuelve `None`). Pero la prueba fue **con el auto parado**
(velocidad siempre 0, RPM de 0 a 2144 = acelerando en el lugar), así que el informe quedaba con
una sola banda y sin análisis.
- Ahora, si el auto **no se movió** (`max(velocidad) < 3 km/h`), el informe usa el **régimen**
  como eje: bandas Ralentí / 1000-1500 / 1500-2000 / 2000-2500 / 2500-3000 / 3000+.
- El resumen expone `eje` ("velocidad" | "rpm") y `se_movio`; los títulos del TXT/HTML lo aclaran
  ("el auto no se movió: se usa el RPM como eje").
- Así la prueba en el taller (acelerando en el lugar) también rinde un informe útil.

## [2026-07-30] — BUG DE FONDO en la autodetección: la vía KWP (21 80) NUNCA podía matchear

Auditando por qué la Kangoo/Dokker no se detectaba (el usuario preguntó bien: "si en algún
momento probaba la correcta, ¿por qué no la conectó?"), aparecieron **tres** problemas reales:

1. **`_parse_ident_2180` devolvía la versión de diagnóstico en DECIMAL** (`str(int(dv,16))`),
   pero `EcuIdent.checkWith` la re-interpreta como HEX: `int("0x104",16)=260 ≠ int("0x68",16)=104`.
   Resultado: **ninguna ECU identificada por el servicio `21 80` podía matchear jamás** — y esa es
   justamente la vía de las Renault clásicas (F4R, EMS312x de Kangoo/Dokker…). La vía UDS
   (`22F1A0`) sí funcionaba porque deja el hex crudo. **Corregido**: ahora devuelve hex crudo,
   consistente con la vía UDS y con `db.json`.
2. **Las ECUs que respondían pero no matcheaban se descartaban en silencio** → el usuario veía
   "no se detectaron ECUs" aunque el auto hubiera contestado. Ahora se juntan en
   `no_identificadas` (dirección + identificación leída), se devuelven en el resultado y el
   frontend las muestra: *"⚠️ N módulo(s) SÍ contestaron"* con sus datos, e invita a cargar la ECU
   a mano.
3. **El match es ambiguo** (documentado, no resuelto): 2 ECUs comparten el autoident exacto del
   EMS312X (él y `N_PB1D_HR15`) y **84** comparten el match aproximado (supplier 001 + soft 00DC),
   así que `_match` puede devolver una ECU equivocada — devuelve la primera que encuentra. Para
   eso está el selector manual.

## [2026-07-30] — Elegir la ECU A MANO de la base (para autos que la autodetección no encuentra)

El usuario probó una **Kangoo/Dokker** y el scanner no detectó la ECU del motor, aunque en
DDT4All conecta bien eligiendo **EMS312X** de la lista. El problema de fondo: el scanner **no
tenía forma de elegir una ECU a mano** — el selector de vehículos tiene 6 modelos hardcodeados
(solo el Mégane II habilitado) y todo lo demás dependía de la autodetección.

- **`SQ24Scanner.buscar_ecus(texto)`**: busca en las 3.945 ECUs del `ecu.zip` por nombre de
  archivo, `ecuname`, grupo y proyectos.
- **`GET /api/ecu-database/buscar?q=`** y **`POST /api/ecu-database/cargar`** (lista de archivos
  → `Registry.load_detectado`, asignando slot/ícono por grupo con `_slot_para_grupo`).
- **Frontend**: en la pantalla de selección de vehículo, caja **"¿Tu auto no está en la lista?"**
  con buscador, ejemplos rápidos (EMS312X, injection, sirius, airbag), resultados con
  grupo/protocolo/proyectos y carga de las ECUs elegidas.
- Verificado: buscar `EMS312` encuentra `EMS312X_RDC_xxx_RDE_...` (Injection, CAN) y al cargarlo
  queda como ECU `motor` en TX 7E0 / RX 7E8 con **3.166 sensores legibles**.

Pendiente: saber POR QUÉ la autodetección no la encontró (hace falta el log de esa sesión, que no
se subió — los logs del día son todos del F4R).

## [2026-07-30] — FIX: el informe de conducción salía SIN velocidad (y por eso sin análisis)

Revisando los informes que subió el usuario (`conduccion_20260729_223241`,
`conduccion_20260730_000518`) apareció el bug: `vel_min/vel_max = None` y **0 bandas de
velocidad** — o sea, el análisis por velocidad (el corazón del módulo) no funcionaba, aunque los
75 sensores sí se grababan.
- Causa: `_conduccion_setup()` tomaba el **primer** parámetro cuyo nombre contuviera "velocidad",
  y en el F4R hay ~10 (botón del limitador, "velocidad solicitada", "velocidad inválida"…).
  Además "Velocidad del vehículo" existe en DOS tramas (01 y DIV-RVLV) y agarraba la que **no se
  captura**, así que la lectura siempre venía vacía.
- Fix: se puntúan los candidatos descartando los que no son la velocidad real (solicitada,
  botón, limitador, mostrada…) y **priorizando el que está en una trama que sí se captura**.
  Verificado: ahora elige `Vitesse véhicule` de la Trame 01. Se loguea cuál eligió, para poder
  auditarlo en el próximo log.

## [2026-07-29] — "Subir logs" ahora sube TODO log/ (informes incluidos) + limpia lo viejo

- **Sube TODO lo que haya en `log/`** (no solo sesion/consola/reporte/ensayo): también los
  `conduccion_*`, informes, PDFs, cualquier archivo. Así los informes se guardan y suben solos.
- **Limpia lo viejo** para no acumular ni re-subir cosas viejas a git:
  - Local: `_limpiar_logs_viejos` borra los `sesion_/consola_` viejos dejando los 12 más
    recientes. Los INFORMES (`reporte_/ensayo_/conduccion_/informe_`) se conservan siempre.
  - Git: tras subir, `_borrar_stale_debug_logs` (API) borra de `debug-logs/` los archivos que ya
    no están en `log/` → git queda como espejo de lo actual. (El fallback git-CLI hace lo mismo
    con `git add -A`.)

## [2026-07-29] — Informe de conducción RICO (como el PDF) + foto final de todos los sensores

El informe de conducción salía muy pobre. Ahora es completo, estilo el informe grande:
- **Veredicto** con semáforo (detecta la mezcla pobre por el ajuste largo alto).
- **Tarjetas de datos clave** del manejo (prom + rango + qué esperar de cada uno).
- **Evolución por velocidad** de cada sensor (promedio por banda) — el análisis propio de la
  conducción.
- **Tabla de TODOS los sensores** del manejo (mín/prom/máx/σ), ordenados por cuánto se movieron.
- **Foto final**: al parar, el scanner lee UNA vez todos los sensores útiles del motor
  (`api_conduccion_detener`), así el informe tiene la completitud del informe grande además de la
  evolución por velocidad.
- HTML rico (imprimible a PDF con Ctrl+P) + TXT enriquecido + JSON con `para_experto`.

Confirmado en el auto (log 28/07 20:xx): la grabación anduvo (~13 min, velocidad 0-50 km/h) y el
ajuste largo bajó de ~30% (ralentí) a mayormente 0-14% (manejando) → **firma de fuga de vacío
confirmada** (la fuga domina en ralentí y se diluye con más aire). El reset de aprendizajes ahora
funciona (arranca en 0 y vuelve a subir con la fuga sin reparar).

## [2026-07-28] — Nuevo: "Grabar conducción" — línea temporal indexada por velocidad (en segundo plano)

Botón **"Grabar conducción"** al lado de "Grabar sesión" (en el tablero). Igual de simple: click y
graba en **segundo plano**, sin gráfico, sin cortar al cambiar de pantalla — solo para cuando le
das stop. Idea del usuario: enfocar todo en la **velocidad** como eje, para ver cómo reacciona el
auto a medida que acelera (en vez de datos dispersos).
- Backend: `estado.conduccion` + `_run_conduccion` (loop en background cada ~0.8 s que lee
  velocidad + todos los sensores clave de las 5 tramas, guardando `{t, vel, valores}`). Endpoints
  `iniciar` / `estado` / `detener` (genera el informe) / `reporte/{tipo}`. Respeta la pausa del
  reset. Corre estés en la pantalla que estés.
- Informe (`reporte.generar_conduccion`): **NO muestra la línea temporal cruda** (como pediste),
  la usa para el análisis: segmenta por **bandas de velocidad** (ralentí / baja / media / alta…) y
  muestra cómo evolucionó cada sensor en cada banda + datos clave (rango en todo el manejo) +
  bloque `para_experto`. HTML/JSON/TXT en `log/`.
- El botón se re-sincroniza al recargar la página (si seguía grabando).

## [2026-07-28] — Separados en DOS módulos: Detonaciones y Misfire (a pedido)

Se dividió el monitor combinado en dos módulos independientes en el menú F4R:
- **💥 Detonaciones (cascabeleo)**: solo Trame 05. Contador de detonaciones NUEVAS de la sesión
  por cilindro (delta) + histórico + ruido del motor. `GET /api/detonaciones/leer` (una sola
  trama → rápido, ya no arrastra la Trama 07 grande).
- **🔥 Misfire (fallo de encendido)**: solo Trame 07/08. Estado por cilindro (OK / ⚠ FALLA ahora)
  + **cuántas veces falló en la sesión** (cuenta las transiciones no-falla→falla) + **modo
  degradado** (ACTIVO/inactivo) + tasa de misfire. `GET /api/misfire/leer`.
- "Modo degradado por misfire" = la ECU corta la nafta al cilindro que falla para proteger el
  catalizador (un cilindro que no quema manda nafta cruda al escape y lo funde). ACTIVO = hay un
  misfire feo a revisar.

## [2026-07-28] — Nuevo módulo: Contador de detonaciones + misfire en vivo

El F4R expone contadores de cascabeleo por cilindro (Trame 05) y detección de misfire por
cilindro (Trame 07). Nuevo módulo **💥 Contador de detonaciones** (menú F4R):
- Cuenta las detonaciones **NUEVAS de la sesión** por cilindro (delta desde que se abre la
  pantalla, no el histórico de por vida). La tarjeta del cilindro **destella en rojo** cuando
  detona. Botón "Reiniciar contador de sesión" para volver a cero.
- Muestra por cilindro: nuevas de la sesión (grande), histórico, y estado de **misfire** (OK / ⚠
  FALLA).
- Abajo: total de detonaciones nuevas, **ruido del motor** en la ventana de detonación, tiempo de
  sesión, y modo degradado por misfire.
- Backend `GET /api/detonaciones/leer` (lee Trame 05 + Trame 07 de una); frontend con loop ~1s,
  baseline al abrir y delta en vivo. Solo perfil F4R.

## [2026-07-28] — Reset: modo "Automático" (prueba sesiones) + default Desarrollo, según ddt4all

Investigación del repo de ddt4all (`cedricp/ddt4all`, código real): (1) el patrón universal es
`10 xx` (abrir sesión) → `11 8x` (reset), como ya hicimos; (2) la sesión requerida NO está en el
código de ddt4all (vive en el archivo de ECU, fuera del repo), pero sus plugins de resets
"delicados" usan la sesión de **desarrollo/engineering**, reservando posventa (10C0) solo para
lecturas; (3) el bug de "falso éxito" viene del diálogo `ecu_command.py` de ddt4all que NO chequea
`7F` — nuestro endpoint nuevo sí lo chequea.

- **Default de sesión → Desarrollo (86)** (antes 85), siguiendo el patrón de ddt4all.
- **Modo "Automático"**: `POST /api/reaprendizaje/reset` con `session="auto"` prueba las sesiones
  en orden **86 → 85 → 81** y para en la primera que el ECU ACEPTA (respuesta positiva `51`),
  informando el resultado de cada intento (sesión + motivo + respuesta cruda). Es el default del
  panel: el usuario le da a Reiniciar y el sistema descubre solo qué sesión funciona.
- El panel muestra cada intento por sesión con su respuesta real del auto.

## [2026-07-28] — Reset de adaptativos COORDINADO: pausa lecturas, abre sesión, y muestra la respuesta REAL

Los logs del auto confirmaron por qué el reset no andaba: se mandaba `11 82` pero el ECU lo
rechazaba (`:12:NR: SubFunction Not Supported`) porque el reset corría en la sesión de lectura
(C0), no en la que necesita — y el barrido de grabación + el tester-present + `ensure_session`
**reabrían la sesión C0 en el medio, pisando** la que el usuario abría a mano (`10 85` → `50 85`
positivo, pero se perdía al instante). Encima el sistema mostraba "Rutina activada" aunque el
ECU había rechazado.

- **Pausa de lecturas por pantalla** (pedido del usuario): en la vista de reaprendizaje el
  scanner **no lee nada** (se pausan el barrido de grabación y el tester-present vía
  `estado.pausar_lecturas` + `POST /api/lecturas/pausar`; el `go()` del frontend pausa al entrar
  y reanuda al salir). Así nada pisa la sesión del reset. Las lecturas en vivo ya paraban al
  salir del tablero.
- **Reset coordinado y honesto** (`POST /api/reaprendizaje/reset`): pausa lecturas → abre la
  sesión elegida (`10 XX`) → manda el reset RAW **en esa sesión** de forma atómica bajo el lock
  (sin que `ensure_session` reabra la C0) → **lee e informa la respuesta REAL** del ECU (positiva
  `51..` o el rechazo `7F`/NR con su motivo). Ya no miente.
- **Panel rehecho**: elegís qué reiniciar (mode) Y en qué sesión (Programación/Desarrollo/
  Posventa/Defecto), con explicación. Muestra la respuesta cruda del auto, así se descubre en una
  prueba qué sesión acepta el reset (todavía no se sabe cuál — nunca se llegó a probar porque la
  sesión se pisaba).

## [2026-07-27] — Panel dedicado "Reaprendizajes" (reset de adaptativos, simple y explicado)

La pantalla "Inicio de rutinas" del F4R mezcla 9 menús con nombres crípticos (RLOCID, RENTOPT1…)
y 5 botones — imposible saber qué usar para resetear los trims. Nueva vista **🔄 Reaprendizajes
(reset ECU)** (`index.html`, menú F4R) que aísla SOLO el reset de aprendizajes con lenguaje claro:
- Opciones en criollo con descripción de cuándo usar cada una: **Ajustes de combustible (mezcla)**
  [recomendado], Regulación del ralentí, Medidor de par, Consumo, Todos los aprendizajes.
  (Request `ECUReset Reinit des Apprentissages`, input `ResetMode` 82/80/83/86/FF.)
- Advertencia clara ("hacelo DESPUÉS de reparar; si no, la corrección vuelve"), gate de modo
  avanzado con explicación, confirmación, y qué hacer después (ralentí caliente + andar un rato).
- Un solo botón. Verificado end-to-end en simulación (ResetMode 82 y FF ejecutan).

## [2026-07-27] — FIX: los procedimientos del F4R NO se ejecutaban (reset de adaptativos, rutinas) + contadores de detonación en el tablero

**Bug grave encontrado al verificar el reset de adaptativos**: `api_comando` (`server.py`) validaba
el request contra `tecu.screens`, un atributo que **NO existe** en `TranslatedECU` → `getattr`
devolvía `{}` → SIEMPRE daba "Request no válido para esta ECU" (400). Es decir, **ningún
procedimiento/rutina del F4R se podía ejecutar** (reset de aprendizajes, arranque de rutinas,
etc.), incluso con el modo avanzado activado.
- **Fix**: nuevo método `TranslatedECU.request_en_pantalla()` que valida contra las pantallas
  reales (`layout["screens"] → buttons → send → RequestName`). Verificado end-to-end: el reset
  de adaptativos ahora ejecuta con modo avanzado, se bloquea sin él (403), y un comando
  inventado sigue rechazado (400, anti-inyección intacto). `ObdGenerico` también tiene el método
  (devuelve False, no expone comandos).
- **Cómo resetear los trims** (para el usuario): conectar en F4R → activar modo avanzado (switch
  rojo) → Procedimientos → "Lancement routines" → "reinicialización de los aprendizajes".

**Contadores de detonación en el tablero** (`index.html`, `PRECARGADOS_VER` 3→4): se precargan los
4 contadores de cascabeleo por cilindro (`Compteur des coups de cliquetis, cylindre 1-4`) + el
ruido en la ventana de detonación. Sirven para ver si el motor detona AHORA (anotar, andar, ver
si suben) vs. historial viejo. Vienen en la Trame 05, ya capturada.

## [2026-07-27] — Chequeo: etapa de 1000 RPM + tiempos más cortos (no cansa mantener 3000)

Pedido del usuario: mantener 3000 RPM mucho tiempo cansa; y mejor tomar más puntos en el rango.
- **Etapas ahora: ralentí → 1000 → 1500 → 2000 → 3000** (antes ralentí→1500→2000→3000). Se agrega
  el punto de 1000 para ver mejor la evolución en la zona baja.
- **Tiempos más cortos**: `ESTABLE_SEG` 2.5→1.2 (mantener menos antes de capturar), `CAPTURA_SEG`
  5→2.5 (captura por etapa más corta), `RALENTI_SEG` 5→3. Cada etapa se resuelve en ~4 s en vez
  de ~7-8 s.
- El reporte (evolución por RPM, TXT/HTML/JSON) incluye la columna de 1000 RPM.
- (Pendiente en esta tanda: ampliar `DATOS_CLAVE_F4R` con más sensores que varían con RPM, para
  un paneo más completo — se está analizando con un agente.)

## [2026-07-27] — Chequeo: usar el régimen REAL (no la corrección de ralentí) para detectar las bandas

El log del chequeo reveló que `_param_rpm` agarraba **`Correction régime ralenti après-vente`**
(contiene "régime" pero es la corrección de ralentí, no las RPM) en vez de `Régime moteur`. Por
eso el medidor de RPM del chequeo mostraba un valor fijo/raro y parecía que "no leía las RPM"
(el reporte igual salía bien porque la captura usa el OBD 010C: 750→2956).

- **`_param_rpm`** ahora descarta correcciones/consignas/umbrales (`correction`, `consigne`,
  `ralenti`, `cible`, `seuil`, `min/max`, …) y prefiere el match exacto `Régime moteur`.
- **`_leer_rpm`** usa el **OBD 010C** (por 7DF) como fuente primaria de la detección de banda
  (es el régimen real, sin ambigüedad, ya probado correcto), con el nativo `Régime moteur` de
  fallback. Así el medidor muestra las RPM reales y las bandas 1500/2000/3000 se detectan bien.

## [2026-07-25] — Tablero F4R rápido de vuelta (el PID 03 colgaba 1s/ciclo) + paneo del chequeo veloz

El log midió los tiempos: la mediana de lectura del F4R es 33 ms (rápido), PERO el PID OBD
**`0103` (estado de lazo) tardaba ~1055 ms CADA ciclo** — el motor no responde ese PID y se
esperaba el timeout completo. Estaba en el tablero por defecto → 1 s perdido por refresco = la
lentitud que reportó el usuario. (El ajuste ±% por 7DF sí anda: `41 06 75`, ~25 ms.)

- **Sacado el PID 03 de los OBD extra** (`ecu_registry.OBD_EXTRA_PIDS` = `06,07,0C`): el estado
  de lazo ya se tiene NATIVO (`Etat stratégie régulation richesse`), sin timeout. Quitado también
  de los precargados del tablero.
- **Auto-descarte de PIDs OBD que no responden**: si un PID falla 3 veces seguidas se deja de
  leer (devuelve vacío al toque) en vez de colgar ~1 s esperando su timeout. Red de seguridad
  para cualquier PID no soportado.
- **Paneo del chequeo mucho más rápido**: leía TODOS los requests del motor (cientos, incluidos
  parámetros de estudio/config) → parecía que "nunca arrancaba". Ahora lee solo los **sensores
  observables** (`util`) y con presupuesto de 30 s (antes 90). Más logging de la fase de RPM
  para diagnosticar si aún fallara.

## [2026-07-22] — FIX: fuel trim OBD por 7DF (el motor no soporta OBD en 7E0) + chequeo usa RPM nativo

El log lo confirmó: leer los PID OBD (0106/0107/010C) en la dirección FÍSICA del motor (7E0)
devuelve `:11:NR: Service Not Supported` — el motor, en la sesión extendida del F4R, no soporta
OBD mode 01 ahí. Por eso el ajuste corto/largo salía vacío y el chequeo se quedaba sin RPM.
(El régimen y la riqueza NATIVOS sí se leían bien: 872 tr/min, factor 47.59%.)

- **Fuel trim ±%**: `_leer_obd_pid` (`ecu_registry.py`) ahora manda el PID al broadcast
  **FUNCIONAL 7DF** (donde el motor SÍ responde OBD, probado) con un cambio de header liviano
  (`AT SH 7DF` → PID → restaurar `AT SH 7E0`), sin reabrir sesión ni cambiar el CRA (el response
  llega en 7E8 = RX del motor, ya filtrado). Detecta y descarta respuestas negativas (`NR:`).
- **Chequeo**: `_param_rpm` ahora apunta al **régimen NATIVO** del F4R (salta el PID OBD 010C), y
  `_leer_rpm` lo lee primero (con el flow-control arreglado se lee perfecto) y deja el OBD como
  fallback. Así el chequeo detecta las RPM y arranca las etapas de aceleración.

## [2026-07-22] — El ajuste ±% se lee en la MISMA ECU del motor (una sola ECU = tablero rápido de vuelta)

El usuario notó que al agregar la ECU "obd" (7DF) al perfil F4R, el tablero se frenó: tener DOS
ECUs (motor 7E0 + obd 7DF) obligaba al WebSocket a saltar de dirección y reabrir el
direccionamiento en cada refresco. Y lo que quería ver es el ajuste ±% (STFT/LTFT estándar).

- **Fix**: el motor F4R está en la dirección OBD estándar (TX 7E0 / RX 7E8), así que ahora lee
  los PIDs OBD `0106` (ajuste corto ±%), `0107` (largo ±%), `03` (lazo) y `010C` (RPM) como
  **sensores extra en SU MISMA dirección** — no más ECU "obd" aparte. (`ecu_registry.py`:
  `TranslatedECU.obd_extra` + `_leer_obd_pid`; se configura solo en el motor en
  `load_curado_f4r`.) Todo el tablero del F4R queda en **una sola ECU** → sin saltos de
  dirección → vuelve a actualizar rápido, y con el ±% incluido.
- La ECU virtual "obd" (7DF) sigue existiendo solo para el **perfil genérico** (`load_generico`).
- El chequeo lee las RPM OBD desde el motor (o la 'obd' en genérico).
- Nota: requiere que el motor responda a OBD mode 01 en su dirección física 7E0 (estándar en el
  motor); a verificar en el auto. Si no respondiera, esos 4 sensores saldrían vacíos (inofensivo).

## [2026-07-22] — CONFIRMADO: el flow control desbloqueó el F4R + tablero en vivo fluido + fin del flood de escritura

**Confirmado en el auto real**: tras el fix de flow control, `received first frame only` = 0 y el
F4R ahora lee sus datos nativos multiframe a 38400 con el ELM327 común (log 22:14): régimen
`840 tr/min`, `Offset/Ganancia de aprendizaje de riqueza`, `Factor de enriquecimiento`, sonda
lambda, estado de lazo, etc. El usuario tenía razón: el dato estaba, solo faltaba pedir bien los
frames.

**Tablero en vivo fluido** (`server.py` WS + `index.html`): como los multiframe ahora sí se leen
(y tardan ~cientos de ms cada uno), leer TODO el ciclo y recién ahí mandar un paquete hacía que
el tablero pareciera actualizarse "cada ~10 s". Ahora el WS **envía sensor por sensor a medida
que los lee** (streaming); `applyLive` ya fusiona, así que cada valor aparece apenas está, sin
congelar el resto. Los fuel trim OBD (ECU secundaria) siguen cada ~2 s.

**Fin del flood de escritura** (`port.py`): el fix anterior de `_port_dead` cortó el spam de
lectura, pero al desconectar el cable seguía inundando con `Serial write error: WriteFile failed`
(miles de líneas) desde `write()`. Ahora `write()` también respeta `_port_dead`: avisa una vez y
no intenta más.

## [2026-07-22] — POSIBLE FIX DE FONDO: re-aplicar flow control tras AT SP (multiframe del F4R a 38400)

Revisión exhaustiva del dato de fuel trim del F4R (Sagem S3000): el ajuste de combustible SÍ
existe nativo (`Correction boucle de richesse` = short-term, `Offset/Gain apprentissage
regulation richesse` = long-term), pero vive en respuestas **multiframe** (requests 21A3, 21A7,
21A9, 1201-1203; minbytes 18-35) que fallan el flow-control a 38400 ("received first frame
only"). Lo mismo que el régimen 21A0 y casi todos los sensores enhanced.

**Causa raíz encontrada en `elm.py` `set_can_addr`**: la config de flow control (`AT FC SH/SD/SM`)
se setea (líneas ~1664-1666), pero después `set_can_500/250` hace `AT SP` (cambio de protocolo)
que **la resetea** en muchos ELM327/clones. El código re-aplicaba `CAF0/S0/AL` tras el `AT SP`
pero **se olvidaba del flow control** → el ELM deja de mandarle el FC frame a la ECU y los frames
consecutivos nunca llegan.

**Fix**: re-aplicar `AT FC SH/SD/SM` + `CFC1` después del `AT SP` (camino ELM327 clásico; el STPX
de los STN ya usa STCFCPA). Si funciona, **desbloquea TODO el enhanced del F4R a 38400** con el
ELM327 común: régimen nativo, fuel trim nativo, y el resto de los sensores multiframe. Falta
verificar en el auto real (no se puede probar en simulación).

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
