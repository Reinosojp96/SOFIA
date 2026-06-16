"""
Motor TTS con Qwen3-TTS-0.6B-CustomVoice (GPU).

CAMBIOS v2:
  - Voces correctas del modelo 0.6B: aiden, dylan, eric, ono_anna,
    ryan, serena, sohee, uncle_fu, vivian
  - Carga desde ruta local (data/qwen3_tts/) en vez de descargar
    en cada arranque
  - Soporte para modo 'clon' (voz_referencia.wav)
  - Suprime warnings de sox y flash-attn
"""

import os
import sys
import warnings
import threading
import logging
from pathlib import Path

# Suprimir warnings molestos al importar
warnings.filterwarnings("ignore")
logging.getLogger("librosa").setLevel(logging.ERROR)
logging.getLogger("sox").setLevel(logging.ERROR)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ── Configuración desde .env ──────────────────
CUDA_DEVICE = os.environ.get("SOFIA_CUDA_DEVICE", "cuda:0")
MODO        = os.environ.get("SOFIA_TTS_VOZ_MODO", "preset")  # "preset" | "clon"
INSTRUCCION = os.environ.get(
    "SOFIA_VOZ_INSTRUCCION",
    "Habla con tono cálido y profesional, ritmo fluido."
)

# Voces reales del modelo 0.6B-CustomVoice
# (las del 1.7B son diferentes — Lucia, Sofia, etc. no existen en 0.6B)
VOCES_0_6B = {
    # Femeninas
    "serena":   "Femenina · tono suave y cálido",
    "vivian":   "Femenina · tono claro y profesional",
    "ono_anna": "Femenina · tono neutro y preciso",
    "sohee":    "Femenina · tono joven y dinámico",
    # Masculinas
    "aiden":    "Masculino · tono seguro y maduro",
    "dylan":    "Masculino · tono amigable",
    "eric":     "Masculino · tono formal",
    "ryan":     "Masculino · tono claro y directo",
    "uncle_fu": "Masculino · tono profundo",
}

# Mapeo de nombres "amigables" del setup → ID real del modelo
# Si el usuario eligió "Lucia" con el setup viejo, mapeamos a "serena"
ALIAS_VOCES = {
    "lucia": "serena", "isabella": "vivian", "valentina": "sohee",
    "sofia": "ono_anna", "diego": "aiden", "alejandro": "ryan",
}

_SPEAKER_RAW = os.environ.get("SOFIA_VOZ_SPEAKER", "serena").lower()
SPEAKER = ALIAS_VOCES.get(_SPEAKER_RAW, _SPEAKER_RAW)
if SPEAKER not in VOCES_0_6B:
    SPEAKER = "serena"  # fallback seguro

# ── Rutas del modelo ──────────────────────────
_RAIZ = Path(__file__).parent.parent
_MODELO_LOCAL_CUSTOM = _RAIZ / "data" / "qwen3_tts"
# El modelo Base puede estar en qwen3_tts_base (si se descargó separado)
# o en la caché de HuggingFace (ya descargado por el setup en modo clon)
_MODELO_LOCAL_BASE   = _RAIZ / "data" / "qwen3_tts_base"
# Si existe la carpeta local del Base, la usamos; si no, buscamos en caché HF
_HF_CACHE_BASE = None
try:
    from huggingface_hub import snapshot_download
    from huggingface_hub.file_download import hf_hub_download
    import huggingface_hub as _hf
    _cache = _hf.constants.HF_HUB_CACHE
    _candidato = next(
        (p for p in (__import__("pathlib").Path(_cache)).glob(
            "models--Qwen--Qwen3-TTS-12Hz-0.6B-Base*") if p.is_dir()), None
    )
    if _candidato:
        _HF_CACHE_BASE = str(_candidato / "snapshots" /
                             next((_candidato / "snapshots").iterdir()).name)                          if (_candidato / "snapshots").exists() else None
except Exception:
    pass
_VOZ_REF             = Path(os.environ.get("SOFIA_VOZ_REF_PATH", "")) \
                       or _RAIZ / "data" / "voz_referencia.wav"

# ID de HuggingFace como fallback si no existe la carpeta local
_HF_CUSTOM = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
_HF_BASE   = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"

_lock        = threading.Lock()
_modelo      = None
_disponible  = False

# Tiempo de inactividad antes de descargar (segundos). Default 30 min.
_TIMEOUT = int(os.environ.get("SOFIA_MODELO_TIMEOUT", "1800"))


def _resolver_modelo_id(local: Path, hf_id: str) -> str:
    """Devuelve la ruta local si existe, sino el ID de HuggingFace."""
    if local.exists() and any(local.iterdir()):
        return str(local)
    return hf_id


