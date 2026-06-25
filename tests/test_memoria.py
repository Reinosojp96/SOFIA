"""
test_memoria.py
===============
Pruebas unitarias del módulo core.memoria (persistencia JSON).

Cubre:
  - CRUD de eventos
  - CRUD de alarmas (activar / desactivar / disparar)
  - CRUD de tareas (agregar / completar / filtrar pendientes)
  - Notas (agregar / leer última)
  - IDs autoincrementales
  - Contadores para la UI
  - Aislamiento: cada test trabaja con archivos temporales (fixture memoria_tmp)
"""

import json
import pytest
from datetime import datetime


# La fixture `memoria_tmp` viene de conftest.py:
# parchea _DB_PATH y _NOTAS_PATH a archivos temporales.


# ═══════════════════════════════════════════════════════════
#  EVENTOS
# ═══════════════════════════════════════════════════════════

class TestEventos:

    def test_agregar_evento_devuelve_dict_con_campos(self, memoria_tmp):
        ev = memoria_tmp.agregar_evento("Reunión", "2026-07-01", "10:00")
        assert ev["titulo"] == "Reunión"
        assert ev["fecha"]  == "2026-07-01"
        assert ev["hora"]   == "10:00"
        assert "id" in ev

    def test_agregar_evento_sin_hora(self, memoria_tmp):
        ev = memoria_tmp.agregar_evento("Cumpleaños", "2026-08-15")
        assert ev["hora"] is None

    def test_listar_eventos_vacio(self, memoria_tmp):
        assert memoria_tmp.listar_eventos() == []

    def test_listar_eventos_despues_de_agregar(self, memoria_tmp):
        memoria_tmp.agregar_evento("A", "2026-07-01")
        memoria_tmp.agregar_evento("B", "2026-07-02")
        eventos = memoria_tmp.listar_eventos()
        assert len(eventos) == 2

    def test_ids_autoincrementales(self, memoria_tmp):
        e1 = memoria_tmp.agregar_evento("Primero", "2026-07-01")
        e2 = memoria_tmp.agregar_evento("Segundo", "2026-07-02")
        assert e2["id"] == e1["id"] + 1

    def test_eliminar_evento_existente(self, memoria_tmp):
        ev = memoria_tmp.agregar_evento("Borrar", "2026-07-01")
        memoria_tmp.eliminar_evento(ev["id"])
        ids = [e["id"] for e in memoria_tmp.listar_eventos()]
        assert ev["id"] not in ids

    def test_eliminar_id_inexistente_no_crashea(self, memoria_tmp):
        memoria_tmp.agregar_evento("Existe", "2026-07-01")
        memoria_tmp.eliminar_evento(9999)          # ID que no existe
        assert len(memoria_tmp.listar_eventos()) == 1

    def test_eliminar_solo_el_correcto(self, memoria_tmp):
        e1 = memoria_tmp.agregar_evento("A", "2026-07-01")
        e2 = memoria_tmp.agregar_evento("B", "2026-07-02")
        memoria_tmp.eliminar_evento(e1["id"])
        restantes = memoria_tmp.listar_eventos()
        assert len(restantes) == 1
        assert restantes[0]["id"] == e2["id"]

    def test_contar_eventos_hoy(self, memoria_tmp, monkeypatch):
        hoy = datetime.now().strftime("%Y-%m-%d")
        memoria_tmp.agregar_evento("Hoy1", hoy)
        memoria_tmp.agregar_evento("Hoy2", hoy)
        memoria_tmp.agregar_evento("Ayer", "2020-01-01")
        assert memoria_tmp.contar_eventos_hoy() == 2


# ═══════════════════════════════════════════════════════════
#  ALARMAS
# ═══════════════════════════════════════════════════════════

class TestAlarmas:

    def test_agregar_alarma_campos_basicos(self, memoria_tmp):
        a = memoria_tmp.agregar_alarma("07:30", "Despertar")
        assert a["hora"]    == "07:30"
        assert a["etiqueta"] == "Despertar"
        assert a["activa"]  is True
        assert "id" in a

    def test_agregar_alarma_sin_etiqueta(self, memoria_tmp):
        a = memoria_tmp.agregar_alarma("08:00")
        assert a["etiqueta"] == ""

    def test_listar_alarmas_solo_activas(self, memoria_tmp):
        a1 = memoria_tmp.agregar_alarma("07:00")
        a2 = memoria_tmp.agregar_alarma("08:00")
        memoria_tmp.desactivar_alarma(a1["id"])
        activas = memoria_tmp.listar_alarmas(solo_activas=True)
        assert len(activas) == 1
        assert activas[0]["id"] == a2["id"]

    def test_listar_todas_las_alarmas(self, memoria_tmp):
        a1 = memoria_tmp.agregar_alarma("07:00")
        memoria_tmp.desactivar_alarma(a1["id"])
        todas = memoria_tmp.listar_alarmas(solo_activas=False)
        assert len(todas) == 1
        assert todas[0]["activa"] is False

    def test_desactivar_alarma_inexistente_no_crashea(self, memoria_tmp):
        memoria_tmp.agregar_alarma("07:00")
        memoria_tmp.desactivar_alarma(9999)
        assert len(memoria_tmp.listar_alarmas()) == 1

    def test_alarmas_para_disparar_coincidencia(self, memoria_tmp):
        memoria_tmp.agregar_alarma("06:00", "Madrugar")
        disparadas = memoria_tmp.alarmas_para_disparar("06:00")
        assert len(disparadas) == 1
        assert disparadas[0]["etiqueta"] == "Madrugar"

    def test_alarmas_para_disparar_se_desactivan(self, memoria_tmp):
        memoria_tmp.agregar_alarma("06:00")
        memoria_tmp.alarmas_para_disparar("06:00")
        # Después de disparar, no debe quedar activa
        activas = memoria_tmp.listar_alarmas(solo_activas=True)
        assert activas == []

    def test_alarmas_para_disparar_sin_coincidencia(self, memoria_tmp):
        memoria_tmp.agregar_alarma("06:00")
        disparadas = memoria_tmp.alarmas_para_disparar("07:00")
        assert disparadas == []

    def test_alarmas_para_disparar_no_activa_alarmas_inactivas(self, memoria_tmp):
        a = memoria_tmp.agregar_alarma("06:00")
        memoria_tmp.desactivar_alarma(a["id"])
        disparadas = memoria_tmp.alarmas_para_disparar("06:00")
        assert disparadas == []

    def test_ids_alarmas_autoincrementales(self, memoria_tmp):
        a1 = memoria_tmp.agregar_alarma("07:00")
        a2 = memoria_tmp.agregar_alarma("08:00")
        assert a2["id"] == a1["id"] + 1


