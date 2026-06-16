"""
Módulo de configuración de voz para setup.py
Se importa desde setup.py después de instalar dependencias.

v2: 
  - Opción de cargar grabación existente (.wav/.mp3)
  - Voces se escuchan ANTES de elegir (en el propio setup)
  - Mejor manejo de errores
"""

import os
import sys
import time
import threading
import tempfile
from pathlib import Path

from gui_protocol import GUI_MODE, pedir as input


class C:
    RESET  = ""  if GUI_MODE else "\033[0m"
    BOLD   = ""  if GUI_MODE else "\033[1m"
    GREEN  = ""  if GUI_MODE else "\033[92m"
    YELLOW = ""  if GUI_MODE else "\033[93m"
    RED    = ""  if GUI_MODE else "\033[91m"
    CYAN   = ""  if GUI_MODE else "\033[96m"
    BLUE   = ""  if GUI_MODE else "\033[94m"

def ok(msg):   print(f"{C.GREEN}  ✓ {msg}{C.RESET}")
def info(msg): print(f"{C.CYAN}  ℹ {msg}{C.RESET}")
def warn(msg): print(f"{C.YELLOW}  ⚠ {msg}{C.RESET}")


# Voces REALES del modelo Qwen3-TTS-0.6B-CustomVoice
# (el 1.7B tiene Lucia/Sofia/etc, el 0.6B tiene estos IDs)
# Usamos nombres amigables en pantalla pero el ID real para el modelo.
VOCES = [
    {"id": "serena",   "nombre": "Serena",   "descripcion": "Femenina · tono suave y cálido",
     "muestra": "Hola, puedo ser la voz de tu asistente SOFÍA. ¿En qué puedo ayudarte hoy?"},
    {"id": "vivian",   "nombre": "Vivian",   "descripcion": "Femenina · tono claro y profesional",
     "muestra": "Hola, estoy lista para ayudarte en lo que necesites hoy."},
    {"id": "ono_anna", "nombre": "Anna",     "descripcion": "Femenina · tono neutro y preciso",
     "muestra": "Hola, tu asistente de voz personal está lista para ayudarte."},
    {"id": "sohee",    "nombre": "Sohee",    "descripcion": "Femenina · tono joven y dinámico",
     "muestra": "Hola, dime qué necesitas y lo resolvemos juntos ahora mismo."},
    {"id": "aiden",    "nombre": "Aiden",    "descripcion": "Masculino · tono seguro y maduro",
     "muestra": "Hola, dime en qué puedo ayudarte hoy."},
    {"id": "dylan",    "nombre": "Dylan",    "descripcion": "Masculino · tono amigable y cercano",
     "muestra": "Hola, estoy aquí para lo que necesites. ¿Cómo puedo ayudarte?"},
    {"id": "ryan",     "nombre": "Ryan",     "descripcion": "Masculino · tono claro y directo",
     "muestra": "Hola, soy tu asistente de voz. Dime cómo puedo ayudarte."},
]


class Spinner:
    def __init__(self, msg=""):
        self._activo = False
        self._msg = msg
        self._hilo = None

    def __enter__(self):
        if GUI_MODE:
            print(f"  {self._msg}", flush=True)
            return self
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
        if self._hilo:
            self._hilo.join(timeout=0.5)
        if not GUI_MODE:
            print()


_modelo_tts = None
_modelo_base = None


def _cargar_modelo_custom():
    global _modelo_tts
    if _modelo_tts is not None:
        return _modelo_tts
    try:
        import torch
        from qwen_tts import Qwen3TTSModel
        with Spinner("Cargando Qwen3-TTS para las muestras..."):
            _modelo_tts = Qwen3TTSModel.from_pretrained(
                "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
                device_map="cuda:0",
                dtype=torch.bfloat16,
            )
        ok("Modelo TTS listo.")
        return _modelo_tts
    except Exception as e:
        warn(f"No se pudo cargar Qwen-TTS: {e}")
        return None


