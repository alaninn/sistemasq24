# Changelog — SISTEMASQ24

Todos los cambios importantes del scanner se anotan acá. El más reciente arriba.
Formato de fecha: AAAA-MM-DD.

Repo: https://github.com/alaninn/sistemasq24

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