# ═══════════════════════════════════════════════════════════
#  TAREAS
# ═══════════════════════════════════════════════════════════

class TestTareas:

    def test_agregar_tarea_campos(self, memoria_tmp):
        t = memoria_tmp.agregar_tarea("Comprar leche")
        assert t["texto"] == "Comprar leche"
        assert t["hecha"] is False
        assert "id" in t

    def test_listar_tareas_pendientes_inicial_vacio(self, memoria_tmp):
        assert memoria_tmp.listar_tareas() == []

    def test_listar_solo_pendientes(self, memoria_tmp):
        t1 = memoria_tmp.agregar_tarea("Pendiente")
        t2 = memoria_tmp.agregar_tarea("Completar")
        memoria_tmp.completar_tarea(t2["id"])
        pendientes = memoria_tmp.listar_tareas(solo_pendientes=True)
        assert len(pendientes) == 1
        assert pendientes[0]["id"] == t1["id"]

    def test_listar_todas_tareas(self, memoria_tmp):
        t1 = memoria_tmp.agregar_tarea("A")
        memoria_tmp.completar_tarea(t1["id"])
        memoria_tmp.agregar_tarea("B")
        todas = memoria_tmp.listar_tareas(solo_pendientes=False)
        assert len(todas) == 2

    def test_completar_tarea_existente(self, memoria_tmp):
        t = memoria_tmp.agregar_tarea("Hacer ejercicio")
        memoria_tmp.completar_tarea(t["id"])
        todas = memoria_tmp.listar_tareas(solo_pendientes=False)
        hecha = next(x for x in todas if x["id"] == t["id"])
        assert hecha["hecha"] is True

    def test_completar_id_inexistente_no_crashea(self, memoria_tmp):
        memoria_tmp.agregar_tarea("Tarea normal")
        memoria_tmp.completar_tarea(9999)
        assert len(memoria_tmp.listar_tareas()) == 1

    def test_contar_tareas_pendientes(self, memoria_tmp):
        t1 = memoria_tmp.agregar_tarea("A")
        memoria_tmp.agregar_tarea("B")
        memoria_tmp.completar_tarea(t1["id"])
        assert memoria_tmp.contar_tareas_pendientes() == 1

    def test_ids_tareas_autoincrementales(self, memoria_tmp):
        t1 = memoria_tmp.agregar_tarea("Primera")
        t2 = memoria_tmp.agregar_tarea("Segunda")
        assert t2["id"] == t1["id"] + 1


# ═══════════════════════════════════════════════════════════
#  NOTAS (NebulaNotes)
# ═══════════════════════════════════════════════════════════

class TestNotas:

    def test_agregar_nota_campos(self, memoria_tmp):
        n = memoria_tmp.agregar_nota("Contenido de prueba", "Título test")
        assert n["content"] == "Contenido de prueba"
        assert n["title"]   == "Título test"
        assert "id" in n
        assert "created" in n

    def test_agregar_nota_sin_titulo_genera_titulo_automatico(self, memoria_tmp):
        n = memoria_tmp.agregar_nota("Solo contenido")
        assert "Nota de voz" in n["title"]

    def test_listar_notas_vacio(self, memoria_tmp):
        assert memoria_tmp.listar_notas() == []

    def test_listar_notas_orden_mas_reciente_primero(self, memoria_tmp):
        memoria_tmp.agregar_nota("Primera nota", "Primera")
        memoria_tmp.agregar_nota("Segunda nota", "Segunda")
        notas = memoria_tmp.listar_notas()
        # La segunda (más reciente) debe ser la primera
        assert notas[0]["title"] == "Segunda"

    def test_ultima_nota_vacio(self, memoria_tmp):
        assert memoria_tmp.ultima_nota() is None

    def test_ultima_nota_devuelve_mas_reciente(self, memoria_tmp):
        memoria_tmp.agregar_nota("Vieja", "Vieja")
        memoria_tmp.agregar_nota("Reciente", "Reciente")
        ultima = memoria_tmp.ultima_nota()
        assert ultima["title"] == "Reciente"

    def test_notas_persisten_en_archivo(self, memoria_tmp):
        """Verifica que las notas se guardan realmente en el archivo JSON."""
        memoria_tmp.agregar_nota("Test persistencia", "Test")
        # Leer el archivo directamente
        import json
        with open(memoria_tmp._NOTAS_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        assert len(raw["notes"]) == 1
        assert raw["notes"][0]["content"] == "Test persistencia"
