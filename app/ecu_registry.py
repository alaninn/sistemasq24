# -*- coding: utf-8 -*-
"""Registro de las ECUs del Renault Mégane II F4R.

Carga los 6 archivos de ECU (vía el parser nativo de ddt4all), sus layouts
(pantallas) y la memoria de traducción francés→español generada en la Fase 1.
Expone vistas ya traducidas al español para el backend web.

No reescribe la lógica de comunicación: reutiliza `EcuFile` / `EcuRequest`
de sistemasq24. Esta capa solo organiza, traduce y decide qué es peligroso.
"""
import json
from pathlib import Path

import sistemasq24.options as options
from sistemasq24.core.ecu.ecu_file import EcuFile

BASE = Path(__file__).resolve().parent.parent            # megane2_f4r/
ORIG = BASE / "original"
ES = BASE / "es"
TM_PATH = BASE / "tools" / "tm.json"
AYUDAS_PATH = Path(__file__).resolve().parent / "ayudas.json"

# Las 6 ECUs confirmadas por escaneo real del Mégane II F4R.
# id -> (archivo base, ícono, nombre corto en español)
ECU_DEFS = [
    ("motor",   "S3000_AD_CAN_3_X84ph2_S",            "🔧", "Motor / Inyección (F4R)"),
    ("abs",     "Abs_X84_Bosch8.1_V1.3",              "🛑", "Frenos ABS / ESP"),
    ("airbag",  "RC5_P1_P2_modifie_le20-04-2007_bis", "💥", "Airbag / Retención"),
    ("uch",     "USM_X84_C5_45",                      "⚡", "Caja de conexiones (UCH/USM)"),
    ("dae",     "DAE_X84_Serie_V1",                   "🎯", "Dirección asistida"),
    ("tablero", "Tdb_BCEKL84_serie_4emeRev",          "📊", "Tablero / Instrumentos"),
]

# Servicios de SOLO LECTURA (no modifican nada en el auto). Lista explícita:
# NO reutilizamos options.safe_commands porque esa es "seguro de transmitir en modo
# experto" e incluye 14 (BorrarDTC), que SÍ modifica el auto (borra la memoria de fallas).
#   10 = cambio de sesión · 12 = freeze frame · 17/19 = leer DTC · 1A = leer identificación
#   21/22 = leer datos · 23 = leer memoria · 3E = tester present
SAFE_SERVICES = {'10', '12', '17', '19', '1A', '21', '22', '23', '3E'}

# Códigos de respuesta negativa UDS (NRC) → explicación en español, para poder
# decirle al usuario POR QUÉ la ECU rechazó un comando (ej. un actuador).
NRC = {
    "10": "rechazo general",
    "11": "servicio no soportado",
    "12": "sub-función no soportada",
    "13": "longitud o formato de mensaje incorrecto",
    "22": "condiciones no correctas (el auto necesita otro estado: contacto, motor, etc.)",
    "31": "valor fuera de rango (actuador o parámetro inválido)",
    "33": "acceso denegado (necesita desbloqueo de seguridad)",
    "35": "clave inválida",
    "78": "recibido, respuesta pendiente",
    "7E": "sub-función no soportada en la sesión activa",
    "7F": "servicio no soportado en la sesión activa (necesita otra sesión)",
}


def dtc_estandar(raw_hex):
    """Convierte un código DTC crudo de 2 bytes al formato universal SAE J2012.
    Ej: '0530' -> 'P0530', 'C111' -> 'U0111', '500F' -> 'C100F'.
    Así el código coincide con los que aparecen en las tablas OBD-II conocidas."""
    if not raw_hex:
        return None
    try:
        v = int(raw_hex, 16) & 0xFFFF
    except (ValueError, TypeError):
        return None
    if v == 0:
        return None
    b1 = (v >> 8) & 0xFF
    letra = "PCBU"[(b1 >> 6) & 0x3]       # 00=P 01=C 10=B 11=U
    d1 = (b1 >> 4) & 0x3                   # primer dígito (0-3)
    d2 = b1 & 0xF                          # segundo dígito (hex)
    d34 = v & 0xFF                         # tercero y cuarto (hex)
    return f"{letra}{d1}{d2:X}{d34:02X}"


