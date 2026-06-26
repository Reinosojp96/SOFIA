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
import warnings
from collections import defaultdict


def _quitar_tildes(texto: str) -> str:
    """Convierte 'á é í ó ú ñ' a 'a e i o u n' para matching tolerante."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


# Correcciones de errores frecuentes del STT (Whisper), token a token.
# El audio corto + palabras en inglés ("Word", "Excel") hace que Whisper
# devuelva variantes fonéticas. Como _normalizar() corrige el texto ANTES
# de rutearlo Y ese mismo texto corregido se pasa a la skill, esto arregla
# de una sola vez el ruteo y el parseo interno de cada skill.
# Solo se corrigen tokens COMPLETOS (no subcadenas), para no romper otras palabras.
_CORRECCIONES_STT = {
    # "word" mal transcrito (visto en logs: ward, warp, wolf, worth, words...)
    "ward": "word", "warp": "word", "wolf": "word", "worth": "word",
    "words": "word", "wort": "word", "wordt": "word", "worl": "word",
    "warth": "word", "guord": "word", "wored": "word",
    # "excel"
    "exel": "excel", "excell": "excel", "exell": "excel",
    # "chrome"
    "crome": "chrome", "croom": "chrome", "crom": "chrome",
    # verbos de ventana mal oídos
    "minimisa": "minimiza", "minimís": "minimiza",
    "maximisa": "maximiza",
    # "cierra" / "tierra"/"sierra" cuando va seguido de app
    # (se corrigen solo si la siguiente palabra es una app; ver _corregir_secuencia)
}

# Correcciones que dependen del contexto (palabra + siguiente).
# Ej.: "tierra word" / "sierra word" -> "cierra word" (no tocar "tierra" sola).
_APPS = {"word", "excel", "chrome", "powerpoint", "ventana", "pestana", "navegador"}
_VERBOS_CERRAR_MAL = {"tierra", "sierra", "yerra", "fierra"}


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

    def detectar_conflictos(self) -> list[str]:
        """Detecta keywords duplicadas o en relación de subcadena entre skills.
        Emite warnings.warn por cada conflicto y devuelve la lista de mensajes.
        """
        alertas = []
        for i, (nombre_a, kws_a, _) in enumerate(self._skills):
            kws_a_norm = [_quitar_tildes(k) for k in kws_a]
            for j, (nombre_b, kws_b, _) in enumerate(self._skills):
                if i >= j:
                    continue
                kws_b_norm = [_quitar_tildes(k) for k in kws_b]
                for ka in kws_a_norm:
                    for kb in kws_b_norm:
                        if ka == kb:
                            msg = (f"[ROUTER] Conflicto exacto: \"{ka}\" -- "
                                   f"'{nombre_a}' registrada antes que '{nombre_b}'")
                            alertas.append(msg)
                            warnings.warn(msg)
                        elif ka in kb:
                            msg = (f"[ROUTER] Subcadena: \"{ka}\" ({nombre_a}) es subcadena "
                                   f"de \"{kb}\" ({nombre_b}) -- '{nombre_a}' ganará siempre")
                            alertas.append(msg)
                            warnings.warn(msg)
                        elif kb in ka:
                            msg = (f"[ROUTER] Subcadena: \"{kb}\" ({nombre_b}) es subcadena "
                                   f"de \"{ka}\" ({nombre_a}) -- '{nombre_b}' ganará siempre")
                            alertas.append(msg)
                            warnings.warn(msg)
        return alertas

    def _normalizar(self, texto: str) -> str:
        texto = texto.lower().strip()
        texto = _quitar_tildes(texto)
        texto = re.sub(r"[¿?¡!.,;:]+", " ", texto)
        texto = re.sub(r"\s+", " ", texto).strip()
        texto = self._corregir_stt(texto)
        return texto

    def _corregir_stt(self, texto: str) -> str:
        """Corrige errores frecuentes del STT token a token (ver _CORRECCIONES_STT)."""
        tokens = texto.split()
        # 1) correcciones simples token a token
        tokens = [_CORRECCIONES_STT.get(t, t) for t in tokens]
        # 2) correcciones por contexto: "tierra/sierra word" -> "cierra word"
        for i in range(len(tokens) - 1):
            if tokens[i] in _VERBOS_CERRAR_MAL and tokens[i + 1] in _APPS:
                tokens[i] = "cierra"
        return " ".join(tokens)

    def procesar(self, texto: str) -> str:
        """Ejecuta la skill correspondiente y devuelve la respuesta."""
        texto_norm = self._normalizar(texto)

        for nombre, keywords, funcion in self._skills:
            # Normalizamos también las keywords para matching sin tildes
            if any(_quitar_tildes(kw) in texto_norm for kw in keywords):
                self._contadores[nombre] += 1
                print(f"[ROUTER] texto={texto_norm!r} → skill={nombre!r}")  # DEBUG
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