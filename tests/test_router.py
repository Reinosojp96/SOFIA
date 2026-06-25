"""
test_router.py
==============
Pruebas unitarias del Router central de SOFÍA.

Cubre:
  - Dispatch correcto a la skill que tiene el keyword
  - Normalización de tildes y puntuación
  - Prioridad (primer match registrado gana)
  - Fallback cuando ninguna skill hace match
  - Manejo de errores dentro de una skill (no crashea)
  - Detección de conflictos entre keywords
  - Contadores de estadísticas
"""

import pytest
from core.router import Router


# ── Helpers ──────────────────────────────────────────────────────────────────

def skill_a(texto): return "respuesta_A"
def skill_b(texto): return "respuesta_B"
def skill_error(texto): raise RuntimeError("fallo intencional")
def fallback(texto): return f"fallback:{texto}"


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def router():
    """Router limpio para cada test."""
    return Router()


# ── Tests: dispatch básico ────────────────────────────────────────────────────

class TestDispatchBasico:

    def test_keyword_exacto_activa_skill(self, router):
        router.registrar("a", ["clima"], skill_a)
        assert router.procesar("clima hoy") == "respuesta_A"

    def test_keyword_en_medio_del_texto(self, router):
        router.registrar("a", ["clima"], skill_a)
        assert router.procesar("dime el clima de bogota") == "respuesta_A"

    def test_keyword_al_final_del_texto(self, router):
        router.registrar("a", ["hora"], skill_a)
        assert router.procesar("que hora es") == "respuesta_A"

    def test_texto_sin_match_devuelve_no_entendi(self, router):
        router.registrar("a", ["clima"], skill_a)
        resultado = router.procesar("esto no tiene ninguna keyword conocida")
        assert "No entendí" in resultado

    def test_sin_skills_registradas_devuelve_no_entendi(self, router):
        assert "No entendí" in router.procesar("cualquier cosa")


# ── Tests: normalización ──────────────────────────────────────────────────────

class TestNormalizacion:

    def test_tildes_en_texto_usuario(self, router):
        """'clima' en keywords matchea 'clíma' o texto con tilde."""
        router.registrar("a", ["clima"], skill_a)
        # El router normaliza el texto de entrada quitando tildes
        assert router.procesar("¿Qué clíma hace hoy?") == "respuesta_A"

    def test_tildes_en_keywords(self, router):
        """Keyword con tilde ('día') matchea texto sin tilde ('dia')."""
        router.registrar("a", ["día"], skill_a)
        assert router.procesar("que dia es hoy") == "respuesta_A"

    def test_mayusculas_no_importan(self, router):
        router.registrar("a", ["clima"], skill_a)
        assert router.procesar("CLIMA EN BOGOTA") == "respuesta_A"

    def test_signos_de_puntuacion_ignorados(self, router):
        router.registrar("a", ["hora"], skill_a)
        assert router.procesar("¿Qué hora es?") == "respuesta_A"

    def test_texto_vacio_no_crashea(self, router):
        router.registrar("a", ["hora"], skill_a)
        resultado = router.procesar("")
        assert isinstance(resultado, str)

    def test_solo_puntuacion_no_crashea(self, router):
        router.registrar("a", ["hora"], skill_a)
        resultado = router.procesar("¿¡!?,;:")
        assert isinstance(resultado, str)


# ── Tests: prioridad de registro ──────────────────────────────────────────────

class TestPrioridad:

    def test_primer_skill_registrada_gana_en_solapamiento(self, router):
        """Cuando dos skills tienen el mismo keyword, la primera gana."""
        router.registrar("a", ["tiempo"], skill_a)
        router.registrar("b", ["tiempo"], skill_b)
        assert router.procesar("el tiempo hoy") == "respuesta_A"

    def test_segunda_skill_no_se_ignora_si_tiene_keyword_unico(self, router):
        router.registrar("a", ["clima"], skill_a)
        router.registrar("b", ["nota"], skill_b)
        assert router.procesar("anota esto") == "respuesta_B"

    def test_multiples_skills_el_orden_correcto_gana(self, router):
        router.registrar("a", ["alpha"], skill_a)
        router.registrar("b", ["beta"], skill_b)
        assert router.procesar("busca alpha") == "respuesta_A"
        assert router.procesar("revisa beta") == "respuesta_B"