class TranslatedECU:
    def __init__(self, ecu_id, icon, short_name, ecu_file, layout, es_dict, tm, ayudas):
        self.id = ecu_id
        self.icon = icon
        self.short_name = short_name
        self.ecu = ecu_file            # EcuFile de ddt4all
        self.layout = layout           # dict con screens/categories
        self.es = es_dict              # diccionario de traducción es/<ecu>.es.json
        self._tm = tm
        self._ayudas = ayudas

    # ---- traducción ----
    def t(self, s):
        """Traduce cualquier cadena FR/EN al español vía la memoria global."""
        if s is None:
            return ""
        return self._tm.get(s, s)

    def help_for(self, data_name):
        """Explicación 'modo niño' de un parámetro, si existe."""
        # 1) ayuda específica por ECU+parámetro  2) ayuda global por nombre
        key = f"{self.id}|{data_name}"
        if key in self._ayudas:
            return self._ayudas[key]
        return self._ayudas.get(data_name, "")

    # ---- metadata ----
    def info(self):
        n_params = len(self.ecu.data)
        n_screens = len(self.layout.get("screens", {}))
        return {
            "id": self.id,
            "icon": self.icon,
            "nombre": self.short_name,
            "ecuname": self.ecu.ecuname,
            "funcion": self.t(self.ecu.funcname),
            "protocolo": self.ecu.ecu_protocol,
            "tx": self.ecu.ecu_send_id,
            "rx": self.ecu.ecu_recv_id,
            "pantallas": n_screens,
            "parametros": n_params,
        }

    # ---- pantallas ----
    def categories(self):
        """Categorías con sus pantallas, traducidas."""
        out = []
        cats = self.layout.get("categories", {})
        for cat_name, screen_names in cats.items():
            out.append({
                "nombre": self.t(cat_name),
                "original": cat_name,
                "pantallas": [
                    {"nombre": self.t(s), "original": s} for s in screen_names
                ],
            })
        # pantallas huérfanas (sin categoría)
        in_cats = {s for sl in cats.values() for s in sl}
        huerfanas = [s for s in self.layout.get("screens", {}) if s not in in_cats]
        if huerfanas:
            out.append({
                "nombre": "Otras pantallas",
                "original": "__otras__",
                "pantallas": [{"nombre": self.t(s), "original": s} for s in huerfanas],
            })
        return out

    def screen(self, screen_name):
        """Detalle de una pantalla: displays, botones, etiquetas (traducidos)."""
        scr = self.layout.get("screens", {}).get(screen_name)
        if scr is None:
            return None

        displays = []
        for d in scr.get("displays", []):
            data_name = d.get("text", "")
            req_name = d.get("request", "")
            displays.append({
                "id": self.param_id(req_name, data_name),
                "dato": data_name,
                "etiqueta": self.t(data_name),
                "unidad": self._unit_of(data_name),
                "ayuda": self.help_for(data_name),
                "request": req_name,
                "escritura": False,
            })

        inputs = []
        for d in scr.get("inputs", []):
            data_name = d.get("text", "")
            req_name = d.get("request", "")
            meta = self._input_meta(data_name)
            inputs.append({
                "id": self.param_id(req_name, data_name),
                "dato": data_name,
                "etiqueta": self.t(data_name),
                "unidad": meta["unidad"],
                "ayuda": self.help_for(data_name),
                "request": req_name,
                "escritura": True,
                "tipo": meta["tipo"],
                "opciones": meta["opciones"],
            })

        botones = []
        for b in scr.get("buttons", []):
            txt = b.get("text", "")
            sends = b.get("send", [])
            req_names = [s.get("RequestName", "") for s in sends]
            peligroso = any(self.is_dangerous(r) for r in req_names)
            # ¿alguno de sus requests necesita que el usuario elija/complete algo?
            necesita_inputs = any(
                len(self.ecu.get_request(r).sendbyte_dataitems) > 0
                for r in req_names if self.ecu.get_request(r) is not None
            )
            # botón de solo-lectura: no modifica el auto y no pide que el usuario elija nada
            solo_lectura = (not peligroso) and (not necesita_inputs) and len(req_names) > 0
            botones.append({
                "texto": self.t(txt),
                "original": txt,
                "requests": req_names,
                "mensajes": [self.t(m) for m in b.get("messages", [])],
                "peligroso": peligroso,
                "necesita_inputs": necesita_inputs,
                "solo_lectura": solo_lectura,
            })

        etiquetas = [self.t(l.get("text", "")) for l in scr.get("labels", [])]

        return {
            "nombre": self.t(screen_name),
            "original": screen_name,
            "displays": displays,
            "inputs": inputs,
            "botones": botones,
            "etiquetas": [e for e in etiquetas if e],
        }

    # ---- parámetros legibles (para el selector personalizado) ----
    def readable_params(self):
        """Todos los parámetros que se pueden leer en vivo, agrupados por request
        de lectura. Devuelve lista de {id, dato, etiqueta, unidad, ayuda, request}."""
        out = []
        seen = set()
        for req_name, req in self.ecu.requests.items():
            if not self._is_read_request(req):
                continue
            for data_name in req.dataitems.keys():
                pid = self.param_id(req_name, data_name)
                if pid in seen:
                    continue
                seen.add(pid)
                out.append({
                    "id": pid,
                    "dato": data_name,
                    "etiqueta": self.t(data_name),
                    "unidad": self._unit_of(data_name),
                    "ayuda": self.help_for(data_name),
                    "request": req_name,
                    "util": self._es_util(data_name),
                })
        out.sort(key=lambda p: p["etiqueta"].lower())
        return out

    def _es_util(self, data_name):
        """True si el parámetro es un sensor OBSERVABLE para el usuario: tiene unidad
        física (°C, V, RPM, %, km/h, ms, bar…) o es un enum de estados chico
        (encendido/apagado, presente/ausente). Los que no tienen ni unidad ni enum
        suelen ser códigos/contadores internos sin valor visible."""
        d = self.ecu.data.get(data_name)
        if d is None:
            return False
        if getattr(d, "unit", ""):
            return True
        items = getattr(d, "items", {}) or {}
        return 2 <= len(items) <= 16

    # ---- helpers ----
    def param_id(self, request_name, data_name):
        return f"{self.id}|{request_name}|{data_name}"

    def _unit_of(self, data_name):
        d = self.ecu.data.get(data_name)
        if d is None:
            return ""
        unit = getattr(d, "unit", "")
        return self.t(unit) if unit else ""

    def _input_meta(self, data_name):
        """Devuelve cómo pedirle este dato al usuario: combo de opciones o campo libre."""
        d = self.ecu.data.get(data_name)
        if d is None:
            return {"tipo": "texto", "opciones": [], "unidad": ""}
        items = getattr(d, "items", {})   # {etiqueta_original: valor_numerico}
        unit = getattr(d, "unit", "")
        unidad = self.t(unit) if unit else ""
        if items:
            opciones = []
            for lbl, val in sorted(items.items(), key=lambda kv: int(kv[1])):
                opciones.append({
                    "etiqueta": self.t(lbl),
                    "valor": hex(int(val))[2:].upper().zfill(2),
                })
            return {"tipo": "opciones", "opciones": opciones, "unidad": unidad}
        return {"tipo": "texto", "opciones": [], "unidad": unidad}

    def _is_read_request(self, req):
        sb = (req.sentbytes or "")[:2].upper()
        return sb in SAFE_SERVICES and not req.manualsend and len(req.dataitems) > 0

    def is_read_request_name(self, request_name):
        req = self.ecu.get_request(request_name)
        return req is not None and self._is_read_request(req)

    def is_dangerous(self, request_name):
        """True si el request modifica el auto (requiere modo avanzado)."""
        req = self.ecu.get_request(request_name)
        if req is None:
            return False
        sb = (req.sentbytes or "")[:2].upper()
        if not sb:
            return False
        if sb == "10":     # cambio de sesión: permitido siempre
            return False
        return sb not in SAFE_SERVICES

    # ---- sesión de diagnóstico (necesaria para leer sensores en Renault) ----
    def _session_cmd(self):
        for cand in ("Start Diagnostic Session", "Session par défaut", "Default Session"):
            req = self.ecu.get_request(cand)
            if req is not None and req.sentbytes:
                return "".join(req.sentbytes.split())
        return "10C0"

    def ensure_session(self, force=False):
        """Abre la sesión de diagnóstico extendida si hace falta. Sin esto, los ECU
        Renault no responden a las lecturas de sensores (servicios 21/22)."""
        if options.simulation_mode or options.elm is None:
            return True
        cmd = self._session_cmd()
        # ddt4all guarda la última sesión abierta en elm.startSession; y la resetea
        # a "" cuando cambia la dirección de ECU. Solo re-mandamos si hace falta.
        if not force and getattr(options.elm, "startSession", "") == cmd:
            return True
        try:
            if self.ecu.ecu_protocol.upper() == "CAN":
                return options.elm.start_session_can(cmd)
            return options.elm.start_session_iso(cmd)
        except Exception:
            return False

    # ---- escaneo: ¿responde esta ECU? + su identificación ----
    def scan_identidad(self):
        """Verifica si la ECU responde y lee su identificación (nº de pieza, versión…)."""
        cands = [
            "System Identification", "Read - SystemIdentification",
            "Lecture Identification Calculateur", "RDBLI Identification",
            "Identification", "RDBLI - System Frame",
            "Lecture des identifiers disponibles", "Read Syst Identification",
        ]
        req = None
        for c in cands:
            r = self.ecu.get_request(c)
            if r is not None and len(r.dataitems) > 0:
                req = r
                break
        if req is None:
            for rn, rq in self.ecu.requests.items():
                if "ident" in rn.lower() and self._is_read_request(rq):
                    req = rq
                    break
        if req is None:
            return {"presente": None, "error": "Esta ECU no tiene un request de identificación"}

        self.ensure_session()
        if not options.simulation_mode and options.elm is not None:
            try:
                options.elm.clear_cache()
            except Exception:
                pass
        try:
            vals = req.send_request({})
        except Exception as e:
            return {"presente": False, "error": str(e)}
        if vals is None or all(v is None for v in vals.values()):
            return {"presente": False}
        datos = {}
        for k, v in vals.items():
            if v is not None and str(v).strip() != "":
                datos[self.t(k)] = self.t(v) if isinstance(v, str) else v
        return {"presente": True, "identificacion": datos}

    # ---- lectura de códigos de falla (DTC) ----
    def _raw_send(self, cmd):
        """Envía un comando crudo al ELM y devuelve la respuesta cruda (string)."""
        if options.simulation_mode:
            # respuestas de ejemplo para el modo demostración
            if "1902" in cmd:
                # respuesta UDS de ejemplo (airbag): 2 DTC
                return ("59 02 FF 90 07 41 90 08 41")
            if "17FF00" in cmd:
                # servicio 17 con 1 DTC de ejemplo
                return "57 01 03 00 01 01"
            return "00 " * 20
        if options.elm is None:
            return None
        return options.elm.request(cmd, cache=False)

    def _dtc_request(self):
        for cand in ("ReadDTCInformation.ReportDTC", "ReadDTC"):
            r = self.ecu.get_request(cand)
            if r is not None:
                return r
        return None

    def read_dtcs(self):
        """Lee los códigos de falla de esta ECU. Devuelve estructura traducida."""
        req = self._dtc_request()
        if req is None:
            return {"soportado": False, "cantidad": 0, "dtcs": []}

        # abrir sesión de diagnóstico extendida
        self.ensure_session()
        if not options.simulation_mode and options.elm is not None:
            try:
                options.elm.set_can_timeout(1500)
            except Exception:
                pass

        cmd = "".join(req.sentbytes.split())
        resp = self._raw_send(cmd)

        if not options.simulation_mode and options.elm is not None:
            try:
                options.elm.set_can_timeout(options.cantimeout)
            except Exception:
                pass

        if resp is None or "WRONG" in resp or "RESPONSE" in resp:
            return {"soportado": True, "cantidad": 0, "dtcs": [], "error": "Respuesta inválida de la ECU"}

        parts = resp.strip().split()
        if not parts or parts[0].upper() == "7F":
            return {"soportado": True, "cantidad": 0, "dtcs": [], "error": "La ECU devolvió un error al leer fallas"}

        # nº de DTC está en el segundo byte
        try:
            numberofdtc = int(parts[1], 16) if len(parts) > 1 else 0
        except ValueError:
            numberofdtc = 0

        if numberofdtc == 0 or len(parts) <= 2:
            return {"soportado": True, "cantidad": 0, "dtcs": []}

        shift = req.shiftbytescount or 3
        endian = self.ecu.endianness
        can_response = parts
        dtcs = []
        for _dn in range(min(numberofdtc, 60)):
            if len(can_response) < 3:
                break
            campos = {}
            codigo_raw = None
            descripcion = None
            detalle = None
            presente = None
            memorizada = None
            for k, dataitem in req.dataitems.items():
                if k == "NDTC":
                    continue
                data = self.ecu.data.get(k)
                if data is None:
                    continue
                try:
                    vhex = data.getHexValue(" ".join(can_response), dataitem, endian)
                except Exception:
                    vhex = None
                if vhex is None:
                    continue
                try:
                    value = int("0x" + vhex, 16)
                except ValueError:
                    continue
                lists = getattr(data, "lists", {})
                items = getattr(data, "items", {})
                if len(items) > 0 and value in lists:
                    texto = self.t(lists[value])
                    campos[self.t(k)] = texto
                    # identificar campos clave
                    kl = k.lower()
                    if k in ("FirstDTC", "DTC status - code panne") or "code" in kl:
                        codigo_raw = vhex.upper()
                        descripcion = texto
                    elif "standard fault" in kl or k in ("Panne type", "DTC status - type", "DTCFailureType"):
                        detalle = texto
                    elif "current failure" in kl or k in ("Panne présente",) or "testfailed" in kl.replace(" ", "") or "confirmeddtc" in kl.replace(" ", ""):
                        presente = value != 0 and texto.lower() not in ("no", "non")
                    elif "historical" in kl or k in ("Panne mémorisée",) or "pendingdtc" in kl.replace(" ", ""):
                        memorizada = value != 0 and texto.lower() not in ("no", "non")
                else:
                    campos[self.t(k)] = value
                    kl = k.lower()
                    if codigo_raw is None and (k == "FirstDTC" or "code" in kl):
                        codigo_raw = vhex.upper()

            codigo_std = dtc_estandar(codigo_raw)
            # Si la ECU no trae descripción, usar la base genérica de DTC (SAE J2012).
            if not descripcion and codigo_std:
                from dtc_db import describir as _describir
                descripcion = _describir(codigo_std)
            dtcs.append({
                "codigo": codigo_std or (("0x" + codigo_raw) if codigo_raw else "—"),
                "codigo_raw": ("0x" + codigo_raw) if codigo_raw else None,
                "descripcion": descripcion or "Falla sin descripción en la base",
                "detalle": detalle,
                "presente": bool(presente) if presente is not None else None,
                "memorizada": bool(memorizada) if memorizada is not None else None,
                "campos": campos,
            })
            can_response = can_response[shift:]

        return {"soportado": True, "cantidad": len(dtcs), "dtcs": dtcs}

    def clear_dtcs(self):
        """Borra los códigos de falla de esta ECU."""
        req = None
        for cand in ("ClearDiagnosticInformation.All", "ClearDTC", "Clear Diagnostic Information"):
            r = self.ecu.get_request(cand)
            if r is not None:
                req = r
                break
        cmd = "".join(req.sentbytes.split()) if req is not None else "14FF00"

        if options.simulation_mode:
            return {"ok": True, "simulado": True}
        if options.elm is None:
            return {"ok": False, "error": "Sin conexión"}
        try:
            if self.ecu.ecu_protocol.upper() == "CAN":
                options.elm.start_session_can("10C0")
            elif self.ecu.ecu_protocol.upper() == "KWP2000":
                options.elm.start_session_iso("10C0")
            options.elm.set_can_timeout(1500)
            resp = options.elm.request(cmd, cache=False)
            options.elm.set_can_timeout(options.cantimeout)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if resp is None or "WRONG" in resp or (resp.strip().split() and resp.strip().split()[0].upper() == "7F"):
            return {"ok": False, "error": "La ECU rechazó el borrado"}
        return {"ok": True}

    # ---- actuadores (control de salidas, servicio 30) ----
    def _output_request(self):
        return self.ecu.get_request("Output Control")

    def actuators(self):
        """Lista los actuadores que se pueden activar en esta ECU (luces, A/C, ventiladores…)."""
        req = self._output_request()
        if req is None:
            return {"soportado": False, "actuadores": []}
        out = []
        temp = self.ecu.data.get("Output Temporary Control List")
        if temp is not None:
            for val, label in getattr(temp, "lists", {}).items():
                out.append({"id": int(val), "nombre": self.t(label), "tipo": "temporal"})
        # ordenar por nombre
        out.sort(key=lambda a: a["nombre"].lower())
        return {"soportado": True, "actuadores": out}

    def activate_actuator(self, actuator_id, on=True):
        """Activa (on=True) o detiene (on=False) un actuador temporal.
        Manda el comando de servicio 30 crudo y parsea la respuesta para poder
        reportar el motivo exacto si la ECU lo rechaza (código NRC)."""
        req = self._output_request()
        if req is None:
            return {"ok": False, "error": "Esta computadora no permite activar actuadores"}
        id_hex = hex(int(actuator_id))[2:].upper().zfill(2)
        if on:
            inputs = {
                "Output Control Command": "00",              # 00 = Start Temporary
                "Output Temporary Control List": id_hex,     # qué salida (enum, hex)
                # tempON: byte que ENCIENDE/mantiene la salida. Es un dato "scaled",
                # así que se pasa en DECIMAL (no hex). En 0 la ECU acepta el comando
                # pero NO enciende (ese era el bug). 255 = duración máxima.
                "Output Control.tempON": "255",
            }
        else:
            inputs = {                                       # 11 (hex) = 17 = Stop
                "Output Control Command": "11",
                "Output Temporary Control List": id_hex,
            }
        # Los actuadores (servicio 30) necesitan la sesión SIEMPRE abierta y activa.
        if not self.ensure_session(force=True):
            return {"ok": False, "error": "No se pudo abrir sesión diagnóstica"}
        try:
            stream = " ".join(req.build_data_stream(inputs))
        except Exception as e:
            return {"ok": False, "error": f"No se pudo armar el comando: {e}"}
        if options.simulation_mode:
            return {"ok": True, "simulado": True, "comando": stream}
        if options.elm is None:
            return {"ok": False, "error": "Sin conexión con el adaptador"}
        try:
            if hasattr(options.elm, "clear_cache"):
                options.elm.clear_cache()
            resp = options.elm.request(stream, cache=False)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if resp is None:
            return {"ok": False, "error": "Sin respuesta de la ECU"}
        r = resp.replace(" ", "").upper()
        # Respuesta negativa: puede venir como '7F 30 xx' o ya decodificada 'NR:xx:...'
        nrc = None
        if r.startswith("7F") and len(r) >= 6:
            nrc = r[4:6]
        elif r.startswith("NR:"):
            nrc = resp.split(":")[1].strip()[:2].upper()
        if nrc:
            return {"ok": False, "nrc": nrc, "respuesta": resp,
                    "error": f"La ECU rechazó el actuador: {NRC.get(nrc, 'código ' + nrc)}"}
        if "WRONG" in r or "NODATA" in r or r == "":
            return {"ok": False, "error": "Respuesta inválida de la ECU", "respuesta": resp}
        return {"ok": True, "respuesta": resp, "comando": stream}

    # ---- reset del aviso de service (autonomía hasta el cambio de aceite) ----
    def read_service(self):
        """Lee cuánto falta para el service: km restantes y meses."""
        req = self.ecu.get_request("Lecture Configuration")
        if req is None:
            return {"soportado": False}
        try:
            vals = req.send_request({})
        except Exception:
            vals = None
        km = vals.get("Autonomie de vidange") if vals else None
        meses = vals.get("Autonomie de vidange : Temps") if vals else None
        # "Autonomie de vidange" viene en unidad "Km x 1000" -> pasar a km reales
        km_reales = None
        try:
            if km is not None and str(km).strip() != "":
                km_reales = int(float(km) * 1000)
        except Exception:
            km_reales = None
        try:
            meses = int(float(meses)) if meses not in (None, "") else None
        except Exception:
            pass
        return {"soportado": True, "km": km_reales, "meses": meses}

    def reset_service(self, km_reales, meses):
        """Reescribe el intervalo de service (apaga el aviso). km_reales en km de verdad."""
        req_km = self.ecu.get_request("Ecriture Param : Autonomie de vidange Km")
        req_mes = self.ecu.get_request("Ecriture Param : Autonomie de vidange Mois")
        if req_km is None or req_mes is None:
            return {"ok": False, "error": "Esta ECU no permite reiniciar el service"}
        # el dato se escribe en unidad "Km x 1000": 30000 km -> valor de display 30
        km_display = max(0, min(255, int(round(float(km_reales) / 1000.0))))
        meses_val = max(0, min(255, int(meses)))
        self.ensure_session()
        try:
            req_km.send_request({"Autonomie de vidange": str(km_display)})
            req_mes.send_request({"Autonomie de vidange : Temps": str(meses_val)})
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "km": km_display * 1000, "meses": meses_val}

    # ---- lector de memoria (ReadMemoryByAddress, svc 23) — solo lectura, seguro ----
    def read_memory(self, tipo, direccion_hex, cantidad):
        """Lee bytes crudos de la memoria del módulo. tipo: 0=micro, 1=EEPROM."""
        req = self.ecu.get_request("ReadMemoryByAddress")
        if req is None:
            return {"soportado": False, "error": "Este módulo no permite leer memoria"}
        # Formato del comando (confirmado por el template 23 00 00 00 00 01):
        #   23 <tipo:1B> <direccion:3B> <cantidad:1B>
        # Lo construimos a mano para que la dirección/cantidad en hex sean exactas
        # (setValue interpretaría los valores como decimal y corrompería la dirección).
        try:
            # Validar hex string antes de parsear
            hex_str = str(direccion_hex).strip().upper().replace("0X", "")
            if not hex_str or not all(c in "0123456789ABCDEF" for c in hex_str):
                return {"soportado": True, "error": f"Dirección hexadecimal inválida: '{direccion_hex}'"}
            direccion = int(hex_str, 16)
            if direccion > 0xFFFFFF:
                return {"soportado": True, "error": f"Dirección fuera de rango (max 0xFFFFFF)"}
            cantidad = max(1, min(255, int(cantidad)))
            tipo_b = f"{int(tipo) & 0xFF:02X}"
            addr_b = f"{direccion & 0xFFFFFF:06X}"
            cant_b = f"{cantidad & 0xFF:02X}"
            cmd = "23" + tipo_b + addr_b + cant_b
        except (ValueError, TypeError) as e:
            return {"soportado": True, "error": f"Dirección o cantidad inválida: {e}"}
        self.ensure_session()
        resp = self._raw_send(cmd)
        if resp is None:
            return {"soportado": True, "error": "Sin respuesta del módulo"}
        partes = resp.strip().split()
        # la respuesta al 23 suele empezar con el eco 63; quitamos el primer byte de servicio
        datos = partes[1:] if partes and partes[0].upper() in ("63", "7F") else partes
        if partes and partes[0].upper() == "7F":
            return {"soportado": True, "error": "El módulo rechazó la lectura de memoria", "comando": cmd}
        return {"soportado": True, "comando": cmd, "direccion": direccion_hex,
                "cantidad": cantidad, "bytes": [b.upper() for b in datos]}

    def read_request(self, request_name, inputs=None):
        """Lee un request y devuelve valores traducidos: {dato: {valor, etiqueta, unidad}}."""
        req = self.ecu.get_request(request_name)
        if req is None:
            return None
        self.ensure_session()
        # Limpiar la caché del ELM: sin esto, devuelve siempre la misma respuesta
        # cacheada y los valores no se actualizan en tiempo real.
        if not options.simulation_mode and options.elm is not None:
            try:
                options.elm.clear_cache()
            except Exception:
                pass
        values = req.send_request(inputs or {})
        # Si la respuesta vino vacía (todos None), puede ser que la sesión se cerró:
        # la reabrimos y reintentamos una vez. Esto hace la lectura robusta en el auto.
        if (not options.simulation_mode and options.elm is not None and
                (values is None or (values and all(v is None for v in values.values())))):
            self.ensure_session(force=True)
            values = req.send_request(inputs or {})
        if values is None:
            return None
        out = {}
        for data_name, val in values.items():
            out[data_name] = {
                "etiqueta": self.t(data_name),
                "valor": self.t(val) if isinstance(val, str) else val,
                "unidad": self._unit_of(data_name),
            }
        return out


