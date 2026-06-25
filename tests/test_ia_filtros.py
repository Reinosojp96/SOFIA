"""
test_ia_filtros.py
==================
Pruebas unitarias de las funciones puras de core.ia que NO requieren el LLM.

Cubre:
  - _es_incoherente(): clasificador de calidad de respuestas
  - registrar_frase_fallida() y agregar_correccion() (con archivo temporal)
  - obtener_estadisticas() (con archivo temporal)
  - esta_disponible() cuando no hay modelo (debe devolver False sin crashear)

El LLM (llama_cpp) NO se carga en estos tests.
"""

import json
import pytest
import core.ia as ia


# ── Fixture: redirigir _LEARNING_PATH a directorio temporal ──────────────────

@pytest.fixture(autouse=True)
def aprendizaje_tmp(tmp_path, monkeypatch):
    ruta = tmp_path / "aprendizaje.json"
    monkeypatch.setattr(ia, "_LEARNING_PATH", ruta)
    monkeypatch.setattr(ia, "_disponible", False)  # Sin modelo en tests
    monkeypatch.setattr(ia, "_llm", None)
    return ruta


# ═══════════════════════════════════════════════════════════
#  _es_incoherente()
# ═══════════════════════════════════════════════════════════

class TestEsIncoherente:

    # Respuestas que DEBEN ser marcadas como incoherentes

    def test_respuesta_vacia_es_incoherente(self):
        assert ia._es_incoherente("") is True

    def test_respuesta_none_es_incoherente(self):
        assert ia._es_incoherente(None) is True

    def test_respuesta_en_ingles_es_incoherente(self):
        assert ia._es_incoherente(
            "The weather is nice today and the sun is shining."
        ) is True

    def test_razonamiento_visible_okay_the_user(self):
        assert ia._es_incoherente("Okay, the user wants to know the time.") is True

    def test_razonamiento_visible_let_me(self):
        assert ia._es_incoherente("Let me think about this question.") is True

    def test_razonamiento_visible_i_need_to(self):
        assert ia._es_incoherente("I need to analyze this carefully.") is True

    def test_razonamiento_visible_i_should(self):
        assert ia._es_incoherente("I should first consider the context.") is True

    def test_tag_think_es_incoherente(self):
        assert ia._es_incoherente("<think>esto es razonamiento</think>") is True

    def test_cierre_think_es_incoherente(self):
        assert ia._es_incoherente("La respuesta es sí. </think>") is True

    def test_mayoria_palabras_ingles_es_incoherente(self):
        # >40% palabras en inglés
        assert ia._es_incoherente(
            "This is a test and you should know the answer."
        ) is True

    # Respuestas que NO deben ser marcadas como incoherentes

    def test_respuesta_espanol_correcta(self):
        assert ia._es_incoherente("Son las tres de la tarde.") is False

    def test_respuesta_espanol_con_numeros(self):
        assert ia._es_incoherente("En Ibagué hay 24 grados centígrados hoy.") is False

    def test_respuesta_espanol_larga(self):
        assert ia._es_incoherente(
            "La inteligencia artificial es la simulación de procesos de "
            "inteligencia humana mediante sistemas computacionales."
        ) is False

    def test_respuesta_corta_espanol(self):
        assert ia._es_incoherente("No lo sé.") is False

    def test_respuesta_pregunta_retórica_espanol(self):
        assert ia._es_incoherente("¿Te refieres al modelo de lenguaje?") is False

    def test_pocas_palabras_ingles_no_es_incoherente(self):
        # "ok" y "fine" presentes pero < 40% del total
        assert ia._es_incoherente(
            "Está bien, el clima es agradable y la temperatura es normal."
        ) is False

    def test_respuesta_con_nombre_propio_ingles(self):
        # Nombres propios en inglés mezclados no deben disparar el filtro
        assert ia._es_incoherente(
            "El modelo Qwen fue desarrollado por Alibaba en China."
        ) is False


# ═══════════════════════════════════════════════════════════
#  Registro de aprendizaje
# ═══════════════════════════════════════════════════════════

