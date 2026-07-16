# -*- coding: utf-8 -*-
"""Escáner de ECUs propio de SISTEMASQ24.

Autodetección real: recorre las direcciones CAN de la base, lee la identificación
UDS de cada ECU que responde (diagversion/supplier/soft/version) y la matchea
contra el índice maestro `db.json` del ecu.zip para elegir la definición exacta.

Toma como base el escáner nativo de ddt4all (core/ecu/ecu_scanner.py) pero se
reescribe headless: sin acoplamiento a Qt (options.main_window) ni al directorio
de trabajo (carga db.json por ruta absoluta). Reutiliza EcuIdent.checkWith para el
match, que es la lógica de identificación probada de sistemasq24.
"""
import json
import zipfile
from pathlib import Path

import sistemasq24.options as options
from sistemasq24.core.ecu.ecu_ident import EcuIdent

BASE = Path(__file__).resolve().parent.parent
ZIP_PATH = BASE / "vendor" / "sistemasq24" / "ecu.zip"

# Mapea el 'group' (rol de la ECU, en francés, de db.json) a un slot con ícono y
# nombre en español. Sirve para presentar las ECUs detectadas de forma coherente.
GRUPO_A_SLOT = [
    (("injection", "ecm", "gasoline", "diesel", "dcm", "sirius", "med", "ems"), "motor",   "🔧", "Motor / Inyección"),
    (("abs", "esp", "vdc"),                                                       "abs",     "🛑", "Frenos ABS / ESP"),
    (("airbag", "acu", "retenue"),                                                "airbag",  "💥", "Airbag / Retención"),
    (("tableau", "cluster", "tdb", "instrument"),                                 "tablero", "📊", "Tablero / Instrumentos"),
    (("direction", "dae", "eps", "steering"),                                     "dae",     "🎯", "Dirección asistida"),
    (("uch", "usm", "bcm", "ucbic", "bfr", "upc", "body"),                        "uch",     "⚡", "Caja de conexiones"),
    (("climat", "clim", "hvac"),                                                  "clima",   "❄️", "Climatización"),
    (("bva", "at ", "transmission", "gearbox"),                                   "caja",    "⚙️", "Caja automática"),
    (("parking", "aide au", "pdc"),                                              "parking", "📡", "Ayuda al estacionamiento"),
    (("audio", "navigation", "radio", "hfm", "telematic"),                        "multimedia", "🎵", "Audio / Navegación"),
]


def _slot_para_grupo(group, indice):
    """Devuelve (ecu_id, icon, nombre) para un 'group' de db.json.
    Si no matchea ningún patrón conocido, genera un slot genérico único."""
    g = (group or "").lower()
    for patrones, ecu_id, icon, nombre in GRUPO_A_SLOT:
        if any(p in g for p in patrones):
            return ecu_id, icon, nombre
    # genérico: usar el propio nombre de grupo (traducible aparte) + id único
    slug = "".join(c for c in g if c.isalnum()) or "ecu"
    return f"{slug}_{indice}", "🧩", (group or "Módulo")


