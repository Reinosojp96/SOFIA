"""
Instalador de SOFIA - Asistente de Voz
Ejecutar con: python setup.py
Requiere: Python 3.10-3.12, conexión a internet, Git (opcional)
"""

import os
import sys
import subprocess
import platform
import shutil
import threading
import time
import json
from pathlib import Path
# paso_voz se importa después de instalar dependencias

# ─────────────────────────────────────────────
# Compatibilidad mínima
# ─────────────────────────────────────────────
if sys.version_info < (3, 10) or sys.version_info >= (3, 13):
    print(f"[ERROR] SOFIA requiere Python 3.10-3.12.")
    print(f"        Tienes Python {sys.version_info.major}.{sys.version_info.minor}")
    print("        Descarga Python 3.12 en https://python.org/downloads")
    sys.exit(1)

IS_WIN = platform.system() == "Windows"

# ─────────────────────────────────────────────
# Colores para terminal
# ─────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"

def ok(msg):    print(f"{C.GREEN}  ✓ {msg}{C.RESET}")
def info(msg):  print(f"{C.CYAN}  ℹ {msg}{C.RESET}")
def warn(msg):  print(f"{C.YELLOW}  ⚠ {msg}{C.RESET}")
def error(msg): print(f"{C.RED}  ✗ {msg}{C.RESET}")
def titulo(msg):
    print(f"\n{C.BOLD}{C.BLUE}{'─'*55}")
    print(f"  {msg}")
    print(f"{'─'*55}{C.RESET}")

# ─────────────────────────────────────────────
# Barra de progreso
# ─────────────────────────────────────────────
class Progreso:
    """Barra de progreso de terminal para descargas y procesos largos."""

    def __init__(self, total: int = 0, descripcion: str = ""):
        self.total = total
        self.desc  = descripcion
        self.actual = 0
        self._activo = False
        self._hilo   = None

    def actualizar(self, n: int):
        self.actual = n
        self._dibujar()

    def _dibujar(self):
        ancho = 40
        if self.total > 0:
            porcentaje = min(self.actual / self.total, 1.0)
            llenos = int(ancho * porcentaje)
            barra = "█" * llenos + "░" * (ancho - llenos)
            mb_actual = self.actual / 1_048_576
            mb_total  = self.total  / 1_048_576
            texto = f"\r  [{barra}] {porcentaje*100:.1f}%  {mb_actual:.0f}/{mb_total:.0f} MB"
        else:
            pos = int(time.time() * 5) % ancho
            barra = " " * pos + "███" + " " * (ancho - pos - 3)
            texto = f"\r  [{barra}]  {self.desc}"
        print(texto, end="", flush=True)

    def spinner(self, mensaje: str):
        """Animación de espera para procesos sin progreso medible."""
        frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._activo = True
        def _loop():
            i = 0
            while self._activo:
                print(f"\r  {C.CYAN}{frames[i % len(frames)]}{C.RESET} {mensaje}", end="", flush=True)
                time.sleep(0.1)
                i += 1
        self._hilo = threading.Thread(target=_loop, daemon=True)
        self._hilo.start()

    def detener(self, exito: bool = True):
        self._activo = False
        if self._hilo:
            self._hilo.join(timeout=0.5)
        print()  # salto de línea

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.detener()


# ─────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────
def ejecutar(cmd, descripcion="", mostrar_salida=False):
    p = Progreso()
    p.spinner(descripcion or " ".join(str(c) for c in cmd))
    resultado = subprocess.run(
        cmd,
        capture_output=not mostrar_salida,
        text=True,
    )
    p.detener(resultado.returncode == 0)
    if resultado.returncode != 0 and not mostrar_salida:
        warn(f"Salida de error:\n{resultado.stderr[:400]}")
    return resultado.returncode == 0


def preguntar_si_no(pregunta: str, defecto: bool = True) -> bool:
    sufijo = "[S/n]" if defecto else "[s/N]"
    resp = input(f"\n  {pregunta} {sufijo}: ").strip().lower()
    if not resp:
        return defecto
    return resp in ("s", "si", "sí", "y", "yes")


