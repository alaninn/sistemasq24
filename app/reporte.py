# -*- coding: utf-8 -*-
"""Genera el reporte del Chequeo General en HTML / JSON / TXT.

Recibe la estructura de datos que arma `chequeo.py` y produce tres archivos en `log/`:
- reporte_<fecha>.html : lindo, para leer una persona
- reporte_<fecha>.json : estructurado y completo, para pegarle a una IA
- reporte_<fecha>.txt  : texto plano legible

Para el perfil F4R evalúa los sensores contra `rangos_f4r.json` (OK/atención/fuera de rango).
Para otros perfiles solo muestra datos crudos + estadísticas.
"""
import json
import re
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR.parent / "log"
RANGOS_PATH = APP_DIR / "rangos_f4r.json"


def _cargar_rangos():
    try:
        d = json.loads(RANGOS_PATH.read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if not k.startswith("_")}
    except Exception:
        return {}


def _num(valor_str):
    """Extrae el número de 'valor unidad' (ej '89 °C' -> 89.0)."""
    try:
        return float(str(valor_str).split()[0])
    except (ValueError, IndexError):
        return None


def _evaluar(etiqueta, valor_str, rangos):
    """Evalúa un sensor contra los rangos (match por subcadena de la etiqueta).
    Devuelve {estado, rango?, nota?}. estado: ok | atencion | sin_rango."""
    el = etiqueta.lower()
    for clave, r in rangos.items():
        if clave in el:
            n = _num(valor_str)
            if n is None:
                return {"estado": "sin_rango"}
            if r["min"] <= n <= r["max"]:
                return {"estado": "ok", "rango": [r["min"], r["max"]], "nota": r.get("nota", "")}
            return {"estado": "atencion", "rango": [r["min"], r["max"]],
                    "nota": r.get("nota", ""),
                    "detalle": f"fuera del rango esperado {r['min']}–{r['max']} {r.get('unidad','')}"}
    return {"estado": "sin_rango"}


def _analizar(datos):
    """Agrega evaluaciones y un resumen a la estructura de datos."""
    rangos = _cargar_rangos() if datos.get("perfil") == "f4r" else {}
    total_sensores = 0
    n_ok = 0
    atencion = []       # [{ecu, sensor, valor, detalle}]
    total_dtcs = 0
    dtcs_lista = []

    for ecu in datos.get("ecus", []):
        evals = {}
        for etiqueta, valor in (ecu.get("sensores") or {}).items():
            total_sensores += 1
            ev = _evaluar(etiqueta, valor, rangos)
            evals[etiqueta] = ev
            if ev["estado"] == "ok":
                n_ok += 1
            elif ev["estado"] == "atencion":
                atencion.append({"ecu": ecu["nombre"], "sensor": etiqueta,
                                 "valor": valor, "detalle": ev.get("detalle", "")})
        ecu["evaluaciones"] = evals
        for d in (ecu.get("dtcs") or []):
            total_dtcs += 1
            dtcs_lista.append({"ecu": ecu["nombre"], "codigo": d.get("codigo"),
                               "descripcion": d.get("descripcion", "")})

    datos["resumen"] = {
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sensores_totales": total_sensores,
        "sensores_ok": n_ok,
        "sensores_en_atencion": len(atencion),
        "atencion": atencion,
        "dtcs_totales": total_dtcs,
        "dtcs": dtcs_lista,
        "con_rangos": bool(rangos),
    }
    return datos


def _tabla_evolucion(datos):
    """Arma la evolución por RPM: {sensor: {ralenti, 1500, 2000, 3000}} con el promedio."""
    etapas = datos.get("rpm_etapas", {})
    orden = ["ralenti", "1500", "2000", "3000"]
    sensores = {}
    for et in orden:
        stats = (etapas.get(et) or {}).get("estadisticas", {})
        for sensor, s in stats.items():
            sensores.setdefault(sensor, {"unidad": s.get("unidad", "")})
            sensores[sensor][et] = s.get("promedio")
    return orden, sensores


