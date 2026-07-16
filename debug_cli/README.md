# DEBUG CLI — Acceso directo interactivo al auto

Servidor Python puro que te permite conectarte directamente al ELM327 y enviar comandos diagnósticos **en tiempo real**, sin interfaz web.

## Uso

**En la notebook con el ELM327 conectado al auto:**

```bash
# Opción 1: doble clic en INICIAR.bat
INICIAR.bat

# Opción 2: línea de comando (con venv activo)
python -m debug_cli.cli
```

## Ejemplo de sesión

```
> 21 A0
  ✓ Datos
  HEX: 61 A0 0C 61
  Time: 18.3 ms

> 22 F1
  ✓ Datos
  HEX: 62 F1 00 00
  Time: 15.1 ms

> 17 FF
  ✓ Datos
  HEX: 59 02 01 12
  Time: 42.5 ms

> exit
[SESIÓN CERRADA]
```

## Comandos disponibles

| Comando | Uso | Ejemplo |
|---------|-----|---------|
| `21` | Leer parámetro (servicio 21) | `21 A0` (batería) |
| `22` | Leer sensor (servicio 22) | `22 F1` (RPM) |
| `17` | Leer DTCs | `17 FF` (todos) |
| `30` | Activar actuador | `30 01 00 00` (luces) |
| `23` | Leer memoria | `23 00 01 23 10` |
| `3E` | Keep-alive manual | `3E` |
| `hex` | Comando crudo | `hex 3E` |
| `help` | Ver comandos | `help` |
| `exit` / `quit` | Salir | `exit` |

## Valores útiles (Mégane II F4R)

```
Batería           21 A0
RPM               22 F1
Temp motor        22 05
Velocidad         22 0D
Dist parcial      21 F4
Odomètre total    21 95
```

## Qué pasa "bajo el capó"

1. **Detección automática del ELM327** en puertos USB disponibles.
2. **Configuración CAN**: ATZ, ATE0, ATL0, ATS0, AT SP 6 (500k).
3. **Sesión diagnóstica 10C0** (After-Sales).
4. **Tester present automático** (3E cada 1.5s en background).
5. **Cada comando** registra:
   - Comando enviado
   - Respuesta en hex
   - Tiempo de latencia en ms
6. **Interpretación básica** de respuestas comunes (batería, sensores).

## Ventajas vs el scanner web

- **Interactivo**: cambiás de comando al toque, sin recargar pantalla.
- **Bajo nivel**: ves exactamente qué va y qué viene del auto.
- **Debugging**: perfecto para explorar respuestas raras, tiempos de latencia, comandos vacíos.
- **No interfiere**: corre en paralelo con el scanner web (puertos diferentes).

## Limitaciones

- No tiene ayudas "modo niño" (es debug puro).
- No interpreta todos los servicios (31, 3B, 3D, etc., son parcialmente soportados).
- Requiere conexión directa al auto (no remota).

## Flujo recomendado con Claude

1. Llevás la notebook al auto.
2. Abrís dos terminales:
   - Una con `INICIAR_SCANNER.bat` (interfaz web en http://127.0.0.1:8073).
   - Otra con `debug_cli/INICIAR.bat` (CLI interactivo).
3. Usás `claude --continue` en una tercera ventana.
4. Yo te guío desde aquí:
   - "Probá `21 A0`" → ejecutás en CLI → me muestras el output → analizo.
   - "Ahora `22 F1`" → lo mismo.
   - Si algo falla, hacemos cambios de código al toque y testeamos de nuevo.

Así tenemos debugging **en tiempo real con el auto real**, sin ciclo de "graba log → trae → analiza".
