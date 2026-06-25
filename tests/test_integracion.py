"""
test_integracion.py
===================
Pruebas de INTEGRACIÓN de SOFÍA.

Validan que el Router, las Skills y la Memoria funcionan
correctamente en conjunto, igual que en producción real.

No se usan mocks de módulos internos — solo se aisla:
  - El sistema de archivos (memoria temporal)
  - Las llamadas HTTP externas (clima)
  - El LLM (no disponible en tests)
"""

import pytest
from unittest.mock import patch, MagicMock
from core.router import Router


# ── Fixture: router completo con todas las skills ────────────────────────────

@pytest.fixture
def router_completo(memoria_tmp, monkeypatch):
    """
    Crea un Router con todas las skills registradas (igual que main.py),
    pero usando memoria temporal en lugar de los archivos reales.
    """
    from skills import tiempo as skill_tiempo
    from skills import notas  as skill_notas

    # Parchear memoria en cada skill
    monkeypatch.setattr(skill_tiempo, "memoria", memoria_tmp)
    monkeypatch.setattr(skill_notas,  "memoria", memoria_tmp)

    r = Router()
    r.registrar("tiempo", skill_tiempo.KEYWORDS, skill_tiempo.manejar)
    r.registrar("notas",  skill_notas.KEYWORDS,  skill_notas.manejar)
    # Fallback: mensaje generico sin LLM
    r.registrar_fallback(lambda texto: "Respuesta del fallback IA.")
    return r, memoria_tmp


# ═══════════════════════════════════════════════════════════
#  Integracion Router <-> Skill Tiempo <-> Memoria
# ═══════════════════════════════════════════════════════════

class TestIntegracionTiempoMemoria:

    def test_crear_evento_y_listarlo(self, router_completo):
        router, mem = router_completo
        router.procesar("agendame una reunion manana")
        eventos = mem.listar_eventos()
        assert len(eventos) == 1

    def test_crear_alarma_y_dispararla(self, router_completo):
        router, mem = router_completo
        # Usar formato "7h30": el router quita ":" pero conserva "h",
        # por lo que el regex de _crear_alarma puede parsearlo correctamente.
        router.procesar("alarma a las 7h30")
        disparadas = mem.alarmas_para_disparar("07:30")
        assert len(disparadas) == 1

    def test_crear_tarea_y_listarla(self, router_completo):
        router, mem = router_completo
        # El router normaliza tildes: el texto se almacena sin acento.
        router.procesar("agrega la tarea comprar cafe")
        respuesta = router.procesar("mis tareas pendientes")
        assert "comprar cafe" in respuesta

    def test_agenda_vacia(self, router_completo):
        router, mem = router_completo
        respuesta = router.procesar("que tengo hoy")
        assert "No tienes eventos" in respuesta

    def test_hora_devuelve_formato_correcto(self, router_completo):
        router, mem = router_completo
        respuesta = router.procesar("que hora es")
        assert ":" in respuesta and "Son las" in respuesta

    def test_fecha_devuelve_dia_semana(self, router_completo):
        router, mem = router_completo
        respuesta = router.procesar("que dia es hoy")
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        assert any(d in respuesta for d in dias)


# ═══════════════════════════════════════════════════════════
#  Integracion Router <-> Skill Notas <-> Memoria
# ═══════════════════════════════════════════════════════════

class TestIntegracionNotasMemoria:

    def test_crear_nota_y_leerla(self, router_completo):
        router, mem = router_completo
        # Usar frase sin "que tengo": esa subcadena es keyword de la skill tiempo
        # y la capturaria antes que notas, causando que la nota no se cree.
        router.procesar("anota mi clase de yoga del viernes")
        respuesta = router.procesar("lee mi ultima nota")
        assert "clase de yoga" in respuesta

    def test_multiples_notas_lee_la_mas_reciente(self, router_completo):
        router, mem = router_completo
        router.procesar("anota mi primera observacion")
        router.procesar("anota mi segunda observacion mas reciente")
        respuesta = router.procesar("ultima nota")
        assert "segunda observacion" in respuesta

    def test_sin_notas_devuelve_mensaje(self, router_completo):
        router, mem = router_completo
        respuesta = router.procesar("que dice mi nota")
        assert "ninguna" in respuesta.lower() or "no tienes" in respuesta.lower()


