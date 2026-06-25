"""
Benchmark de calidad de respuestas del LLM local de SOFIA.

Ejecuta un conjunto de consultas de prueba contra el LLM (Qwen3-8B via
llama.cpp) y mide cuatro metricas de calidad:

  1. Tasa de espanol       % de respuestas que pasan el filtro _es_incoherente()
  2. Tasa de rechazo       % de respuestas descartadas por el filtro (en ingles,
                           razonamiento visible, etc.)
  3. Latencia de inferencia  Tiempo medio de generacion en ms
  4. Longitud de respuesta   Promedio de palabras por respuesta valida

Si el modelo LLM no esta disponible (archivo .gguf ausente), el benchmark
analiza el historial de data/aprendizaje.json para mostrar estadisticas
acumuladas reales de sesiones anteriores.

Uso:
    python herramientas/benchmark_llm.py            # usa el LLM si esta disponible
    python herramientas/benchmark_llm.py --solo-historico  # solo analiza aprendizaje.json

Salida:
    Consola con tabla de resultados por consulta
    data/logs/benchmark_llm_<fecha>.json

"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

_RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(_RAIZ))

_LOG_DIR = _RAIZ / "data" / "logs"
_LEARNING_PATH = _RAIZ / "data" / "aprendizaje.json"

# ─────────────────────────────────────────────────────────────────────────────
#  Corpus de consultas de prueba
# ─────────────────────────────────────────────────────────────────────────────

CONSULTAS_PRUEBA = [
    # (id, categoria, consulta)
    (1,  "saludo",        "Hola, buenos dias"),
    (2,  "fecha_hora",    "Que hora es en este momento"),
    (3,  "conocimiento",  "Que es la inteligencia artificial"),
    (4,  "conocimiento",  "Explica brevemente como funciona internet"),
    (5,  "consejo",       "Dame un consejo para concentrarme mejor al estudiar"),
    (6,  "curiosidad",    "Cual es el animal mas rapido del mundo"),
    (7,  "tecnologia",    "Que diferencia hay entre RAM y almacenamiento"),
    (8,  "conversacion",  "Como te llamas y que puedes hacer"),
    (9,  "matematica",    "Cuanto es 15 por 7"),
    (10, "opinion",       "Que opinas sobre el cambio climatico"),
    (11, "cocina",        "Como se prepara un arroz con leche"),
    (12, "historia",      "Quien fue Simon Bolivar"),
    (13, "ciencia",       "Por que el cielo es azul"),
    (14, "idioma",        "Como se dice gracias en frances"),
    (15, "resumen",       "Explica en pocas palabras que es Python"),
]

# Palabras clave esperadas por categoria para verificar relevancia tematica
_PALABRAS_CLAVE_DOMINIO = {
    "saludo":       ["hola", "buen", "dia", "saludar"],
    "fecha_hora":   ["hora", "minuto", "tiempo", "reloj"],
    "conocimiento": ["es", "consiste", "sistema", "proceso"],
    "consejo":      ["puedes", "intenta", "recomiend", "ayuda"],
    "curiosidad":   ["km", "veloc", "animal", "guepardo"],
    "tecnologia":   ["memoria", "disco", "dato", "almacen"],
    "conversacion": ["sofia", "asistente", "puedo", "ayudar"],
    "matematica":   ["105", "ciento", "resultado"],
    "opinion":      ["temperatura", "clima", "ambiente", "planeta"],
    "cocina":       ["leche", "azucar", "arroz", "hervir", "ingrediente"],
    "historia":     ["libertador", "independencia", "Venezuela", "Colombia"],
    "ciencia":      ["luz", "dispersion", "atmosfera", "onda"],
    "idioma":       ["merci", "gracias", "frances"],
    "resumen":      ["lenguaje", "programacion", "codigo"],
}

# Palabras comunes en ingles para deteccion rapida en el filtro
_PALABRAS_INGLES = {
    "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can",
    "this", "that", "these", "those", "it", "its",
    "i", "you", "he", "she", "we", "they", "me", "him", "her", "us", "them",
    "and", "or", "but", "not", "if", "then", "else",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "about",
    "okay", "let", "think", "need", "user", "sure", "just", "get",
}


def _contiene_palabras_ingles(texto: str) -> float:
    """Devuelve fraccion de palabras del texto que son palabras comunes en ingles."""
    palabras = texto.lower().split()
    if not palabras:
        return 0.0
    ingles = sum(1 for p in palabras if p.strip(".,;:!?\"'") in _PALABRAS_INGLES)
    return ingles / len(palabras)


def _relevancia_tematica(respuesta: str, categoria: str) -> bool:
    """True si la respuesta contiene al menos una palabra clave del dominio esperado."""
    claves = _PALABRAS_CLAVE_DOMINIO.get(categoria, [])
    if not claves:
        return True
    resp_lower = respuesta.lower()
    return any(c in resp_lower for c in claves)


# ─────────────────────────────────────────────────────────────────────────────
#  Benchmark con el LLM real
# ─────────────────────────────────────────────────────────────────────────────

def _ejecutar_benchmark_llm() -> dict:
    """Carga el LLM y ejecuta las consultas de prueba."""
    from core import ia

    if not ia.esta_disponible():
        print("[!] El modelo LLM no esta disponible (archivo .gguf no encontrado).")
        print("    Ejecuta con --solo-historico para analizar aprendizaje.json.")
        return {}

    print(f"Modelo: {Path(ia.MODEL_PATH).name}")
    print(f"Consultas: {len(CONSULTAS_PRUEBA)}\n")
    print(f"{'ID':<4} {'Categoria':<14} {'Lat(ms)':<9} {'Palabras':<9} {'Espanol':<8} {'Tema':<6} {'Respuesta (recortada)'}")
    print("-" * 80)

    resultados = []
    for cid, categoria, consulta in CONSULTAS_PRUEBA:
        t0 = time.perf_counter()
        try:
            respuesta = ia.preguntar(consulta)
        except Exception as e:
            respuesta = ""
            print(f"  [{cid:2}] ERROR en ia.preguntar: {e}")
        latencia_ms = (time.perf_counter() - t0) * 1000

        # Metricas de calidad
        from core.ia import _es_incoherente
        rechazada = _es_incoherente(respuesta)
        fraccion_ingles = _contiene_palabras_ingles(respuesta)
        n_palabras = len(respuesta.split()) if respuesta else 0
        relevante = _relevancia_tematica(respuesta, categoria) if not rechazada else False
        recorte = (respuesta[:60] + "...") if len(respuesta) > 63 else respuesta

        estado = "RECHAZADA" if rechazada else "OK"
        print(
            f"  [{cid:2}] {categoria:<14} {latencia_ms:>7.0f}ms  "
            f"{n_palabras:>5}pal  {'SI' if not rechazada else 'NO':<7}  "
            f"{'SI' if relevante else 'NO':<6}  {recorte!r}"
        )

        resultados.append({
            "id": cid,
            "categoria": categoria,
            "consulta": consulta,
            "respuesta": respuesta,
            "latencia_ms": round(latencia_ms, 1),
            "n_palabras": n_palabras,
            "rechazada": rechazada,
            "fraccion_ingles": round(fraccion_ingles, 3),
            "relevante": relevante,
        })

    return resultados


def _calcular_metricas(resultados: list) -> dict:
    """Calcula metricas agregadas a partir de los resultados."""
    if not resultados:
        return {}

    n = len(resultados)
    rechazadas = [r for r in resultados if r["rechazada"]]
    validas = [r for r in resultados if not r["rechazada"]]

    metricas = {
        "n_consultas": n,
        "n_validas": len(validas),
        "n_rechazadas": len(rechazadas),
        "tasa_espanol_pct": round(100 * len(validas) / n, 1),
        "tasa_rechazo_pct": round(100 * len(rechazadas) / n, 1),
    }

    if validas:
        metricas["latencia_ms_promedio"] = round(
            sum(r["latencia_ms"] for r in validas) / len(validas), 1
        )
        metricas["latencia_ms_min"] = round(min(r["latencia_ms"] for r in validas), 1)
        metricas["latencia_ms_max"] = round(max(r["latencia_ms"] for r in validas), 1)
        metricas["palabras_promedio"] = round(
            sum(r["n_palabras"] for r in validas) / len(validas), 1
        )
        metricas["palabras_min"] = min(r["n_palabras"] for r in validas)
        metricas["palabras_max"] = max(r["n_palabras"] for r in validas)
        metricas["relevancia_tematica_pct"] = round(
            100 * sum(1 for r in validas if r.get("relevante")) / len(validas), 1
        )

    if rechazadas:
        metricas["razones_rechazo_muestra"] = [
            {"consulta": r["consulta"], "fraccion_ingles": r["fraccion_ingles"]}
            for r in rechazadas[:3]
        ]

    return metricas


# ─────────────────────────────────────────────────────────────────────────────
#  Analisis historico desde aprendizaje.json
# ─────────────────────────────────────────────────────────────────────────────

def _analizar_historico() -> dict:
    """Lee data/aprendizaje.json y extrae estadisticas de sesiones anteriores."""
    if not _LEARNING_PATH.exists():
        print("[!] No se encontro data/aprendizaje.json — aun no hay sesiones registradas.")
        return {}

    with open(_LEARNING_PATH, encoding="utf-8") as f:
        data = json.load(f)

    frases_fallidas = data.get("frases_fallidas", [])
    correcciones = data.get("correcciones", [])
    consultas_totales = data.get("consultas_totales", 0)
    sin_respuesta = data.get("sin_respuesta", 0)
    respondidas_ok = consultas_totales - sin_respuesta

    print(f"Historial leido: {_LEARNING_PATH}")
    print(f"  Consultas totales registradas : {consultas_totales}")
    print(f"  Respondidas correctamente     : {respondidas_ok}")
    print(f"  Sin respuesta (fallback vacio): {sin_respuesta}")
    print(f"  Frases fallidas guardadas     : {len(frases_fallidas)}")
    print(f"  Correcciones en cola          : {len(correcciones)}")

    # Analizar razones de fallo
    razones = {}
    for ff in frases_fallidas:
        razon = ff.get("razon", "desconocida")
        razones[razon] = razones.get(razon, 0) + 1

    if razones:
        print("\n  Razones de fallo:")
        for razon, count in sorted(razones.items(), key=lambda x: -x[1]):
            print(f"    {razon:<25}: {count}")

    tasa_respuesta = round(100 * respondidas_ok / consultas_totales, 1) if consultas_totales else None

    return {
        "fuente": str(_LEARNING_PATH),
        "consultas_totales": consultas_totales,
        "respondidas_ok": respondidas_ok,
        "sin_respuesta": sin_respuesta,
        "tasa_respuesta_pct": tasa_respuesta,
        "frases_fallidas_guardadas": len(frases_fallidas),
        "correcciones_pendientes": len(correcciones),
        "razones_fallo": razones,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Punto de entrada
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark de calidad del LLM local de SOFIA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python herramientas/benchmark_llm.py\n"
            "  python herramientas/benchmark_llm.py --solo-historico\n"
        ),
    )
    parser.add_argument(
        "--solo-historico",
        action="store_true",
        help="No ejecutar el LLM; solo analizar data/aprendizaje.json",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("SOFIA -- Benchmark de calidad del LLM")
    print("=" * 70)

    informe = {
        "fecha": datetime.now().isoformat(),
        "metricas_benchmark": {},
        "historico": {},
        "detalle_consultas": [],
    }

    # ── Historico acumulado ──────────────────────────────────────────────────
    print("\n[1/2] Historial de sesiones anteriores")
    print("-" * 40)
    historico = _analizar_historico()
    informe["historico"] = historico

    # ── Benchmark en vivo ────────────────────────────────────────────────────
    if not args.solo_historico:
        print("\n[2/2] Benchmark en vivo con el LLM")
        print("-" * 40)
        try:
            resultados = _ejecutar_benchmark_llm()
        except Exception as e:
            print(f"[!] Error al cargar el LLM: {e}")
            resultados = []

        if resultados:
            metricas = _calcular_metricas(resultados)
            informe["metricas_benchmark"] = metricas
            informe["detalle_consultas"] = resultados

            print("\n" + "=" * 70)
            print("METRICAS DE CALIDAD")
            print("=" * 70)
            print(f"  Consultas ejecutadas     : {metricas.get('n_consultas', 0)}")
            print(f"  Respuestas en espanol    : {metricas.get('n_validas', 0)} "
                  f"({metricas.get('tasa_espanol_pct', 0):.1f}%)")
            print(f"  Respuestas rechazadas    : {metricas.get('n_rechazadas', 0)} "
                  f"({metricas.get('tasa_rechazo_pct', 0):.1f}%)")
            print(f"  Latencia media           : {metricas.get('latencia_ms_promedio', '-')} ms")
            print(f"  Latencia min/max         : {metricas.get('latencia_ms_min', '-')} / "
                  f"{metricas.get('latencia_ms_max', '-')} ms")
            print(f"  Palabras por respuesta   : {metricas.get('palabras_promedio', '-')} "
                  f"(min {metricas.get('palabras_min', '-')}, "
                  f"max {metricas.get('palabras_max', '-')})")
            print(f"  Relevancia tematica      : {metricas.get('relevancia_tematica_pct', '-')}%")
    else:
        print("\n[2/2] Benchmark en vivo omitido (--solo-historico)")

    # ── Guardar informe ──────────────────────────────────────────────────────
    fecha = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    salida = _LOG_DIR / f"benchmark_llm_{fecha}.json"

    with open(salida, "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=2)

    print(f"\nGuardado en: {salida}")


if __name__ == "__main__":
    main()