class SQ24Scanner:
    def __init__(self):
        self.targets = []          # lista de EcuIdent
        self.addresses_can = []    # direcciones CAN únicas a sondear
        self._cargado = False

    # ---------------------------------------------------------------- base
    def cargar_indice(self):
        """Carga db.json del ecu.zip y arma la lista de targets (EcuIdent)."""
        if self._cargado:
            return True
        if not ZIP_PATH.exists():
            return False
        with zipfile.ZipFile(ZIP_PATH, "r") as zf:
            db = json.loads(zf.read("db.json"))
        addrs = set()
        for href, tv in db.items():
            proto = tv.get("protocol", "")
            addr = tv.get("address", "")
            group = tv.get("group", "")
            projects = tv.get("projects", [])
            ecuname = tv.get("ecuname", href)
            if "CAN" in proto and addr not in ("00", "FF", ""):
                addrs.add(addr)
            autoidents = tv.get("autoidents", [])
            if not autoidents:
                self.targets.append(EcuIdent("", "", "", "", ecuname, group, href,
                                             proto, projects, addr, True))
            else:
                for ai in autoidents:
                    self.targets.append(EcuIdent(
                        ai.get("diagnostic_version", ""), ai.get("supplier_code", ""),
                        ai.get("soft_version", ""), ai.get("version", ""),
                        ecuname, group, href, proto, projects, addr, True))
        self.addresses_can = sorted(addrs)
        self._cargado = True
        return True

    # ---------------------------------------------------------------- match
    def _match(self, diagversion, supplier, soft, version, addr):
        """Devuelve el mejor EcuIdent para una identificación leída, o None."""
        aprox = []
        for t in self.targets:
            if t.protocol != "CAN":
                continue
            try:
                if t.checkWith(diagversion, supplier, soft, version, addr):
                    return t
            except (ValueError, TypeError):
                continue
            try:
                if t.checkApproximate(diagversion, supplier, soft, addr):
                    aprox.append(t)
            except (ValueError, TypeError):
                continue
        # match aproximado: el de versión más cercana
        if aprox:
            try:
                iv = int("0x" + version, 16)
                aprox.sort(key=lambda t: abs(int("0x" + t.version, 16) - iv)
                           if t.version else 0xFFFFFF)
            except ValueError:
                pass
            return aprox[0]
        return None

    # ---------------------------------------------------------------- probe
    def _identificar(self, addr):
        """Lee la identificación UDS de la ECU en `addr` (protocolo de ddt4all).
        Devuelve (diagversion, supplier, soft, version) o None si no responde."""
        elm = options.elm
        if not options.simulation_mode:
            if elm is None:
                return None
            if not elm.start_session_can("1003"):
                return None
        try:
            # diagversion (22F1A0)
            r = self._req(addr, "22F1A0")
            if r is None:
                return None
            diagversion = r.replace(" ", "")[6:8]
            # supplier (22F18A)
            r = self._req(addr, "22F18A")
            if r is None:
                return None
            supplier = bytes.fromhex(r.replace(" ", "")[6:132]).decode("utf8", "ignore")
            # soft (22F194)
            r = self._req(addr, "22F194")
            if r is None:
                return None
            soft = bytes.fromhex(r.replace(" ", "")[6:38]).decode("utf8", "ignore")
            # version (22F195)
            r = self._req(addr, "22F195")
            if r is None:
                return None
            version = bytes.fromhex(r.replace(" ", "")[6:38]).decode("utf8", "ignore")
        except (ValueError, Exception):
            self._cerrar_sesion()
            return None
        self._cerrar_sesion()
        if diagversion == "":
            return None
        return diagversion, supplier, soft, version

    def _req(self, addr, cmd):
        """Envía un request UDS (servicio 22) y devuelve la respuesta solo si es
        POSITIVA (empieza con 62). En simulación usa las respuestas canned."""
        if options.simulation_mode:
            return _SIM_RESP.get((addr, cmd))
        try:
            resp = options.elm.request(req=cmd, positive="", cache=False)
        except Exception:
            return None
        if resp is None or "WRONG" in resp:
            return None
        # Rechazar respuestas negativas (7F ...) o cualquier cosa que no sea el eco
        # positivo del servicio 22 (0x62). Sin esto, un '7F 22 78' entraría al parser.
        if not resp.replace(" ", "").upper().startswith("62"):
            return None
        return resp

    def _cerrar_sesion(self):
        if not options.simulation_mode and options.elm is not None:
            try:
                options.elm.cmd("1001")
            except Exception:
                pass

    # ---------------------------------------------------------------- escaneo
    def escanear(self, canline=0, progress_cb=None):
        """Recorre las direcciones CAN, identifica y matchea. Devuelve lista de
        dicts: {ecu_id, archivo, icon, nombre, group, projects, addr}.
        progress_cb(actual, total, addr, n_detectadas) se llama por cada dirección."""
        if not self.cargar_indice():
            return {"ok": False, "error": "No se pudo cargar el índice de ECUs"}

        elm = options.elm
        timeout_prev = None
        if not options.simulation_mode:
            if elm is None:
                return {"ok": False, "error": "Sin conexión con el adaptador"}
            try:
                elm.init_can()
                # Timeout CORTO durante el escaneo: las direcciones que no responden
                # deben fallar rápido (si no, 124 direcciones × varios segundos = eterno).
                timeout_prev = getattr(options, "cantimeout", None)
                elm.set_can_timeout(200)
            except Exception:
                pass

        addrs = self.addresses_can if not options.simulation_mode else ["26", "13", "62", "01", "04"]
        total = len(addrs)
        detectadas = []
        vistos = set()
        for i, addr in enumerate(addrs):
            if progress_cb:
                try: progress_cb(i + 1, total, addr, len(detectadas))
                except Exception: pass
            if addr in ("00", "FF"):
                continue
            if not options.simulation_mode:
                try:
                    # init_can() ya se llamó una vez antes del loop; set_can_addr
                    # reconfigura el protocolo por dirección, así que no hace falta
                    # re-inicializar en cada vuelta (solo agrega latencia).
                    elm.set_can_addr(addr, {"ecuname": "SCAN"}, canline)
                except Exception:
                    continue
            ident = self._identificar(addr)
            if ident is None:
                continue
            t = self._match(*ident, addr)
            if t is None:
                continue
            if t.href in vistos:
                continue
            vistos.add(t.href)
            ecu_id, icon, nombre = _slot_para_grupo(t.group, i)
            # evitar colisión de ecu_id (dos motores, etc.)
            base_id = ecu_id
            k = 2
            while ecu_id in [d["ecu_id"] for d in detectadas]:
                ecu_id = f"{base_id}{k}"
                k += 1
            detectadas.append({
                "ecu_id": ecu_id, "archivo": t.href, "icon": icon,
                "nombre": nombre, "group": t.group,
                "projects": t.projects, "addr": addr, "ecuname": t.name,
            })

        if not options.simulation_mode and elm is not None:
            try:
                if timeout_prev is not None:
                    elm.set_can_timeout(timeout_prev)
                elm.close_protocol()
            except Exception:
                pass

        vehiculo = self._deducir_vehiculo(detectadas)
        return {"ok": True, "detectadas": detectadas, "vehiculo": vehiculo,
                "total": len(detectadas)}

    def _deducir_vehiculo(self, detectadas):
        """Deduce el nombre del vehículo por el 'project' más común entre las ECUs."""
        from collections import Counter
        proys = Counter()
        for d in detectadas:
            for p in d.get("projects", []):
                proys[p] += 1
        if not proys:
            return "Auto detectado"
        top = proys.most_common(1)[0][0]
        return f"Auto detectado ({top})"


