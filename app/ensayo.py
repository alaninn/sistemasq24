# -*- coding: utf-8 -*-
"""Ensayo de Aceleración — orquestador (máquina de estados en background).

A diferencia del Chequeo General (que mide el auto DETENIDO, subiendo RPM en el lugar),
este módulo mide el motor EN MOVIMIENTO durante un tramo corto de aceleración (~50/100 m).
En un auto quieto muchos valores no son reales (enriquecimiento en carga, respuesta de la
mariposa, avance bajo carga, boost, fuel trims bajo demanda): sólo aparecen acelerando.

Flujo:
  1. espera_arranque: espera a que el auto se empiece a mover (velocidad > umbral) o a que
     el usuario fuerce el inicio. Muestra velocidad/RPM en vivo.
  2. grabando: captura TODOS los sensores clave del motor a alta frecuencia mientras se
     acelera, integrando la velocidad para estimar la distancia recorrida. Termina al
     alcanzar la distancia objetivo, al levantar el pie (desaceleración), por timeout de
     seguridad, o manualmente.
  3. reporte: arma la serie temporal + estadísticas + métricas derivadas del tramo y llama a
     `reporte.generar_ensayo(...)` (HTML/JSON/TXT).

Diseño desacoplado igual que `chequeo.py`: recibe un `ctx` con lo que necesita del server, se
testea en simulación (velocidad en rampa canned).
"""
import time
from datetime import datetime

from chequeo import estadisticas_de_muestras  # reutilizamos la misma lógica de stats

# --- Parámetros del ensayo (constantes ajustables) ---
DISTANCIA_OBJETIVO_DEF = 100.0   # metros a recorrer por defecto (el usuario puede pedir 50)
UMBRAL_ARRANQUE_KMH = 4.0        # velocidad a partir de la cual se considera que arrancó
ESTABLE_ARRANQUE_SEG = 0.4       # cuánto tiene que sostener el movimiento para arrancar
INTERVALO_MS = 200               # entre muestras durante la grabación (alta frecuencia)
TIMEOUT_ARRANQUE = 120           # seg máx esperando que el usuario arranque
TIMEOUT_GRABANDO = 45            # seg máx de grabación (seguridad, por si no llega a la dist.)
DESACEL_FRAC = 0.6               # si la velocidad cae por debajo de pico*frac → levantó el pie
PICO_MIN_FIN = 25.0             # sólo cortar por desaceleración si antes pasó de este pico (km/h)

# Sensores clave del motor que se graban en el tramo (además de RPM y velocidad, que se
# buscan aparte). Bajo carga estos son los que más información dan.
DATOS_ENSAYO_F4R = [
    "Régime moteur", "Vitesse véhicule",
    "Pression collecteur absolue mesurée", "Pression de suralimentation",
    "Avance allumage", "Avance allumage corrigée",
    "Débit air moteur évalué", "Remplissage en air",
    "Position papillon mesurée piste 1 après filtrage", "Position pédale mesurée",
    "Facteur enrichissement regulation richesse",
    "Correction adaptative de la 1ère zone de pression",
    "Tension sonde amont", "Tension sonde aval",
    "Temps injection réel", "Température eau mesurée", "Température air mesurée",
    "Tension batterie mesurée",
    "Valeur max correction lente avance cliquetis",
]
DATOS_ENSAYO_OBD = [
    "Régimen del motor (RPM)", "Velocidad del vehículo",
    "Presión absoluta del colector (MAP)", "Avance de encendido",
    "Caudal de aire (MAF)", "Posición del acelerador",
    "Ajuste de combustible a corto plazo (banco 1)",
    "Ajuste de combustible a largo plazo (banco 1)",
    "Sonda lambda 1 — tensión", "Temperatura del refrigerante",
    "Temperatura del aire de admisión", "Tensión del módulo (batería)",
    "Carga calculada del motor",
]


