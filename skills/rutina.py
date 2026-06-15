"""
Skill de rutina matutina (y de "despertar").

Cuando el usuario dice "buenos días", "despierta", o variantes,
SOFÍA ejecuta en secuencia:
  1. Saludo personalizado según la hora real
  2. Resumen del clima para hoy
  3. Abre WhatsApp (app de escritorio si existe, sino WhatsApp Web)
     + avisa que lo abrió para que revise mensajes (leer mensajes
     de WhatsApp requiere API oficial de negocio, fuera de alcance)
  4. Resume eventos y recordatorios del día

Cualquiera de las partes que falle (sin API de clima, sin eventos,
etc.) se maneja con gracia: SOFÍA lo menciona y sigue con lo demás.
"""

import os
import sys
import subprocess
import webbrowser
from datetime import datetime

KEYWORDS = [
    "buenos días", "buenos dias",
    "despierta", "despiértate",
    "buenas tardes", "buenas noches",
    "morning", "wake up",
    "inicio del día", "inicio del dia",
    "resumen del día", "resumen del dia",
    "qué hay para hoy", "que hay para hoy",
]


def _saludo_hora() -> str:
    hora = datetime.now().hour
    if hora < 12:
        return "Buenos días"
    if hora < 19:
        return "Buenas tardes"
    return "Buenas noches"


def _resumen_clima() -> str:
    try:
        from skills.clima import obtener_resumen
        info = obtener_resumen()
        if info and info.get("ok"):
            return (
                f"El clima en {info['ciudad']} hoy está a {info['temp']} grados, "
                f"{info['descripcion'].lower()}."
            )
        return "No pude obtener el clima para hoy, puede que no haya conexión."
    except Exception as e:
        return f"No pude consultar el clima: {e}"


def _abrir_whatsapp() -> str:
    """
    Intenta abrir WhatsApp de escritorio. Si no está instalado,
    abre WhatsApp Web en el navegador. Devuelve un mensaje para el usuario.
    """
    # Rutas comunes de WhatsApp en Windows
    rutas_windows = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "WhatsApp", "WhatsApp.exe"),
        os.path.join(os.environ.get("APPDATA", ""), "WhatsApp", "WhatsApp.exe"),
    ]

    if sys.platform == "win32":
        # Intentar por ruta directa
        for ruta in rutas_windows:
            if os.path.exists(ruta):
                try:
                    subprocess.Popen([ruta])
                    return (
                        "Abrí WhatsApp. No puedo leer tus mensajes directamente, "
                        "pero puedes revisarlos ahí."
                    )
                except Exception:
                    pass
        # Intentar por startfile (funciona si WhatsApp está en el Menú Inicio)
        try:
            os.startfile("whatsapp:")
            return (
                "Abrí WhatsApp. Revisa tus mensajes nuevos ahí, "
                "no tengo acceso directo a ellos."
            )
        except Exception:
            pass

    # Fallback: WhatsApp Web
    webbrowser.open("https://web.whatsapp.com")
    return (
        "No encontré WhatsApp instalado, abrí WhatsApp Web en tu navegador. "
        "Revisa tus mensajes ahí."
    )


def _resumen_agenda() -> str:
    try:
        from core import memoria
        from datetime import datetime as _dt

        hoy = _dt.now().strftime("%Y-%m-%d")
        eventos = [e for e in memoria.listar_eventos() if e.get("fecha") == hoy]
        alarmas = memoria.listar_alarmas(solo_activas=True)
        tareas = memoria.listar_tareas(solo_pendientes=True)

        partes = []

        if eventos:
            if len(eventos) == 1:
                e = eventos[0]
                hora_str = f" a las {e['hora']}" if e.get("hora") else ""
                partes.append(f"tienes un evento hoy{hora_str}: {e['titulo']}")
            else:
                partes.append(f"tienes {len(eventos)} eventos agendados hoy")

        if alarmas:
            horas = ", ".join(a["hora"] for a in alarmas[:3])
            partes.append(f"tienes alarmas a las {horas}")

        if tareas:
            partes.append(
                f"tienes {len(tareas)} tarea{'s' if len(tareas) > 1 else ''} pendiente{'s' if len(tareas) > 1 else ''}"
            )

        if not partes:
            return "No tienes eventos, alarmas ni tareas pendientes para hoy. Día libre."

        return "En tu agenda: " + ", y ".join(partes) + "."

    except Exception as e:
        return f"No pude revisar tu agenda: {e}"


def manejar(texto: str) -> str:
    """
    Ejecuta la rutina completa y devuelve el resumen en un solo
    bloque de texto para que SOFÍA lo lea de corrido.
    """
    nombre = os.environ.get("SOFIA_USER_NAME", "")
    saludo = _saludo_hora()
    saludo_completo = f"{saludo}{', ' + nombre + '.' if nombre else '.'}"

    partes = [saludo_completo]
    partes.append(_resumen_clima())
    partes.append(_abrir_whatsapp())
    partes.append(_resumen_agenda())

    return " ".join(partes)