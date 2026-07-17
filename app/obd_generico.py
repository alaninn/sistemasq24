# -*- coding: utf-8 -*-
"""Scanner OBD-II GENÉRICO — funciona en CUALQUIER auto, sin base de ECUs.

Usa el estándar universal SAE J1979 / ISO 15031 (el mismo que ScanMaster, Torque, etc.):
- Modo 01: sensores en vivo estándar (RPM, temps, MAP, MAF, sonda lambda, velocidad…).
- Modo 03/07/0A: códigos de falla (DTC) genéricos. Modo 04: borrarlos. Modo 09: VIN.

Dirección funcional de broadcast 7DF (responden 7E8-7EF). No necesita el ecu.zip.

`ObdGenerico` imita la interfaz de `TranslatedECU` (info, readable_params, read_request,
read_dtcs, clear_dtcs, param_id, is_dangerous, ensure_session, actuators) para que el
tablero en vivo, el analizador de ondas y la lectura de DTC ya existentes funcionen sin
cambios.
"""
import sistemasq24.options as options


def _u16(d, i=0):
    return (d[i] << 8) | d[i + 1]


# Tabla de PIDs estándar del Modo 01. Cada entrada:
#   pid_hex -> (nombre_es, unidad, nbytes, formula(bytes)->valor)
# Fórmulas de la norma SAE J1979 (universales; no dependen del auto).
PIDS = {
    "04": ("Carga calculada del motor", "%",     1, lambda d: round(d[0] * 100 / 255, 1)),
    "05": ("Temperatura del refrigerante", "°C", 1, lambda d: d[0] - 40),
    "06": ("Ajuste corto de combustible B1", "%", 1, lambda d: round(d[0] * 100 / 128 - 100, 1)),
    "07": ("Ajuste largo de combustible B1", "%", 1, lambda d: round(d[0] * 100 / 128 - 100, 1)),
    "08": ("Ajuste corto de combustible B2", "%", 1, lambda d: round(d[0] * 100 / 128 - 100, 1)),
    "09": ("Ajuste largo de combustible B2", "%", 1, lambda d: round(d[0] * 100 / 128 - 100, 1)),
    "0A": ("Presión de combustible", "kPa",  1, lambda d: d[0] * 3),
    "0B": ("Presión absoluta del colector (MAP)", "kPa", 1, lambda d: d[0]),
    "0C": ("Régimen del motor (RPM)", "RPM",  2, lambda d: round(_u16(d) / 4)),
    "0D": ("Velocidad del vehículo", "km/h",  1, lambda d: d[0]),
    "0E": ("Avance de encendido", "°",        1, lambda d: round(d[0] / 2 - 64, 1)),
    "0F": ("Temperatura del aire de admisión", "°C", 1, lambda d: d[0] - 40),
    "10": ("Caudal de aire (MAF)", "g/s",     2, lambda d: round(_u16(d) / 100, 2)),
    "11": ("Posición del acelerador", "%",    1, lambda d: round(d[0] * 100 / 255, 1)),
    "14": ("Sonda lambda 1 — tensión", "V",   2, lambda d: round(d[0] / 200, 3)),
    "15": ("Sonda lambda 2 — tensión", "V",   2, lambda d: round(d[0] / 200, 3)),
    "1F": ("Tiempo de marcha desde arranque", "s", 2, lambda d: _u16(d)),
    "21": ("Distancia con testigo MIL", "km", 2, lambda d: _u16(d)),
    "23": ("Presión de riel de combustible", "kPa", 2, lambda d: _u16(d) * 10),
    "2C": ("Comando EGR", "%",                1, lambda d: round(d[0] * 100 / 255, 1)),
    "2F": ("Nivel de combustible", "%",       1, lambda d: round(d[0] * 100 / 255, 1)),
    "31": ("Distancia desde borrado de DTC", "km", 2, lambda d: _u16(d)),
    "33": ("Presión barométrica", "kPa",      1, lambda d: d[0]),
    "42": ("Tensión del módulo (batería)", "V", 2, lambda d: round(_u16(d) / 1000, 2)),
    "43": ("Carga absoluta del motor", "%",   2, lambda d: round(_u16(d) * 100 / 255, 1)),
    "44": ("Relación lambda comandada", "λ",  2, lambda d: round(_u16(d) / 32768, 3)),
    "45": ("Posición relativa del acelerador", "%", 1, lambda d: round(d[0] * 100 / 255, 1)),
    "46": ("Temperatura ambiente", "°C",      1, lambda d: d[0] - 40),
    "47": ("Posición absoluta acelerador B", "%", 1, lambda d: round(d[0] * 100 / 255, 1)),
    "49": ("Posición del pedal D", "%",       1, lambda d: round(d[0] * 100 / 255, 1)),
    "4C": ("Acelerador comandado", "%",       1, lambda d: round(d[0] * 100 / 255, 1)),
    "5C": ("Temperatura del aceite del motor", "°C", 1, lambda d: d[0] - 40),
    "5E": ("Consumo de combustible", "L/h",   2, lambda d: round(_u16(d) / 20, 2)),
}