def _cargar_modelo_base():
    global _modelo_base
    if _modelo_base is not None:
        return _modelo_base
    try:
        import torch
        from qwen_tts import Qwen3TTSModel
        with Spinner("Cargando modelo de clonación..."):
            _modelo_base = Qwen3TTSModel.from_pretrained(
                "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                device_map="cuda:0",
                dtype=torch.bfloat16,
            )
        ok("Modelo de clonación listo.")
        return _modelo_base
    except Exception as e:
        warn(f"No se pudo cargar modelo de clonación: {e}")
        return None


def _reproducir(audio, sr: int):
    try:
        import sounddevice as sd
        sd.play(audio, samplerate=sr)
        sd.wait()
    except Exception as e:
        warn(f"No se pudo reproducir: {e}")


def _generar_muestra(modelo, voz: dict):
    try:
        with Spinner(f"Generando muestra de {voz['id']}..."):
            wavs, sr = modelo.generate_custom_voice(
                text=voz["muestra"],
                language="Spanish",
                speaker=voz["id"],
                instruct="Habla con tono cálido y natural.",
            )
        return wavs[0], sr
    except Exception as e:
        warn(f"Error generando muestra de {voz['id']}: {e}")
        return None, None


def _convertir_a_numpy_wav(ruta: Path):
    """
    Carga un archivo de audio (.wav o .mp3) y lo convierte a
    numpy float32 a 16kHz (formato que necesita Qwen3-TTS para clonar).
    """
    import numpy as np
    try:
        import soundfile as sf
        audio, sr = sf.read(str(ruta), dtype="float32")
        # Si es estéreo, convertir a mono
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        # Resamplear a 16kHz si es necesario
        if sr != 16000:
            try:
                import torchaudio
                import torch
                tensor = torch.tensor(audio).unsqueeze(0)
                resampleado = torchaudio.functional.resample(tensor, sr, 16000)
                audio = resampleado.squeeze(0).numpy()
                sr = 16000
            except Exception:
                warn("No se pudo resamplear. Se usará el audio tal cual (puede afectar calidad).")
        return audio, sr
    except Exception:
        # Intentar con pydub para MP3
        try:
            from pydub import AudioSegment
            seg = AudioSegment.from_file(str(ruta))
            seg = seg.set_channels(1).set_frame_rate(16000)
            muestras = np.array(seg.get_array_of_samples(), dtype=np.float32)
            muestras /= 32768.0
            return muestras, 16000
        except Exception as e:
            warn(f"No se pudo cargar el archivo de audio: {e}")
            return None, None


def _grabar_voz(duracion: int = 5, sr: int = 16000):
    try:
        import numpy as np
        import sounddevice as sd
        print(f"\n  {C.YELLOW}Habla durante {duracion} segundos cuando veas '▶ Grabando...'{C.RESET}")
        input("  Presiona Enter cuando estés listo...")
        grabacion = sd.rec(int(duracion * sr), samplerate=sr, channels=1, dtype="float32")
        for i in range(duracion, 0, -1):
            print(f"\r  {C.RED}▶ Grabando... {i}s{C.RESET}", end="", flush=True)
            time.sleep(1)
        sd.wait()
        print(f"\r  {C.GREEN}✓ Grabación completada.{C.RESET}       ")
        return grabacion[:, 0], sr
    except Exception as e:
        warn(f"Error durante la grabación: {e}")
        return None, None


def _preview_clonacion(modelo_base, audio_ref, sr_ref, ref_text: str = ""):
    try:
        with Spinner("Generando preview con tu voz..."):
            wavs, sr = modelo_base.generate_voice_clone(
                text="Hola, soy SOFÍA. Esta es mi voz. ¿En qué puedo ayudarte hoy?",
                language="Spanish",
                ref_audio=(audio_ref, sr_ref),
                ref_text=ref_text,
            )
        return wavs[0], sr
    except Exception as e:
        warn(f"Error generando preview: {e}")
        return None, None


