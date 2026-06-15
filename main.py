"""
SOFÍA - Punto de entrada principal.
Solo arranca la aplicación. La instalación y configuración
se hace con setup.py (una sola vez).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# ── Cargar .env ──────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # si no hay dotenv, usa variables del sistema

# ── Verificar instalación ────────────────────
from pathlib import Path

def _verificar_instalacion():
    """Comprueba que setup.py ya fue ejecutado."""
    problemas = []
    raiz = Path(__file__).parent

    if not (raiz / ".env").exists():
        problemas.append(".env no encontrado")

    if not (raiz / "voz" / "escuchar.py").exists():
        problemas.append("Módulos de voz no encontrados")

    if problemas:
        print("[SOFÍA] Parece que la instalación no está completa:")
        for p in problemas:
            print(f"  · {p}")
        print("\nEjecuta primero: python setup.py")
        sys.exit(1)

_verificar_instalacion()

# ── Imports del proyecto ─────────────────────
import threading

from core.router import router
from core import ia, memoria
from skills import clima, tiempo, sistema, web, aprendizaje, notas, rutina
from ui.widget import ejecutar_app


def registrar_skills():
    router.registrar("rutina",      rutina.KEYWORDS,       rutina.manejar)
    router.registrar("clima",       clima.KEYWORDS,        clima.consultar_clima)
    router.registrar("tiempo",      tiempo.KEYWORDS,       tiempo.manejar)
    router.registrar("sistema",     sistema.KEYWORDS,      sistema.manejar)
    router.registrar("web",         web.KEYWORDS,          web.manejar)
    router.registrar("notas",       notas.KEYWORDS,        notas.manejar)
    router.registrar("aprendizaje", aprendizaje.KEYWORDS,  aprendizaje.manejar)
    router.registrar_fallback(lambda texto: ia.preguntar(texto))


def procesar_comando(texto: str) -> str:
    if not texto or not texto.strip():
        return "No escuché nada."
    return router.procesar(texto)


def main():
    registrar_skills()

    escuchador = None
    hablador   = None
    PALABRA_ACTIVACION = os.environ.get("SOFIA_WAKE_WORD", "sofia")

    # ── Cargar voz ───────────────────────────
    try:
        from voz.escuchar import Escuchador, PALABRA_ACTIVACION as _PA
        from voz.hablar import hablar as _hablar_fn
        PALABRA_ACTIVACION = _PA
        escuchador = Escuchador()

        class _Hablador:
            def hablar(self, texto):
                _hablar_fn(texto)

        hablador = _Hablador()
    except Exception as e:
        print(f"[main] Voz no disponible: {e}")

    # ── Helpers ──────────────────────────────
    def _hablar(texto: str):
        if not hablador:
            return
        if escuchador:
            escuchador.pausar()
        try:
            hablador.hablar(texto)
        finally:
            if escuchador:
                escuchador.reanudar(retardo=0.35)

    def _procesar_y_responder(texto: str, origen: str = "Tú (voz)"):
        widget.agregar_mensaje(origen, texto)
        respuesta = procesar_comando(texto)
        widget.agregar_mensaje("SOFÍA", respuesta)
        _hablar(respuesta)

    def on_comando(texto: str) -> str:
        return procesar_comando(texto)

    def on_hablar_voz():
        if not escuchador:
            widget.agregar_mensaje("SOFÍA", "El micrófono no está disponible.")
            return
        texto = escuchador.escuchar_frase(tiempo_espera=6, limite_frase=10)
        if not texto:
            widget.agregar_mensaje("SOFÍA", "No escuché nada, intenta de nuevo.")
            return
        _procesar_y_responder(texto, origen="Tú")

    def hilo_activacion_continua():
        if not escuchador:
            return
        while True:
            try:
                resto = escuchador.esperar_activacion()
            except Exception as e:
                print(f"[voz] Error en activación: {e}")
                continue

            origen = f"Tú ({PALABRA_ACTIVACION.capitalize()})"
            widget.set_estado("Te escucho...", "#7c3aed")

            if resto:
                _procesar_y_responder(resto, origen=origen)
            else:
                _hablar("Dime")
                comando = escuchador.escuchar_frase(tiempo_espera=6, limite_frase=10)
                if comando:
                    _procesar_y_responder(comando, origen=origen)
                else:
                    widget.agregar_mensaje("SOFÍA", "No escuché ningún comando.")

            widget.set_estado("Lista", "#3fb950")

    def hilo_alarmas():
        import time
        from datetime import datetime as _dt
        while True:
            try:
                ahora = _dt.now().strftime("%H:%M")
                for alarma in memoria.alarmas_para_disparar(ahora):
                    etiqueta = alarma.get("etiqueta") or "Es la hora que pediste."
                    widget.agregar_mensaje("SOFÍA", f"⏰ Alarma de las {alarma['hora']}: {etiqueta}")
                    widget.set_estado("¡Alarma!", "#d29922")
                    _hablar(f"Alarma. {etiqueta}")
                    widget.set_estado("Lista", "#3fb950")
            except Exception as e:
                print(f"[alarmas] error: {e}")
            time.sleep(20)

    def post_init(widget_creado):
        nonlocal widget
        widget = widget_creado

        nombre = os.environ.get("SOFIA_USER_NAME", "")
        saludo = f"Hola{', ' + nombre if nombre else ''}. Soy SOFÍA."
        widget.agregar_mensaje("SOFÍA", saludo)

        if escuchador:
            widget.agregar_mensaje(
                "SOFÍA",
                f"Di '{PALABRA_ACTIVACION.capitalize()}' para activarme por voz."
            )
            threading.Thread(target=hilo_activacion_continua, daemon=True).start()
        else:
            widget.agregar_mensaje("SOFÍA", "Micrófono no disponible. Usa el modo texto.")

        threading.Thread(target=hilo_alarmas, daemon=True).start()

    widget = None
    ejecutar_app(on_comando=on_comando, on_hablar_voz=on_hablar_voz, post_init=post_init)


if __name__ == "__main__":
    main()