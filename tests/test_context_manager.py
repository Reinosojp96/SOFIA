"""
test_context_manager.py
=======================
Pruebas unitarias de core.context_manager.ContextManager.

No requiere hardware ni archivos externos.
"""

import pytest
from core.context_manager import ContextManager


@pytest.fixture
def ctx():
    return ContextManager()


class TestEstadoInicial:

    def test_sin_contexto_inicialmente(self, ctx):
        assert ctx.tiene_contexto() is False

    def test_app_activa_inicial_es_none(self, ctx):
        assert ctx.app_activa() is None

    def test_titulo_activo_inicial_es_none(self, ctx):
        assert ctx.titulo_activo() is None

    def test_ultima_accion_inicial_es_none(self, ctx):
        assert ctx.ultima_accion() is None

    def test_contenido_resumen_inicial_es_vacio(self, ctx):
        assert ctx.contenido_resumen() == ""


class TestActualizar:

    def test_actualizar_registra_app(self, ctx):
        ctx.actualizar("chrome", "Google - Chrome")
        assert ctx.app_activa() == "chrome"

    def test_actualizar_registra_titulo(self, ctx):
        ctx.actualizar("notepad", "sin título - Notepad")
        assert ctx.titulo_activo() == "sin título - Notepad"

    def test_actualizar_normaliza_app_a_minusculas(self, ctx):
        ctx.actualizar("CHROME", "Título")
        assert ctx.app_activa() == "chrome"

    def test_actualizar_strips_espacios_en_app(self, ctx):
        ctx.actualizar("  chrome  ", "Título")
        assert ctx.app_activa() == "chrome"

    def test_actualizar_con_accion(self, ctx):
        ctx.actualizar("notepad", "doc.txt", accion="minimizar")
        assert ctx.ultima_accion() == "minimizar"

    def test_actualizar_con_contenido(self, ctx):
        ctx.actualizar("notepad", "doc.txt", contenido="Texto del documento")
        assert ctx.contenido_resumen() == "Texto del documento"

    def test_actualizar_sin_accion_queda_none(self, ctx):
        ctx.actualizar("chrome", "Google")
        assert ctx.ultima_accion() is None

    def test_tiene_contexto_true_despues_de_actualizar(self, ctx):
        ctx.actualizar("chrome", "Google")
        assert ctx.tiene_contexto() is True

    def test_app_none_no_tiene_contexto(self, ctx):
        ctx.actualizar(None, "algún título")
        assert ctx.tiene_contexto() is False

    def test_segundo_actualizar_sobreescribe_el_primero(self, ctx):
        ctx.actualizar("chrome", "Google")
        ctx.actualizar("word", "documento.docx")
        assert ctx.app_activa() == "word"
        assert ctx.titulo_activo() == "documento.docx"

    def test_snapshot_devuelve_copia_del_estado(self, ctx):
        ctx.actualizar("vlc", "video.mp4")
        snap = ctx.snapshot()
        # Modificar el snapshot no debe afectar el contexto interno
        snap["app"] = "MODIFICADO"
        assert ctx.app_activa() == "vlc"

    def test_snapshot_contiene_timestamp(self, ctx):
        ctx.actualizar("chrome", "Google")
        snap = ctx.snapshot()
        assert "timestamp" in snap
        assert snap["timestamp"] is not None

    def test_snapshot_inicial_tiene_timestamp_none(self, ctx):
        snap = ctx.snapshot()
        assert snap["timestamp"] is None


class TestCasosEspeciales:

    def test_titulo_con_espacios_se_hace_strip(self, ctx):
        ctx.actualizar("app", "  Título con espacios  ")
        assert ctx.titulo_activo() == "Título con espacios"

    def test_multiples_actualizaciones_acumulan_solo_ultima(self, ctx):
        for i in range(10):
            ctx.actualizar(f"app{i}", f"titulo{i}")
        assert ctx.app_activa() == "app9"

    def test_contenido_vacio_string_vacio(self, ctx):
        ctx.actualizar("app", "titulo", contenido="")
        assert ctx.contenido_resumen() == ""

    def test_contenido_none_devuelve_string_vacio(self, ctx):
        ctx.actualizar("app", "titulo", contenido=None)
        assert ctx.contenido_resumen() == ""