def elegir(opciones: list[str], pregunta: str, defecto: int = 1) -> int:
    print(f"\n  {pregunta}")
    for i, op in enumerate(opciones, 1):
        marca = f" {C.GREEN}(defecto){C.RESET}" if i == defecto else ""
        print(f"    {i}. {op}{marca}")
    while True:
        resp = input(f"  Elige [1-{len(opciones)}] (Enter={defecto}): ").strip()
        if not resp:
            return defecto
        if resp.isdigit() and 1 <= int(resp) <= len(opciones):
            return int(resp)
        error("Opción inválida.")


# ─────────────────────────────────────────────
# PASO 1: Directorio de instalación
# ─────────────────────────────────────────────
def paso_directorio() -> Path:
    titulo("PASO 1 — Directorio de instalación")

    if IS_WIN:
        defecto = Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "SOFIA"
    else:
        defecto = Path.home() / "sofia"

    info(f"Directorio por defecto: {defecto}")
    entrada = input(f"\n  Directorio de instalación (Enter para usar el defecto): ").strip()
    directorio = Path(entrada) if entrada else defecto

    directorio.mkdir(parents=True, exist_ok=True)
    ok(f"Directorio: {directorio}")
    return directorio


# ─────────────────────────────────────────────
# PASO 2: Obtener el código (git clone o copiar)
# ─────────────────────────────────────────────
def paso_codigo(directorio: Path):
    titulo("PASO 2 — Código fuente")

    # Si setup.py está dentro del repo ya clonado, no clonamos de nuevo
    script_dir = Path(__file__).parent.resolve()
    if (script_dir / "main.py").exists():
        info("El código ya está disponible en el directorio actual.")
        if script_dir != directorio:
            info(f"Copiando archivos a {directorio}...")
            for item in script_dir.iterdir():
                if item.name in {".git", "__pycache__", "venv", ".env"}:
                    continue
                destino = directorio / item.name
                if item.is_dir():
                    shutil.copytree(item, destino, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, destino)
            ok("Archivos copiados.")
        return

    # Intentar con git
    git_url = "https://github.com/TU_USUARIO/SOFIA.git"  # ← cambia por tu repo real
    if shutil.which("git"):
        if preguntar_si_no(f"¿Clonar desde GitHub ({git_url})?", defecto=True):
            exito = ejecutar(
                ["git", "clone", git_url, str(directorio)],
                "Clonando repositorio..."
            )
            if exito:
                ok("Repositorio clonado.")
                return
            else:
                error("No se pudo clonar. Verifica la URL o tu conexión.")
    else:
        warn("Git no está instalado. Descarga el ZIP manualmente desde GitHub.")
        info(f"URL: {git_url}")
        input("  Extrae el ZIP en el directorio de instalación y presiona Enter...")


# ─────────────────────────────────────────────
# PASO 3: Entorno virtual
# ─────────────────────────────────────────────
def paso_venv(directorio: Path) -> Path:
    titulo("PASO 3 — Entorno virtual (venv)")

    venv_dir = directorio / "venv"
    if venv_dir.exists():
        info("El venv ya existe.")
    else:
        exito = ejecutar(
            [sys.executable, "-m", "venv", str(venv_dir)],
            "Creando entorno virtual..."
        )
        if not exito:
            error("No se pudo crear el venv.")
            sys.exit(1)
        ok("Venv creado.")

    if IS_WIN:
        python = venv_dir / "Scripts" / "python.exe"
        pip    = venv_dir / "Scripts" / "pip.exe"
    else:
        python = venv_dir / "bin" / "python"
        pip    = venv_dir / "bin" / "pip"

    ok(f"Python del venv: {python}")
    return python, pip


