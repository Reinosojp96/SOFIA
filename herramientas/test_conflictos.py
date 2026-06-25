"""
Detecta solapamientos de keywords entre skills registradas.
Salida 0 = sin conflictos. Salida 1 = hay conflictos (útil para CI/pre-commit).

Uso:
    python herramientas/test_conflictos.py
"""

import sys
import os
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.router import Router
from skills import rutina, clima, tiempo, sistema, web, notas, aprendizaje, control_escritorio

r = Router()
r.registrar("rutina",      rutina.KEYWORDS,                  rutina.manejar)
r.registrar("clima",       clima.KEYWORDS,                   clima.consultar_clima)
r.registrar("tiempo",      tiempo.KEYWORDS,                  tiempo.manejar)
r.registrar("sistema",     sistema.KEYWORDS,                 sistema.manejar)
r.registrar("web",         web.KEYWORDS,                     web.manejar)
r.registrar("notas",       notas.KEYWORDS,                   notas.manejar)
r.registrar("aprendizaje", aprendizaje.KEYWORDS,             aprendizaje.manejar)
r.registrar("escritorio",  control_escritorio.KEYWORDS,      control_escritorio.manejar)

with warnings.catch_warnings(record=True):
    warnings.simplefilter("always")
    conflictos = r.detectar_conflictos()

if not conflictos:
    print("Sin conflictos de keywords detectados.")
    sys.exit(0)

print(f"{len(conflictos)} conflicto(s) encontrado(s):\n")
for c in conflictos:
    print(" ", c)
sys.exit(1)