# PIDs que se muestran POR DEFECTO en el tablero (los clásicos oscilantes).
PRECARGADOS = ["0C", "05", "0F", "0B", "10", "0D", "11", "0E", "42", "14", "04", "2F"]

# Códigos de respuesta negativa (para mensajes claros)
from ecu_registry import dtc_estandar, NRC  # reutilizamos el decodificador de DTC


class _FakeEcu:
    """Objeto mínimo que imita `EcuFile` para el direccionamiento del server."""
    def __init__(self):
        self.ecu_send_id = "7DF"      # dirección funcional de broadcast OBD-II
        self.ecu_recv_id = "7E8"
        self.ecu_protocol = "CAN"
        self.ecuname = "OBD-II Genérico"
        self.funcname = "OBD-II"
        self.data = {}
        self.requests = {}
    def get_request(self, name):
        return None


class ObdGenerico:
    """ECU virtual que habla OBD-II estándar. Compatible con la interfaz de TranslatedECU."""
    id = "obd"
    icon = "🌐"
    short_name = "Motor (OBD-II Genérico)"

    def __init__(self):
        self.ecu = _FakeEcu()
        self.soportados = set()       # PIDs soportados por el auto (se llena al escanear)
        self._probado = False

    # ---- traducción (no hace falta, ya están en español) ----
    def t(self, s):
        return s if s is not None else ""

    def help_for(self, data_name):
        return ""

    # ---- direccionamiento OBD ----
    def _pids_disponibles(self):
        """PIDs a exponer: los soportados por el auto, o todos si aún no se probó."""
        if self.soportados:
            return [p for p in PIDS if p in self.soportados]
        return list(PIDS.keys())

    # ---- metadata (imita info()) ----
    def info(self):
        pids = self._pids_disponibles()
        return {
            "id": self.id, "icon": self.icon, "nombre": self.short_name,
            "ecuname": "OBD-II Genérico", "funcion": "Estándar SAE J1979",
            "protocolo": "CAN", "tx": "7DF", "rx": "7E8",
            "pantallas": 0, "parametros": len(pids),
        }

    def categories(self):
        return []

    def screen(self, screen_name):
        return None

    def param_id(self, request_name, data_name):
        return f"{self.id}|{request_name}|{data_name}"

    # ---- sensores legibles (imita readable_params) ----
    def readable_params(self):
        out = []
        for pid in self._pids_disponibles():
            nombre, unidad, _n, _f = PIDS[pid]
            req = "01" + pid
            out.append({
                "id": self.param_id(req, nombre),
                "dato": nombre, "etiqueta": nombre, "unidad": unidad,
                "ayuda": "", "request": req, "util": True,
            })
        out.sort(key=lambda p: p["etiqueta"].lower())
        return out

    # ---- lectura de un PID (imita read_request) ----
    def read_request(self, request_name, inputs=None):
        """request_name = '01'+PID (ej '010C'). Devuelve {nombre: {etiqueta,valor,unidad}}."""
        rn = request_name.replace(" ", "").upper()
        if not rn.startswith("01") or len(rn) < 4:
            return None
        pid = rn[2:4]
        info = PIDS.get(pid)
        if info is None:
            return None
        nombre, unidad, nbytes, formula = info
        resp = self._enviar(rn)
        if resp is None:
            return None
        datos = self._parse_modo01(resp, pid, nbytes)
        if datos is None:
            return {nombre: {"etiqueta": nombre, "valor": None, "unidad": unidad}}
        try:
            valor = formula(datos)
        except Exception:
            valor = None
        return {nombre: {"etiqueta": nombre, "valor": valor, "unidad": unidad}}

    def _parse_modo01(self, resp, pid, nbytes):
        """Extrae los bytes de datos de una respuesta '41 <pid> <datos...>'."""
        partes = resp.strip().split()
        # buscar el eco 41 <pid>
        for i in range(len(partes) - 1):
            if partes[i].upper() == "41" and partes[i + 1].upper() == pid.upper():
                try:
                    return [int(b, 16) for b in partes[i + 2:i + 2 + nbytes]]
                except ValueError:
                    return None
        return None

    def _enviar(self, cmd):
        if options.simulation_mode:
            return _SIM.get(cmd)
        if options.elm is None:
            return None
        try:
            resp = options.elm.request(cmd, cache=False)
        except Exception:
            return None
        if resp is None or "WRONG" in resp or "NO DATA" in resp.upper():
            return None
        return resp

    # ---- escaneo de PIDs soportados ----
    def escanear_soportados(self):
        """Consulta qué PIDs soporta el auto (PID 00/20/40 = bitmask)."""
        self.soportados = set()
        for base_cmd, base in [("0100", 0x00), ("0120", 0x20), ("0140", 0x40)]:
            resp = self._enviar(base_cmd)
            if not resp:
                continue
            partes = resp.strip().split()
            # respuesta: 41 00 AA BB CC DD  (bitmask de 32 PIDs)
            for i in range(len(partes) - 1):
                if partes[i].upper() == "41" and partes[i + 1].upper() == f"{base:02X}":
                    try:
                        mask = [int(b, 16) for b in partes[i + 2:i + 6]]
                    except ValueError:
                        break
                    bits = 0
                    for b in mask:
                        bits = (bits << 8) | b
                    for k in range(32):
                        if bits & (1 << (31 - k)):
                            pid_num = base + k + 1
                            self.soportados.add(f"{pid_num:02X}")
                    break
        self._probado = True
        return self.soportados

    # ---- DTC (imita read_dtcs / clear_dtcs) ----
    def read_dtcs(self):
        """Lee DTC almacenados (modo 03) y pendientes (modo 07)."""
        dtcs = []
        for modo, tipo in [("03", "almacenado"), ("07", "pendiente")]:
            resp = self._enviar_dtc(modo)
            for cod in self._parse_dtcs(resp, modo):
                dtcs.append({
                    "codigo": cod, "codigo_raw": None,
                    "descripcion": "Código genérico OBD-II",
                    "detalle": None,
                    "presente": tipo == "almacenado",
                    "memorizada": tipo == "pendiente",
                    "campos": {"tipo": tipo},
                })
        return {"soportado": True, "cantidad": len(dtcs), "dtcs": dtcs}

    def _enviar_dtc(self, modo):
        if options.simulation_mode:
            return _SIM.get(modo)
        if options.elm is None:
            return None
        try:
            return options.elm.request(modo, cache=False)
        except Exception:
            return None

    def _parse_dtcs(self, resp, modo):
        if not resp:
            return []
        partes = resp.strip().split()
        eco = {"03": "43", "07": "47", "0A": "4A"}.get(modo, "43")
        # ubicar el eco y tomar los bytes que siguen en pares
        idx = None
        for i, b in enumerate(partes):
            if b.upper() == eco:
                idx = i + 1
                break
        if idx is None:
            return []
        cuerpo = partes[idx:]
        # algunos ECU meten un byte de cantidad; si es impar, lo salteamos
        if len(cuerpo) % 2 == 1:
            cuerpo = cuerpo[1:]
        out = []
        for i in range(0, len(cuerpo) - 1, 2):
            raw = (cuerpo[i] + cuerpo[i + 1]).upper()
            if raw in ("0000", ""):
                continue
            cod = dtc_estandar(raw)
            if cod:
                out.append(cod)
        return out

    def clear_dtcs(self):
        """Borra los DTC (modo 04)."""
        if options.simulation_mode:
            return {"ok": True, "simulado": True}
        if options.elm is None:
            return {"ok": False, "error": "Sin conexión"}
        try:
            resp = options.elm.request("04", cache=False)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if resp and "44" in resp.upper():
            return {"ok": True}
        return {"ok": True, "respuesta": resp}

    # ---- VIN (modo 09 PID 02) ----
    def leer_vin(self):
        resp = self._enviar("0902")
        if not resp:
            return None
        partes = [p for p in resp.strip().split() if len(p) == 2]
        try:
            # saltar eco 49 02 y byte de conteo; tomar ASCII
            chars = []
            for b in partes:
                v = int(b, 16)
                if 32 <= v < 127:
                    chars.append(chr(v))
            txt = "".join(chars)
            # el VIN son 17 caracteres alfanuméricos al final
            import re
            m = re.search(r"[A-HJ-NPR-Z0-9]{17}", txt.upper())
            return m.group(0) if m else (txt[-17:] if len(txt) >= 17 else None)
        except Exception:
            return None

    # ---- compatibilidad con la interfaz (no aplican al OBD genérico) ----
    def is_dangerous(self, request_name):
        return False

    def is_read_request_name(self, request_name):
        return True

    def ensure_session(self, force=False):
        return True

    def actuators(self):
        return {"soportado": False, "actuadores": []}

    def scan_identidad(self):
        vin = self.leer_vin() if not options.simulation_mode else "SIMVIN0000000000"
        return {"presente": True, "identificacion": {"VIN": vin} if vin else {}}


# Respuestas de simulación para probar sin auto.
_SIM = {
    "0100": "41 00 BE 3E B8 11",
    "0120": "41 20 80 00 00 01",
    "0140": "41 40 40 00 00 00",
    "010C": "41 0C 1A F8",       # ~1758 RPM
    "0105": "41 05 5A",          # 50 °C
    "010F": "41 0F 46",          # 30 °C
    "010B": "41 0B 60",          # 96 kPa
    "0110": "41 10 05 DC",       # 15.0 g/s
    "010D": "41 0D 00",          # 0 km/h
    "0111": "41 11 20",          # ~12.5 %
    "010E": "41 0E 80",          # 0°
    "0142": "41 42 39 D0",       # ~14.8 V
    "0114": "41 14 90 80",       # 0.72 V
    "0104": "41 04 40",          # ~25 %
    "012F": "41 2F 80",          # ~50 %
    "03": "43 01 33 00 00",      # DTC P0133
    "07": "47 00 00",
}


_instancia = None

def get_obd():
    global _instancia
    if _instancia is None:
        _instancia = ObdGenerico()
    return _instancia
