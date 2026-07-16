# -*- coding: utf-8 -*-
"""Aplica la memoria de traducción tm.json a los diccionarios es/*.es.json,
rellenando todos los campos "es" vacíos. Reporta cobertura final por ECU.
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
tm = json.load(open(BASE / "tools" / "tm.json", encoding="utf-8"))

def tr(s):
    return tm.get(s, "")

total_filled = total_missing = 0

def process(p):
    d = json.load(open(p, encoding="utf-8"))
    filled = missing = 0

    def setes(entry, key_orig):
        nonlocal filled, missing
        if not entry.get("es"):
            v = tr(key_orig)
            if v:
                entry["es"] = v
                filled += 1
            else:
                missing += 1

    for name, e in d.get("data", {}).items():
        setes(e, name)
        if "comment" in e and not e["comment"].get("es"):
            v = tr(e["comment"]["original"])
            if v: e["comment"]["es"] = v; filled += 1
            else: missing += 1
        if "unit" in e and not e["unit"].get("es"):
            v = tr(e["unit"]["original"])
            if v: e["unit"]["es"] = v; filled += 1
            else: missing += 1
        for le in e.get("lists", {}).values():
            if not le.get("es"):
                v = tr(le["original"])
                if v: le["es"] = v; filled += 1
                else: missing += 1

    for section in ("requests", "screens", "categories", "labels", "buttons"):
        for k, e in d.get(section, {}).items():
            setes(e, k)

    meta = d.get("_meta", {})
    if "funcname" in meta and not meta["funcname"].get("es"):
        v = tr(meta["funcname"]["original"])
        if v: meta["funcname"]["es"] = v; filled += 1

    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print(f"{p.name}: rellenadas {filled}, sin traducción {missing}")
    return filled, missing

for p in sorted((BASE / "es").glob("*.es.json")):
    f, m = process(p)
    total_filled += f
    total_missing += m

print(f"\nTOTAL: rellenadas {total_filled}, faltantes {total_missing}")