class TestRegistroAprendizaje:

    def test_registrar_frase_fallida_crea_archivo(self, aprendizaje_tmp):
        ia.registrar_frase_fallida("no sé qué decir", razon="sin_modelo")
        assert aprendizaje_tmp.exists()

    def test_registrar_frase_fallida_estructura(self, aprendizaje_tmp):
        ia.registrar_frase_fallida("pregunta sin respuesta", razon="error_llm")
        data = json.loads(aprendizaje_tmp.read_text(encoding="utf-8"))
        assert len(data["frases_fallidas"]) == 1
        assert data["frases_fallidas"][0]["texto"] == "pregunta sin respuesta"
        assert data["frases_fallidas"][0]["razon"] == "error_llm"

    def test_registrar_multiples_frases_fallidas(self, aprendizaje_tmp):
        for i in range(5):
            ia.registrar_frase_fallida(f"pregunta {i}")
        data = json.loads(aprendizaje_tmp.read_text(encoding="utf-8"))
        assert len(data["frases_fallidas"]) == 5

    def test_frases_fallidas_no_supera_500(self, aprendizaje_tmp):
        for i in range(510):
            ia.registrar_frase_fallida(f"frase {i}")
        data = json.loads(aprendizaje_tmp.read_text(encoding="utf-8"))
        assert len(data["frases_fallidas"]) <= 500

    def test_agregar_correccion_estructura(self, aprendizaje_tmp):
        result = ia.agregar_correccion(
            "pregunta mal entendida",
            "esta es la respuesta correcta",
            skill_sugerida="clima"
        )
        assert "Corrección registrada" in result
        data = json.loads(aprendizaje_tmp.read_text(encoding="utf-8"))
        corr = data["correcciones"][0]
        assert corr["frase"] == "pregunta mal entendida"
        assert corr["respuesta_esperada"] == "esta es la respuesta correcta"
        assert corr["skill_sugerida"] == "clima"
        assert corr["aplicada"] is False

    def test_agregar_correccion_sin_skill(self, aprendizaje_tmp):
        ia.agregar_correccion("frase", "respuesta")
        data = json.loads(aprendizaje_tmp.read_text(encoding="utf-8"))
        assert data["correcciones"][0]["skill_sugerida"] == ""


# ═══════════════════════════════════════════════════════════
#  Estadísticas
# ═══════════════════════════════════════════════════════════

class TestEstadisticas:

    def test_estadisticas_inicial(self, aprendizaje_tmp):
        resultado = ia.obtener_estadisticas()
        assert "Consultas totales: 0" in resultado
        assert "Sin respuesta: 0" in resultado

    def test_estadisticas_tras_fallida(self, aprendizaje_tmp):
        ia.registrar_frase_fallida("pregunta")
        resultado = ia.obtener_estadisticas()
        assert "Sin respuesta: 1" in resultado
        assert "Frases fallidas registradas: 1" in resultado

    def test_estadisticas_tras_correccion(self, aprendizaje_tmp):
        ia.agregar_correccion("frase", "respuesta")
        resultado = ia.obtener_estadisticas()
        assert "Correcciones en cola: 1" in resultado


# ═══════════════════════════════════════════════════════════
#  esta_disponible() sin modelo
# ═══════════════════════════════════════════════════════════

class TestDisponibilidad:

    def test_sin_modelo_devuelve_false(self, monkeypatch):
        """Si el archivo .gguf no existe, esta_disponible() debe devolver False."""
        monkeypatch.setattr(ia, "MODEL_PATH", "/ruta/inexistente/modelo.gguf")
        monkeypatch.setattr(ia, "_llm", None)
        monkeypatch.setattr(ia, "_disponible", False)
        assert ia.esta_disponible() is False

    def test_preguntar_sin_modelo_devuelve_mensaje_seguro(self, monkeypatch):
        """preguntar() sin modelo no debe crashear, debe devolver texto."""
        monkeypatch.setattr(ia, "MODEL_PATH", "/ruta/inexistente/modelo.gguf")
        monkeypatch.setattr(ia, "_llm", None)
        monkeypatch.setattr(ia, "_disponible", False)
        resultado = ia.preguntar("¿Qué hora es?")
        assert isinstance(resultado, str)
        assert len(resultado) > 0
