"""
Punto de entrada de SOFIA.

Registra las skills en el router, arranca la interfaz gráfica y conecta
la entrada de voz (botón + activación continua) y texto al mismo flujo
de procesamiento.

MEJORAS v2:
  - Registra la skill de aprendizaje (skills/aprendizaje.py)
  - origen en _procesar_y_responder usa PALABRA_ACTIVACION real siempre
  - on_closing no puede lanzar excepción si escuchador es None
  - mensaje de bienvenida más informativo
"""

import sys
import os
import threading

sys.path.insert(0, os.path.dirname(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv()  # busca .env en el directorio actual / raíz del proyecto
except ImportError:
    print("[main] python-dotenv no instalado; usando solo variables de entorno del sistema.")

from core.router import router
from core import ia, memoria
from skills import clima, tiempo, sistema, web, aprendizaje, notas
from ui.widget import ejecutar_app


def registrar_skills():
    router.registrar("clima",       clima.KEYWORDS,       clima.consultar_clima)
    router.registrar("tiempo",      tiempo.KEYWORDS,       tiempo.manejar)
    router.registrar("sistema",     sistema.KEYWORDS,      sistema.manejar)
    router.registrar("web",         web.KEYWORDS,          web.manejar)
    router.registrar("notas",       notas.KEYWORDS,        notas.manejar)
    router.registrar("aprendizaje", aprendizaje.KEYWORDS,  aprendizaje.manejar)

    # Fallback: conversación libre con la IA local (llama.cpp)
    router.registrar_fallback(lambda texto: ia.preguntar(texto))


def procesar_comando(texto: str) -> str:
    """Punto único de entrada para texto o voz."""
    if not texto or not texto.strip():
        return "No escuché nada."
    return router.procesar(texto)


def main():
    registrar_skills()

    escuchador = None
    hablador = None
    PALABRA_ACTIVACION = "sofia"

    try:
        from voz.escuchar import Escuchador, PALABRA_ACTIVACION as _PA
        from voz import hablar as hablador_modulo
        PALABRA_ACTIVACION = _PA
        escuchador = Escuchador()
        hablador = hablador_modulo
    except Exception as e:
        print(f"[main] Voz no disponible, solo modo texto: {e}")

    def _hablar(texto: str):
        """
        Habla por TTS, pausando la captura de audio mientras tanto para
        que el micrófono no se escuche a sí mismo (bucle de feedback).
        """
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
        """Común para botón y activación continua: muestra, procesa, habla."""
        widget.agregar_mensaje(origen, texto)
        respuesta = procesar_comando(texto)
        widget.agregar_mensaje("SOFÍA", respuesta)
        _hablar(respuesta)

    def on_comando(texto: str) -> str:
        return procesar_comando(texto)

    def on_hablar_voz():
        """Botón 'Hablar': una escucha manual, sin necesidad de decir el nombre."""
        if not escuchador:
            widget.agregar_mensaje("SOFÍA", "El micrófono no está disponible en este equipo.")
            return

        texto = escuchador.escuchar_frase(tiempo_espera=6, limite_frase=10)
        if not texto:
            widget.agregar_mensaje("SOFÍA", "No escuché nada, intenta de nuevo.")
            return

        _procesar_y_responder(texto, origen="Tú")

    def hilo_activacion_continua():
        """
        Corre en segundo plano: espera la palabra de activación,
        responde como Alexa y luego escucha el comando.
        """
        if not escuchador:
            return

        while True:
            try:
                resto = escuchador.esperar_activacion()
            except Exception as e:
                print(f"[voz] Error en activación continua: {e}")
                continue

            origen = f"Tú ({PALABRA_ACTIVACION.capitalize()})"
            widget.set_estado("Te escucho...", "#7c3aed")

            if resto:
                _procesar_y_responder(resto, origen=origen)
            else:
                if hablador:
                    _hablar("Dime")
                comando = escuchador.escuchar_frase(tiempo_espera=6, limite_frase=10)
                if comando:
                    _procesar_y_responder(comando, origen=origen)
                else:
                    widget.agregar_mensaje("SOFÍA", "No escuché ningún comando, te sigo escuchando.")

            widget.set_estado("Lista", "#3fb950")

    def hilo_alarmas():
        """
        Revisa cada 20s si alguna alarma activa coincide con la hora
        actual (HH:MM). Si es así, la anuncia (voz + chat) y la
        desactiva (alarma de un solo uso).
        """
        import time
        from datetime import datetime as _dt

        while True:
            try:
                ahora = _dt.now().strftime("%H:%M")
                for alarma in memoria.alarmas_para_disparar(ahora):
                    etiqueta = alarma.get("etiqueta") or "Es la hora que pediste."
                    mensaje = f"⏰ Alarma de las {alarma['hora']}: {etiqueta}"
                    widget.agregar_mensaje("SOFÍA", mensaje)
                    widget.set_estado("¡Alarma!", "#d29922")
                    if hablador:
                        _hablar(f"Alarma. {etiqueta}")
                    widget.set_estado("Lista", "#3fb950")
            except Exception as e:
                print(f"[alarmas] error: {e}")

            time.sleep(20)

    def post_init(widget_creado):
        nonlocal widget
        widget = widget_creado

        widget.agregar_mensaje("SOFÍA", "Hola, soy Sofía. Escribe un comando o presiona Hablar.")
        if escuchador:
            widget.agregar_mensaje(
                "SOFÍA",
                f"También puedes decir '{PALABRA_ACTIVACION.capitalize()}' en "
                f"cualquier momento para darme una orden por voz."
            )
            hilo = threading.Thread(target=hilo_activacion_continua, daemon=True)
            hilo.start()
        else:
            widget.agregar_mensaje("SOFÍA", "Micrófono no disponible. Usa el modo texto.")

        threading.Thread(target=hilo_alarmas, daemon=True).start()

    widget = None
    ejecutar_app(on_comando=on_comando, on_hablar_voz=on_hablar_voz, post_init=post_init)


if __name__ == "__main__":
    main()