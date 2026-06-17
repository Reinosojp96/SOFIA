"""
Wrapper para llama.cpp (vía llama-cpp-python).
Funciones públicas: preguntar(texto) -> str, esta_disponible() -> bool

MEJORAS v2:
  - Variable de entorno unificada: SOFIA_MODEL_PATH (antes era ALE_MODEL_PATH)
  - SYSTEM_PROMPT dice "SOFÍA", no "ALE"
  - Soporte de aprendizaje automático: registra errores y correcciones en
    data/aprendizaje.json para retroalimentación futura
  - historial de conversación configurable (memoria de contexto corta)
  - Descarga automática del modelo GGUF desde Hugging Face
"""

import os
import json
import sys
from datetime import datetime
from pathlib import Path
import urllib.request
import urllib.parse

_llm = None
_disponible = False

# URL del modelo GGUF en Hugging Face
MODEL_URL = "https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf?download=true"

# Ruta del modelo: SOFIA_MODEL_PATH tiene prioridad; ALE_MODEL_PATH como alias
# para no romper instalaciones existentes
MODEL_PATH = (
    os.environ.get("SOFIA_MODEL_PATH")
    or os.environ.get("ALE_MODEL_PATH")
    or str(Path(__file__).parent.parent / "data" / "modelo.gguf")
)

SYSTEM_PROMPT = (
    "Eres SOFÍA, una asistente de voz en español. "
    "Responde SIEMPRE en español, en UNA sola frase corta, sin markdown, sin listas, "
    "sin repetir texto. NUNCA uses inglés, chino, ni ningún otro idioma. "
    "Si no sabes algo, dilo en español en una frase."
)

# Ruta del archivo de aprendizaje
_LEARNING_PATH = Path(__file__).parent.parent / "data" / "aprendizaje.json"


# ---------------------------------------------------------------------------
# Descarga del modelo
# ---------------------------------------------------------------------------

def _descargar_modelo():
    """Descarga el modelo GGUF desde Hugging Face si no existe."""
    model_path = Path(MODEL_PATH)
    
    # Si el modelo ya existe, no hacer nada
    if model_path.exists():
        print(f"[ia] Modelo ya existe en {model_path}")
        return True
    
    # Crear directorio data si no existe
    model_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"[ia] Modelo no encontrado. Iniciando descarga desde Hugging Face...")
    print(f"[ia] URL: {MODEL_URL}")
    print(f"[ia] Destino: {model_path}")
    print(f"[ia] Tamaño aproximado: ~4.5 GB. Por favor espera...")
    
    try:
        # Configurar la solicitud con headers para evitar problemas
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(MODEL_URL, headers=headers)
        
        # Descargar con barra de progreso simple
        with urllib.request.urlopen(req) as response:
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 8192
            
            with open(model_path, 'wb') as out_file:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    
                    # Mostrar progreso
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        mb_downloaded = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        print(f"\r[ia] Descargando: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)", end='')
                        sys.stdout.flush()
        
        print("\n[ia] ¡Descarga completada!")
        return True
        
    except Exception as e:
        print(f"\n[ia] Error al descargar el modelo: {e}")
        # Limpiar archivo parcial si existe
        if model_path.exists():
            model_path.unlink()
        return False


# ---------------------------------------------------------------------------
# Carga del modelo
# ---------------------------------------------------------------------------

def _cargar():
    global _llm, _disponible
    if _llm is not None:
        return
    
    # Si el modelo no existe, no intentar descargarlo en tiempo de ejecución.
    # La descarga debe hacerse durante la instalación (setup.py paso 8).
    if not os.path.exists(MODEL_PATH):
        print(f"[ia] Modelo no encontrado en {MODEL_PATH}.")
        print(f"[ia] Ejecuta el instalador (setup.py) para descargarlo.")
        _disponible = False
        return
    
    try:
        from llama_cpp import Llama
        if not os.path.exists(MODEL_PATH):
            print(f"[ia] Modelo no encontrado en {MODEL_PATH} después de la descarga")
            _disponible = False
            return
        
        print(f"[ia] Cargando modelo desde {MODEL_PATH}...")
        print(f"[ia] Esto puede tomar unos segundos la primera vez...")
        
        _llm = Llama(
            model_path=MODEL_PATH,
            n_ctx=2048,
            n_threads=os.cpu_count() or 4,
            verbose=False,
        )
        _disponible = True
        print(f"[ia] Modelo cargado exitosamente")
        
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

def _es_incoherente(respuesta: str) -> bool:
    """
    Detecta si la respuesta es incoherente o está en inglés.
    Señales: empieza con razonamiento visible, mayoría de palabras en inglés,
    o contiene marcadores del modo thinking de Qwen3.
    """
    if not respuesta:
        return True

    r = respuesta.lower()

    # Razonamiento visible (modo thinking filtrado)
    frases_pensamiento = [
        "okay, the user", "let's break", "let me ", "the user is asking",
        "i need to", "i should", "i'll ", "so the answer", "first,",
        "this is a", "the context", "based on the",
    ]
    if any(r.startswith(f) for f in frases_pensamiento):
        return True

    # Marcadores internos de Qwen3 thinking
    if "<think>" in r or "</think>" in r:
        return True

    # Caracteres CJK (chino, japonés, coreano) — respuesta inválida
    import unicodedata
    if any(unicodedata.category(c) in ("Lo",) and "一" <= c <= "鿿" for c in respuesta):
        return True

    # Mayoría de palabras en inglés (heurística simple)
    palabras_en = {
        "the", "and", "is", "are", "you", "have", "has", "with", "that",
        "this", "from", "for", "not", "but", "was", "it", "be", "or",
        "an", "at", "by", "so", "if", "do", "we", "as", "on", "in",
        "user", "asking", "okay", "let", "can", "will", "would", "should",
        "your", "their", "they", "what", "which", "when", "where", "how",
    }
    tokens = r.split()
    if len(tokens) >= 4:
        en_count = sum(1 for t in tokens if t.strip(".,?!;:") in palabras_en)
        if en_count / len(tokens) > 0.4:
            return True

    return False


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

    sistema = SYSTEM_PROMPT
    if contexto_extra:
        sistema += f" Contexto útil: {contexto_extra}"

    # Formato chatml de Qwen3.
    # Prefillamos el turno del asistente con <think>\n\n</think>\n para
    # desactivar el modo "thinking" del modelo y evitar que filtre su
    # razonamiento interno en inglés.
    prompt = (
        f"<|im_start|>system\n{sistema}<|im_end|>\n"
        f"<|im_start|>user\n{texto} /no_think<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n\n</think>\n"
    )

    try:
        salida = _llm(
            prompt,
            max_tokens=100,
            temperature=0.3,
            repeat_penalty=1.3,
            stop=[
                "<|im_end|>",
                "<|im_start|>",
                "\n\n",
                "\n",
                "SOFÍA:",
                "Usuario:",
                "Answer:",
                "user\n",
                "<think>",
            ],
        )
        respuesta = salida["choices"][0]["text"].strip()

        # Limpiar artefactos de formato
        for tag in ["<|im_end|>", "<|im_start|>", "SOFÍA:", "Answer:", "</think>", "<think>"]:
            respuesta = respuesta.split(tag)[0].strip()

        if not respuesta or _es_incoherente(respuesta):
            registrar_frase_fallida(texto, razon="incoherente_o_ingles")
            return "No entendí eso, ¿puedes decirlo de otra forma?"

        return respuesta
    except Exception as e:
        registrar_frase_fallida(texto, razon=f"error_llm: {e}")
        return f"Error consultando la IA: {e}"