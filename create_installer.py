#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para empaquetar el Scanner Mégane II Universal en un instalador.

Uso:
    python create_installer.py

Genera:
    dist/megane2_scanner_installer.zip
    dist/install.bat
    dist/LEEME_INSTALACION.txt
"""

import os
import shutil
import zipfile
from pathlib import Path

def create_installer():
    """Crea el paquete instalador comprimido."""

    BASE_DIR = Path(__file__).parent
    DIST_DIR = BASE_DIR / "dist"
    PROJECT_ROOT = BASE_DIR

    # Crear carpeta dist si no existe
    DIST_DIR.mkdir(exist_ok=True)
    print(f"📁 Creando carpeta: {DIST_DIR}")

    # Lista de carpetas/archivos a INCLUIR
    INCLUDE = [
        "app",
        "vendor",
        "wheels",
        "log",
        "requirements.txt",
        "setup_y_correr.ps1",
        "INICIAR_SCANNER.bat",
        "README.md",
        ".gitignore",
        "procedimientos.json",
    ]

    # Lista de carpetas/archivos a EXCLUIR
    EXCLUDE_DIRS = {
        ".venv",
        ".git",
        "__pycache__",
        ".pytest_cache",
        "dist",
        ".idea",
        ".vscode",
    }

    EXCLUDE_FILES = {".deps_ok", ".DS_Store"}
    EXCLUDE_EXTENSIONS = {".pyc", ".pyo", ".egg-info"}

    # Crear ZIP
    zip_path = DIST_DIR / "megane2_scanner_installer.zip"
    print(f"📦 Creando ZIP: {zip_path}")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            # Filtrar directorios a excluir
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            # Procesar archivos
            for file in files:
                file_path = Path(root) / file

                # Excluir archivos específicos
                if file in EXCLUDE_FILES:
                    continue
                if file.endswith(tuple(EXCLUDE_EXTENSIONS)):
                    continue

                # Calcular ruta relativa
                try:
                    rel_path = file_path.relative_to(PROJECT_ROOT.parent)

                    # Solo incluir si está en INCLUDE o es archivo de config
                    should_include = any(
                        rel_path.parts[1] == inc if len(rel_path.parts) > 1 else False
                        for inc in INCLUDE
                    ) or file in {"README.md", "requirements.txt"}

                    if should_include:
                        arcname = str(rel_path)
                        zipf.write(file_path, arcname)
                        print(f"  ✓ {arcname}")
                except ValueError:
                    pass

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"✅ ZIP creado: {size_mb:.1f} MB\n")

    # Copiar install.bat a dist
    install_bat = BASE_DIR / "install.bat"
    if install_bat.exists():
        shutil.copy(install_bat, DIST_DIR / "install.bat")
        print(f"✓ Copiado: install.bat")

    # Copiar instrucciones
    readme = BASE_DIR / "LEEME_INSTALACION.txt"
    if readme.exists():
        shutil.copy(readme, DIST_DIR / "LEEME_INSTALACION.txt")
        print(f"✓ Copiado: LEEME_INSTALACION.txt")

    print(f"\n🎉 Installer creado en: {DIST_DIR}")
    print(f"   📦 {zip_path.name}")
    print(f"   📝 LEEME_INSTALACION.txt")
    print(f"   ⚙️  install.bat")

if __name__ == "__main__":
    create_installer()