# ----------------------------------------------------------------- salidas
def _txt(datos):
    r = datos["resumen"]
    L = []
    L.append("=" * 70)
    L.append("  CHEQUEO GENERAL DEL AUTO — SISTEMASQ24")
    L.append(f"  Vehículo: {datos.get('vehiculo')}   |   {datos.get('fecha')}")
    L.append("=" * 70)
    L.append("")
    L.append("RESUMEN")
    L.append(f"  Sensores leídos: {r['sensores_totales']}  |  OK: {r['sensores_ok']}  |  "
             f"En atención: {r['sensores_en_atencion']}  |  Códigos de falla: {r['dtcs_totales']}")
    if not r["con_rangos"]:
        L.append("  (Sin rangos de referencia para este perfil: los valores van crudos.)")
    L.append("")
    if r["atencion"]:
        L.append("⚠ SENSORES EN ATENCIÓN")
        for a in r["atencion"]:
            L.append(f"  · [{a['ecu']}] {a['sensor']}: {a['valor']}  — {a['detalle']}")
        L.append("")
    if r["dtcs"]:
        L.append("🚨 CÓDIGOS DE FALLA (DTC)")
        for d in r["dtcs"]:
            L.append(f"  · [{d['ecu']}] {d['codigo']}: {d['descripcion']}")
        L.append("")
    # por ECU
    for ecu in datos.get("ecus", []):
        estado = "responde" if ecu.get("presente") else ("no responde" if ecu.get("presente") is False else "?")
        L.append("-" * 70)
        L.append(f"ECU: {ecu['nombre']}  [{estado}]")
        if ecu.get("identificacion"):
            for k, v in ecu["identificacion"].items():
                L.append(f"    {k}: {v}")
        L.append(f"  Sensores ({len(ecu.get('sensores', {}))}):")
        for etiqueta, valor in (ecu.get("sensores") or {}).items():
            ev = (ecu.get("evaluaciones") or {}).get(etiqueta, {})
            marca = {"ok": "✓", "atencion": "⚠", "sin_rango": " "}.get(ev.get("estado"), " ")
            L.append(f"    {marca} {etiqueta}: {valor}")
        L.append("")
    # evolución por RPM
    orden, sensores = _tabla_evolucion(datos)
    if sensores:
        L.append("=" * 70)
        L.append("EVOLUCIÓN DE SENSORES DEL MOTOR POR RPM (promedio)")
        L.append(f"  {'Sensor':<40} {'ralentí':>10} {'1500':>10} {'2000':>10} {'3000':>10}")
        for sensor, vals in sensores.items():
            fila = f"  {sensor[:40]:<40}"
            for et in orden:
                v = vals.get(et)
                fila += f" {('' if v is None else v):>10}"
            L.append(fila + f"  {vals.get('unidad','')}")
        L.append("")
    return "\n".join(L)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _html(datos):
    r = datos["resumen"]
    css = """body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0e141b;color:#e8eef4;margin:0;padding:24px;line-height:1.5}
    h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;border-bottom:1px solid #24303f;padding-bottom:6px;margin-top:28px}
    .sub{color:#8ea0b2;font-size:13px;margin-bottom:18px}
    .cards{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}
    .card{background:#161e27;border:1px solid #24303f;border-radius:10px;padding:14px 18px;min-width:120px}
    .card b{font-size:24px;display:block}
    table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
    th,td{text-align:left;padding:5px 8px;border-bottom:1px solid #1c2732}
    th{color:#8ea0b2}
    .ok{color:#4ade80}.warn{color:#ffab2e}.dim{color:#8ea0b2}
    .ecu{background:#131b23;border:1px solid #24303f;border-radius:10px;padding:14px 18px;margin:12px 0}
    .badge{display:inline-block;padding:2px 8px;border-radius:100px;font-size:11px}
    .badge.ok{background:rgba(74,222,128,.15)}.badge.warn{background:rgba(255,171,46,.15)}"""
    H = [f"<style>{css}</style>",
         f"<h1>🩺 Chequeo General — {_esc(datos.get('vehiculo'))}</h1>",
         f"<div class='sub'>{_esc(datos.get('fecha'))} · perfil {_esc(datos.get('perfil'))}</div>",
         "<div class='cards'>",
         f"<div class='card'><b>{r['sensores_totales']}</b>sensores leídos</div>",
         f"<div class='card'><b class='ok'>{r['sensores_ok']}</b>en rango OK</div>",
         f"<div class='card'><b class='warn'>{r['sensores_en_atencion']}</b>en atención</div>",
         f"<div class='card'><b>{r['dtcs_totales']}</b>códigos de falla</div>",
         "</div>"]
    if r["atencion"]:
        H.append("<h2>⚠ Sensores en atención</h2><table><tr><th>ECU</th><th>Sensor</th><th>Valor</th><th>Detalle</th></tr>")
        for a in r["atencion"]:
            H.append(f"<tr><td>{_esc(a['ecu'])}</td><td>{_esc(a['sensor'])}</td>"
                     f"<td class='warn'>{_esc(a['valor'])}</td><td class='dim'>{_esc(a['detalle'])}</td></tr>")
        H.append("</table>")
    if r["dtcs"]:
        H.append("<h2>🚨 Códigos de falla</h2><table><tr><th>ECU</th><th>Código</th><th>Descripción</th></tr>")
        for d in r["dtcs"]:
            H.append(f"<tr><td>{_esc(d['ecu'])}</td><td><b>{_esc(d['codigo'])}</b></td><td>{_esc(d['descripcion'])}</td></tr>")
        H.append("</table>")
    # ECUs
    H.append("<h2>Computadoras (ECUs)</h2>")
    for ecu in datos.get("ecus", []):
        pres = ecu.get("presente")
        badge = "<span class='badge ok'>responde</span>" if pres else ("<span class='badge warn'>no responde</span>" if pres is False else "")
        H.append(f"<div class='ecu'><b>{_esc(ecu['icon'])} {_esc(ecu['nombre'])}</b> {badge}")
        if ecu.get("sensores"):
            H.append("<table><tr><th>Sensor</th><th>Valor</th><th></th></tr>")
            for etiqueta, valor in ecu["sensores"].items():
                ev = (ecu.get("evaluaciones") or {}).get(etiqueta, {})
                cls = {"ok": "ok", "atencion": "warn"}.get(ev.get("estado"), "dim")
                marca = {"ok": "✓ OK", "atencion": "⚠"}.get(ev.get("estado"), "")
                H.append(f"<tr><td>{_esc(etiqueta)}</td><td>{_esc(valor)}</td><td class='{cls}'>{marca}</td></tr>")
            H.append("</table>")
        H.append("</div>")
    # evolución
    orden, sensores = _tabla_evolucion(datos)
    if sensores:
        H.append("<h2>Evolución del motor por RPM (promedio)</h2><table><tr><th>Sensor</th><th>ralentí</th><th>1500</th><th>2000</th><th>3000</th><th></th></tr>")
        for sensor, vals in sensores.items():
            H.append("<tr><td>" + _esc(sensor) + "</td>" +
                     "".join(f"<td>{'' if vals.get(et) is None else _esc(vals.get(et))}</td>" for et in orden) +
                     f"<td class='dim'>{_esc(vals.get('unidad',''))}</td></tr>")
        H.append("</table>")
    return "\n".join(H)


