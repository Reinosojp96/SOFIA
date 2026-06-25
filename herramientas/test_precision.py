"""
Test de precisión de reconocimiento de voz para SOFÍA.

Recorre herramientas/guion_pruebas.json en 3 bloques de condición
(silencio, ruido_moderado, distancia). Disponible en dos modos:

  --modo voz (default)
      Interactivo con micrófono real. Para cada frase: la muestra en
      consola, espera Enter, captura con Escuchador.escuchar_frase(),
      calcula WER frente a la frase esperada y mide latencia STT + Router + TTS.

  --modo texto
      Sin micrófono. Alimenta cada frase del guion directamente al router
      (saltando STT), mide precisión de intents y latencia de router.
      Útil para demo en sala o entornos sin hardware de audio.

También repite el flujo con el texto exacto del guion (sin STT) como
línea base de comparación voz-vs-texto (solo en --modo voz).

Cada frase corre en un bloque try/except independiente: un fallo puntual
no aborta la corrida completa, se registra como error y se continúa.

Uso:
    python herramientas/test_precision.py              # modo voz (micrófono)
    python herramientas/test_precision.py --modo texto # sin micrófono

Salida:
    data/logs/diagnostico_precision_<fecha>.json
    data/logs/diagnostico_precision_<fecha>.csv

MEJORAS v2
----------
- Añadido --modo {voz,texto}: el modo texto no requiere micrófono y
  puede usarse para demostración ante un jurado sin hardware de audio.
"""

import argparse
import csv
import json
import os
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

_RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(_RAIZ))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import main as sofia_main  # noqa: E402
from core.router import router, _quitar_tildes  # noqa: E402
from core import ia as core_ia  # noqa: E402

_GUION_PATH = Path(__file__).parent / "guion_pruebas.json"
_LOG_DIR = _RAIZ / "data" / "logs"


def _wer(hipotesis: str, referencia: str) -> float:
    """Word Error Rate: distancia de edición a nivel de palabra / nº palabras de referencia."""
    ref = referencia.lower().split()
    hip = hipotesis.lower().split()
    n, m = len(ref), len(hip)
    if n == 0:
        return 0.0 if m == 0 else 1.0
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            costo = 0 if ref[i - 1] == hip[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + costo)
    return dp[n][m] / n


def _skill_que_matchea(texto: str) -> str:
    """Determina qué skill respondería a 'texto' sin ejecutarla (solo para auditar)."""
    norm = router._normalizar(texto)
    for nombre, kws, _fn in router._skills:
        if any(_quitar_tildes(kw) in norm for kw in kws):
            return nombre
    return "fallback"


def _capturar_specs_hardware() -> dict:
    specs = {
        "cpu": platform.processor() or platform.machine(),
        "cpu_nucleos": os.cpu_count(),
        "ram_gb": None,
        "gpu": None,
        "vram_gb": None,
    }
    try:
        import psutil
        specs["ram_gb"] = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            specs["gpu"] = torch.cuda.get_device_name(0)
            specs["vram_gb"] = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 1)
    except Exception:
        pass
    return specs


def _capturar_versiones_modelos() -> dict:
    llm_path = Path(core_ia.MODEL_PATH)
    return {
        "whisper": os.environ.get("SOFIA_WHISPER_MODEL", "base"),
        "tts_motor": os.environ.get("SOFIA_TTS_MOTOR", "pyttsx3"),
        "tts_voz": os.environ.get("SOFIA_VOZ_SPEAKER", "serena"),
        "llm": llm_path.name if llm_path.exists() else "no_disponible",
    }


def _medir_tts(respuesta: str) -> tuple:
    """Devuelve (tts_primer_audio_ms, tts_total_ms). Reproduce la respuesta completa."""
    from voz import hablar as voz_hablar
    motor = os.environ.get("SOFIA_TTS_MOTOR", "pyttsx3").lower()
    if motor != "qwen":
        t0 = time.perf_counter()
        voz_hablar.hablar(respuesta)
        return None, (time.perf_counter() - t0) * 1000

    from voz.hablar import _ensure_qwen
    if not _ensure_qwen():
        t0 = time.perf_counter()
        voz_hablar.hablar(respuesta)
        return None, (time.perf_counter() - t0) * 1000

    import voz.hablar as _vh
    primera_oracion = (respuesta.split(".")[0].strip() or respuesta)

    t0 = time.perf_counter()
    _vh._qwen_motor.generar_array(primera_oracion)
    tts_primer_audio_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    audio, sr = _vh._qwen_motor.generar_array(respuesta)
    tts_total_ms = (time.perf_counter() - t1) * 1000

    if audio is not None:
        try:
            import sounddevice as sd
            sd.play(audio, samplerate=sr)
            sd.wait()
        except Exception:
            pass

    return tts_primer_audio_ms, tts_total_ms


