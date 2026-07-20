# -*- coding: utf-8 -*-
"""Backend local del scanner Mégane II F4R.

FastAPI + WebSocket. Reutiliza el motor de comunicación de ddt4all (core/elm,
core/ecu). Sirve el frontend web y expone:
  - lista de ECUs y sus pantallas/parámetros (ya en español)
  - conexión al adaptador ELM327 (o modo simulación sin auto)
  - lectura en vivo por WebSocket
  - envío de comandos con gate de 'modo peligroso' (options.promode)
"""
import asyncio
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

# Permitir 'import sistemasq24' de forma autocontenida.
# El core (base tomada de ddt4all, ya rebrandeada a sistemasq24) va empaquetado en
# megane2_f4r/vendor/sistemasq24 para que el proyecto sea portable copiando la carpeta.
for _cand in [
    APP_DIR.parent / "vendor",                        # megane2_f4r/vendor  (empaquetado)
    APP_DIR.parent.parent / "sistemasq24" / "src",    # dev: al lado
    APP_DIR.parent / "sistemasq24" / "src",
]:
    if (_cand / "sistemasq24" / "__init__.py").exists():
        sys.path.insert(0, str(_cand))
        break

import sistemasq24.options as options
import ecu_registry as registry_mod
from session_logger import logger as slog
from sq24_scanner import get_scanner

WEB_DIR = APP_DIR / "web"

# Constantes de validación (prevenir DoS)
MAX_PAYLOAD_SIZE = 10_000  # 10KB máximo por request
MAX_STRING_LENGTH = 1_000  # Máximo para strings de input
MAX_RETRY_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 120

app = FastAPI(title="Scanner Mégane II F4R")

# ----------------------------------------------------------------------------
# Estado de conexión (global, un solo auto a la vez)
# ----------------------------------------------------------------------------
class Estado:
    def __init__(self):
        self.conectado = False
        self.modo = "desconectado"       # "simulacion" | "real" | "desconectado"
        self.puerto = None
        self.ecu_activa = None           # id de ECU cuyo direccionamiento está cargado
        self.registro = registry_mod.get_registry()
        self.ultima_actividad = 0.0      # timestamp del último comando al ELM
        self.ultimo_log_sensores = 0.0   # throttle para loguear sensores en vivo
        self.captura_automatica = False  # flag global: capturar pantallas automáticamente
        self.csrf_token = str(uuid.uuid4())  # token CSRF para POST peligrosos
        self.vehiculo_seleccionado = None  # id del vehículo seleccionado (ej: "megane_ii")
        # progreso de la autodetección (para mostrar barra + dirección en curso)
        self.deteccion = {"corriendo": False, "actual": 0, "total": 0,
                          "addr": "", "n": 0, "terminado": False, "resultado": None}
        # actuadores encendidos: {"ecu|id": {"ecu","id"}}. Se re-envían periódicamente
        # (keep-alive) porque el "Start Temporary" del servicio 30 expira solo.
        self.actuadores_activos = {}
        # estado del chequeo general (progreso por polling, igual que la detección)
        self.chequeo = {"corriendo": False, "fase": "", "rpm_objetivo": 0, "rpm_actual": None,
                        "progreso": 0, "instruccion": "", "timeout": False,
                        "terminado": False, "resultado": None, "error": None}
        self.chequeo_cancelar = False    # flag para abortar el chequeo
        self.chequeo_capturar = False    # flag "capturar ahora" (fallback manual)
        # estado del ensayo de aceleración (motor en movimiento, ~50/100 m)
        self.ensayo = {"corriendo": False, "fase": "", "vel_actual": None, "rpm_actual": None,
                       "distancia": 0, "progreso": 0, "instruccion": "", "timeout": False,
                       "terminado": False, "resultado": None, "error": None}
        self.ensayo_cancelar = False     # flag para abortar el ensayo
        self.ensayo_ahora = False        # flag "ahora" (forzar arranque o fin del tramo)

    @property
    def modo_peligroso(self):
        return options.promode

estado = Estado()

# Locks para serializar acceso concurrente
# El puerto serie del ELM327 acepta UN comando a la vez. Este lock serializa TODO
# acceso al adaptador para que las lecturas en vivo (WebSocket) y los comandos
# (HTTP: actuadores, DTC, etc.) no se pisen y corrompan el framing ISO-TP.
ELM_LOCK = threading.RLock()
# Lock para proteger el objeto `estado` global (conectado, ecu_activa, etc.)
ESTADO_LOCK = threading.RLock()
# Pool de threads limitado para operaciones async (máximo 10 concurrent)
THREAD_POOL = ThreadPoolExecutor(max_workers=10, thread_name_prefix="scanner_")


def _marcar_actividad():
    estado.ultima_actividad = time.time()


