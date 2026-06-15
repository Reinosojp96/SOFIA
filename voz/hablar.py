"""
Punto de entrada unificado para TTS.

Lee SOFIA_TTS_MOTOR del .env:
  "pyttsx3"  -> motor clásico, offline, funciona en CPU, voz robótica (defecto)
  "qwen"     -> Qwen3-TTS 0.6B, requiere GPU Nvidia con 4GB+ VRAM, voz natural

Si el motor preferido falla al cargar (GPU no disponible, modelo no
descargado, etc.), cae automáticamente a pyttsx3 con un aviso.

El resto del proyecto llama solo a:
  from voz.hablar import hablar
  hablar("texto")
"""

import os
import threading

MOTOR = os.environ.get("SOFIA_TTS_MOTOR", "pyttsx3").lower().strip()

# ---- Motor Qwen --------------------------------------------------------

_qwen_motor  = None
_qwen_ok     = False
_qwen_lock   = threading.Lock()


def _init_qwen():
    global _qwen_motor, _qwen_ok
    try:
        from voz.hablar_qwen import HabladorQwen
        h = HabladorQwen()
        if h.disponible():
            _qwen_motor = h
            _qwen_ok    = True
            print("[tts] Usando motor: Qwen3-TTS 0.6B (GPU)")
        else:
            raise RuntimeError("modelo no disponible")
    except Exception as e:
        print(f"[tts] Qwen3-TTS no disponible ({e}), usando pyttsx3 como respaldo.")
        _qwen_ok = False


if MOTOR == "qwen":
    _init_qwen()
else:
    print("[tts] Usando motor: pyttsx3 (CPU, voz estándar)")


# ---- Motor pyttsx3 -----------------------------------------------------

_pyttsx3_lock = threading.Lock()


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


# ---- API pública -------------------------------------------------------

def hablar(texto: str):
    """
    Convierte texto a voz usando el motor configurado.
    Bloqueante: retorna cuando el audio termina de reproducirse.
    """
    if not texto or not texto.strip():
        return

    if MOTOR == "qwen" and _qwen_ok and _qwen_motor:
        _qwen_motor.hablar(texto)
    else:
        _hablar_pyttsx3(texto)