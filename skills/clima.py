"""
Skill de clima usando Open-Meteo (gratuito, sin API key).

Flujo:
  1. Geocodificación: Open-Meteo Geocoding API → latitud/longitud de la ciudad
  2. Clima actual: Open-Meteo Weather API → temperatura, sensación, descripción
  3. Caché en memoria (5 minutos) para no repetir llamadas si el usuario
     pregunta varias veces seguidas.

Ventajas sobre OpenWeatherMap:
  - Sin API key (cero configuración para el usuario/demo)
  - Sin límite de peticiones
  - Datos en tiempo real con resolución horaria
"""

import os
import re
import time
import requests

CIUDAD_DEFECTO = os.environ.get("SOFIA_CIUDAD", "Ibague")

KEYWORDS = [
    "clima", "temperatura", "pronostico", "pronóstico",
    "llueve", "lluvia", "nublado", "soleado", "calor", "frio", "frío",
    "tiempo", "como esta el tiempo", "como va el tiempo",
]

# Caché en memoria: {ciudad_lower: (timestamp, resultado)}
_cache: dict = {}
_CACHE_TTL = 300  # segundos (5 minutos)

# Descripción en español de los códigos WMO de Open-Meteo
_WMO_CODES = {
    0: "cielo despejado",
    1: "mayormente despejado", 2: "parcialmente nublado", 3: "nublado",
    45: "niebla", 48: "niebla con escarcha",
    51: "llovizna ligera", 53: "llovizna moderada", 55: "llovizna intensa",
    61: "lluvia ligera", 63: "lluvia moderada", 65: "lluvia intensa",
    71: "nieve ligera", 73: "nieve moderada", 75: "nieve intensa",
    77: "granizo",
    80: "chubascos ligeros", 81: "chubascos moderados", 82: "chubascos intensos",
    85: "nevadas ligeras", 86: "nevadas intensas",
    95: "tormenta eléctrica", 96: "tormenta con granizo ligero",
    99: "tormenta con granizo intenso",
}


def _geocodificar(ciudad: str) -> tuple[float, float] | None:
    """Devuelve (latitud, longitud) o None si no se encuentra la ciudad."""
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        resp = requests.get(url, params={"name": ciudad, "count": 1, "language": "es"}, timeout=5)
        data = resp.json()
        resultados = data.get("results")
        if not resultados:
            return None
        r = resultados[0]
        return r["latitude"], r["longitude"]
    except Exception:
        return None


def _consultar_openmeteo(lat: float, lon: float) -> dict | None:
    """Consulta el clima actual en las coordenadas dadas."""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": [
                "temperature_2m",
                "apparent_temperature",
                "weathercode",
                "windspeed_10m",
                "relativehumidity_2m",
            ],
            "timezone": "auto",
        }
        resp = requests.get(url, params=params, timeout=5)
        return resp.json().get("current")
    except Exception:
        return None


def _obtener_clima_ciudad(ciudad: str) -> dict:
    """
    Devuelve un dict con el clima de la ciudad.
    Formato: {"ok": True, "temp": int, "sensacion": int,
              "descripcion": str, "ciudad": str, "humedad": int, "viento": float}
    O: {"ok": False, "mensaje": str}
    """
    ciudad_key = ciudad.lower().strip()
    ahora = time.time()

    # Revisar caché
    if ciudad_key in _cache:
        ts, resultado = _cache[ciudad_key]
        if ahora - ts < _CACHE_TTL:
            return resultado

    coords = _geocodificar(ciudad)
    if not coords:
        resultado = {"ok": False, "mensaje": f"No encontré la ciudad '{ciudad}'."}
        _cache[ciudad_key] = (ahora, resultado)
        return resultado

    lat, lon = coords
    datos = _consultar_openmeteo(lat, lon)
    if not datos:
        resultado = {"ok": False, "mensaje": "No pude obtener el clima en este momento."}
        _cache[ciudad_key] = (ahora, resultado)
        return resultado

    codigo = datos.get("weathercode", 0)
    descripcion = _WMO_CODES.get(codigo, "condición desconocida")

    resultado = {
        "ok": True,
        "temp": round(datos.get("temperature_2m", 0)),
        "sensacion": round(datos.get("apparent_temperature", 0)),
        "descripcion": descripcion,
        "ciudad": ciudad.title(),
        "humedad": datos.get("relativehumidity_2m"),
        "viento": datos.get("windspeed_10m"),
    }
    _cache[ciudad_key] = (ahora, resultado)
    return resultado


def _extraer_ciudad(texto: str) -> str:
    """
    Extrae el nombre de la ciudad de frases como:
      'cómo está el clima en ibagué hoy'
      'clima de bogotá'
      'qué tiempo hace'
    Si no se detecta, devuelve CIUDAD_DEFECTO.
    """
    texto = texto.lower()
    # Quitar palabras temporales
    for palabra in ["hoy", "ahora", "mañana", "maniana", "esta semana"]:
        texto = re.sub(rf"\b{palabra}\b", "", texto)
    texto = texto.strip()

    patrones = [
        r"(?:en|de|para)\s+([a-záéíóúñü][a-záéíóúñü\s\-]{1,30})$",
    ]
    for patron in patrones:
        m = re.search(patron, texto)
        if m:
            ciudad = m.group(1).strip()
            ciudad = re.sub(r"^(el|la|los|las|un|una)\s+", "", ciudad)
            if ciudad:
                return ciudad

    return CIUDAD_DEFECTO


# ---------------------------------------------------------------------------
# Funciones públicas
# ---------------------------------------------------------------------------

def consultar_clima(texto: str) -> str:
    """Para el router de SOFÍA: recibe el texto del usuario, devuelve respuesta hablada."""
    ciudad = _extraer_ciudad(texto)
    info = _obtener_clima_ciudad(ciudad)

    if not info["ok"]:
        return info["mensaje"]

    respuesta = (
        f"En {info['ciudad']} hay {info['temp']} grados, "
        f"sensación de {info['sensacion']} grados, {info['descripcion']}."
    )
    if info.get("humedad"):
        respuesta += f" Humedad del {info['humedad']}%."

    return respuesta


def obtener_resumen(ciudad: str = None) -> dict:
    """
    Para la tarjeta de clima en la UI.
    Devuelve el mismo dict que _obtener_clima_ciudad.
    Si ciudad es None, usa CIUDAD_DEFECTO.
    """
    return _obtener_clima_ciudad(ciudad or CIUDAD_DEFECTO)