# =====================================================================
# ENSAYO DE ACELERACIÓN (motor en movimiento, ~50/100 m)
# =====================================================================
def _muestrear_serie(muestras, maximo=24):
    """Reduce la lista de muestras a ~`maximo` filas parejas para la tabla temporal."""
    n = len(muestras)
    if n <= maximo:
        return muestras
    paso = n / maximo
    return [muestras[min(n - 1, int(i * paso))] for i in range(maximo)]


def _txt_ensayo(datos):
    r = datos.get("resumen_run", {})
    stats = datos.get("estadisticas", {})
    L = []
    L.append("=" * 70)
    L.append("  ENSAYO DE ACELERACIÓN — SISTEMASQ24")
    L.append(f"  Vehículo: {datos.get('vehiculo')}   |   {datos.get('fecha')}")
    L.append("=" * 70)
    L.append("")
    L.append("RESUMEN DEL TRAMO")
    L.append(f"  Distancia recorrida: {r.get('distancia_m')} m (objetivo {datos.get('distancia_objetivo')} m)")
    L.append(f"  Duración: {r.get('duracion_seg')} s   |   Muestras: {r.get('n_muestras')}   |   Fin por: {r.get('motivo_fin')}")
    L.append(f"  Velocidad máx: {r.get('vel_max')} km/h   |   RPM máx: {r.get('rpm_max')}   (RPM inicial: {r.get('rpm_inicial')})")
    if r.get("tiempos"):
        tt = "  ".join(f"{k.replace('t_a_','0→').replace('kmh',' km/h')}: {v}s" for k, v in r["tiempos"].items())
        L.append(f"  Tiempos de aceleración:  {tt}")
    L.append("")
    if r.get("destacados"):
        L.append("DESTACADOS BAJO CARGA (mín / prom / máx)")
        for _k, d in r["destacados"].items():
            L.append(f"  · {d['sensor']}: {d['min']} / {d['prom']} / {d['max']} {d['unidad']}")
        L.append("")
    L.append("ESTADÍSTICAS POR SENSOR EN EL TRAMO")
    L.append(f"  {'Sensor':<40} {'mín':>9} {'prom':>9} {'máx':>9} {'σ':>7}")
    for sensor, s in stats.items():
        L.append(f"  {sensor[:40]:<40} {s['minimo']:>9} {s['promedio']:>9} {s['maximo']:>9} {s['desv_std']:>7}  {s['unidad']}")
    L.append("")
    # serie temporal (muestreada)
    serie = _muestrear_serie(datos.get("muestras", []))
    if serie:
        L.append("EVOLUCIÓN EN EL TRAMO (muestreada)")
        L.append(f"  {'t(s)':>6} {'dist(m)':>8} {'vel(km/h)':>10} {'RPM':>7}")
        for m in serie:
            L.append(f"  {m.get('t',''):>6} {m.get('distancia',''):>8} "
                     f"{('' if m.get('vel') is None else m['vel']):>10} {('' if m.get('rpm') is None else m['rpm']):>7}")
    L.append("")
    L.append("Nota: es una foto del motor EN CARGA. Los rangos de ralentí no aplican; los")
    L.append("valores van crudos + estadísticas para que los interpretes vos o una IA.")
    return "\n".join(L)


