"""
Skill de clima. Usa OpenWeatherMap (gratis, requiere API key).
Configura la key en variable de entorno OPENWEATHER_API_KEY.
"""

import os
import re
import requests

API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
CIUDAD_DEFECTO = "Ibague"

KEYWORDS = ["clima", "temperatura", "pronostico", "pronóstico", "llueve", "lluvia", "nublado", "soleado"]


def _extraer_ciudad(texto):
    """
    Extrae el nombre de la ciudad de frases como:
    - "como esta el clima en ibague"
    - "clima de bogota hoy"
    - "que clima hace"
    Devuelve CIUDAD_DEFECTO si no encuentra ninguna.
    """
    texto = texto.lower()
    # quitar palabras de tiempo que estorban al final
    for palabra in ["hoy", "ahora", "mañana", "maniana"]:
        texto = re.sub(rf"\b{palabra}\b", "", texto)
    texto = texto.strip()

    patrones = [
        r"(?:en|de|para)\s+([a-záéíóúñü\s\-]+)$",
    ]
    for patron in patrones:
        m = re.search(patron, texto)
        if m:
            ciudad = m.group(1).strip()
            ciudad = re.sub(r"^(el|la|los|las|un|una)\s+", "", ciudad)
            if ciudad:
                return ciudad

    return CIUDAD_DEFECTO


def consultar_clima(texto):
    ciudad = _extraer_ciudad(texto)

    if not API_KEY:
        return (
            f"No tengo configurada la clave de la API del clima, "
            f"así que no puedo darte el clima real de {ciudad}."
        )

    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": ciudad,
            "appid": API_KEY,
            "units": "metric",
            "lang": "es",
        }
        resp = requests.get(url, params=params, timeout=6)
        data = resp.json()

        if resp.status_code != 200:
            return f"No pude obtener el clima de {ciudad}: {data.get('message', 'error desconocido')}."

        temp = round(data["main"]["temp"])
        sensacion = round(data["main"]["feels_like"])
        descripcion = data["weather"][0]["description"]

        return (
            f"En {ciudad.title()} hay {temp} grados, "
            f"sensación de {sensacion} grados, {descripcion}."
        )
    except Exception as e:
        return f"No pude consultar el clima de {ciudad}: {e}"


def obtener_resumen(ciudad=None):
    """
    Para la tarjeta 'Clima actual' de la interfaz.
    Devuelve un dict:
      {"ok": True, "temp": int, "descripcion": str, "ciudad": str}
      {"ok": False, "mensaje": "Sin conexión"}

    Nunca lanza excepción ni hace que la UI se rompa: si no hay
    API key o falla la consulta, devuelve ok=False con mensaje
    "Sin conexión" para mostrar en la tarjeta.
    """
    ciudad = ciudad or CIUDAD_DEFECTO

    if not API_KEY:
        return {"ok": False, "mensaje": "Sin conexión"}

    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": ciudad,
            "appid": API_KEY,
            "units": "metric",
            "lang": "es",
        }
        resp = requests.get(url, params=params, timeout=4)
        data = resp.json()

        if resp.status_code != 200:
            return {"ok": False, "mensaje": "Sin conexión"}

        return {
            "ok": True,
            "temp": round(data["main"]["temp"]),
            "descripcion": data["weather"][0]["description"].capitalize(),
            "ciudad": ciudad.title(),
        }
    except Exception:
        return {"ok": False, "mensaje": "Sin conexión"}