def _cargar():
    global _modelo, _disponible
    if _modelo is not None:
        return

    # Suprimir stdout de flash-attn y sox durante la carga
    _stderr_orig = sys.stderr
    try:
        import torch
        from qwen_tts import Qwen3TTSModel

        if MODO == "clon":
            # Prioridad: carpeta local > caché HF ya descargada > descargar de HF
            if _MODELO_LOCAL_BASE.exists() and any(_MODELO_LOCAL_BASE.iterdir()):
                model_id = str(_MODELO_LOCAL_BASE)
            elif _HF_CACHE_BASE:
                model_id = _HF_CACHE_BASE
            else:
                model_id = _HF_BASE
        else:
            model_id = _resolver_modelo_id(_MODELO_LOCAL_CUSTOM, _HF_CUSTOM)

        print(f"[tts] Cargando Qwen3-TTS ({MODO}) desde {model_id}...")

        _modelo = Qwen3TTSModel.from_pretrained(
            model_id,
            device_map=CUDA_DEVICE,
            dtype=torch.bfloat16,
        )
        _disponible = True
        print(f"[tts] Modelo listo. Voz: {SPEAKER if MODO == 'preset' else 'clonada'}")

    except Exception as e:
        print(f"[tts] Error cargando Qwen3-TTS: {e}")
        _disponible = False
    finally:
        sys.stderr = _stderr_orig


class HabladorQwen:
    def __init__(self):
        # No carga el modelo al instanciar — lazy loading explícito con cargar()
        self._timer: threading.Timer | None = None

    # ── Ciclo de vida del modelo ───────────────────────────────────────

    def cargar(self):
        """Carga el modelo en VRAM. Idempotente si ya está cargado."""
        _cargar()

    def descargar(self):
        """Libera el modelo de VRAM y limpia la cache de CUDA."""
        global _modelo, _disponible
        with _lock:
            _modelo = None
            _disponible = False
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
        print("[tts] Qwen3-TTS descargado de VRAM")

    def esta_cargado(self) -> bool:
        return _disponible and _modelo is not None

    def disponible(self) -> bool:
        return _disponible

    def _reiniciar_timer(self):
        """Cancela el timer anterior e inicia uno nuevo de inactividad."""
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(_TIMEOUT, self.descargar)
        self._timer.daemon = True
        self._timer.start()

    # ── Generación de audio ────────────────────────────────────────────

    def _generar_wavs(self, texto: str):
        """Genera audio y devuelve (wavs, sr) sin reproducir."""
        if MODO == "clon" and _VOZ_REF.exists():
            import soundfile as sf
            audio_ref, sr_ref = sf.read(str(_VOZ_REF), dtype="float32")
            if audio_ref.ndim > 1:
                audio_ref = audio_ref.mean(axis=1)
            ref_text_path = _VOZ_REF.parent / "voz_referencia_texto.txt"
            ref_text = ref_text_path.read_text(encoding="utf-8").strip() \
                       if ref_text_path.exists() else ""
            return _modelo.generate_voice_clone(
                text=texto, language="Spanish",
                ref_audio=(audio_ref, sr_ref), ref_text=ref_text,
            )
        else:
            return _modelo.generate_custom_voice(
                text=texto, language="Spanish",
                speaker=SPEAKER, instruct=INSTRUCCION,
            )

    def generar_array(self, texto: str):
        """
        Genera audio para 'texto' y devuelve (np.ndarray, sample_rate).
        No reproduce nada. Carga el modelo si es necesario.
        """
        import numpy as np
        self.cargar()
        if not _disponible or _modelo is None:
            return None, None
        with _lock:
            try:
                wavs, sr = self._generar_wavs(texto)
                audio = np.array(wavs[0], dtype=np.float32) \
                        if not hasattr(wavs[0], "dtype") else wavs[0]
                return audio, sr
            except Exception as e:
                print(f"[tts] Error generando array: {e}")
                return None, None

    def hablar(self, texto: str):
        if not texto or not texto.strip():
            return
        self.cargar()
        if not _disponible or _modelo is None:
            print(f"[tts] No disponible: {texto}")
            return

        self._reiniciar_timer()

        with _lock:
            try:
                import sounddevice as sd
                import numpy as np

                wavs, sr = self._generar_wavs(texto)
                audio = np.array(wavs[0], dtype=np.float32) \
                        if not hasattr(wavs[0], "dtype") else wavs[0]
                sd.play(audio, samplerate=sr)
                sd.wait()

            except Exception as e:
                import traceback
                print(f"[tts] Error al generar voz: {e}")
                traceback.print_exc()