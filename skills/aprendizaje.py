"""
Skill de aprendizaje automático.

Permite a SOFÍA registrar errores, ver estadísticas de uso y recibir
correcciones mediante comandos de voz o texto.

Ejemplos de comandos:
  "sofia, estadísticas"
  "sofia, qué no entiendes"
  "sofia, aprende que decir 'pon reggaeton' significa abrir YouTube"
"""

from core import ia as _ia
from core.router import router as _router

KEYWORDS = [
    "estadisticas", "estadísticas", "que no entiendes", "qué no entiendes",
    "aprende que", "aprende a", "corrección", "correccion",
    "cuantas preguntas", "cuántas preguntas", "resumen de uso",
]


def manejar(texto: str) -> str:
    if any(p in texto for p in ["estadistica", "resumen de uso", "cuantas preguntas"]):
        return _ia.obtener_estadisticas() + " " + _router.stats()

    if "que no entiendes" in texto or "no puedes responder" in texto:
        data = _ia._leer_aprendizaje()
        fallidas = data.get("frases_fallidas", [])
        if not fallidas:
            return "No tengo frases fallidas registradas aún."
        recientes = [f["texto"] for f in fallidas[-5:]]
        return "Las últimas frases que no pude responder fueron: " + ". ".join(recientes) + "."

    if "aprende que" in texto or "aprende a" in texto:
        # Formato esperado: "aprende que [frase] significa [respuesta]"
        import re
        m = re.search(r"aprende que (.+?) significa (.+)", texto)
        if m:
            frase = m.group(1).strip()
            respuesta = m.group(2).strip()
            return _ia.agregar_correccion(frase, respuesta)
        return "No entendí. Dime: aprende que [frase] significa [respuesta]."

    return "No entendí la solicitud de aprendizaje."