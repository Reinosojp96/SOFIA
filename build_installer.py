"""
Script para generar Instalar_SOFIA.exe con PyInstaller.

Ejecutar en Windows con el venv activado:
  pip install pyinstaller
  python build_installer.py

El .exe resultante estará en dist/Instalar_SOFIA.exe
Es standalone (~8MB), no requiere Python instalado para ejecutarse.

NOTA: PyInstaller debe ejecutarse en Windows para generar un .exe de Windows.
"""

import subprocess
import sys
import os
from pathlib import Path

# Evita UnicodeEncodeError al imprimir ✓/✗ en consolas Windows con
# codificación cp1252 (mismo problema que mitiga instalar_sofia.py).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

NOMBRE_EXE = "Instalar_SOFIA"
SCRIPT     = "installer_gui.py"
ICONO      = "ui/icon.ico"          # opcional, omitir si no existe

def build():
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                            # un solo .exe
        "--windowed",                           # sin consola (es una GUI)
        "--clean",
        "--uac-admin",                          # pide elevación UAC al ejecutar
        f"--name={NOMBRE_EXE}",
        "--hidden-import=urllib.request",
        "--hidden-import=zipfile",
        "--hidden-import=pathlib",
        "--hidden-import=subprocess",
        "--hidden-import=threading",
        "--hidden-import=tkinter",
        "--hidden-import=queue",
        "--hidden-import=instalar_sofia",
    ]

    # Agregar icono si existe
    if Path(ICONO).exists():
        args += [f"--icon={ICONO}"]
    else:
        print(f"[build] Sin icono ({ICONO} no encontrado), continuando sin él.")

    # Metadata de versión en Windows (opcional)
    version_file = Path("_version_info.txt")
    version_file.write_text("""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f, flags=0x0,
    OS=0x40004, fileType=0x1,
    subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Reinosojp96'),
        StringStruct('FileDescription', 'Instalador de SOFIA'),
        StringStruct('FileVersion', '1.0.0'),
        StringStruct('InternalName', 'Instalar_SOFIA'),
        StringStruct('LegalCopyright', '2025'),
        StringStruct('OriginalFilename', 'Instalar_SOFIA.exe'),
        StringStruct('ProductName', 'SOFIA Asistente de Voz'),
        StringStruct('ProductVersion', '1.0.0'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [0x0409, 1200])])
  ]
)
""")
    args += [f"--version-file={version_file}"]
    args.append(SCRIPT)

    print(f"\n[build] Ejecutando PyInstaller...")
    print(f"[build] Comando: {' '.join(str(a) for a in args)}\n")

    r = subprocess.run(args)

    # Limpiar archivos temporales
    try:
        version_file.unlink()
    except Exception:
        pass

    if r.returncode == 0:
        exe = Path("dist") / f"{NOMBRE_EXE}.exe"
        if exe.exists():
            size_mb = exe.stat().st_size / 1_048_576
            print(f"\n✓ Generado: {exe} ({size_mb:.1f} MB)")
            print(f"\nDistribuye solo este archivo a tus usuarios.")
            print(f"Al ejecutarlo, pedirá directorio de instalación")
            print(f"y hará todo automáticamente.")
        else:
            print(f"\n✓ Build completado. Revisa la carpeta dist/")
    else:
        print(f"\n✗ Build falló con código {r.returncode}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller no está instalado.")
        print("Instálalo con: pip install pyinstaller")
        sys.exit(1)

    build()