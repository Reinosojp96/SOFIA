"""
test_skill_notas.py
===================
Pruebas unitarias de skills/notas.py.

Cubre:
  - _crear_nota(): extracción del contenido tras el prefijo de comando
  - _leer_ultima_nota(): casos con y sin notas
  - manejar(): dispatcher por keywords
"""

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_memoria_notas(memoria_tmp):
    import skills.notas as notas_mod
    with patch.object(notas_mod, "memoria", memoria_tmp):
        yield memoria_tmp


import skills.notas as notas


# ═══════════════════════════════════════════════════════════
#  _crear_nota()
# ═══════════════════════════════════════════════════════════

class TestCrearNota:

    def test_anota_que_extrae_contenido(self, memoria_tmp):
        notas._crear_nota("anota que la reunión es el viernes")
        nota = memoria_tmp.ultima_nota()
        assert nota is not None
        assert "la reunión es el viernes" in nota["content"]

    def test_anota_sin_que(self, memoria_tmp):
        notas._crear_nota("anota comprar pan")
        nota = memoria_tmp.ultima_nota()
        assert "comprar pan" in nota["content"]

    def test_crea_una_nota(self, memoria_tmp):
        notas._crear_nota("crea una nota mi contraseña es 1234")
        nota = memoria_tmp.ultima_nota()
        assert "mi contraseña es 1234" in nota["content"]

    def test_nueva_nota(self, memoria_tmp):
        notas._crear_nota("nueva nota recordar llamar al banco")
        nota = memoria_tmp.ultima_nota()
        assert "recordar llamar al banco" in nota["content"]

    def test_apunta_que(self, memoria_tmp):
        notas._crear_nota("apunta que debo entregar el lunes")
        nota = memoria_tmp.ultima_nota()
        assert "debo entregar el lunes" in nota["content"]

    def test_contenido_vacio_pide_que_anotar(self):
        resultado = notas._crear_nota("anota")
        assert "¿Qué" in resultado or "anotar" in resultado.lower()

    def test_respuesta_confirma_contenido(self, memoria_tmp):
        resultado = notas._crear_nota("anota que llueve hoy")
        assert "llueve hoy" in resultado
        assert "Anotado" in resultado


# ═══════════════════════════════════════════════════════════
#  _leer_ultima_nota()
# ═══════════════════════════════════════════════════════════

class TestLeerUltimaNota:

    def test_sin_notas_devuelve_mensaje(self):
        resultado = notas._leer_ultima_nota()
        assert "ninguna nota" in resultado.lower() or "no tienes" in resultado.lower()

    def test_con_nota_devuelve_contenido(self, memoria_tmp):
        memoria_tmp.agregar_nota("Contenido de prueba", "Título")
        resultado = notas._leer_ultima_nota()
        assert "Contenido de prueba" in resultado

    def test_devuelve_la_mas_reciente(self, memoria_tmp):
        memoria_tmp.agregar_nota("Primera nota", "Primera")
        memoria_tmp.agregar_nota("Segunda nota", "Segunda")
        resultado = notas._leer_ultima_nota()
        assert "Segunda nota" in resultado

    def test_nota_sin_contenido_avisa(self, memoria_tmp):
        memoria_tmp.agregar_nota("", "Solo título")
        resultado = notas._leer_ultima_nota()
        assert "vacía" in resultado or "título" in resultado.lower()


# ═══════════════════════════════════════════════════════════
#  manejar() — dispatcher
# ═══════════════════════════════════════════════════════════

class TestManejar:

    def test_manejar_crear_nota_con_anota(self, memoria_tmp):
        resultado = notas.manejar("anota que tengo que llamar a mamá")
        assert "Anotado" in resultado
        assert memoria_tmp.ultima_nota() is not None

    def test_manejar_leer_nota(self, memoria_tmp):
        memoria_tmp.agregar_nota("Nota de prueba", "Test")
        resultado = notas.manejar("lee mi ultima nota")
        assert "Nota de prueba" in resultado

    def test_manejar_ultima_nota(self, memoria_tmp):
        memoria_tmp.agregar_nota("Última nota importante", "Título")
        resultado = notas.manejar("ultima nota")
        assert "Última nota importante" in resultado

    def test_manejar_que_dice_mi_nota(self, memoria_tmp):
        memoria_tmp.agregar_nota("El contenido es este", "Mi nota")
        resultado = notas.manejar("que dice mi nota")
        assert "El contenido es este" in resultado

    def test_manejar_texto_no_reconocido(self):
        resultado = notas.manejar("algo completamente diferente")
        assert isinstance(resultado, str)
        assert len(resultado) > 0
