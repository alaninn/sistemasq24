# -*- coding: utf-8 -*-
"""Descripciones de códigos de falla (DTC) genéricos OBD-II, en español.

Curado a mano a partir de la norma SAE J2012 (los códigos genéricos P0/C0/B0/U0
más comunes). Se usa para explicar los DTC que lee el scanner cuando la ECU no
trae su propia descripción (sobre todo en el modo OBD-II genérico).

`describir(codigo)` devuelve la descripción: match exacto → fallback por familia
→ genérico por letra. Nunca falla; si no lo conoce, describe la categoría.
"""

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


def describir(codigo):
    """Descripción en español de un DTC. Nunca devuelve vacío."""
    if not codigo:
        return "Código de falla desconocido"
    c = str(codigo).strip().upper()
    if c in DESCRIPCIONES:
        return DESCRIPCIONES[c]
    # fallback por familia (prefijos más largos primero)
    for pref in sorted(_FAMILIAS, key=len, reverse=True):
        if c.startswith(pref):
            return _FAMILIAS[pref] + f" (código {c})"
    return _LETRAS.get(c[:1], "Código de falla") + f" (código {c})"
