"""
Punto de entrada unificado para TTS.
Lee SOFIA_TTS_MOTOR del .env: "pyttsx3" o "qwen"

v3: suprime warnings de sox/flash-attn, usa hablar_qwen v2
"""

import os
import sys
import warnings
import logging
import threading

# Suprimir antes de cualquier import
warnings.filterwarnings("ignore")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Silenciar sox y librosa antes de que se importen
logging.getLogger("sox").setLevel(logging.CRITICAL)
logging.getLogger("librosa").setLevel(logging.CRITICAL)
logging.getLogger("audioread").setLevel(logging.CRITICAL)

# Redirigir stderr temporalmente para silenciar el print de sox
import io
_stderr_orig = sys.stderr
sys.stderr = io.StringIO()

MOTOR = os.environ.get("SOFIA_TTS_MOTOR", "pyttsx3").lower().strip()

_qwen_motor = None
_qwen_ok    = False
_pyttsx3_lock = threading.Lock()


def _init_qwen():
    global _qwen_motor, _qwen_ok
    try:
        from voz.hablar_qwen import HabladorQwen
        h = HabladorQwen()
        if h.disponible():
            _qwen_motor = h
            _qwen_ok    = True
        else:
            raise RuntimeError("modelo no disponible")
    except Exception as e:
        sys.stderr = _stderr_orig  # restaurar para mostrar este warning
        print(f"[tts] Qwen3-TTS no disponible ({e}), usando pyttsx3.")
        _qwen_ok = False
    finally:
        sys.stderr = _stderr_orig


if MOTOR == "qwen":
    _init_qwen()
else:
    sys.stderr = _stderr_orig
    print("[tts] Motor: pyttsx3")


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
    if MOTOR == "qwen" and _qwen_ok and _qwen_motor:
        _qwen_motor.hablar(texto)
    else:
        _hablar_pyttsx3(texto)