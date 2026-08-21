# -*- coding: utf-8 -*-
"""Parte `upstream/ddt4all.rar` (copia archivada del proyecto ddt4all original, GPL-3.0 —
NO hace falta para correr el scanner, ya está vendoreado/rebrandeado en
vendor/sistemasq24/core; esto es solo referencia histórica) en `ddt4all.rar.part*` de
<95 MB para que entre en GitHub (límite 100 MB por archivo).

Uso:
    python tools/repartir_ddt4all_rar.py  RUTA_al_ddt4all.rar

El .rar completo queda gitignoreado; para reconstruirlo ver `tools/rearmar_ddt4all_rar.py`.
"""
import hashlib
import sys
from pathlib import Path

# En Windows, la consola por defecto (cp1252) no puede imprimir ✓/tildes — forzar UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UPSTREAM = Path(__file__).resolve().parent.parent / "upstream"
DESTINO = UPSTREAM / "ddt4all.rar"
TAM_PARTE = 90_000_000   # 90 MB (decimal) por parte, con margen real bajo el límite de 100 MB de GitHub


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _repartir(rar_path):
    UPSTREAM.mkdir(parents=True, exist_ok=True)
    for viejo in sorted(UPSTREAM.glob("ddt4all.rar.part*")):
        viejo.unlink()
    data = rar_path.read_bytes()
    n = 0
    for i in range(0, len(data), TAM_PARTE):
        parte = UPSTREAM / f"ddt4all.rar.part{n:02d}"
        parte.write_bytes(data[i:i + TAM_PARTE])
        print(f"   escrita {parte.name} ({parte.stat().st_size / 1e6:.1f} MB)")
        n += 1
    return n


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    rar = Path(sys.argv[1])
    if not rar.exists():
        print(f"No existe el archivo: {rar}")
        return 1

    print(f"Tamaño: {rar.stat().st_size / 1e6:.1f} MB")
    print("Calculando hash del original …")
    hash_original = _sha256(rar)
    print(f"  sha256: {hash_original}")

    if rar.resolve() != DESTINO.resolve():
        print(f"Copiando a {DESTINO} …")
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        DESTINO.write_bytes(rar.read_bytes())

    print("Repartiendo para GitHub …")
    partes = _repartir(DESTINO)

    # Verificación: re-armar en memoria y comparar hash (sin escribir el .rar final).
    print("Verificando integridad de las partes …")
    h = hashlib.sha256()
    for p in sorted(UPSTREAM.glob("ddt4all.rar.part*")):
        h.update(p.read_bytes())
    if h.hexdigest() != hash_original:
        print("✗ ERROR: el hash de las partes no coincide con el original. Abortado.")
        return 1

    print(f"✓ Listo: {partes} partes, integridad verificada.")
    print("  Ahora: git add upstream/ddt4all.rar.part* && commit && push.")
    print("  (ddt4all.rar queda gitignoreado; para reconstruirlo, ver tools/rearmar_ddt4all_rar.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
