# -*- coding: utf-8 -*-
"""Conexión directa al ELM327 y gestión de sesión diagnóstica.

Este módulo reusa el core de ddt4all para:
- Detectar automáticamente el puerto ELM327
- Abrir sesión diagnóstica (10C0)
- Mantener tester present (3E cada 1.5s)
- Enviar comandos crudos y recibir respuestas
"""
import sys
import time
import threading
from pathlib import Path

# Bootstrap: importar sistemasq24 (core) desde vendor
APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR / "vendor"))

from sistemasq24.core.elm import elm
from sistemasq24.core.elm import elm_device
from sistemasq24 import options


class ECUConnection:
    """Interfaz simplificada para conectar y comunicar con el auto."""

    def __init__(self):
        self.elm_instance = None
        self.session_active = False
        self._tester_present_thread = None
        self._stop_tester = threading.Event()
        self._lock = threading.RLock()

    def detect_and_connect(self, auto_detect=True):
        """Detecta el puerto ELM327 y establece conexión.

        Returns:
            bool: True si conexión exitosa, False si falló
        """
        if auto_detect:
            # Detectar puertos disponibles
            ports = elm_device.find_serial_ports()
            if not ports:
                print("[ERROR] No ELM327 adapter found. Check USB connection.")
                return False
            port = ports[0]
            print(f"[INFO] Detected ELM327 on port {port}")
        else:
            port = "COM3"  # default fallback

        try:
            # Crear instancia ELM
            self.elm_instance = elm.Elm()
            self.elm_instance.port = port
            self.elm_instance.speed = 38400

            # Conectar
            if not self.elm_instance.open_serial():
                print(f"[ERROR] Could not open {port}")
                return False

            print(f"[OK] Connected to ELM327 on {port}")
            options.elm = self.elm_instance

            # Inicializar CAN (11-bit ID, 500k baud — estándar Mégane II)
            self._send_raw("AT Z")  # reset
            self._send_raw("ATE 0")  # echo off
            self._send_raw("ATL 0")  # linefeeds off
            self._send_raw("ATS 0")  # spaces off
            self._send_raw("AT SP 6")  # CAN 500k

            print("[OK] ELM initialized for CAN 500k")
            return True
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")
            return False

    def open_session(self, ecu_can_addr="000000F1"):
        """Abre sesión diagnóstica (10C0 para After-Sales).

        Args:
            ecu_can_addr: CAN RX address (default Renault After-Sales)

        Returns:
            bool: True si sesión abierta
        """
        if not self.elm_instance:
            print("[ERROR] No ELM connection")
            return False

        try:
            # Configurar dirección CAN de recepción
            self._send_raw(f"AT CRA {ecu_can_addr}")

            # Enviar sesión diagnóstica 10C0
            resp = self._send_raw("10 C0")

            if resp and "7E" in resp.upper():  # respuesta positiva
                self.session_active = True
                print("[OK] Diagnostic session opened (10C0)")

                # Iniciar tester present en background
                self._start_tester_present()
                return True
            else:
                print(f"[ERROR] Session open failed: {resp}")
                return False
        except Exception as e:
            print(f"[ERROR] Session open exception: {e}")
            return False

    def _send_raw(self, command):
        """Envía comando crudo al ELM327 y devuelve respuesta."""
        if not self.elm_instance:
            return None
        try:
            with self._lock:
                return self.elm_instance.send_raw(command)
        except Exception as e:
            print(f"[SEND ERROR] {command}: {e}")
            return None

    def _start_tester_present(self):
        """Inicia thread que envía tester present (3E) cada 1.5s."""
        self._stop_tester.clear()
        self._tester_present_thread = threading.Thread(
            target=self._tester_present_loop, daemon=True
        )
        self._tester_present_thread.start()

    def _tester_present_loop(self):
        """Loop de tester present: envía 3E cada 1.5s."""
        while not self._stop_tester.is_set():
            try:
                time.sleep(1.5)
                with self._lock:
                    self.elm_instance.send_raw("3E")
            except Exception:
                pass

    def send_command(self, hex_command, timeout=2.0):
        """Envía comando diagnóstico y retorna respuesta.

        Args:
            hex_command: string con comando (ej. "21 A0" o "21A0")
            timeout: segundos para esperar respuesta

        Returns:
            dict con keys 'success', 'response', 'raw', 'time_ms'
        """
        if not self.session_active:
            return {"success": False, "error": "Session not open"}

        # Normalizar comando (quitar espacios, mayúsculas)
        cmd = hex_command.replace(" ", "").upper()

        t0 = time.time()
        try:
            with self._lock:
                resp = self.elm_instance.send_raw(cmd)
            elapsed_ms = round((time.time() - t0) * 1000, 1)

            if not resp or resp.strip() == "":
                return {
                    "success": False,
                    "error": "Empty response",
                    "raw": resp,
                    "time_ms": elapsed_ms
                }

            return {
                "success": True,
                "response": resp.strip(),
                "raw": resp,
                "time_ms": elapsed_ms
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "time_ms": round((time.time() - t0) * 1000, 1)
            }

    def close(self):
        """Cierra la sesión y la conexión."""
        self._stop_tester.set()
        if self._tester_present_thread:
            self._tester_present_thread.join(timeout=2)

        if self.elm_instance:
            try:
                self.elm_instance.close_serial()
                print("[OK] ELM connection closed")
            except Exception:
                pass

        self.session_active = False
