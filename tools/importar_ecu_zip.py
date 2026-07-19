# -*- coding: utf-8 -*-
"""Importa un ecu.zip nuevo (ej. la base comunitaria de oct-2022, ~3086 ECUs) a la
estructura del repo: lo valida, muestra el diff contra la base actual, lo copia a
vendor/sistemasq24/ecu.zip y lo re-parte en ecu.zip.part* (<95 MB) para que entre en
GitHub y `app/run.py._armar_ecu_zip()` lo reconstruya solo.

Uso:
    python tools/importar_ecu_zip.py  RUTA_AL_NUEVO_ecu.zip

No borra nada hasta confirmar que el zip nuevo es válido y tiene MÁS ECUs que el actual.
"""
import sys
import zipfile
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "sistemasq24"
ZIP_DESTINO = VENDOR / "ecu.zip"
TAM_PARTE = 95 * 1024 * 1024   # 95 MB por parte (< límite de 100 MB de GitHub)


def _contar(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        return sum(1 for n in z.namelist() if n.lower().endswith(".json") and not n.endswith(".layout"))


def _repartir(zip_path):
    for viejo in sorted(VENDOR.glob("ecu.zip.part*")):
        viejo.unlink()
    data = zip_path.read_bytes()
    n = 0
    for i in range(0, len(data), TAM_PARTE):
        parte = VENDOR / f"ecu.zip.part{n:02d}"
        parte.write_bytes(data[i:i + TAM_PARTE])
        print(f"   escrita {parte.name} ({parte.stat().st_size/1e6:.1f} MB)")
        n += 1
    return n


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    nuevo = Path(sys.argv[1])
    if not nuevo.exists():
        print(f"No existe el archivo: {nuevo}")
        return 1
    try:
        with zipfile.ZipFile(nuevo) as z:
            if z.testzip() is not None:
                print("El zip está corrupto (testzip falló).")
                return 1
    except zipfile.BadZipFile:
        print("No es un zip válido.")
        return 1

    n_nuevo = _contar(nuevo)
    n_actual = _contar(ZIP_DESTINO) if ZIP_DESTINO.exists() else 0
    print(f"ECUs (JSON) en el zip NUEVO : {n_nuevo}")
    print(f"ECUs (JSON) en el zip ACTUAL: {n_actual}")
    if n_nuevo < n_actual:
        print("⚠ El zip nuevo tiene MENOS ECUs que el actual. Abortado (pasá --forzar para igual importarlo).")
        if "--forzar" not in sys.argv:
            return 1

    print(f"Copiando a {ZIP_DESTINO} …")
    ZIP_DESTINO.write_bytes(nuevo.read_bytes())
    print("Re-partiendo para GitHub …")
    partes = _repartir(ZIP_DESTINO)
    print(f"✓ Listo: {partes} partes. Ahora: git add vendor/sistemasq24/ecu.zip.part* && commit && push.")
    print("  (ecu.zip queda gitignoreado; se re-arma solo desde las partes al arrancar.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
