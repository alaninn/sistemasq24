# -*- coding: utf-8 -*-
"""Captura TODO lo que se imprime en la consola (CMD) a un archivo de log.

Cada arranque del sistema crea `log/consola_<fecha>.txt` que duplica stdout y stderr
(prints, warnings, tracebacks, logs de uvicorn/FastAPI, errores de importación…). Sirve
para atrapar errores que no aparecen en ningún otro lado: los que la app tira a la consola
antes de que el logger de sesión esté vivo, o cuando el proceso se cae.

Uso: llamar `consola_log.iniciar()` lo ANTES posible en el arranque (antes de importar
uvicorn/server), para que capture también los mensajes de inicio.
"""
import atexit
import datetime
import faulthandler
import sys
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "log"
_MAX_LOGS = 20            # cuántos consola_*.txt conservar (se borran los más viejos)
_archivo = None
_ruta = None


class _Tee:
    """Escribe en el stream original Y en el archivo de log a la vez."""

    def __init__(self, original, fh):
        self._orig = original
        self._fh = fh

    def write(self, texto):
        try:
            self._orig.write(texto)
        except Exception:
            pass
        try:
            self._fh.write(texto)
            self._fh.flush()      # flush inmediato: si el proceso se cae, no se pierde nada
        except Exception:
            pass
        return len(texto) if texto else 0

    def flush(self):
        for s in (self._orig, self._fh):
            try:
                s.flush()
            except Exception:
                pass

    # algunos consumidores (uvicorn/colorama) piden estos atributos del stream real
    def isatty(self):
        try:
            return self._orig.isatty()
        except Exception:
            return False

    def fileno(self):
        return self._orig.fileno()

    def __getattr__(self, nombre):
        return getattr(self._orig, nombre)


def _limpiar_viejos():
    try:
        logs = sorted(_LOG_DIR.glob("consola_*.txt"))
        for viejo in logs[:-_MAX_LOGS]:
            try:
                viejo.unlink()
            except Exception:
                pass
    except Exception:
        pass


def iniciar():
    """Arranca la captura de consola. Devuelve la ruta del log (o None si falló)."""
    global _archivo, _ruta
    if _archivo is not None:
        return _ruta
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        _limpiar_viejos()
        marca = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        _ruta = _LOG_DIR / f"consola_{marca}.txt"
        _archivo = open(_ruta, "a", encoding="utf-8", buffering=1)
        cab = (f"{'='*60}\n"
               f"  CONSOLA SISTEMASQ24 — {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n"
               f"  Python {sys.version.split()[0]} · {sys.platform}\n"
               f"{'='*60}\n")
        _archivo.write(cab)
        _archivo.flush()
        # duplicar stdout y stderr
        sys.stdout = _Tee(sys.__stdout__ or sys.stdout, _archivo)
        sys.stderr = _Tee(sys.__stderr__ or sys.stderr, _archivo)
        # volcar tracebacks de crashes duros (segfault, deadlock) al mismo archivo
        try:
            faulthandler.enable(file=_archivo)
        except Exception:
            pass
        # atrapar excepciones no manejadas (además de lo que ya sale por stderr)
        _hook_previo = sys.excepthook

        def _excepthook(exc_type, exc, tb):
            try:
                import traceback
                _archivo.write("\n*** EXCEPCIÓN NO MANEJADA ***\n")
                traceback.print_exception(exc_type, exc, tb, file=_archivo)
                _archivo.flush()
            except Exception:
                pass
            _hook_previo(exc_type, exc, tb)

        sys.excepthook = _excepthook
        atexit.register(_cerrar)
        return _ruta
    except Exception:
        return None


def ruta_actual():
    return str(_ruta) if _ruta else None


def _cerrar():
    try:
        if _archivo:
            _archivo.write(f"\n--- consola cerrada {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
            _archivo.flush()
            _archivo.close()
    except Exception:
        pass