# ─────────────────────────────────────────────
# PASO 4: Detección de hardware
# ─────────────────────────────────────────────
def paso_hardware(pip: Path) -> dict:
    titulo("PASO 4 — Detección de hardware")

    hardware = {
        "gpu_nombre": None,
        "gpu_vram_gb": 0,
        "ram_gb": 0,
        "cpu_nucleos": os.cpu_count() or 4,
        "espacio_gb": 0,
        "cuda_version": None,
        "cuda_whl": "cu126",
    }

    # RAM
    try:
        if IS_WIN:
            resultado = subprocess.run(
                ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory", "/value"],
                capture_output=True, text=True
            )
            for linea in resultado.stdout.split("\n"):
                if "TotalPhysicalMemory" in linea:
                    bytes_ram = int(linea.split("=")[1].strip())
                    hardware["ram_gb"] = round(bytes_ram / 1_073_741_824, 1)
        else:
            with open("/proc/meminfo") as f:
                for linea in f:
                    if "MemTotal" in linea:
                        kb = int(linea.split()[1])
                        hardware["ram_gb"] = round(kb / 1_048_576, 1)
    except Exception:
        pass

    # GPU y CUDA vía nvidia-smi
    try:
        resultado = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True
        )
        if resultado.returncode == 0:
            linea = resultado.stdout.strip().split("\n")[0]
            nombre, vram_mb = linea.split(",")
            hardware["gpu_nombre"] = nombre.strip()
            hardware["gpu_vram_gb"] = round(int(vram_mb.strip()) / 1024, 1)

        # Versión de CUDA
        resultado2 = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
        for linea in resultado2.stdout.split("\n"):
            if "CUDA Version" in linea:
                ver = linea.split("CUDA Version:")[-1].strip().split()[0]
                hardware["cuda_version"] = ver
                mayor, menor = ver.split(".")[:2]
                v = int(mayor) * 100 + int(menor) * 10
                if v >= 1280:
                    hardware["cuda_whl"] = "cu128"
                elif v >= 1260:
                    hardware["cuda_whl"] = "cu126"
                elif v >= 1240:
                    hardware["cuda_whl"] = "cu124"
                else:
                    hardware["cuda_whl"] = "cu118"
    except Exception:
        pass

    # Espacio disponible en disco
    try:
        stat = shutil.disk_usage(str(Path.home()))
        hardware["espacio_gb"] = round(stat.free / 1_073_741_824, 1)
    except Exception:
        pass

    # Mostrar resumen
    info(f"CPU: {hardware['cpu_nucleos']} núcleos")
    info(f"RAM: {hardware['ram_gb']} GB")
    if hardware["gpu_nombre"]:
        info(f"GPU: {hardware['gpu_nombre']} — {hardware['gpu_vram_gb']} GB VRAM")
        info(f"CUDA: {hardware['cuda_version']} → tag PyTorch: {hardware['cuda_whl']}")
    else:
        warn("No se detectó GPU Nvidia. Solo se instalarán componentes CPU.")
    info(f"Espacio libre: {hardware['espacio_gb']} GB")

    if hardware["espacio_gb"] < 5:
        warn("Menos de 5 GB libres. La instalación completa puede fallar.")

    return hardware


# ─────────────────────────────────────────────
# PASO 5: Preferencias del usuario
# ─────────────────────────────────────────────
def paso_preferencias(hardware: dict) -> dict:
    titulo("PASO 5 — Preferencias")

    prefs = {}

    # Nombre
    nombre = input("\n  ¿Cómo te llamas? (para el saludo): ").strip()
    prefs["nombre"] = nombre or "Usuario"

    # Ciudad
    ciudad = input("  Ciudad para el clima por defecto [Ibague]: ").strip()
    prefs["ciudad"] = ciudad or "Ibague"

    # Motor de voz
    tiene_gpu = hardware["gpu_nombre"] is not None
    tiene_vram = hardware["gpu_vram_gb"] >= 3.5

    print(f"\n  {C.BOLD}Voz de SOFÍA:{C.RESET}")
    if tiene_gpu and tiene_vram:
        opciones_tts = [
            "pyttsx3 — voz estándar del sistema (sin GPU, siempre funciona)",
            f"Qwen3-TTS 0.6B — voz natural con IA (GPU: {hardware['gpu_nombre']}, ~1.2 GB)",
        ]
        idx_tts = elegir(opciones_tts, "¿Qué motor de voz prefieres?", defecto=2)
    else:
        if tiene_gpu:
            warn(f"Tu GPU tiene {hardware['gpu_vram_gb']} GB VRAM. Qwen3-TTS necesita ~3.5 GB.")
        else:
            warn("Sin GPU Nvidia, Qwen3-TTS no está disponible.")
        info("Usando pyttsx3 (voz estándar).")
        idx_tts = 1
        opciones_tts = ["pyttsx3"]

    prefs["tts"] = "qwen" if idx_tts == 2 else "pyttsx3"

    if prefs["tts"] == "qwen":
        voces = ["Lucia", "Isabella", "Valentina", "Sofia", "Diego", "Alejandro"]
        idx_voz = elegir(voces, "Voz para SOFÍA (español nativo):", defecto=1)
        prefs["voz_speaker"] = voces[idx_voz - 1]

        instruccion = input(
            "  Estilo de voz (Enter para defecto 'tono cálido y profesional'): "
        ).strip()
        prefs["voz_instruccion"] = instruccion or \
            "Habla con tono cálido y profesional, ritmo fluido, acento neutro latinoamericano."

    # Micrófono
    mic = input(
        "\n  Nombre (o parte) de tu micrófono externo\n"
        "  (deja vacío para usar el micrófono por defecto del sistema): "
    ).strip()
    prefs["microfono"] = mic

    # Palabra de activación
    wake = input(
        "\n  Palabra de activación [sofia]: "
    ).strip().lower()
    prefs["wake_word"] = wake or "sofia"

    return prefs


