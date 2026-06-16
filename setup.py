"""
SOFÍA — Instalador v2.0
Ejecutar con: python setup.py

Arquitectura de dos fases:
  FASE 1 (Python del sistema): pasos 1-7
    - Directorio, código, venv, hardware, preferencias, dependencias
  FASE 2 (Python del venv):   pasos 8-13
    - Modelos, voz, .env, acceso directo, test
    - Invocada automáticamente por fase 1 vía subprocess

Requiere: Python 3.10-3.12
"""

import os, sys, subprocess, platform, shutil, threading, time, json, argparse
from pathlib import Path

# ─────────────────────────────────────────────
# Verificación de versión (solo en fase 1)
# ─────────────────────────────────────────────
if "--fase2" not in sys.argv:
    if sys.version_info < (3, 10) or sys.version_info >= (3, 13):
        print(f"[ERROR] SOFIA requiere Python 3.10-3.12.")
        print(f"        Tienes Python {sys.version_info.major}.{sys.version_info.minor}")
        print("        Descarga Python 3.12 en https://python.org/downloads")
        sys.exit(1)

IS_WIN = platform.system() == "Windows"

# ─────────────────────────────────────────────
# Colores
# ─────────────────────────────────────────────
class C:
    RESET = "\033[0m"; BOLD = "\033[1m"
    GREEN = "\033[92m"; YELLOW = "\033[93m"
    RED = "\033[91m"; CYAN = "\033[96m"; BLUE = "\033[94m"

def ok(msg):    print(f"{C.GREEN}  ✓ {msg}{C.RESET}")
def info(msg):  print(f"{C.CYAN}  ℹ {msg}{C.RESET}")
def warn(msg):  print(f"{C.YELLOW}  ⚠ {msg}{C.RESET}")
def error(msg): print(f"{C.RED}  ✗ {msg}{C.RESET}")

def titulo(n, msg):
    print(f"\n{C.BOLD}{C.BLUE}{'─'*55}")
    print(f"  PASO {n} — {msg}")
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
                print(f"\r  {C.CYAN}{frames[i%len(frames)]}{C.RESET} {self._msg}", end="", flush=True)
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
class BarraProgreso:
    def __init__(self, total=0):
        self.total = total; self.actual = 0
    def actualizar(self, n):
        self.actual = n; self._dibujar()
    def _dibujar(self):
        ancho = 40
        if self.total > 0:
            pct = min(self.actual / self.total, 1.0)
            llenos = int(ancho * pct)
            barra = "█" * llenos + "░" * (ancho - llenos)
            mb_a = self.actual / 1_048_576; mb_t = self.total / 1_048_576
            print(f"\r  [{barra}] {pct*100:.1f}%  {mb_a:.0f}/{mb_t:.0f} MB", end="", flush=True)

# ─────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────
def ejecutar_en_venv(pip_o_python: Path, args: list, descripcion=""):
    with Spinner(descripcion or " ".join(str(a) for a in args)):
        r = subprocess.run([str(pip_o_python)] + args, capture_output=True, text=True)
    if r.returncode != 0:
        warn(f"Salida de error:\n{r.stderr[:300]}")
    return r.returncode == 0

def elegir(opciones, pregunta, defecto=1):
    print(f"\n  {pregunta}")
    for i, op in enumerate(opciones, 1):
        marca = f" {C.GREEN}(defecto){C.RESET}" if i == defecto else ""
        print(f"    {i}. {op}{marca}")
    while True:
        r = input(f"  Elige [1-{len(opciones)}] (Enter={defecto}): ").strip()
        if not r: return defecto
        if r.isdigit() and 1 <= int(r) <= len(opciones): return int(r)
        print("  Opción inválida.")

def si_no(pregunta, defecto=True):
    s = "[S/n]" if defecto else "[s/N]"
    r = input(f"\n  {pregunta} {s}: ").strip().lower()
    return defecto if not r else r in ("s","si","sí","y","yes")

# ─────────────────────────────────────────────
# ════════════════════════════════════════════
#  FASE 1 — corre con el Python del sistema
# ════════════════════════════════════════════
# ─────────────────────────────────────────────

