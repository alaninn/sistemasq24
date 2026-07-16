# DTC Database — Qué revisar por código

## Sistema de clasificación

- **P0xxx**: Powertrain (Motor/Transmisión) — MÁS COMÚN
- **C0xxx**: Chassis (Frenos/Suspensión/ABS)
- **B0xxx**: Body (Carrocería/Luces/Clima)
- **U0xxx**: Network (Comunicación entre ECUs)

---

## CÓDIGOS FRECUENTES — Mégane II F4R

### **COMBUSTIBLE & INYECCIÓN**

| Código | Descripción | Qué revisar |
|--------|-------------|------------|
| **P0001** | Fuel Pump Control Circuit Open | Bomba de nafta sin respuesta. Revisar: cable bomba, conectores, relé |
| **P0010-P0013** | Camshaft Position Actuator Circuit | VVT (Variable Valve Timing) defectuoso. Revisar: aceite, filtro, sensor posición |
| **P0030-P0036** | O2 Sensor Heater Circuit | Sonda lambda sin calefacción. Revisar: conectores, fusible, elemento calefacción |
| **P0101** | Mass or Volume Air Flow | MAF/MAP fuera de rango. Revisar: sensor limpio, conexiones, intakes |
| **P0102** | Mass Air Flow Below Normal | Flujo aire bajo. Revisar: filtro aire, fugas admisión |
| **P0103** | Mass Air Flow Above Normal | Flujo aire alto. Revisar: rotura en tuberías, MAF sucio |
| **P0111** | Intake Air Temperature | Sensor temperatura aire defectuoso. Revisar: conector IAT |
| **P0115** | Engine Coolant Temperature | Sensor temperatura agua fuera rango. Revisar: sensor ECT, conectores |
| **P0130** | O2 Sensor Circuit | Sonda lambda sin respuesta. Revisar: cable, conector, elemento sensor |
| **P0131-P0141** | O2 Sensor Upstream/Downstream | Sonda amont/aval defectuosa. Revisar: elemento sensor, conectores |
| **P0300** | Random Misfire | Fallos encendido aleatorios. Revisar: bujías, cables, bobinas, inyectores, compresión |
| **P0301-P0308** | Cylinder [1-8] Misfire | Fallo encendido cilindro específico. Revisar: bujía ese cilindro, inyector, bobina |
| **P0335** | Crankshaft Position Sensor | Sensor posición cigüeñal defectuoso. Revisar: sensor, conector, entrehierro |
| **P0400** | Exhaust Gas Recirculation | Válvula EGR no responde. Revisar: válvula, solenoide, conectores |
| **P0455** | Evaporative Emission System Leak | Fuga sistema evaporación (EVAP). Revisar: tuberías, canister, válvula carbón |
| **P0500** | Vehicle Speed Sensor | Sensor velocidad defectuoso. Revisar: sensor rueda, conectores, ajustes |
| **P0530** | A/C Refrigerant Pressure Sensor | Sensor presión A/C defectuoso. Revisar: sensor, conectores, presión refrigerante |

---

### **ENCENDIDO & ELECTRICIDAD**

| Código | Descripción | Qué revisar |
|--------|-------------|------------|
| **P0300-P0308** | Misfire Detected | Fallos encendido. Revisar: bujías (edad), cables, bobinas, compresión cilindros |
| **P0420** | Catalyst System Efficiency Below Threshold | Catalizador deficiente. Revisar: integridad catalizador, sensores O2 |
| **P0500** | Vehicle Speed Sensor Malfunction | Velocidad no se lee. Revisar: sensor ABS ruedas, conectores |
| **P0601** | Internal Control Module Memory | Memoria ECU corrupta. Revisar: conexión batería, cortes de energía recientes |
| **P0650** | Malfunction Indicator Lamp | Luz Check Engine encendida. Revisar: si hay DTCs más específicos |
| **P0700** | Transmission Control System Malfunction | Caja de cambios sin comunicación. Revisar: conectores, TCU |

