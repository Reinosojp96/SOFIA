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