# Ruta al ecu.zip con las 1973 ECUs + layouts de toda la base sistemasq24.
ZIP_PATH = BASE / "vendor" / "sistemasq24" / "ecu.zip"


class Registry:
    """Registro con perfil activo. Puede servir el set curado del F4R (default,
    100% traducido + procedimientos/ayudas) o un set DETECTADO en runtime que se
    arma cargando las ECUs directo del ecu.zip (traducción parcial vía tm.json)."""

    def __init__(self):
        self.tm = json.loads(TM_PATH.read_text(encoding="utf-8"))
        self.ayudas = {}
        if AYUDAS_PATH.exists():
            self.ayudas = json.loads(AYUDAS_PATH.read_text(encoding="utf-8"))
        # Arranca SIN auto: nada del F4R hasta seleccionarlo o detectar un vehículo.
        self.ecus = {}
        self.perfil = "ninguno"        # "ninguno" | "f4r" (curado) | "detectado"
        self.vehiculo = None
        self._orden = []               # orden de las ECUs del perfil activo (para list())

    # ------------------------------------------------------------------ perfiles
    def reset(self):
        """Descarga el auto activo: vuelve al estado sin vehículo."""
        self.ecus = {}
        self._orden = []
        self.perfil = "ninguno"
        self.vehiculo = None

    def load_curado_f4r(self):
        """Carga las 6 ECUs curadas del Mégane II F4R desde original/ + es/."""
        self.ecus = {}
        self._orden = []
        for ecu_id, base, icon, short in ECU_DEFS:
            ecu_file = EcuFile(str(ORIG / f"{base}.json"), isfile=True)
            layout = json.loads((ORIG / f"{base}.json.layout").read_text(encoding="utf-8"))
            es_path = ES / f"{base}.es.json"
            es_dict = json.loads(es_path.read_text(encoding="utf-8")) if es_path.exists() else {}
            self.ecus[ecu_id] = TranslatedECU(
                ecu_id, icon, short, ecu_file, layout, es_dict, self.tm, self.ayudas
            )
            self._orden.append(ecu_id)
        # Además de las 6 ECUs curadas, sumamos el "Motor OBD-II estándar": el ECU enhanced
        # del F4R (Sagem S3000) NO expone el ajuste corto/largo de combustible como % ± igual
        # que el escáner genérico — usa "factor de enriquecimiento" y "corrección adaptativa"
        # por zonas, en otra escala. Para que en F4R se vean los MISMOS % que muestra el modo
        # genérico (PID 0106/0107) y el estado de lazo (PID 03), exponemos esos PIDs estándar
        # como una ECU virtual extra. Usa broadcast 7DF, addressing propio (ver _seleccionar_ecu).
        try:
            from obd_generico import get_obd
            self.ecus["obd"] = get_obd()
            self._orden.append("obd")
        except Exception:
            pass
        self.perfil = "f4r"
        self.vehiculo = "Mégane II F4R"

    def load_generico(self):
        """Carga el perfil OBD-II GENÉRICO (funciona en cualquier auto, sin ecu.zip)."""
        from obd_generico import get_obd
        obd = get_obd()
        self.ecus = {"obd": obd}
        self._orden = ["obd"]
        self.perfil = "generico"
        self.vehiculo = "OBD-II Genérico"
        return obd

    def load_detectado(self, matches, vehiculo="Auto detectado"):
        """Arma el perfil activo desde ECUs del ecu.zip.
        matches = [{'ecu_id','archivo','icon','nombre'}, ...] donde 'archivo' es el
        nombre del .json dentro del zip (sin ruta)."""
        nuevas = {}
        orden = []
        for m in matches:
            tecu = self._ecu_desde_zip(
                m["ecu_id"], m["archivo"], m.get("icon", "🧩"), m.get("nombre", m["ecu_id"])
            )
            if tecu is not None:
                nuevas[m["ecu_id"]] = tecu
                orden.append(m["ecu_id"])
        if not nuevas:
            return 0
        self.ecus = nuevas
        self._orden = orden
        self.perfil = "detectado"
        self.vehiculo = vehiculo
        return len(nuevas)

    def _ecu_desde_zip(self, ecu_id, archivo, icon, nombre):
        """Construye un TranslatedECU cargando <archivo>.json y su .layout del zip.
        La ECU se extrae a un temporal para reusar el parser nativo de sistemasq24."""
        import tempfile
        import zipfile
        if not ZIP_PATH.exists():
            return None
        base = archivo[:-5] if archivo.endswith(".json") else archivo
        json_name = base + ".json"
        layout_name = base + ".json.layout"
        try:
            with zipfile.ZipFile(ZIP_PATH, "r") as zf:
                nombres = set(zf.namelist())
                if json_name not in nombres:
                    return None
                js_bytes = zf.read(json_name)
                layout = {}
                if layout_name in nombres:
                    layout = json.loads(zf.read(layout_name).decode("utf-8", "ignore"))
            # extraer el JSON a un temporal para que EcuFile lo parsee (isfile=True)
            tmpdir = tempfile.mkdtemp(prefix="sq24_ecu_")
            tmppath = Path(tmpdir) / json_name
            tmppath.write_bytes(js_bytes)
            ecu_file = EcuFile(str(tmppath), isfile=True)
        except Exception:
            return None
        # perfil detectado: sin diccionario es/ curado (traducción parcial vía tm.json)
        return TranslatedECU(ecu_id, icon, nombre, ecu_file, layout, {}, self.tm, self.ayudas)

    # ------------------------------------------------------------------ consultas
    def list(self):
        return [self.ecus[e_id].info() for e_id in self._orden if e_id in self.ecus]

    def get(self, ecu_id):
        return self.ecus.get(ecu_id)


_registry = None

def get_registry():
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry
