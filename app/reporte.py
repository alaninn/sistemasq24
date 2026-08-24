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


# Sensores CLAVE para el diagnóstico de un motor naftero, con cómo leerlos. Se buscan por
# subcadena de la etiqueta (case-insensitive) entre TODOS los sensores del paneo + ralentí.
DIAG_CLAVE = [
    (["régimen", "regime", "rpm"],
     "Ralentí estable ~750-850 rpm. Inestable → admisión de aire falsa, bujías, inyectores."),
    (["temperatura del refrigerante", "température eau", "temperatura de agua", "eau mesurée"],
     "Con el motor caliente debe estar ~85-95 °C. Frío = no entra en lazo cerrado; muy alto = riesgo."),
    (["ajuste corto", "enrichissement regulation", "facteur enrichissement"],
     "STFT: corrección instantánea de mezcla. Sano ±10%. Muy + = mezcla pobre; muy − = rica."),
    (["ajuste largo", "correction adaptative"],
     "LTFT: corrección aprendida, por zona de carga. 0%=neutro. Alto + = falsa de aire / "
     "inyectores sucios / MAF; alto − = mezcla rica. Normal ±5%, sospechoso ±5-8%, "
     "problema >±25% sostenido."),
    (["offset de aprendizaje", "ganancia de aprendizaje", "offset apprentissage", "gain apprentissage"],
     "Calibración del ALGORITMO de aprendizaje de mezcla (no es directamente la corrección "
     "en sí, a diferencia del ajuste largo). CONFIRMADO EN LA PRÁCTICA: el reset de mezcla "
     "(modo 82) NO cambia este valor, ni reiniciando el programa — solo resetea el ajuste "
     "corto y las 5 zonas. Su fórmula tampoco tiene offset de -50 como las 5 zonas — hipótesis "
     "razonada (NO confirmada con fuente Renault) es que su neutro esté en ~50% (equivalente a "
     "byte crudo 128), no en 0%. Interpretar con cautela; comparar sesiones entre sí más que "
     "buscar un valor absoluto, y no esperar que un reset lo mueva."),
    (["estado del sistema de combustible", "lazo", "stratégie régulation", "état stratégie"],
     "Con motor caliente debe estar en LAZO CERRADO. Si queda abierto → sonda o temperatura."),
    (["sonda lambda", "sonde amont", "tension sonde", "relación lambda", "λ"],
     "En lazo cerrado la sonda anterior debe OSCILAR (0.1–0.9 V). Fija = sonda vaga/envejecida."),
    (["tensión de batería", "tension batterie", "tensión del módulo", "batería"],
     "Con el motor en marcha 13.5–14.8 V (alternador cargando). Bajo = alternador/batería."),
    (["presión del colector", "map", "pression collecteur", "colector absolut"],
     "MAP: bajo en ralentí (~25-40 kPa), sube con la carga. Alto en ralentí = fuga/válvula."),
    (["avance de encendido", "avance allumage"],
     "El avance debe aumentar con las RPM. Plano o negativo = detonación/sensor de picado."),
    (["posición del acelerador", "posición de la mariposa", "papillon", "acelerador"],
     "TPS: ~0-15% en ralentí, sigue al pedal de forma lineal."),
    (["tiempo de inyección", "temps injection"],
     "Ancho de pulso del inyector: sube con la carga. Anómalo = inyector/mezcla."),
    (["caudal de aire", "maf", "débit air"],
     "MAF: proporcional a las RPM y la carga. Bajo = MAF sucio / falsa de aire."),
]


def _iter_sensores_paneo(datos):
    """Itera (ecu_nombre, etiqueta, valor_str) de todos los sensores del paneo."""
    for ecu in datos.get("ecus", []):
        for etiqueta, valor in (ecu.get("sensores") or {}).items():
            yield ecu.get("nombre", "?"), etiqueta, valor


def _valor_clave(datos, keywords):
    """Busca el primer sensor cuya etiqueta contenga alguno de los keywords.
    Prioriza el paneo (ralentí, auto quieto); devuelve (etiqueta, valor_str, origen) o None."""
    for _ecu, etiqueta, valor in _iter_sensores_paneo(datos):
        el = etiqueta.lower()
        if any(k in el for k in keywords):
            return etiqueta, valor, "ralentí"
    # si no está en el paneo, buscar en las estadísticas de la etapa ralentí
    stats = (datos.get("rpm_etapas", {}).get("ralenti") or {}).get("estadisticas", {})
    for etiqueta, s in stats.items():
        el = etiqueta.lower()
        if any(k in el for k in keywords):
            return etiqueta, f"{s.get('promedio')} {s.get('unidad','')}".strip(), "ralentí (prom)"
    return None


def _diagnostico(datos):
    """Arma la lista de datos clave para el diagnóstico: cada sensor clave con su valor
    medido y la explicación de qué esperar. Lo que no se leyó queda marcado."""
    out = []
    for keywords, explicacion in DIAG_CLAVE:
        hit = _valor_clave(datos, keywords)
        if hit:
            etiqueta, valor, origen = hit
            out.append({"sensor": etiqueta, "valor": valor, "origen": origen,
                        "referencia": explicacion, "leido": True})
        else:
            out.append({"sensor": keywords[0], "valor": None, "origen": None,
                        "referencia": explicacion, "leido": False})
    return out


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

    # ECUs presentes / ausentes (para saber qué módulos respondieron)
    ecus_presentes = [e["nombre"] for e in datos.get("ecus", []) if e.get("presente")]
    ecus_ausentes = [e["nombre"] for e in datos.get("ecus", []) if e.get("presente") is False]

    # Notas sobre la captura de RPM (honestidad: qué se alcanzó realmente)
    notas_captura = []
    if datos.get("rpm_disponible") is False:
        notas_captura.append("No se pudieron leer las RPM del motor: se saltearon las etapas de "
                             "aceleración. El reporte tiene solo el paneo y el ralentí.")
    for et, d in (datos.get("rpm_etapas") or {}).items():
        if et != "ralenti" and d.get("alcanzo_banda") is False:
            notas_captura.append(f"La etapa de {et} RPM no llegó a una banda estable: los valores "
                                f"de esa etapa son aproximados (el motor no se mantuvo ahí).")

    datos["resumen"] = {
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sensores_totales": total_sensores,
        "sensores_ok": n_ok,
        "sensores_en_atencion": len(atencion),
        "atencion": atencion,
        "dtcs_totales": total_dtcs,
        "dtcs": dtcs_lista,
        "con_rangos": bool(rangos),
        "ecus_presentes": ecus_presentes,
        "ecus_ausentes": ecus_ausentes,
        "notas_captura": notas_captura,
        "diagnostico": _diagnostico(datos),
    }
    # Bloque compacto pensado para pegarle a una IA / experto: todo lo esencial junto.
    datos["para_experto"] = {
        "vehiculo": datos.get("vehiculo"),
        "perfil": datos.get("perfil"),
        "fecha": datos.get("fecha"),
        "modulos_presentes": ecus_presentes,
        "modulos_sin_respuesta": ecus_ausentes,
        "codigos_de_falla": dtcs_lista,
        "sensores_en_atencion": atencion,
        "datos_clave": datos["resumen"]["diagnostico"],
        "evolucion_por_rpm": _evolucion_completa(datos),
        "advertencias_de_captura": notas_captura,
    }
    return datos


def _evolucion_completa(datos):
    """Evolución por RPM con TODAS las estadísticas (min/prom/max/σ/oscila) por sensor y etapa.
    Estructura pensada para análisis: {sensor: {unidad, etapas:{ralenti:{...}, 1500:{...}}}}."""
    etapas = datos.get("rpm_etapas", {})
    orden = ["ralenti", "1000", "1500", "2000", "3000"]
    out = {}
    for et in orden:
        stats = (etapas.get(et) or {}).get("estadisticas", {})
        for sensor, s in stats.items():
            d = out.setdefault(sensor, {"unidad": s.get("unidad", ""), "etapas": {}})
            d["etapas"][et] = {"min": s.get("minimo"), "prom": s.get("promedio"),
                               "max": s.get("maximo"), "desv": s.get("desv_std"),
                               "oscila": s.get("oscila")}
    return out


