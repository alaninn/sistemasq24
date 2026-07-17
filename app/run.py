# -*- coding: utf-8 -*-
"""Lanza SISTEMASQ24: arranca el servidor local y abre el navegador.

Uso:
    <ruta-al-venv>/Scripts/python run.py
"""
import sys
import threading
import time
import webbrowser
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

# Hacer que 'import sistemasq24' funcione sin instalar el paquete completo (evita PyQt5).
# El core (base de ddt4all, ya rebrandeada) va empaquetado en megane2_f4r/vendor/sistemasq24.
for _cand in [
    APP_DIR.parent / "vendor",                        # megane2_f4r/vendor
    APP_DIR.parent.parent / "sistemasq24" / "src",    # dev: al lado
    APP_DIR.parent / "sistemasq24" / "src",
]:
    if (_cand / "sistemasq24" / "__init__.py").exists():
        sys.path.insert(0, str(_cand))
        break


def _armar_ecu_zip():
    """Re-arma vendor/sistemasq24/ecu.zip desde sus partes (ecu.zip.part*) si falta.
    El zip (142 MB) se sube a GitHub partido en piezas <100 MB; acá se reconstruye solo."""
    vendor = APP_DIR.parent / "vendor" / "sistemasq24"
    zip_final = vendor / "ecu.zip"
    if zip_final.exists():
        return
    partes = sorted(vendor.glob("ecu.zip.part*"))
    if not partes:
        return  # sin partes ni zip: el F4R igual funciona (usa original/)
    try:
        with open(zip_final, "wb") as out:
            for p in partes:
                out.write(p.read_bytes())
        print(f"  ecu.zip re-armado desde {len(partes)} partes.")
    except Exception as e:
        print(f"  (aviso: no se pudo armar ecu.zip: {e})")


_armar_ecu_zip()

HOST = "127.0.0.1"
PORT = 8073
URL = f"http://{HOST}:{PORT}/"


def _open_browser():
    time.sleep(1.5)
    try:
        webbrowser.open(URL)
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    print("=" * 54)
    print("  SISTEMASQ24 · Scanner Universal")
    print(f"  Abrí en el navegador:  {URL}")
    print("  (Ctrl+C para detener)")
    print("=" * 54)
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("server:app", host=HOST, port=PORT, log_level="warning")
