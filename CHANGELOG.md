# Changelog — SISTEMASQ24

Todos los cambios importantes del scanner se anotan acá. El más reciente arriba.
Formato de fecha: AAAA-MM-DD.

Repo: https://github.com/alaninn/sistemasq24

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
