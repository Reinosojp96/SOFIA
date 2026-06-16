"""
SOFÍA — Bootstrap Installer
Archivo único que el usuario ejecuta con doble clic (como .exe)
o con: python instalar_sofia.py

No requiere Git. Solo necesita Python 3.11+ instalado.

Hace:
  1. Verifica Python 3.10-3.12
  2. Descarga el ZIP del repositorio de GitHub
  3. Extrae en el directorio de instalación
  4. Crea el venv
  5. Instala dependencias base (incluyendo llama-cpp-python con wheels
     precompiladas para evitar Build Tools de Visual Studio)
  6. Lanza setup.py del proyecto con el Python del venv
"""

import sys
import os
import platform
import subprocess
import shutil
import zipfile
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

# ─────────────────────────────────────────────
# Frozen (.exe de PyInstaller) vs script normal
# ─────────────────────────────────────────────
# Si está "frozen", sys.executable apunta al propio bootloader del .exe,
# NO a un Python real — por eso la verificación de versión y la creación
# del venv no pueden basarse en sys.executable/sys.version_info aquí.
# Ver localizar_python_sistema() más abajo.
FROZEN = getattr(sys, "frozen", False)

# ─────────────────────────────────────────────
# Verificación de versión ANTES de cualquier import (solo si NO está frozen)
# ─────────────────────────────────────────────
if not FROZEN and (sys.version_info < (3, 10) or sys.version_info >= (3, 13)):
    print("=" * 55)
    print("  ERROR: SOFÍA requiere Python 3.10, 3.11 o 3.12")
    print(f"  Tienes Python {sys.version_info.major}.{sys.version_info.minor}")
    print()
    print("  Descarga Python 3.11 en:")
    print("  https://www.python.org/downloads/")
    print()
    print("  IMPORTANTE: marca 'Add Python to PATH'")
    print("  durante la instalación.")
    print("=" * 55)
    input("\n  Presiona Enter para cerrar...")
    sys.exit(1)

IS_WIN = platform.system() == "Windows"

