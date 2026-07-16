# -*- coding: utf-8 -*-
"""Vuelca las cadenas pendientes de traducir de tm.json, en orden (más usadas primero).
Uso: python dump_pending.py [inicio] [cantidad]
Imprime JSON: {"original": "", ...} listo para completar como lote.
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
TM_PATH = BASE / "tm.json"

def main(start=0, count=150):
    tm = json.load(open(TM_PATH, encoding="utf-8"))
    pending = [k for k, v in tm.items() if v == ""]
    chunk = pending[start:start + count]
    print(json.dumps({k: "" for k in chunk}, ensure_ascii=False, indent=0))
    print(f"\n# mostrando {len(chunk)} de {len(pending)} pendientes (desde {start})", file=sys.stderr)

if __name__ == "__main__":
    a = [int(x) for x in sys.argv[1:3]]
    main(*a)