class Ensayo:
    """Ejecuta el ensayo de aceleración. `ctx` provee la misma interfaz que usa `chequeo.py`:
    registro, seleccionar_ecu(id), elm_lock, marcar_actividad(), set_estado(dict),
    cancelado()->bool, simulacion(bool), log(tipo,msg,det), ahora()->bool (forzar
    arranque/fin), reset_ahora()."""

    def __init__(self, ctx, distancia_objetivo=DISTANCIA_OBJETIVO_DEF):
        self.ctx = ctx
        self.distancia_objetivo = float(distancia_objetivo or DISTANCIA_OBJETIVO_DEF)
        self.datos = {
            "tipo": "ensayo_aceleracion",
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "perfil": ctx.registro.perfil,
            "vehiculo": ctx.registro.vehiculo,
            "distancia_objetivo": self.distancia_objetivo,
            "muestras": [],
            "estadisticas": {},
            "resumen_run": {},
        }
        self._t0_sim = time.time()
        self._t_run0 = None

    # ------------------------------------------------------------------ helpers
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

    def _motor_tecu(self):
        for cand in ("motor", "obd"):
            t = self.ctx.registro.get(cand)
            if t is not None:
                return t
        lst = self.ctx.registro.list()
        return self.ctx.registro.get(lst[0]["id"]) if lst else None

    def _buscar_param(self, tecu, claves):
        """Ubica el (request, dato, etiqueta) del primer param cuyo texto contenga alguna clave."""
        for p in tecu.readable_params():
            texto = (p.get("dato", "") + " " + p.get("etiqueta", "")).lower()
            if any(c in texto for c in claves):
                return p["request"], p["dato"], p["etiqueta"]
        return None

    def _requests_captura(self, tecu):
        """Requests a grabar en el tramo: los de los sensores clave del ensayo (dedup)."""
        clave = DATOS_ENSAYO_OBD if self.datos["perfil"] == "generico" else DATOS_ENSAYO_F4R
        params = tecu.readable_params()
        reqs = []
        for p in params:
            if p.get("dato") in clave and p["request"] not in reqs:
                reqs.append(p["request"])
        if not reqs:  # perfil desconocido: primeros útiles
            for p in params:
                if p.get("util") is not False and p["request"] not in reqs:
                    reqs.append(p["request"])
                if len(reqs) >= 5:
                    break
        return reqs

    def _num(self, valor_str):
        try:
            return float(str(valor_str).split()[0])
        except (ValueError, TypeError, IndexError):
            return None

    # ------------------------------------------------------------------ lectura en vivo
    def _leer_valor(self, valores, dato_info):
        """Devuelve el número de un dato dado (request,dato,etiqueta) desde un dict ya leído."""
        if not dato_info or not valores:
            return None
        _req, dato, _et = dato_info
        v = valores.get(dato)
        return self._num(v.get("valor")) if v else None

    def _muestra(self, tecu, reqs, vel_info, rpm_info):
        """Lee todos los reqs una vez. Devuelve (valores_legibles, vel_kmh, rpm)."""
        if self.ctx.simulacion():
            return self._muestra_sim()
        crudos = {}
        legibles = {}
        for r in reqs:
            v = self._leer_request(tecu, r)
            if v:
                crudos.update(v)
                legibles.update(self._valores_legibles(v))
        vel = self._leer_valor(crudos, vel_info)
        rpm = self._leer_valor(crudos, rpm_info)
        return legibles, vel, rpm

    def _muestra_sim(self):
        """Simulación: rampa de velocidad y RPM correlacionadas para probar todo el flujo."""
        if self._t_run0 is None:
            t = time.time() - self._t0_sim
            vel = 0.0 if t < 1.5 else 6.0     # arranca tras ~1.5s de "espera"
        else:
            t = time.time() - self._t_run0
            vel = min(78.0, 8.0 + t * 13.0)   # acelera hasta ~78 km/h
        rpm = 900 + vel * 45
        valores = {
            "Régimen del motor": f"{round(rpm)} rpm",
            "Velocidad del vehículo": f"{round(vel)} km/h",
            "Presión colector (MAP)": f"{round(30 + vel * 0.9)} kPa",
            "Avance de encendido": f"{round(12 + vel * 0.25, 1)} °",
            "Posición del acelerador": f"{round(min(100, vel * 1.4), 1)} %",
            "Ajuste corto de combustible": f"{round(-2 + (vel % 7), 1)} %",
            "Tensión batería": f"{round(13.9 + (vel % 3) * 0.05, 2)} V",
        }
        return valores, vel, rpm

    def _probar_velocidad(self, tecu, reqs, vel_info, rpm_info):
        """Prueba si la ECU realmente devuelve velocidad (no todas la exponen).
        Devuelve True/False; se informa al frontend para explicar qué esperar."""
        if self.ctx.simulacion():
            return True
        if not vel_info:
            return False
        for _ in range(3):
            _v, vel, _r = self._muestra(tecu, reqs, vel_info, rpm_info)
            if vel is not None:
                return True
        return False

    # ------------------------------------------------------------------ fases
    def _fase_espera(self, tecu, reqs, vel_info, rpm_info):
        """Espera a que el auto arranque (velocidad > umbral sostenida) o inicio forzado.
        Si la ECU no da velocidad, avisa y espera el arranque manual (o sube de RPM)."""
        self.ctx.reset_ahora()
        vel_ok = self.datos.get("vel_disponible", True)
        t_ini = time.time()
        moviendo_desde = None
        rpm_base = None
        while True:
            if self.ctx.cancelado():
                return False
            _val, vel, rpm = self._muestra(tecu, reqs, vel_info, rpm_info)
            if rpm is not None and rpm_base is None and rpm > 0:
                rpm_base = rpm          # ralentí de referencia
            if vel_ok:
                instr = ("Cuando estés listo en un tramo seguro, acelerá. "
                         "La grabación arranca sola al detectar movimiento.")
            else:
                instr = ("Esta ECU no informa la velocidad. Tocá «Arrancar grabación» "
                         "justo antes de acelerar (el tramo se mide por tiempo).")
            self._set(fase="esperando_arranque",
                      vel_actual=round(vel) if vel is not None else None,
                      rpm_actual=round(rpm) if rpm is not None else None,
                      vel_disponible=vel_ok,
                      distancia=0, progreso=0, timeout=not vel_ok,
                      instruccion=instr)
            if self.ctx.ahora():           # inicio manual forzado (botón siempre disponible)
                return True
            if vel_ok and vel is not None and vel >= UMBRAL_ARRANQUE_KMH:
                if moviendo_desde is None:
                    moviendo_desde = time.time()
                elif time.time() - moviendo_desde >= ESTABLE_ARRANQUE_SEG:
                    return True
            else:
                moviendo_desde = None
            # Sin velocidad: arrancar solo si las RPM suben claramente sobre el ralentí
            # (el usuario ya está acelerando). Es una ayuda, no reemplaza el botón.
            if (not vel_ok and rpm is not None and rpm_base
                    and rpm > rpm_base + 800):
                if moviendo_desde is None:
                    moviendo_desde = time.time()
                elif time.time() - moviendo_desde >= ESTABLE_ARRANQUE_SEG:
                    return True
            if time.time() - t_ini > TIMEOUT_ARRANQUE and not self.ctx.simulacion():
                self._set(timeout=True,
                          instruccion="No detecté movimiento. Arrancá la grabación a mano "
                                      "justo antes de acelerar.")
            time.sleep(0.25)

    def _fase_grabando(self, tecu, reqs, vel_info, rpm_info):
        """Graba todos los sensores del motor a alta frecuencia durante el tramo."""
        self.ctx.reset_ahora()
        self._t_run0 = time.time()
        self._t0_sim = self._t_run0
        distancia = 0.0
        pico_vel = 0.0
        t_ultima = time.time()
        muestras = []
        motivo = "distancia"
        while True:
            if self.ctx.cancelado():
                return False
            ahora = time.time()
            dt = ahora - t_ultima
            t_ultima = ahora
            valores, vel, rpm = self._muestra(tecu, reqs, vel_info, rpm_info)
            if vel is not None:
                distancia += (vel / 3.6) * dt          # km/h -> m/s * seg
                pico_vel = max(pico_vel, vel)
            muestras.append({
                "t": round(ahora - self._t_run0, 2),
                "distancia": round(distancia, 1),
                "vel": round(vel, 1) if vel is not None else None,
                "rpm": round(rpm) if rpm is not None else None,
                "valores": valores,
            })
            vel_ok = self.datos.get("vel_disponible", True)
            transcurrido = ahora - self._t_run0
            if vel_ok:
                progreso = min(100, round(distancia / self.distancia_objetivo * 100))
                instr = (f"Grabando… acelerá parejo. "
                         f"{round(distancia)} de {round(self.distancia_objetivo)} m")
            else:
                # sin velocidad no hay distancia: el tramo se mide por tiempo
                progreso = min(100, round(transcurrido / TIMEOUT_GRABANDO * 100))
                instr = (f"Grabando… acelerá parejo. {round(transcurrido, 1)} s "
                         f"(tocá «Terminar tramo» al llegar a los "
                         f"{round(self.distancia_objetivo)} m)")
            self._set(fase="grabando",
                      vel_actual=round(vel) if vel is not None else None,
                      rpm_actual=round(rpm) if rpm is not None else None,
                      distancia=round(distancia, 1), vel_disponible=vel_ok,
                      progreso=progreso, instruccion=instr)
            # --- condiciones de fin ---
            if vel_ok and distancia >= self.distancia_objetivo:
                motivo = "distancia"; break
            if self.ctx.ahora():
                motivo = "manual"; break
            if (vel is not None and pico_vel >= PICO_MIN_FIN
                    and vel < pico_vel * DESACEL_FRAC):
                motivo = "desaceleracion"; break
            if ahora - self._t_run0 > TIMEOUT_GRABANDO:
                motivo = "timeout"; break
            time.sleep(INTERVALO_MS / 1000.0)

        self.datos["muestras"] = muestras
        self.datos["estadisticas"] = estadisticas_de_muestras(muestras)
        self.datos["resumen_run"] = self._resumen_run(muestras, distancia, motivo)
        return True

    # ------------------------------------------------------------------ resumen
    def _resumen_run(self, muestras, distancia, motivo):
        vels = [m["vel"] for m in muestras if m.get("vel") is not None]
        rpms = [m["rpm"] for m in muestras if m.get("rpm") is not None]
        dur = muestras[-1]["t"] if muestras else 0
        res = {
            "distancia_m": round(distancia, 1),
            "duracion_seg": round(dur, 1),
            "n_muestras": len(muestras),
            "motivo_fin": motivo,
            "velocidad_disponible": self.datos.get("vel_disponible", True),
            "vel_max": round(max(vels), 1) if vels else None,
            "vel_final": vels[-1] if vels else None,
            "rpm_max": max(rpms) if rpms else None,
            "rpm_inicial": rpms[0] if rpms else None,
        }
        # tiempos de aceleración a hitos de velocidad (0→X) si se alcanzaron
        hitos = {}
        for objetivo in (40, 60, 80, 100):
            for m in muestras:
                if m.get("vel") is not None and m["vel"] >= objetivo:
                    hitos[f"t_a_{objetivo}kmh"] = m["t"]
                    break
        res["tiempos"] = hitos
        # destacados de sensores bajo carga (máximos, por subcadena de etiqueta)
        stats = self.datos["estadisticas"]
        def _pico(subs):
            for et, s in stats.items():
                if any(x in et.lower() for x in subs):
                    return {"sensor": et, "max": s["maximo"], "min": s["minimo"],
                            "prom": s["promedio"], "unidad": s["unidad"]}
            return None
        res["destacados"] = {k: v for k, v in {
            "boost": _pico(["suralimentation", "boost", "sobrealim"]),
            "map": _pico(["collecteur", "map", "colector"]),
            "avance": _pico(["avance", "encendido"]),
            "mariposa": _pico(["papillon", "acelerador", "mariposa"]),
            "aire": _pico(["débit", "debit", "maf", "caudal", "remplissage", "llenado"]),
            "ajuste_corto": _pico(["enrichissement", "corto", "short"]),
            "sonda": _pico(["sonde amont", "lambda 1", "sonda lambda"]),
            "inyeccion": _pico(["injection", "inyección", "inyeccion"]),
        }.items() if v is not None}
        return res

    # ------------------------------------------------------------------ run
    def run(self):
        try:
            tecu = self._motor_tecu()
            if tecu is None:
                return {"ok": False, "error": "No hay ECU de motor en el perfil activo."}
            self._set(fase="iniciando", instruccion="Preparando el ensayo…")
            vel_info = self._buscar_param(tecu, ["vitesse", "velocidad", "vehicle speed", "speed"])
            rpm_info = self._buscar_param(tecu, ["régime", "regime", "régimen", "rpm"])
            reqs = self._requests_captura(tecu)
            # CRÍTICO: los requests de velocidad y RPM tienen que estar SÍ o SÍ en la captura,
            # si no `vel`/`rpm` salen None y el ensayo nunca detecta el arranque.
            for info in (vel_info, rpm_info):
                if info and info[0] not in reqs:
                    reqs.insert(0, info[0])
            # ¿la velocidad se lee de verdad? (algunas ECU de motor no la exponen)
            self.datos["vel_disponible"] = self._probar_velocidad(tecu, reqs, vel_info, rpm_info)
            if not self._fase_espera(tecu, reqs, vel_info, rpm_info):
                return {"ok": False, "error": "Ensayo cancelado antes de arrancar."}
            if not self._fase_grabando(tecu, reqs, vel_info, rpm_info):
                return {"ok": False, "error": "Ensayo cancelado durante la grabación."}
            self._set(fase="reporte", progreso=100, instruccion="Generando el informe…")
            import reporte
            rutas = reporte.generar_ensayo(self.datos)
            r = self.datos["resumen_run"]
            return {"ok": True, "vehiculo": self.datos["vehiculo"],
                    "distancia": r.get("distancia_m"), "duracion": r.get("duracion_seg"),
                    "vel_max": r.get("vel_max"), "rpm_max": r.get("rpm_max"),
                    "n_muestras": r.get("n_muestras"), "reporte": rutas}
        except Exception as e:
            self.ctx.log("ENSAYO", f"Error en el ensayo: {e}", {})
            return {"ok": False, "error": f"Error en el ensayo: {e}"}