# ─────────────────────────────────────────────
# PASO 6: Instalación de dependencias
# ─────────────────────────────────────────────
def paso_dependencias(pip: Path, hardware: dict, prefs: dict):
    titulo("PASO 6 — Instalación de dependencias")

    req_path = Path(__file__).parent / "requirements.txt"

    # PyTorch con CUDA si hay GPU
    if hardware["gpu_nombre"]:
        whl = hardware["cuda_whl"]
        torch_url = f"https://download.pytorch.org/whl/{whl}"
        info(f"Instalando PyTorch con {whl}...")
        ejecutar(
            [str(pip), "install", "torch", "torchaudio",
             "--index-url", torch_url],
            f"pip install torch torchaudio ({whl})..."
        )
    else:
        info("Instalando PyTorch CPU...")
        ejecutar(
            [str(pip), "install", "torch", "torchaudio"],
            "pip install torch torchaudio (CPU)..."
        )

    # Qwen TTS si se eligió
    if prefs["tts"] == "qwen":
        info("Instalando qwen-tts y soundfile...")
        ejecutar(
            [str(pip), "install", "qwen-tts", "soundfile"],
            "pip install qwen-tts soundfile..."
        )

    # Requirements base
    if req_path.exists():
        info("Instalando requirements.txt...")
        ejecutar(
            [str(pip), "install", "-r", str(req_path)],
            "pip install -r requirements.txt..."
        )
    else:
        # Dependencias mínimas hardcodeadas como fallback
        paquetes = [
            "faster-whisper", "sounddevice", "numpy",
            "pyttsx3", "requests", "llama-cpp-python",
            "PyQt6", "python-dotenv",
        ]
        ejecutar(
            [str(pip), "install"] + paquetes,
            "Instalando dependencias base..."
        )

    ok("Dependencias instaladas.")


# ─────────────────────────────────────────────
# PASO 7: Descarga de modelos
# ─────────────────────────────────────────────
def _descargar_hf(repo_id: str, destino: Path, descripcion: str):
    """Descarga un modelo de HuggingFace Hub con barra de progreso."""
    try:
        from huggingface_hub import snapshot_download
        p = Progreso()
        p.spinner(f"Descargando {descripcion}...")
        ruta = snapshot_download(repo_id=repo_id, local_dir=str(destino))
        p.detener(True)
        ok(f"{descripcion} → {ruta}")
        return True
    except Exception as e:
        error(f"Error descargando {descripcion}: {e}")
        return False


def _descargar_archivo(url: str, destino: Path, descripcion: str):
    """Descarga un archivo con barra de progreso real."""
    import urllib.request

    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        info(f"{descripcion} ya existe, omitiendo.")
        return True

    print(f"\n  Descargando {descripcion}...")
    try:
        progreso = Progreso(descripcion=descripcion)

        def callback(bloques, tam_bloque, tam_total):
            progreso.total = tam_total
            progreso.actualizar(bloques * tam_bloque)

        urllib.request.urlretrieve(url, str(destino), reporthook=callback)
        print()
        ok(f"{descripcion} descargado.")
        return True
    except Exception as e:
        error(f"Error: {e}")
        return False


