# -*- coding: utf-8 -*-
"""Fusiona un lote de traducciones {original: español} dentro de tm.json.
Uso: python merge_batch.py lote.json
Valida que cada clave exista en tm.json (evita claves con typos que se perderían).
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
TM_PATH = BASE / "tm.json"

def main(batch_file):
    tm = json.load(open(TM_PATH, encoding="utf-8"))
    batch = json.load(open(batch_file, encoding="utf-8"))
    unknown, merged, overwritten = [], 0, 0
    for k, v in batch.items():
        if k not in tm:
            unknown.append(k)
            continue
        if tm[k] and tm[k] != v:
            overwritten += 1
        tm[k] = v
        merged += 1
    with open(TM_PATH, "w", encoding="utf-8") as f:
        json.dump(tm, f, ensure_ascii=False, indent=0)
    pending = sum(1 for v in tm.values() if v == "")
    print(f"fusionadas: {merged}  sobrescritas: {overwritten}  desconocidas: {len(unknown)}")
    for k in unknown[:10]:
        print("  ??", repr(k[:80]))
    print(f"PENDIENTES: {pending}")

if __name__ == "__main__":
    main(sys.argv[1])
