"""
test_skill_clima.py
===================
Pruebas unitarias de skills/clima.py.

Las llamadas HTTP a Open-Meteo se MOCKEAN completamente —
ningún test requiere conexión a Internet.

Cubre:
  - _extraer_ciudad(): detección de ciudad en el texto
  - consultar_clima(): formato de respuesta con datos válidos
  - consultar_clima(): manejo de ciudad no encontrada
  - consultar_clima(): manejo de error de red
  - Caché en memoria (segunda llamada no hace HTTP)
  - Palabras temporales ignoradas ("hoy", "mañana")
"""

import pytest
import time
from unittest.mock import patch, MagicMock
import skills.clima as clima


# ── Helpers de mocks ─────────────────────────────────────────────────────────

def _mock_geocoding_ok(ciudad="Ibague", lat=4.44, lon=-75.23):
    mock = MagicMock()
    mock.json.return_value = {
        "results": [{"latitude": lat, "longitude": lon, "name": ciudad}]
    }
    return mock


def _mock_geocoding_no_results():
    mock = MagicMock()
    mock.json.return_value = {"results": []}
    return mock


def _mock_clima_ok(temp=24, sensacion=23, codigo=0, humedad=65, viento=10.5):
    mock = MagicMock()
    mock.json.return_value = {
        "current": {
            "temperature_2m": temp,
            "apparent_temperature": sensacion,
            "weathercode": codigo,
            "relativehumidity_2m": humedad,
            "windspeed_10m": viento,
        }
    }
    return mock


@pytest.fixture(autouse=True)
def limpiar_cache():
    """Limpia el caché entre tests para evitar contaminación."""
    clima._cache.clear()
    yield
    clima._cache.clear()


# ═══════════════════════════════════════════════════════════
#  _extraer_ciudad()
# ═══════════════════════════════════════════════════════════

class TestExtraerCiudad:

    def test_ciudad_con_preposicion_en(self):
        assert clima._extraer_ciudad("clima en bogota") == "bogota"

    def test_ciudad_con_preposicion_de(self):
        assert clima._extraer_ciudad("temperatura de medellin") == "medellin"

    def test_ciudad_con_preposicion_para(self):
        assert clima._extraer_ciudad("clima para cali") == "cali"

    def test_ciudad_con_articulo_se_elimina(self):
        ciudad = clima._extraer_ciudad("clima en la ciudad")
        assert "la" not in ciudad.lower()

    def test_palabra_hoy_se_ignora(self):
        ciudad = clima._extraer_ciudad("clima en ibague hoy")
        assert "hoy" not in ciudad.lower()
        assert "ibague" in ciudad.lower()

    def test_palabra_manana_se_ignora(self):
        ciudad = clima._extraer_ciudad("clima en bogota mañana")
        assert "mañana" not in ciudad.lower()
        assert "bogota" in ciudad.lower()

    def test_sin_ciudad_devuelve_defecto(self):
        defecto = clima.CIUDAD_DEFECTO
        assert clima._extraer_ciudad("que clima hace") == defecto

    def test_texto_vacio_devuelve_defecto(self):
        assert clima._extraer_ciudad("") == clima.CIUDAD_DEFECTO

    def test_ciudad_con_espacio(self):
        ciudad = clima._extraer_ciudad("clima en santa marta")
        assert "santa marta" in ciudad.lower()


# ═══════════════════════════════════════════════════════════
#  consultar_clima() con mocks
# ═══════════════════════════════════════════════════════════

class TestConsultarClima:

    def test_respuesta_contiene_temperatura(self):
        with patch("skills.clima.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_geocoding_ok("Bogota", 4.71, -74.07),
                _mock_clima_ok(temp=18, sensacion=17, codigo=2, humedad=70)
            ]
            resultado = clima.consultar_clima("clima en bogota")
        assert "18" in resultado
        assert "Bogota" in resultado

    def test_respuesta_contiene_descripcion_wmo(self):
        with patch("skills.clima.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_geocoding_ok(),
                _mock_clima_ok(codigo=61)   # lluvia ligera
            ]
            resultado = clima.consultar_clima("clima en ibague")
        assert "lluvia" in resultado.lower()

    def test_respuesta_cielo_despejado(self):
        with patch("skills.clima.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_geocoding_ok(),
                _mock_clima_ok(codigo=0)   # cielo despejado
            ]
            resultado = clima.consultar_clima("que clima hay")
        assert "despejado" in resultado.lower()

    def test_respuesta_incluye_humedad(self):
        with patch("skills.clima.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_geocoding_ok(),
                _mock_clima_ok(humedad=80)
            ]
            resultado = clima.consultar_clima("clima")
        assert "80" in resultado

    def test_ciudad_no_encontrada_devuelve_mensaje(self):
        with patch("skills.clima.requests.get") as mock_get:
            mock_get.return_value = _mock_geocoding_no_results()
            resultado = clima.consultar_clima("clima en xyzxyzxyz")
        assert "No encontré" in resultado or "no encontré" in resultado.lower()

    def test_error_de_red_geocoding_devuelve_mensaje(self):
        with patch("skills.clima.requests.get") as mock_get:
            mock_get.side_effect = Exception("timeout")
            resultado = clima.consultar_clima("clima en bogota")
        # No debe crashear, debe devolver un mensaje amigable
        assert isinstance(resultado, str)
        assert len(resultado) > 0

    def test_error_de_red_clima_devuelve_mensaje(self):
        def side_effect(url, **kwargs):
            if "geocoding" in url:
                return _mock_geocoding_ok()
            raise Exception("timeout en clima")

        with patch("skills.clima.requests.get", side_effect=side_effect):
            resultado = clima.consultar_clima("clima en bogota")
        assert isinstance(resultado, str)
        assert len(resultado) > 0


# ═══════════════════════════════════════════════════════════
#  Caché
# ═══════════════════════════════════════════════════════════

class TestCache:

    def test_segunda_llamada_no_hace_http(self):
        with patch("skills.clima.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_geocoding_ok(),
                _mock_clima_ok(temp=24)
            ]
            clima.consultar_clima("clima en ibague")
            clima.consultar_clima("clima en ibague")   # segunda vez: de caché
        # Solo se deben haber hecho 2 llamadas HTTP (geo + clima), no 4
        assert mock_get.call_count == 2

    def test_cache_expira_tras_ttl(self, monkeypatch):
        """Simula que el TTL expiró forzando timestamps viejos."""
        with patch("skills.clima.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_geocoding_ok(), _mock_clima_ok(temp=20),
                _mock_geocoding_ok(), _mock_clima_ok(temp=25),
            ]
            clima.consultar_clima("clima en ibague")
            # Envejece la entrada de caché
            key = "ibague"
            ts, result = clima._cache[key]
            clima._cache[key] = (ts - clima._CACHE_TTL - 1, result)
            # Segunda llamada debe refrescar
            clima.consultar_clima("clima en ibague")
        assert mock_get.call_count == 4

    def test_ciudades_distintas_se_cachean_por_separado(self):
        with patch("skills.clima.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_geocoding_ok("Bogota"), _mock_clima_ok(temp=18),
                _mock_geocoding_ok("Cali"),   _mock_clima_ok(temp=28),
            ]
            r1 = clima.consultar_clima("clima en bogota")
            r2 = clima.consultar_clima("clima en cali")
        assert "18" in r1
        assert "28" in r2