def paso_modelos(directorio: Path, hardware: dict, prefs: dict):
    titulo("PASO 7 — Descarga de modelos")

    data_dir = directorio / "data"
    data_dir.mkdir(exist_ok=True)

    tiene_gpu   = hardware["gpu_nombre"] is not None
    vram        = hardware["gpu_vram_gb"]
    espacio     = hardware["espacio_gb"]

    # ── Whisper (se descarga automático al primer uso via faster-whisper,
    #    pero lo forzamos aquí para que no tarde en la primera ejecución)
    modelo_whisper = "base" if vram >= 4 or not tiene_gpu else "tiny"
    info(f"Modelo Whisper: {modelo_whisper}")
    try:
        from faster_whisper import WhisperModel
        p = Progreso()
        p.spinner(f"Descargando Whisper '{modelo_whisper}'...")
        WhisperModel(modelo_whisper, device="cpu", compute_type="int8")
        p.detener(True)
        ok(f"Whisper '{modelo_whisper}' listo.")
    except Exception as e:
        warn(f"No se pudo predescargar Whisper: {e}")

    # ── Silero-VAD (se descarga automático via torch.hub)
    try:
        import torch
        p = Progreso()
        p.spinner("Descargando Silero-VAD...")
        torch.hub.load("snakers4/silero-vad", "silero_vad", force_reload=False, onnx=False)
        p.detener(True)
        ok("Silero-VAD listo.")
    except Exception as e:
        warn(f"No se pudo predescargar Silero-VAD: {e}")

    # ── Qwen3-TTS
    if prefs["tts"] == "qwen":
        if preguntar_si_no("¿Descargar Qwen3-TTS 0.6B ahora? (~1.2 GB)", defecto=True):
            _descargar_hf(
                "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
                data_dir / "qwen3_tts",
                "Qwen3-TTS 0.6B"
            )

    # ── LLM (Qwen3-8B-Q4 ≈ 4.7 GB)
    modelo_llm = directorio / "data" / "modelo.gguf"
    if modelo_llm.exists():
        info("Modelo LLM ya existe.")
    else:
        # Recomendar según hardware
        if vram >= 8 or (not tiene_gpu and hardware["ram_gb"] >= 16):
            url_llm = "https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf"
            desc_llm = "Qwen3-8B Q4 (~4.7 GB) — calidad alta"
        else:
            url_llm = "https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q8_0.gguf"
            desc_llm = "Qwen3-0.6B Q8 (~0.7 GB) — ligero"

        if espacio < 6:
            warn(f"Poco espacio ({espacio} GB). El modelo LLM puede no caber.")

        info(f"Modelo LLM recomendado para tu hardware: {desc_llm}")
        if preguntar_si_no(f"¿Descargar {desc_llm}?", defecto=True):
            _descargar_archivo(url_llm, modelo_llm, "Modelo LLM")

    ok("Modelos listos.")


# ─────────────────────────────────────────────
# PASO 8: Generar .env
# ─────────────────────────────────────────────
def paso_env(directorio: Path, prefs: dict):
    titulo("PASO 8 — Configuración (.env)")

    lineas = [
        f"SOFIA_USER_NAME={prefs['nombre']}",
        f"SOFIA_CIUDAD={prefs['ciudad']}",
        f"SOFIA_TTS_MOTOR={prefs['tts']}",
        f"SOFIA_WAKE_WORD={prefs['wake_word']}",
    ]

    if prefs.get("microfono"):
        lineas.append(f"SOFIA_MIC_NAME={prefs['microfono']}")

    if prefs["tts"] == "qwen":
        modo = prefs.get("SOFIA_TTS_VOZ_MODO", "preset")
        lineas.append(f"SOFIA_TTS_VOZ_MODO={modo}")
        if modo == "preset":
            lineas.append(f"SOFIA_VOZ_SPEAKER={prefs.get('SOFIA_VOZ_SPEAKER', prefs.get('voz_speaker', 'Lucia'))}")
        elif prefs.get("VOZ_REF_PATH"):
            lineas.append(f"SOFIA_VOZ_REF_PATH={prefs['VOZ_REF_PATH']}")
        instruccion = prefs.get("SOFIA_VOZ_INSTRUCCION", prefs.get("voz_instruccion", ""))
        if instruccion:
            lineas.append(f"SOFIA_VOZ_INSTRUCCION={instruccion}")

    env_path = directorio / ".env"
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")

    ok(f".env generado en {env_path}")