def _tabla_evolucion(datos):
    """Arma la evolución por RPM: {sensor: {ralenti, 1500, 2000, 3000}} con el promedio."""
    etapas = datos.get("rpm_etapas", {})
    orden = ["ralenti", "1000", "1500", "2000", "3000"]
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
    if r.get("ecus_presentes"):
        L.append(f"  Módulos que responden: {', '.join(r['ecus_presentes'])}")
    if r.get("ecus_ausentes"):
        L.append(f"  Módulos SIN respuesta: {', '.join(r['ecus_ausentes'])}")
    if not r["con_rangos"]:
        L.append("  (Sin rangos de referencia para este perfil: los valores van crudos.)")
    L.append("")
    if r.get("notas_captura"):
        L.append("NOTAS DE LA CAPTURA")
        for n in r["notas_captura"]:
            L.append(f"  • {n}")
        L.append("")
    # Datos clave para el diagnóstico (con qué esperar de cada uno)
    if r.get("diagnostico"):
        L.append("DATOS CLAVE PARA EL DIAGNÓSTICO")
        for d in r["diagnostico"]:
            val = d["valor"] if d["leido"] else "— (no se leyó)"
            L.append(f"  · {d['sensor']}: {val}")
            L.append(f"      ↳ {d['referencia']}")
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
        # Detalle completo por etapa (min/prom/max/σ) — para ver variabilidad bajo carga
        completa = _evolucion_completa(datos)
        L.append("DETALLE POR ETAPA (mín / prom / máx / σ)")
        for sensor, d in completa.items():
            L.append(f"  {sensor}  [{d.get('unidad','')}]")
            for et in orden:
                e = d["etapas"].get(et)
                if not e:
                    continue
                osc = " ~oscila" if e.get("oscila") else ""
                L.append(f"      {et:<8} min {e['min']:<8} prom {e['prom']:<8} "
                         f"max {e['max']:<8} σ {e['desv']}{osc}")
        L.append("")
    L.append("=" * 70)
    L.append("Cómo leer este reporte: 'DATOS CLAVE' resume el estado del motor con qué esperar")
    L.append("de cada sensor. 'EN ATENCIÓN' son los que se salieron del rango. La 'EVOLUCIÓN POR")
    L.append("RPM' muestra cómo responde el motor bajo demanda. El .json trae el bloque")
    L.append("'para_experto' con todo junto, listo para pegarle a un mecánico o a una IA.")
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
    .badge.ok{background:rgba(74,222,128,.15)}.badge.warn{background:rgba(255,171,46,.15)}
    .note{margin:14px 0;padding:10px 14px;background:rgba(47,212,212,.08);border:1px solid rgba(47,212,212,.3);border-radius:8px;font-size:13px;color:#9fd}"""
    H = [f"<style>{css}</style>",
         f"<h1>🩺 Chequeo General — {_esc(datos.get('vehiculo'))}</h1>",
         f"<div class='sub'>{_esc(datos.get('fecha'))} · perfil {_esc(datos.get('perfil'))}</div>",
         "<div class='cards'>",
         f"<div class='card'><b>{r['sensores_totales']}</b>sensores leídos</div>",
         f"<div class='card'><b class='ok'>{r['sensores_ok']}</b>en rango OK</div>",
         f"<div class='card'><b class='warn'>{r['sensores_en_atencion']}</b>en atención</div>",
         f"<div class='card'><b>{r['dtcs_totales']}</b>códigos de falla</div>",
         "</div>"]
    if r.get("ecus_presentes") or r.get("ecus_ausentes"):
        H.append("<div class='sub'>")
        if r.get("ecus_presentes"):
            H.append("✅ Responden: " + _esc(", ".join(r["ecus_presentes"])) + ". ")
        if r.get("ecus_ausentes"):
            H.append("⛔ Sin respuesta: <span class='warn'>" + _esc(", ".join(r["ecus_ausentes"])) + "</span>.")
        H.append("</div>")
    if r.get("notas_captura"):
        H.append("<div class='note'>ⓘ " + "<br>".join(_esc(n) for n in r["notas_captura"]) + "</div>")
    # Datos clave para el diagnóstico
    if r.get("diagnostico"):
        H.append("<h2>🔑 Datos clave para el diagnóstico</h2>")
        H.append("<table><tr><th>Sensor</th><th>Valor medido</th><th>Qué esperar</th></tr>")
        for d in r["diagnostico"]:
            if d["leido"]:
                val = f"<b>{_esc(d['valor'])}</b>"
                cls = ""
            else:
                val = "<span class='dim'>— no se leyó</span>"
                cls = "dim"
            H.append(f"<tr class='{cls}'><td>{_esc(d['sensor'])}</td><td>{val}</td>"
                     f"<td class='dim'>{_esc(d['referencia'])}</td></tr>")
        H.append("</table>")
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
        # Detalle completo por etapa (min/prom/max/σ)
        completa = _evolucion_completa(datos)
        H.append("<h2>Detalle por etapa (mín / prom / máx / σ)</h2>")
        H.append("<table><tr><th>Sensor</th><th>Etapa</th><th>mín</th><th>prom</th>"
                 "<th>máx</th><th>σ</th><th></th></tr>")
        for sensor, d in completa.items():
            for et in orden:
                e = d["etapas"].get(et)
                if not e:
                    continue
                osc = "~oscila" if e.get("oscila") else ""
                H.append(f"<tr><td>{_esc(sensor)}</td><td class='dim'>{et}</td>"
                         f"<td>{_esc(e['min'])}</td><td><b>{_esc(e['prom'])}</b></td>"
                         f"<td>{_esc(e['max'])}</td><td class='dim'>{_esc(e['desv'])}</td>"
                         f"<td class='dim'>{_esc(d.get('unidad',''))} {osc}</td></tr>")
        H.append("</table>")
    H.append("<div class='note'>Cómo leer: <b>Datos clave</b> resume el estado del motor con qué "
             "esperar de cada sensor; <b>En atención</b> son los que se salieron de rango; la "
             "<b>evolución por RPM</b> muestra la respuesta bajo demanda. El <b>.json</b> trae el "
             "bloque <code>para_experto</code> con todo junto, listo para un mecánico o una IA.</div>")
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


# =====================================================================
# GRABACIÓN DE CONDUCCIÓN — línea temporal indexada por VELOCIDAD
# =====================================================================
# Bandas de velocidad para segmentar el manejo (km/h). El informe muestra cómo reaccionó cada
# sensor en cada banda → "cómo se comportó el auto a medida que aceleraba".
BANDAS_VEL = [
    (0, 3, "Detenido / ralentí"), (3, 20, "Baja (3-20)"), (20, 40, "Media-baja (20-40)"),
    (40, 60, "Media (40-60)"), (60, 90, "Alta (60-90)"), (90, 9999, "Muy alta (90+)"),
]
# Si el auto NO se movió (prueba en el taller/garage acelerando en el lugar), la velocidad es 0
# todo el tiempo y segmentar por ella no dice nada. En ese caso se usa el RÉGIMEN como eje.
BANDAS_RPM = [
    (0, 400, "Motor apagado"), (400, 900, "Ralentí"), (900, 1500, "1000-1500"),
    (1500, 2000, "1500-2000"), (2000, 2500, "2000-2500"), (2500, 3000, "2500-3000"),
    (3000, 99999, "3000+"),
]


def _conduccion_analizar(datos):
    """Segmenta las muestras por banda de velocidad y calcula, por sensor, el promedio en cada
    banda + estadísticas globales + un diagnóstico. Devuelve la estructura para el informe."""
    from chequeo import estadisticas_de_muestras
    muestras = datos.get("muestras", [])
    vels = [m["vel"] for m in muestras if m.get("vel") is not None]
    dur = muestras[-1]["t"] if muestras else 0

    # estadísticas globales (todas las muestras)
    stats_glob = estadisticas_de_muestras(muestras)

    # ¿el auto se movió? Si la velocidad fue siempre ~0 (prueba en el lugar), el eje pasa a ser
    # el RÉGIMEN: si no, el informe queda con una sola banda ("detenido") y no dice nada.
    se_movio = bool(vels) and max(vels) >= 3
    eje = "velocidad" if se_movio else "rpm"

    def _rpm_de(m):
        """RPM de una muestra (viene dentro de `valores` como texto 'NNN RPM')."""
        for k, v in (m.get("valores") or {}).items():
            kl = k.lower()
            if "régimen del motor" in kl or "regime moteur" in kl or "rpm" in kl:
                try:
                    return float(str(v).split()[0])
                except (ValueError, IndexError):
                    return None
        return None

    bandas = []
    if se_movio:
        for lo, hi, nombre in BANDAS_VEL:
            sub = [m for m in muestras if m.get("vel") is not None and lo <= m["vel"] < hi]
            if len(sub) < 2:
                continue
            st = estadisticas_de_muestras(sub)
            bandas.append({"banda": nombre, "rango": [lo, hi], "n": len(sub),
                           "vel_prom": round(sum(m["vel"] for m in sub) / len(sub), 1),
                           "promedios": {s: v["promedio"] for s, v in st.items()}})
    else:
        for m in muestras:
            m["_rpm"] = _rpm_de(m)
        for lo, hi, nombre in BANDAS_RPM:
            sub = [m for m in muestras if m.get("_rpm") is not None and lo <= m["_rpm"] < hi]
            if len(sub) < 2:
                continue
            st = estadisticas_de_muestras(sub)
            bandas.append({"banda": nombre, "rango": [lo, hi], "n": len(sub),
                           "rpm_prom": round(sum(m["_rpm"] for m in sub) / len(sub)),
                           "promedios": {s: v["promedio"] for s, v in st.items()}})

    # evolución por velocidad: {sensor: {unidad, por_banda:{banda:prom}}}
    evolucion = {}
    for b in bandas:
        for sensor, prom in b["promedios"].items():
            d = evolucion.setdefault(sensor, {"unidad": stats_glob.get(sensor, {}).get("unidad", ""), "por_banda": {}})
            d["por_banda"][b["banda"]] = prom

    # diagnóstico: usa los mismos sensores clave del chequeo, sobre las stats globales
    diag = []
    for keywords, explicacion in DIAG_CLAVE:
        hit = None
        for sensor, s in stats_glob.items():
            if any(k in sensor.lower() for k in keywords):
                hit = (sensor, s)
                break
        if hit:
            sensor, s = hit
            diag.append({"sensor": sensor, "min": s["minimo"], "prom": s["promedio"],
                         "max": s["maximo"], "unidad": s["unidad"], "referencia": explicacion, "leido": True})
        else:
            diag.append({"sensor": keywords[0], "leido": False, "referencia": explicacion})

    # veredicto general: sobre todo el ajuste largo de combustible (mezcla)
    veredicto = {"nivel": "ok", "titulo": "Sin anomalías evidentes en el manejo",
                 "detalle": "Los sensores clave se movieron dentro de lo esperado durante la conducción."}
    ltft = next((s for n, s in stats_glob.items() if "ajuste largo" in n.lower()), None)
    if ltft and ltft.get("maximo") is not None and ltft["maximo"] > 25:
        veredicto = {"nivel": "warn", "titulo": "Atención — mezcla pobre a baja carga (posible fuga de vacío)",
                     "detalle": f"El ajuste largo de combustible llegó a {ltft['maximo']}% (sano ±10%). "
                     "Típico de una entrada de aire falso que se nota a bajas RPM/carga y se diluye acelerando. "
                     "Revisar manguera de servofreno, PCV, regulador de presión de nafta y juntas de admisión."}

    datos["resumen"] = {
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "muestras": len(muestras), "duracion_seg": dur,
        "vel_min": round(min(vels), 1) if vels else None,
        "vel_max": round(max(vels), 1) if vels else None,
        "sensores_distintos": len(stats_glob),
        "eje": eje,                 # "velocidad" | "rpm" (si el auto no se movió)
        "se_movio": se_movio,
        "veredicto": veredicto,
        "bandas_velocidad": bandas, "evolucion_por_velocidad": evolucion, "diagnostico": diag,
        "estadisticas": stats_glob,   # todas: min/prom/max/σ/oscila por sensor
        "snapshot": datos.get("snapshot", {}),
    }
    datos["para_experto"] = {
        "vehiculo": datos.get("vehiculo"), "perfil": datos.get("perfil"), "fecha": datos.get("fecha"),
        "duracion_seg": dur, "velocidad": {"min": datos["resumen"]["vel_min"], "max": datos["resumen"]["vel_max"]},
        "veredicto": veredicto, "eje": eje, "datos_clave": diag, "evolucion_por_velocidad": evolucion,
        "bandas": bandas, "estadisticas_por_sensor": stats_glob, "foto_final": datos.get("snapshot", {}),
    }
    return datos


def _txt_conduccion(datos):
    r = datos["resumen"]
    L = ["=" * 70, "  GRABACIÓN DE CONDUCCIÓN — SISTEMASQ24",
         f"  Vehículo: {datos.get('vehiculo')}   |   {datos.get('fecha')}", "=" * 70, ""]
    L.append(f"Duración: {r['duracion_seg']} s  |  Muestras: {r['muestras']}  |  "
             f"Velocidad: {r['vel_min']}–{r['vel_max']} km/h  |  Sensores: {r['sensores_distintos']}")
    L.append("")
    vd = r.get("veredicto", {})
    L.append(f"VEREDICTO: {vd.get('titulo','')}")
    L.append(f"  {vd.get('detalle','')}")
    L.append("")
    L.append("DATOS CLAVE (rango en todo el manejo: mín / prom / máx)")
    for d in r["diagnostico"]:
        if d.get("leido"):
            L.append(f"  · {d['sensor']}: {d['min']} / {d['prom']} / {d['max']} {d['unidad']}")
            L.append(f"      ↳ {d['referencia']}")
    L.append("")
    _ejet = "VELOCIDAD" if r.get("eje", "velocidad") == "velocidad" else "RÉGIMEN (el auto no se movió)"
    L.append(f"EVOLUCIÓN POR {_ejet} (promedio de cada sensor en cada banda)")
    bandas = [b["banda"] for b in r["bandas_velocidad"]]
    if bandas:
        L.append("  " + "Sensor".ljust(38) + "".join(b[:12].rjust(13) for b in bandas))
        for sensor, d in r["evolucion_por_velocidad"].items():
            fila = "  " + sensor[:38].ljust(38)
            for b in bandas:
                v = d["por_banda"].get(b)
                fila += ("" if v is None else str(v)).rjust(13)
            L.append(fila + f"  {d.get('unidad','')}")
    L.append("")
    stats = r.get("estadisticas", {})
    if stats:
        L.append(f"TODOS LOS SENSORES DEL MANEJO ({len(stats)}) — mín / prom / máx / σ")
        L.append(f"  {'Sensor':<42} {'mín':>9} {'prom':>9} {'máx':>9} {'σ':>7}")
        for s, st in sorted(stats.items(), key=lambda x: -(x[1].get('maximo', 0) - x[1].get('minimo', 0))):
            L.append(f"  {s[:42]:<42} {st['minimo']:>9} {st['promedio']:>9} {st['maximo']:>9} {st['desv_std']:>7}  {st['unidad']}")
        L.append("")
    L.append("Nota: es un registro CONTINUO indexado por velocidad. Muestra cómo reaccionó cada")
    L.append("sistema a medida que el auto aceleraba. El .json trae 'para_experto' con todo junto.")
    return "\n".join(L)


# Sensores que se ofrecen en el selector del gráfico de evolución (nombre a buscar por
# subcadena → color). Se buscan en las muestras reales; si no aparecen, no se ofrecen.
_GRAF_CANDIDATOS = [
    ("Velocidad del vehículo", "#2fd4d4"), ("Régimen del motor", "#8f9cff"),
    ("Ajuste corto de combustible", "#3ddc97"), ("Ajuste largo de combustible", "#ff7a45"),
    ("Temperatura del agua", "#ff9d7a"), ("Temperatura del aire", "#ffcf7a"),
    ("Presión absoluta del colector", "#ffab2e"), ("Avance de encendido", "#9fd0ff"),
    ("Tensión de la sonda lambda anterior", "#ff5a9e"), ("Tensión de batería", "#f1c40f"),
    ("Posición de la mariposa", "#c98bff"), ("Posición del pedal", "#e08bff"),
    ("Par motor efectivo", "#ffd166"), ("Tiempo de inyección", "#7ee0c0"),
]


def _series_para_grafico(muestras):
    """Arma {sensor: [[t, valor], ...]} para los sensores candidatos que realmente aparecen
    en las muestras, listo para pasarle a Chart.js. Solo valores numéricos."""
    series = {}
    for etiqueta, color in _GRAF_CANDIDATOS:
        pts = []
        nombre_real = None
        for m in muestras:
            for k, v in (m.get("valores") or {}).items():
                if etiqueta.lower() not in k.lower():
                    continue
                nombre_real = k
                try:
                    val = float(str(v).split()[0])
                except (ValueError, IndexError):
                    continue
                # Chart.js con `parsing:false` exige {x,y} (un array [t,v] queda vacío).
                pts.append({"x": round(m["t"], 2), "y": val})
                break
        if pts and nombre_real:
            series[nombre_real] = {"color": color, "puntos": pts}
    return series


def _bloque_grafico(datos, id_prefix="cond"):
    """HTML+JS de un gráfico Chart.js de evolución temporal, con scroll horizontal (el canvas
    es ANCHO — no responsive — así nunca queda chico; el contenedor con overflow-x lo scrollea).
    Chart.js se embebe INLINE (el informe es un archivo suelto, sin servidor detrás).

    El RÉGIMEN (RPM) es la referencia principal: se dibuja como ÁREA de fondo (no una línea más),
    porque es el dato que dice en qué estado estaba el motor en cada instante — en las pruebas
    del F4R el auto casi nunca se mueve, así que la velocidad no sirve de contexto pero el RPM
    sí. El resto de los sensores se superponen encima como líneas finas (con sus propios ejes Y,
    para que un ajuste de ±10% y un RPM de miles no se aplasten entre sí)."""
    muestras = datos.get("muestras", [])
    series = _series_para_grafico(muestras)
    if not series:
        return ""
    try:
        chartjs_src = (APP_DIR / "web" / "chart.umd.js").read_text(encoding="utf-8")
    except Exception:
        chartjs_src = None
    dur = muestras[-1]["t"] if muestras else 1
    # ~14 px por segundo de manejo, con un piso y un techo razonables para no generar un
    # canvas absurdo en grabaciones muy largas.
    ancho_px = max(1000, min(24000, int(dur * 14)))

    # El RPM (o, si no está, la velocidad) va SIEMPRE primero y como área de fondo.
    def _es_rpm(n):
        nl = n.lower()
        return "régime moteur" in nl or "regime moteur" in nl or "régimen del motor" in nl
    def _es_vel(n):
        nl = n.lower()
        return "vitesse véhicule" in nl or "velocidad del vehículo" in nl
    nombre_rpm = next((n for n in series if _es_rpm(n)), None)
    nombre_vel = next((n for n in series if _es_vel(n)), None)
    fondo = nombre_rpm or nombre_vel
    orden = ([fondo] if fondo else []) + sorted(n for n in series if n != fondo)

    DEFAULT_ON = {"Vitesse véhicule", "Velocidad del vehículo", "Régime moteur", "Régimen del motor (RPM)",
                  "Ajuste corto de combustible B1", "Ajuste largo de combustible B1"}
    datasets_js, checks_html = [], []
    for i, nombre in enumerate(orden):
        info = series[nombre]
        cid = f"{id_prefix}_chk_{i}"
        es_fondo = (nombre == fondo)
        visible = "true" if (es_fondo or nombre in DEFAULT_ON or i < 3) else "false"
        if es_fondo:
            # Área rellena, algo más gruesa, dibujada primero (queda "atrás" del resto).
            datasets_js.append(
                "{id:%r,label:%r,data:%s,borderColor:%r,backgroundColor:%r,borderWidth:2,"
                "pointRadius:0,tension:.1,fill:true,order:99,yAxisID:'y%d',hidden:!%s}" % (
                    cid, nombre, json.dumps(info["puntos"]), info["color"], info["color"] + "33", i, visible))
        else:
            datasets_js.append(
                "{id:%r,label:%r,data:%s,borderColor:%r,backgroundColor:%r,borderWidth:1.6,"
                "pointRadius:0,tension:.15,order:%d,yAxisID:'y%d',hidden:!%s}" % (
                    cid, nombre, json.dumps(info["puntos"]), info["color"], info["color"] + "22", i, i, visible))
        marca = " gchk-fondo" if es_fondo else ""
        checks_html.append(
            f"<label class='gchk{marca}' title='{_esc(nombre)}'>"
            f"<input type='checkbox' data-id='{cid}' onchange=\"{id_prefix}_toggle(this)\" "
            f"{'checked' if visible=='true' else ''}>"
            f"<i style='background:{info['color']}'></i>{_esc(nombre)}"
            f"{' <b>(referencia)</b>' if es_fondo else ''}</label>")
    scales_js = ", ".join(
        f"y{i}:{{type:'linear',display:false,position:'left'}}" for i in range(len(orden)))
    script = "" if not chartjs_src else f"<script>{chartjs_src}</script>"
    ref_txt = (f"El área de fondo es el <b>{_esc(fondo)}</b>: es la referencia — te dice en qué "
               "estado estaba el motor en cada momento, para leer el resto de los sensores en "
               "contexto." if fondo else "")
    return f"""
<h2>📈 Evolución de los sensores en el tiempo</h2>
<p class='lead' style='color:#8ea0b2;font-size:13px;margin:4px 0 10px'>{ref_txt} Tildá qué otros
sensores mostrar encima. El gráfico es ancho — <b>desplazate con la barra de abajo</b> (o Shift +
rueda del mouse) para recorrer todo el manejo sin que se achique.</p>
<div class='gchecks'>{''.join(checks_html)}</div>
<div class='gwrap'><div style='width:{ancho_px}px;height:360px'><canvas id='{id_prefix}_canvas'></canvas></div></div>
{script}
<script>
(function(){{
  var ctx = document.getElementById('{id_prefix}_canvas');
  if(!ctx || typeof Chart==='undefined') return;
  var chart = new Chart(ctx, {{
    type: 'line',
    data: {{ datasets: [{','.join(datasets_js)}] }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{mode:'nearest', axis:'x', intersect:false}},
      parsing: false,
      scales: {{
        x: {{type:'linear', title:{{display:true,text:'segundos desde el inicio',color:'#8ea0b2'}},
             ticks:{{color:'#8ea0b2'}}, grid:{{color:'#1c2732'}}}},
        {scales_js}
      }},
      plugins: {{
        legend: {{display:false}},
        tooltip: {{mode:'nearest', axis:'x', intersect:false}}
      }}
    }}
  }});
  window['{id_prefix}_toggle'] = function(el){{
    var ds = chart.data.datasets.find(function(d){{return d.id===el.dataset.id}});
    if(ds){{ ds.hidden = !el.checked; chart.update(); }}
  }};
}})();
</script>"""


def _html_conduccion(datos):
    r = datos["resumen"]
    v = r.get("veredicto", {})
    vcol = {"ok": "#3ddc97", "warn": "#ffab2e", "bad": "#ff5a5a"}.get(v.get("nivel"), "#8ea0b2")
    vico = {"ok": "🟢", "warn": "🟡", "bad": "🔴"}.get(v.get("nivel"), "⚪")
    css = """body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0e141b;color:#e8eef4;margin:0;padding:24px;line-height:1.5}
    .wrap{max-width:1040px;margin:0 auto}
    h1{font-size:23px;margin:0 0 4px}h2{font-size:16px;border-bottom:1px solid #24303f;padding-bottom:6px;margin-top:30px}
    .sub{color:#8ea0b2;font-size:13px;margin-bottom:16px}
    .verdict{display:flex;gap:14px;align-items:flex-start;border-radius:11px;padding:15px 18px;margin:6px 0 8px}
    .verdict .d{font-size:24px;line-height:1}.verdict h3{margin:0 0 3px;font-size:16px}.verdict p{margin:0;font-size:13.5px;color:#cdd8e2}
    .cards{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
    .card{background:#161e27;border:1px solid #24303f;border-radius:10px;padding:13px 17px;min-width:120px}
    .card b{font-size:23px;display:block;font-variant-numeric:tabular-nums}.card .u{color:#8ea0b2;font-size:12px}
    .kcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:11px}
    .kc{background:#161e27;border:1px solid #24303f;border-radius:11px;padding:13px 15px;border-top:3px solid #2c3b49}
    .kc .t{font-size:12.5px;color:#8ea0b2;font-weight:600}.kc .v{font-size:15px;margin:5px 0;font-variant-numeric:tabular-nums}
    .kc .r{font-size:11.5px;color:#8ea0b2;margin-top:7px;padding-top:7px;border-top:1px dashed #24303f}
    table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
    .tw{overflow-x:auto;border:1px solid #22303c;border-radius:10px;margin-top:10px}
    th,td{text-align:left;padding:6px 10px;border-bottom:1px solid #1c2732;white-space:nowrap}
    thead th{background:#111922;color:#8ea0b2;font-size:11px;text-transform:uppercase;letter-spacing:.03em}
    tbody tr:nth-child(even){background:#111922}
    .num{text-align:right;font-variant-numeric:tabular-nums}.dim{color:#8ea0b2}.cyan{color:#2fd4d4}
    .note{margin-top:16px;padding:10px 14px;background:rgba(47,212,212,.08);border:1px solid rgba(47,212,212,.3);border-radius:8px;font-size:13px;color:#9fd}
    details{margin-top:10px}summary{cursor:pointer;color:#2fd4d4;font-size:13px;font-weight:600;padding:6px 0}
    .est2{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1px 18px;margin-top:10px}
    .est2 div{display:flex;justify-content:space-between;gap:10px;font-size:12px;padding:3px 0;border-bottom:1px solid #1c2732}
    .est2 span{color:#8ea0b2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .gchecks{display:flex;flex-wrap:wrap;gap:6px 14px;margin:6px 0 12px}
    .gchk{display:flex;align-items:center;gap:6px;font-size:12.5px;color:#c9d3dc;cursor:pointer;user-select:none;
    padding:3px 9px;border-radius:20px;border:1px solid transparent}
    .gchk input{accent-color:#2fd4d4}
    .gchk i{display:inline-block;width:12px;height:12px;border-radius:3px}
    .gchk-fondo{background:#161e27;border-color:#2c3b49}
    .gchk-fondo b{font-weight:600;color:#8ea0b2;font-size:11px}
    .gwrap{overflow-x:auto;border:1px solid #22303c;border-radius:10px;background:#0b1017;padding:14px 10px}"""
    evol = r["evolucion_por_velocidad"]
    bandas = [b["banda"] for b in r["bandas_velocidad"]]
    stats = r.get("estadisticas", {})
    varian = {s: st for s, st in stats.items() if st.get("oscila")}
    por_rpm = r.get("eje", "velocidad") == "rpm"
    sub_eje = "indexado por RÉGIMEN (el auto no se movió)" if por_rpm else "indexado por velocidad"
    if por_rpm:
        card1 = "<div class='card'><b class='cyan'>RPM</b><span class='u'>eje: régimen (auto detenido)</span></div>"
    else:
        card1 = f"<div class='card'><b class='cyan'>{r['vel_min']}–{r['vel_max']}</b><span class='u'>km/h recorridos</span></div>"
    H = [f"<style>{css}</style><div class='wrap'>",
         f"<h1>🏁 Grabación de conducción — {_esc(datos.get('vehiculo'))}</h1>",
         f"<div class='sub'>{_esc(datos.get('fecha'))} · perfil {_esc(datos.get('perfil'))} · registro continuo {sub_eje}</div>",
         f"<div class='verdict' style='background:{vcol}1a;border:1px solid {vcol};border-left:5px solid {vcol}'>"
         f"<span class='d'>{vico}</span><div><h3 style='color:{vcol}'>{_esc(v.get('titulo',''))}</h3><p>{_esc(v.get('detalle',''))}</p></div></div>",
         "<div class='cards'>", card1,
         f"<div class='card'><b>{r['duracion_seg']}</b><span class='u'>segundos</span></div>",
         f"<div class='card'><b>{r['muestras']}</b><span class='u'>muestras</span></div>",
         f"<div class='card'><b>{r['sensores_distintos']}</b><span class='u'>sensores</span></div>",
         f"<div class='card'><b>{len(varian)}</b><span class='u'>varían al manejar</span></div>",
         "</div>"]
    # tarjetas de datos clave con interpretación
    H.append("<h2>🔑 Datos clave del manejo</h2><div class='kcards'>")
    for d in r["diagnostico"]:
        if d.get("leido"):
            H.append(f"<div class='kc'><div class='t'>{_esc(d['sensor'])}</div>"
                     f"<div class='v'><b>{_esc(d['prom'])}</b> <span class='dim'>{_esc(d['unidad'])}</span> "
                     f"<span class='dim'>(rango {_esc(d['min'])}–{_esc(d['max'])})</span></div>"
                     f"<div class='r'>{_esc(d['referencia'])}</div></div>")
    H.append("</div>")
    # gráfico de evolución temporal (interactivo, con scroll horizontal)
    H.append(_bloque_grafico(datos, "cond"))
    # evolución por velocidad (todos los que varían)
    if bandas:
        titulo_tabla = ("Cómo reaccionó cada sensor según el RÉGIMEN (promedio por banda de RPM)"
                        if por_rpm else "Cómo reaccionó cada sensor según la velocidad (promedio por banda)")
        H.append(f"<h2>📈 {titulo_tabla}</h2>")
        H.append("<div class='tw'><table><thead><tr><th>Sensor</th>" + "".join(f"<th class='num'>{_esc(b)}</th>" for b in bandas) + "<th></th></tr></thead><tbody>")
        for sensor, d in evol.items():
            H.append("<tr><td>" + _esc(sensor) + "</td>" +
                     "".join(f"<td class='num'>{'' if d['por_banda'].get(b) is None else _esc(d['por_banda'][b])}</td>" for b in bandas) +
                     f"<td class='dim'>{_esc(d.get('unidad',''))}</td></tr>")
        H.append("</tbody></table></div>")
    # todos los sensores capturados (stats)
    if stats:
        H.append(f"<h2>Todos los sensores del manejo (mín / prom / máx / σ) <span class='dim'>{len(stats)}</span></h2>")
        H.append("<div class='tw'><table><thead><tr><th>Sensor</th><th class='num'>mín</th><th class='num'>prom</th><th class='num'>máx</th><th class='num'>σ</th><th></th></tr></thead><tbody>")
        for s, st in sorted(stats.items(), key=lambda x: -(x[1].get('maximo',0)-x[1].get('minimo',0))):
            H.append(f"<tr><td>{_esc(s)}</td><td class='num'>{_esc(st['minimo'])}</td><td class='num'><b>{_esc(st['promedio'])}</b></td>"
                     f"<td class='num'>{_esc(st['maximo'])}</td><td class='num dim'>{_esc(st['desv_std'])}</td><td class='dim'>{_esc(st['unidad'])}</td></tr>")
        H.append("</tbody></table></div>")
    # foto final: todos los sensores (completitud)
    snap = r.get("snapshot", {})
    if snap:
        H.append(f"<h2>Foto final del motor <span class='dim'>{len(snap)}</span></h2>")
        H.append(f"<details><summary>Ver los {len(snap)} valores al terminar el manejo</summary><div class='est2'>")
        for k, val in sorted(snap.items()):
            H.append(f"<div><span>{_esc(k)}</span><span>{_esc(val)}</span></div>")
        H.append("</div></details>")
    H.append("<div class='note'>Registro CONTINUO indexado por velocidad: muestra cómo reaccionó cada sistema a medida "
             "que el auto aceleraba. El <b>.json</b> trae el bloque <code>para_experto</code> con todo junto, listo para "
             "un mecánico o una IA. Podés imprimir esta página a PDF (Ctrl+P).</div></div>")
    return "\n".join(H)


def generar_conduccion(datos):
    """Analiza la grabación de conducción y escribe HTML/JSON/TXT. Devuelve {html,json,txt}."""
    _conduccion_analizar(datos)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    nombre = "conduccion_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    p_json = LOG_DIR / f"{nombre}.json"
    p_txt = LOG_DIR / f"{nombre}.txt"
    p_html = LOG_DIR / f"{nombre}.html"
    p_json.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    p_txt.write_text(_txt_conduccion(datos), encoding="utf-8")
    p_html.write_text("<!doctype html><meta charset='utf-8'><title>Conducción " +
                      _esc(datos.get("vehiculo", "")) + "</title>" + _html_conduccion(datos), encoding="utf-8")
    return {"html": str(p_html), "json": str(p_json), "txt": str(p_txt),
            "carpeta": str(LOG_DIR), "nombre": nombre}


# ============================================================================
# CHEQUEO DE MEZCLA (2 etapas: ralentí + ~2500 rpm)
# ============================================================================
def _evaluar_zona_mezcla(valor):
    """Clasifica el % de una zona de ajuste (o el ajuste corto) con el criterio de mezcla:
    0=neutral, ±5=normal, ±5-8=sospechoso, >±8 (y sobre todo >±25 sostenido)=problema.
    Positivo=mezcla pobre (la ECU agrega nafta); negativo=mezcla rica (la ECU saca nafta).
    Devuelve {estado: normal|sospechoso|problema|sin_dato, signo: pobre|rica|neutral, texto}."""
    if valor is None:
        return {"estado": "sin_dato", "signo": None, "texto": "No se pudo leer."}
    av = abs(valor)
    signo = "neutral" if av < 0.5 else ("pobre" if valor > 0 else "rica")
    if av <= 5:
        estado_, calif = "normal", "dentro de lo normal"
    elif av <= 8:
        estado_, calif = "sospechoso", "sospechoso"
    else:
        estado_, calif = "problema", ("problema" if av > 25 else "sospechoso alto")
    if signo == "neutral":
        texto = f"{valor:+.1f}% — {calif} (mezcla correcta)."
    else:
        accion = "agregando" if signo == "pobre" else "sacando"
        texto = (f"{valor:+.1f}% — {calif} (mezcla {signo}: la ECU está {accion} nafta "
                 f"para compensar).")
    return {"estado": estado_, "signo": signo, "texto": texto}


# Traducciones verificadas (motor.t()) de los datos nativos usados como CLAVE de
# lookup contra las estadisticas (que vienen indexadas por ETIQUETA en espanol, no
# por el nombre original en frances -- usar el nombre frances ahi es un bug silencioso
# que siempre devuelve None/sin_dato, tanto en real como en simulacion).
_ES_NATIVO = {'Correction adaptative de la 1ère zone de pression': 'Corrección adaptativa de la 1.ª zona de presión', 'Correction adaptative de la 2ème zone de pression': 'Corrección adaptativa de la 2.ª zona de presión', 'Correction adaptative de la 3ème zone de pression': 'Corrección adaptativa de la 3.ª zona de presión', 'Correction adaptative de la 4ème zone de pression': 'Corrección adaptativa de la 4.ª zona de presión', 'Correction adaptative de la 5ème zone de pression': 'Corrección adaptativa de la 5.ª zona de presión', 'Facteur enrichissement regulation richesse': 'Factor de enriquecimiento de la regulación de riqueza', 'Etat stratégie régulation richesse': 'Estado de la estrategia de regulación de riqueza de mezcla', 'Tension sonde amont': 'Tensión de la sonda lambda anterior', 'RCO théorique régulation ralenti': 'Ciclo de trabajo (RCO) teórico de la regulación del ralentí', 'Correction régime ralenti après-vente': 'Corrección del régimen de ralentí de posventa', 'Valeur apprentissage régulation ralenti': 'Valor de aprendizaje de la regulación del ralentí', 'RCO purge canister': 'Ciclo de trabajo (RCO) de la purga del cánister', 'Régime consigne régulation ralenti': 'Régimen de consigna de la regulación del ralentí', 'Pression collecteur absolue mesurée': 'Presión absoluta del colector medida'}


def _mezcla_analizar(datos):
    """Evalúa las 5 zonas de ajuste largo (prioriza la etapa 2500rpm, cae a ralentí si no hay
    dato) y arma el veredicto general + por zona."""
    from chequeo_mezcla import ZONAS_MEZCLA
    etapas = datos.get("etapas", {})
    ralenti_stats = (etapas.get("ralenti") or {}).get("estadisticas", {})
    p2500_stats = (etapas.get("2500") or {}).get("estadisticas", {})

    def _valor(stats, nombre):
        s = stats.get(nombre)
        return s.get("promedio") if s else None

    orden = {"ok": 0, "warn": 1, "bad": 2}
    nivel_de_estado = {"normal": "ok", "sospechoso": "warn", "problema": "bad", "sin_dato": "ok"}
    por_zona = []
    peor = "ok"
    for i, zona in enumerate(ZONAS_MEZCLA, start=1):
        v_ral = _valor(ralenti_stats, _ES_NATIVO.get(zona, zona))
        v_25 = _valor(p2500_stats, _ES_NATIVO.get(zona, zona))
        valor = v_25 if v_25 is not None else v_ral
        ev = _evaluar_zona_mezcla(valor)
        nivel = nivel_de_estado[ev["estado"]]
        if orden[nivel] > orden[peor]:
            peor = nivel
        por_zona.append({"zona": f"Zona {i}", "dato": zona, "valor": valor,
                         "estado": ev["estado"], "nivel": nivel, "texto": ev["texto"]})

    stft_ralenti = _valor(ralenti_stats, _ES_NATIVO["Facteur enrichissement regulation richesse"])
    stft_2500 = _valor(p2500_stats, _ES_NATIVO["Facteur enrichissement regulation richesse"])
    lazo = (ralenti_stats.get(_ES_NATIVO["Etat stratégie régulation richesse"]) or {})
    v_amont = _valor(ralenti_stats, _ES_NATIVO["Tension sonde amont"])
    amont_osc = (ralenti_stats.get(_ES_NATIVO["Tension sonde amont"]) or {}).get("oscila")

    n_problema = sum(1 for z in por_zona if z["nivel"] == "bad")
    n_sospechoso = sum(1 for z in por_zona if z["nivel"] == "warn")
    if peor == "bad":
        titulo = f"Problema de mezcla detectado ({n_problema} zona{'s' if n_problema != 1 else ''})"
        detalle = ("Al menos una zona de presión superó el ±8% (>25% ya es un problema claro): "
                   "revisar fugas de vacío/admisión, inyectores, MAF o sonda lambda según el "
                   "signo de cada zona (ver detalle por zona).")
    elif peor == "warn":
        titulo = f"Mezcla sospechosa en {n_sospechoso} zona{'s' if n_sospechoso != 1 else ''}"
        detalle = "Algunas zonas están entre ±5% y ±8%: vale la pena vigilar, no es concluyente aún."
    else:
        titulo = "Mezcla dentro de lo normal"
        detalle = "Las 5 zonas de corrección adaptativa están dentro de ±5%."

    veredicto = {"nivel": peor, "titulo": titulo, "detalle": detalle}
    datos["resumen"] = {
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "veredicto": veredicto,
        "por_zona": por_zona,
        "stft_ralenti": stft_ralenti, "stft_2500": stft_2500,
        "lazo_cerrado": lazo,
        "tension_amont": v_amont, "amont_oscila": amont_osc,
        "etapas": {k: {"rpm_prom": v.get("rpm_prom"), "n_muestras": v.get("n_muestras"),
                       "alcanzo_banda": v.get("alcanzo_banda")} for k, v in etapas.items()},
        "estadisticas_ralenti": ralenti_stats, "estadisticas_2500": p2500_stats,
    }
    datos["para_experto"] = {
        "vehiculo": datos.get("vehiculo"), "perfil": datos.get("perfil"), "fecha": datos.get("fecha"),
        "veredicto": veredicto, "por_zona": por_zona,
        "stft": {"ralenti": stft_ralenti, "2500rpm": stft_2500}, "lazo_cerrado": lazo,
        "sonda_amont": {"tension": v_amont, "oscila": amont_osc},
        "estadisticas_ralenti": ralenti_stats, "estadisticas_2500": p2500_stats,
    }
    return datos


def _txt_mezcla(datos):
    r = datos["resumen"]
    L = ["=" * 70, "  CHEQUEO DE MEZCLA — SISTEMASQ24",
         f"  Vehículo: {datos.get('vehiculo')}   |   {datos.get('fecha')}", "=" * 70, ""]
    v = r["veredicto"]
    L.append(f"VEREDICTO: {v['titulo']}")
    L.append(f"  {v['detalle']}")
    L.append("")
    L.append("POR ZONA DE PRESIÓN (ajuste largo nativo del F4R):")
    for z in r["por_zona"]:
        L.append(f"  · {z['zona']} ({z['dato']}): {z['texto']}")
    L.append("")
    L.append(f"Ajuste corto (richesse) — ralentí: {r.get('stft_ralenti')}%  |  a 2500rpm: {r.get('stft_2500')}%")
    lazo = r.get("lazo_cerrado") or {}
    L.append(f"Lazo de riqueza (ralentí): {lazo.get('promedio', '—')}")
    L.append(f"Sonda amont — tensión (ralentí): {r.get('tension_amont')} V  (oscila: {r.get('amont_oscila')})")
    etapas = r.get("etapas", {})
    L.append("")
    L.append("ETAPAS:")
    for nombre, e in etapas.items():
        L.append(f"  · {nombre}: rpm_prom={e.get('rpm_prom')}  muestras={e.get('n_muestras')}  "
                 f"banda_alcanzada={e.get('alcanzo_banda')}")
    return "\n".join(L)


def _html_mezcla(datos):
    r = datos["resumen"]
    v = r.get("veredicto", {})
    vcol = {"ok": "#3ddc97", "warn": "#ffab2e", "bad": "#ff5a5a"}.get(v.get("nivel"), "#8ea0b2")
    vico = {"ok": "🟢", "warn": "🟡", "bad": "🔴"}.get(v.get("nivel"), "⚪")
    nivelico = {"normal": "🟢", "sospechoso": "🟡", "problema": "🔴", "sin_dato": "⚪"}
    css = """body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0e141b;color:#e8eef4;margin:0;padding:24px;line-height:1.5}
    .wrap{max-width:820px;margin:0 auto}
    h1{font-size:23px;margin:0 0 4px}h2{font-size:16px;border-bottom:1px solid #24303f;padding-bottom:6px;margin-top:26px}
    .sub{color:#8ea0b2;font-size:13px;margin-bottom:16px}
    .verdict{display:flex;gap:14px;align-items:flex-start;border-radius:11px;padding:15px 18px;margin:6px 0 8px}
    .verdict .d{font-size:24px;line-height:1}.verdict h3{margin:0 0 3px;font-size:16px}.verdict p{margin:0;font-size:13.5px;color:#cdd8e2}
    .zona{display:flex;align-items:flex-start;gap:10px;padding:9px 0;border-bottom:1px solid #1c2732}
    .zona .ico{font-size:17px}.zona b{font-size:13.5px}.zona .dato{color:#8ea0b2;font-size:11.5px}
    .zona .txt{font-size:13px;color:#cdd8e2;margin-top:2px}
    table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
    th,td{text-align:left;padding:6px 10px;border-bottom:1px solid #1c2732}
    thead th{background:#111922;color:#8ea0b2;font-size:11px;text-transform:uppercase;letter-spacing:.03em}
    .dim{color:#8ea0b2}
    .note{margin-top:16px;padding:10px 14px;background:rgba(47,212,212,.08);border:1px solid rgba(47,212,212,.3);border-radius:8px;font-size:13px;color:#9fd}"""
    H = [f"<style>{css}</style><div class='wrap'>",
         f"<h1>⚗️ Chequeo de mezcla — {_esc(datos.get('vehiculo'))}</h1>",
         f"<div class='sub'>{_esc(datos.get('fecha'))} · perfil {_esc(datos.get('perfil'))} · ralentí + ~2500 rpm</div>",
         f"<div class='verdict' style='background:{vcol}1a;border:1px solid {vcol};border-left:5px solid {vcol}'>"
         f"<span class='d'>{vico}</span><div><h3 style='color:{vcol}'>{_esc(v.get('titulo',''))}</h3><p>{_esc(v.get('detalle',''))}</p></div></div>"]
    H.append("<h2>Por zona de presión (ajuste largo nativo)</h2>")
    for z in r["por_zona"]:
        H.append(f"<div class='zona'><span class='ico'>{nivelico.get(z['estado'],'⚪')}</span>"
                 f"<div><b>{_esc(z['zona'])}</b> <span class='dato'>({_esc(z['dato'])})</span>"
                 f"<div class='txt'>{_esc(z['texto'])}</div></div></div>")
    H.append("<h2>Otros datos de mezcla</h2>")
    H.append("<table><tbody>")
    H.append(f"<tr><td>Ajuste corto (richesse) — ralentí</td><td>{_esc(r.get('stft_ralenti'))}%</td></tr>")
    H.append(f"<tr><td>Ajuste corto (richesse) — a 2500rpm</td><td>{_esc(r.get('stft_2500'))}%</td></tr>")
    lazo = r.get("lazo_cerrado") or {}
    H.append(f"<tr><td>Lazo de riqueza (ralentí)</td><td>{_esc(lazo.get('promedio','—'))}</td></tr>")
    H.append(f"<tr><td>Sonda amont — tensión (ralentí)</td><td>{_esc(r.get('tension_amont'))} V "
             f"<span class='dim'>(oscila: {_esc(r.get('amont_oscila'))})</span></td></tr>")
    H.append("</tbody></table>")
    etapas = r.get("etapas", {})
    if etapas:
        H.append("<h2>Etapas capturadas</h2><table><thead><tr><th>Etapa</th><th>RPM prom.</th>"
                 "<th>Muestras</th><th>Banda alcanzada</th></tr></thead><tbody>")
        for nombre, e in etapas.items():
            H.append(f"<tr><td>{_esc(nombre)}</td><td>{_esc(e.get('rpm_prom'))}</td>"
                     f"<td>{_esc(e.get('n_muestras'))}</td><td>{_esc(e.get('alcanzo_banda'))}</td></tr>")
        H.append("</tbody></table>")
    H.append("<div class='note'>Chequeo enfocado solo en mezcla (RPM, MAP, las 5 zonas de ajuste "
             "largo, ajuste corto, lazo y sondas de oxígeno) — no barre otras ECUs. El <b>.json</b> "
             "trae el bloque <code>para_experto</code> con todo junto. Podés imprimir esta página "
             "a PDF (Ctrl+P).</div></div>")
    return "\n".join(H)


def generar_mezcla(datos):
    """Analiza el chequeo de mezcla y escribe HTML/JSON/TXT. Devuelve {html,json,txt,carpeta,nombre}."""
    _mezcla_analizar(datos)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    nombre = "mezcla_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    p_json = LOG_DIR / f"{nombre}.json"
    p_txt = LOG_DIR / f"{nombre}.txt"
    p_html = LOG_DIR / f"{nombre}.html"
    p_json.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    p_txt.write_text(_txt_mezcla(datos), encoding="utf-8")
    p_html.write_text("<!doctype html><meta charset='utf-8'><title>Mezcla " +
                      _esc(datos.get("vehiculo", "")) + "</title>" + _html_mezcla(datos), encoding="utf-8")
    return {"html": str(p_html), "json": str(p_json), "txt": str(p_txt),
            "carpeta": str(LOG_DIR), "nombre": nombre}


# ============================================================================
# PRUEBA DE VACÍO (2 etapas: ralentí + ~2500 rpm)
# ============================================================================
def _vacio_analizar(datos):
    """Evalúa la zona 1 (ralentí/baja carga) con el criterio de mezcla ya validado, el MAP
    de ralentí contra el rango curado, y el estado de lazo — esos 3 son el veredicto "duro".
    Los datos de RCO/corrección/aprendizaje de ralentí y purga canister se muestran como
    evidencia de apoyo (ralentí vs. 2500rpm) SIN clasificación, porque no hay un umbral
    numérico confirmado para ellos (ninguna de las variantes de S3000 en la base lo trae)."""
    from prueba_vacio import ZONAS_VACIO
    etapas = datos.get("etapas", {})
    ralenti_stats = (etapas.get("ralenti") or {}).get("estadisticas", {})
    p2500_stats = (etapas.get("2500") or {}).get("estadisticas", {})

    def _valor(stats, nombre):
        s = stats.get(nombre)
        return s.get("promedio") if s else None

    def _valor_unidad(stats, nombre):
        s = stats.get(nombre)
        if not s:
            return None, ""
        return s.get("promedio"), s.get("unidad", "")

    # --- zona 1 (ralentí/baja carga): mismo evaluador ya validado en mezcla ---
    # Ojo: ZONAS_VACIO trae el nombre ORIGINAL francés (se usa para filtrar requests); las
    # estadísticas están indexadas por la ETIQUETA en español (_ES_NATIVO la traduce).
    zona1_dato = ZONAS_VACIO[0]
    v_ral = _valor(ralenti_stats, _ES_NATIVO.get(zona1_dato, zona1_dato))
    v_25 = _valor(p2500_stats, _ES_NATIVO.get(zona1_dato, zona1_dato))
    zona1_valor = v_25 if v_25 is not None else v_ral
    ev_zona1 = _evaluar_zona_mezcla(zona1_valor)
    nivel_de_estado = {"normal": "ok", "sospechoso": "warn", "problema": "bad", "sin_dato": "ok"}
    nivel_zona1 = nivel_de_estado[ev_zona1["estado"]]
    # Patrón de CONVERGENCIA (investigado): una fuga de vacío real hace que el ajuste se
    # normalice al acelerar (el aire de la fuga pesa menos sobre el total que entra). Si en
    # ralentí está mal y en 2500rpm mejora claramente, es una firma típica de fuga — más
    # específica que solo mirar un valor aislado. Si sigue mal en las dos etapas, es más
    # probable que sea otra causa (inyector, sonda, MAF/MAP) que una fuga de vacío puntual.
    converge = (v_ral is not None and v_25 is not None
                and abs(v_ral) > 8 and abs(v_25) < abs(v_ral) * 0.5)
    persiste = (v_ral is not None and v_25 is not None
                and abs(v_ral) > 8 and abs(v_25) > 8)

    # --- MAP a ralentí: contra el rango curado (rangos_f4r.json) ---
    map_prom, map_unidad = _valor_unidad(ralenti_stats, "Presión absoluta del colector medida")
    rangos = _cargar_rangos()
    if map_prom is not None:
        ev_map = _evaluar("presión absoluta del colector", f"{map_prom} {map_unidad}", rangos)
    else:
        ev_map = {"estado": "sin_rango"}
    nivel_map = {"ok": "ok", "atencion": "bad", "sin_rango": "ok"}[ev_map["estado"]]

    # --- lazo cerrado (BOUCLE) en ralentí ---
    lazo_ral = (ralenti_stats.get(_ES_NATIVO["Etat stratégie régulation richesse"]) or {})
    lazo_txt = str(lazo_ral.get("promedio", "")) if lazo_ral else ""
    lazo_cerrado = "1" in lazo_txt or "bouc" in lazo_txt.lower()
    nivel_lazo = "ok" if (not lazo_ral or lazo_cerrado) else "warn"

    # --- sonda lambda anterior: ¿oscila a ralentí? (investigado: una fuga grande puede
    # hacer que la sonda quede "pegada pobre" sin oscilar, en vez de solo subir el ajuste) ---
    sonda_ral = (ralenti_stats.get(_ES_NATIVO["Tension sonde amont"]) or {})
    sonda_oscila = sonda_ral.get("oscila")
    # Solo cuenta como señal de alarma si además hay indicios de mezcla pobre (zona1/map mal)
    # — una sonda quieta por sí sola puede ser solo que el motor no varió de régimen/carga.
    nivel_sonda = "ok"
    if sonda_ral and sonda_oscila is False and (nivel_zona1 == "bad" or nivel_map == "bad"):
        nivel_sonda = "bad"

    orden = {"ok": 0, "warn": 1, "bad": 2}
    peor = max([nivel_zona1, nivel_map, nivel_lazo, nivel_sonda], key=lambda n: orden[n])

    if peor == "bad":
        titulo = "Evidencia de fuga de vacío / entrada de aire no medida"
        detalle = ("La zona 1 (ralentí/baja carga) del ajuste largo y/o la presión de colector "
                   "a ralentí están fuera de lo esperado — patrón típico de una fuga de vacío. "
                   "Revisar manguera de servofreno, PCV, junta de admisión, cuerpo de mariposa "
                   "y sus O-rings.")
        if nivel_sonda == "bad":
            detalle += (" La sonda lambda anterior NO está oscilando en ralentí (se quedó fija "
                        "en un valor bajo) — refuerza la sospecha: con una fuga grande, la sonda "
                        "puede quedar \"pegada pobre\" en vez de oscilar normalmente.")
        if converge:
            detalle += (" El ajuste mejora claramente al acelerar a 2500rpm — patrón específico "
                        "de fuga de vacío (el aire de la fuga pesa menos sobre el total que entra "
                        "con más carga).")
        elif persiste:
            detalle += (" El ajuste sigue mal incluso a 2500rpm — esto es MENOS típico de una "
                        "fuga de vacío puntual y más compatible con otra causa (inyector, sonda, "
                        "calibración de MAP/presión), conviene no asumir que es solo una fuga.")
    elif peor == "warn":
        titulo = "Indicios sospechosos, no concluyente"
        detalle = "Alguno de los datos clave está en zona de sospecha, no de problema claro todavía."
    else:
        titulo = "Sin evidencia clara de fuga de vacío"
        detalle = "La zona 1, el MAP a ralentí y el lazo de riqueza están dentro de lo esperado."
        if sonda_ral and sonda_oscila:
            detalle += " La sonda lambda anterior oscila con normalidad en ralentí."
    veredicto = {"nivel": peor, "titulo": titulo, "detalle": detalle}

    # --- evidencia de apoyo: ralentí vs 2500rpm, SIN umbral (no confirmado con fuente) ---
    def _apoyo(nombre_es):
        v_r, u = _valor_unidad(ralenti_stats, nombre_es)
        v_2, _ = _valor_unidad(p2500_stats, nombre_es)
        return {"dato": nombre_es, "ralenti": v_r, "2500rpm": v_2, "unidad": u}

    apoyo = [
        _apoyo("Ciclo de trabajo (RCO) teórico de la regulación del ralentí"),
        _apoyo("Corrección del régimen de ralentí de posventa"),
        _apoyo("Valor de aprendizaje de la regulación del ralentí"),
        _apoyo("Ciclo de trabajo (RCO) de la purga del cánister"),
    ]
    rpm_consigna = _valor(ralenti_stats, "Régimen de consigna de la regulación del ralentí")
    rpm_real = _valor(ralenti_stats, "Régimen del motor (RPM)")

    datos["resumen"] = {
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "veredicto": veredicto,
        "zona1": {"dato": zona1_dato, "valor": zona1_valor, "estado": ev_zona1["estado"],
                  "nivel": nivel_zona1, "texto": ev_zona1["texto"]},
        "map_ralenti": {"valor": map_prom, "unidad": map_unidad, "estado": ev_map["estado"],
                        "nivel": nivel_map},
        "lazo_cerrado_ralenti": lazo_txt or None,
        "sonda_amont_oscila_ralenti": sonda_oscila,
        "zona1_converge_al_acelerar": converge, "zona1_persiste_al_acelerar": persiste,
        "rpm_consigna_ralenti": rpm_consigna, "rpm_real_ralenti": rpm_real,
        "apoyo": apoyo,
        "etapas": {k: {"rpm_prom": v.get("rpm_prom"), "n_muestras": v.get("n_muestras"),
                       "alcanzo_banda": v.get("alcanzo_banda")} for k, v in etapas.items()},
        "estadisticas_ralenti": ralenti_stats, "estadisticas_2500": p2500_stats,
    }
    datos["para_experto"] = {
        "vehiculo": datos.get("vehiculo"), "perfil": datos.get("perfil"), "fecha": datos.get("fecha"),
        "veredicto": veredicto, "zona1": datos["resumen"]["zona1"],
        "map_ralenti": datos["resumen"]["map_ralenti"],
        "rpm": {"consigna_ralenti": rpm_consigna, "real_ralenti": rpm_real},
        "evidencia_de_apoyo_sin_umbral_confirmado": apoyo,
        "estadisticas_ralenti": ralenti_stats, "estadisticas_2500": p2500_stats,
    }
    return datos


def _txt_vacio(datos):
    r = datos["resumen"]
    L = ["=" * 70, "  PRUEBA DE VACÍO — SISTEMASQ24",
         f"  Vehículo: {datos.get('vehiculo')}   |   {datos.get('fecha')}", "=" * 70, ""]
    v = r["veredicto"]
    L.append(f"VEREDICTO: {v['titulo']}")
    L.append(f"  {v['detalle']}")
    L.append("")
    z = r["zona1"]
    L.append(f"Zona 1 de ajuste largo (ralentí/baja carga): {z['texto']}")
    m = r["map_ralenti"]
    L.append(f"Presión de colector (MAP) a ralentí: {m['valor']} {m['unidad']} "
             f"({'dentro de rango' if m['estado']=='ok' else ('fuera de rango' if m['estado']=='atencion' else 'sin rango de referencia')})")
    L.append(f"Lazo de riqueza (ralentí): {r.get('lazo_cerrado_ralenti') or '—'}")
    osc = r.get('sonda_amont_oscila_ralenti')
    L.append(f"Sonda lambda anterior oscila en ralentí: {'sí' if osc else ('no' if osc is False else '—')}")
    L.append(f"RPM consigna vs. real en ralentí: {r.get('rpm_consigna_ralenti')} vs {r.get('rpm_real_ralenti')}")
    L.append("")
    L.append("EVIDENCIA DE APOYO (ralentí vs. 2500rpm — sin umbral numérico confirmado):")
    for a in r["apoyo"]:
        L.append(f"  · {a['dato']}: {a['ralenti']} -> {a['2500rpm']} {a['unidad']}")
    L.append("")
    etapas = r.get("etapas", {})
    L.append("ETAPAS:")
    for nombre, e in etapas.items():
        L.append(f"  · {nombre}: rpm_prom={e.get('rpm_prom')}  muestras={e.get('n_muestras')}  "
                 f"banda_alcanzada={e.get('alcanzo_banda')}")
    return "\n".join(L)


def _html_vacio(datos):
    r = datos["resumen"]
    v = r.get("veredicto", {})
    vcol = {"ok": "#3ddc97", "warn": "#ffab2e", "bad": "#ff5a5a"}.get(v.get("nivel"), "#8ea0b2")
    vico = {"ok": "🟢", "warn": "🟡", "bad": "🔴"}.get(v.get("nivel"), "⚪")
    css = """body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0e141b;color:#e8eef4;margin:0;padding:24px;line-height:1.5}
    .wrap{max-width:820px;margin:0 auto}
    h1{font-size:23px;margin:0 0 4px}h2{font-size:16px;border-bottom:1px solid #24303f;padding-bottom:6px;margin-top:26px}
    .sub{color:#8ea0b2;font-size:13px;margin-bottom:16px}
    .verdict{display:flex;gap:14px;align-items:flex-start;border-radius:11px;padding:15px 18px;margin:6px 0 8px}
    .verdict .d{font-size:24px;line-height:1}.verdict h3{margin:0 0 3px;font-size:16px}.verdict p{margin:0;font-size:13.5px;color:#cdd8e2}
    table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
    th,td{text-align:left;padding:6px 10px;border-bottom:1px solid #1c2732}
    thead th{background:#111922;color:#8ea0b2;font-size:11px;text-transform:uppercase;letter-spacing:.03em}
    .dim{color:#8ea0b2}
    .note{margin-top:16px;padding:10px 14px;background:rgba(47,212,212,.08);border:1px solid rgba(47,212,212,.3);border-radius:8px;font-size:13px;color:#9fd}
    .warnbox{margin-top:10px;padding:10px 14px;background:rgba(255,171,46,.08);border:1px solid rgba(255,171,46,.3);border-radius:8px;font-size:12.5px;color:#ffcf8a}"""
    H = [f"<style>{css}</style><div class='wrap'>",
         f"<h1>🕳️ Prueba de vacío — {_esc(datos.get('vehiculo'))}</h1>",
         f"<div class='sub'>{_esc(datos.get('fecha'))} · perfil {_esc(datos.get('perfil'))} · ralentí + ~2500 rpm</div>",
         f"<div class='verdict' style='background:{vcol}1a;border:1px solid {vcol};border-left:5px solid {vcol}'>"
         f"<span class='d'>{vico}</span><div><h3 style='color:{vcol}'>{_esc(v.get('titulo',''))}</h3><p>{_esc(v.get('detalle',''))}</p></div></div>"]
    H.append("<h2>Datos clave (veredicto)</h2><table><tbody>")
    z = r["zona1"]
    H.append(f"<tr><td>Zona 1 de ajuste largo (ralentí/baja carga)</td><td>{_esc(z['texto'])}</td></tr>")
    m = r["map_ralenti"]
    est_map = {"ok": "dentro de rango", "atencion": "fuera de rango", "sin_rango": "sin referencia"}.get(m["estado"], "")
    H.append(f"<tr><td>Presión de colector (MAP) a ralentí</td><td>{_esc(m['valor'])} {_esc(m['unidad'])} — {_esc(est_map)}</td></tr>")
    H.append(f"<tr><td>Lazo de riqueza (ralentí)</td><td>{_esc(r.get('lazo_cerrado_ralenti') or '—')}</td></tr>")
    osc = r.get('sonda_amont_oscila_ralenti')
    H.append(f"<tr><td>Sonda lambda anterior oscila en ralentí</td><td>{'sí' if osc else ('no' if osc is False else '—')}</td></tr>")
    H.append(f"<tr><td>RPM consigna vs. real (ralentí)</td><td>{_esc(r.get('rpm_consigna_ralenti'))} vs {_esc(r.get('rpm_real_ralenti'))}</td></tr>")
    H.append("</tbody></table>")
    H.append("<h2>Evidencia de apoyo (ralentí → 2500rpm)</h2>")
    H.append("<div class='warnbox'>⚠️ Estos 4 datos NO tienen un umbral numérico confirmado con documentación de Renault "
             "(ninguna de las 15 variantes de la base lo trae) — se muestran para comparar, no como pass/fail. "
             "Si mejoran mucho al acelerar, refuerza la hipótesis de fuga (se diluye con más aire real entrando); "
             "si no cambian, el problema probablemente no es una fuga de vacío.</div>")
    H.append("<table><thead><tr><th>Dato</th><th>Ralentí</th><th>~2500rpm</th></tr></thead><tbody>")
    for a in r["apoyo"]:
        H.append(f"<tr><td>{_esc(a['dato'])}</td><td>{_esc(a['ralenti'])} {_esc(a['unidad'])}</td>"
                 f"<td>{_esc(a['2500rpm'])} {_esc(a['unidad'])}</td></tr>")
    H.append("</tbody></table>")
    etapas = r.get("etapas", {})
    if etapas:
        H.append("<h2>Etapas capturadas</h2><table><thead><tr><th>Etapa</th><th>RPM prom.</th>"
                 "<th>Muestras</th><th>Banda alcanzada</th></tr></thead><tbody>")
        for nombre, e in etapas.items():
            H.append(f"<tr><td>{_esc(nombre)}</td><td>{_esc(e.get('rpm_prom'))}</td>"
                     f"<td>{_esc(e.get('n_muestras'))}</td><td>{_esc(e.get('alcanzo_banda'))}</td></tr>")
        H.append("</tbody></table>")
    H.append("<div class='note'>Prueba enfocada en fuga de vacío (RPM, MAP, RCO/corrección/aprendizaje de "
             "ralentí, purga canister, zona 1 de ajuste largo, lazo) — no barre otras ECUs. El <b>.json</b> "
             "trae el bloque <code>para_experto</code> con todo junto. Podés imprimir esta página a PDF "
             "(Ctrl+P).</div></div>")
    return "\n".join(H)


def generar_vacio(datos):
    """Analiza la prueba de vacío y escribe HTML/JSON/TXT. Devuelve {html,json,txt,carpeta,nombre}."""
    _vacio_analizar(datos)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    nombre = "vacio_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    p_json = LOG_DIR / f"{nombre}.json"
    p_txt = LOG_DIR / f"{nombre}.txt"
    p_html = LOG_DIR / f"{nombre}.html"
    p_json.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    p_txt.write_text(_txt_vacio(datos), encoding="utf-8")
    p_html.write_text("<!doctype html><meta charset='utf-8'><title>Vacío " +
                      _esc(datos.get("vehiculo", "")) + "</title>" + _html_vacio(datos), encoding="utf-8")
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
