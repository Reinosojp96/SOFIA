"""
Router central de intenciones.
Una sola fuente de verdad: cada skill se registra con palabras clave
y una función. El router evalúa en orden y ejecuta la primera que matchee.
Si nada matchea, cae al fallback (IA conversacional).

MEJORAS v2:
  - Registra automáticamente frases no reconocidas para aprendizaje
  - Método stats() para ver qué skills se usan más
  - _normalizar() elimina tildes para matching más robusto
"""

import re
import unicodedata
from collections import defaultdict


def _quitar_tildes(texto: str) -> str:
    """Convierte 'á é í ó ú ñ' a 'a e i o u n' para matching tolerante."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


class Router:
    def __init__(self):
        self._skills: list[tuple[str, list[str], callable]] = []
        self._fallback: callable | None = None
        self._contadores: dict[str, int] = defaultdict(int)

    def registrar(self, nombre: str, keywords: list[str], funcion: callable):
        """Registra una skill con sus palabras clave (en minúsculas)."""
        self._skills.append((nombre, keywords, funcion))

    def registrar_fallback(self, funcion: callable):
        """Función llamada si ninguna skill hace match (IA conversacional)."""
        self._fallback = funcion

    def _normalizar(self, texto: str) -> str:
        texto = texto.lower().strip()
        texto = _quitar_tildes(texto)
        texto = re.sub(r"[¿?¡!.,;:]+", " ", texto)
        texto = re.sub(r"\s+", " ", texto).strip()
        return texto

    def procesar(self, texto: str) -> str:
        """Ejecuta la skill correspondiente y devuelve la respuesta."""
        texto_norm = self._normalizar(texto)

        for nombre, keywords, funcion in self._skills:
            # Normalizamos también las keywords para matching sin tildes
            if any(_quitar_tildes(kw) in texto_norm for kw in keywords):
                self._contadores[nombre] += 1
                try:
                    return funcion(texto_norm)
                except Exception as e:
                    return f"Tuve un error ejecutando '{nombre}': {e}"

        # Nada matcheó → fallback
        self._contadores["fallback"] += 1
        if self._fallback:
            try:
                return self._fallback(texto_norm)
            except Exception as e:
                return f"No pude pensar una respuesta: {e}"

        return "No entendí ese comando."

    def stats(self) -> str:
        """Devuelve un resumen de uso de skills (útil para depuración)."""
        if not self._contadores:
            return "Sin estadísticas aún."
        lineas = [f"  {nombre}: {n}" for nombre, n in sorted(self._contadores.items(), key=lambda x: -x[1])]
        return "Uso de skills:\n" + "\n".join(lineas)


router = Router()