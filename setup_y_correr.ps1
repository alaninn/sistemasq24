# Scanner Mégane II F4R - Setup automático y arranque
# Verifica Python, lo instala si falta, arma el entorno y arranca el servidor.
$ErrorActionPreference = "Stop"
$ProjDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvDir = Join-Path $ProjDir ".venv"
$VenvPy  = Join-Path $VenvDir "Scripts\python.exe"
$AppRun  = Join-Path $ProjDir "app\run.py"
$MarkerOk = Join-Path $VenvDir ".deps_ok"

function Write-Step($msg) { Write-Host ""; Write-Host ">> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "   OK: $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "   $msg" -ForegroundColor Yellow }

Write-Host "==============================================" -ForegroundColor White
Write-Host "  Scanner Megane II - F4R" -ForegroundColor White
Write-Host "  Preparando el equipo..." -ForegroundColor White
Write-Host "==============================================" -ForegroundColor White

# ---------- 1) Buscar Python ----------
Write-Step "Buscando Python en el equipo..."
$PyExe = $null
foreach ($cand in @("py -3", "python", "python3")) {
    try {
        $parts = $cand.Split(" ")
        $exe = $parts[0]; $args = if ($parts.Count -gt 1) { $parts[1..($parts.Count-1)] } else { @() }
        $ver = & $exe @args "-c" "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
        if ($ver -and [version]$ver -ge [version]"3.8") {
            $PyExe = $cand
            Write-Ok "Python $ver encontrado ($cand)"
            break
        }
    } catch {}
}

# ---------- 2) Instalar Python si falta ----------
if (-not $PyExe) {
    Write-Warn "No hay Python instalado. Instalando automáticamente (puede tardar unos minutos)..."
    $installed = $false
    # 2a) intentar con winget (Windows 10/11 moderno)
    try {
        $wg = Get-Command winget -ErrorAction SilentlyContinue
        if ($wg) {
            Write-Warn "Instalando Python con winget..."
            winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements
            $installed = $true
        }
    } catch { Write-Warn "winget no disponible o falló, probando descarga directa..." }

    # 2b) fallback: descargar el instalador oficial y correrlo silencioso
    if (-not $installed) {
        $url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        $tmp = Join-Path $env:TEMP "python-3.11.9-amd64.exe"
        Write-Warn "Descargando Python desde python.org..."
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        Write-Warn "Instalando Python (silencioso, solo para tu usuario)..."
        Start-Process -FilePath $tmp -ArgumentList "/quiet","InstallAllUsers=0","PrependPath=1","Include_test=0","Include_launcher=1" -Wait
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }

    # re-detectar Python tras instalar
    Start-Sleep -Seconds 2
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","User") + ";" + [System.Environment]::GetEnvironmentVariable("Path","Machine")
    foreach ($cand in @("py -3", "python")) {
        try {
            $parts = $cand.Split(" "); $exe=$parts[0]; $args=if($parts.Count -gt 1){$parts[1..($parts.Count-1)]}else{@()}
            $ver = & $exe @args "-c" "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
            if ($ver) { $PyExe = $cand; break }
        } catch {}
    }
    # buscar en la ruta típica de instalación por-usuario
    if (-not $PyExe) {
        $guess = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($guess) { $PyExe = "`"$($guess.FullName)`"" }
    }
    if (-not $PyExe) {
        Write-Host "   No se pudo instalar Python automáticamente." -ForegroundColor Red
        Write-Host "   Instalalo a mano desde https://www.python.org/downloads/ (marcá 'Add to PATH') y volvé a correr esto." -ForegroundColor Red
        Read-Host "Enter para salir"; exit 1
    }
    Write-Ok "Python instalado."
}

# ---------- 3) Crear/validar entorno virtual ----------
# Un venv copiado de otra PC apunta al Python de esa PC y no funciona acá.
# Verificamos que el venv realmente arranque; si no, lo recreamos.
$venvValido = $false
if (Test-Path $VenvPy) {
    try {
        $test = & $VenvPy "-c" "print('ok')" 2>$null
        if ($test -eq "ok") { $venvValido = $true }
    } catch {}
    if (-not $venvValido) {
        Write-Warn "El entorno venía de otra computadora. Recreándolo para este equipo..."
        Remove-Item $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $MarkerOk) { Remove-Item $MarkerOk -Force -ErrorAction SilentlyContinue }
    }
}
if (-not (Test-Path $VenvPy)) {
    Write-Step "Creando entorno de trabajo (una sola vez)..."
    $parts = $PyExe.Split(" "); $exe=$parts[0]; $args=if($parts.Count -gt 1){$parts[1..($parts.Count-1)]}else{@()}
    & $exe @args "-m" "venv" $VenvDir
    if (-not (Test-Path $VenvPy)) {
        Write-Host "   No se pudo crear el entorno. ¿Python quedó bien instalado?" -ForegroundColor Red
        Read-Host "Enter para salir"; exit 1
    }
    Write-Ok "Entorno creado."
}

# ---------- 4) Instalar dependencias (solo si faltan) ----------
if (-not (Test-Path $MarkerOk)) {
    Write-Step "Instalando lo necesario (pyserial, fastapi, uvicorn... liviano, sin PyQt)..."

    $ReqFile = Join-Path $ProjDir "requirements.txt"
    $WheelsDir = Join-Path $ProjDir "wheels"

    # Instalar dependencias: preferir wheels locales, pero permitir fallback a internet
    if (Test-Path $WheelsDir) {
        Write-Warn "Intentando usar paquetes locales primero…"
        # Primero intenta con wheels locales, pero SIN --no-index (permite fallback a internet si falta algo)
        & $VenvPy "-m" "pip" "install" "--quiet" "--find-links" $WheelsDir "--prefer-binary" "-r" $ReqFile
    } else {
        Write-Warn "Descargando dependencias desde internet…"
        & $VenvPy "-m" "pip" "install" "--quiet" "--no-cache-dir" "--prefer-binary" "-r" $ReqFile
    }

    if ($LASTEXITCODE -eq 0) {
        "ok" | Out-File -FilePath $MarkerOk -Encoding ascii
        Write-Ok "Dependencias instaladas."
    } else {
        Write-Host "   Falló la instalación. Revisá:" -ForegroundColor Red
        Write-Host "     • ¿Hay conexión a internet?" -ForegroundColor Red
        Write-Host "     • ¿La carpeta 'wheels/' está intacta?" -ForegroundColor Red
        Read-Host "Enter para salir"; exit 1
    }
} else {
    Write-Ok "Dependencias ya instaladas."
}

# ---------- 5) Arrancar ----------
Write-Step "Iniciando el scanner..."
Write-Host "   Cuando quieras cerrarlo, cerrá esta ventana." -ForegroundColor Yellow
Write-Host ""
Set-Location (Join-Path $ProjDir "app")
& $VenvPy $AppRun
