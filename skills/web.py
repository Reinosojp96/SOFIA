"""
Skill web: reproducir videos en YouTube, búsquedas en internet, noticias (RSS).

MEJORAS v2:
  - reproducir_youtube(): usa yt-dlp para obtener el primer resultado y abrir
    el video directamente (autoplay), en vez de la página de resultados.
  - buscar_en_internet(): usa duckduckgo-search (DDGS) para leer los 3 primeros
    snippets en voz y además abre Google en el navegador.
  - Ambas funciones tienen fallback al comportamiento anterior si las deps faltan.
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
        texto, ["en youtube", "youtube", "reproduce", "reproducir",
                "pon musica", "pon música", "pon", "toca"]
    )
    if not consulta:
        webbrowser.open("https://www.youtube.com")
        return "Abriendo YouTube."

    # Intentar obtener el primer video directamente con yt-dlp
    try:
        import yt_dlp
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "playlist_items": "1",
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{consulta}", download=False)
        entries = info.get("entries", [])
        if entries and entries[0].get("id"):
            video_id = entries[0]["id"]
            webbrowser.open(f"https://www.youtube.com/watch?v={video_id}&autoplay=1")
            return f"Reproduciendo {consulta} en YouTube."
    except Exception:
        pass

    # Fallback: abrir página de resultados de búsqueda
    url = f"https://www.youtube.com/results?search_query={consulta.replace(' ', '+')}"
    webbrowser.open(url)
    return f"Buscando {consulta} en YouTube."


def buscar_en_internet(texto):
    consulta = _extraer_consulta(
        texto, ["buscar", "busca", "investiga", "en google", "google", "en internet"]
    )
    if not consulta:
        return "¿Qué quieres que busque?"

    url_google = f"https://www.google.com/search?q={consulta.replace(' ', '+')}"

    # Intentar leer resultados con DDGS (paquete renombrado de duckduckgo_search a ddgs)
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            resultados = list(ddgs.text(consulta, max_results=3))
        if resultados:
            snippets = [r["body"][:120] for r in resultados if r.get("body")]
            if snippets:
                resumen = ". ".join(snippets)
                webbrowser.open(url_google)
                return f"Esto es lo que encontré sobre {consulta}: {resumen}"
    except Exception:
        pass

    # Fallback: solo abrir el navegador
    webbrowser.open(url_google)
    return f"Abrí los resultados de '{consulta}' en el navegador."


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
        return buscar_en_internet(texto)

    return "No entendí la solicitud web."