# ─────────────────────────────────────────────────────────────────────────────
#  MODO TEXTO: sin micrófono, solo mide intents y latencia de router
# ─────────────────────────────────────────────────────────────────────────────

def _correr_modo_texto(guion: list) -> list:
    """
    Ejecuta el benchmark sin micrófono.

    Alimenta cada frase directamente al router (sin STT) y mide:
    - Si el intent detectado coincide con la skill esperada.
    - Latencia del router (ms).
    No calcula WER (no hay transcripción que comparar con una grabación real).
    """
    print("\nMODO TEXTO — sin micrófono. Cada frase se alimenta directamente al router.")
    print("=" * 70)

    bloques = {}
    for caso in guion:
        bloques.setdefault(caso["condicion"], []).append(caso)

    resultados = []

    for condicion, casos in bloques.items():
        print(f"\n── BLOQUE: {condicion.upper()} ({len(casos)} frases) ──")
        for caso in casos:
            frase = caso["frase_esperada"]
            esperada = caso["skill_esperada"]
            fila = {
                "id": caso["id"],
                "condicion": condicion,
                "categoria": caso["categoria"],
                "frase_esperada": frase,
                "skill_esperada": esperada,
                "modo": "texto",
                "resultado": "ok",
            }

            try:
                detectada = _skill_que_matchea(frase)

                t0 = time.perf_counter()
                router.procesar(frase)
                router_ms = (time.perf_counter() - t0) * 1000

                correcto = detectada == esperada
                simbolo = "OK" if correcto else "!!"
                print(f"  [{caso['id']:2}] [{simbolo}] \"{frase}\"")
                if not correcto:
                    print(f"        -> esperada: {esperada!r}  detectada: {detectada!r}")

                fila.update({
                    "transcrito": frase,
                    "wer": 0.0,
                    "stt_ms": None,
                    "router_ms": round(router_ms, 1),
                    "tts_primer_audio_ms": None,
                    "tts_total_ms": None,
                    "intent_correcto_voz": correcto,
                    "intent_correcto_texto": correcto,
                })
            except Exception as e:
                fila.update({"resultado": "error", "tipo": type(e).__name__, "mensaje": str(e)})
                print(f"  [{caso['id']:2}] ERROR: {e}")

            resultados.append(fila)

    return resultados


# ─────────────────────────────────────────────────────────────────────────────
#  MODO VOZ: interactivo con micrófono real
# ─────────────────────────────────────────────────────────────────────────────

def _correr_modo_voz(guion: list) -> list:
    """Modo original: captura de audio real con el Escuchador, calcula WER."""
    from voz.escuchar import Escuchador

    bloques = {}
    for caso in guion:
        bloques.setdefault(caso["condicion"], []).append(caso)

    print("Cargando micrófono y modelos de voz (puede tardar unos segundos)...")
    escuchador = Escuchador()
    escuchador.cargar_whisper_cmd()

    resultados = []
    instrucciones = {
        "silencio": "Asegurate de estar en un ambiente SIN ruido de fondo.",
        "ruido_moderado": "Activa una fuente de ruido moderado (ventilador, musica baja o TV).",
        "distancia": "Alejate del microfono (alterna entre 50cm / 1m / 2m segun la frase).",
    }

    for condicion, casos in bloques.items():
        print("\n" + "-" * 70)
        print(f"BLOQUE: {condicion.upper()} — {instrucciones.get(condicion, '')}")
        input("Presiona Enter cuando estes listo para empezar este bloque...")

        for caso in casos:
            frase = caso["frase_esperada"]
            esperada = caso["skill_esperada"]
            fila = {
                "id": caso["id"],
                "condicion": condicion,
                "categoria": caso["categoria"],
                "frase_esperada": frase,
                "skill_esperada": esperada,
                "modo": "voz",
                "resultado": "ok",
            }
            print(f"\n[{caso['id']}] Di en voz alta: \"{frase}\"")
            input("(Enter para empezar a grabar) ")

            try:
                t0 = time.perf_counter()
                transcrito = escuchador.escuchar_frase(tiempo_espera=6, limite_frase=10) or ""
                stt_ms = (time.perf_counter() - t0) * 1000
                print(f"  Transcrito: \"{transcrito}\"")

                wer = _wer(transcrito, frase)
                detectada_voz = _skill_que_matchea(transcrito)

                t1 = time.perf_counter()
                respuesta_voz = router.procesar(transcrito)
                router_ms = (time.perf_counter() - t1) * 1000

                tts_primer_audio_ms, tts_total_ms = _medir_tts(respuesta_voz)

                detectada_texto = _skill_que_matchea(frase)
                router.procesar(frase)

                fila.update({
                    "transcrito": transcrito,
                    "wer": round(wer, 3),
                    "stt_ms": round(stt_ms, 1),
                    "router_ms": round(router_ms, 1),
                    "tts_primer_audio_ms": round(tts_primer_audio_ms, 1) if tts_primer_audio_ms else None,
                    "tts_total_ms": round(tts_total_ms, 1) if tts_total_ms else None,
                    "intent_correcto_voz": detectada_voz == esperada,
                    "intent_correcto_texto": detectada_texto == esperada,
                })
            except Exception as e:
                fila.update({"resultado": "error", "tipo": type(e).__name__, "mensaje": str(e)})
                print(f"  ERROR: {e}")

            resultados.append(fila)

    return resultados


