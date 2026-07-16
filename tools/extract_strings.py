# -*- coding: utf-8 -*-
"""Extrae todas las cadenas traducibles de una ECU de DDT4All (.json + .json.layout)
y genera/actualiza el diccionario de traducción es/<ecu>.es.json.

Estructura del diccionario generado:
{
  "ecuname": "...",
  "funcname": {"original": "...", "es": ""},
  "data": {  # parámetros/sensores
     "<nombre original>": {"es": "", "ayuda": "", "comment": {"original": "...", "es": ""},
                            "unit": {"original": "...", "es": ""},
                            "lists": {"<id>": {"original": "...", "es": ""}}}
  },
  "requests": {"<nombre original>": {"es": ""}},
  "screens": {"<nombre original>": {"es": ""}},
  "categories": {"<nombre original>": {"es": ""}},
  "labels": {"<texto original>": {"es": ""}},   # etiquetas libres del layout
  "buttons": {"<texto original>": {"es": ""}}
}
Solo se crean entradas con texto visible; claves ya traducidas se conservan al re-ejecutar.
"""
import json
import sys
from pathlib import Path

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def merge_entry(store, key, template):
    """Crea la entrada si no existe; si existe conserva las traducciones hechas."""
    if key not in store:
        store[key] = template
    return store[key]

def extract(ecu_json_path: Path, layout_path: Path, out_path: Path):
    d = load(ecu_json_path)
    L = load(layout_path) if layout_path.exists() else {"screens": {}, "categories": {}}

    if out_path.exists():
        out = load(out_path)
    else:
        out = {}

    out.setdefault("ecuname", d.get("ecuname", ""))
    fn = d.get("obd", {}).get("funcname", "")
    if fn:
        e = merge_entry(out.setdefault("_meta", {}), "funcname", {"original": fn, "es": ""})

    data_out = out.setdefault("data", {})
    for name, item in d.get("data", {}).items():
        entry = merge_entry(data_out, name, {"es": "", "ayuda": ""})
        c = item.get("comment", "")
        if c:
            entry.setdefault("comment", {"original": c, "es": ""})
            entry["comment"]["original"] = c
        u = item.get("unit", "")
        if u:
            entry.setdefault("unit", {"original": u, "es": ""})
        lists = item.get("lists", {})
        if lists:
            lo = entry.setdefault("lists", {})
            for lid, txt in lists.items():
                if isinstance(txt, str) and txt.strip():
                    le = merge_entry(lo, lid, {"original": txt, "es": ""})
                    le["original"] = txt

    req_out = out.setdefault("requests", {})
    for r in d.get("requests", []):
        n = r.get("name", "")
        if n:
            merge_entry(req_out, n, {"es": ""})

    scr_out = out.setdefault("screens", {})
    cat_out = out.setdefault("categories", {})
    lab_out = out.setdefault("labels", {})
    btn_out = out.setdefault("buttons", {})

    for sname, scr in L.get("screens", {}).items():
        merge_entry(scr_out, sname, {"es": ""})
        for lab in scr.get("labels", []):
            t = (lab.get("text") or "").strip()
            if t:
                merge_entry(lab_out, t, {"es": ""})
        for b in scr.get("buttons", []):
            t = (b.get("text") or "").strip()
            if t:
                merge_entry(btn_out, t, {"es": ""})

    for cname in L.get("categories", {}).keys():
        merge_entry(cat_out, cname, {"es": ""})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)

    # estadísticas
    def pend(store, field="es"):
        n = 0
        for v in store.values():
            if isinstance(v, dict) and not v.get(field):
                n += 1
        return n
    nlists = sum(len(v.get("lists", {})) for v in data_out.values())
    print(f"{ecu_json_path.name}:")
    print(f"  data(nombres): {len(data_out)}  requests: {len(req_out)}  screens: {len(scr_out)}"
          f"  categories: {len(cat_out)}  labels: {len(lab_out)}  buttons: {len(btn_out)}  valores-lista: {nlists}")
    total = len(data_out) + len(req_out) + len(scr_out) + len(cat_out) + len(lab_out) + len(btn_out) + nlists
    print(f"  TOTAL cadenas: {total}")
    return total

if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    orig = base / "original"
    esd = base / "es"
    total = 0
    for jf in sorted(orig.glob("*.json")):
        if jf.name.endswith(".layout"):
            continue
        layout = orig / (jf.name + ".layout")
        out = esd / (jf.stem + ".es.json")
        total += extract(jf, layout, out)
    print(f"\nTOTAL GENERAL: {total} cadenas")
