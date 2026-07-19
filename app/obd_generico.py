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
from dtc_db import describir as describir_dtc  # descripciones en español de los DTC


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
                    "descripcion": describir_dtc(cod),
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

    def decodificar_vin(self, vin=None):
        """Decodifica el VIN offline: país/región, fabricante (WMI) y año de modelo.
        No necesita internet; usa tablas estándar ISO 3779/3780."""
        if vin is None:
            vin = self.leer_vin() if not options.simulation_mode else "VF1BB000000000000"
        return decodificar_vin(vin)

    # ---- Freeze Frame (Modo 02): foto de los sensores cuando saltó el DTC ----
    def leer_freeze_frame(self):
        """Lee el freeze frame (cuadro congelado): el DTC que lo disparó + los sensores
        clave en el instante de la falla. Frame 00 (el más reciente)."""
        # 1) DTC que originó el freeze frame (Modo 02 PID 02)
        dtc = None
        resp = self._enviar("020200")
        if resp:
            partes = [p for p in resp.strip().split() if len(p) == 2]
            for i in range(len(partes) - 1):
                if partes[i].upper() == "42" and partes[i + 1].upper() == "02":
                    raw = (partes[i + 3] + partes[i + 4]).upper() if len(partes) > i + 4 else ""
                    if raw and raw != "0000":
                        dtc = dtc_estandar(raw)
                    break
        # 2) sensores clave en el momento de la falla (mismas fórmulas, eco '42')
        pids_ff = ["04", "05", "06", "07", "0B", "0C", "0D", "0E", "0F", "10", "11", "2F", "42"]
        sensores = []
        for pid in pids_ff:
            info = PIDS.get(pid)
            if info is None:
                continue
            nombre, unidad, nbytes, formula = info
            r = self._enviar("02" + pid + "00")
            if not r:
                continue
            datos = self._parse_freeze(r, pid, nbytes)
            if datos is None:
                continue
            try:
                valor = formula(datos)
            except Exception:
                valor = None
            if valor is not None:
                sensores.append({"dato": nombre, "valor": valor, "unidad": unidad})
        disponible = dtc is not None or bool(sensores)
        return {
            "disponible": disponible,
            "dtc": dtc,
            "dtc_descripcion": describir_dtc(dtc) if dtc else None,
            "sensores": sensores,
        }

    def _parse_freeze(self, resp, pid, nbytes):
        """Extrae los bytes de una respuesta Modo 02 '42 <pid> <frame> <datos...>'."""
        partes = resp.strip().split()
        for i in range(len(partes) - 2):
            if partes[i].upper() == "42" and partes[i + 1].upper() == pid.upper():
                try:
                    # tras 42 <pid> <frame(00)> vienen los datos
                    return [int(b, 16) for b in partes[i + 3:i + 3 + nbytes]]
                except ValueError:
                    return None
        return None

    # ---- Readiness / monitores (Modo 01 PID 01) ----
    def leer_readiness(self):
        """Estado de los monitores de emisiones (I/M readiness) y del testigo MIL."""
        resp = self._enviar("0101")
        if not resp:
            return {"disponible": False}
        partes = resp.strip().split()
        idx = None
        for i in range(len(partes) - 1):
            if partes[i].upper() == "41" and partes[i + 1].upper() == "01":
                idx = i + 2
                break
        if idx is None or len(partes) < idx + 4:
            return {"disponible": False}
        try:
            A, B, C, D = [int(partes[idx + k], 16) for k in range(4)]
        except ValueError:
            return {"disponible": False}
        mil = bool(A & 0x80)
        n_dtc = A & 0x7F
        # monitores continuos (byte B, bits bajos = soportado, altos = incompleto)
        continuos = [
            ("Fallo de encendido (misfire)", B & 0x01, B & 0x10),
            ("Sistema de combustible", B & 0x02, B & 0x20),
            ("Componentes (comprehensive)", B & 0x04, B & 0x40),
        ]
        # monitores no continuos (C = soportado, D = incompleto), orden estándar gasolina
        nombres_nc = ["Catalizador", "Catalizador calefaccionado", "Sistema evaporativo (EVAP)",
                      "Aire secundario", "A/C (refrigerante)", "Sonda lambda (O2)",
                      "Calefactor de sonda lambda", "EGR / VVT"]
        no_continuos = []
        for k, nombre in enumerate(nombres_nc):
            sop = C & (1 << k)
            inc = D & (1 << k)
            no_continuos.append({"nombre": nombre, "soportado": bool(sop), "listo": bool(sop and not inc)})
        def _fmt(lst):
            return [{"nombre": n, "soportado": bool(s), "listo": bool(s and not i)} for n, s, i in lst]
        return {
            "disponible": True, "mil_encendido": mil, "dtc_count": n_dtc,
            "continuos": _fmt(continuos),
            "no_continuos": [m for m in no_continuos if m["soportado"]],
        }

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


