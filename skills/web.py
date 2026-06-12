"""
Skill web: abrir youtube/buscar videos, búsquedas en Google, noticias (RSS).
"""

import re
import webbrowser
import requests

KEYWORDS = [
    "youtube", "reproduce", "reproducir", "pon musica", "pon música",
    "buscar", "busca", "investiga", "google",
    "noticias", "titulares",
]

NOTICIAS_RSS = "https://news.google.com/rss?hl=es&gl=CO&ceid=CO:es"


def _extraer_consulta(texto, palabras_quitar):
    consulta = texto
    for palabra in palabras_quitar:
        consulta = consulta.replace(palabra, "")
    return consulta.strip()


def reproducir_youtube(texto):
    consulta = _extraer_consulta(
        texto, ["en youtube", "youtube", "reproduce", "reproducir", "pon musica", "pon música", "pon", "toca"]
    )
    if not consulta:
        webbrowser.open("https://www.youtube.com")
        return "Abriendo YouTube."

    url = f"https://www.youtube.com/results?search_query={consulta.replace(' ', '+')}"
    webbrowser.open(url)
    return f"Buscando {consulta} en YouTube."


def buscar_google(texto):
    consulta = _extraer_consulta(texto, ["buscar", "busca", "investiga", "en google", "google"])
    if not consulta:
        return "¿Qué quieres que busque?"

    url = f"https://www.google.com/search?q={consulta.replace(' ', '+')}"
    webbrowser.open(url)
    return f"Busqué '{consulta}' y abrí los resultados en el navegador."


def consultar_noticias(_texto=None):
    try:
        resp = requests.get(NOTICIAS_RSS, timeout=6)
        titulos = re.findall(r"<title>(.*?)</title>", resp.text)
        # el primer <title> es el del feed, lo saltamos
        titulares = titulos[1:4]
        if not titulares:
            return "No encontré noticias en este momento."
        return "Estas son las noticias principales: " + ". ".join(titulares) + "."
    except Exception as e:
        return f"No pude obtener noticias: {e}"


def manejar(texto):
    if "noticias" in texto or "titulares" in texto:
        return consultar_noticias()

    if "youtube" in texto or any(p in texto for p in ["reproduce", "reproducir", "pon musica", "pon música"]):
        return reproducir_youtube(texto)

    if any(p in texto for p in ["buscar", "busca", "investiga", "google"]):
        return buscar_google(texto)

    return "No entendí la solicitud web."