# Forzar UTF-8 en la consola de Windows (evita UnicodeEncodeError con
# caracteres del spinner como ⠸ ⠋ etc. en terminales con cp1252)
if IS_WIN and sys.stdout is not None and getattr(sys.stdout, "isatty", lambda: False)():
    os.system("chcp 65001 > nul 2>&1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
GITHUB_USER   = "Reinosojp96"
GITHUB_REPO   = "SOFIA"
GITHUB_BRANCH = "main"
ZIP_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"

if IS_WIN:
    DIR_DEFECTO = Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "SOFIA"
else:
    DIR_DEFECTO = Path.home() / "sofia"

# ─────────────────────────────────────────────
# Colores (solo si la terminal los soporta)
# ─────────────────────────────────────────────
# os.system("") ya activa el modo VT100 en consolas modernas de Windows
# (10+, mínimo soportado), así que no dependemos de la variable TERM.
_COLOR = True

class C:
    RESET  = "\033[0m"  if _COLOR else ""
    BOLD   = "\033[1m"  if _COLOR else ""
    GREEN  = "\033[92m" if _COLOR else ""
    YELLOW = "\033[93m" if _COLOR else ""
    RED    = "\033[91m" if _COLOR else ""
    CYAN   = "\033[96m" if _COLOR else ""
    BLUE   = "\033[94m" if _COLOR else ""

def ok(msg):    print(f"{C.GREEN}  ✓ {msg}{C.RESET}")
def info(msg):  print(f"{C.CYAN}  ℹ {msg}{C.RESET}")
def warn(msg):  print(f"{C.YELLOW}  ⚠ {msg}{C.RESET}")
def error(msg): print(f"{C.RED}  ✗ {msg}{C.RESET}")
def titulo(msg):
    print(f"\n{C.BOLD}{C.BLUE}{'─'*55}")
    print(f"  {msg}")
    print(f"{'─'*55}{C.RESET}")

# ─────────────────────────────────────────────
# Spinner
# ─────────────────────────────────────────────
class Spinner:
    def __init__(self, msg=""):
        self._msg = msg; self._activo = False; self._hilo = None
    def __enter__(self):
        frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._activo = True
        def _loop():
            i = 0
            while self._activo:
                print(f"\r  {C.CYAN}{frames[i%len(frames)]}{C.RESET} {self._msg}",
                      end="", flush=True)
                time.sleep(0.1); i += 1
        self._hilo = threading.Thread(target=_loop, daemon=True)
        self._hilo.start()
        return self
    def __exit__(self, *_):
        self._activo = False
        if self._hilo: self._hilo.join(timeout=0.5)
        print()

# ─────────────────────────────────────────────
# Barra de progreso para descargas
# ─────────────────────────────────────────────
class Progreso:
    def __init__(self, descripcion=""):
        self.descripcion = descripcion
        self.total = 0
        self.actual = 0

    def callback(self, bloques, tam_bloque, tam_total):
        self.total  = tam_total
        self.actual = min(bloques * tam_bloque, tam_total)
        self._dibujar()

    def _dibujar(self):
        ancho = 38
        if self.total > 0:
            pct = min(self.actual / self.total, 1.0)
            llenos = int(ancho * pct)
            barra = "█" * llenos + "░" * (ancho - llenos)
            mb_a = self.actual / 1_048_576
            mb_t = self.total  / 1_048_576
            print(f"\r  [{barra}] {pct*100:.0f}%  {mb_a:.0f}/{mb_t:.0f} MB",
                  end="", flush=True)
        else:
            print(f"\r  Descargando {self.descripcion}...", end="", flush=True)

# ─────────────────────────────────────────────
# PASO 0 — Localizar un Python real del sistema (3.10–3.12)
# ─────────────────────────────────────────────
def _version_de(candidato) -> tuple | None:
    """Ejecuta <candidato> -c "..." y devuelve (major, minor) o None si falla."""
    try:
        r = subprocess.run(
            list(candidato) + ["-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            maj, mn = r.stdout.strip().split()
            return (int(maj), int(mn))
    except Exception:
        pass
    return None


def localizar_python_sistema() -> Path | None:
    """
    Devuelve la ruta a un Python 3.10-3.12 real instalado en el sistema.

    Si no estamos "frozen" (corriendo como .py), basta con sys.executable.
    Si estamos frozen (.exe de PyInstaller), sys.executable apunta al
    propio bootloader del .exe, no a un Python real, así que hay que
    buscarlo: lanzador "py", luego "python"/"python3" en el PATH, y por
    último ubicaciones típicas de instalación en Windows.
    """
    if not FROZEN:
        return Path(sys.executable)

    candidatos = []
    if IS_WIN:
        for v in ("3.12", "3.11", "3.10"):
            candidatos.append(["py", f"-{v}"])
        candidatos.append(["py", "-3"])
    candidatos.append(["python"])
    candidatos.append(["python3"])

    if IS_WIN:
        local_appdata = os.environ.get("LocalAppData", "")
        if local_appdata:
            base = Path(local_appdata) / "Programs" / "Python"
            for nombre in ("Python312", "Python311", "Python310"):
                exe = base / nombre / "python.exe"
                if exe.exists():
                    candidatos.append([str(exe)])

    for candidato in candidatos:
        ver = _version_de(candidato)
        if ver and (3, 10) <= ver <= (3, 12):
            # Resolver a la ruta real del ejecutable (sys.executable del candidato)
            try:
                r = subprocess.run(
                    list(candidato) + ["-c", "import sys; print(sys.executable)"],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0 and r.stdout.strip():
                    return Path(r.stdout.strip())
            except Exception:
                pass
            # Si el candidato ya era una ruta directa a python.exe, usarla
            if len(candidato) == 1 and Path(candidato[0]).exists():
                return Path(candidato[0])

    return None


# ─────────────────────────────────────────────
# PASO 1 — Verificar / detectar CUDA
# ─────────────────────────────────────────────
def detectar_cuda() -> str:
    """Devuelve el tag de PyTorch (cu118, cu124, cu126, cu128) o 'cpu'."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=6
        )
        if r.returncode == 0 and r.stdout.strip():
            # Detectar versión de CUDA
            r2 = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=6)
            for linea in r2.stdout.split("\n"):
                if "CUDA Version" in linea:
                    ver = linea.split("CUDA Version:")[-1].strip().split()[0]
                    maj, mn = ver.split(".")[:2]
                    v = int(maj) * 100 + int(mn) * 10
                    if v >= 1280: return "cu128"
                    if v >= 1260: return "cu126"
                    if v >= 1240: return "cu124"
                    return "cu118"
            return "cu126"  # GPU detectada, CUDA desconocida → asumir cu126
    except Exception:
        pass
    return "cpu"

# ─────────────────────────────────────────────
# PASO 2 — Descargar ZIP del repositorio
# ─────────────────────────────────────────────
def descargar_repo(destino_zip: Path, ui=None) -> bool:
    if ui is None:
        titulo("Descargando SOFÍA desde GitHub")
        info(f"URL: {ZIP_URL}")
    else:
        ui.status("Descargando SOFÍA desde GitHub...")

    progreso = Progreso("repositorio")
    try:
        req = urllib.request.Request(
            ZIP_URL,
            headers={"User-Agent": "SOFIA-Installer/1.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            tam_total = int(resp.headers.get("Content-Length", 0))
            progreso.total = tam_total
            descargado = 0
            chunk = 65536

            with open(destino_zip, "wb") as f:
                while True:
                    datos = resp.read(chunk)
                    if not datos:
                        break
                    f.write(datos)
                    descargado += len(datos)
                    progreso.actual = descargado
                    if ui is None:
                        progreso._dibujar()
                    else:
                        ui.progress(descargado, tam_total)

        if ui is None:
            print()
            ok(f"Repositorio descargado ({destino_zip.stat().st_size // 1024} KB)")
        else:
            ui.log(f"Repositorio descargado ({destino_zip.stat().st_size // 1024} KB)")
        return True

    except urllib.error.URLError as e:
        if ui is None:
            print()
            error(f"No se pudo descargar: {e}")
            error("Verifica tu conexión a internet e inténtalo de nuevo.")
        else:
            ui.log(f"No se pudo descargar: {e}. Verifica tu conexión a internet.", level="error")
        return False
    except Exception as e:
        if ui is None:
            print()
            error(f"Error inesperado: {e}")
        else:
            ui.log(f"Error inesperado: {e}", level="error")
        return False

# ─────────────────────────────────────────────
# PASO 3 — Extraer ZIP
# ─────────────────────────────────────────────
def extraer_repo(zip_path: Path, directorio: Path, ui=None) -> bool:
    if ui is None:
        titulo("Extrayendo archivos")
    else:
        ui.status("Extrayendo archivos...")

    try:
        ctx = Spinner("Extrayendo...") if ui is None else _nullcontext()
        with ctx:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # El ZIP de GitHub tiene una carpeta raíz tipo "SOFIA-main/"
                nombres = zf.namelist()
                raiz_zip = nombres[0].split("/")[0] + "/"

                for miembro in nombres:
                    # Quitar la carpeta raíz del ZIP
                    ruta_rel = miembro[len(raiz_zip):]
                    if not ruta_rel:
                        continue

                    destino = directorio / ruta_rel

                    if miembro.endswith("/"):
                        destino.mkdir(parents=True, exist_ok=True)
                    else:
                        destino.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(miembro) as src, open(destino, "wb") as dst:
                            shutil.copyfileobj(src, dst)

        if ui is None:
            ok(f"Archivos extraídos en {directorio}")
        else:
            ui.log(f"Archivos extraídos en {directorio}")
        return True

    except zipfile.BadZipFile:
        msg = "El archivo descargado está corrupto. Inténtalo de nuevo."
        error(msg) if ui is None else ui.log(msg, level="error")
        return False
    except Exception as e:
        msg = f"Error al extraer: {e}"
        error(msg) if ui is None else ui.log(msg, level="error")
        return False


class _nullcontext:
    def __enter__(self): return self
    def __exit__(self, *_): return False

# ─────────────────────────────────────────────
# PASO 4 — Crear venv
# ─────────────────────────────────────────────
def crear_venv(directorio: Path, python_sistema: Path, ui=None):
    if ui is None:
        titulo("Creando entorno virtual")
    else:
        ui.status("Creando entorno virtual...")
    venv_dir = directorio / "venv"

    if venv_dir.exists():
        msg = "El venv ya existe, omitiendo."
        info(msg) if ui is None else ui.log(msg)
    else:
        ctx = Spinner("Creando venv...") if ui is None else _nullcontext()
        with ctx:
            r = subprocess.run(
                [str(python_sistema), "-m", "venv", str(venv_dir)],
                capture_output=True, text=True
            )
        if r.returncode != 0:
            if ui is None:
                error("No se pudo crear el venv:")
                error(r.stderr[:300])
                sys.exit(1)
            else:
                ui.log(f"No se pudo crear el venv: {r.stderr[:300]}", level="error")
                raise RuntimeError("No se pudo crear el venv")
        ok("Venv creado.") if ui is None else ui.log("Venv creado.")

    if IS_WIN:
        python = venv_dir / "Scripts" / "python.exe"
        pip    = venv_dir / "Scripts" / "pip.exe"
    else:
        python = venv_dir / "bin" / "python"
        pip    = venv_dir / "bin" / "pip"

    ok(f"Python: {python}") if ui is None else ui.log(f"Python del venv: {python}")
    return python, pip

# ─────────────────────────────────────────────
# PASO 5 — Instalar dependencias base
# ─────────────────────────────────────────────
def instalar_dependencias(pip: Path, python: Path, cuda_tag: str, ui=None):
    if ui is None:
        titulo("Instalando dependencias base")
    else:
        ui.status("Instalando dependencias base...")

    def pip_install(args, descripcion):
        ctx = Spinner(descripcion) if ui is None else _nullcontext()
        if ui is not None:
            ui.log(descripcion)
        with ctx:
            r = subprocess.run(
                [str(pip)] + args,
                capture_output=True, text=True
            )
        if r.returncode != 0:
            if ui is None:
                warn(f"Advertencia en '{descripcion}':")
                warn(r.stderr[:200])
            else:
                ui.log(f"Advertencia en '{descripcion}': {r.stderr[:200]}", level="warn")
        else:
            ok(descripcion) if ui is None else ui.log(f"{descripcion} listo.")

    # Actualizar pip primero
    pip_install(["install", "--upgrade", "pip"], "Actualizando pip...")

    def _log(msg):
        info(msg) if ui is None else ui.log(msg)

    def _warn(msg):
        warn(msg) if ui is None else ui.log(msg, level="warn")

    # PyTorch con CUDA o CPU
    if cuda_tag != "cpu":
        torch_url = f"https://download.pytorch.org/whl/{cuda_tag}"
        _log(f"GPU detectada → instalando PyTorch con {cuda_tag}")
        pip_install(
            ["install", "torch", "torchaudio",
             "--index-url", torch_url],
            f"PyTorch + CUDA ({cuda_tag})..."
        )
    else:
        _log("Sin GPU → instalando PyTorch CPU")
        pip_install(["install", "torch", "torchaudio"], "PyTorch CPU...")

    # llama-cpp-python con wheels precompiladas (sin Build Tools)
    _log("Instalando llama-cpp-python (wheel precompilada, sin compilador)...")
    if cuda_tag != "cpu":
        llama_url = f"https://abetlen.github.io/llama-cpp-python/whl/{cuda_tag}"
    else:
        llama_url = "https://abetlen.github.io/llama-cpp-python/whl/cpu"

    ctx = Spinner("llama-cpp-python (wheel precompilada)...") if ui is None else _nullcontext()
    with ctx:
        r = subprocess.run(
            [str(pip), "install", "llama-cpp-python",
             "--extra-index-url", llama_url],
            capture_output=True, text=True
        )
    if r.returncode != 0:
        _warn("No se encontró wheel para esta versión de CUDA.")
        _warn("Intentando wheel CPU como alternativa...")
        pip_install(
            ["install", "llama-cpp-python",
             "--extra-index-url",
             "https://abetlen.github.io/llama-cpp-python/whl/cpu"],
            "llama-cpp-python (CPU fallback)..."
        )
    else:
        _log("llama-cpp-python instalado.")

    # PyQt6
    pip_install(["install", "PyQt6"], "PyQt6...")

    # psutil (para detección de hardware en setup.py)
    pip_install(["install", "psutil"], "psutil...")

    _log("Dependencias base listas.")

# ─────────────────────────────────────────────
# PASO 6 — Lanzar setup.py del proyecto
# ─────────────────────────────────────────────
def lanzar_setup(python: Path, directorio: Path):
    titulo("Lanzando instalador de SOFÍA")
    setup_path = directorio / "setup.py"

    if not setup_path.exists():
        error(f"No se encontró setup.py en {directorio}")
        error("El repositorio puede estar incompleto. Inténtalo de nuevo.")
        sys.exit(1)

    info("El instalador de SOFÍA continuará ahora.")
    info("Sigue las instrucciones en pantalla.")
    print()

    # --desde-bootstrap le dice a setup.py que ya tiene venv + deps base
    r = subprocess.run(
        [str(python), str(setup_path), "--desde-bootstrap"],
        cwd=str(directorio),
        env={**os.environ, "PYTHONPATH": str(directorio)},
    )

    return r.returncode

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    if IS_WIN:
        os.system("")  # activa modo VT100 para colores ANSI

    print(f"\n{C.BOLD}{C.BLUE}{'='*55}")
    print("       SOFÍA — Instalador")
    print(f"{'='*55}{C.RESET}")
    print(f"\n  {C.CYAN}Python {sys.version_info.major}.{sys.version_info.minor}{C.RESET}"
          f"  ·  {platform.system()} {platform.release()}")

    # Localizar un Python real del sistema (necesario para crear el venv
    # del proyecto; si estamos frozen, sys.executable no sirve para esto)
    titulo("Buscando Python instalado")
    python_sistema = localizar_python_sistema()
    if python_sistema is None:
        error("No se encontró un Python 3.10, 3.11 o 3.12 instalado en tu sistema.")
        error("SOFÍA necesita uno para crear su propio entorno virtual.")
        print()
        info("Descarga Python 3.11 en:")
        info("https://www.python.org/downloads/")
        print()
        info("IMPORTANTE: marca 'Add Python to PATH' durante la instalación.")
        input("\n  Presiona Enter para cerrar...")
        sys.exit(1)
    ok(f"Python encontrado: {python_sistema}")

    # Detectar GPU/CUDA antes de preguntar directorio
    titulo("Detectando hardware")
    cuda_tag = detectar_cuda()
    if cuda_tag != "cpu":
        ok(f"GPU NVIDIA detectada → usando {cuda_tag}")
    else:
        warn("Sin GPU NVIDIA detectada → se usará CPU (más lento)")

    # Directorio de instalación
    titulo("Directorio de instalación")
    info(f"Por defecto: {DIR_DEFECTO}")
    entrada = input("\n  Directorio (Enter para el defecto): ").strip()
    directorio = Path(entrada) if entrada else DIR_DEFECTO

    try:
        directorio.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        error(f"Sin permisos para crear {directorio}")
        error("Intenta ejecutar como administrador o elige otra carpeta.")
        input("\n  Presiona Enter para cerrar...")
        sys.exit(1)

    ok(f"Directorio: {directorio}")

    # Descargar repo
    zip_temporal = directorio / "_sofia_download.zip"
    if not descargar_repo(zip_temporal):
        input("\n  Presiona Enter para cerrar...")
        sys.exit(1)

    # Extraer
    if not extraer_repo(zip_temporal, directorio):
        input("\n  Presiona Enter para cerrar...")
        sys.exit(1)

    # Limpiar ZIP
    try:
        zip_temporal.unlink()
    except Exception:
        pass

    # Crear venv
    python, pip = crear_venv(directorio, python_sistema)

    # Instalar dependencias base
    instalar_dependencias(pip, python, cuda_tag)

    # Lanzar setup.py del proyecto
    codigo = lanzar_setup(python, directorio)

    if codigo == 0:
        print(f"\n{C.GREEN}{C.BOLD}{'='*55}")
        print("  ¡SOFÍA instalada correctamente!")
        print(f"  Inicia con: {directorio / 'iniciar_sofia.bat'}")
        print(f"{'='*55}{C.RESET}\n")
    else:
        print(f"\n{C.YELLOW}  La instalación terminó con advertencias.")
        print(f"  Revisa los mensajes arriba.{C.RESET}\n")

    input("  Presiona Enter para cerrar...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}  Instalación cancelada.{C.RESET}\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n{C.RED}  Error inesperado: {e}{C.RESET}")
        import traceback
        traceback.print_exc()
        input("\n  Presiona Enter para cerrar...")
        sys.exit(1)