"""
Módulo de configuración de voz para setup.py
Se importa desde setup.py después de instalar dependencias.
"""

import os
import sys
import time
import threading
import tempfile
import subprocess
from pathlib import Path


# ─────────────────────────────────────────────
# Colores (duplicados aquí para que sea importable de forma independiente)
# ─────────────────────────────────────────────
class C:
    RESET  = "\033[0m"; BOLD = "\033[1m"
    GREEN  = "\033[92m"; YELLOW = "\033[93m"
    RED    = "\033[91m"; CYAN = "\033[96m"
    BLUE   = "\033[94m"

def ok(msg):   print(f"{C.GREEN}  ✓ {msg}{C.RESET}")
def info(msg): print(f"{C.CYAN}  ℹ {msg}{C.RESET}")
def warn(msg): print(f"{C.YELLOW}  ⚠ {msg}{C.RESET}")

# ─────────────────────────────────────────────
# Voces disponibles con descripción
# ─────────────────────────────────────────────
VOCES = [
    {
        "id": "Lucia",
        "descripcion": "Femenina · acento español neutro · cálida y profesional",
        "muestra": "Hola, soy Lucía. Puedo ser la voz de tu asistente SOFÍA.",
    },
    {
        "id": "Isabella",
        "descripcion": "Femenina · tono suave y cercano · latinoamericana",
        "muestra": "Hola, soy Isabella. Estoy lista para ayudarte en lo que necesites.",
    },
    {
        "id": "Valentina",
        "descripcion": "Femenina · energética y clara · joven",
        "muestra": "Hola, soy Valentina. ¿En qué puedo ayudarte hoy?",
    },
    {
        "id": "Sofia",
        "descripcion": "Femenina · tono formal y preciso",
        "muestra": "Hola, soy Sofía. Tu asistente de voz personal está lista.",
    },
    {
        "id": "Diego",
        "descripcion": "Masculina · tono profundo y seguro",
        "muestra": "Hola, soy Diego. Dime en qué puedo ayudarte.",
    },
    {
        "id": "Alejandro",
        "descripcion": "Masculina · tono amigable y relajado",
        "muestra": "Hola, soy Alejandro. Estoy aquí para lo que necesites.",
    },
]


# ─────────────────────────────────────────────
# Spinner simple (sin dependencia de setup.py)
# ─────────────────────────────────────────────
class Spinner:
    def __init__(self, mensaje=""):
        self._activo = False
        self._hilo   = None
        self._msg    = mensaje

    def __enter__(self):
        frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._activo = True
        def _loop():
            i = 0
            while self._activo:
                print(f"\r  {C.CYAN}{frames[i % len(frames)]}{C.RESET} {self._msg}",
                      end="", flush=True)
                time.sleep(0.1)
                i += 1
        self._hilo = threading.Thread(target=_loop, daemon=True)
        self._hilo.start()
        return self

    def __exit__(self, *_):
        self._activo = False
        if self._hilo:
            self._hilo.join(timeout=0.5)
        print()


# ─────────────────────────────────────────────
# Carga lazy del modelo TTS
# ─────────────────────────────────────────────
_modelo_tts = None

def _cargar_modelo_tts():
    global _modelo_tts
    if _modelo_tts is not None:
        return _modelo_tts
    try:
        import torch
        from qwen_tts import Qwen3TTSModel
        with Spinner("Cargando Qwen3-TTS para las muestras (solo esta vez)..."):
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


# ─────────────────────────────────────────────
# Reproducir audio
# ─────────────────────────────────────────────
def _reproducir(audio, sr: int):
    """Reproduce un array numpy de audio."""
    try:
        import sounddevice as sd
        sd.play(audio, samplerate=sr)
        sd.wait()
    except Exception as e:
        warn(f"No se pudo reproducir: {e}")


def _generar_muestra(modelo, voz: dict) -> tuple:
    """Genera y devuelve (audio, sr) para una voz. None si falla."""
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
        warn(f"Error generando muestra: {e}")
        return None, None