_scanner = None

def get_scanner():
    global _scanner
    if _scanner is None:
        _scanner = SQ24Scanner()
    return _scanner


# Respuestas de simulación (portadas de identify_new de ddt4all) para poder probar
# el pipeline de detección sin un auto conectado. Cubren addr 26/13/62/01/04.
_SIM_RESP = {
    ("26", "22F1A0"): "62 F1 A0 08",
    ("26", "22F18A"): "62 F1 8A 43 4F 4E 54 49 4E 45 4E 54 41 4C 20 41 55 54 4F 4D 4F 54 49 56 45",
    ("26", "22F194"): "62 F1 94 31 34 32 36 20 20 20 20 20 20 20 20 20",
    ("26", "22F195"): "62 F1 95 31 30 30 30 20 20 20 20 20 20 20 20 20",
    ("13", "22F1A0"): "62 F1 A0 0D",
    ("13", "22F18A"): "62 F1 8A 43 41 50",
    ("13", "22F194"): "62 F1 94 32 32",
    ("13", "22F195"): "62 F1 95 31 38 35 39 30 FF FF FF FF FF",
    ("62", "22F1A0"): "62 F1 A0 04",
    ("62", "22F18A"): "62 F1 8A 41 46 4B",
    ("62", "22F194"): "62 F1 94 31 30 30 30 30 30 30 20 20 20 20 20 20 20 20",
    ("62", "22F195"): "62 F1 95 30 35 30 31 30 30 30 32 31 37 30 30 FF FF FF FF FF",
    ("01", "22F1A0"): "62 F1 A0 04",
    ("01", "22F18A"): "62 F1 8A 43 41 53",
    ("01", "22F194"): "62 F1 94 4E 33 32 52 41 46 30 30 30 31 31 00 00 00 00 00 00",
    ("01", "22F195"): "62 F1 95 46 30 37 2F 34 6F 00 00 00 03",
    ("04", "22F1A0"): "62 F1 A0 04",
    ("04", "22F18A"): "62 F1 8A 56 69 73 74 65 6F 6E 5F 4E 61 6D 65 73 74 6F 76 6F 5F 30 39 36 20",
    ("04", "22F194"): "62 F1 94 56 30 36 30 32 F1 94 56 30 36",
    ("04", "22F195"): "62 F1 95 56 30 36 30 32 F1 95 56 30 36",
}
