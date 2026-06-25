"""
Fixtures compartidas para toda la suite de tests de SOFÍA.

Estrategia de aislamiento:
  - memoria.py  → se parchea _DB_PATH y _NOTAS_PATH a archivos temporales
  - ia.py       → el LLM no se carga (no hay .gguf en CI); se testea la lógica pura
  - clima.py    → requests.get se mockea para no hacer llamadas reales
  - PyQt6, sounddevice, llama_cpp → NO se importan aquí (hardware no disponible)
"""

import json
import sys
import types
import pytest


# ---------------------------------------------------------------------------
# Bloquear módulos pesados / de hardware antes de que algo los importe
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """
    Registra stubs vacíos para módulos que requieren hardware o GPU,
    evitando ImportError en el entorno de pruebas.
    """
    _stub_modules = [
        "PyQt6", "PyQt6.QtWidgets", "PyQt6.QtCore", "PyQt6.QtGui",
        "sounddevice",
        "faster_whisper",
        "torch", "torchaudio",
        "llama_cpp",
        "pyttsx3",
        "pywinauto", "pywinauto.application",
        "psutil",
        "win32gui", "win32con", "win32api",
        "qwen_tts",
    ]
    for mod in _stub_modules:
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)


# ---------------------------------------------------------------------------
# Fixture: base de datos de memoria aislada en directorio temporal
# ---------------------------------------------------------------------------

@pytest.fixture
def memoria_tmp(tmp_path, monkeypatch):
    """
    Redirige memoria.py a usar archivos JSON temporales.
    Devuelve el módulo ya parcheado.
    """
    import core.memoria as mem

    db_path   = str(tmp_path / "memoria.json")
    notas_path = tmp_path / "nebula_notes.json"

    monkeypatch.setattr(mem, "_DB_PATH",    db_path)
    monkeypatch.setattr(mem, "_DATA_DIR",   str(tmp_path))
    monkeypatch.setattr(mem, "_NOTAS_PATH", notas_path)

    # Inicializar con estructura limpia
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump({"eventos": [], "alarmas": [], "tareas": []}, f)

    return mem
