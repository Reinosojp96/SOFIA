"""
Skill de notas: crear y leer notas rápidas por voz.

Usa el mismo archivo que la app de escritorio NebulaNotes
(~/Documentos/nebula_notes.json), así las notas creadas por voz
aparecen ahí, y las que escribas en NebulaNotes pueden leerse aquí.
"""

from core import memoria

KEYWORDS = [
    "anota", "anotar", "apunta", "apuntar",
    "crea una nota", "crear nota", "nueva nota",
    "lee mi nota", "lee mis notas", "que dice mi nota",
    "que dice mi ultima nota", "que dice mi última nota",
    "ultima nota", "última nota",
]

# Frases que se quitan del comando para quedarnos con el contenido
_PREFIJOS_CREAR = [
    "anota que", "anota", "anotar que", "anotar",
    "apunta que", "apunta", "apuntar que", "apuntar",
    "crea una nota que diga", "crea una nota que dice", "crea una nota",
    "crear nota", "nueva nota",
]


def _crear_nota(texto):
    contenido = texto
    for prefijo in _PREFIJOS_CREAR:
        if prefijo in contenido:
            contenido = contenido.split(prefijo, 1)[-1].strip(' :,')
            break

    if not contenido:
        return "¿Qué quieres que anote?"

    memoria.agregar_nota(contenido)
    return f"Anotado: {contenido}."


def _leer_ultima_nota(_texto=None):
    nota = memoria.ultima_nota()
    if not nota:
        return "No tienes ninguna nota guardada."

    contenido = nota.get("content", "").strip()
    if not contenido:
        return f"Tu última nota se llama '{nota.get('title', 'sin título')}' pero está vacía."

    return f"Tu última nota dice: {contenido}"


def manejar(texto):
    if any(p in texto for p in ["lee mi nota", "lee mis notas", "que dice mi", "ultima nota", "última nota"]):
        return _leer_ultima_nota(texto)

    if any(p in texto for p in ["anota", "anotar", "apunta", "apuntar", "crea una nota", "crear nota", "nueva nota"]):
        return _crear_nota(texto)

    return "No entendí la solicitud de notas."