---

### **ABS & SEGURIDAD (Códigos C0xxx)**

| Código | Descripción | Qué revisar |
|--------|-------------|------------|
| **C0035** | ABS Wheel Speed Sensor Circuit | Sensor velocidad rueda ABS. Revisar: sensor, conector, entrehierro |
| **C0040-C0093** | ABS Sensor [wheel] Malfunction | Sensor ABS rueda específica defectuoso. Revisar: sensor, cable, conector |
| **C0121** | Invalid ABS Sensor Signal | Señal sensor ABS incoherente. Revisar: suciedad sensor, corrosión conector |
| **C1262** | Solenoid Valve Defect | Válvula solenoide ABS defectuosa. Revisar: válvula, conectores, presión |

---

### **COMUNICACIÓN (Códigos U0xxx)**

| Código | Descripción | Qué revisar |
|--------|-------------|------------|
| **U0100** | Lost Communication With ECM | Pérdida comunicación motor. Revisar: batería voltaje, conectores ECU |
| **U0111** | Communication Between Modules | Fallo comunicación entre módulos (ej. UCH). Revisar: conectores CAN, aislamiento cables |
| **U0128** | Communication Error | Error general comunicación red. Revisar: CAN bus, conectores, terminales |

---

### **CARROCERÍA (Códigos B0xxx)**

| Código | Descripción | Qué revisar |
|--------|-------------|------------|
| **B0082** | Lamp Defect | Luz defectuosa. Revisar: bombilla, conector, fusible |
| **B1001-B1099** | Body Electronics | Problemas carrocería/clima. Revisar: switches, motores, sensores específicos |

---

## WORKFLOW: Qué hacer cuando aparece un DTC

### **Paso 1: Leer código exacto**
- Anota formato (ej. P0530)
- Ej. `P` = Powertrain (motor)
- Ej. `05` = Combustible  
- Ej. `30` = Sensor presión

### **Paso 2: Revisar tabla arriba**
- Busca el código en esta tabla
- Lee qué revisar
- Prioriza cables/conectores (80% de problemas)

### **Paso 3: Chequear sensores en vivo**
- Abre Tablero
- Busca sensores relacionados
- ¿Están en rango? ¿Oscilan? ¿Congelados?
- Ej. P0530 → busca "Presión A/C" en sensores

### **Paso 4: Test físico**
- Desconecta conector del sensor reportado
- Debería causar otro DTC (pérdida comunicación)
- Si no hay DTC al desconectar → sensor está muerto

### **Paso 5: Borrar DTC**
- Una vez arreglado
- Botón "Borrar todos códigos" (modo avanzado)
- Haz una prueba de manejo
- Verifica que no reaparece

---

## Códigos "Fantasmas" Comunes

| Código | Razón | Solución |
|--------|-------|----------|
| P0128 | Termostat malfunction (casi nunca es true) | 90% es sensor temperatura. Revisar ECT sensor |
| U0100 | Lost ECM (a veces falsa alarma) | Revisar voltaje batería y conectores |
| P0300 | Random misfire (muy genérico) | Revisar compresión cilindros primero |

---

## Patrón de lectura

Cuando lees un código tipo **P0530**:
- **P** = Powertrain (motor/caja)
- **0** = Código genérico SAE
- **5** = Combustible & Aire
- **30** = Sensor Presión A/C

Así sabes dónde buscar sin memorizar todos los códigos.

---

## Notas importantes

✓ Algunos DTCs son FALSOS (intermitentes)  
✓ Los conectores sueltos causan 80% de DTCs  
✓ Un DTC NO significa que ese componente falló — puede ser sensor, cable, ECU  
✓ Siempre revisa sensores en vivo PRIMERO antes de cambiar piezas  
✓ Los DTCs se borran tras 40-80 ciclos de encendido si no reaparece el problema  
