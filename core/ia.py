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
    "Responde SIEMPRE en UNA sola frase corta, sin markdown, sin listas, "
    "sin repetir texto, sin traducir al inglés. "
    "Si no sabes algo, dilo en una frase."
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
    
    # Intentar descargar el modelo si no existe
    if not _descargar_modelo():
        print(f"[ia] No se pudo obtener el modelo")
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

    # Formato de chat Qwen3 (chatml)
    prompt = (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{texto}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    if contexto_extra:
        # Inyectar contexto en el turno del sistema
        prompt = (
            f"<|im_start|>system\n{SYSTEM_PROMPT} "
            f"Contexto útil: {contexto_extra}<|im_end|>\n"
            f"<|im_start|>user\n{texto}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    try:
        salida = _llm(
            prompt,
            max_tokens=80,          # corto: una frase
            temperature=0.5,
            repeat_penalty=1.3,     # evita repeticiones
            stop=[
                "<|im_end|>",       # stop nativo de Qwen3
                "<|im_start|>",
                "\n\n",
                "SOFÍA:",
                "Usuario:",
                "Answer:",           # evita que cambie al inglés
                "user\n",
            ],
        )
        respuesta = salida["choices"][0]["text"].strip()
        # Limpiar cualquier artefacto que se cuele igual
        for tag in ["<|im_end|>", "<|im_start|>", "SOFÍA:", "Answer:"]:
            respuesta = respuesta.split(tag)[0].strip()
        if not respuesta:
            registrar_frase_fallida(texto, razon="respuesta_vacia")
            return "No tengo una respuesta para eso."
        return respuesta
    except Exception as e:
        registrar_frase_fallida(texto, razon=f"error_llm: {e}")
        return f"Error consultando la IA: {e}"