def _read_with_retry(tecu, request, inputs, max_retries=3):
    """Lee un request con reintentos automáticos (backoff exponencial)."""
    backoff_ms = [100, 200, 400]  # ms entre reintentos
    last_error = None
    for attempt in range(max_retries):
        try:
            return tecu.read_request(request, inputs)
        except (TimeoutError, ConnectionError, OSError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = backoff_ms[min(attempt, len(backoff_ms)-1)] / 1000.0
                slog.log("RETRY", f"Reintentando {request} (intento {attempt+1}/{max_retries})", {})
                time.sleep(wait_time)
            continue
        except Exception as e:
            # No reintentar excepciones no-transitorias
            raise
    # Falló en todos los reintentos
    raise last_error or Exception(f"Error desconocido tras {max_retries} reintentos")


# ----------------------------------------------------------------------------
# Conexión al hardware
# ----------------------------------------------------------------------------
def _conectar_simulacion():
    """Conecta al modo simulación (sin hardware ELM327). Útil para testing."""
    options.simulation_mode = True
    options.elm = None
    with ESTADO_LOCK:
        estado.conectado = True
        estado.modo = "simulacion"
        estado.puerto = None
        estado.ecu_activa = None
    return {"ok": True, "modo": "simulacion"}


def _conectar_real(puerto, velocidad, adaptador):
    """Conecta al adaptador OBD-II real (ELM327, VLinker, etc).

    Args:
        puerto: puerto serie (ej: COM3, /dev/ttyUSB0)
        velocidad: baudrate (típicamente 38400)
        adaptador: tipo de adaptador (ELM327, STPX, VGate, etc)

    Returns:
        dict con {ok: bool, modo: str, puerto: str} o {ok: False, error: str}
    """
    from sistemasq24.core.elm.elm import ELM
    # Validar inputs antes de usarlos
    if not puerto or not str(puerto).strip():
        return {"ok": False, "error": "Puerto debe especificarse"}
    try:
        velocidad = int(velocidad)
        if velocidad <= 0:
            return {"ok": False, "error": "Velocidad debe ser positiva"}
    except (ValueError, TypeError):
        return {"ok": False, "error": "Velocidad debe ser un número"}

    options.simulation_mode = False
    try:
        options.elm = ELM(puerto, velocidad, adaptador)
    except Exception as e:
        options.elm = None
        with ESTADO_LOCK:
            estado.conectado = False
            estado.modo = "desconectado"
        slog.log("CONEXION", f"Error conectando: {e}", {})
        return {"ok": False, "error": f"No se pudo abrir el adaptador: {e}"}

    try:
        if not options.elm.connectionStat():
            options.elm = None
            with ESTADO_LOCK:
                estado.conectado = False
                estado.modo = "desconectado"
            return {"ok": False, "error": "El adaptador no respondió. Revisá el cable/puerto."}
    except Exception as e:
        options.elm = None
        with ESTADO_LOCK:
            estado.conectado = False
            estado.modo = "desconectado"
        slog.log("CONEXION", f"Error verificando conexión: {e}", {})
        return {"ok": False, "error": f"Error verificando conexión: {e}"}

    with ESTADO_LOCK:
        estado.conectado = True
        estado.modo = "real"
        estado.puerto = puerto
        estado.ecu_activa = None
    _enganchar_log_elm()
    slog.log("CONEXION", "Conectado al auto (real)", {"puerto": puerto, "velocidad": velocidad, "adaptador": adaptador})
    return {"ok": True, "modo": "real", "puerto": puerto}


def _enganchar_log_elm():
    """Envuelve request() para grabar TODA la comunicación con detalle (como DDT4All).

    Engancha `request()` (usado por ecu_request.py) para capturar comandos del adaptador
    con su tiempo de respuesta.
    """
    if options.elm is None or getattr(options.elm, "_log_enganchado", False):
        return
    if hasattr(options.elm, "request"):
        orig_req = options.elm.request
        def logged_req(command, *a, **kw):
            t0 = time.time()
            resp = orig_req(command, *a, **kw)
            ms = round((time.time() - t0) * 1000, 1)
            try:
                slog.log_raw(str(command), str(resp), ms)
            except Exception as e:
                slog.log("LOG_ELM", f"Error loguando respuesta: {e}", {})
            return resp
        options.elm.request = logged_req
    options.elm._log_enganchado = True


def _seleccionar_ecu(ecu_id):
    """Carga el direccionamiento CAN de una ECU en el adaptador (o nada en sim)."""
    tecu = estado.registro.get(ecu_id)
    if tecu is None:
        return False
    if estado.ecu_activa == ecu_id:
        return True
    slog.log("ECU", "Acceso a módulo", {"ecu": ecu_id, "nombre": tecu.short_name,
                                          "tx": tecu.ecu.ecu_send_id, "rx": tecu.ecu.ecu_recv_id})
    ecu = tecu.ecu
    if not options.simulation_mode and options.elm is not None:
        # Limpiar caché ANTES de cambiar dirección CAN
        try:
            options.elm.clear_cache()
        except Exception as e:
            slog.log("CLEAR_CACHE", f"Error limpiando caché: {e}", {})
        # Conexión CAN directa usando los IDs Tx/Rx del propio archivo de ECU,
        # sin depender de las tablas de direccionamiento globales.
        ecu_conf = {
            "idTx": ecu.ecu_send_id,
            "idRx": ecu.ecu_recv_id,
            "ecuname": ecu.ecuname,
            "protocol": ecu.ecu_protocol,
        }
        proto = ecu.ecu_protocol.upper()
        if proto == "CAN":
            options.elm.init_can()
            options.elm.set_can_addr(ecu.ecu_send_id, ecu_conf, 0)
            # Limpiar caché DESPUÉS de cambiar dirección (set_can_addr resetea todo)
            try:
                options.elm.clear_cache()
            except Exception:
                pass
        else:
            ecu.connect_to_hardware(0)
        # La sesión de diagnóstico (10C0) la abre el propio registro antes de cada
        # lectura (tecu.ensure_session), con reintento si la respuesta viene vacía.
        # set_can_addr resetea elm.startSession, así que la próxima lectura la reabre.
    estado.ecu_activa = ecu_id
    return True


def _puertos_disponibles():
    try:
        from sistemasq24.core.elm.elm import get_available_ports
        ports = get_available_ports()
        out = []
        for p in ports:
            if isinstance(p, (list, tuple)):
                out.append({"puerto": p[0], "descripcion": p[1] if len(p) > 1 else p[0]})
            else:
                out.append({"puerto": str(p), "descripcion": str(p)})
        return out
    except Exception as e:
        return [{"puerto": "", "descripcion": f"(no se pudieron listar puertos: {e})"}]


def _rango_compatibilidad(desc):
    """Estima qué tan compatible es un adaptador según su descripción, sin conectarse."""
    d = (desc or "").upper()
    # adaptadores probados y recomendados por DDT4All
    if any(k in d for k in ["ELM327", "OBDLINK", "VLINKER", "VGATE", "ICAR", "ELS27"]):
        return ("alta", "Adaptador reconocido y recomendado para este auto.")
    if any(k in d for k in ["FTDI", "FT232", "CP210", "CH340", "CH341", "PL2303"]):
        return ("media", "Chip típico de clones ELM327. Suele andar; probalo con el test.")
    if any(k in d for k in ["OBD", "SCANTOOL", "DIAG"]):
        return ("media", "Parece un adaptador OBD. Conviene probarlo con el test.")
    return ("desconocida", "No se pudo identificar el tipo. Probá el test para confirmar.")


def _puertos_disponibles_detallado():
    out = []
    for p in _puertos_disponibles():
        rango, nota = _rango_compatibilidad(p.get("descripcion", ""))
        out.append({**p, "compatibilidad": rango, "nota": nota})
    return out


def _test_adaptador(puerto, adaptador):
    """Abre el adaptador y corre una batería de comandos AT para medir compatibilidad."""
    from sistemasq24.core.elm.elm import ELM
    from sistemasq24.core.elm.device_manager import DeviceManager
    settings = DeviceManager.get_optimal_settings(adaptador)
    velocidad = settings.get("baudrate", 38400)

    pruebas = []
    def prueba(nombre, ok, detalle=""):
        pruebas.append({"nombre": nombre, "ok": bool(ok), "detalle": detalle})

    prev_sim = options.simulation_mode
    options.simulation_mode = False
    elm = None
    try:
        try:
            elm = ELM(puerto, velocidad, adaptador)
        except Exception as e:
            options.simulation_mode = prev_sim
            return {"ok": False, "error": f"No se pudo abrir el puerto {puerto}: {e}",
                    "puerto": puerto, "velocidad": velocidad, "pruebas": []}

        if not elm.connectionStat():
            prueba("Conexión al puerto", False, "El adaptador no respondió")
            return _resultado_test(puerto, velocidad, adaptador, pruebas, None)
        prueba("Conexión al puerto", True, f"Abierto a {velocidad} baudios")

        # ATZ: reinicio, debería devolver "ELM327 vX.X"
        version = None
        try:
            rz = elm.send_raw("ATZ") or ""
            es_elm = "ELM" in rz.upper()
            prueba("Reinicio (ATZ)", es_elm, rz.strip()[:40] or "sin respuesta")
        except Exception as e:
            prueba("Reinicio (ATZ)", False, str(e))
        # ATI: versión
        try:
            ri = elm.send_raw("ATI") or ""
            version = ri.strip()
            prueba("Versión (ATI)", "ELM" in ri.upper() or bool(ri.strip()), version[:40])
        except Exception as e:
            prueba("Versión (ATI)", False, str(e))
        # ATRV: voltaje de batería (confirma que lee el auto)
        try:
            rv = elm.send_raw("ATRV") or ""
            tiene_v = "V" in rv.upper()
            prueba("Lectura de voltaje (ATRV)", tiene_v, rv.strip()[:20])
        except Exception as e:
            prueba("Lectura de voltaje (ATRV)", False, str(e))
        # ATE0: eco off (comando básico)
        try:
            re0 = elm.send_raw("ATE0") or ""
            prueba("Comando básico (ATE0)", "OK" in re0.upper(), re0.strip()[:20])
        except Exception as e:
            prueba("Comando básico (ATE0)", False, str(e))

        return _resultado_test(puerto, velocidad, adaptador, pruebas, version)
    finally:
        if elm is not None:
            try:
                elm.__del__()
            except Exception:
                pass
        options.simulation_mode = prev_sim


def _resultado_test(puerto, velocidad, adaptador, pruebas, version):
    total = len(pruebas)
    ok = sum(1 for p in pruebas if p["ok"])
    pct = int(round(100 * ok / total)) if total else 0
    if pct >= 80:
        verdicto = "compatible"
        mensaje = "✅ El adaptador funciona bien y es compatible con tu auto."
    elif pct >= 50:
        verdicto = "parcial"
        mensaje = "⚠️ El adaptador responde pero falló en algunas pruebas. Puede andar con limitaciones."
    else:
        verdicto = "incompatible"
        mensaje = "❌ El adaptador casi no respondió. Revisá el cable, el puerto o probá otro adaptador."
    return {
        "ok": True, "puerto": puerto, "velocidad": velocidad, "adaptador": adaptador,
        "version": version, "pruebas": pruebas, "puntaje": pct,
        "verdicto": verdicto, "mensaje": mensaje,
    }


# ----------------------------------------------------------------------------
# Modelos de request
# ----------------------------------------------------------------------------
class ConexionReq(BaseModel):
    modo: str = "simulacion"          # "simulacion" | "real"
    puerto: str = ""
    velocidad: int = 38400
    adaptador: str = "ELM327"


class PeligroReq(BaseModel):
    activar: bool


class ComandoReq(BaseModel):
    ecu: str
    request: str
    inputs: dict = {}

    @validator('ecu')
    def validate_ecu(cls, v):
        if not v or len(v) > MAX_STRING_LENGTH:
            raise ValueError(f"ECU ID inválido (máx {MAX_STRING_LENGTH} caracteres)")
        return v.strip()

    @validator('request')
    def validate_request(cls, v):
        if not v or len(v) > MAX_STRING_LENGTH:
            raise ValueError(f"Request inválido (máx {MAX_STRING_LENGTH} caracteres)")
        return v.strip()

    @validator('inputs')
    def validate_inputs(cls, v):
        if len(str(v)) > MAX_PAYLOAD_SIZE:
            raise ValueError(f"Payload muy grande (máx {MAX_PAYLOAD_SIZE} bytes)")
        return v


# ----------------------------------------------------------------------------
# Rutas REST
# ----------------------------------------------------------------------------
@app.post("/api/grabar/iniciar")
def api_grabar_iniciar():
    """Empieza a grabar todo lo que pasa en la sesión de diagnóstico."""
    r = slog.start({"modo": estado.modo, "puerto": estado.puerto, "conectado": estado.conectado})
    # si ya estamos conectados en real, enganchar el log del ELM ahora
    if estado.modo == "real":
        _enganchar_log_elm()
    return r


@app.post("/api/grabar/detener")
def api_grabar_detener():
    """Detiene la grabación y guarda los archivos en la carpeta log/."""
    return slog.stop()


@app.get("/api/grabar/estado")
def api_grabar_estado():
    return slog.estado()


GITHUB_REPO = "alaninn/sistemasq24"   # owner/repo para la API de subida de logs


def _github_token():
    """Token de GitHub para subir logs por API: de github_token.txt o env GITHUB_TOKEN."""
    import os
    tf = APP_DIR.parent / "github_token.txt"
    if tf.exists():
        t = tf.read_text(encoding="utf-8").strip()
        if t:
            return t
    return os.environ.get("GITHUB_TOKEN", "").strip() or None


@app.post("/api/logs/subir")
def api_logs_subir():
    """(TEMPORAL — solo para debug) Sube los logs a GitHub (carpeta debug-logs/) para
    revisarlos desde otra máquina. Usa la API de GitHub con token (funciona sin git ni
    .git, ideal para la notebook); si no hay token, cae al git CLI (esta PC).
    Ver CLAUDE.md ('flujo de logs')."""
    import base64
    import json as _json
    import urllib.request
    from datetime import datetime as _dt
    # Volcar la sesión actual si está grabando, para no perder los últimos eventos.
    try:
        if slog.activo:
            slog._guardar()
    except Exception:
        pass
    repo = APP_DIR.parent
    log_dir = repo / "log"
    # Sube logs de sesión + consola + los reportes del chequeo general y del ensayo.
    txts = []
    if log_dir.exists():
        txts = (sorted(log_dir.glob("sesion_*.txt")) + sorted(log_dir.glob("consola_*.txt"))
                + sorted(log_dir.glob("reporte_*.json")) + sorted(log_dir.glob("reporte_*.txt"))
                + sorted(log_dir.glob("reporte_*.html"))
                + sorted(log_dir.glob("ensayo_*.json")) + sorted(log_dir.glob("ensayo_*.txt"))
                + sorted(log_dir.glob("ensayo_*.html")))
    if not txts:
        return {"ok": False, "error": "Todavía no hay logs ni reportes para subir."}

    token = _github_token()
    if token:
        # --- Subida por API de GitHub (Contents API) — no necesita git ---
        subidos, errores = [], []
        for f in txts:
            try:
                contenido = base64.b64encode(f.read_bytes()).decode("ascii")
                url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/debug-logs/{f.name}"
                # ¿ya existe? (para actualizar necesita el sha)
                sha = None
                try:
                    req = urllib.request.Request(url, headers={
                        "Authorization": f"token {token}",
                        "Accept": "application/vnd.github+json", "User-Agent": "sq24"})
                    sha = _json.load(urllib.request.urlopen(req)).get("sha")
                except Exception:
                    sha = None
                body = {"message": "log " + f.name, "content": contenido, "branch": "main"}
                if sha:
                    body["sha"] = sha
                req = urllib.request.Request(url, method="PUT",
                    data=_json.dumps(body).encode("utf-8"),
                    headers={"Authorization": f"token {token}",
                             "Accept": "application/vnd.github+json",
                             "Content-Type": "application/json", "User-Agent": "sq24"})
                urllib.request.urlopen(req, timeout=60)
                subidos.append(f.name)
            except Exception as e:
                errores.append(f"{f.name}: {e}")
        if subidos:
            msg = f"{len(subidos)} log(s) subidos a GitHub (debug-logs/)."
            if errores:
                msg += f" ({len(errores)} fallaron)"
            return {"ok": True, "archivos": subidos, "mensaje": msg, "errores": errores}
        return {"ok": False, "error": "No se pudo subir por la API: " + "; ".join(errores)[:400]}

    # --- Fallback: git CLI (solo si esta máquina tiene el repo clonado + credenciales) ---
    import subprocess
    import shutil
    dest = repo / "debug-logs"
    dest.mkdir(exist_ok=True)
    copiados = []
    for f in txts + (list(log_dir.glob("sesion_*.json")) if log_dir.exists() else []):
        try:
            shutil.copy2(f, dest / f.name); copiados.append(f.name)
        except Exception:
            pass

    def git(*a):
        return subprocess.run(["git", *a], cwd=str(repo), capture_output=True, text=True, timeout=180)
    try:
        git("add", "debug-logs")
        git("commit", "-m", "logs de prueba " + _dt.now().strftime("%Y-%m-%d %H:%M"))
        push = git("push", "origin", "main")
        if push.returncode != 0:
            return {"ok": False, "archivos": copiados,
                    "error": "No hay token de GitHub y el git push falló (¿la notebook no "
                             "tiene el repo clonado ni credenciales?). Poné un token en "
                             "github_token.txt. Detalle: " + (push.stderr or push.stdout or "").strip()[:300]}
    except FileNotFoundError:
        return {"ok": False, "falta_token": True,
                "error": "Esta máquina no tiene token de GitHub ni git instalado. "
                         "Pegá un token acá (se guarda para las próximas veces) o bajá "
                         "los logs en un ZIP y mandámelos por otra vía."}
    except Exception as e:
        return {"ok": False, "error": f"Error subiendo logs: {e}"}
    return {"ok": True, "archivos": copiados, "mensaje": f"{len(copiados)} log(s) subidos a GitHub."}


class TokenReq(BaseModel):
    token: str


@app.get("/api/logs/token-estado")
def api_logs_token_estado():
    """¿Esta máquina tiene token de GitHub guardado?"""
    return {"tiene_token": bool(_github_token())}


@app.post("/api/logs/token")
def api_logs_token(req: TokenReq):
    """Guarda el token de GitHub en github_token.txt (gitignoreado) desde la interfaz, así
    la notebook no necesita crear archivos a mano ni tener git instalado. Valida el token
    contra la API antes de guardarlo."""
    import json as _json
    import urllib.request
    token = (req.token or "").strip()
    if not token:
        return {"ok": False, "error": "Pegá el token."}
    # validar contra la API (que exista y tenga acceso al repo)
    try:
        r = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}",
            headers={"Authorization": f"token {token}",
                     "Accept": "application/vnd.github+json", "User-Agent": "sq24"})
        info = _json.load(urllib.request.urlopen(r, timeout=30))
        if not info.get("permissions", {}).get("push"):
            return {"ok": False, "error": "El token es válido pero NO tiene permiso de "
                                          "escritura sobre el repo. Creá uno con permiso "
                                          "'Contents: Read and write'."}
    except Exception as e:
        return {"ok": False, "error": f"El token no funciona ({e}). Revisá que lo hayas "
                                      f"copiado completo y que tenga acceso al repo."}
    try:
        (APP_DIR.parent / "github_token.txt").write_text(token, encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"No se pudo guardar el token: {e}"}
    slog.log("LOGS", "Token de GitHub guardado desde la interfaz", {})
    return {"ok": True, "mensaje": "Token guardado. Ya podés subir los logs."}


