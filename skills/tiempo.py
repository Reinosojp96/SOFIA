"""
Skill de tiempo: hora, fecha, alarmas y agenda local.

MEJORAS v2:
  - Agrega función listar_agenda() que responde "qué tengo hoy/mañana"
    (estaba en memoria pero sin skill que la expusiera por voz)
  - Quita duplicados de lógica en manejar()
  - Maneja "manana" (sin tilde) además de "mañana"
"""

import re
from datetime import datetime, timedelta
from core import memoria

KEYWORDS = [
    "hora", "fecha", "que dia es", "que día es",
    "alarma", "despiertame", "despertame", "despiertame",
    "recuerdame", "recordatorio", "evento", "agenda", "agendar",
    "que tengo", "tengo algo", "mis eventos",
    "tareas pendientes", "mis tareas", "que tareas", "tarea",
]


# ---------------------------------------------------------------------------
# Hora y fecha
# ---------------------------------------------------------------------------

def _decir_hora(_texto=None) -> str:
    ahora = datetime.now()
    return f"Son las {ahora.strftime('%H:%M')}."


def _decir_fecha(_texto=None) -> str:
    ahora = datetime.now()
    dias   = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses  = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
               "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return f"Hoy es {dias[ahora.weekday()]}, {ahora.day} de {meses[ahora.month - 1]} de {ahora.year}."


# ---------------------------------------------------------------------------
# Alarmas
# ---------------------------------------------------------------------------

def _crear_alarma(texto: str) -> str:
    m = re.search(r"(\d{1,2})[:h](\d{2})", texto)
    if m:
        hora = f"{int(m.group(1)):02d}:{m.group(2)}"
    else:
        m = re.search(r"a las (\d{1,2})", texto)
        if m:
            hora = f"{int(m.group(1)):02d}:00"
        else:
            return "No entendí a qué hora poner la alarma. Dime por ejemplo: alarma a las 7 y 30."

    alarma = memoria.agregar_alarma(hora, etiqueta=texto)
    return f"Alarma creada para las {alarma['hora']}."


# ---------------------------------------------------------------------------
# Eventos / agenda
# ---------------------------------------------------------------------------

def _crear_evento(texto: str) -> str:
    fecha = datetime.now().strftime("%Y-%m-%d")
    if "mañana" in texto or "manana" in texto:
        fecha = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    hora = None
    m = re.search(r"(\d{1,2})[:h](\d{2})", texto)
    if m:
        hora = f"{int(m.group(1)):02d}:{m.group(2)}"

    evento = memoria.agregar_evento(texto, fecha, hora)
    if hora:
        return f"Evento agendado para el {evento['fecha']} a las {hora}."
    return f"Evento agendado para el {evento['fecha']}."


def _listar_agenda(texto: str) -> str:
    """Responde a 'qué tengo hoy', 'qué tengo mañana', 'mis eventos'."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    if "mañana" in texto or "manana" in texto:
        fecha_filtro = manana
        etiqueta = "mañana"
    else:
        fecha_filtro = hoy
        etiqueta = "hoy"

    eventos = [e for e in memoria.listar_eventos() if e.get("fecha") == fecha_filtro]

    if not eventos:
        return f"No tienes eventos agendados para {etiqueta}."

    if len(eventos) == 1:
        e = eventos[0]
        hora_str = f" a las {e['hora']}" if e.get("hora") else ""
        return f"Tienes un evento {etiqueta}{hora_str}: {e['titulo']}."

    resumen = ", ".join(
        (f"{e['titulo']} a las {e['hora']}" if e.get("hora") else e["titulo"])
        for e in eventos[:3]
    )
    return f"Tienes {len(eventos)} eventos {etiqueta}: {resumen}."


# ---------------------------------------------------------------------------
# Tareas pendientes
# ---------------------------------------------------------------------------

def _listar_tareas(_texto: str = None) -> str:
    """Responde a 'qué tareas tengo', 'mis tareas pendientes'."""
    tareas = memoria.listar_tareas(solo_pendientes=True)

    if not tareas:
        return "No tienes tareas pendientes."

    if len(tareas) == 1:
        return f"Tienes una tarea pendiente: {tareas[0]['texto']}."

    resumen = ", ".join(t["texto"] for t in tareas[:5])
    return f"Tienes {len(tareas)} tareas pendientes: {resumen}."


def _crear_tarea(texto: str) -> str:
    """Crea una tarea a partir de 'agrega la tarea X' / 'nueva tarea X'."""
    resto = texto
    for prefijo in ["agrega la tarea", "agregar tarea", "nueva tarea", "crear tarea", "tarea"]:
        if prefijo in resto:
            resto = resto.split(prefijo, 1)[-1].strip(' :')
            break

    if not resto:
        return "¿Cuál es la tarea que quieres agregar?"

    memoria.agregar_tarea(resto)
    return f"Tarea agregada: {resto}."


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def manejar(texto: str) -> str:
    if "hora" in texto:
        return _decir_hora()

    if "fecha" in texto or "dia es" in texto:
        return _decir_fecha()

    if any(p in texto for p in ["alarma", "despiertame", "despertame"]):
        return _crear_alarma(texto)

    # Tareas: primero "agrega/crea tarea X" (crear), si no, "qué tareas tengo" (listar)
    if any(p in texto for p in ["agrega la tarea", "agregar tarea", "nueva tarea", "crear tarea"]):
        return _crear_tarea(texto)

    if any(p in texto for p in ["tareas pendientes", "mis tareas", "que tareas"]):
        return _listar_tareas()

    # Eventos: "agéndame/recuérdame X" (crear) tiene prioridad sobre "agenda" como
    # consulta, ya que "agenda" es substring de "agendar".
    if any(p in texto for p in ["recuerdame", "recordatorio", "agendar", "agéndame", "agendame"]):
        return _crear_evento(texto)

    if any(p in texto for p in ["que tengo", "tengo algo", "mis eventos", "agenda", "evento"]):
        return _listar_agenda(texto)

    return "No entendí la solicitud de tiempo o agenda."