def paso1_directorio() -> Path:
    titulo(1, "Directorio de instalación")
    defecto = Path(os.environ.get("ProgramData","C:\\ProgramData")) / "SOFIA" \
              if IS_WIN else Path.home() / "sofia"
    info(f"Por defecto: {defecto}")
    entrada = input("\n  Directorio (Enter para el defecto): ").strip()
    directorio = Path(entrada) if entrada else defecto
    directorio.mkdir(parents=True, exist_ok=True)
    ok(f"Directorio: {directorio}")
    return directorio


def paso2_codigo(directorio: Path):
    titulo(2, "Código fuente")
    script_dir = Path(__file__).parent.resolve()
    if (script_dir / "main.py").exists():
        info("Código disponible en el directorio actual.")
        if script_dir != directorio:
            info(f"Copiando a {directorio}...")
            for item in script_dir.iterdir():
                if item.name in {".git","__pycache__","venv",".env"}: continue
                dst = directorio / item.name
                if item.is_dir(): shutil.copytree(item, dst, dirs_exist_ok=True)
                else: shutil.copy2(item, dst)
            ok("Archivos copiados.")
        return

    git_url = "https://github.com/TU_USUARIO/SOFIA.git"
    if shutil.which("git") and si_no(f"¿Clonar desde GitHub ({git_url})?"):
        with Spinner("Clonando repositorio..."):
            r = subprocess.run(["git","clone",git_url,str(directorio)],
                               capture_output=True, text=True)
        if r.returncode == 0: ok("Repositorio clonado.")
        else: error("No se pudo clonar. Descarga el ZIP manualmente.")
    else:
        warn("Descarga el ZIP desde GitHub, extráelo en el directorio de instalación.")
        input("  Presiona Enter cuando esté listo...")


def paso3_venv(directorio: Path):
    titulo(3, "Entorno virtual (venv)")
    venv_dir = directorio / "venv"
    if venv_dir.exists():
        info("El venv ya existe.")
    else:
        with Spinner("Creando venv..."):
            r = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)],
                               capture_output=True, text=True)
        if r.returncode != 0:
            error("No se pudo crear el venv.")
            sys.exit(1)
        ok("Venv creado.")
    if IS_WIN:
        python = venv_dir / "Scripts" / "python.exe"
        pip    = venv_dir / "Scripts" / "pip.exe"
    else:
        python = venv_dir / "bin" / "python"
        pip    = venv_dir / "bin"   / "pip"
    ok(f"Python del venv: {python}")
    return python, pip


