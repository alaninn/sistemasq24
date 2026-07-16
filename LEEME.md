# SISTEMASQ24 · Scanner Universal

Scanner de diagnóstico automotriz en español, fácil de usar, con interfaz web moderna.
Está 100% curado para el **Renault Mégane II F4R** y además puede **autodetectar otros
autos** leyendo sus computadoras y buscándolas en una base de +1900 ECUs.

Construido sobre el motor de comunicación de [DDT4All](https://github.com/cedricp/ddt4all)
(GPL-3.0), reutilizado y rebrandeado, con backend propio (FastAPI) y frontend nuevo.

---

## Descargar y usar en la notebook

1. **Bajar la última versión** desde GitHub:
   - Con git: `git clone https://github.com/alaninn/sistemasq24`
   - O desde la web: botón verde **Code → Download ZIP** y descomprimir.
2. **(Opcional) Base de ECUs para el scanner universal:** copiá tu archivo `ecu.zip` a
   `megane2_f4r/vendor/sistemasq24/ecu.zip`. **No hace falta para el Mégane II F4R** (ese
   usa los archivos de `original/`); solo se necesita para autodetectar OTROS autos.
3. **Doble clic en `megane2_f4r/INICIAR_SCANNER.bat`**. La primera vez, si el equipo no tiene
   Python, lo instala solo, arma el entorno e instala lo necesario desde `wheels/` (sin
   internet). Después abre el navegador en `http://127.0.0.1:8073`.

> Funciona **sin internet** (ideal para el auto en movimiento): todas las librerías van en
> `wheels/` y el frontend no usa recursos externos.

Cada vez que quieras probar la última versión: borrás la carpeta y volvés a bajar/descomprimir.
Lo único que conviene conservar aparte es tu `ecu.zip` (que cargás a mano) y la carpeta `log/`
con tus grabaciones.

---

## Cómo usarlo

Al entrar hay 4 tarjetas:
- **Testear Scanner** — probá que el adaptador ELM327 responde.
- **Scanner Universal / Escanear Auto** — detecta las computadoras del auto conectado y arma
  su perfil automáticamente (con barra de progreso).
- **Seleccionar Vehículo** — atajo directo: elegí **Mégane II F4R** (100% curado). Los demás
  modelos entran por autodetección.

Una vez cargado un auto, aparece el menú completo:
1. **Tablero en vivo** — los sensores estándar del motor (RPM, temp agua/aire, MAP, batería,
   velocidad, mariposa, pedal, sondas lambda, inyección…) en tiempo real. Botón En vivo /
   Congelar para fijar valores.
2. **Analizador de Ondas** — visualizá sensores como oscilograma en tiempo real; buscador para
   elegir, hasta 6 sensores, en un gráfico solapado o en grillas separadas. Exportá a CSV.
3. **Códigos de falla (DTC)** — lee de una vez las fallas de todas las computadoras.
4. **Elegir sensores** — buscá y marcá cuáles ver (se guardan solos).
5. **Actuadores** — encendé/apagá piezas para probarlas (luces, A/C, ventiladores…). Necesita
   **modo avanzado**.
6. **Módulos (ECU)** — explorá cada sistema con pantallas interactivas.
7. **Procedimientos** (solo F4R curado) — reset de aprendizajes, purga de frenos ABS,
   calibración de dirección, diagnóstico de batería/alternador, reset de service, etc.
8. **Adaptador** y **Memoria (avanzado)**.
9. **Modo avanzado** (arriba a la derecha) — habilita comandos que MODIFICAN el auto. Apagado
   por defecto; al activarlo la interfaz se tiñe de rojo.

### Grabar la sesión
Botón **"Grabar sesión"** arriba a la derecha: graba todo (comandos, respuestas, DTC,
actuadores…) en `log/sesion_<fecha>.txt` y `.json`.

---

## Las 6 ECUs del Mégane II F4R (confirmadas por escaneo real)

| Módulo | Archivo |
|---|---|
| Motor / Inyección (F4R) | `S3000_AD_CAN_3_X84ph2_S` |
| Frenos ABS / ESP | `Abs_X84_Bosch8.1_V1.3` |
| Airbag / Retención | `RC5_P1_P2_modifie_le20-04-2007_bis` |
| Caja de conexiones (UCH/USM) | `USM_X84_C5_45` |
| Dirección asistida | `DAE_X84_Serie_V1` |
| Tablero / Instrumentos | `Tdb_BCEKL84_serie_4emeRev` |

## Estructura

```
megane2_f4r/
├── INICIAR_SCANNER.bat      ← doble clic para arrancar (Windows)
├── wheels/                  ← librerías para instalar sin internet
├── original/  es/  tools/   ← ECUs del F4R, traducciones, memoria tm.json
├── vendor/sistemasq24/      ← motor de comunicación (core de ddt4all rebrandeado)
│   └── ecu.zip              ← (lo cargás a mano; base para el scanner universal)
└── app/                     ← backend (server.py, ecu_registry.py, sq24_scanner.py) + web/
```

## Nota legal

Basado en DDT4All (GPL-3.0): si redistribuís esta versión debe seguir siendo GPL-3.0 con el
código disponible. Trabajar sobre la red CAN puede dañar el vehículo — usá el modo avanzado
solo si sabés lo que hacés.