# ─────────────────────────────────────────────────────────────────────────────
#  Agregados y reporte
# ─────────────────────────────────────────────────────────────────────────────

def _calcular_resumen(resultados: list, specs: dict, versiones: dict, modo: str) -> dict:
    completados = [r for r in resultados if r["resultado"] == "ok"]
    tasa_exito = len(completados) / len(resultados) if resultados else 0.0

    bloques_uniq = list(dict.fromkeys(r["condicion"] for r in resultados))
    por_condicion = {}
    for cond in bloques_uniq:
        filas = [r for r in completados if r["condicion"] == cond]
        if not filas:
            continue
        entry = {
            "n": len(filas),
            "intent_correcto_pct": round(100 * sum(r["intent_correcto_voz"] for r in filas) / len(filas), 1),
        }
        if modo == "voz":
            entry["wer_prom"] = round(sum(r["wer"] for r in filas) / len(filas), 3)
            entry["intent_correcto_texto_pct"] = round(
                100 * sum(r["intent_correcto_texto"] for r in filas) / len(filas), 1
            )
        por_condicion[cond] = entry

    resumen = {
        "fecha": datetime.now().isoformat(),
        "modo": modo,
        "hardware": specs,
        "modelos": versiones,
        "n_total": len(resultados),
        "n_completados": len(completados),
        "tasa_exito_pct": round(tasa_exito * 100, 1),
        "intent_correcto_pct_global": (
            round(100 * sum(r["intent_correcto_voz"] for r in completados) / len(completados), 1)
            if completados else None
        ),
        "router_ms_promedio": (
            round(sum(r["router_ms"] for r in completados) / len(completados), 1)
            if completados else None
        ),
        "por_condicion": por_condicion,
    }

    if modo == "voz":
        resumen["wer_promedio_global"] = (
            round(sum(r["wer"] for r in completados) / len(completados), 3) if completados else None
        )
        latencias_stt = [r["stt_ms"] for r in completados if r.get("stt_ms")]
        resumen["stt_ms_promedio"] = (
            round(sum(latencias_stt) / len(latencias_stt), 1) if latencias_stt else None
        )
        latencias_tts = [r["tts_total_ms"] for r in completados if r.get("tts_total_ms")]
        resumen["tts_total_ms_promedio"] = (
            round(sum(latencias_tts) / len(latencias_tts), 1) if latencias_tts else None
        )

    return resumen


def main():
    parser = argparse.ArgumentParser(
        description="Test de precision STT/intent de SOFIA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python herramientas/test_precision.py              # con microfono\n"
            "  python herramientas/test_precision.py --modo texto # sin microfono\n"
        ),
    )
    parser.add_argument(
        "--modo",
        choices=["voz", "texto"],
        default="voz",
        help=(
            "voz: interactivo con microfono real (default); "
            "texto: sin microfono, alimenta frases directamente al router"
        ),
    )
    args = parser.parse_args()

    print("=" * 70)
    print(f"SOFIA -- Test de precision  [modo: {args.modo}]")
    print("=" * 70)

    specs = _capturar_specs_hardware()
    versiones = _capturar_versiones_modelos()
    print(f"\nHardware: {specs}")
    print(f"Modelos:  {versiones}\n")

    sofia_main.registrar_skills()

    with open(_GUION_PATH, encoding="utf-8") as f:
        guion = json.load(f)["casos"]

    if args.modo == "texto":
        resultados = _correr_modo_texto(guion)
    else:
        resultados = _correr_modo_voz(guion)

    resumen = _calcular_resumen(resultados, specs, versiones, args.modo)

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(json.dumps(resumen, indent=2, ensure_ascii=False))

    fecha = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    salida_json = _LOG_DIR / f"diagnostico_precision_{fecha}.json"
    salida_csv  = _LOG_DIR / f"diagnostico_precision_{fecha}.csv"

    with open(salida_json, "w", encoding="utf-8") as f:
        json.dump({"resumen": resumen, "detalle": resultados}, f, ensure_ascii=False, indent=2)

    campos = [
        "id", "condicion", "categoria", "frase_esperada", "transcrito", "wer",
        "skill_esperada", "intent_correcto_voz", "intent_correcto_texto",
        "stt_ms", "router_ms", "tts_primer_audio_ms", "tts_total_ms", "resultado", "modo",
    ]
    with open(salida_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(resultados)

    print(f"\nGuardado en:\n  {salida_json}\n  {salida_csv}")


if __name__ == "__main__":
    main()