# ─────────────────────────────────────────────
# Grabación de voz del usuario
# ─────────────────────────────────────────────
def _grabar_voz_usuario(duracion: int = 5, sr: int = 16000) -> tuple:
    """
    Graba la voz del usuario durante 'duracion' segundos.
    Devuelve (audio_numpy, sr) o (None, None) si falla.
    """
    try:
        import numpy as np
        import sounddevice as sd

        print(f"\n  {C.YELLOW}Habla durante {duracion} segundos cuando veas '▶ Grabando...'{C.RESET}")
        input("  Presiona Enter cuando estés listo...")

        print(f"\n  {C.RED}▶ Grabando...{C.RESET}", end="", flush=True)

        # Cuenta regresiva visual mientras graba
        grabacion = sd.rec(
            int(duracion * sr),
            samplerate=sr,
            channels=1,
            dtype="float32",
        )
        for i in range(duracion, 0, -1):
            print(f"\r  {C.RED}▶ Grabando... {i}s{C.RESET}", end="", flush=True)
            time.sleep(1)
        sd.wait()
        print(f"\r  {C.GREEN}✓ Grabación completada.{C.RESET}       ")

        audio = grabacion[:, 0]
        return audio, sr

    except Exception as e:
        warn(f"Error durante la grabación: {e}")
        return None, None


def _clonar_voz(modelo, audio_ref, sr_ref: int, texto_prueba: str) -> tuple:
    """
    Genera audio clonando la voz de referencia.
    Devuelve (audio, sr) o (None, None).
    """
    try:
        import numpy as np

        # Qwen3-TTS-Base acepta array numpy directamente como ref_audio
        with Spinner("Clonando tu voz..."):
            # Necesitamos el modelo Base para clonar, no el CustomVoice
            import torch
            from qwen_tts import Qwen3TTSModel
            modelo_base = Qwen3TTSModel.from_pretrained(
                "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                device_map="cuda:0",
                dtype=torch.bfloat16,
            )
            wavs, sr = modelo_base.generate_voice_clone(
                text=texto_prueba,
                language="Spanish",
                ref_audio=audio_ref,
                ref_text="",   # sin transcripción de referencia
            )
        return wavs[0], sr
    except Exception as e:
        warn(f"Error clonando voz: {e}")
        return None, None


