# -*- coding: utf-8 -*-
"""Chequeo de mezcla — pantalla exclusiva y rápida para diagnosticar mezcla rica/pobre.

A diferencia de Chequeo General (paneo de todas las ECUs + 4 etapas de RPM), esto lee
SOLO los sensores de mezcla (RPM, MAP, las 5 zonas nativas de ajuste largo, ajuste corto,
lazo abierto/cerrado, sondas lambda) en 2 etapas: ralentí y ~2500 RPM sostenidas. No barre
otras ECUs, así queda rápido y no compite con otras lecturas.

Mismo diseño desacoplado que chequeo.py: `ChequeoMezcla(ctx).run()` recibe un contexto con
lo que necesita del server (registro, seleccionar_ecu, lock, callbacks).
"""
import time
from datetime import datetime

from chequeo import (estadisticas_de_muestras, BANDA_RPM, ESTABLE_SEG,
                      CAPTURA_SEG, INTERVALO_MS, TIMEOUT_ETAPA, RALENTI_SEG,
                      PROBE_RPM_SEG)

RPM_OBJETIVO_MEZCLA = 2500

# Sensores fijos para el diagnóstico de mezcla — nada más se lee (rápido, no compite por
# el ELM con otras lecturas). Nombres `dato` EXACTOS del F4R (ver SENSOR_ALIAS en index.html).
DATOS_MEZCLA_F4R = [
    "Régime moteur", "Pression collecteur absolue mesurée",
    "Correction adaptative de la 1ère zone de pression",
    "Correction adaptative de la 2ème zone de pression",
    "Correction adaptative de la 3ème zone de pression",
    "Correction adaptative de la 4ème zone de pression",
    "Correction adaptative de la 5ème zone de pression",
    "Facteur enrichissement regulation richesse",
    "Etat stratégie régulation richesse",
    "Tension sonde amont", "Tension sonde aval",
]
ZONAS_MEZCLA = DATOS_MEZCLA_F4R[2:7]   # las 5 "Correction adaptative de la Nème zone..."


