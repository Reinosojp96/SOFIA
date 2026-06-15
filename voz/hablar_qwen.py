"""
Motor TTS con Qwen3-TTS-0.6B-CustomVoice (GPU, RTX 3050+).

Uso:
  from voz.hablar_qwen import HabladorQwen
  hablador = HabladorQwen()
  hablador.hablar("Buenos días, ¿en qué puedo ayudarte?")

Voces disponibles (CustomVoice 0.6B):
  Femeninas (español nativo): Lucia, Isabella, Valentina, Sofia
  Masculinas (español nativo): Diego, Alejandro

Configuración en .env:
  SOFIA_VOZ_SPEAKER=Lucia          # voz elegida
  SOFIA_VOZ_INSTRUCCION=Habla con tono cálido y profesional, ritmo fluido
  SOFIA_CUDA_DEVICE=cuda:0         # si tienes varias GPUs

Requisitos:
  pip install qwen-tts soundfile
  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
  # Ajusta cu126 según tu versión de CUDA (nvidia-smi -> CUDA Version)
  # cu118 = CUDA 11.8, cu124 = CUDA 12.4, cu126 = CUDA 12.6, cu128 = CUDA 12.8
"""

import os
import io
import threading
import tempfile
import sounddevice as sd
import soundfile as sf
import numpy as np

SPEAKER       = os.environ.get("SOFIA_VOZ_SPEAKER", "Lucia")
INSTRUCCION   = os.environ.get(
    "SOFIA_VOZ_INSTRUCCION",
    "Habla con tono cálido y profesional, ritmo fluido, acento neutro latinoamericano."
)
CUDA_DEVICE   = os.environ.get("SOFIA_CUDA_DEVICE", "cuda:0")
MODEL_ID      = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"

_lock  = threading.Lock()
_model = None


def _cargar():
    global _model
    if _model is not None:
        return
    try:
        import torch
        from qwen_tts import Qwen3TTSModel

        print(f"[tts] Cargando Qwen3-TTS 0.6B en {CUDA_DEVICE}...")
        _model = Qwen3TTSModel.from_pretrained(
            MODEL_ID,
            device_map=CUDA_DEVICE,
            dtype=torch.bfloat16,
        )
        print("[tts] Modelo listo.")
    except Exception as e:
        print(f"[tts] Error cargando Qwen3-TTS: {e}")
        _model = None


class HabladorQwen:
    def __init__(self):
        _cargar()

    def disponible(self) -> bool:
        return _model is not None

    def hablar(self, texto: str):
        if not texto or not texto.strip():
            return
        if _model is None:
            print(f"[tts] Modelo no disponible, no se puede hablar: {texto}")
            return

        with _lock:
            try:
                wavs, sr = _model.generate_custom_voice(
                    text=texto,
                    language="Spanish",
                    speaker=SPEAKER,
                    instruct=INSTRUCCION,
                )
                audio = wavs[0]
                if isinstance(audio, list):
                    audio = np.array(audio, dtype=np.float32)
                # Reproducir directamente sin guardar archivo
                sd.play(audio, samplerate=sr)
                sd.wait()
            except Exception as e:
                print(f"[tts] Error al generar voz: {e}")