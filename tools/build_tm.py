# -*- coding: utf-8 -*-
"""Construye/actualiza la memoria de traducción global tm.json a partir de los
diccionarios es/*.es.json. Auto-rellena cadenas que no requieren traducción
(unidades, números, códigos, siglas). Las ya traducidas se conservan.
"""
import json
import re
from pathlib import Path
from collections import Counter

BASE = Path(__file__).resolve().parent.parent
TM_PATH = BASE / "tools" / "tm.json"

# Cadenas que se dejan idénticas (unidades y términos universales)
KEEP_AS_IS = {
    "OK", "V", "mV", "A", "mA", "Ohm", "ohm", "kOhm", "ms", "s", "min", "h",
    "%", "km", "km/h", "m", "mm", "cm", "bar", "mbar", "hPa", "kPa", "Pa",
    "g", "kg", "N", "Nm", "N.m", "Hz", "kHz", "rpm", "tr/min", "RPM",
    "g (m/s2)", "m/s2", "deg", "°", "°C", "C", "l", "L", "l/h", "mg/cp",
    "ABS", "ESP", "VIN", "ECU", "CAN", "LIN", "DTC", "OBD", "EOBD",
    "Airbag", "AIRBAG", "SRS", "UCH", "USM", "DAE", "TDB", "Tdb",
    "-", "--", "---", "?", "N/A", "NA",
}

RE_TRIVIAL = re.compile(
    r"^["                       # solo:
    r"0-9A-Fa-fxX\s\.,:;/\\\-\+\(\)\[\]#_$%=<>°"  # números, hex, signos
    r"]*$"
)

RE_VALUE_UNIT = re.compile(
    r"^\d+([.,]\d+)?\s*(Ohms?|kOhms?|Okhms?|kohms?|mV|V|mA|A|ms|s|Hz|kHz|%|bar|mbar|km/h|Km/H|rpm|tr/min|Nm|mm|cm|m)$",
    re.IGNORECASE,
)


# Identificadores tipo código (C_B_ActiveDiagTest, AllowedPowerGradient_DF...):
# se dejan tal cual — son nombres de constantes de calibración, no texto de UI.
RE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9]*(_[A-Za-z0-9]+)+$")

def is_trivial(s: str) -> bool:
    if s in KEEP_AS_IS:
        return True
    if RE_TRIVIAL.match(s):
        return True
    if RE_VALUE_UNIT.match(s.strip()):
        return True
    if RE_IDENTIFIER.match(s.strip()):
        return True
    return False

def collect():
    uniq = Counter()
    for p in sorted((BASE / "es").glob("*.es.json")):
        d = json.load(open(p, encoding="utf-8"))
        for name, e in d.get("data", {}).items():
            uniq[name] += 1
            if "comment" in e:
                uniq[e["comment"]["original"]] += 1
            if "unit" in e:
                uniq[e["unit"]["original"]] += 1
            for le in e.get("lists", {}).values():
                uniq[le["original"]] += 1
        for s in ("requests", "screens", "categories", "labels", "buttons"):
            for k in d.get(s, {}):
                uniq[k] += 1
    return uniq

def main():
    uniq = collect()
    tm = {}
    if TM_PATH.exists():
        tm = json.load(open(TM_PATH, encoding="utf-8"))

    added = auto = 0
    for s in uniq:
        if s not in tm:
            if is_trivial(s):
                tm[s] = s
                auto += 1
            else:
                tm[s] = ""
                added += 1
        elif tm[s] == "" and is_trivial(s):
            tm[s] = s
            auto += 1

    # ordenar por frecuencia descendente para traducir lo más usado primero
    ordered = {k: tm[k] for k in sorted(tm, key=lambda x: (-uniq.get(x, 0), x))}
    with open(TM_PATH, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=0)

    pending = sum(1 for v in ordered.values() if v == "")
    print(f"únicas: {len(ordered)}  auto-rellenadas ahora: {auto}  nuevas pendientes: {added}")
    print(f"PENDIENTES de traducir: {pending}")

if __name__ == "__main__":
    main()
