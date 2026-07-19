# -*- coding: utf-8 -*-
"""Descripciones de códigos de falla (DTC) genéricos OBD-II, en español.

Curado a mano a partir de la norma SAE J2012 (los códigos genéricos P0/C0/B0/U0
más comunes). Se usa para explicar los DTC que lee el scanner cuando la ECU no
trae su propia descripción (sobre todo en el modo OBD-II genérico).

`describir(codigo)` devuelve la descripción por orden de calidad:
  1. `DESCRIPCIONES` — ~107 códigos curados a mano en español perfecto (los de taller).
  2. `dtc_generico.json` — base completa (~9400 códigos SAE J2012, de Wal33D/dtc-database,
     MIT) traducida al español por términos (buena, no siempre perfectamente gramatical).
  3. fallback por familia → por letra.
Nunca falla; si no conoce el código, describe la categoría.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

_GENERICO_PATH = Path(__file__).resolve().parent / "dtc_generico.json"
try:
    _GENERICO_EN = json.loads(_GENERICO_PATH.read_text(encoding="utf-8"))
except Exception:
    _GENERICO_EN = {}

# Traductor por términos del vocabulario OBD (muy formulaico). Se aplica sobre el texto en
# minúsculas, frases largas primero para no romper las cortas. No busca gramática perfecta:
# busca que un mecánico entienda el código aunque no esté en la lista curada.
_TERMINOS = [
    # --- frases largas (multi-palabra) ---
    ("random/multiple cylinder misfire detected", "fallo de encendido aleatorio/múltiple detectado"),
    ("catalyst system efficiency below threshold", "eficiencia del catalizador por debajo del umbral"),
    ("high speed can communication bus", "bus CAN de alta velocidad"),
    ("medium speed can communication bus", "bus CAN de media velocidad"),
    ("low speed can communication bus", "bus CAN de baja velocidad"),
    ("can communication bus", "bus de comunicación CAN"),
    ("communication bus", "bus de comunicación"),
    ("lost communication with", "pérdida de comunicación con"),
    ("mass or volume air flow", "caudal másico o volumétrico de aire"),
    ("manifold absolute pressure", "presión absoluta del colector"),
    ("barometric pressure", "presión barométrica"),
    ("engine coolant temperature", "temperatura del refrigerante del motor"),
    ("intake air temperature", "temperatura del aire de admisión"),
    ("ambient air temperature", "temperatura del aire ambiente"),
    ("fuel rail pressure", "presión del riel de combustible"),
    ("fuel volume regulator", "regulador de caudal de combustible"),
    ("crankshaft position", "posición del cigüeñal"),
    ("camshaft position", "posición del árbol de levas"),
    ("accelerator pedal position", "posición del pedal del acelerador"),
    ("throttle/pedal position", "posición de mariposa/pedal"),
    ("throttle position", "posición de la mariposa"),
    ("throttle actuator control", "control del actuador de mariposa"),
    ("throttle body", "cuerpo de mariposa"),
    ("misfire detected", "fallo de encendido detectado"),
    ("cylinder misfire", "fallo de encendido en cilindro"),
    ("system too lean", "sistema demasiado pobre"),
    ("system too rich", "sistema demasiado rico"),
    ("fuel trim", "ajuste de combustible"),
    ("air fuel ratio", "relación aire/combustible"),
    ("heated oxygen sensor", "sonda lambda (calefaccionada)"),
    ("oxygen sensor", "sonda lambda"),
    ("o2 sensor", "sonda lambda"),
    ("evaporative emission", "emisión evaporativa (EVAP)"),
    ("exhaust gas recirculation", "recirculación de gases de escape (EGR)"),
    ("secondary air injection", "inyección de aire secundario"),
    ("vehicle speed sensor", "sensor de velocidad del vehículo"),
    ("vehicle speed", "velocidad del vehículo"),
    ("idle air control", "control de aire de ralentí"),
    ("idle control system", "sistema de control de ralentí"),
    ("engine oil temperature", "temperatura del aceite del motor"),
    ("engine oil pressure", "presión del aceite del motor"),
    ("turbocharger/supercharger", "turbo/compresor"),
    ("turbocharger", "turbocompresor"),
    ("boost pressure", "presión de sobrealimentación"),
    ("wastegate", "válvula de descarga (wastegate)"),
    ("knock sensor", "sensor de detonación (knock)"),
    ("ignition coil", "bobina de encendido"),
    ("glow plug", "bujía incandescente"),
    ("fuel pump", "bomba de combustible"),
    ("fuel injector", "inyector de combustible"),
    ("cooling fan", "electroventilador"),
    ("transmission control", "control de la transmisión"),
    ("torque converter", "convertidor de par"),
    ("control module", "módulo de control"),
    ("control circuit/open", "circuito de control/abierto"),
    ("control circuit", "circuito de control"),
    ("sensor circuit", "circuito del sensor"),
    ("circuit/open", "circuito/abierto"),
    ("range/performance", "rango/rendimiento"),
    ("intermittent/erratic", "intermitente/errático"),
    ("open circuit", "circuito abierto"),
    ("short to ground", "cortocircuito a masa"),
    ("short to battery", "cortocircuito a positivo"),
    ("high input", "señal alta"),
    ("low input", "señal baja"),
    ("circuit high", "circuito — señal alta"),
    ("circuit low", "circuito — señal baja"),
    ("out of range", "fuera de rango"),
    ("not plausible", "no plausible"),
    ("signal", "señal"),
    ("performance", "rendimiento"),
    # --- palabras sueltas ---
    ("circuit", "circuito"), ("sensor", "sensor"), ("control", "control"),
    ("high", "alta"), ("low", "baja"), ("bank", "banco"), ("module", "módulo"),
    ("battery", "batería"), ("position", "posición"), ("temperature", "temperatura"),
    ("pressure", "presión"), ("fuel", "combustible"), ("cylinder", "cilindro"),
    ("voltage", "tensión"), ("valve", "válvula"), ("communication", "comunicación"),
    ("system", "sistema"), ("lost", "pérdida"), ("coolant", "refrigerante"),
    ("actuator", "actuador"), ("pump", "bomba"), ("current", "corriente"),
    ("data", "datos"), ("invalid", "inválido"), ("received", "recibido"),
    ("exhaust", "escape"), ("solenoid", "solenoide"), ("stuck", "atascado"),
    ("engine", "motor"), ("transmission", "transmisión"), ("shift", "cambio"),
    ("injector", "inyector"), ("heater", "calefactor"), ("brake", "freno"),
    ("camshaft", "árbol de levas"), ("crankshaft", "cigüeñal"), ("intake", "admisión"),
    ("clutch", "embrague"), ("speed", "velocidad"), ("switch", "interruptor"),
    ("phase", "fase"), ("injection", "inyección"), ("power", "alimentación"),
    ("malfunction", "falla"), ("open", "abierto"), ("short", "cortocircuito"),
    ("ground", "masa"), ("relay", "relé"), ("motor", "motor"), ("valve", "válvula"),
    ("throttle", "mariposa"), ("pedal", "pedal"), ("catalyst", "catalizador"),
    ("misfire", "fallo de encendido"), ("lean", "pobre"), ("rich", "rico"),
    ("threshold", "umbral"), ("efficiency", "eficiencia"), ("flow", "flujo"),
    ("mass", "masa"), ("air", "aire"), ("intermittent", "intermitente"),
    ("erratic", "errático"), ("stuck open", "atascada abierta"), ("stuck closed", "atascada cerrada"),
    ("too", "demasiado"), ("detected", "detectado"), ("input", "entrada"),
    ("output", "salida"), ("circuit", "circuito"), ("with", "con"), ("from", "de"),
    ("range", "rango"), ("bank 1", "banco 1"), ("bank 2", "banco 2"),
    ("cooling", "refrigeración"), ("level", "nivel"), ("supply", "alimentación"),
    ("reference", "referencia"), ("charging", "carga"), ("charge", "carga"),
    ("timing", "sincronización"), ("advance", "avance"), ("torque", "par"),
    ("transmission", "transmisión"), ("wheel", "rueda"), ("steering", "dirección"),
    ("airbag", "airbag"), ("door", "puerta"), ("window", "ventanilla"),
    ("lamp", "luz"), ("light", "luz"), ("horn", "bocina"), ("seat", "asiento"),
    ("correlation", "correlación"), ("plausibility", "plausibilidad"),
    # --- posiciones / lados ---
    ("right front", "delantero derecho"), ("left front", "delantero izquierdo"),
    ("right rear", "trasero derecho"), ("left rear", "trasero izquierdo"),
    ("front", "delantero"), ("rear", "trasero"), ("right", "derecho"), ("left", "izquierdo"),
    ("upstream", "aguas arriba (pre-cat)"), ("downstream", "aguas abajo (post-cat)"),
    # --- estados / condiciones ---
    ("over-advanced", "muy adelantado"), ("over-retarded", "muy atrasado"),
    ("overboost condition", "condición de sobrepresión"), ("overboost", "sobrepresión"),
    ("underboost", "baja presión (underboost)"), ("biased", "desviado"),
    ("commanded", "comandado"), ("requested", "solicitado"), ("closed", "cerrado"),
    ("condition", "condición"), ("boost control", "control de sobrealimentación"),
    ("boost", "sobrealimentación"), ("deployment", "despliegue"), ("stage", "etapa"),
    ("driver", "conductor"), ("passenger", "acompañante"), ("off", "desconectado"),
    ("incorrect", "incorrecto"), ("mismatch", "no coincide"), ("failure", "falla"),
    ("excessive", "excesivo"), ("insufficient", "insuficiente"), ("slow response", "respuesta lenta"),
    ("no activity", "sin actividad"), ("inactive", "inactivo"), ("active", "activo"),
    ("regulator", "regulador"), ("thermostat", "termostato"), ("purge", "purga"),
    ("vent", "ventilación"), ("leak", "fuga"), ("small leak", "fuga pequeña"),
    ("large leak", "fuga grande"), ("gross leak", "fuga grande"),
    ("reductant", "reductor (AdBlue)"), ("particulate filter", "filtro de partículas"),
    ("glow", "incandescencia"), ("preheat", "precalentamiento"), ("water in fuel", "agua en el combustible"),
    ("engine speed", "régimen del motor"), ("output speed", "velocidad de salida"),
    ("input speed", "velocidad de entrada"), ("gear", "marcha"), ("solenoid valve", "electroválvula"),
    ("fuel rail", "riel de combustible"), ("rail", "riel"), (" or ", " o "), (" and ", " y "),
    ("column", "columna"), ("knee", "rodilla"), ("bolster", "soporte"),
    ("collapsible", "colapsable"), ("seat belt", "cinturón de seguridad"), ("buckle", "hebilla"),
    ("occupant", "ocupante"), ("restraint", "sujeción"), ("side", "lateral"),
    ("performance or incorrect operation", "rendimiento u operación incorrecta"),
    ("below threshold", "por debajo del umbral"), ("above threshold", "por encima del umbral"),
    ("below", "por debajo de"), ("above", "por encima de"), ("threshold", "umbral"),
    ("efficiency", "eficiencia"), ("particulate filter", "filtro de partículas"),
]

# Precompilar reemplazos (con límites de palabra donde tiene sentido).
_TERMINOS_COMP = [(re.compile(r"\b" + re.escape(en) + r"\b", re.I), es) for en, es in _TERMINOS]

# Códigos genéricos más comunes (verificados). No pretende ser exhaustivo:
# cubre lo que realmente aparece en un taller. Se puede ampliar.
DESCRIPCIONES = {
    # --- P00xx / P01xx: medición de aire y combustible ---
    "P0100": "Circuito del caudalímetro de aire (MAF) — falla",
    "P0101": "Caudalímetro de aire (MAF) — rango/rendimiento",
    "P0102": "Caudalímetro de aire (MAF) — señal baja",
    "P0103": "Caudalímetro de aire (MAF) — señal alta",
    "P0105": "Sensor de presión del colector (MAP) — falla",
    "P0106": "Sensor MAP — rango/rendimiento",
    "P0107": "Sensor MAP — señal baja",
    "P0108": "Sensor MAP — señal alta",
    "P0110": "Sensor de temperatura del aire de admisión (IAT) — falla",
    "P0111": "Sensor IAT — rango/rendimiento",
    "P0112": "Sensor IAT — señal baja",
    "P0113": "Sensor IAT — señal alta",
    "P0115": "Sensor de temperatura del refrigerante (ECT) — falla",
    "P0116": "Sensor ECT — rango/rendimiento",
    "P0117": "Sensor ECT — señal baja",
    "P0118": "Sensor ECT — señal alta",
    "P0120": "Sensor de posición de mariposa (TPS) — falla",
    "P0121": "Sensor TPS — rango/rendimiento",
    "P0122": "Sensor TPS — señal baja",
    "P0123": "Sensor TPS — señal alta",
    "P0125": "Temperatura insuficiente para control de combustible en lazo cerrado",
    "P0128": "Termostato — temperatura de refrigerante bajo el umbral",
    "P0130": "Sonda lambda (B1S1) — falla de circuito",
    "P0131": "Sonda lambda (B1S1) — señal baja",
    "P0132": "Sonda lambda (B1S1) — señal alta",
    "P0133": "Sonda lambda (B1S1) — respuesta lenta",
    "P0134": "Sonda lambda (B1S1) — sin actividad",
    "P0135": "Sonda lambda (B1S1) — calefactor, falla",
    "P0136": "Sonda lambda (B1S2) — falla de circuito",
    "P0137": "Sonda lambda (B1S2) — señal baja",
    "P0138": "Sonda lambda (B1S2) — señal alta",
    "P0139": "Sonda lambda (B1S2) — respuesta lenta",
    "P0140": "Sonda lambda (B1S2) — sin actividad",
    "P0141": "Sonda lambda (B1S2) — calefactor, falla",
    "P0150": "Sonda lambda (B2S1) — falla de circuito",
    "P0155": "Sonda lambda (B2S1) — calefactor, falla",
    "P0170": "Ajuste de combustible (Banco 1) — falla",
    "P0171": "Sistema demasiado pobre (Banco 1)",
    "P0172": "Sistema demasiado rico (Banco 1)",
    "P0173": "Ajuste de combustible (Banco 2) — falla",
    "P0174": "Sistema demasiado pobre (Banco 2)",
    "P0175": "Sistema demasiado rico (Banco 2)",
    "P0180": "Sensor de temperatura de combustible A — falla",
    # --- P02xx: inyectores / combustible ---
    "P0200": "Circuito de inyectores — falla",
    "P0201": "Inyector cilindro 1 — circuito",
    "P0202": "Inyector cilindro 2 — circuito",
    "P0203": "Inyector cilindro 3 — circuito",
    "P0204": "Inyector cilindro 4 — circuito",
    "P0217": "Sobretemperatura del motor",
    "P0219": "Sobrerrégimen del motor",
    "P0230": "Circuito de la bomba de combustible — falla",
    "P0261": "Inyector cilindro 1 — señal baja",
    "P0299": "Turbo/supercargador — baja presión (underboost)",
    # --- P03xx: encendido / fallo de combustión (misfire) ---
    "P0300": "Fallo de encendido múltiple/aleatorio detectado",
    "P0301": "Fallo de encendido — cilindro 1",
    "P0302": "Fallo de encendido — cilindro 2",
    "P0303": "Fallo de encendido — cilindro 3",
    "P0304": "Fallo de encendido — cilindro 4",
    "P0305": "Fallo de encendido — cilindro 5",
    "P0306": "Fallo de encendido — cilindro 6",
    "P0313": "Fallo de encendido con bajo nivel de combustible",
    "P0325": "Sensor de detonación (knock) 1 — circuito",
    "P0327": "Sensor de detonación 1 — señal baja",
    "P0335": "Sensor de posición del cigüeñal (CKP) — circuito",
    "P0336": "Sensor CKP — rango/rendimiento",
    "P0340": "Sensor de posición del árbol de levas (CMP) — circuito",
    "P0341": "Sensor CMP — rango/rendimiento",
    # --- P04xx: control de emisiones (EGR, catalizador, EVAP, aire secundario) ---
    "P0401": "EGR — flujo insuficiente",
    "P0402": "EGR — flujo excesivo",
    "P0403": "EGR — circuito de control",
    "P0420": "Eficiencia del catalizador bajo el umbral (Banco 1)",
    "P0421": "Eficiencia del catalizador de arranque (Banco 1)",
    "P0430": "Eficiencia del catalizador bajo el umbral (Banco 2)",
    "P0440": "Sistema EVAP (evaporativo) — falla general",
    "P0441": "Sistema EVAP — flujo de purga incorrecto",
    "P0442": "Sistema EVAP — fuga pequeña detectada",
    "P0443": "Válvula de purga EVAP — circuito",
    "P0446": "Sistema EVAP — circuito de ventilación",
    "P0455": "Sistema EVAP — fuga grande detectada (tapa de nafta?)",
    "P0456": "Sistema EVAP — fuga muy pequeña",
    "P0480": "Relé del electroventilador 1 — circuito",
    # --- P05xx: velocidad, ralentí, entradas auxiliares ---
    "P0500": "Sensor de velocidad del vehículo (VSS) — falla",
    "P0501": "Sensor de velocidad — rango/rendimiento",
    "P0505": "Sistema de control de ralentí (IAC) — falla",
    "P0506": "Ralentí más bajo de lo esperado",
    "P0507": "Ralentí más alto de lo esperado",
    "P0562": "Tensión del sistema baja",
    "P0563": "Tensión del sistema alta",
    "P0571": "Interruptor del pedal de freno A — circuito",
    # --- P06xx: computadora y salidas ---
    "P0600": "Enlace de comunicación serie — falla",
    "P0601": "Módulo de control (ECU) — error de memoria interna",
    "P0603": "Módulo de control — error de memoria KAM",
    "P0605": "Módulo de control — error de memoria ROM",
    "P0606": "Módulo de control (ECU/PCM) — falla de procesador",
    # --- P07xx: transmisión ---
    "P0700": "Sistema de control de la transmisión — falla",
    "P0705": "Sensor de rango de la transmisión — circuito",
    "P0715": "Sensor de velocidad de entrada/turbina — circuito",
    "P0720": "Sensor de velocidad de salida — circuito",
    "P0730": "Relación de cambios incorrecta",
    "P0740": "Embrague del convertidor — circuito",
    # --- U0xxx: comunicación de red (CAN) ---
    "U0001": "Bus CAN de alta velocidad — falla",
    "U0100": "Pérdida de comunicación con la ECU del motor (ECM/PCM)",
    "U0101": "Pérdida de comunicación con la ECU de la transmisión",
    "U0121": "Pérdida de comunicación con la ECU del ABS",
    "U0140": "Pérdida de comunicación con la caja de conexiones (BCM)",
    "U0155": "Pérdida de comunicación con el tablero (cuadro de instrumentos)",
    "U0164": "Pérdida de comunicación con el módulo de climatización",
}

# Familias: si no hay match exacto, se describe el grupo (los códigos comparten tema).
_FAMILIAS = {
    "P030": "Fallo de encendido / combustión (misfire)",
    "P013": "Sonda lambda / sensor de oxígeno (Banco 1)",
    "P015": "Sonda lambda / sensor de oxígeno (Banco 2)",
    "P017": "Ajuste de mezcla de combustible (rico/pobre)",
    "P02":  "Circuito de inyectores / combustible",
    "P010": "Medición de aire de admisión (MAF/MAP/IAT)",
    "P011": "Sensores de temperatura / mariposa",
    "P012": "Sensor de mariposa / pedal",
    "P040": "Control de emisiones (EGR / catalizador)",
    "P044": "Sistema evaporativo (EVAP)",
    "P045": "Sistema evaporativo (EVAP) — fugas",
    "P07":  "Transmisión automática",
    "P06":  "Módulo de control / salidas de la ECU",
    "U01":  "Comunicación de red (CAN) con un módulo",
}

_LETRAS = {
    "P": "Falla del tren motriz (motor/transmisión)",
    "C": "Falla del chasis (frenos/ABS/dirección/suspensión)",
    "B": "Falla de carrocería (confort/seguridad/airbag)",
    "U": "Falla de red/comunicación entre módulos",
}


@lru_cache(maxsize=4096)
def _traducir(en):
    """Traduce una descripción DTC del inglés al español por términos."""
    t = " " + en.strip() + " "
    for rx, es in _TERMINOS_COMP:
        t = rx.sub(es, t)
    t = t.strip()
    return t[:1].upper() + t[1:] if t else en


def describir(codigo):
    """Descripción en español de un DTC. Nunca devuelve vacío."""
    if not codigo:
        return "Código de falla desconocido"
    c = str(codigo).strip().upper()
    # 1) curados a mano (español perfecto, los de taller)
    if c in DESCRIPCIONES:
        return DESCRIPCIONES[c]
    # 2) base completa (~9400) traducida por términos
    en = _GENERICO_EN.get(c)
    if en:
        return _traducir(en)
    # 3) fallback por familia (prefijos más largos primero)
    for pref in sorted(_FAMILIAS, key=len, reverse=True):
        if c.startswith(pref):
            return _FAMILIAS[pref] + f" (código {c})"
    return _LETRAS.get(c[:1], "Código de falla") + f" (código {c})"


def es_conocido(codigo):
    """True si el código está en la base curada o en la genérica (no es solo fallback)."""
    c = str(codigo or "").strip().upper()
    return c in DESCRIPCIONES or c in _GENERICO_EN
