# -*- coding: utf-8 -*-
"""CLI interactivo para acceso directo al auto.

Uso:
    python cli.py

Comandos:
    21 <ID>          Leer parámetro (ej. "21 A0" = batería)
    22 <ID>          Leer sensor (ej. "22 F1" = RPM)
    3E               Tester present (keep-alive manual)
    17 <tipo>        Leer DTCs (ej. "17 FF" = todos)
    30 <act> <val>   Actuador (ej. "30 01 00 00" = luces)
    23 <tipo> <...>  Leer memoria (servicio ReadMemoryByAddress)
    hex <comando>    Enviar comando crudo en hex
    help             Ver comandos disponibles
    exit / quit      Salir

Ejemplo sesión:
    > 21 A0
    → Response: 61 A0 0C 61  (batería 12.54V)
    > 22 F1
    → Response: 62 F1 00 00  (RPM 0)
    > help
"""
import sys
import time
from pathlib import Path
from .ecu_connection import ECUConnection


def format_response(resp_dict):
    """Formatea respuesta en salida legible."""
    if not resp_dict["success"]:
        print(f"  ✗ Error: {resp_dict.get('error', '?')}")
        print(f"    Time: {resp_dict.get('time_ms', '?')} ms")
        return

    raw = resp_dict["response"]
    ms = resp_dict["time_ms"]

    # Clasificar tipo de respuesta
    if raw.startswith("7E"):
        tipo = "📋 Sesión OK"
    elif raw.startswith("7F"):
        print(f"  ✗ Comando rechazado (NRC: {raw[4:6]})")
        print(f"    Time: {ms} ms")
        return
    elif raw.startswith("6"):
        tipo = "✓ Datos"
    else:
        tipo = "? Respuesta"

    print(f"  {tipo}")
    print(f"  HEX: {raw}")
    print(f"  Time: {ms} ms")

    # Intentar interpretar valores comunes
    if raw.startswith("61"):  # Respuesta a 21 (lectura parámetro)
        _interpret_21_response(raw)
    elif raw.startswith("62"):  # Respuesta a 22 (lectura sensor)
        _interpret_22_response(raw)


def _interpret_21_response(hex_resp):
    """Intenta decodificar respuesta de 21 (lecturas de parámetro)."""
    # Ejemplos: 61 A0 0C 61 (batería), 61 F4 12 34 (temp)
    if len(hex_resp) < 6:
        return

    # Solo mostrar info si es interesante
    try:
        data_bytes = hex_resp[6:]  # Skip "61 XX"
        if len(data_bytes) >= 4:
            print(f"  Bytes de datos: {data_bytes}")
    except Exception:
        pass


def _interpret_22_response(hex_resp):
    """Intenta decodificar respuesta de 22 (sensores)."""
    # Similar a 21
    try:
        data_bytes = hex_resp[6:]  # Skip "62 XX"
        if len(data_bytes) >= 4:
            print(f"  Bytes de datos: {data_bytes}")
    except Exception:
        pass


def print_help():
    """Muestra ayuda."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║          DEBUG CLI — Acceso directo al auto                  ║
╚══════════════════════════════════════════════════════════════╝

Comandos diagnósticos:
  21 <ID>               Leer parámetro (ej: "21 A0" = batería)
  22 <ID>               Leer sensor (ej: "22 F1" = RPM)
  17 [FF | tipo]        Leer DTCs (ej: "17 FF" todos, "17 01" presentes)
  30 <act> <val> <val>  Actuador (ej: "30 01 00 00" = encender luces)
  23 <tipo> <addr> <cnt> Leer memoria (ej: "23 00 01 23 10")
  3E                    Keep-alive manual (si se para tester present)

Utilidades:
  hex <comando>         Enviar hex crudo (ej: "hex 3E")
  help                  Esta pantalla
  exit / quit           Salir

Valores comunes (Mégane II F4R):
  Batería:              21 A0
  RPM:                  22 F1
  Temperatura motor:    22 05
  Velocidad:            22 0D

Ejemplo:
  > 21 A0
  > 22 F1
  > 17 FF
  > exit
""")


def main():
    """Punto de entrada principal del CLI."""
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║   DEBUG CLI — Acceso interactivo al auto (Mégane II F4R)      ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")

    # Conectar
    conn = ECUConnection()
    print("[CONECTANDO...]")
    if not conn.detect_and_connect():
        print("[FALLO] No se pudo conectar al ELM327")
        return

    print("\n[ABRIENDO SESIÓN DIAGNÓSTICA...]")
    if not conn.open_session():
        print("[FALLO] No se pudo abrir sesión")
        conn.close()
        return

    print("\n[LISTO] Escribí comandos o 'help' para ver opciones\n")

    try:
        while True:
            try:
                cmd = input("> ").strip()
            except KeyboardInterrupt:
                print("\n[Ctrl+C detectado]")
                break
            except EOFError:
                print("\n[EOF]")
                break

            if not cmd:
                continue

            # Parsear comando
            parts = cmd.split()
            cmd_type = parts[0].lower()

            # Comandos especiales
            if cmd_type in ("exit", "quit"):
                print("[Cerrando...]")
                break
            elif cmd_type == "help":
                print_help()
            elif cmd_type == "hex":
                # Enviar hex crudo
                if len(parts) < 2:
                    print("  Uso: hex <comando>\n")
                    continue
                hex_cmd = " ".join(parts[1:])
                print(f"  Enviando: {hex_cmd}")
                resp = conn.send_command(hex_cmd)
                format_response(resp)
            else:
                # Asumir que es comando diagnóstico (21, 22, 17, 30, etc)
                hex_cmd = " ".join(parts)
                resp = conn.send_command(hex_cmd)
                format_response(resp)

            print()  # línea en blanco
    finally:
        conn.close()
        print("\n[SESIÓN CERRADA]\n")


if __name__ == "__main__":
    main()
