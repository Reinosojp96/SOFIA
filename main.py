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
import time
from pathlib import Path

_T_INICIO_PROCESO = time.perf_counter()

sys.path.insert(0, os.path.dirname(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv()  # busca .env en el directorio actual / raíz del proyecto
except ImportError:
    print("[main] python-dotenv no instalado; usando solo variables de entorno del sistema.")

from core.router import router
from core import ia, memoria
from core.context_manager import contexto
from skills import clima, tiempo, sistema, web, aprendizaje, notas, rutina, control_escritorio
from ui.widget import ejecutar_app
from herramientas.diagnostico import registrar_estado, medir_tiempo


def registrar_skills():
    # rutina primero: "buenos días" debe ganar sobre cualquier otro match
    router.registrar("rutina",      rutina.KEYWORDS,       rutina.manejar)
    router.registrar("clima",       clima.KEYWORDS,       clima.consultar_clima)
    router.registrar("tiempo",      tiempo.KEYWORDS,       tiempo.manejar)
    router.registrar("sistema",     sistema.KEYWORDS,      sistema.manejar)
    router.registrar("web",         web.KEYWORDS,          web.manejar)
    router.registrar("notas",       notas.KEYWORDS,        notas.manejar)
    router.registrar("aprendizaje", aprendizaje.KEYWORDS,  aprendizaje.manejar)
    router.registrar("escritorio",  control_escritorio.KEYWORDS, control_escritorio.manejar)

    # Fallback: conversación libre con la IA local, enriquecida con contexto de escritorio
    router.registrar_fallback(_fallback_con_contexto)

    conflictos = router.detectar_conflictos()
    if conflictos:
        print(f"[ROUTER] {len(conflictos)} conflicto(s) de keywords detectados al arrancar.")


def _fallback_con_contexto(texto: str) -> str:
    ctx = contexto.snapshot()
    extra = ""
    if ctx.get("app"):
        extra = f"App activa: {ctx['app']}. Título de ventana: {ctx.get('titulo', '')}."
        resumen = ctx.get("contenido_resumen", "")
        if resumen:
            extra += f" Contenido visible: {resumen}"
    return ia.preguntar(texto, contexto_extra=extra)


def procesar_comando(texto: str) -> str:
    """Punto único de entrada para texto o voz."""
    if not texto or not texto.strip():
        return "No escuché nada."
    return router.procesar(texto)


def _prerender_si_falta():
    """Genera audio estático la primera vez (si no existe data/audio_estatico/dime.wav)."""
    motor = os.environ.get("SOFIA_TTS_MOTOR", "pyttsx3").lower().strip()
    if motor != "qwen":
        return
    marcador = Path(__file__).parent / "data" / "audio_estatico" / "dime.wav"
    if marcador.exists():
        return
    print("[main] Primera ejecución con Qwen: generando audio estático...")
    try:
        from voz.hablar import prerender_frases_estaticas
        nombre = os.environ.get("SOFIA_USER_NAME", "")
        prerender_frases_estaticas(nombre)
    except Exception as e:
        print(f"[main] No se pudo pre-renderizar audio: {e}")


def main():
    # Soporte para python main.py --prerender (regenerar audio estático)
    if "--prerender" in sys.argv:
        from voz.hablar import prerender_frases_estaticas
        nombre = os.environ.get("SOFIA_USER_NAME", "")
        prerender_frases_estaticas(nombre)
        return

    # "Primer arranque" se aproxima viendo si los modelos de voz ya estaban
    # descargados antes de instanciar el Escuchador (que los descarga si
    # faltan) — un arranque posterior con todo ya en disco es mucho más
    # rápido y conviene poder distinguirlo en el reporte de diagnóstico.
    primer_arranque = not (Path(__file__).parent / "data" / "modelos" / "whisper").exists()

    _prerender_si_falta()
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
        """Habla por TTS, pausando captura para evitar feedback."""
        if not hablador:
            return
        if escuchador:
            escuchador.pausar()
        registrar_estado("hablando")
        try:
            hablador.hablar(texto)
        finally:
            if escuchador:
                escuchador.reanudar(retardo=0.35)

    def _hablar_estatico(clave: str) -> bool:
        """Reproduce audio pre-renderizado pausando el micro. Sin GPU."""
        if not hablador:
            return False
        if escuchador:
            escuchador.pausar()
        try:
            return hablador.hablar_estatico(clave)
        finally:
            if escuchador:
                escuchador.reanudar(retardo=0.2)

    def _cargar_modelos_voz():
        """Carga Whisper base + Qwen-TTS en segundo plano."""
        try:
            if escuchador:
                escuchador.cargar_whisper_cmd()
        except Exception as e:
            print(f"[main] Error cargando Whisper cmd: {e}")
        try:
            motor = os.environ.get("SOFIA_TTS_MOTOR", "pyttsx3").lower()
            if motor == "qwen" and hablador:
                # Dispara la carga de Qwen a través de la función pública del módulo
                from voz.hablar import _ensure_qwen
                _ensure_qwen()
                from voz.hablar import _qwen_motor as _qm
                if _qm:
                    _qm.cargar()
        except Exception as e:
            print(f"[main] Error cargando Qwen: {e}")

    def _procesar_y_responder(texto: str, origen: str = "Tú (voz)"):
        """Común para botón y activación continua: muestra, procesa, habla."""
        widget.agregar_mensaje(origen, texto)
        registrar_estado("procesando")
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
        Flujo con lazy loading:
          1. Detecta wake-word (VAD + Whisper tiny, 0 VRAM de Qwen)
          2. Reproduce "Dime" desde .wav pre-renderizado (sin GPU)
          3. En paralelo: carga Whisper base + Qwen-TTS
          4. Escucha el comando con Whisper base
          5. Cuando modelos listos: responde con voz clonada
        """
        if not escuchador:
            return

        while True:
            registrar_estado("reposo")
            try:
                resto = escuchador.esperar_activacion()
            except Exception as e:
                print(f"[voz] Error en activación continua: {e}")
                continue

            origen = f"Tú ({PALABRA_ACTIVACION.capitalize()})"
            registrar_estado("escuchando")
            widget.set_estado("Te escucho...", "#7c3aed")

            # Respuesta inmediata sin GPU
            if not _hablar_estatico("dime"):
                _hablar("Dime")  # fallback si .wav no existe

            # Cargar modelos pesados mientras el usuario formula su pregunta
            hilo_carga = threading.Thread(target=_cargar_modelos_voz, daemon=True)
            hilo_carga.start()

            if resto:
                # El comando ya vino con la activación: esperar modelos y procesar
                hilo_carga.join(timeout=15)
                _procesar_y_responder(resto, origen=origen)
            else:
                # Escuchar comando (carga Whisper cmd si es necesario)
                comando = escuchador.escuchar_frase(tiempo_espera=6, limite_frase=10)
                hilo_carga.join(timeout=15)
                if comando:
                    if not _hablar_estatico("dame_un_momento"):
                        pass  # silencio si no existe el .wav
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

        from datetime import datetime as _dt
        hora = _dt.now().hour
        if hora < 12:
            saludo = "Buenos días"
        elif hora < 19:
            saludo = "Buenas tardes"
        else:
            saludo = "Buenas noches"

        nombre = os.environ.get("SOFIA_USER_NAME", "")
        if nombre:
            bienvenida = f"{saludo}, {nombre}. Bienvenido, estoy lista para ayudarte."
        else:
            bienvenida = f"{saludo}. Bienvenido, soy SOFÍA y estoy lista para ayudarte."

        widget.agregar_mensaje("SOFÍA", bienvenida)

        medir_tiempo(
            "arranque",
            time.perf_counter() - _T_INICIO_PROCESO,
            {"primer_arranque": primer_arranque},
        )

        def _hablar_bienvenida():
            # Intentar saludo estático primero (sin GPU)
            clave_saludo = {"buenos días": "buenos_dias",
                            "buenas tardes": "buenas_tardes",
                            "buenas noches": "buenas_noches"}.get(saludo.lower())
            if hablador and clave_saludo and hablador.hablar_estatico(clave_saludo):
                return
            _hablar(bienvenida)
        threading.Thread(target=_hablar_bienvenida, daemon=True).start()

        if escuchador:
            widget.agregar_mensaje(
                "SOFÍA",
                f"Di '{PALABRA_ACTIVACION.capitalize()}' para activarme por voz."
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