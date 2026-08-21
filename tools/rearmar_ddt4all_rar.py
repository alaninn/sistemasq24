# -*- coding: utf-8 -*-
"""Reconstruye `upstream/ddt4all.rar` desde sus partes (`ddt4all.rar.part*`).

A diferencia de `ecu.zip` (que `app/run.py` re-arma solo al arrancar porque el scanner lo
necesita para funcionar), este .rar es solo una copia archivada del proyecto ddt4all
original — no hace falta para correr el scanner, así que se re-arma a mano, solo si alguien
quiere el archivo completo.

Uso:
    python tools/rearmar_ddt4all_rar.py
"""
import sys
from pathlib import Path

# En Windows, la consola por defecto (cp1252) no puede imprimir ✓/tildes — forzar UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UPSTREAM = Path(__file__).resolve().parent.parent / "upstream"
DESTINO = UPSTREAM / "ddt4all.rar"


def main():
    partes = sorted(UPSTREAM.glob("ddt4all.rar.part*"))
    if not partes:
        print("No hay partes (ddt4all.rar.part*) en upstream/.")
        return 1
    print(f"Re-armando desde {len(partes)} partes …")
    with open(DESTINO, "wb") as out:
        for p in partes:
            out.write(p.read_bytes())
    print(f"✓ Listo: {DESTINO} ({DESTINO.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