# ─────────────────────────────────────────────
# Paso principal exportado a setup.py
# ─────────────────────────────────────────────
def configurar_voz() -> dict:
    """
    Flujo completo de configuración de voz.
    Devuelve un dict con las claves para el .env:
      {
        "SOFIA_TTS_VOZ_MODO": "preset" | "clon",
        "SOFIA_VOZ_SPEAKER": str,          # solo si modo=preset
        "SOFIA_VOZ_INSTRUCCION": str,
        # Si modo=clon, el audio de referencia se guarda en data/voz_referencia.wav
      }
    """
    print(f"\n{C.BOLD}{C.BLUE}{'─'*55}")
    print("  Configuración de voz de SOFÍA")
    print(f"{'─'*55}{C.RESET}")

    info("Cargando el modelo de voz (esto puede tardar 1-2 minutos la primera vez)...")
    modelo = _cargar_modelo_tts()

    if modelo is None:
        warn("No se pudo cargar el modelo TTS. Usando voz por defecto (Lucia).")
        return {
            "SOFIA_TTS_VOZ_MODO": "preset",
            "SOFIA_VOZ_SPEAKER": "Lucia",
            "SOFIA_VOZ_INSTRUCCION": "Habla con tono cálido y profesional.",
        }

    # ── Opción: escuchar voces predefinidas o clonar la propia
    print(f"\n  {C.BOLD}¿Qué tipo de voz quieres para SOFÍA?{C.RESET}")
    print("    1. Elegir una voz de la lista (la puedes escuchar antes de decidir)")
    print("    2. Clonar tu propia voz (graba 5 segundos y SOFÍA hablará como tú)")

    while True:
        resp = input("  Elige [1/2] (Enter=1): ").strip()
        if resp in ("", "1"):
            modo = "preset"
            break
        elif resp == "2":
            modo = "clon"
            break
        print("  Opción inválida.")

    resultado = {"SOFIA_TTS_VOZ_MODO": modo}

    # ═══════════════════════════════════════════
    # MODO PRESET: escuchar y elegir
    # ═══════════════════════════════════════════
    if modo == "preset":
        print(f"\n  {C.BOLD}Voces disponibles:{C.RESET}")
        for i, voz in enumerate(VOCES, 1):
            print(f"    {i}. {C.CYAN}{voz['id']}{C.RESET} — {voz['descripcion']}")

        voz_elegida = None
        while True:
            print("\n  Opciones:")
            print("    · Escribe el número de una voz para escuchar la muestra")
            print("    · Escribe 'ok N' para confirmar la voz N (ej: ok 2)")
            print("    · Escribe 'todas' para escuchar todas en secuencia")

            cmd = input("\n  > ").strip().lower()

            if cmd == "todas":
                for i, voz in enumerate(VOCES, 1):
                    print(f"\n  [{i}/6] {voz['id']}...")
                    audio, sr = _generar_muestra(modelo, voz)
                    if audio is not None:
                        _reproducir(audio, sr)
                    time.sleep(0.5)

            elif cmd.isdigit() and 1 <= int(cmd) <= len(VOCES):
                voz = VOCES[int(cmd) - 1]
                print(f"\n  Reproduciendo muestra de {voz['id']}...")
                audio, sr = _generar_muestra(modelo, voz)
                if audio is not None:
                    _reproducir(audio, sr)

            elif cmd.startswith("ok "):
                partes = cmd.split()
                if len(partes) == 2 and partes[1].isdigit():
                    idx = int(partes[1])
                    if 1 <= idx <= len(VOCES):
                        voz_elegida = VOCES[idx - 1]
                        ok(f"Voz seleccionada: {voz_elegida['id']}")
                        break
                print("  Formato: ok N  (ej: ok 3)")
            else:
                print("  No entendí. Escribe un número, 'ok N' o 'todas'.")

        resultado["SOFIA_VOZ_SPEAKER"] = voz_elegida["id"]

    # ═══════════════════════════════════════════
    # MODO CLON: grabar la voz del usuario
    # ═══════════════════════════════════════════
    else:
        info("Necesitas grabar al menos 5 segundos de tu voz, leyendo cualquier texto.")
        info("Ejemplo: 'Buenos días. Hoy es un día perfecto para aprender cosas nuevas.'")

        audio_ref = None
        sr_ref    = 16000

        while True:
            audio_ref, sr_ref = _grabar_voz_usuario(duracion=5, sr=16000)

            if audio_ref is None:
                warn("La grabación falló. ¿Intentar de nuevo?")
                if input("  [s/n]: ").strip().lower() != "s":
                    warn("Usando voz Lucia por defecto.")
                    resultado["SOFIA_VOZ_SPEAKER"] = "Lucia"
                    resultado["SOFIA_TTS_VOZ_MODO"] = "preset"
                    break
                continue

            # Generar preview con la voz clonada
            print("\n  Generando preview con tu voz clonada...")
            audio_preview, sr_preview = _clonar_voz(
                modelo, audio_ref, sr_ref,
                "Hola, soy SOFÍA. Esta es mi voz clonada."
            )

            if audio_preview is not None:
                print(f"  {C.CYAN}Reproduciendo preview...{C.RESET}")
                _reproducir(audio_preview, sr_preview)

                resp = input("\n  ¿Te gusta cómo suena? [S/n]: ").strip().lower()
                if resp not in ("n", "no"):
                    # Guardar audio de referencia
                    try:
                        import soundfile as sf
                        import numpy as np
                        ref_path = Path(__file__).parent / "data" / "voz_referencia.wav"
                        ref_path.parent.mkdir(parents=True, exist_ok=True)
                        sf.write(str(ref_path), audio_ref, sr_ref)
                        ok(f"Voz de referencia guardada en {ref_path}")
                        resultado["VOZ_REF_PATH"] = str(ref_path)
                    except Exception as e:
                        warn(f"No se pudo guardar la referencia: {e}")
                    break
                else:
                    info("Grabemos de nuevo.")
            else:
                warn("No se pudo generar el preview. Grabemos de nuevo.")

    # ── Instrucción de estilo (aplica a ambos modos)
    print(f"\n  {C.BOLD}Instrucción de estilo para la voz:{C.RESET}")
    print("  Describe cómo quieres que hable SOFÍA.")
    print("  Ejemplos:")
    print("    · 'Habla despacio y con calma'")
    print("    · 'Tono energético y juvenil'")
    print("    · 'Voz formal y precisa, sin pausas largas'")

    instruccion = input("\n  Tu instrucción (Enter para 'tono cálido y profesional'): ").strip()
    resultado["SOFIA_VOZ_INSTRUCCION"] = instruccion or \
        "Habla con tono cálido y profesional, ritmo fluido, acento neutro latinoamericano."

    print(f"\n  {C.GREEN}{C.BOLD}Configuración de voz completada.{C.RESET}")
    return resultado