@app.get("/api/logs/descargar")
def api_logs_descargar():
    """Descarga TODOS los logs y reportes en un ZIP. Alternativa que funciona siempre:
    sin token, sin git y sin internet (para pasarlos por mail/pendrive/WhatsApp)."""
    import io as _io
    import zipfile as _zip
    from datetime import datetime as _dt
    try:
        if slog.activo:
            slog._guardar()
    except Exception:
        pass
    log_dir = APP_DIR.parent / "log"
    patrones = ("sesion_*.txt", "sesion_*.json", "consola_*.txt",
                "reporte_*.json", "reporte_*.txt", "reporte_*.html",
                "ensayo_*.json", "ensayo_*.txt", "ensayo_*.html")
    archivos = []
    if log_dir.exists():
        for p in patrones:
            archivos += sorted(log_dir.glob(p))
    if not archivos:
        return JSONResponse({"error": "Todavía no hay logs ni reportes para descargar."},
                            status_code=404)
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as z:
        for f in archivos:
            try:
                z.write(f, arcname=f.name)
            except Exception:
                pass
    buf.seek(0)
    nombre = "logs_sistemasq24_" + _dt.now().strftime("%Y%m%d_%H%M%S") + ".zip"
    from fastapi.responses import Response
    return Response(content=buf.read(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@app.post("/api/captura-automatica/toggle")
def api_captura_toggle():
    """Activa/desactiva captura automática en TODAS las pantallas."""
    estado.captura_automatica = not estado.captura_automatica
    return {
        "captura_automatica": estado.captura_automatica,
        "mensaje": "Captura automática " + ("ACTIVADA" if estado.captura_automatica else "DESACTIVADA")
    }


@app.get("/api/captura-automatica/estado")
def api_captura_estado():
    """Retorna estado de captura automática."""
    return {"captura_automatica": estado.captura_automatica}


@app.get("/api/estado")
def api_estado():
    return {
        "conectado": estado.conectado,
        "modo": estado.modo,
        "puerto": estado.puerto,
        "ecu_activa": estado.ecu_activa,
        "modo_peligroso": estado.modo_peligroso,
        "captura_automatica": estado.captura_automatica,
    }


@app.get("/api/puertos")
def api_puertos():
    return {"puertos": _puertos_disponibles()}


@app.get("/api/csrf-token")
def api_csrf_token():
    """Devuelve el token CSRF actual."""
    return {"csrf_token": estado.csrf_token}


def _validar_csrf(csrf_token: str) -> bool:
    """Valida que el token CSRF coincida con el del servidor."""
    return csrf_token == estado.csrf_token


@app.post("/api/conectar")
def api_conectar(req: ConexionReq):
    if req.modo == "simulacion":
        return _conectar_simulacion()
    return _conectar_real(req.puerto, req.velocidad, req.adaptador)


@app.post("/api/desconectar")
def api_desconectar():
    if options.elm is not None:
        try:
            options.elm.close_protocol()
        except Exception as e:
            slog.log("CLEAR_CACHE", f"Error limpiando caché: {e}", {})
    options.elm = None
    with ESTADO_LOCK:
        estado.conectado = False
        estado.modo = "desconectado"
        estado.ecu_activa = None
        estado.vehiculo_seleccionado = None
        estado.actuadores_activos = {}   # cortar el keep-alive de actuadores
        estado.chequeo_cancelar = True   # abortar chequeo si estaba corriendo
        estado.ensayo_cancelar = True    # abortar ensayo si estaba corriendo
        # Descargar el auto activo: al desconectar no debe quedar ningún perfil cargado.
        estado.registro.reset()
    slog.log("CONEXION", "Desconectado del auto")
    return {"ok": True}


@app.post("/api/peligro")
def api_peligro(req: PeligroReq):
    options.promode = bool(req.activar)
    return {"modo_peligroso": options.promode}


@app.get("/api/ecus")
def api_ecus():
    return {"ecus": estado.registro.list()}


@app.get("/api/renault/modelos")
def api_renault_modelos():
    """Vehículos del selector. Solo Mégane II F4R está curado (disponible);
    el resto figura como 'Próximamente' (los autos reales entran por autodetección)."""
    modelos = [
        {"id": "megane_ii", "modelo": "Mégane II", "motor": "F4R/K4M", "año": "2002-2009",
         "ecuCount": 6, "imagen": "🔴", "disponible": True, "presente": "✓ Curado 100%"},
        {"id": "clio_ii", "modelo": "Clio II", "motor": "K4M/1.4", "año": "1998-2005",
         "ecuCount": 5, "imagen": "🟠", "disponible": False, "presente": "Próximamente"},
        {"id": "clio_iii", "modelo": "Clio III", "motor": "K4M/1.6", "año": "2005-2012",
         "ecuCount": 5, "imagen": "🟠", "disponible": False, "presente": "Próximamente"},
        {"id": "laguna_ii", "modelo": "Laguna II", "motor": "V6/2.0", "año": "2001-2007",
         "ecuCount": 6, "imagen": "🔵", "disponible": False, "presente": "Próximamente"},
        {"id": "scenic_ii", "modelo": "Scenic II", "motor": "K4M/1.6", "año": "2003-2009",
         "ecuCount": 6, "imagen": "🟢", "disponible": False, "presente": "Próximamente"},
        {"id": "kangoo", "modelo": "Kangoo", "motor": "K4M/1.6", "año": "2003-2010",
         "ecuCount": 5, "imagen": "🟣", "disponible": False, "presente": "Próximamente"},
    ]
    return {"modelos": modelos}


@app.post("/api/renault/conectar/{vehiculo_id}")
def api_renault_conectar(vehiculo_id: str):
    """Conecta a un modelo Renault específico (selecciona ECUs a cargar)."""
    vehiculo_map = {
        "megane_ii": {"nombre": "Mégane II F4R", "ecus": ["motor", "abs", "tablero", "airbag", "uch", "dae"]},
        "clio_ii": {"nombre": "Clio II", "ecus": ["motor", "abs", "tablero", "airbag", "uch"]},
        "clio_iii": {"nombre": "Clio III", "ecus": ["motor", "abs", "tablero", "airbag", "uch"]},
        "laguna_ii": {"nombre": "Laguna II", "ecus": ["motor", "abs", "tablero", "airbag", "uch", "dae"]},
        "scenic_ii": {"nombre": "Scenic II", "ecus": ["motor", "abs", "tablero", "airbag", "uch", "dae"]},
        "symbol": {"nombre": "Symbol", "ecus": ["motor", "abs", "tablero", "uch"]},
        "kangoo": {"nombre": "Kangoo", "ecus": ["motor", "abs", "tablero", "airbag", "uch"]},
    }

    if vehiculo_id not in vehiculo_map:
        return JSONResponse({"error": "Vehículo no soportado"}, status_code=400)

    info = vehiculo_map[vehiculo_id]

    # Mégane II F4R: perfil CURADO (100% traducido + procedimientos + ayudas).
    if vehiculo_id == "megane_ii":
        with ESTADO_LOCK:
            estado.registro.load_curado_f4r()
            estado.vehiculo_seleccionado = vehiculo_id
        slog.log("VEHICULO", f"Perfil curado: {info['nombre']}", {"ecus": len(info['ecus'])})
        return {
            "ok": True,
            "modelo": info['nombre'],
            "curado": True,
            "ecu_ids": [i["id"] for i in estado.registro.list()],
            "mensaje": f"{info['nombre']} — perfil curado 100%",
        }

    # Resto de modelos: se arman por AUTODETECCIÓN (no hay set curado).
    with ESTADO_LOCK:
        estado.vehiculo_seleccionado = vehiculo_id
    slog.log("VEHICULO", f"Seleccionado (genérico): {info['nombre']}")
    return {
        "ok": True,
        "modelo": info['nombre'],
        "curado": False,
        "ecu_ids": info['ecus'],
        "autodetectar": True,
        "mensaje": f"{info['nombre']} se arma escaneando el auto. Conectá y tocá 'Detectar ECUs'.",
    }


@app.post("/api/escanear")
def api_escanear():
    """Escanea las 6 ECUs del auto: cuáles responden y su identificación."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    slog.log("ESCANEO", "Escaneo de ECUs del auto")
    resultado = []
    with ELM_LOCK:
      _marcar_actividad()
      for info in estado.registro.list():
        tecu = estado.registro.get(info["id"])
        _seleccionar_ecu(info["id"])
        try:
            r = tecu.scan_identidad()
        except Exception as e:
            r = {"presente": False, "error": str(e)}
        slog.log("ESCANEO", f"{info['nombre']}: {'responde' if r.get('presente') else 'no responde'}",
                 r.get("identificacion", {}))
        resultado.append({
            "ecu": info["id"], "icono": info["icon"], "nombre": info["nombre"],
            "tx": info["tx"], "rx": info["rx"], **r,
        })
    presentes = sum(1 for r in resultado if r.get("presente"))
    return {"presentes": presentes, "total": len(resultado), "modulos": resultado}


@app.get("/api/procedimientos")
def api_procedimientos():
    """Catálogo curado de procedimientos útiles para el Mégane II F4R.
    Solo devuelve los que apuntan a una pantalla que realmente existe en la ECU."""
    path = APP_DIR / "procedimientos.json"
    if not path.exists():
        return {"procedimientos": []}
    # Los procedimientos curados son solo del perfil F4R. Para autos detectados
    # (genéricos) no aplican: se usan las pantallas/actuadores automáticos.
    if estado.registro.perfil != "f4r":
        return {"procedimientos": []}
    catalogo = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for p in catalogo:
        tecu = estado.registro.get(p.get("ecu"))
        if tecu is None:
            continue
        info = tecu.info()
        # Procedimientos que abren una sección propia (ej: Actuadores) en vez de una pantalla cruda
        if p.get("destino"):
            out.append({**p, "ecu_nombre": info["nombre"], "n_botones": 0, "n_lecturas": 0})
            continue
        detalle = tecu.screen(p.get("pantalla"))
        if detalle is None:
            continue
        out.append({
            **p,
            "ecu_nombre": info["nombre"],
            "pantalla_es": detalle["nombre"],
            "n_botones": len(detalle["botones"]),
            "n_lecturas": len(detalle["displays"]),
        })
    return {"procedimientos": out}


@app.get("/api/ecus/{ecu_id}/pantallas")
def api_pantallas(ecu_id: str):
    tecu = estado.registro.get(ecu_id)
    if tecu is None:
        return JSONResponse({"error": "ECU no encontrada"}, status_code=404)
    return {"info": tecu.info(), "categorias": tecu.categories()}


@app.get("/api/ecus/{ecu_id}/pantalla")
def api_pantalla(ecu_id: str, nombre: str):
    tecu = estado.registro.get(ecu_id)
    if tecu is None:
        return JSONResponse({"error": "ECU no encontrada"}, status_code=404)
    detail = tecu.screen(nombre)
    if detail is None:
        return JSONResponse({"error": "Pantalla no encontrada"}, status_code=404)
    return detail


@app.get("/api/ecus/{ecu_id}/parametros")
def api_parametros(ecu_id: str):
    tecu = estado.registro.get(ecu_id)
    if tecu is None:
        return JSONResponse({"error": "ECU no encontrada"}, status_code=404)
    return {"info": tecu.info(), "parametros": tecu.readable_params()}


def _capturar_pantalla_background(ecu, nombre_pantalla, request, inputs):
    """Captura en background (sin bloquear la respuesta HTTP)."""
    try:
        time.sleep(0.1)  # pequeña pausa para que se vea "después" de la lectura
        with ELM_LOCK:
            tecu = estado.registro.get(ecu)
            if tecu is None:
                return
            _marcar_actividad()
            _seleccionar_ecu(ecu)
            muestras = []
            t0 = time.time()
            for i in range(15):  # 15 muestras cada 100ms = 1.5s
                try:
                    valores = tecu.read_request(request, inputs)
                    if valores is not None:
                        valores_legibles = {}
                        for k, info in valores.items():
                            v = info.get("valor")
                            u = info.get("unidad", "")
                            if v is not None:
                                valores_legibles[info.get("etiqueta", k)] = f"{v} {u}".strip()
                        muestras.append({
                            "timestamp": round(time.time() - t0, 3),
                            "valores": valores_legibles
                        })
                    time.sleep(0.1)
                except Exception:
                    break
            duracion = time.time() - t0
            slog.log_captura_pantalla(ecu, nombre_pantalla, muestras, round(duracion, 2))
    except Exception:
        pass


@app.post("/api/leer")
def api_leer(req: ComandoReq):
    """Lectura puntual de un request (solo lectura)."""
    tecu = estado.registro.get(req.ecu)
    if tecu is None:
        return JSONResponse({"error": "ECU no encontrada"}, status_code=404)
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    try:
        with ELM_LOCK:
            _marcar_actividad()
            _seleccionar_ecu(req.ecu)
            valores = tecu.read_request(req.request, req.inputs)
    except Exception as e:
        slog.log("ERROR", f"Lectura fallida ({req.ecu})", {"request": req.request, "error": str(e)})
        return JSONResponse({"error": f"Error de lectura: {e}"}, status_code=500)
    if valores is None:
        slog.log("ERROR", f"Lectura vacía ({req.ecu})", {"request": req.request})
        return JSONResponse({"error": "La ECU no devolvió datos válidos"}, status_code=502)

    # Registrar en log
    try:
        slog.log_lectura(req.ecu, req.request, valores)
    except Exception:
        pass

    # Si captura automática está habilitada, capturar en background (no bloquea respuesta)
    if estado.captura_automatica and slog.activo:
        THREAD_POOL.submit(_capturar_pantalla_background, req.ecu, req.request, req.request, req.inputs)

    return {"valores": valores}


class CapturarMuestrasReq(BaseModel):
    ecu: str
    request: str
    inputs: dict = {}
    cantidad: int = 5  # default 5 muestras
    intervalo_ms: int = 500  # default 500ms entre muestras


class CapturarPantallaReq(BaseModel):
    ecu: str
    nombre_pantalla: str
    request: str
    inputs: dict = {}
    cantidad: int = 20  # default 20 muestras para captura automática
    intervalo_ms: int = 200  # default 200ms (más rápido que manual)


@app.post("/api/capturar-muestras")
def api_capturar_muestras(req: CapturarMuestrasReq):
    """Captura múltiples muestras de un request en secuencia (para ver evolución).

    Util para: acelerar motor y ver cómo suben RPM/temperatura, etc.
    Devuelve lista de (timestamp, valores) — se guarda en log como SERIE_TEMPORAL.
    """
    tecu = estado.registro.get(req.ecu)
    if tecu is None:
        return JSONResponse({"error": "ECU no encontrada"}, status_code=404)
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)

    muestras = []
    t0 = time.time()

    try:
        for i in range(req.cantidad):
            with ELM_LOCK:
                _marcar_actividad()
                _seleccionar_ecu(req.ecu)
                valores = tecu.read_request(req.request, req.inputs)

            if valores is not None:
                # Convertir valores a strings legibles (valor + unidad)
                valores_legibles = {}
                for k, info in valores.items():
                    v = info.get("valor")
                    u = info.get("unidad", "")
                    if v is not None:
                        valores_legibles[info.get("etiqueta", k)] = f"{v} {u}".strip()

                elapsed = time.time() - t0
                muestras.append({
                    "timestamp": round(elapsed, 2),
                    "valores": valores_legibles
                })

            # Esperar antes de la siguiente muestra (excepto la última)
            if i < req.cantidad - 1:
                time.sleep(req.intervalo_ms / 1000.0)
    except Exception as e:
        return JSONResponse({"error": f"Error capturando muestras: {e}"}, status_code=500)

    # Registrar serie temporal en log
    try:
        slog.log_series_temporal(req.ecu, req.request, muestras)
    except Exception:
        pass

    return {"muestras": muestras, "cantidad": len(muestras)}


@app.post("/api/capturar-pantalla")
def api_capturar_pantalla(req: CapturarPantallaReq):
    """Captura automática de pantalla (múltiples muestras + estadísticas).

    Se llama automáticamente cuando el usuario abre una pantalla en el scanner.
    Captura N muestras en background, calcula min/max/promedio, detecta anomalías.
    """
    tecu = estado.registro.get(req.ecu)
    if tecu is None:
        return JSONResponse({"error": "ECU no encontrada"}, status_code=404)
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)

    muestras = []
    t0 = time.time()

    try:
        for i in range(req.cantidad):
            with ELM_LOCK:
                _marcar_actividad()
                _seleccionar_ecu(req.ecu)
                valores = tecu.read_request(req.request, req.inputs)

            if valores is not None:
                # Convertir a formato legible
                valores_legibles = {}
                for k, info in valores.items():
                    v = info.get("valor")
                    u = info.get("unidad", "")
                    if v is not None:
                        valores_legibles[info.get("etiqueta", k)] = f"{v} {u}".strip()

                elapsed = time.time() - t0
                muestras.append({
                    "timestamp": round(elapsed, 3),
                    "valores": valores_legibles
                })

            # Esperar antes de siguiente muestra
            if i < req.cantidad - 1:
                time.sleep(req.intervalo_ms / 1000.0)
    except Exception as e:
        return JSONResponse({"error": f"Error capturando pantalla: {e}"}, status_code=500)

    # Registrar en log con estadísticas
    duracion = time.time() - t0
    try:
        slog.log_captura_pantalla(req.ecu, req.nombre_pantalla, muestras, round(duracion, 2))
    except Exception:
        pass

    return {
        "nombre_pantalla": req.nombre_pantalla,
        "cantidad": len(muestras),
        "duracion_s": round(duracion, 2),
        "muestras": muestras
    }


@app.get("/api/ecus/{ecu_id}/actuadores")
def api_actuadores(ecu_id: str):
    tecu = estado.registro.get(ecu_id)
    if tecu is None:
        return JSONResponse({"error": "ECU no encontrada"}, status_code=404)
    return tecu.actuators()


class ActuadorReq(BaseModel):
    ecu: str
    actuador_id: int = 0
    encender: bool = True


@app.post("/api/actuador")
def api_actuador(req: ActuadorReq):
    """Enciende/apaga un actuador (luces, A/C, ventilador…). Encender requiere modo avanzado."""
    tecu = estado.registro.get(req.ecu)
    if tecu is None:
        return JSONResponse({"error": "ECU no encontrada"}, status_code=404)
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    # Encender modifica el auto -> requiere modo avanzado. Apagar/detener siempre se permite.
    if req.encender and not options.promode:
        return JSONResponse(
            {"error": "BLOQUEADO", "detalle": "Activar un actuador enciende una pieza real del auto. "
             "Activá el modo avanzado para permitirlo."},
            status_code=403,
        )
    with ELM_LOCK:
        _marcar_actividad()
        _seleccionar_ecu(req.ecu)
        r = tecu.activate_actuator(req.actuador_id, on=req.encender)
    # Registrar resultado en log (incluir error si falló)
    try:
        log_detalle = {"accion": "encender" if req.encender else "apagar"}
        if not r.get("ok"):
            log_detalle["error"] = r.get("error", "Desconocido")
        slog.log_actuador(req.ecu, f"ID{req.actuador_id}", log_detalle, r.get("ok", False))
    except Exception:
        pass
    # Mantener registro de actuadores encendidos para el keep-alive (re-envío).
    key = f"{req.ecu}|{req.actuador_id}"
    with ESTADO_LOCK:
        if r.get("ok") and req.encender:
            estado.actuadores_activos[key] = {"ecu": req.ecu, "id": req.actuador_id}
        else:
            estado.actuadores_activos.pop(key, None)
    if not r.get("ok"):
        return JSONResponse({"error": r.get("error", "No se pudo activar"), "detalle": str(r)}, status_code=500)
    return r


@app.get("/api/service")
def api_service_leer():
    """Lee cuánto falta para el próximo service (km y meses)."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    tecu = estado.registro.get("tablero")
    with ELM_LOCK:
        _marcar_actividad()
        _seleccionar_ecu("tablero")
        return tecu.read_service()


class ServiceResetReq(BaseModel):
    km: int = 30000
    meses: int = 24


@app.post("/api/service/reset")
def api_service_reset(req: ServiceResetReq):
    """Reinicia el aviso de service. Requiere modo avanzado."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    if not options.promode:
        return JSONResponse(
            {"error": "BLOQUEADO", "detalle": "Reiniciar el service escribe en la memoria del "
             "tablero. Activá el modo avanzado para permitirlo."},
            status_code=403,
        )
    tecu = estado.registro.get("tablero")
    slog.log("SERVICE", "Reset del aviso de service", {"km": req.km, "meses": req.meses})
    with ELM_LOCK:
        _marcar_actividad()
        _seleccionar_ecu("tablero")
        r = tecu.reset_service(req.km, req.meses)
    if not r.get("ok"):
        return JSONResponse({"error": r.get("error", "No se pudo reiniciar")}, status_code=500)
    return r


class MemoriaReq(BaseModel):
    ecu: str = "tablero"
    tipo: int = 1                # 0 = micro, 1 = EEPROM
    direccion: str = "0000"
    cantidad: int = 16


@app.post("/api/memoria/leer")
def api_memoria_leer(req: MemoriaReq):
    """Lee bytes crudos de la memoria de un módulo (herramienta avanzada, solo lectura)."""
    tecu = estado.registro.get(req.ecu)
    if tecu is None:
        return JSONResponse({"error": "ECU no encontrada"}, status_code=404)
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    with ELM_LOCK:
        _marcar_actividad()
        _seleccionar_ecu(req.ecu)
        r = tecu.read_memory(req.tipo, req.direccion, req.cantidad)
    slog.log("MEMORIA", "Lectura de memoria", {"ecu": req.ecu, "tipo": req.tipo,
             "direccion": req.direccion, "cantidad": req.cantidad,
             "comando": r.get("comando"), "bytes": " ".join(r.get("bytes", []))})
    return r


@app.get("/api/adaptadores/buscar")
def api_adaptadores_buscar():
    """Busca adaptadores conectados y evalúa qué tan compatibles son."""
    puertos = _puertos_disponibles_detallado()
    return {"adaptadores": puertos}


class TestAdaptadorReq(BaseModel):
    puerto: str
    adaptador: str = "ELM327"


@app.post("/api/adaptadores/test")
def api_adaptadores_test(req: TestAdaptadorReq):
    """Prueba un adaptador: verifica que responde y qué tan compatible es."""
    return _test_adaptador(req.puerto, req.adaptador)


@app.post("/api/dtc/leer")
def api_dtc_leer():
    """Lee los códigos de falla (DTC) de TODAS las ECUs y los junta."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    slog.log("DTC", "Lectura de códigos de falla de todas las ECUs")
    resultado = []
    total = 0
    with ELM_LOCK:
      _marcar_actividad()
      for info in estado.registro.list():
        ecu_id = info["id"]
        tecu = estado.registro.get(ecu_id)
        _seleccionar_ecu(ecu_id)
        try:
            r = tecu.read_dtcs()
        except Exception as e:
            r = {"soportado": True, "cantidad": 0, "dtcs": [], "error": str(e)}
        slog.log("DTC", f"{info['nombre']}: {r.get('cantidad', 0)} falla(s)",
                 {"dtcs": [{"codigo": d.get("codigo"), "desc": d.get("descripcion")} for d in r.get("dtcs", [])]})
        resultado.append({
            "ecu": ecu_id,
            "icono": info["icon"],
            "nombre": info["nombre"],
            **r,
        })
        total += r.get("cantidad", 0)
    return {"total": total, "modulos": resultado}


@app.post("/api/dtc/leer/{ecu_id}")
def api_dtc_leer_ecu(ecu_id: str):
    tecu = estado.registro.get(ecu_id)
    if tecu is None:
        return JSONResponse({"error": "ECU no encontrada"}, status_code=404)
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    _seleccionar_ecu(ecu_id)
    return tecu.read_dtcs()


@app.post("/api/dtc/borrar")
def api_dtc_borrar():
    """Borra los códigos de falla de TODAS las ECUs. Requiere modo avanzado (peligroso)."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    if not options.promode:
        return JSONResponse(
            {"error": "BLOQUEADO", "detalle": "Borrar los códigos de falla modifica la memoria "
             "del auto. Activá el modo avanzado para permitirlo."},
            status_code=403,
        )
    resultado = []
    with ELM_LOCK:
      _marcar_actividad()
      for info in estado.registro.list():
        ecu_id = info["id"]
        tecu = estado.registro.get(ecu_id)
        _seleccionar_ecu(ecu_id)
        try:
            r = tecu.clear_dtcs()
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        resultado.append({"ecu": ecu_id, "nombre": info["nombre"], **r})
    ok = sum(1 for r in resultado if r.get("ok"))
    return {"borrados_ok": ok, "total": len(resultado), "modulos": resultado}


@app.post("/api/comando")
def api_comando(req: ComandoReq):
    """Envía un comando que puede modificar el auto. Bloqueado si no está el modo peligroso."""
    tecu = estado.registro.get(req.ecu)
    if tecu is None:
        return JSONResponse({"error": "ECU no encontrada"}, status_code=404)
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)

    peligroso = tecu.is_dangerous(req.request)
    if peligroso and not options.promode:
        return JSONResponse(
            {"error": "BLOQUEADO", "detalle": "Este comando puede modificar el auto. "
             "Activá el modo avanzado para permitirlo."},
            status_code=403,
        )

    slog.log("COMANDO", f"{req.request}", {"ecu": req.ecu, "inputs": req.inputs, "peligroso": peligroso})

    # Validar que el request exista en la ECU (prevenir inyección de comandos)
    request_exists = False
    for screens in getattr(tecu, 'screens', {}).values():
        for btn in screens.get('botones', []):
            if req.request in btn.get('requests', []):
                request_exists = True
                break
        if request_exists:
            break
    if not request_exists:
        return JSONResponse({"error": f"Request '{req.request}' no válido para esta ECU"}, status_code=400)

    # Detectar si es una rutina (StartRoutine - servicio 31)
    es_rutina = "routine" in req.request.lower() or "lancer" in req.request.lower()

    try:
        with ELM_LOCK:
            _marcar_actividad()
            _seleccionar_ecu(req.ecu)
            valores = _read_with_retry(tecu, req.request, req.inputs, max_retries=3)

            # Si es una rutina, esperar a que termine haciendo polling del estado
            if es_rutina:
                valores = _esperar_rutina(tecu, req.ecu, valores)
    except Exception as e:
        return JSONResponse({"error": f"Error al enviar comando: {e}"}, status_code=500)
    return {"ok": True, "peligroso": peligroso, "valores": valores or {}, "es_rutina": es_rutina}


def _esperar_rutina(tecu, ecu_id, valores_iniciales):
    """Espera a que una rutina termine, haciendo polling del estado (max 120 segundos)."""
    # Estados: 0=parada, 1=activa, 2=OK, 4=error, 8=error crítico
    tiempo_inicio = time.time()
    timeout = 120  # máximo 2 minutos

    # Intentar leer el estado de la rutina en el request de estado
    # (varia según ECU, pero típicamente hay un parámetro RENTSTAT1)
    estado_request = None
    for screen in getattr(tecu, 'screens', {}).values():
        for btn in screen.get('botones', []):
            if 'etat' in btn.get('texto', '').lower() or 'état' in btn.get('texto', '').lower():
                estado_request = btn.get('requests', [None])[0]
                break
        if estado_request:
            break

    # Si no hay request de estado explícito, usar el mismo (algunas rutinas devuelven estado en respuesta)
    if not estado_request:
        estado_request = None

    # Polling cada 500ms
    while time.time() - tiempo_inicio < timeout:
        time.sleep(0.5)
        try:
            # Intentar leer el estado
            if estado_request:
                estado = tecu.read_request(estado_request, {})
                # Buscar parámetro de estado en la respuesta
                for param_id, param_data in (estado or {}).items():
                    valor = param_data.get('valor')
                    if valor is not None:
                        # Estados: 2=OK, 4/8=error, otros=en progreso
                        if valor == 2:
                            slog.log("RUTINA", "Terminada OK", {"ecu": ecu_id})
                            return {**valores_iniciales, **estado}
                        elif valor in (4, 8):
                            slog.log("RUTINA", f"Error (estado {valor})", {"ecu": ecu_id})
                            return {**valores_iniciales, **estado, "_rutina_error": True}
            else:
                # Sin request de estado explícito, asumir que terminó
                return valores_iniciales
        except Exception as e:
            slog.log("RUTINA", f"Error polling estado: {e}", {})
            continue

    # Timeout
    slog.log("RUTINA", "Timeout esperando a que termine", {"ecu": ecu_id})
    return {**valores_iniciales, "_rutina_timeout": True}


# ----------------------------------------------------------------------------
# SCANNER UNIVERSAL — Base de datos de ECUs
# ----------------------------------------------------------------------------
@app.get("/api/ecu-database/info")
def api_ecu_database_info():
    """Info sobre la base de datos universal de ECUs (índice del ecu.zip)."""
    sc = get_scanner()
    sc.cargar_indice()
    return {
        "total_targets": len(sc.targets),
        "direcciones_can": len(sc.pares_can),
    }


@app.get("/api/perfil")
def api_perfil():
    """Perfil de ECUs activo: 'ninguno' | 'f4r' | 'detectado' | 'generico'."""
    return {
        "perfil": estado.registro.perfil,
        "vehiculo": estado.registro.vehiculo,
        "curado": estado.registro.perfil == "f4r",
        "generico": estado.registro.perfil == "generico",
        "ecus": [i["id"] for i in estado.registro.list()],
    }


@app.post("/api/obd/conectar")
def api_obd_conectar():
    """Activa el modo OBD-II GENÉRICO: funciona en cualquier auto sin la base de ECUs.
    Escanea qué PIDs (sensores) soporta el auto y lee el VIN."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    with ESTADO_LOCK:
        obd = estado.registro.load_generico()
        estado.vehiculo_seleccionado = "generico"
        estado.ecu_activa = None
    vin = None
    soportados = []
    with ELM_LOCK:
        _marcar_actividad()
        try:
            _seleccionar_ecu("obd")   # setea el direccionamiento funcional 7DF
        except Exception:
            pass
        try:
            soportados = sorted(obd.escanear_soportados())
        except Exception as e:
            slog.log("OBD", f"Error escaneando PIDs: {e}", {})
        try:
            vin = obd.leer_vin()
        except Exception:
            pass
    slog.log("OBD", "Modo OBD-II genérico activado",
             {"pids_soportados": len(soportados), "vin": vin})
    return {
        "ok": True,
        "vehiculo": "OBD-II Genérico",
        "vin": vin,
        "sensores": len(obd.readable_params()),
        "pids_soportados": soportados,
    }


@app.get("/api/obd/freeze-frame")
def api_obd_freeze_frame():
    """Freeze frame (cuadro congelado): sensores en el instante que saltó el DTC (Modo 02)."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    from obd_generico import get_obd
    obd = get_obd()
    with ELM_LOCK:
        _marcar_actividad()
        try:
            _seleccionar_ecu("obd")
        except Exception:
            pass
        try:
            return obd.leer_freeze_frame()
        except Exception as e:
            return JSONResponse({"error": f"Error leyendo freeze frame: {e}"}, status_code=500)


@app.get("/api/obd/readiness")
def api_obd_readiness():
    """Estado de los monitores de emisiones (I/M readiness) + testigo MIL."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    from obd_generico import get_obd
    obd = get_obd()
    with ELM_LOCK:
        _marcar_actividad()
        try:
            _seleccionar_ecu("obd")
        except Exception:
            pass
        try:
            return obd.leer_readiness()
        except Exception as e:
            return JSONResponse({"error": f"Error leyendo readiness: {e}"}, status_code=500)


@app.get("/api/obd/vin")
def api_obd_vin():
    """Lee el VIN y lo decodifica offline (país/fabricante/año), sin internet."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    from obd_generico import get_obd
    obd = get_obd()
    with ELM_LOCK:
        _marcar_actividad()
        try:
            _seleccionar_ecu("obd")
        except Exception:
            pass
        try:
            vin = obd.leer_vin() if not options.simulation_mode else "VF1BB000000000000"
            return {"vin": vin, "decodificado": obd.decodificar_vin(vin)}
        except Exception as e:
            return JSONResponse({"error": f"Error leyendo VIN: {e}"}, status_code=500)


def _construir_resultado_deteccion(res):
    """Carga el perfil detectado y arma el JSON de respuesta."""
    detectadas = res.get("detectadas", [])
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "Fallo el escaneo")}
    if not detectadas:
        return {"ok": True, "detectadas": [], "total": 0,
                "mensaje": "No se detectaron ECUs. Verificá la conexión OBD y el contacto."}
    with ESTADO_LOCK:
        n = estado.registro.load_detectado(detectadas, vehiculo=res.get("vehiculo", "Auto detectado"))
        estado.vehiculo_seleccionado = "detectado"
    slog.log("DETECTAR", f"Detectadas {n} ECUs — {res.get('vehiculo')}",
             {"ecus": [d["ecu_id"] for d in detectadas]})
    return {
        "ok": True, "vehiculo": res.get("vehiculo"), "total": n,
        "detectadas": [
            {"ecu_id": d["ecu_id"], "nombre": d["nombre"], "icon": d["icon"],
             "group": d["group"], "addr": d["addr"], "archivo": d["archivo"],
             "ecuname": d["ecuname"]}
            for d in detectadas
        ],
    }


def _run_deteccion():
    """Corre el escaneo en background, reportando progreso a estado.deteccion."""
    sc = get_scanner()

    def cb(actual, total, addr, n):
        with ESTADO_LOCK:
            estado.deteccion.update({"actual": actual, "total": total, "addr": addr, "n": n})

    try:
        with ELM_LOCK:
            _marcar_actividad()
            res = sc.escanear(progress_cb=cb)
        resultado = _construir_resultado_deteccion(res)
    except Exception as e:
        slog.log("DETECTAR", f"Error escaneando: {e}", {})
        resultado = {"ok": False, "error": f"Error escaneando: {e}"}
    with ESTADO_LOCK:
        estado.deteccion.update({"corriendo": False, "terminado": True, "resultado": resultado})


@app.post("/api/auto/detectar")
def api_auto_detectar():
    """Inicia la autodetección en segundo plano. Devuelve enseguida; el frontend
    consulta el progreso en /api/auto/detectar/progreso."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    with ESTADO_LOCK:
        if estado.deteccion.get("corriendo"):
            return {"ok": True, "iniciado": True, "ya_corria": True}
        estado.deteccion = {"corriendo": True, "actual": 0, "total": 0,
                            "addr": "", "n": 0, "terminado": False, "resultado": None}
    slog.log("DETECTAR", "Autodetección de ECUs iniciada")
    THREAD_POOL.submit(_run_deteccion)
    return {"ok": True, "iniciado": True}


@app.get("/api/auto/detectar/progreso")
def api_auto_detectar_progreso():
    """Progreso de la autodetección: {corriendo, actual, total, addr, n, terminado, resultado}."""
    with ESTADO_LOCK:
        return dict(estado.deteccion)


# ----------------------------------------------------------------------------
# CHEQUEO GENERAL DEL AUTO (reporte exhaustivo con captura por RPM)
# ----------------------------------------------------------------------------
class _CtxChequeo:
    """Contexto que el orquestador `chequeo.Chequeo` usa para hablar con el server,
    sin imports circulares."""
    registro = estado.registro
    elm_lock = ELM_LOCK

    def marcar_actividad(self):
        _marcar_actividad()

    def seleccionar_ecu(self, ecu_id):
        _seleccionar_ecu(ecu_id)

    def set_estado(self, kw):
        with ESTADO_LOCK:
            estado.chequeo.update(kw)

    def cancelado(self):
        return estado.chequeo_cancelar

    def capturar_ahora(self):
        return estado.chequeo_capturar

    def reset_capturar_ahora(self):
        estado.chequeo_capturar = False

    def simulacion(self):
        return options.simulation_mode

    def log(self, tipo, msg, det=None):
        slog.log(tipo, msg, det or {})


def _run_chequeo():
    import chequeo
    ctx = _CtxChequeo()
    ctx.registro = estado.registro   # perfil activo al momento de iniciar
    try:
        resultado = chequeo.Chequeo(ctx).run()
    except Exception as e:
        slog.log("CHEQUEO", f"Error en el chequeo: {e}", {})
        resultado = {"ok": False, "error": f"Error en el chequeo: {e}"}
    with ESTADO_LOCK:
        estado.chequeo.update({"corriendo": False, "terminado": True, "resultado": resultado})


@app.post("/api/chequeo/iniciar")
def api_chequeo_iniciar():
    """Inicia el chequeo general en segundo plano. Requiere auto conectado con motor."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    if estado.registro.perfil in ("ninguno", None):
        return JSONResponse({"error": "Primero seleccioná o detectá un auto"}, status_code=409)
    with ESTADO_LOCK:
        if estado.chequeo.get("corriendo"):
            return {"ok": True, "iniciado": True, "ya_corria": True}
        estado.chequeo = {"corriendo": True, "fase": "iniciando", "rpm_objetivo": 0,
                          "rpm_actual": None, "progreso": 0, "instruccion": "Preparando…",
                          "timeout": False, "terminado": False, "resultado": None, "error": None}
        estado.chequeo_cancelar = False
        estado.chequeo_capturar = False
    slog.log("CHEQUEO", "Chequeo general iniciado", {"perfil": estado.registro.perfil})
    THREAD_POOL.submit(_run_chequeo)
    return {"ok": True, "iniciado": True}


@app.get("/api/chequeo/estado")
def api_chequeo_estado():
    """Progreso del chequeo (fase, rpm_actual/objetivo, instruccion, terminado, resultado)."""
    with ESTADO_LOCK:
        return dict(estado.chequeo)


@app.post("/api/chequeo/capturar-ahora")
def api_chequeo_capturar():
    """Fuerza la captura de la etapa de RPM actual (fallback si no detecta la banda)."""
    estado.chequeo_capturar = True
    return {"ok": True}


@app.post("/api/chequeo/cancelar")
def api_chequeo_cancelar():
    """Aborta el chequeo en curso."""
    estado.chequeo_cancelar = True
    return {"ok": True}


@app.get("/api/chequeo/reporte/{tipo}")
def api_chequeo_reporte(tipo: str):
    """Descarga el reporte generado (tipo: html | json | txt)."""
    res = (estado.chequeo.get("resultado") or {}).get("reporte") or {}
    ruta = res.get(tipo)
    if not ruta or not Path(ruta).exists():
        return JSONResponse({"error": "Reporte no disponible"}, status_code=404)
    contenido = Path(ruta).read_text(encoding="utf-8")
    media = {"html": "text/html", "json": "application/json", "txt": "text/plain"}.get(tipo, "text/plain")
    from fastapi.responses import Response
    return Response(content=contenido, media_type=media + "; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{Path(ruta).name}"'})


# ----------------------------------------------------------------------------
# ENSAYO DE ACELERACIÓN (motor en movimiento, tramo de ~50/100 m)
# ----------------------------------------------------------------------------
class _CtxEnsayo:
    """Contexto que el orquestador `ensayo.Ensayo` usa para hablar con el server."""
    registro = estado.registro
    elm_lock = ELM_LOCK

    def marcar_actividad(self):
        _marcar_actividad()

    def seleccionar_ecu(self, ecu_id):
        _seleccionar_ecu(ecu_id)

    def set_estado(self, kw):
        with ESTADO_LOCK:
            estado.ensayo.update(kw)

    def cancelado(self):
        return estado.ensayo_cancelar

    def ahora(self):
        return estado.ensayo_ahora

    def reset_ahora(self):
        estado.ensayo_ahora = False

    def simulacion(self):
        return options.simulation_mode

    def log(self, tipo, msg, det=None):
        slog.log(tipo, msg, det or {})


def _run_ensayo(distancia):
    import ensayo
    ctx = _CtxEnsayo()
    ctx.registro = estado.registro
    try:
        resultado = ensayo.Ensayo(ctx, distancia_objetivo=distancia).run()
    except Exception as e:
        slog.log("ENSAYO", f"Error en el ensayo: {e}", {})
        resultado = {"ok": False, "error": f"Error en el ensayo: {e}"}
    with ESTADO_LOCK:
        estado.ensayo.update({"corriendo": False, "terminado": True, "resultado": resultado})


class EnsayoReq(BaseModel):
    distancia: float = 100.0


@app.post("/api/ensayo/iniciar")
def api_ensayo_iniciar(req: EnsayoReq = EnsayoReq()):
    """Inicia el ensayo de aceleración en segundo plano. Requiere auto conectado con motor.
    Acepta {distancia} (metros objetivo, default 100)."""
    if not estado.conectado:
        return JSONResponse({"error": "No hay conexión con el auto"}, status_code=409)
    if estado.registro.perfil in ("ninguno", None):
        return JSONResponse({"error": "Primero seleccioná o detectá un auto"}, status_code=409)
    distancia = max(20.0, min(500.0, float(req.distancia or 100.0)))
    with ESTADO_LOCK:
        if estado.ensayo.get("corriendo"):
            return {"ok": True, "iniciado": True, "ya_corria": True}
        estado.ensayo = {"corriendo": True, "fase": "iniciando", "vel_actual": None,
                         "rpm_actual": None, "distancia": 0, "progreso": 0,
                         "instruccion": "Preparando…", "timeout": False,
                         "terminado": False, "resultado": None, "error": None}
        estado.ensayo_cancelar = False
        estado.ensayo_ahora = False
    slog.log("ENSAYO", "Ensayo de aceleración iniciado",
             {"perfil": estado.registro.perfil, "distancia": distancia})
    THREAD_POOL.submit(_run_ensayo, distancia)
    return {"ok": True, "iniciado": True}


@app.get("/api/ensayo/estado")
def api_ensayo_estado():
    """Progreso del ensayo (fase, vel/rpm actuales, distancia, instruccion, terminado, resultado)."""
    with ESTADO_LOCK:
        return dict(estado.ensayo)


@app.post("/api/ensayo/ahora")
def api_ensayo_ahora():
    """Fuerza el 'ahora': arranca la grabación (en espera) o termina el tramo (grabando)."""
    estado.ensayo_ahora = True
    return {"ok": True}


@app.post("/api/ensayo/cancelar")
def api_ensayo_cancelar():
    """Aborta el ensayo en curso."""
    estado.ensayo_cancelar = True
    return {"ok": True}


@app.get("/api/ensayo/reporte/{tipo}")
def api_ensayo_reporte(tipo: str):
    """Descarga el reporte del ensayo (tipo: html | json | txt)."""
    res = (estado.ensayo.get("resultado") or {}).get("reporte") or {}
    ruta = res.get(tipo)
    if not ruta or not Path(ruta).exists():
        return JSONResponse({"error": "Reporte no disponible"}, status_code=404)
    contenido = Path(ruta).read_text(encoding="utf-8")
    media = {"html": "text/html", "json": "application/json", "txt": "text/plain"}.get(tipo, "text/plain")
    from fastapi.responses import Response
    return Response(content=contenido, media_type=media + "; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{Path(ruta).name}"'})


# ----------------------------------------------------------------------------
# WebSocket: lectura en vivo
# ----------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_vivo(ws: WebSocket):
    await ws.accept()
    suscripcion = {"ecu": None, "requests": [], "intervalo": 1.0}
    try:
        while True:
            # recibir suscripción (no bloqueante: con timeout corto)
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=0.01)
                data = json.loads(msg)
                if data.get("tipo") == "suscribir":
                    suscripcion["ecu"] = data.get("ecu")
                    suscripcion["requests"] = data.get("requests", [])
                    suscripcion["intervalo"] = float(data.get("intervalo", 1.0))
            except asyncio.TimeoutError:
                pass
            except (WebSocketDisconnect, RuntimeError):
                break

            if suscripcion["ecu"] and suscripcion["requests"] and estado.conectado:
                tecu = estado.registro.get(suscripcion["ecu"])
                if tecu is not None:
                    ecu_id = suscripcion["ecu"]
                    reqs = list(suscripcion["requests"])

                    def _leer_sync():
                        # Acceso exclusivo al ELM (no pisar comandos HTTP concurrentes).
                        with ELM_LOCK:
                            _marcar_actividad()
                            _seleccionar_ecu(ecu_id)
                            res = {}
                            for req_name in reqs:
                                try:
                                    vals = tecu.read_request(req_name)
                                except Exception as e:
                                    slog.log("WS_READ", f"Error leyendo {req_name}: {e}", {})
                                    vals = None
                                if vals:
                                    for dato, info in vals.items():
                                        res[tecu.param_id(req_name, dato)] = info
                            # Snapshot legible de sensores en la grabación (cada ~2s)
                            if slog.activo and res and time.time() - estado.ultimo_log_sensores > 2.0:
                                estado.ultimo_log_sensores = time.time()
                                try:
                                    legible = {info["etiqueta"]: info for info in res.values()}
                                    slog.log_sensores(ecu_id, legible)
                                except Exception as e:
                                    slog.log("WS_LOG", f"Error loguando sensores: {e}", {})
                            return res

                    # Correr la lectura serie en un thread para no bloquear el servidor.
                    resultado = await asyncio.get_event_loop().run_in_executor(None, _leer_sync)
                    await ws.send_text(json.dumps({"tipo": "valores", "datos": resultado}))

            await asyncio.sleep(max(0.05, suscripcion["intervalo"]))
    except WebSocketDisconnect:
        pass


# ----------------------------------------------------------------------------
# Tester present: mantiene viva la sesión de diagnóstico cuando hay pausas.
# Renault cierra la sesión tras unos segundos de silencio; sin esto, los
# actuadores y lecturas dejan de responder. Se saltea si hubo actividad reciente
# (las lecturas en vivo ya mantienen el bus, igual que hace DDT4All).
# ----------------------------------------------------------------------------
async def _tester_present_loop():
    while True:
        await asyncio.sleep(1.2)
        if not (estado.conectado and estado.modo == "real" and options.elm is not None):
            continue

        # Si hay actuadores encendidos, re-enviar su comando (keep-alive): el
        # "Start Temporary" del servicio 30 expira solo, así que hay que refrescarlo
        # para que la salida siga activa. Esto también mantiene viva la sesión.
        activos = None
        with ESTADO_LOCK:
            if estado.actuadores_activos:
                activos = list(estado.actuadores_activos.values())

        if activos:
            def _refrescar_actuadores():
                with ELM_LOCK:
                    for a in activos:
                        try:
                            tecu = estado.registro.get(a["ecu"])
                            if tecu is None:
                                continue
                            _seleccionar_ecu(a["ecu"])
                            tecu.activate_actuator(a["id"], on=True)
                        except Exception:
                            pass
                    _marcar_actividad()
            try:
                await asyncio.get_event_loop().run_in_executor(None, _refrescar_actuadores)
            except Exception:
                pass
            continue

        if time.time() - estado.ultima_actividad < 1.4:
            continue

        def _enviar():
            with ELM_LOCK:
                try:
                    if estado.ecu_activa:
                        tecu = estado.registro.get(estado.ecu_activa)
                        if tecu is not None:
                            tecu.ensure_session()
                    # TesterPresent estándar UDS es 3E 00 (sub-función), no 3E pelado:
                    # algunos ECU estrictos rechazan 3E solo con 7F 3E 13.
                    options.elm.request("3E00", cache=False)
                    _marcar_actividad()
                except Exception:
                    pass
        try:
            await asyncio.get_event_loop().run_in_executor(None, _enviar)
        except Exception as e:
            slog.log("CLEAR_CACHE", f"Error limpiando caché: {e}", {})


@app.on_event("startup")
async def _startup():
    # Precargar el índice de ECUs (db.json) en background para que la autodetección
    # sea instantánea cuando el usuario la pida.
    threading.Thread(target=lambda: get_scanner().cargar_indice(), daemon=True).start()
    asyncio.create_task(_tester_present_loop())


# ----------------------------------------------------------------------------
# Frontend estático
# ----------------------------------------------------------------------------
@app.get("/")
def index():
    return HTMLResponse((WEB_DIR / "index.html").read_text(encoding="utf-8"))


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