def _html_ensayo(datos):
    r = datos.get("resumen_run", {})
    stats = datos.get("estadisticas", {})
    css = """body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0e141b;color:#e8eef4;margin:0;padding:24px;line-height:1.5}
    h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;border-bottom:1px solid #24303f;padding-bottom:6px;margin-top:28px}
    .sub{color:#8ea0b2;font-size:13px;margin-bottom:18px}
    .cards{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}
    .card{background:#161e27;border:1px solid #24303f;border-radius:10px;padding:14px 18px;min-width:110px}
    .card b{font-size:24px;display:block}.card .u{color:#8ea0b2;font-size:12px}
    table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
    th,td{text-align:left;padding:5px 8px;border-bottom:1px solid #1c2732}
    th{color:#8ea0b2}.dim{color:#8ea0b2}.cyan{color:#2fd4d4}
    .ecu{background:#131b23;border:1px solid #24303f;border-radius:10px;padding:14px 18px;margin:12px 0}
    .note{margin-top:16px;padding:10px 14px;background:rgba(47,212,212,.08);border:1px solid rgba(47,212,212,.3);border-radius:8px;font-size:13px;color:#9fd}"""
    tiempos = ""
    if r.get("tiempos"):
        tiempos = " · ".join(f"0→{k.replace('t_a_','').replace('kmh',' km/h')}: <b>{v}s</b>" for k, v in r["tiempos"].items())
    H = [f"<style>{css}</style>",
         f"<h1>🏁 Ensayo de Aceleración — {_esc(datos.get('vehiculo'))}</h1>",
         f"<div class='sub'>{_esc(datos.get('fecha'))} · perfil {_esc(datos.get('perfil'))} · "
         f"fin por {_esc(r.get('motivo_fin'))}</div>",
         "<div class='cards'>",
         f"<div class='card'><b class='cyan'>{r.get('distancia_m','—')}</b><span class='u'>metros recorridos</span></div>",
         f"<div class='card'><b>{r.get('duracion_seg','—')}</b><span class='u'>segundos</span></div>",
         f"<div class='card'><b>{r.get('vel_max','—')}</b><span class='u'>km/h máx</span></div>",
         f"<div class='card'><b>{r.get('rpm_max','—')}</b><span class='u'>RPM máx</span></div>",
         f"<div class='card'><b>{r.get('n_muestras','—')}</b><span class='u'>muestras</span></div>",
         "</div>"]
    if tiempos:
        H.append(f"<div class='sub'>⏱️ {tiempos}</div>")
    if r.get("destacados"):
        H.append("<h2>Destacados bajo carga</h2><table><tr><th>Magnitud</th><th>Sensor</th><th>mín</th><th>prom</th><th>máx</th></tr>")
        for _k, d in r["destacados"].items():
            H.append(f"<tr><td class='dim'>{_esc(_k)}</td><td>{_esc(d['sensor'])}</td>"
                     f"<td>{_esc(d['min'])}</td><td>{_esc(d['prom'])}</td><td class='cyan'>{_esc(d['max'])} {_esc(d['unidad'])}</td></tr>")
        H.append("</table>")
    H.append("<h2>Estadísticas por sensor en el tramo</h2>")
    H.append("<table><tr><th>Sensor</th><th>mín</th><th>prom</th><th>máx</th><th>σ</th><th></th></tr>")
    for sensor, s in stats.items():
        H.append(f"<tr><td>{_esc(sensor)}</td><td>{_esc(s['minimo'])}</td><td>{_esc(s['promedio'])}</td>"
                 f"<td>{_esc(s['maximo'])}</td><td class='dim'>{_esc(s['desv_std'])}</td><td class='dim'>{_esc(s['unidad'])}</td></tr>")
    H.append("</table>")
    serie = _muestrear_serie(datos.get("muestras", []))
    if serie:
        H.append("<h2>Evolución en el tramo</h2><table><tr><th>t (s)</th><th>dist (m)</th><th>vel (km/h)</th><th>RPM</th></tr>")
        for m in serie:
            H.append(f"<tr><td>{_esc(m.get('t',''))}</td><td>{_esc(m.get('distancia',''))}</td>"
                     f"<td>{'' if m.get('vel') is None else _esc(m['vel'])}</td>"
                     f"<td>{'' if m.get('rpm') is None else _esc(m['rpm'])}</td></tr>")
        H.append("</table>")
    H.append("<div class='note'>🏁 Es una foto del motor <b>en carga</b>. Los rangos de ralentí no "
             "aplican acá; los valores van crudos + estadísticas para interpretarlos vos o una IA. "
             "Compará este ensayo con el Chequeo General (auto detenido) para ver el comportamiento bajo demanda.</div>")
    return "\n".join(H)


