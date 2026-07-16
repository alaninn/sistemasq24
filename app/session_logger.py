# -*- coding: utf-8 -*-
"""Grabador de sesión de diagnóstico.

Cuando está activo, registra TODO lo que pasa durante un chequeo:
- info del equipo (SO, Python, adaptador, puerto)
- cada conexión / desconexión
- cada comando crudo enviado al ELM327 y su respuesta
- cada evento de alto nivel (leer DTC, entrar a una ECU, actuadores, memoria, service…)

Al detener, guarda dos archivos en `megane2_f4r/log/`:
- `sesion_<fecha>.txt`  → legible, para leer/pegar
- `sesion_<fecha>.json` → estructurado, para analizar

Pensado para: escanear con la notebook en el auto, traer el archivo y pegarlo acá.
"""
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "log"


class SessionLogger:
    def __init__(self):
        self.activo = False
        self.eventos = []
        self.inicio = None
        self.nombre = None

    # ---- control ----
    def start(self, contexto=None):
        self.activo = True
        self.eventos = []
        self.inicio = time.time()
        self.nombre = "sesion_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log("SESION", "Inicio de grabación", contexto or {})
        self.log("EQUIPO", "Información del equipo", self._info_equipo())
        return {"activo": True, "nombre": self.nombre}

    def stop(self):
        if not self.activo:
            return {"activo": False, "guardado": False}
        self.log("SESION", "Fin de grabación", {"eventos": len(self.eventos)})
        rutas = self._guardar()
        self.activo = False
        return {"activo": False, "guardado": True, "nombre": self.nombre, **rutas}

    def estado(self):
        return {
            "activo": self.activo,
            "nombre": self.nombre,
            "eventos": len(self.eventos),
            "segundos": round(time.time() - self.inicio, 1) if self.inicio and self.activo else 0,
        }

    # ---- registro ----
    def log(self, tipo, mensaje, detalle=None):
        if not self.activo:
            return
        t = time.time()
        rel = round(t - self.inicio, 2) if self.inicio else 0
        self.eventos.append({
            "t": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "seg": rel,
            "tipo": tipo,
            "mensaje": mensaje,
            "detalle": detalle if detalle is not None else {},
        })

    def log_elm(self, comando, respuesta, contexto=""):
        """Registra un comando crudo ELM y su respuesta."""
        if not self.activo:
            return
        self.log("ELM", contexto or "comando", {"envio": comando, "respuesta": respuesta})

    def log_raw(self, comando, respuesta, ms=None):
        """Registra un comando de bajo nivel al adaptador (AT, sesión, framing) con su tiempo."""
        if not self.activo:
            return
        det = {"envio": comando, "respuesta": respuesta}
        if ms is not None:
            det["ms"] = ms
        # clasificar para lectura fácil
        c = str(comando).strip().upper()
        if c.startswith("AT"):
            etiqueta = "config"
        elif c.replace(" ", "").startswith("10"):
            etiqueta = "sesión"
        elif c.replace(" ", "").startswith("3E"):
            etiqueta = "keep-alive"
        else:
            etiqueta = "diag"
        self.log("ELM", etiqueta, det)

    def log_sensores(self, ecu, valores):
        """Registra un snapshot legible de sensores leídos en vivo (valor + unidad)."""
        if not self.activo:
            return
        resumen = {}
        for etiqueta, info in valores.items():
            v = info.get("valor")
            if v is None or str(v).strip() == "":
                continue
            u = info.get("unidad", "")
            resumen[etiqueta] = f"{v} {u}".strip()
        if resumen:
            self.log("SENSORES", f"Lectura en vivo ({ecu})", resumen)

    def log_lectura(self, ecu, request_name, valores):
        """Registra una lectura completa de un request (para ver exactamente qué volvió)."""
        if not self.activo:
            return
        det = {"ecu": ecu, "request": request_name, "datos": valores or {}}
        self.log("LECTURA", f"{ecu} → {request_name}", det)

    def log_actuador(self, ecu, actuador, valores_enviados, exito):
        """Registra un intento de activar un actuador."""
        if not self.activo:
            return
        det = {
            "ecu": ecu,
            "actuador": actuador,
            "valores": valores_enviados,
            "exito": exito
        }
        self.log("ACTUADOR", f"{ecu} → {actuador}", det)

    def log_pantalla(self, accion, ecu, nombre_pantalla, contenido=None):
        """Registra cuando se abre/cierra una pantalla de ECU o se refresca."""
        if not self.activo:
            return
        det = {"ecu": ecu, "pantalla": nombre_pantalla}
        if contenido:
            det["contenido"] = contenido
        self.log("PANTALLA", accion, det)

    def log_dtc(self, ecu, codigos):
        """Registra DTCs leídos de una ECU."""
        if not self.activo:
            return
        det = {"ecu": ecu, "codigos": codigos or []}
        self.log("DTC", f"Lectura de DTCs ({ecu})", det)

    def log_series_temporal(self, ecu, request_name, muestras):
        """Registra una serie temporal de muestras (para ver evolución: ralenti→acelerado→ralenti).

        muestras: lista de dicts con formato:
            [
                {"timestamp": 0.0, "valores": {"RPM": "0", "Temp": "80 °C"}},
                {"timestamp": 0.5, "valores": {"RPM": "3500", "Temp": "82 °C"}},
                ...
            ]
        """
        if not self.activo or not muestras:
            return
        det = {
            "ecu": ecu,
            "request": request_name,
            "cantidad": len(muestras),
            "muestras": muestras
        }
        self.log("SERIE_TEMPORAL", f"{ecu} → {request_name} ({len(muestras)} muestras)", det)

    def log_captura_pantalla(self, ecu, nombre_pantalla, muestras, duracion_s):
        """Registra captura automática de una pantalla (múltiples muestras + estadísticas).

        Se ejecuta automáticamente al abrir una pantalla. Captura N muestras durante duracion_s,
        calcula min/max/promedio, y detecta anomalías.

        muestras: [{"timestamp": t, "valores": {...}}, ...]
        """
        if not self.activo or not muestras:
            return

        # Calcular estadísticas por sensor
        stats = {}
        for muestra in muestras:
            for sensor, valor_str in muestra.get("valores", {}).items():
                if sensor not in stats:
                    stats[sensor] = {"valores": [], "unidad": ""}

                # Extraer número y unidad
                partes = str(valor_str).split()
                try:
                    num = float(partes[0])
                    stats[sensor]["valores"].append(num)
                    if len(partes) > 1:
                        stats[sensor]["unidad"] = " ".join(partes[1:])
                except (ValueError, IndexError):
                    pass

        # Resumir estadísticas
        resumen_stats = {}
        anomalias = []
        for sensor, data in stats.items():
            vals = data["valores"]
            if not vals:
                continue
            promedio = sum(vals) / len(vals)
            minimo = min(vals)
            maximo = max(vals)
            unidad = data["unidad"]

            # Desviación estándar (para detectar fluctuaciones)
            varianza = sum((x - promedio) ** 2 for x in vals) / len(vals) if len(vals) > 1 else 0
            desv_std = varianza ** 0.5

            resumen_stats[sensor] = {
                "promedio": round(promedio, 2),
                "minimo": round(minimo, 2),
                "maximo": round(maximo, 2),
                "desv_std": round(desv_std, 2),
                "unidad": unidad,
                "muestras": len(vals)
            }

            # Detectar anomalías: cambios bruscos > 1.5 desv_std
            if len(vals) > 1 and desv_std > 0:
                for i in range(1, len(vals)):
                    cambio = abs(vals[i] - vals[i-1])
                    if cambio > desv_std * 1.5:
                        anomalias.append({
                            "sensor": sensor,
                            "de": round(vals[i-1], 2),
                            "a": round(vals[i], 2),
                            "cambio": round(cambio, 2),
                            "unidad": unidad
                        })

        det = {
            "ecu": ecu,
            "pantalla": nombre_pantalla,
            "duracion_s": duracion_s,
            "cantidad_muestras": len(muestras),
            "estadisticas": resumen_stats,
            "anomalias": anomalias,
            "muestras": muestras  # guardar también las muestras crudas en JSON
        }
        self.log("CAPTURA_PANTALLA", f"{ecu} → {nombre_pantalla} ({len(muestras)} muestras en {duracion_s}s)", det)

    # ---- interno ----
    def _info_equipo(self):
        return {
            "sistema": platform.system() + " " + platform.release(),
            "version": platform.version(),
            "maquina": platform.machine(),
            "python": sys.version.split()[0],
            "nodo": platform.node(),
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _guardar(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        txt_path = LOG_DIR / f"{self.nombre}.txt"
        json_path = LOG_DIR / f"{self.nombre}.json"

        # JSON estructurado
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"nombre": self.nombre, "eventos": self.eventos}, f, ensure_ascii=False, indent=1)

        # TXT legible
        lineas = []
        lineas.append("=" * 66)
        lineas.append("  GRABACIÓN DE SESIÓN — SISTEMASQ24")
        lineas.append(f"  {self.nombre}")
        lineas.append("=" * 66)
        lineas.append("")
        for ev in self.eventos:
            cab = f"[{ev['t']}] (+{ev['seg']:>6}s) {ev['tipo']:<8} {ev['mensaje']}"
            lineas.append(cab)
            det = ev.get("detalle") or {}
            if det:
                if ev["tipo"] == "ELM":
                    # Comando bajo nivel: mostrar con tiempo
                    ms = det.get("ms")
                    tstr = f"  ({ms} ms)" if ms is not None else ""
                    lineas.append(f"           → envío:     {det.get('envio','')}{tstr}")
                    lineas.append(f"           → respuesta: {det.get('respuesta','')}")
                elif ev["tipo"] == "CAPTURA_PANTALLA":
                    # Captura automática de pantalla con estadísticas
                    lineas.append(f"           ECU: {det.get('ecu', '?')}")
                    lineas.append(f"           Pantalla: {det.get('pantalla', '?')}")
                    lineas.append(f"           Duración: {det.get('duracion_s', '?')}s | Muestras: {det.get('cantidad_muestras', '?')}")
                    lineas.append("")

                    # Tabla de estadísticas
                    stats = det.get("estadisticas", {})
                    if stats:
                        lineas.append("           ESTADÍSTICAS POR SENSOR:")
                        lineas.append("           ┌─ Sensor ──────────┬──────────┬──────────┬──────────┬──────────┐")
                        lineas.append("           │ Nombre            │ Promedio │ Mínimo   │ Máximo   │ Desv.Est │")
                        lineas.append("           ├───────────────────┼──────────┼──────────┼──────────┼──────────┤")
                        for sensor, s_data in sorted(stats.items()):
                            nom = f"{sensor[:15]:<15}"
                            prom = f"{s_data.get('promedio', '?'):<8}"
                            mini = f"{s_data.get('minimo', '?'):<8}"
                            maxi = f"{s_data.get('maximo', '?'):<8}"
                            desvest = f"{s_data.get('desv_std', '?'):<8}"
                            lineas.append(f"           │ {nom} │ {prom} │ {mini} │ {maxi} │ {desvest} │")
                        lineas.append("           └───────────────────┴──────────┴──────────┴──────────┴──────────┘")

                    # Anomalías detectadas
                    anomalias = det.get("anomalias", [])
                    if anomalias:
                        lineas.append("")
                        lineas.append("           ANOMALÍAS DETECTADAS (cambios bruscos):")
                        for anom in anomalias:
                            lineas.append(f"           ⚠ {anom['sensor']}: {anom['de']} → {anom['a']} {anom['unidad']} (Δ {anom['cambio']})")
                    else:
                        lineas.append("")
                        lineas.append("           Sin anomalías detectadas.")
                    lineas.append("")

                elif ev["tipo"] == "SERIE_TEMPORAL":
                    # Muestras múltiples (evolución de sensores): mostrar como tabla
                    lineas.append(f"           ECU: {det.get('ecu', '?')}")
                    lineas.append(f"           Request: {det.get('request', '?')}")
                    lineas.append(f"           Muestras: {det.get('cantidad', '?')}")
                    lineas.append("")
                    muestras = det.get("muestras", [])
                    if muestras:
                        # Encabezado de tabla
                        header = "           │ T(s)  │"
                        sensores_cols = set()
                        for m in muestras:
                            sensores_cols.update(m.get("valores", {}).keys())
                        sensores_cols = sorted(sensores_cols)
                        for sensor in sensores_cols:
                            header += f" {sensor[:12]:<12} │"
                        lineas.append(header)
                        lineas.append("           ├" + "───────┼" * (len(sensores_cols) + 1) + "─")
                        # Datos
                        for muestra in muestras:
                            fila = f"           │ {muestra.get('timestamp', 0):<5.1f} │"
                            valores = muestra.get("valores", {})
                            for sensor in sensores_cols:
                                val = valores.get(sensor, "—")
                                fila += f" {str(val)[:12]:<12} │"
                            lineas.append(fila)
                    lineas.append("")
                elif ev["tipo"] in ("LECTURA", "ACTUADOR", "DTC"):
                    # Eventos de alto nivel: mostrar con más detalle
                    for k, v in det.items():
                        if isinstance(v, (dict, list)):
                            vs = json.dumps(v, ensure_ascii=False, indent=1)
                            for ln in vs.split("\n"):
                                lineas.append(f"           {ln}")
                        else:
                            lineas.append(f"           · {k}: {v}")
                elif ev["tipo"] == "PANTALLA":
                    # Eventos de navegación
                    lineas.append(f"           ├─ ecu: {det.get('ecu', '?')}")
                    lineas.append(f"           ├─ pantalla: {det.get('pantalla', '?')}")
                    if det.get('contenido'):
                        lineas.append(f"           └─ (contiene {len(det['contenido'])} elementos)")
                else:
                    # Resto de eventos
                    for k, v in det.items():
                        vs = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
                        if len(vs) > 400:
                            vs = vs[:400] + "…"
                        lineas.append(f"           · {k}: {vs}")
            lineas.append("")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas))

        return {"txt": str(txt_path), "json": str(json_path), "carpeta": str(LOG_DIR)}


# instancia global
logger = SessionLogger()