# ─────────────────────────────────────────────
# Flujo principal exportado
# ─────────────────────────────────────────────

def configurar_voz() -> dict:
    print(f"\n{C.BOLD}{C.BLUE}{'─'*55}")
    print("  Configuración de voz de SOFÍA")
    print(f"{'─'*55}{C.RESET}")

    # ── Elegir modo ──────────────────────────
    print(f"\n  {C.BOLD}¿Qué tipo de voz quieres para SOFÍA?{C.RESET}")
    print("    1. Elegir una voz de la lista (puedes escucharlas antes)")
    print("    2. Clonar una voz — grabar ahora con el micrófono")
    print("    3. Clonar una voz — usar grabación existente (.wav o .mp3)")

    while True:
        resp = input("  Elige [1/2/3] (Enter=1): ").strip()
        if resp in ("", "1"): modo = "preset"; break
        elif resp == "2":     modo = "grabar";  break
        elif resp == "3":     modo = "archivo"; break
        else: print("  Opción inválida.")

    resultado = {}

    # ═══════════════════════════════════════════
    # MODO PRESET
    # ═══════════════════════════════════════════
    if modo == "preset":
        modelo = _cargar_modelo_custom()

        print(f"\n  {C.BOLD}Voces disponibles:{C.RESET}")
        for i, v in enumerate(VOCES, 1):
            nombre_display = v.get("nombre", v["id"])
            print(f"    {i}. {C.CYAN}{nombre_display}{C.RESET} — {v['descripcion']}")

        print(f"\n  {C.BOLD}Comandos:{C.RESET}")
        print("    · Número (ej: 3)      → escuchar muestra de esa voz")
        print("    · 'todas'             → escuchar todas en secuencia")
        print("    · 'ok N' (ej: ok 2)   → confirmar la voz N")

        voz_elegida = None
        while True:
            cmd = input("\n  > ").strip().lower()

            if cmd == "todas":
                if modelo is None:
                    warn("Modelo no disponible, no se pueden generar muestras.")
                    continue
                for i, voz in enumerate(VOCES, 1):
                    print(f"\n  [{i}/{len(VOCES)}] {voz['id']}...")
                    audio, sr = _generar_muestra(modelo, voz)
                    if audio is not None:
                        _reproducir(audio, sr)
                    time.sleep(0.3)

            elif cmd.isdigit() and 1 <= int(cmd) <= len(VOCES):
                voz = VOCES[int(cmd) - 1]
                if modelo is None:
                    warn("Modelo no disponible para generar muestras.")
                    continue
                print(f"\n  Escuchando {voz['id']}...")
                audio, sr = _generar_muestra(modelo, voz)
                if audio is not None:
                    _reproducir(audio, sr)

            elif cmd.startswith("ok "):
                partes = cmd.split()
                if len(partes) == 2 and partes[1].isdigit():
                    idx = int(partes[1])
                    if 1 <= idx <= len(VOCES):
                        voz_elegida = VOCES[idx - 1]
                        ok(f"Voz seleccionada: {voz_elegida.get('nombre', voz_elegida['id'])}")
                        break
                print("  Formato: ok N  (ej: ok 3)")

            elif cmd.isdigit():
                print(f"  Número fuera de rango. Elige entre 1 y {len(VOCES)}.")
            else:
                print("  No entendí. Escribe un número, 'todas' o 'ok N'.")

        resultado["SOFIA_TTS_VOZ_MODO"] = "preset"
        resultado["SOFIA_VOZ_SPEAKER"]  = voz_elegida["id"]

    # ═══════════════════════════════════════════
    # MODO CLONAR — GRABAR
    # ═══════════════════════════════════════════
    elif modo == "grabar":
        modelo_base = _cargar_modelo_base()
        if modelo_base is None:
            warn("No se pudo cargar el modelo de clonación. Usando voz Lucia por defecto.")
            resultado["SOFIA_TTS_VOZ_MODO"] = "preset"
            resultado["SOFIA_VOZ_SPEAKER"]  = "Lucia"
        else:
            info("Graba 5 segundos de tu voz leyendo cualquier texto natural.")
            info("Ejemplo: 'Buenos días. Hoy es un día perfecto para aprender.'")

            audio_ref = sr_ref = None
            ref_text_grabacion = ""
            while True:
                print(f"\n  {C.BOLD}¿Qué vas a decir en la grabación?{C.RESET}")
                print("  Escribe el texto que vas a leer (para que el modelo sepa qué se dice).")
                print("  Ejemplo: 'Buenos días. Hoy es un día perfecto para aprender cosas nuevas.'")
                ref_text_grabacion = input("  Texto a leer: ").strip()
                if not ref_text_grabacion:
                    warn("El texto es obligatorio para la clonación de voz.")
                    continue

                audio_ref, sr_ref = _grabar_voz(duracion=5)
                if audio_ref is None:
                    if input("  ¿Intentar de nuevo? [s/n]: ").strip().lower() != "s":
                        break
                    continue

                audio_prev, sr_prev = _preview_clonacion(modelo_base, audio_ref, sr_ref, ref_text_grabacion)
                if audio_prev is not None:
                    print(f"  {C.CYAN}Reproduciendo preview...{C.RESET}")
                    _reproducir(audio_prev, sr_prev)
                    if input("\n  ¿Te gusta? [S/n]: ").strip().lower() not in ("n","no"):
                        break
                info("Grabemos de nuevo.")

            if audio_ref is not None:
                ref_path = Path(__file__).parent / "data" / "voz_referencia.wav"
                ref_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    import soundfile as sf
                    sf.write(str(ref_path), audio_ref, sr_ref)
                    # Guardar también el texto de referencia
                    ref_text_path = ref_path.parent / "voz_referencia_texto.txt"
                    ref_text_path.write_text(ref_text_grabacion, encoding="utf-8")
                    ok(f"Voz de referencia guardada: {ref_path}")
                    resultado["SOFIA_TTS_VOZ_MODO"] = "clon"
                    resultado["SOFIA_VOZ_REF_PATH"] = str(ref_path)
                    resultado["SOFIA_VOZ_REF_TEXT"] = ref_text_grabacion
                except Exception as e:
                    warn(f"No se pudo guardar: {e}")
                    resultado["SOFIA_TTS_VOZ_MODO"] = "preset"
                    resultado["SOFIA_VOZ_SPEAKER"]  = "Lucia"
            else:
                resultado["SOFIA_TTS_VOZ_MODO"] = "preset"
                resultado["SOFIA_VOZ_SPEAKER"]  = "Lucia"

    # ═══════════════════════════════════════════
    # MODO CLONAR — ARCHIVO EXISTENTE
    # ═══════════════════════════════════════════
    elif modo == "archivo":
        modelo_base = _cargar_modelo_base()
        if modelo_base is None:
            warn("No se pudo cargar el modelo de clonación. Usando voz Lucia.")
            resultado["SOFIA_TTS_VOZ_MODO"] = "preset"
            resultado["SOFIA_VOZ_SPEAKER"]  = "Lucia"
        else:
            info("Ingresa la ruta completa al archivo de audio (.wav o .mp3).")
            info("El archivo debe tener al menos 3 segundos de voz limpia.")

            audio_ref = sr_ref = None
            while True:
                ruta_str = input("\n  Ruta del archivo: ").strip().strip('"\'')
                ruta = Path(ruta_str)

                if not ruta.exists():
                    warn(f"No se encontró el archivo: {ruta}")
                    if input("  ¿Intentar con otra ruta? [s/n]: ").strip().lower() != "s":
                        break
                    continue

                if ruta.suffix.lower() not in (".wav", ".mp3", ".ogg", ".flac", ".m4a"):
                    warn("Formato no reconocido. Usa .wav, .mp3, .ogg, .flac o .m4a")
                    continue

                info(f"Cargando {ruta.name}...")
                audio_ref, sr_ref = _convertir_a_numpy_wav(ruta)

                if audio_ref is None:
                    warn("No se pudo cargar el archivo.")
                    if input("  ¿Intentar con otro archivo? [s/n]: ").strip().lower() != "s":
                        break
                    continue

                duracion_seg = len(audio_ref) / sr_ref
                info(f"Audio cargado: {duracion_seg:.1f} segundos a {sr_ref} Hz")

                if duracion_seg < 3:
                    warn("El audio es muy corto (menos de 3 segundos). La calidad puede ser baja.")

                # Pedir transcripción del audio de referencia
                print(f"\n  {C.BOLD}¿Qué dice el audio que acabas de cargar?{C.RESET}")
                print("  Escribe el texto que se habla en la grabación.")
                print("  Esto ayuda al modelo a clonar la voz con mayor precisión.")
                ref_text_archivo = input("  Transcripción: ").strip()
                if not ref_text_archivo:
                    warn("Sin transcripción la calidad de clonación será menor.")

                # Preview
                audio_prev, sr_prev = _preview_clonacion(modelo_base, audio_ref, sr_ref, ref_text_archivo)
                if audio_prev is not None:
                    print(f"  {C.CYAN}Reproduciendo preview con la voz clonada...{C.RESET}")
                    _reproducir(audio_prev, sr_prev)

                    if input("\n  ¿Te gusta cómo suena? [S/n]: ").strip().lower() not in ("n","no"):
                        break
                    info("Prueba con otro archivo.")
                else:
                    warn("No se pudo generar el preview.")
                    if input("  ¿Usar este archivo de todas formas? [s/n]: ").strip().lower() == "s":
                        break

            if audio_ref is not None:
                ref_path = Path(__file__).parent / "data" / "voz_referencia.wav"
                ref_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    import soundfile as sf
                    sf.write(str(ref_path), audio_ref, sr_ref)
                    # Guardar también el texto de referencia
                    ref_text_path = ref_path.parent / "voz_referencia_texto.txt"
                    ref_text_path.write_text(ref_text_archivo, encoding="utf-8")
                    ok(f"Referencia guardada: {ref_path}")
                    resultado["SOFIA_TTS_VOZ_MODO"] = "clon"
                    resultado["SOFIA_VOZ_REF_PATH"] = str(ref_path)
                    resultado["SOFIA_VOZ_REF_TEXT"] = ref_text_archivo
                except Exception as e:
                    warn(f"No se pudo guardar la referencia: {e}")
                    resultado["SOFIA_TTS_VOZ_MODO"] = "preset"
                    resultado["SOFIA_VOZ_SPEAKER"]  = "Lucia"
            else:
                resultado["SOFIA_TTS_VOZ_MODO"] = "preset"
                resultado["SOFIA_VOZ_SPEAKER"]  = "Lucia"

    # ── Instrucción de estilo ────────────────
    print(f"\n  {C.BOLD}Instrucción de estilo:{C.RESET}")
    print("  Describe cómo quieres que hable SOFÍA.")
    print("  Ejemplos: 'Habla despacio y con calma'")
    print("            'Tono energético y juvenil'")
    print("            'Voz formal y precisa'")

    instruccion = input(
        "\n  Tu instrucción (Enter para 'tono cálido y profesional'): "
    ).strip()
    resultado["SOFIA_VOZ_INSTRUCCION"] = instruccion or \
        "Habla con tono cálido y profesional, ritmo fluido, acento neutro latinoamericano."

    ok("Configuración de voz completada.")
    return resultado