def generar_ensayo(datos):
    """Escribe el reporte del ensayo de aceleración (HTML/JSON/TXT). Devuelve {html,json,txt}."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    nombre = "ensayo_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    p_json = LOG_DIR / f"{nombre}.json"
    p_txt = LOG_DIR / f"{nombre}.txt"
    p_html = LOG_DIR / f"{nombre}.html"
    p_json.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    p_txt.write_text(_txt_ensayo(datos), encoding="utf-8")
    p_html.write_text("<!doctype html><meta charset='utf-8'><title>Ensayo " +
                      _esc(datos.get("vehiculo", "")) + "</title>" + _html_ensayo(datos), encoding="utf-8")
    return {"html": str(p_html), "json": str(p_json), "txt": str(p_txt),
            "carpeta": str(LOG_DIR), "nombre": nombre}


def generar(datos):
    """Analiza los datos y escribe los 3 archivos. Devuelve {html, json, txt, carpeta}."""
    _analizar(datos)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    nombre = "reporte_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    p_json = LOG_DIR / f"{nombre}.json"
    p_txt = LOG_DIR / f"{nombre}.txt"
    p_html = LOG_DIR / f"{nombre}.html"
    p_json.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    p_txt.write_text(_txt(datos), encoding="utf-8")
    p_html.write_text("<!doctype html><meta charset='utf-8'><title>Chequeo " +
                      _esc(datos.get("vehiculo", "")) + "</title>" + _html(datos), encoding="utf-8")
    return {"html": str(p_html), "json": str(p_json), "txt": str(p_txt),
            "carpeta": str(LOG_DIR), "nombre": nombre}
