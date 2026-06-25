"""
Punto de entrada unificado para TTS.
Lee SOFIA_TTS_MOTOR del .env: "pyttsx3" o "qwen"

v4: lazy loading de Qwen (no carga al importar) + hablar_estatico()
"""

import json
import os
import sys
import warnings
import logging
import threading
from pathlib import Path

# Suprimir antes de cualquier import
warnings.filterwarnings("ignore")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

logging.getLogger("sox").setLevel(logging.CRITICAL)
logging.getLogger("librosa").setLevel(logging.CRITICAL)
logging.getLogger("audioread").setLevel(logging.CRITICAL)

import io
_stderr_orig = sys.stderr
sys.stderr = io.StringIO()

MOTOR = os.environ.get("SOFIA_TTS_MOTOR", "pyttsx3").lower().strip()

_qwen_motor    = None
_qwen_init_ok  = False   # True si el import de HabladorQwen fue exitoso
_qwen_lock     = threading.Lock()  # evita múltiples cargas simultáneas
_pyttsx3_lock  = threading.Lock()

# Directorio de audio pre-renderizado
_AUDIO_DIR = Path(__file__).parent.parent / "data" / "audio_estatico"

sys.stderr = _stderr_orig
if MOTOR == "qwen":
    print("[tts] Motor: qwen (lazy loading)")
else:
    print("[tts] Motor: pyttsx3")


# ---------------------------------------------------------------------------
# Inicialización lazy de Qwen
# ---------------------------------------------------------------------------

def _ensure_qwen() -> bool:
    """Instancia HabladorQwen si aún no está instanciado. Devuelve True si OK."""
    global _qwen_motor, _qwen_init_ok
    if _qwen_init_ok:
        return True
    with _qwen_lock:
        if _qwen_init_ok:
            return True
        try:
            from voz.hablar_qwen import HabladorQwen
            _qwen_motor  = HabladorQwen()
            _qwen_init_ok = True
            return True
        except Exception as e:
            print(f"[tts] Qwen3-TTS no disponible ({e}), usando pyttsx3.")
            _qwen_init_ok = False
            return False


# ---------------------------------------------------------------------------
# Audio estático (pre-renderizado)
# ---------------------------------------------------------------------------

def hablar_estatico(clave: str) -> bool:
    """
    Reproduce el .wav pre-renderizado para 'clave' si existe Y el motor activo es qwen.
    Si el motor es pyttsx3 devuelve False para que el llamador use TTS de texto.
    """
    if MOTOR != "qwen":
        return False
    archivo = _AUDIO_DIR / f"{clave}.wav"
    if not archivo.exists():
        return False
    try:
        import soundfile as sf
        import sounddevice as sd
        audio, sr = sf.read(str(archivo), dtype="float32")
        sd.play(audio, samplerate=sr)
        sd.wait()
        return True
    except Exception as e:
        print(f"[tts] Error reproduciendo estático '{clave}': {e}")
        return False


def prerender_frases_estaticas(nombre_usuario: str = ""):
    """
    Genera y guarda en data/audio_estatico/ los .wav de las frases fijas.
    Debe llamarse con Qwen cargado (lo carga si es necesario).
    Solo aplica cuando SOFIA_TTS_MOTOR=qwen.
    """
    if MOTOR != "qwen":
        return

    n = (", " + nombre_usuario) if nombre_usuario else ""
    frases = {
        "dime":            "Dime",
        "te_escucho":      "Te escucho",
        "dame_un_momento": "Dame un momento",
        "verificando":     "Verificando",
        "buscando":        "Buscando",
        "listo":           "Listo",
        "hecho":           "Hecho",
        "esto_encontre":   "Esto es lo que encontré",
        "no_entendi":      "No te entendí, ¿podrías repetirme?",
        "error":           "No pude completar eso",
        "buenos_dias":     f"Buenos días{n}",
        "buenas_tardes":   f"Buenas tardes{n}",
        "buenas_noches":   f"Buenas noches{n}",
        "bienvenido":      f"Bienvenida{n}, estoy lista para ayudarte",
    }

    if not _ensure_qwen():
        print("[tts] No se puede pre-renderizar: Qwen no disponible")
        return

    _AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    indice = {}

    for clave, texto in frases.items():
        print(f"[tts] Pre-renderizando: '{clave}'...")
        try:
            import soundfile as sf
            audio, sr = _qwen_motor.generar_array(texto)
            if audio is None:
                print(f"[tts]   ✗ Falló '{clave}'")
                continue
            ruta = _AUDIO_DIR / f"{clave}.wav"
            sf.write(str(ruta), audio, sr)
            indice[clave] = {"archivo": f"{clave}.wav", "texto": texto, "sr": sr}
            print(f"[tts]   ✓ {clave}.wav")
        except Exception as e:
            print(f"[tts]   ✗ Error en '{clave}': {e}")

    # Guardar índice
    with open(_AUDIO_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(indice, f, ensure_ascii=False, indent=2)

    print(f"[tts] Pre-rendering completado: {len(indice)}/{len(frases)} frases guardadas en {_AUDIO_DIR}")


# ---------------------------------------------------------------------------
# TTS principal
# ---------------------------------------------------------------------------

def _hablar_pyttsx3(texto: str):
    with _pyttsx3_lock:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.say(texto)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"[tts] Error pyttsx3: {e}")


def hablar(texto: str):
    if not texto or not texto.strip():
        return
    if MOTOR == "qwen":
        if _ensure_qwen() and _qwen_motor:
            _qwen_motor.hablar(texto)
        else:
            _hablar_pyttsx3(texto)
    else:
        _hablar_pyttsx3(texto)
