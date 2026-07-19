# -*- coding: utf-8 -*-
"""Chequeo General del Auto — orquestador (máquina de estados en background).

Lee todo el auto (todas las ECUs + DTCs) a ralentí, después captura los sensores del
motor a 1500/2000/3000 rpm mientras el usuario acelera, y arma la estructura de datos
que `reporte.py` convierte en el informe (HTML/JSON/TXT).

Diseño desacoplado: `run_chequeo(ctx)` recibe un contexto con todo lo que necesita del
server (registro, seleccionar_ecu, lock, callbacks), así se testea sin imports circulares
y funciona en simulación (RPM en rampa canned).
"""
import time
from datetime import datetime

# Bandas y tiempos de captura (constantes ajustables).
BANDA_RPM = 200        # ± rpm alrededor del objetivo para considerar "en banda"
ESTABLE_SEG = 2.5      # cuánto tiene que mantenerse en banda antes de capturar
CAPTURA_SEG = 5.0      # duración de cada captura del motor por etapa
INTERVALO_MS = 250     # entre muestras de la captura del motor
TIMEOUT_ETAPA = 60     # seg máx esperando que llegue a una RPM antes de ofrecer manual
RALENTI_SEG = 5.0      # duración de la captura a ralentí

ETAPAS_RPM = [1500, 2000, 3000]

# Nombres (dato original) de los sensores CLAVE que varían con las RPM — se capturan
# a alta frecuencia en las etapas de RPM. Si no se encuentran (otro perfil), se cae a
# los primeros requests útiles.
DATOS_CLAVE_F4R = [
    "Régime moteur", "Température eau mesurée", "Température air mesurée",
    "Pression collecteur absolue mesurée", "Avance allumage",
    "Tension sonde amont", "Tension sonde aval", "Temps injection réel",
    "Position papillon mesurée piste 1 après filtrage", "Tension batterie mesurée",
    "Pression de suralimentation",
]
DATOS_CLAVE_OBD = [
    "Régimen del motor (RPM)", "Temperatura del refrigerante",
    "Temperatura del aire de admisión", "Presión absoluta del colector (MAP)",
    "Avance de encendido", "Sonda lambda 1 — tensión", "Posición del acelerador",
    "Tensión del módulo (batería)", "Caudal de aire (MAF)",
]


def estadisticas_de_muestras(muestras):
    """Calcula estadísticas por sensor a partir de una lista de muestras
    [{timestamp, valores:{etiqueta: "valor unidad"}}]. Devuelve
    {etiqueta: {promedio, minimo, maximo, desv_std, unidad, muestras, oscila}}.
    Portado de session_logger.log_captura_pantalla (misma lógica)."""
    acum = {}
    for m in muestras:
        for sensor, valor_str in (m.get("valores") or {}).items():
            if sensor not in acum:
                acum[sensor] = {"valores": [], "unidad": ""}
            partes = str(valor_str).split()
            try:
                acum[sensor]["valores"].append(float(partes[0]))
                if len(partes) > 1:
                    acum[sensor]["unidad"] = " ".join(partes[1:])
            except (ValueError, IndexError):
                pass
    out = {}
    for sensor, d in acum.items():
        vals = d["valores"]
        if not vals:
            continue
        prom = sum(vals) / len(vals)
        var = sum((x - prom) ** 2 for x in vals) / len(vals) if len(vals) > 1 else 0
        desv = var ** 0.5
        out[sensor] = {
            "promedio": round(prom, 2), "minimo": round(min(vals), 2),
            "maximo": round(max(vals), 2), "desv_std": round(desv, 2),
            "unidad": d["unidad"], "muestras": len(vals),
            "oscila": (max(vals) - min(vals)) > (abs(prom) * 0.05 + 0.01),
        }
    return out