# --------------------------------------------------------------------------
# Decodificador de VIN offline (ISO 3779/3780) — sin internet, sin base externa
# --------------------------------------------------------------------------
# Región/país por el 1er carácter (WMI[0]).
_VIN_REGION = {
    tuple("ABCDEFGH"): "África", tuple("JKLMNPR"): "Asia",
    tuple("STUVWXYZ"): "Europa", tuple("123456789"): "América del Norte",
    tuple("0"): "Oceanía",
}
# Fabricante por los primeros 2-3 caracteres (WMI). Foco en la Alianza + comunes.
_VIN_WMI = {
    "VF1": "Renault", "VF2": "Renault (utilitarios)", "VF3": "Peugeot", "VF7": "Citroën",
    "VNV": "Renault/Nissan", "93Y": "Renault (Brasil)", "8A1": "Renault (Argentina)",
    "93U": "Renault (Brasil)", "UU1": "Dacia", "UU2": "Dacia", "VSY": "Dacia (Ford Iberia)",
    "VNE": "Nissan (España)", "VWA": "Volkswagen", "WVW": "Volkswagen", "WV1": "VW (comercial)",
    "1N4": "Nissan (EE.UU.)", "JN1": "Nissan (Japón)", "JN6": "Nissan (Japón)",
    "SJN": "Nissan (Reino Unido)", "3N1": "Nissan (México)", "MDH": "Nissan (India)",
    "WBA": "BMW", "WBS": "BMW M", "WDB": "Mercedes-Benz", "WDD": "Mercedes-Benz",
    "ZFA": "Fiat", "ZAR": "Alfa Romeo", "1G1": "Chevrolet", "KMH": "Hyundai",
    "KNA": "Kia", "JHM": "Honda", "JTD": "Toyota", "JT1": "Toyota", "9BW": "VW (Brasil)",
    "8AP": "Fiat (Argentina)", "8AG": "Chevrolet (Argentina)", "9BD": "Fiat (Brasil)",
    "935": "Peugeot (Brasil)", "936": "Citroën (Brasil)", "8AD": "Peugeot (Argentina)",
}
# Año de modelo por el 10º carácter (código estándar; se repite cada 30 años).
_VIN_ANIO = {
    "A": 1980, "B": 1981, "C": 1982, "D": 1983, "E": 1984, "F": 1985, "G": 1986, "H": 1987,
    "J": 1988, "K": 1989, "L": 1990, "M": 1991, "N": 1992, "P": 1993, "R": 1994, "S": 1995,
    "T": 1996, "V": 1997, "W": 1998, "X": 1999, "Y": 2000, "1": 2001, "2": 2002, "3": 2003,
    "4": 2004, "5": 2005, "6": 2006, "7": 2007, "8": 2008, "9": 2009,
}
_VIN_ANIO_2 = {  # segunda vuelta del código (2010-2039)
    "A": 2010, "B": 2011, "C": 2012, "D": 2013, "E": 2014, "F": 2015, "G": 2016, "H": 2017,
    "J": 2018, "K": 2019, "L": 2020, "M": 2021, "N": 2022, "P": 2023, "R": 2024, "S": 2025,
    "T": 2026, "V": 2027, "W": 2028, "X": 2029, "Y": 2030,
}


def _vin_valido(vin):
    import re
    return bool(vin) and bool(re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", str(vin).upper()))


def decodificar_vin(vin):
    """Decodifica un VIN offline → {vin, valido, region, fabricante, wmi, anio_modelo, planta}.
    Nunca falla; si no reconoce algo lo deja en None."""
    if not vin:
        return {"vin": None, "valido": False}
    v = str(vin).strip().upper()
    valido = _vin_valido(v)
    out = {"vin": v, "valido": valido, "region": None, "fabricante": None,
           "wmi": v[:3] if len(v) >= 3 else None, "anio_modelo": None, "planta": None}
    if len(v) >= 1:
        for chars, region in _VIN_REGION.items():
            if v[0] in chars:
                out["region"] = region
                break
    if len(v) >= 3:
        out["fabricante"] = _VIN_WMI.get(v[:3]) or _VIN_WMI.get(v[:2]) or _VIN_WMI.get(v[:1])
    if len(v) >= 10:
        c = v[9]
        # elegir la vuelta más plausible: si hay 7º carácter numérico suele ser <2010
        anio = _VIN_ANIO_2.get(c) if c in _VIN_ANIO_2 else _VIN_ANIO.get(c)
        # heurística: autos con VIN moderno (letra en pos 7) tienden a ser >=2010
        if c in _VIN_ANIO and c in _VIN_ANIO_2:
            anio = _VIN_ANIO_2.get(c) if (len(v) >= 7 and v[6].isalpha()) else _VIN_ANIO.get(c)
        out["anio_modelo"] = anio
    if len(v) >= 11:
        out["planta"] = v[10]
    return out


# Respuestas de simulación para probar sin auto.
_SIM = {
    "0100": "41 00 BE 3E B8 11",
    "0120": "41 20 80 00 00 01",
    "0140": "41 40 40 00 00 00",
    "0101": "41 01 83 07 61 05",          # MIL on, 3 DTC, monitores
    "020200": "42 02 00 01 33 00 00",     # freeze frame disparado por P0133
    "020400": "42 04 00 40",              # carga ~25% en freeze
    "020500": "42 05 00 5C",              # 52°C
    "020600": "42 06 00 78",
    "020700": "42 07 00 82",
    "020B00": "42 0B 00 62",
    "020C00": "42 0C 00 2E E0",           # ~3000 RPM en freeze
    "020D00": "42 0D 00 50",              # 80 km/h
    "020E00": "42 0E 00 90",
    "020F00": "42 0F 00 3C",
    "021000": "42 10 00 12 C0",
    "021100": "42 11 00 60",
    "022F00": "42 2F 00 A0",
    "024200": "42 42 00 39 D0",
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
