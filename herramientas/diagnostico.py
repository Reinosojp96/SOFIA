"""
Registro de estados del pipeline para diagnóstico de recursos.

Si la variable de entorno SOFIA_DIAGNOSTICO=1 está activa, cada llamada a
registrar_estado(nombre) toma una muestra de CPU/RAM (y VRAM si hay GPU)
del proceso actual y la agrega como una línea JSON a
data/logs/diagnostico_estados.jsonl. Si la variable no está activa, la
función no hace nada — overhead cero en uso normal.

Pensado para ser llamado desde main.py en las transiciones de estado que
ya existen (widget.set_estado), de forma que herramientas/medir_recursos.py
pueda cruzar estas marcas de tiempo con muestras de CPU/RAM/VRAM del
sistema y reportar promedio/pico por etapa (reposo, escuchando, procesando,
hablando).
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

_RAIZ = Path(__file__).parent.parent
_LOG_DIR = _RAIZ / "data" / "logs"
_LOG_PATH = _LOG_DIR / "diagnostico_estados.jsonl"

_ACTIVO = os.environ.get("SOFIA_DIAGNOSTICO", "0").strip() == "1"

_psutil_proc = None
if _ACTIVO:
    try:
        import psutil
        _psutil_proc = psutil.Process(os.getpid())
        _psutil_proc.cpu_percent()  # primera llamada "calienta" la medición
    except Exception:
        _psutil_proc = None


def _vram_mb() -> float | None:
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / (1024 ** 2)
    except Exception:
        pass
    return None


def registrar_estado(nombre_estado: str):
    """Registra una muestra de recursos asociada a 'nombre_estado'.

    No hace nada si SOFIA_DIAGNOSTICO no está activo (costo cero en
    producción normal).
    """
    if not _ACTIVO:
        return
    try:
        cpu_pct = _psutil_proc.cpu_percent() if _psutil_proc else None
        ram_mb = _psutil_proc.memory_info().rss / (1024 ** 2) if _psutil_proc else None
        muestra = {
            "ts": datetime.now().isoformat(),
            "estado": nombre_estado,
            "cpu_pct": cpu_pct,
            "ram_mb": round(ram_mb, 1) if ram_mb is not None else None,
            "vram_mb": (lambda v: round(v, 1) if v is not None else None)(_vram_mb()),
        }
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(muestra, ensure_ascii=False) + "\n")
    except Exception:
        pass


def medir_tiempo(nombre_evento: str, segundos: float, extra: dict | None = None):
    """Registra un evento de duración (ej. tiempos de arranque) en
    data/logs/diagnostico_arranque.jsonl. Independiente de SOFIA_DIAGNOSTICO,
    porque es información liviana de instalación/arranque, no muestreo
    continuo de recursos."""
    try:
        evento = {"ts": datetime.now().isoformat(), "evento": nombre_evento, "segundos": round(segundos, 2)}
        if extra:
            evento.update(extra)
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_LOG_DIR / "diagnostico_arranque.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False) + "\n")
    except Exception:
        pass