class ChequeoMezcla:
    """ctx: mismo contrato que chequeo._CtxChequeo (registro, seleccionar_ecu, elm_lock,
    marcar_actividad, set_estado, cancelado, capturar_ahora, reset_capturar_ahora,
    simulacion, log) + pausar_lecturas()->bool (para autopausarse en reaprendizajes)."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.datos = {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "perfil": ctx.registro.perfil,
            "vehiculo": ctx.registro.vehiculo,
            "etapas": {},
        }
        self._t0_sim = time.time()

    # ------------------------------------------------------------------ helpers
    # Copiados tal cual de chequeo.Chequeo (son genéricos, no dependen del paneo/4-etapas).
    def _set(self, **kw):
        self.ctx.set_estado(kw)

    def _leer_request(self, tecu, request):
        with self.ctx.elm_lock:
            self.ctx.marcar_actividad()
            self.ctx.seleccionar_ecu(tecu.id)
            try:
                return tecu.read_request(request)
            except Exception:
                return None

    def _valores_legibles(self, valores):
        out = {}
        for k, info in (valores or {}).items():
            v = info.get("valor")
            if v is None or str(v).strip() == "":
                continue
            u = info.get("unidad", "")
            out[info.get("etiqueta", k)] = f"{v} {u}".strip()
        return out

    def _param_rpm(self, tecu):
        obd_reqs = {"01" + p for p in getattr(tecu, "obd_extra", [])}
        malos = ("correction", "consigne", "cible", "souhait", "objectif", "ralenti",
                 "seuil", "après-vente", "apres-vente", "min", "max", "delta", "écart", "ecart")
        mejor = None
        for p in tecu.readable_params():
            if p["request"] in obd_reqs:
                continue
            texto = (p.get("dato", "") + " " + p.get("etiqueta", "")).lower()
            if not ("régime" in texto or "regime" in texto or "régimen" in texto or "rpm" in texto):
                continue
            if any(m in texto for m in malos):
                continue
            if ("régime moteur" in texto or "regime moteur" in texto
                    or "régimen del motor" in texto or "régimen motor" in texto):
                return p["request"], p["dato"], p["etiqueta"]
            if mejor is None:
                mejor = (p["request"], p["dato"], p["etiqueta"])
        return mejor

    def _requests_captura(self, tecu):
        """A diferencia de chequeo.py: SIEMPRE los requests de DATOS_MEZCLA_F4R fijos
        (sin fallback a "primeros útiles" — la lista de mezcla es chica y fija)."""
        params = tecu.readable_params()
        reqs = []
        for p in params:
            if p.get("dato") in DATOS_MEZCLA_F4R and p["request"] not in reqs:
                reqs.append(p["request"])
        return reqs

    def _leer_rpm_obd(self):
        tecu = self.ctx.registro.get("motor") or self.ctx.registro.get("obd")
        if tecu is None:
            return None
        vals = self._leer_request(tecu, "010C")
        if not vals:
            return None
        for info in vals.values():
            try:
                return float(str(info.get("valor")).split()[0])
            except (ValueError, TypeError, IndexError):
                continue
        return None

    def _leer_rpm(self, tecu, rpm_info, objetivo_sim=None):
        if self.ctx.simulacion():
            base = objetivo_sim if objetivo_sim else 850
            t = time.time() - self._t0_sim
            return min(base, 400 + t * 250) if objetivo_sim else 850
        rpm = self._leer_rpm_obd()
        if rpm is not None:
            return rpm
        if rpm_info is not None:
            req, dato, _et = rpm_info
            vals = self._leer_request(tecu, req)
            if vals and dato in vals:
                try:
                    return float(str(vals[dato].get("valor")).split()[0])
                except (ValueError, TypeError, IndexError):
                    pass
        return None

    def _probar_rpm(self, tecu, rpm_info):
        if self.ctx.simulacion():
            return True
        t0 = time.time()
        while time.time() - t0 < PROBE_RPM_SEG:
            if self.ctx.cancelado():
                return False
            if self._leer_rpm(tecu, rpm_info) is not None:
                return True
            time.sleep(0.3)
        return False

    def _motor_tecu(self):
        for cand in ("motor", "obd"):
            t = self.ctx.registro.get(cand)
            if t is not None:
                return t
        lst = self.ctx.registro.list()
        return self.ctx.registro.get(lst[0]["id"]) if lst else None

    def _capturar_motor(self, tecu, reqs, segundos):
        """Igual que chequeo.Chequeo._capturar_motor, pero se autopausa si el usuario
        está en una pantalla "silenciosa" (ej. reaprendizajes) para no competir por el ELM."""
        muestras = []
        t0 = time.time()
        usar_obd_rpm = not self.ctx.simulacion()
        while time.time() - t0 < segundos:
            if self.ctx.cancelado():
                break
            if self.ctx.pausar_lecturas():
                time.sleep(0.3)
                continue
            valores = {}
            for r in reqs:
                v = self._leer_request(tecu, r)
                if v:
                    valores.update(self._valores_legibles(v))
            if usar_obd_rpm:
                rpm = self._leer_rpm_obd()
                if rpm is not None:
                    valores["Régimen del motor (RPM)"] = f"{round(rpm)} RPM"
            if valores:
                muestras.append({"timestamp": round(time.time() - t0, 2), "valores": valores})
            time.sleep(INTERVALO_MS / 1000.0)
        return muestras

    def _resumir_etapa(self, muestras, rpm_info, tecu, alcanzo_banda=True):
        stats = estadisticas_de_muestras(muestras)
        rpm_prom = None
        claves = ["Régimen del motor (RPM)"] + ([rpm_info[2]] if rpm_info else [])
        for clave in claves:
            if clave in stats:
                rpm_prom = stats[clave]["promedio"]
                break
        return {"rpm_prom": rpm_prom, "n_muestras": len(muestras),
                "alcanzo_banda": bool(alcanzo_banda), "estadisticas": stats}

    # ------------------------------------------------------------------ fase
    def _fase_idle_y_2500(self):
        tecu = self._motor_tecu()
        if tecu is None:
            return False
        rpm_info = self._param_rpm(tecu)
        reqs = self._requests_captura(tecu)
        self.ctx.log("MEZCLA", "Chequeo de mezcla: sensores a capturar",
                     {"requests": len(reqs)})

        # --- Etapa 1: ralentí ---
        self._set(fase="ralenti", rpm_objetivo=0, progreso=0,
                  instruccion="Dejá el auto en RALENTÍ. Capturando…")
        muestras = self._capturar_motor(tecu, reqs, RALENTI_SEG)
        self.datos["etapas"]["ralenti"] = self._resumir_etapa(muestras, rpm_info, tecu, True)

        rpm_ok = self._probar_rpm(tecu, rpm_info)
        self.datos["rpm_disponible"] = rpm_ok
        if not rpm_ok:
            self._set(fase="rpm_no_disponible", progreso=100,
                      instruccion="No pude leer las RPM; genero el reporte solo con ralentí.")
            return True

        # --- Etapa 2: ~2500 rpm sostenidas ---
        objetivo = RPM_OBJETIVO_MEZCLA
        self._t0_sim = time.time()
        t_ini = time.time()
        estable_desde = None
        alcanzo = False
        self.ctx.reset_capturar_ahora()
        while True:
            if self.ctx.cancelado():
                return False
            if self.ctx.pausar_lecturas():
                time.sleep(0.3)
                continue
            rpm = self._leer_rpm(tecu, rpm_info, objetivo_sim=objetivo)
            self._set(fase="esperando_2500", rpm_objetivo=objetivo,
                      rpm_actual=round(rpm) if rpm is not None else None,
                      instruccion=f"Llevá el motor a {objetivo} RPM y mantené…")
            en_banda = rpm is not None and abs(rpm - objetivo) <= BANDA_RPM
            if en_banda:
                if estable_desde is None:
                    estable_desde = time.time()
                elif time.time() - estable_desde >= ESTABLE_SEG:
                    alcanzo = True
                    break
            else:
                estable_desde = None
            if self.ctx.capturar_ahora():
                alcanzo = en_banda
                break
            if time.time() - t_ini > TIMEOUT_ETAPA and not self.ctx.simulacion():
                self.ctx.log("MEZCLA", "Etapa 2500 RPM sin banda estable: capturo igual y sigo", {})
                alcanzo = False
                break
            time.sleep(0.3)
        self._set(fase="capturando_2500", rpm_objetivo=objetivo,
                  instruccion=f"Capturando a {objetivo} RPM…")
        muestras = self._capturar_motor(tecu, reqs, CAPTURA_SEG)
        self.datos["etapas"]["2500"] = self._resumir_etapa(muestras, rpm_info, tecu, alcanzo)
        return True

    # ------------------------------------------------------------------ run
    def run(self):
        try:
            if not self._fase_idle_y_2500():
                return {"ok": False, "error": "Chequeo de mezcla cancelado."}
            self._set(fase="reporte", progreso=100, instruccion="Generando el veredicto…")
            import reporte
            rutas = reporte.generar_mezcla(self.datos)
            return {"ok": True, "vehiculo": self.datos["vehiculo"],
                    "etapas": list(self.datos["etapas"].keys()),
                    "reporte": rutas}
        except Exception as e:
            self.ctx.log("MEZCLA", f"Error en el chequeo de mezcla: {e}", {})
            return {"ok": False, "error": f"Error en el chequeo de mezcla: {e}"}