def paso4_hardware_basico() -> dict:
    """Detección SIN torch ni psutil — solo herramientas del sistema."""
    titulo(4, "Detección de hardware")
    hw = {"gpu": None, "vram_gb": 0, "ram_gb": 0,
          "nucleos": os.cpu_count() or 4, "espacio_gb": 0,
          "cuda": None, "cuda_whl": "cu126"}
    # CPU / espacio
    try:
        stat = shutil.disk_usage(str(Path.home()))
        hw["espacio_gb"] = round(stat.free / 1_073_741_824, 1)
    except Exception: pass
    # RAM via PowerShell (más confiable que wmic en Win11)
    try:
        if IS_WIN:
            r = subprocess.run(
                ["powershell","-Command",
                 "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
                capture_output=True, text=True, timeout=8)
            val = r.stdout.strip()
            if val.isdigit():
                hw["ram_gb"] = round(int(val) / 1_073_741_824, 1)
        else:
            with open("/proc/meminfo") as f:
                for l in f:
                    if "MemTotal" in l:
                        hw["ram_gb"] = round(int(l.split()[1]) / 1_048_576, 1); break
    except Exception: pass
    # GPU via nvidia-smi
    try:
        r = subprocess.run(
            ["nvidia-smi","--query-gpu=name,memory.total","--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=6)
        if r.returncode == 0:
            nombre, vram_mb = r.stdout.strip().split("\n")[0].split(",")
            hw["gpu"]     = nombre.strip()
            hw["vram_gb"] = round(int(vram_mb.strip()) / 1024, 1)
        # CUDA version
        r2 = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=6)
        for l in r2.stdout.split("\n"):
            if "CUDA Version" in l:
                ver = l.split("CUDA Version:")[-1].strip().split()[0]
                hw["cuda"] = ver
                maj, mn = ver.split(".")[:2]
                v = int(maj)*100 + int(mn)*10
                hw["cuda_whl"] = "cu128" if v>=1280 else "cu126" if v>=1260 \
                                  else "cu124" if v>=1240 else "cu118"
    except Exception: pass
    # Mostrar
    info(f"CPU: {hw['nucleos']} núcleos")
    info(f"RAM: {hw['ram_gb']} GB" + (" (verificando con psutil en paso 6)" if hw["ram_gb"]==0 else ""))
    if hw["gpu"]:
        info(f"GPU: {hw['gpu']} — {hw['vram_gb']} GB VRAM")
        info(f"CUDA: {hw['cuda']} → PyTorch: {hw['cuda_whl']}")
    else:
        warn("Sin GPU Nvidia detectada.")
    info(f"Espacio libre: {hw['espacio_gb']} GB")
    return hw


def paso5_preferencias(hw: dict) -> dict:
    titulo(5, "Preferencias")
    p = {}
    p["nombre"] = input("\n  ¿Cómo te llamas? (para el saludo): ").strip() or "Usuario"
    ciudad = input("  Ciudad para el clima [Ibague]: ").strip()
    p["ciudad"] = ciudad or "Ibague"

    tiene_gpu  = hw["gpu"] is not None
    tiene_vram = hw["vram_gb"] >= 3.5

    print(f"\n  {C.BOLD}Motor de voz:{C.RESET}")
    if tiene_gpu and tiene_vram:
        idx = elegir([
            "pyttsx3 — voz estándar del sistema (sin GPU, siempre funciona)",
            f"Qwen3-TTS 0.6B — voz natural con IA (GPU: {hw['gpu']}, ~1.2 GB)",
        ], "¿Qué motor prefieres?", defecto=2)
    else:
        if tiene_gpu: warn(f"Tu GPU tiene {hw['vram_gb']} GB VRAM (mínimo 3.5 GB para Qwen-TTS).")
        else: warn("Sin GPU Nvidia, Qwen-TTS no disponible.")
        info("Se usará pyttsx3.")
        idx = 1
    p["tts"] = "qwen" if idx == 2 else "pyttsx3"

    mic = input("\n  Nombre de tu micrófono externo (vacío = micrófono por defecto): ").strip()
    p["mic"] = mic
    wake = input("  Palabra de activación [sofia]: ").strip().lower()
    p["wake"] = wake or "sofia"
    return p


def paso6_dependencias(pip: Path, hw: dict, prefs: dict):
    titulo(6, "Instalación de dependencias")
    info("Instalando psutil primero para verificar hardware...")
    ejecutar_en_venv(pip, ["install", "psutil"], "pip install psutil...")

    # Re-detectar RAM con psutil si quedó en 0
    if hw["ram_gb"] == 0:
        try:
            r = subprocess.run(
                [str(pip.parent / ("python.exe" if IS_WIN else "python")),
                 "-c", "import psutil; print(psutil.virtual_memory().total)"],
                capture_output=True, text=True)
            val = r.stdout.strip()
            if val.isdigit():
                hw["ram_gb"] = round(int(val) / 1_073_741_824, 1)
                ok(f"RAM detectada con psutil: {hw['ram_gb']} GB")
        except Exception: pass

    # PyTorch
    if hw["gpu"]:
        whl = hw["cuda_whl"]
        info(f"Instalando PyTorch con CUDA ({whl})...")
        ejecutar_en_venv(pip,
            ["install", "torch", "torchaudio",
             "--index-url", f"https://download.pytorch.org/whl/{whl}"],
            f"pip install torch torchaudio ({whl})...")
    else:
        info("Instalando PyTorch CPU...")
        ejecutar_en_venv(pip, ["install", "torch", "torchaudio"],
                         "pip install torch torchaudio (CPU)...")

    # Qwen-TTS si se eligió
    if prefs["tts"] == "qwen":
        ejecutar_en_venv(pip, ["install", "qwen-tts", "soundfile"],
                         "pip install qwen-tts soundfile...")

    # PyQt6 (siempre necesario para la UI)
    ejecutar_en_venv(pip, ["install", "PyQt6"], "pip install PyQt6...")

    # Requirements del proyecto
    req = Path(__file__).parent / "requirements.txt"
    if req.exists():
        ejecutar_en_venv(pip, ["install", "-r", str(req)],
                         "pip install -r requirements.txt...")
    else:
        paquetes = ["faster-whisper","sounddevice","numpy","pyttsx3",
                    "requests","llama-cpp-python","python-dotenv","pydub"]
        ejecutar_en_venv(pip, ["install"] + paquetes,
                         "Instalando dependencias base...")
    ok("Dependencias instaladas.")


def _guardar_estado(directorio: Path, hw: dict, prefs: dict):
    """Guarda hw + prefs en un JSON temporal para pasarlos a fase 2."""
    estado = {"hw": hw, "prefs": prefs}
    ruta = directorio / ".setup_state.json"
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    return ruta


def fase1():
    print(f"\n{C.BOLD}{C.BLUE}{'='*55}")
    print("       SOFÍA — Instalador v2.0")
    print(f"{'='*55}{C.RESET}")
    info(f"Python {sys.version_info.major}.{sys.version_info.minor} · {platform.system()}")

    directorio = paso1_directorio()
    paso2_codigo(directorio)
    python, pip = paso3_venv(directorio)
    hw    = paso4_hardware_basico()
    prefs = paso5_preferencias(hw)
    paso6_dependencias(pip, hw, prefs)

    estado_path = _guardar_estado(directorio, hw, prefs)

    print(f"\n{C.BOLD}{C.BLUE}{'─'*55}")
    print("  Dependencias listas. Continuando con el venv...")
    print(f"{'─'*55}{C.RESET}\n")

    # Relanzar este mismo script con el Python del venv en fase 2
    r = subprocess.run(
        [str(python), str(directorio / "setup.py"),
         "--fase2", str(directorio), str(estado_path)],
        env={**os.environ, "PYTHONPATH": str(directorio)},
    )
    sys.exit(r.returncode)


# ─────────────────────────────────────────────
# ════════════════════════════════════════════
#  FASE 2 — corre con el Python del VENV
# ════════════════════════════════════════════
# ─────────────────────────────────────────────

def paso7_re_detectar_hw(hw: dict) -> dict:
    """Verificación con psutil y torch ya disponibles en el venv."""
    titulo(7, "Verificación de hardware (con venv)")
    try:
        import psutil
        hw["ram_gb"] = round(psutil.virtual_memory().total / 1_073_741_824, 1)
        ok(f"RAM: {hw['ram_gb']} GB")
    except Exception: pass
    try:
        import torch
        hw["cuda_disponible"] = torch.cuda.is_available()
        if hw["cuda_disponible"]:
            nombre = torch.cuda.get_device_name(0)
            vram   = torch.cuda.get_device_properties(0).total_memory / 1_073_741_824
            hw["gpu"]     = nombre
            hw["vram_gb"] = round(vram, 1)
            ok(f"GPU (torch): {nombre} — {hw['vram_gb']:.1f} GB VRAM")
    except Exception: pass
    return hw


def paso8_modelos(directorio: Path, hw: dict, prefs: dict):
    titulo(8, "Descarga de modelos")
    import warnings; warnings.filterwarnings("ignore")
    data_dir = directorio / "data"
    data_dir.mkdir(exist_ok=True)

    vram    = hw.get("vram_gb", 0)
    ram     = hw.get("ram_gb", 8)
    espacio = hw.get("espacio_gb", 20)

    # ── Whisper ──
    modelo_whisper = "base" if vram >= 4 else "tiny"
    info(f"Descargando Whisper '{modelo_whisper}'...")
    try:
        from faster_whisper import WhisperModel
        with Spinner(f"Whisper '{modelo_whisper}'..."):
            WhisperModel(modelo_whisper, device="cpu", compute_type="int8")
        ok(f"Whisper '{modelo_whisper}' listo.")
    except Exception as e:
        warn(f"No se pudo predescargar Whisper: {e}")

    # ── Silero-VAD ──
    try:
        import torch
        with Spinner("Silero-VAD..."):
            torch.hub.load("snakers4/silero-vad","silero_vad",
                           force_reload=False, onnx=False)
        ok("Silero-VAD listo.")
    except Exception as e:
        warn(f"No se pudo predescargar Silero-VAD: {e}")

    # ── Qwen3-TTS ──
    if prefs["tts"] == "qwen":
        tts_dir = data_dir / "qwen3_tts"
        if tts_dir.exists() and any(tts_dir.iterdir()):
            info("Qwen3-TTS CustomVoice ya descargado.")
        elif si_no("¿Descargar Qwen3-TTS 0.6B ahora? (~1.2 GB)", defecto=True):
            try:
                from huggingface_hub import snapshot_download
                with Spinner("Descargando Qwen3-TTS 0.6B CustomVoice..."):
                    snapshot_download(
                        repo_id="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
                        local_dir=str(tts_dir)
                    )
                ok("Qwen3-TTS CustomVoice descargado.")
            except Exception as e:
                warn(f"Error: {e}. El modelo se descargará al primer arranque.")

        # Modelo Base — necesario para clonación de voz
        # Se descarga aquí para que no haya descarga al primer arranque
        tts_base_dir = data_dir / "qwen3_tts_base"
        if tts_base_dir.exists() and any(tts_base_dir.iterdir()):
            info("Qwen3-TTS Base ya descargado.")
        elif si_no("¿Descargar Qwen3-TTS Base 0.6B? (~1.8 GB, necesario para clonar voz)", defecto=True):
            try:
                from huggingface_hub import snapshot_download
                with Spinner("Descargando Qwen3-TTS 0.6B Base..."):
                    snapshot_download(
                        repo_id="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                        local_dir=str(tts_base_dir)
                    )
                ok("Qwen3-TTS Base descargado.")
            except Exception as e:
                warn(f"Error: {e}. El modelo Base se descargará al primer uso.")

    # ── LLM ──
    modelo_llm = data_dir / "modelo.gguf"
    if modelo_llm.exists():
        info(f"Modelo LLM ya existe ({modelo_llm.stat().st_size//1_048_576} MB).")
    else:
        if vram >= 8 or (not hw.get("gpu") and ram >= 16):
            url_llm  = "https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf"
            desc_llm = "Qwen3-8B Q4 (~4.7 GB) — calidad alta"
        else:
            url_llm  = "https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q8_0.gguf"
            desc_llm = "Qwen3-0.6B Q8 (~0.7 GB) — ligero"

        info(f"LLM recomendado: {desc_llm}")
        if espacio < 6:
            warn(f"Solo {espacio} GB libres — el modelo puede no caber.")

        if si_no(f"¿Descargar {desc_llm}?", defecto=True):
            import urllib.request
            barra = BarraProgreso()
            def cb(bloques, tam, total):
                barra.total = total; barra.actualizar(bloques * tam)
            try:
                urllib.request.urlretrieve(url_llm, str(modelo_llm), reporthook=cb)
                print(); ok("Modelo LLM descargado.")
            except Exception as e:
                print(); error(f"Error: {e}")
                if modelo_llm.exists(): modelo_llm.unlink()

    ok("Modelos listos.")


def paso9_configurar_voz(directorio: Path, prefs: dict) -> dict:
    titulo(9, "Configuración de voz")
    if prefs["tts"] != "qwen":
        info("Motor pyttsx3 seleccionado — sin configuración de voz adicional.")
        return {}
    try:
        sys.path.insert(0, str(directorio))
        from paso_voz import configurar_voz
        return configurar_voz()
    except Exception as e:
        warn(f"Configuración de voz omitida: {e}")
        return {"SOFIA_TTS_VOZ_MODO": "preset", "SOFIA_VOZ_SPEAKER": "serena"}


def paso10_env(directorio: Path, prefs: dict, config_voz: dict):
    titulo(10, "Generando .env")
    lineas = [
        f"SOFIA_USER_NAME={prefs['nombre']}",
        f"SOFIA_CIUDAD={prefs['ciudad']}",
        f"SOFIA_TTS_MOTOR={prefs['tts']}",
        f"SOFIA_WAKE_WORD={prefs['wake']}",
    ]
    if prefs.get("mic"):
        lineas.append(f"SOFIA_MIC_NAME={prefs['mic']}")

    if prefs["tts"] == "qwen":
        modo = config_voz.get("SOFIA_TTS_VOZ_MODO", "preset")
        lineas.append(f"SOFIA_TTS_VOZ_MODO={modo}")
        if modo == "preset":
            lineas.append(f"SOFIA_VOZ_SPEAKER={config_voz.get('SOFIA_VOZ_SPEAKER','serena')}")
        if config_voz.get("SOFIA_VOZ_REF_PATH"):
            lineas.append(f"SOFIA_VOZ_REF_PATH={config_voz['SOFIA_VOZ_REF_PATH']}")
        if config_voz.get("SOFIA_VOZ_INSTRUCCION"):
            lineas.append(f"SOFIA_VOZ_INSTRUCCION={config_voz['SOFIA_VOZ_INSTRUCCION']}")

    env_path = directorio / ".env"
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    ok(f".env generado: {env_path}")


def paso11_acceso_directo(directorio: Path):
    titulo(11, "Acceso directo")
    if not IS_WIN:
        info("Solo disponible en Windows por ahora.")
        return
    bat = directorio / "iniciar_sofia.bat"
    with open(bat, "w", encoding="utf-8") as f:
        f.write(f'@echo off\n')
        f.write(f'cd /d "{directorio}"\n')
        f.write(f'call venv\\Scripts\\activate\n')
        # python.exe (con consola) en lugar de pythonw.exe para que
        # sounddevice y pyttsx3 funcionen correctamente
        f.write(f'start /B python main.py\n')
    ok(f"Script de inicio: {bat}")
    info("Haz doble clic en 'iniciar_sofia.bat' para iniciar SOFÍA.")


def paso12_test(directorio: Path, prefs: dict):
    titulo(12, "Verificación final")
    archivos = ["main.py","core/router.py","skills/clima.py",
                "voz/escuchar.py","voz/hablar.py"]
    todos_ok = True
    for arch in archivos:
        if (directorio / arch).exists(): ok(f"Encontrado: {arch}")
        else: error(f"Falta: {arch}"); todos_ok = False

    modelo_llm = directorio / "data" / "modelo.gguf"
    if modelo_llm.exists():
        ok(f"Modelo LLM: {modelo_llm.stat().st_size//1_048_576} MB")
    else:
        warn("Modelo LLM no descargado. SOFÍA usará respuestas básicas.")

    if si_no("¿Hacer prueba de voz?", defecto=True):
        try:
            if prefs["tts"] == "pyttsx3":
                import pyttsx3
                e = pyttsx3.init(); e.say("Hola, instalación completada."); e.runAndWait(); e.stop()
                ok("Test de voz exitoso.")
            else:
                info("El test de Qwen-TTS ocurre al primer arranque de SOFIA.")
        except Exception as e:
            warn(f"Test de voz: {e}")

    if todos_ok:
        print(f"\n{C.GREEN}{C.BOLD}{'='*55}")
        print("  ¡SOFÍA instalada correctamente!")
        print(f"  Inicia con: iniciar_sofia.bat")
        print(f"  O con:      python main.py  (con el venv activo)")
        print(f"{'='*55}{C.RESET}\n")
    else:
        print(f"\n{C.YELLOW}  Instalación incompleta. Revisa los errores arriba.{C.RESET}\n")


def fase2(directorio: Path, estado_path: Path):
    import warnings; warnings.filterwarnings("ignore")

    with open(estado_path, encoding="utf-8") as f:
        estado = json.load(f)
    hw    = estado["hw"]
    prefs = estado["prefs"]

    # Limpieza: borrar estado temporal
    try: estado_path.unlink()
    except Exception: pass

    hw         = paso7_re_detectar_hw(hw)
    paso8_modelos(directorio, hw, prefs)
    config_voz = paso9_configurar_voz(directorio, prefs)
    paso10_env(directorio, prefs, config_voz)
    paso11_acceso_directo(directorio)
    paso12_test(directorio, prefs)


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    try:
        if "--fase2" in sys.argv:
            idx = sys.argv.index("--fase2")
            directorio   = Path(sys.argv[idx + 1])
            estado_path  = Path(sys.argv[idx + 2])
            fase2(directorio, estado_path)
        else:
            fase1()
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}  Instalación cancelada.{C.RESET}")
        sys.exit(0)