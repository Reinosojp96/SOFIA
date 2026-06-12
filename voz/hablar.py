"""
Texto a voz con pyttsx3 (funciona offline).

Nota: se crea una instancia nueva del motor cada vez que se habla.
pyttsx3 tiene un bug conocido donde reutilizar la misma instancia
despues de la primera llamada a runAndWait() deja de sonar en
Windows. Crear una instancia por llamada es mas lento (decenas de ms)
pero confiable.
"""

import pyttsx3
import threading

_lock = threading.Lock()


def hablar(texto):
    """Convierte texto a voz. Bloqueante."""
    with _lock:
        try:
            engine = pyttsx3.init()
            # Velocidad natural: 160-170 palabras/min suena mas humano que 175
            engine.setProperty("rate", 165)
            # Intentar voz femenina para Sofia (si el sistema la tiene)
            voices = engine.getProperty("voices")
            voz_femenina = None
            for v in voices:
                # Buscar voz en espanol femenina
                if any(lang in (v.languages or []) for lang in [b"es", "es", "es_CO", "es_ES", "es-CO", "es-ES"]):
                    # Heuristica: IDs con "female", "zira", "helena", "sabina", "laura"
                    vid = (v.id or "").lower()
                    vname = (v.name or "").lower()
                    if any(k in vid or k in vname for k in ["female", "zira", "helena", "sabina", "laura", "sofia", "mujer"]):
                        voz_femenina = v.id
                        break
            if voz_femenina:
                engine.setProperty("voice", voz_femenina)
            engine.say(texto)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"[voz] Error al hablar: {e}")