# ─────────────────────────────────────────────
# PASO 9: Acceso directo
# ─────────────────────────────────────────────
def paso_acceso_directo(directorio: Path):
    titulo("PASO 9 — Acceso directo")

    if not IS_WIN:
        info("Acceso directo solo disponible en Windows.")
        return

    try:
        import winshell
        from win32com.client import Dispatch

        escritorio = Path(winshell.desktop())
        acceso = escritorio / "SOFÍA.lnk"

        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(acceso))
        shortcut.Targetpath = str(directorio / "venv" / "Scripts" / "pythonw.exe")
        shortcut.Arguments = f'"{directorio / "main.py"}"'
        shortcut.WorkingDirectory = str(directorio)
        shortcut.IconLocation = str(directorio / "ui" / "icon.ico") \
            if (directorio / "ui" / "icon.ico").exists() else ""
        shortcut.Description = "SOFÍA - Asistente de Voz"
        shortcut.save()
        ok(f"Acceso directo creado en el escritorio.")
    except ImportError:
        # winshell no siempre está disponible, crear .bat como alternativa
        bat = directorio / "iniciar_sofia.bat"
        with open(bat, "w") as f:
            f.write(f'@echo off\n')
            f.write(f'cd /d "{directorio}"\n')
            f.write(f'call venv\\Scripts\\activate\n')
            f.write(f'pythonw main.py\n')
        ok(f"Script de inicio creado: {bat}")
        info("Haz doble clic en 'iniciar_sofia.bat' para iniciar SOFÍA.")
    except Exception as e:
        warn(f"No se pudo crear el acceso directo: {e}")


# ─────────────────────────────────────────────
# PASO 10: Test rápido
# ─────────────────────────────────────────────
def paso_test(directorio: Path, prefs: dict):
    titulo("PASO 10 — Verificación final")

    errores = []

    # Verificar archivos clave
    archivos = ["main.py", "core/router.py", "skills/clima.py", "voz/escuchar.py", "voz/hablar.py"]
    for arch in archivos:
        if not (directorio / arch).exists():
            errores.append(f"Falta: {arch}")
        else:
            ok(f"Encontrado: {arch}")

    # Verificar modelo LLM
    modelo = directorio / "data" / "modelo.gguf"
    if modelo.exists():
        ok(f"Modelo LLM: {modelo.stat().st_size // 1_048_576} MB")
    else:
        warn("Modelo LLM no descargado. SOFÍA usará respuestas predeterminadas.")

    # Test de voz rápido
    if preguntar_si_no("¿Hacer una prueba de voz?", defecto=True):
        try:
            if prefs["tts"] == "pyttsx3":
                import pyttsx3
                engine = pyttsx3.init()
                engine.say("Hola, soy Sofía. Instalación completada.")
                engine.runAndWait()
                engine.stop()
                ok("Test de voz pyttsx3 exitoso.")
            else:
                info("El test de Qwen-TTS se hará al iniciar SOFIA por primera vez.")
        except Exception as e:
            warn(f"Test de voz fallido: {e}")

    if errores:
        error("Algunos archivos faltan. Verifica la instalación:")
        for e in errores:
            error(f"  {e}")
    else:
        print(f"\n{C.GREEN}{C.BOLD}{'='*55}")
        print("  ¡SOFÍA instalada correctamente!")
        print(f"  Para iniciar: python main.py")
        print(f"{'='*55}{C.RESET}\n")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print(f"\n{C.BOLD}{C.BLUE}{'='*55}")
    print("       SOFÍA — Instalador v1.0")
    print(f"{'='*55}{C.RESET}\n")
    info(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    info(f"Sistema: {platform.system()} {platform.release()}")

    directorio = paso_directorio()
    paso_codigo(directorio)
    python, pip = paso_venv(directorio)
    hardware    = paso_hardware(pip)
    prefs       = paso_preferencias(hardware)
    paso_dependencias(pip, hardware, prefs)

    # Configuración de voz — DESPUÉS de instalar dependencias
    # porque necesita qwen-tts ya instalado para generar muestras
    if prefs["tts"] == "qwen":
        try:
            sys.path.insert(0, str(directorio))
            from paso_voz import configurar_voz
            config_voz = configurar_voz()
            # Guardar en prefs para que paso_env las incluya en .env
            prefs.update(config_voz)
        except Exception as e:
            warn(f"Configuración de voz omitida: {e}")
            prefs["voz_speaker"]     = "Lucia"
            prefs["voz_instruccion"] = "Habla con tono cálido y profesional."

    paso_modelos(directorio, hardware, prefs)
    paso_env(directorio, prefs)
    paso_acceso_directo(directorio)
    paso_test(directorio, prefs)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}  Instalación cancelada por el usuario.{C.RESET}")
        sys.exit(0)