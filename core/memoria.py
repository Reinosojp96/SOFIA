"""
Persistencia local simple en JSON: eventos, alarmas, tareas pendientes.
Sin base de datos, sin dependencias externas.
"""

import json
import os
from datetime import datetime

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_DB_PATH = os.path.join(_DATA_DIR, "memoria.json")

_DEFAULT = {
    "eventos": [],     # {id, titulo, fecha, hora}
    "alarmas": [],      # {id, hora, etiqueta, activa}
    "tareas": [],       # {id, texto, hecha}
}


def _asegurar_archivo():
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.exists(_DB_PATH):
        with open(_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT, f, ensure_ascii=False, indent=2)


def _leer():
    _asegurar_archivo()
    with open(_DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _guardar(data):
    with open(_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _siguiente_id(lista):
    if not lista:
        return 1
    return max(item["id"] for item in lista) + 1


# ---------- Eventos ----------

def agregar_evento(titulo, fecha, hora=None):
    data = _leer()
    nuevo = {
        "id": _siguiente_id(data["eventos"]),
        "titulo": titulo,
        "fecha": fecha,
        "hora": hora,
        "creado": datetime.now().isoformat(),
    }
    data["eventos"].append(nuevo)
    _guardar(data)
    return nuevo


def listar_eventos():
    return _leer()["eventos"]


def eliminar_evento(evento_id):
    data = _leer()
    data["eventos"] = [e for e in data["eventos"] if e["id"] != evento_id]
    _guardar(data)


# ---------- Alarmas ----------

def agregar_alarma(hora, etiqueta=""):
    data = _leer()
    nueva = {
        "id": _siguiente_id(data["alarmas"]),
        "hora": hora,  # "HH:MM"
        "etiqueta": etiqueta,
        "activa": True,
    }
    data["alarmas"].append(nueva)
    _guardar(data)
    return nueva


def listar_alarmas(solo_activas=True):
    alarmas = _leer()["alarmas"]
    if solo_activas:
        return [a for a in alarmas if a["activa"]]
    return alarmas


def desactivar_alarma(alarma_id):
    data = _leer()
    for a in data["alarmas"]:
        if a["id"] == alarma_id:
            a["activa"] = False
    _guardar(data)


def alarmas_para_disparar(hora_actual):
    """
    Devuelve las alarmas activas cuya 'hora' (HH:MM) coincide con
    hora_actual (HH:MM), y las desactiva de inmediato (alarmas de un
    solo uso, como un "despiértame a las X").

    Pensado para llamarse periódicamente (cada ~20-30s) desde un hilo
    de fondo en main.py.
    """
    data = _leer()
    disparadas = []
    for a in data["alarmas"]:
        if a["activa"] and a["hora"] == hora_actual:
            a["activa"] = False
            disparadas.append(dict(a))
    if disparadas:
        _guardar(data)
    return disparadas


# ---------- Tareas ----------

def agregar_tarea(texto):
    data = _leer()
    nueva = {
        "id": _siguiente_id(data["tareas"]),
        "texto": texto,
        "hecha": False,
    }
    data["tareas"].append(nueva)
    _guardar(data)
    return nueva


def listar_tareas(solo_pendientes=True):
    tareas = _leer()["tareas"]
    if solo_pendientes:
        return [t for t in tareas if not t["hecha"]]
    return tareas


def completar_tarea(tarea_id):
    data = _leer()
    for t in data["tareas"]:
        if t["id"] == tarea_id:
            t["hecha"] = True
    _guardar(data)


# ---------- Resumen para la interfaz ----------

def contar_tareas_pendientes():
    """Para la tarjeta 'Tareas pendientes' de la UI."""
    return len(listar_tareas(solo_pendientes=True))


def contar_eventos_hoy():
    """Para la tarjeta 'Recordatorios hoy' de la UI."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    return len([e for e in listar_eventos() if e.get("fecha") == hoy])


# ---------------------------------------------------------------------------
# Notas (compatibles con NebulaNotes: ~/Documentos/nebula_notes.json)
# ---------------------------------------------------------------------------
#
# Se usa el MISMO archivo y formato que tu app NebulaNotes (.pyw), así
# las notas creadas por voz aparecen ahí y viceversa. No se toca la
# papelera ni nada más de ese archivo: solo la lista "notes".

from pathlib import Path

_NOTAS_PATH = Path.home() / "Documentos" / "nebula_notes.json"


def _leer_notas_archivo():
    if not _NOTAS_PATH.exists():
        return {"notes": []}
    try:
        with open(_NOTAS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("notes", [])
            return data
    except Exception:
        return {"notes": []}


def _guardar_notas_archivo(data):
    _NOTAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_NOTAS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def agregar_nota(contenido, titulo=None):
    """
    Crea una nota nueva (al principio de la lista, igual que NebulaNotes
    al pulsar '+ NUEVA'). Si no se da título, usa la fecha/hora actual.
    """
    data = _leer_notas_archivo()

    ahora = datetime.now()
    if not titulo:
        titulo = f"Nota de voz {ahora.strftime('%d/%m %H:%M')}"

    nueva = {
        "id": ahora.timestamp(),
        "title": titulo,
        "content": contenido,
        "created": ahora.isoformat(),
        "modified": ahora.isoformat(),
    }
    data["notes"].insert(0, nueva)
    _guardar_notas_archivo(data)
    return nueva


def listar_notas():
    """Devuelve la lista de notas (más reciente primero)."""
    return _leer_notas_archivo()["notes"]


def ultima_nota():
    notas = listar_notas()
    return notas[0] if notas else None

# ---------- Resumen para la interfaz ----------

def contar_tareas_pendientes():
    """Para la tarjeta 'Tareas pendientes' de la UI."""
    return len(listar_tareas(solo_pendientes=True))


def contar_eventos_hoy():
    """Para la tarjeta 'Recordatorios hoy' de la UI."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    return len([e for e in listar_eventos() if e.get("fecha") == hoy])