class Chequeo:
    """Ejecuta el chequeo. `ctx` provee: registro, seleccionar_ecu(id), elm_lock,
    marcar_actividad(), set_estado(dict), cancelado()->bool, simulacion(bool),
    log(tipo,msg,det), capturar_ahora()->bool (flag de captura manual)."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.datos = {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "perfil": ctx.registro.perfil,
            "vehiculo": ctx.registro.vehiculo,
            "ecus": [],
            "rpm_etapas": {},
        }
        self._t0_sim = time.time()

    # ------------------------------------------------------------------ helpers
    def _set(self, **kw):
        self.ctx.set_estado(kw)

    def _leer_request(self, tecu, request):
        """Lee un request bajo el lock del ELM; devuelve {dato:{etiqueta,valor,unidad}} o None."""
        with self.ctx.elm_lock:
            self.ctx.marcar_actividad()
            self.ctx.seleccionar_ecu(tecu.id)
            try:
                return tecu.read_request(request)
            except Exception:
                return None

    def _valores_legibles(self, valores):
        """{dato:{etiqueta,valor,unidad}} -> {etiqueta: 'valor unidad'} (solo no-nulos)."""
        out = {}
        for k, info in (valores or {}).items():
            v = info.get("valor")
            if v is None or str(v).strip() == "":
                continue
            u = info.get("unidad", "")
            out[info.get("etiqueta", k)] = f"{v} {u}".strip()
        return out

    # ------------------------------------------------------------------ RPM
    def _param_rpm(self, tecu):
        """Ubica el request/dato/etiqueta de las RPM del motor. Devuelve (request,dato,etiqueta) o None."""
        for p in tecu.readable_params():
            texto = (p.get("dato", "") + " " + p.get("etiqueta", "")).lower()
            if "régime" in texto or "regime" in texto or "régimen" in texto or "rpm" in texto:
                return p["request"], p["dato"], p["etiqueta"]
        return None

    def _requests_captura(self, tecu):
        """Requests a capturar en las etapas de RPM: los de los sensores CLAVE (para que
        sea rápido y con buena frecuencia). Fallback: primeros útiles."""
        clave = DATOS_CLAVE_OBD if self.datos["perfil"] == "generico" else DATOS_CLAVE_F4R
        params = tecu.readable_params()
        reqs = []
        for p in params:
            if p.get("dato") in clave and p["request"] not in reqs:
                reqs.append(p["request"])
        if not reqs:  # otro perfil / no matchea: primeros útiles
            for p in params:
                if p.get("util") is not False and p["request"] not in reqs:
                    reqs.append(p["request"])
                if len(reqs) >= 4:
                    break
        return reqs

    def _leer_rpm(self, tecu, rpm_info, objetivo_sim=None):
        """Lee las RPM actuales. En simulación devuelve una rampa hacia objetivo_sim."""
        if self.ctx.simulacion():
            # rampa: en ~4s llega al objetivo y se queda ahí
            base = objetivo_sim if objetivo_sim else 850
            t = time.time() - self._t0_sim
            return min(base, 400 + t * 250) if objetivo_sim else 850
        req, dato, _et = rpm_info
        vals = self._leer_request(tecu, req)
        if not vals or dato not in vals:
            return None
        try:
            return float(str(vals[dato].get("valor")).split()[0])
        except (ValueError, TypeError, IndexError):
            return None

    def _capturar_motor(self, tecu, reqs, segundos):
        """Captura los `reqs` del motor durante `segundos`. Devuelve lista de muestras."""
        muestras = []
        t0 = time.time()
        while time.time() - t0 < segundos:
            if self.ctx.cancelado():
                break
            valores = {}
            for r in reqs:
                v = self._leer_request(tecu, r)
                if v:
                    valores.update(self._valores_legibles(v))
            if valores:
                muestras.append({"timestamp": round(time.time() - t0, 2), "valores": valores})
            time.sleep(INTERVALO_MS / 1000.0)
        return muestras

    # ------------------------------------------------------------------ fases
    def _fase_paneo(self):
        """Lee todas las ECUs del perfil: identificación + una lectura de cada request
        legible + DTCs."""
        ecus = self.ctx.registro.list()
        total = max(1, len(ecus))
        for i, info in enumerate(ecus):
            if self.ctx.cancelado():
                return False
            eid = info["id"]
            tecu = self.ctx.registro.get(eid)
            self._set(fase="paneo", progreso=round(i / total * 100),
                      instruccion=f"Leyendo {info['nombre']}… ({i+1}/{total})")
            ecu_data = {"id": eid, "nombre": info["nombre"], "icon": info.get("icon", ""),
                        "identificacion": {}, "presente": None, "sensores": {}, "dtcs": []}
            # identificación
            try:
                with self.ctx.elm_lock:
                    self.ctx.marcar_actividad()
                    self.ctx.seleccionar_ecu(eid)
                    ident = tecu.scan_identidad()
                ecu_data["presente"] = ident.get("presente")
                ecu_data["identificacion"] = ident.get("identificacion", {})
            except Exception:
                pass
            # una lectura de cada request legible (deduplicado)
            reqs = []
            for p in tecu.readable_params():
                if p["request"] not in reqs:
                    reqs.append(p["request"])
            for r in reqs:
                if self.ctx.cancelado():
                    return False
                vals = self._leer_request(tecu, r)
                if vals:
                    ecu_data["sensores"].update(self._valores_legibles(vals))
            # DTCs
            try:
                with self.ctx.elm_lock:
                    self.ctx.marcar_actividad()
                    self.ctx.seleccionar_ecu(eid)
                    dtc = tecu.read_dtcs()
                ecu_data["dtcs"] = dtc.get("dtcs", [])
            except Exception:
                pass
            self.datos["ecus"].append(ecu_data)
        return True

    def _motor_tecu(self):
        """Devuelve el TranslatedECU del motor del perfil activo (o el primero que haya)."""
        for cand in ("motor", "obd"):
            t = self.ctx.registro.get(cand)
            if t is not None:
                return t
        lst = self.ctx.registro.list()
        return self.ctx.registro.get(lst[0]["id"]) if lst else None

    def _fase_rpm(self):
        """Captura del motor a ralentí y a 1500/2000/3000 rpm."""
        tecu = self._motor_tecu()
        if tecu is None:
            return True
        rpm_info = self._param_rpm(tecu)
        reqs = self._requests_captura(tecu)

        # --- Ralentí ---
        self._set(fase="ralenti", rpm_objetivo=0, progreso=0,
                  instruccion="Dejá el auto en RALENTÍ. Capturando…")
        muestras = self._capturar_motor(tecu, reqs, RALENTI_SEG)
        self.datos["rpm_etapas"]["ralenti"] = self._resumir_etapa(muestras, rpm_info, tecu)

        # --- 1500 / 2000 / 3000 ---
        for objetivo in ETAPAS_RPM:
            if self.ctx.cancelado():
                return False
            self._t0_sim = time.time()  # reiniciar rampa sim para esta etapa
            t_ini = time.time()
            estable_desde = None
            self.ctx.reset_capturar_ahora()
            # esperar a que llegue y se estabilice (o captura manual, o timeout)
            while True:
                if self.ctx.cancelado():
                    return False
                rpm = self._leer_rpm(tecu, rpm_info, objetivo_sim=objetivo)
                self._set(fase=f"esperando_{objetivo}", rpm_objetivo=objetivo,
                          rpm_actual=round(rpm) if rpm is not None else None,
                          instruccion=f"Llevá el motor a {objetivo} RPM y mantené…")
                en_banda = rpm is not None and abs(rpm - objetivo) <= BANDA_RPM
                if en_banda:
                    if estable_desde is None:
                        estable_desde = time.time()
                    elif time.time() - estable_desde >= ESTABLE_SEG:
                        break
                else:
                    estable_desde = None
                if self.ctx.capturar_ahora():
                    break
                if time.time() - t_ini > TIMEOUT_ETAPA and not self.ctx.simulacion():
                    # ofrecer captura manual: seguir esperando pero avisando
                    self._set(instruccion=f"No detecté {objetivo} RPM estable. "
                              f"Poné el motor ahí y tocá 'Capturar ahora'.", timeout=True)
                time.sleep(0.3)
            self._set(fase=f"capturando_{objetivo}", rpm_objetivo=objetivo,
                      instruccion=f"Capturando a {objetivo} RPM…")
            muestras = self._capturar_motor(tecu, reqs, CAPTURA_SEG)
            self.datos["rpm_etapas"][str(objetivo)] = self._resumir_etapa(muestras, rpm_info, tecu)
        return True

    def _resumir_etapa(self, muestras, rpm_info, tecu):
        stats = estadisticas_de_muestras(muestras)
        rpm_prom = None
        if rpm_info:
            et = rpm_info[2]
            if et in stats:
                rpm_prom = stats[et]["promedio"]
        return {"rpm_prom": rpm_prom, "n_muestras": len(muestras), "estadisticas": stats}

    # ------------------------------------------------------------------ run
    def run(self):
        try:
            if not self._fase_paneo():
                return {"ok": False, "error": "Chequeo cancelado en el paneo."}
            if not self._fase_rpm():
                return {"ok": False, "error": "Chequeo cancelado en las etapas de RPM."}
            self._set(fase="reporte", progreso=100, instruccion="Generando el reporte…")
            import reporte
            rutas = reporte.generar(self.datos)
            return {"ok": True, "vehiculo": self.datos["vehiculo"],
                    "n_ecus": len(self.datos["ecus"]),
                    "etapas": list(self.datos["rpm_etapas"].keys()),
                    "reporte": rutas}
        except Exception as e:
            self.ctx.log("CHEQUEO", f"Error en el chequeo: {e}", {})
            return {"ok": False, "error": f"Error en el chequeo: {e}"}
