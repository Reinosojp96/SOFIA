"""
test_skill_tiempo.py
====================
Pruebas unitarias de skills/tiempo.py.

Cubre:
  - _decir_hora() y _decir_fecha()
  - _crear_alarma() con y sin hora reconocible
  - _crear_evento() con y sin hora, hoy y mañana
  - _listar_agenda() con y sin eventos
  - _listar_tareas() y _crear_tarea()
  - manejar() como dispatcher principal
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


# ── Fixture: aislar memoria ──────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_memoria(memoria_tmp):
    """
    Redirige todas las llamadas de skills.tiempo a la memoria temporal.
    """
    import skills.tiempo as tiempo_mod
    with patch.object(tiempo_mod, "memoria", memoria_tmp):
        yield memoria_tmp


# ── Importar después del patch ───────────────────────────────────────────────

import skills.tiempo as tiempo


# ═══════════════════════════════════════════════════════════
#  Hora y fecha
# ═══════════════════════════════════════════════════════════

class TestHoraFecha:

    def test_decir_hora_contiene_dos_puntos(self):
        resultado = tiempo._decir_hora()
        assert ":" in resultado
        assert "Son las" in resultado

    def test_decir_fecha_contiene_dia_semana(self):
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        resultado = tiempo._decir_fecha()
        assert any(d in resultado for d in dias)

    def test_decir_fecha_contiene_año(self):
        año_actual = str(datetime.now().year)
        assert año_actual in tiempo._decir_fecha()

    def test_manejar_hora(self):
        resultado = tiempo.manejar("que hora es")
        assert "Son las" in resultado

    def test_manejar_fecha(self):
        resultado = tiempo.manejar("que dia es hoy")
        assert "Hoy es" in resultado


# ═══════════════════════════════════════════════════════════
#  Alarmas
# ═══════════════════════════════════════════════════════════

class TestCrearAlarma:

    def test_alarma_formato_hhmm_con_dos_puntos(self, memoria_tmp):
        resultado = tiempo._crear_alarma("alarma a las 07:30")
        assert "07:30" in resultado
        alarmas = memoria_tmp.listar_alarmas()
        assert len(alarmas) == 1
        assert alarmas[0]["hora"] == "07:30"

    def test_alarma_formato_con_h(self, memoria_tmp):
        resultado = tiempo._crear_alarma("despiertame a las 6h30")
        assert "06:30" in resultado

    def test_alarma_formato_solo_hora(self, memoria_tmp):
        resultado = tiempo._crear_alarma("pon alarma a las 8")
        assert "08:00" in resultado

    def test_alarma_sin_hora_reconocible_devuelve_error(self):
        resultado = tiempo._crear_alarma("pon una alarma pronto")
        assert "No entendí" in resultado

    def test_manejar_alarma(self, memoria_tmp):
        resultado = tiempo.manejar("alarma a las 07:00")
        assert "07:00" in resultado
        assert len(memoria_tmp.listar_alarmas()) == 1


# ═══════════════════════════════════════════════════════════
#  Eventos
# ═══════════════════════════════════════════════════════════

class TestCrearEvento:

    def test_crear_evento_hoy(self, memoria_tmp):
        hoy = datetime.now().strftime("%Y-%m-%d")
        tiempo._crear_evento("reunion de equipo")
        eventos = memoria_tmp.listar_eventos()
        assert len(eventos) == 1
        assert eventos[0]["fecha"] == hoy

    def test_crear_evento_manana(self, memoria_tmp):
        manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        tiempo._crear_evento("junta manana a las 10:00")
        eventos = memoria_tmp.listar_eventos()
        assert eventos[0]["fecha"] == manana

    def test_crear_evento_con_hora(self, memoria_tmp):
        tiempo._crear_evento("reunion a las 14:30")
        eventos = memoria_tmp.listar_eventos()
        assert eventos[0]["hora"] == "14:30"

    def test_crear_evento_sin_hora(self, memoria_tmp):
        tiempo._crear_evento("fiesta de cumpleaños")
        eventos = memoria_tmp.listar_eventos()
        assert eventos[0]["hora"] is None


# ═══════════════════════════════════════════════════════════
#  Agenda (listar)
# ═══════════════════════════════════════════════════════════

class TestListarAgenda:

    def test_sin_eventos_hoy(self):
        resultado = tiempo._listar_agenda("que tengo hoy")
        assert "No tienes eventos" in resultado

    def test_con_un_evento_hoy(self, memoria_tmp):
        hoy = datetime.now().strftime("%Y-%m-%d")
        memoria_tmp.agregar_evento("Reunión", hoy, "10:00")
        resultado = tiempo._listar_agenda("que tengo hoy")
        assert "un evento" in resultado or "Reunión" in resultado

    def test_con_multiples_eventos_hoy(self, memoria_tmp):
        hoy = datetime.now().strftime("%Y-%m-%d")
        memoria_tmp.agregar_evento("A", hoy)
        memoria_tmp.agregar_evento("B", hoy)
        resultado = tiempo._listar_agenda("mis eventos hoy")
        assert "2" in resultado

    def test_filtro_manana(self, memoria_tmp):
        manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        memoria_tmp.agregar_evento("Junta mañana", manana)
        resultado = tiempo._listar_agenda("que tengo manana")
        assert "mañana" in resultado or "Junta" in resultado

    def test_eventos_manana_no_aparecen_hoy(self, memoria_tmp):
        manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        memoria_tmp.agregar_evento("Solo mañana", manana)
        resultado = tiempo._listar_agenda("que tengo hoy")
        assert "No tienes eventos" in resultado


# ═══════════════════════════════════════════════════════════
#  Tareas
# ═══════════════════════════════════════════════════════════

class TestTareas:

    def test_listar_sin_tareas(self):
        resultado = tiempo._listar_tareas()
        assert "No tienes tareas" in resultado

    def test_listar_con_una_tarea(self, memoria_tmp):
        memoria_tmp.agregar_tarea("Lavar la ropa")
        resultado = tiempo._listar_tareas()
        assert "Lavar la ropa" in resultado

    def test_listar_con_multiples_tareas(self, memoria_tmp):
        memoria_tmp.agregar_tarea("A")
        memoria_tmp.agregar_tarea("B")
        memoria_tmp.agregar_tarea("C")
        resultado = tiempo._listar_tareas()
        assert "3" in resultado

    def test_crear_tarea_extrae_contenido(self, memoria_tmp):
        tiempo._crear_tarea("agrega la tarea llamar al médico")
        tareas = memoria_tmp.listar_tareas()
        assert len(tareas) == 1
        assert "llamar al médico" in tareas[0]["texto"]

    def test_crear_tarea_vacia_pide_contenido(self):
        resultado = tiempo._crear_tarea("nueva tarea")
        assert "¿Cuál" in resultado or "tarea" in resultado.lower()


# ═══════════════════════════════════════════════════════════
#  manejar() — dispatcher
# ═══════════════════════════════════════════════════════════

class TestManejar:

    def test_manejar_tarea_pendiente(self, memoria_tmp):
        memoria_tmp.agregar_tarea("Hacer informe")
        resultado = tiempo.manejar("mis tareas pendientes")
        assert "Hacer informe" in resultado

    def test_manejar_crear_tarea(self, memoria_tmp):
        tiempo.manejar("agrega la tarea revisar correo")
        tareas = memoria_tmp.listar_tareas()
        assert any("revisar correo" in t["texto"] for t in tareas)

    def test_manejar_agendar_evento(self, memoria_tmp):
        tiempo.manejar("agendame una junta a las 15:00")
        assert len(memoria_tmp.listar_eventos()) == 1

    def test_manejar_texto_no_reconocido(self):
        resultado = tiempo.manejar("esto no tiene sentido para tiempo")
        assert isinstance(resultado, str)
        assert len(resultado) > 0