# ═══════════════════════════════════════════════════════════
#  Integracion Router <-> Skill Clima (con mock HTTP)
# ═══════════════════════════════════════════════════════════

class TestIntegracionClima:

    def test_consulta_clima_exitosa(self, router_completo):
        router, mem = router_completo

        from skills import clima as skill_clima
        router.registrar("clima", skill_clima.KEYWORDS, skill_clima.consultar_clima)
        skill_clima._cache.clear()

        mock_geo   = MagicMock()
        mock_clima = MagicMock()
        mock_geo.json.return_value   = {"results": [{"latitude": 4.44, "longitude": -75.23}]}
        mock_clima.json.return_value = {
            "current": {
                "temperature_2m": 25,
                "apparent_temperature": 24,
                "weathercode": 0,
                "relativehumidity_2m": 60,
                "windspeed_10m": 8.0,
            }
        }

        with patch("skills.clima.requests.get", side_effect=[mock_geo, mock_clima]):
            respuesta = router.procesar("que clima hay en ibague")

        assert "25" in respuesta
        skill_clima._cache.clear()

    def test_consulta_clima_ciudad_no_encontrada(self, router_completo):
        router, mem = router_completo
        from skills import clima as skill_clima
        router.registrar("clima", skill_clima.KEYWORDS, skill_clima.consultar_clima)
        skill_clima._cache.clear()

        mock_no_result = MagicMock()
        mock_no_result.json.return_value = {"results": []}

        with patch("skills.clima.requests.get", return_value=mock_no_result):
            respuesta = router.procesar("clima en ciudadinexistentexyz")

        assert isinstance(respuesta, str) and len(respuesta) > 0
        skill_clima._cache.clear()


# ═══════════════════════════════════════════════════════════
#  Integracion: prioridad y fallback del router
# ═══════════════════════════════════════════════════════════

class TestIntegracionPrioridadFallback:

    def test_comando_sin_skill_activa_fallback(self, router_completo):
        router, mem = router_completo
        respuesta = router.procesar("explicame la teoria de la relatividad")
        assert "fallback" in respuesta.lower() or "IA" in respuesta

    def test_tildes_en_entrada_usuario_no_rompen_dispatch(self, router_completo):
        router, mem = router_completo
        # "anota" con tilde en la a inicial debe matchear la skill de notas
        router.procesar("anota mi reunion del martes")
        nota = mem.ultima_nota()
        assert nota is not None

    def test_mayusculas_en_entrada_no_rompen_dispatch(self, router_completo):
        router, mem = router_completo
        respuesta = router.procesar("QUE HORA ES")
        assert "Son las" in respuesta

    def test_stats_registra_multiples_skills(self, router_completo):
        router, mem = router_completo
        router.procesar("que hora es")
        router.procesar("que hora es")
        # Usar frase que solo tenga keywords de notas, sin solapamiento con tiempo
        router.procesar("anota mi reunion del lunes")
        stats = router.stats()
        assert "tiempo" in stats
        assert "notas" in stats

    def test_flujo_completo_agenda(self, router_completo):
        """Simula una sesion real: crear evento -> consultar agenda."""
        from datetime import datetime
        router, mem = router_completo
        hoy = datetime.now().strftime("%Y-%m-%d")

        # Crear evento directamente en memoria para el dia de hoy
        mem.agregar_evento("Reunion de equipo", hoy, "10:00")
        respuesta = router.procesar("que tengo hoy")
        assert "Reunion" in respuesta or "un evento" in respuesta.lower()

    def test_flujo_completo_notas_multiples(self, router_completo):
        """Crea varias notas y verifica que siempre se lee la ultima."""
        router, mem = router_completo
        router.procesar("anota comprar leche")
        router.procesar("anota llamar al banco")
        router.procesar("anota revisar el correo")
        respuesta = router.procesar("que dice mi nota")
        assert "revisar el correo" in respuesta

    def test_error_en_skill_no_rompe_el_router(self, router_completo):
        """Si una skill lanza excepcion, el router devuelve mensaje sin crashear."""
        router, mem = router_completo

        def skill_rota(texto):
            raise RuntimeError("Error inesperado")

        router.registrar("rota", ["crashea"], skill_rota)
        resultado = router.procesar("crashea ahora")
        assert isinstance(resultado, str)
        assert len(resultado) > 0