# ── Tests: fallback ───────────────────────────────────────────────────────────

class TestFallback:

    def test_fallback_se_llama_cuando_no_hay_match(self, router):
        router.registrar_fallback(fallback)
        resultado = router.procesar("pregunta libre sin keywords")
        assert resultado.startswith("fallback:")

    def test_fallback_recibe_texto_normalizado(self, router):
        router.registrar_fallback(fallback)
        resultado = router.procesar("¿Qué ES Esto?")
        # El texto llega normalizado (sin tildes, sin puntuación, en minúsculas)
        assert "fallback:" in resultado
        assert "¿" not in resultado

    def test_sin_fallback_registrado_devuelve_mensaje_estandar(self, router):
        resultado = router.procesar("algo sin match y sin fallback")
        assert "No entendí" in resultado

    def test_fallback_con_excepcion_devuelve_mensaje_seguro(self, router):
        def fallback_roto(texto): raise ValueError("error en fallback")
        router.registrar_fallback(fallback_roto)
        resultado = router.procesar("texto libre")
        # No debe propagar la excepción
        assert isinstance(resultado, str)
        assert len(resultado) > 0


# ── Tests: manejo de errores en skills ───────────────────────────────────────

class TestManejoErrores:

    def test_skill_que_lanza_excepcion_devuelve_mensaje_de_error(self, router):
        router.registrar("error_skill", ["crashea"], skill_error)
        resultado = router.procesar("crashea aqui")
        assert "error" in resultado.lower() or "Tuve" in resultado

    def test_skill_con_error_no_propaga_excepcion(self, router):
        router.registrar("error_skill", ["crashea"], skill_error)
        # No debe lanzar excepción
        resultado = router.procesar("crashea aqui")
        assert isinstance(resultado, str)

    def test_skills_posteriores_no_se_llaman_tras_error_en_primera(self, router):
        """Si la primera skill matchea pero falla, la segunda NO se llama."""
        llamadas = []
        def skill_segunda(texto):
            llamadas.append(texto)
            return "segunda"

        router.registrar("primera", ["keyword"], skill_error)
        router.registrar("segunda", ["keyword"], skill_segunda)
        router.procesar("keyword aqui")
        assert llamadas == []  # La segunda nunca se llamó


# ── Tests: detección de conflictos ───────────────────────────────────────────

class TestConflictos:

    def test_detectar_keywords_exactas_duplicadas(self, router):
        router.registrar("a", ["clima"], skill_a)
        router.registrar("b", ["clima"], skill_b)
        alertas = router.detectar_conflictos()
        assert len(alertas) >= 1
        assert any("clima" in a for a in alertas)

    def test_detectar_subcadena_conflictiva(self, router):
        """'dia' es subcadena de 'que dia es': debe reportarse."""
        router.registrar("a", ["dia"], skill_a)
        router.registrar("b", ["que dia es"], skill_b)
        alertas = router.detectar_conflictos()
        assert len(alertas) >= 1

    def test_skills_sin_solapamiento_no_generan_alertas(self, router):
        router.registrar("a", ["clima"], skill_a)
        router.registrar("b", ["nota"], skill_b)
        alertas = router.detectar_conflictos()
        assert alertas == []

    def test_sin_skills_no_genera_alertas(self, router):
        assert router.detectar_conflictos() == []


# ── Tests: estadísticas ───────────────────────────────────────────────────────

class TestEstadisticas:

    def test_stats_inicial_sin_datos(self, router):
        assert "Sin estadísticas" in router.stats()

    def test_stats_incrementa_contador_por_skill(self, router):
        router.registrar("clima_skill", ["clima"], skill_a)
        router.procesar("que clima hay")
        router.procesar("clima en bogota")
        stats = router.stats()
        assert "clima_skill" in stats
        assert "2" in stats

    def test_stats_cuenta_fallbacks(self, router):
        router.registrar_fallback(fallback)
        router.procesar("texto sin keywords")
        stats = router.stats()
        assert "fallback" in stats
