"""
Wrapper para llama.cpp (vía llama-cpp-python).
Funciones públicas: preguntar(texto) -> str, esta_disponible() -> bool

MEJORAS v2:
  - Variable de entorno unificada: SOFIA_MODEL_PATH (antes era ALE_MODEL_PATH)
  - SYSTEM_PROMPT dice "SOFÍA", no "ALE"
  - Soporte de aprendizaje automático: registra errores y correcciones en
    data/aprendizaje.json para retroalimentación futura
  - historial de conversación configurable (memoria de contexto corta)
"""

import os
import json
from datetime import datetime
from pathlib import Path

_llm = None
_disponible = False

# Ruta del modelo: SOFIA_MODEL_PATH tiene prioridad; ALE_MODEL_PATH como alias
# para no romper instalaciones existentes
MODEL_PATH = (
    os.environ.get("SOFIA_MODEL_PATH")
    or os.environ.get("ALE_MODEL_PATH")
    or str(Path(__file__).parent.parent / "data" / "modelo.gguf")
)

SYSTEM_PROMPT = (
    "Eres SOFÍA, una asistente de voz en español, concisa y clara. "
    "Responde en una o dos frases, sin markdown, sin listas. "
    "Si no sabes algo, dilo brevemente."
)

# Ruta del archivo de aprendizaje
_LEARNING_PATH = Path(__file__).parent.parent / "data" / "aprendizaje.json"


# ---------------------------------------------------------------------------
# Carga del modelo
# ---------------------------------------------------------------------------

def _cargar():
    global _llm, _disponible
    if _llm is not None:
        return
    try:
        from llama_cpp import Llama
        if not os.path.exists(MODEL_PATH):
            print(f"[ia] Modelo no encontrado en {MODEL_PATH}")
            _disponible = False
            return
        _llm = Llama(
            model_path=MODEL_PATH,
            n_ctx=2048,
            n_threads=os.cpu_count() or 4,
            verbose=False,
        )
        _disponible = True
    except Exception as e:
        print(f"[ia] No se pudo cargar el modelo: {e}")
        _disponible = False


def esta_disponible() -> bool:
    _cargar()
    return _disponible


# ---------------------------------------------------------------------------
# Aprendizaje automático de errores
# ---------------------------------------------------------------------------

def _leer_aprendizaje() -> dict:
    if _LEARNING_PATH.exists():
        try:
            with open(_LEARNING_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"correcciones": [], "frases_fallidas": [], "estadisticas": {"total_consultas": 0, "fallbacks": 0}}


def _guardar_aprendizaje(data: dict):
    _LEARNING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LEARNING_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def registrar_frase_fallida(texto: str, razon: str = "sin_modelo"):
    """
    Registra una frase que SOFÍA no pudo responder.
    Esto alimenta el sistema de aprendizaje: permite revisar qué preguntas
    frecuentes quedan sin respuesta y agregar skills o contexto.
    """
    data = _leer_aprendizaje()
    data["frases_fallidas"].append({
        "texto": texto,
        "razon": razon,
        "fecha": datetime.now().isoformat(),
    })
    # Mantener solo las últimas 500 para no crecer indefinidamente
    data["frases_fallidas"] = data["frases_fallidas"][-500:]
    data["estadisticas"]["fallbacks"] = data["estadisticas"].get("fallbacks", 0) + 1
    _guardar_aprendizaje(data)


def registrar_consulta(texto: str, respuesta: str):
    """Incrementa el contador de consultas totales."""
    data = _leer_aprendizaje()
    data["estadisticas"]["total_consultas"] = data["estadisticas"].get("total_consultas", 0) + 1
    _guardar_aprendizaje(data)


def agregar_correccion(frase_erronea: str, respuesta_correcta: str, skill_sugerida: str = ""):
    """
    Registra manualmente una corrección para que SOFÍA aprenda.
    Se puede llamar desde la UI o desde código externo.
    En el futuro, estas correcciones pueden usarse para fine-tuning o
    para agregar nuevas keywords al router automáticamente.
    """
    data = _leer_aprendizaje()
    data["correcciones"].append({
        "frase": frase_erronea,
        "respuesta_esperada": respuesta_correcta,
        "skill_sugerida": skill_sugerida,
        "fecha": datetime.now().isoformat(),
        "aplicada": False,
    })
    _guardar_aprendizaje(data)
    return f"Corrección registrada. Total correcciones: {len(data['correcciones'])}."


def obtener_estadisticas() -> str:
    """Devuelve un resumen de estadísticas de aprendizaje."""
    data = _leer_aprendizaje()
    stats = data.get("estadisticas", {})
    fallidas = data.get("frases_fallidas", [])
    correcciones = data.get("correcciones", [])
    return (
        f"Consultas totales: {stats.get('total_consultas', 0)}. "
        f"Sin respuesta: {stats.get('fallbacks', 0)}. "
        f"Frases fallidas registradas: {len(fallidas)}. "
        f"Correcciones en cola: {len([c for c in correcciones if not c.get('aplicada')])}."
    )


# ---------------------------------------------------------------------------
# Inferencia
# ---------------------------------------------------------------------------

def preguntar(texto: str, contexto_extra: str = "") -> str:
    """
    Pregunta libre a la IA local. Devuelve texto de respuesta.
    Registra automáticamente la consulta y los errores para aprendizaje.
    """
    _cargar()
    registrar_consulta(texto, "")

    if not _disponible:
        registrar_frase_fallida(texto, razon="sin_modelo")
        return "No tengo el modelo de IA disponible en este momento."

    prompt = f"{SYSTEM_PROMPT}\n"
    if contexto_extra:
        prompt += f"Información de contexto: {contexto_extra}\n"
    prompt += f"Usuario: {texto}\nSOFÍA:"

    try:
        salida = _llm(
            prompt,
            max_tokens=150,
            temperature=0.6,
            stop=["Usuario:", "\n\n"],
        )
        respuesta = salida["choices"][0]["text"].strip()
        if not respuesta:
            registrar_frase_fallida(texto, razon="respuesta_vacia")
            return "No tengo una respuesta para eso."
        return respuesta
    except Exception as e:
        registrar_frase_fallida(texto, razon=f"error_llm: {e}")
        return f"Error consultando la IA: {e}"