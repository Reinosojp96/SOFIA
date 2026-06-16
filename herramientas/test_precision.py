"""
Test interactivo de precisión de reconocimiento de voz para SOFÍA.

Recorre herramientas/guion_pruebas.json en 3 bloques de condición
(silencio, ruido_moderado, distancia). Para cada frase: la muestra en
consola, espera Enter, captura por micrófono con Escuchador.escuchar_frase()
(sin necesidad de decir la wake-word), calcula el Word Error Rate (WER)
frente a la frase esperada, pasa el texto transcrito por el router para
medir si acertó la skill y cuánto tardó (incluye el LLM local si cae a
fallback), y mide la latencia de TTS (tiempo hasta el primer audio y
tiempo total). También repite el mismo flujo usando el texto exacto del
guion (sin pasar por STT) como línea base de comparación voz-vs-texto.

Cada frase corre en un bloque try/except independiente: un fallo puntual
no aborta la corrida completa, se registra como error y se continúa.

Uso:
    python herramientas/test_precision.py

Salida:
    data/logs/diagnostico_precision_<fecha>.json
    data/logs/diagnostico_precision_<fecha>.csv
"""

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
from voz.escuchar import Escuchador  # noqa: E402
from voz import hablar as voz_hablar  # noqa: E402

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
    return {
        "whisper": os.environ.get("SOFIA_WHISPER_MODEL", "base"),
        "tts_motor": os.environ.get("SOFIA_TTS_MOTOR", "pyttsx3"),
        "tts_voz": os.environ.get("SOFIA_VOZ_SPEAKER", "serena"),
        "llm": Path(core_ia.MODEL_PATH).name,
    }


def _medir_tts(respuesta: str) -> tuple[float | None, float | None]:
    """Devuelve (tts_primer_audio_ms, tts_total_ms). Reproduce la respuesta completa."""
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


def main():
    print("=" * 70)
    print("SOFÍA — Test de precisión de voz")
    print("=" * 70)

    specs = _capturar_specs_hardware()
    versiones = _capturar_versiones_modelos()
    print(f"\nHardware: {specs}")
    print(f"Modelos:  {versiones}\n")

    sofia_main.registrar_skills()

    with open(_GUION_PATH, encoding="utf-8") as f:
        guion = json.load(f)["casos"]

    bloques = {}
    for caso in guion:
        bloques.setdefault(caso["condicion"], []).append(caso)

    print("Cargando micrófono y modelos de voz (puede tardar unos segundos)...")
    escuchador = Escuchador()
    escuchador.cargar_whisper_cmd()

    resultados = []
    instrucciones = {
        "silencio": "Asegúrate de estar en un ambiente SIN ruido de fondo.",
        "ruido_moderado": "Activa una fuente de ruido moderado (ventilador, música baja o TV).",
        "distancia": "Aléjate del micrófono (alterna entre 50cm / 1m / 2m según la frase).",
    }

    for condicion, casos in bloques.items():
        print("\n" + "-" * 70)
        print(f"BLOQUE: {condicion.upper()} — {instrucciones.get(condicion, '')}")
        input("Presiona Enter cuando estés listo para empezar este bloque...")

        for caso in casos:
            frase = caso["frase_esperada"]
            esperada = caso["skill_esperada"]
            fila = {
                "id": caso["id"], "condicion": condicion, "categoria": caso["categoria"],
                "frase_esperada": frase, "skill_esperada": esperada,
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

                # Control voz-vs-texto: mismo flujo usando la frase exacta (sin STT)
                detectada_texto = _skill_que_matchea(frase)
                router.procesar(frase)  # no se mide latencia de nuevo, solo intent

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

    # ── Agregados ──
    completados = [r for r in resultados if r["resultado"] == "ok"]
    tasa_exito = len(completados) / len(resultados) if resultados else 0.0

    por_condicion = {}
    for cond in bloques:
        filas = [r for r in completados if r["condicion"] == cond]
        if not filas:
            continue
        por_condicion[cond] = {
            "n": len(filas),
            "wer_prom": round(sum(r["wer"] for r in filas) / len(filas), 3),
            "intent_correcto_voz_pct": round(100 * sum(r["intent_correcto_voz"] for r in filas) / len(filas), 1),
            "intent_correcto_texto_pct": round(100 * sum(r["intent_correcto_texto"] for r in filas) / len(filas), 1),
        }

    latencias = [r for r in completados]
    resumen = {
        "fecha": datetime.now().isoformat(),
        "hardware": specs,
        "modelos": versiones,
        "n_total": len(resultados),
        "n_completados": len(completados),
        "tasa_exito_pct": round(tasa_exito * 100, 1),
        "wer_promedio_global": round(sum(r["wer"] for r in completados) / len(completados), 3) if completados else None,
        "intent_correcto_voz_pct_global": round(100 * sum(r["intent_correcto_voz"] for r in completados) / len(completados), 1) if completados else None,
        "intent_correcto_texto_pct_global": round(100 * sum(r["intent_correcto_texto"] for r in completados) / len(completados), 1) if completados else None,
        "stt_ms_promedio": round(sum(r["stt_ms"] for r in latencias) / len(latencias), 1) if latencias else None,
        "router_ms_promedio": round(sum(r["router_ms"] for r in latencias) / len(latencias), 1) if latencias else None,
        "tts_primer_audio_ms_promedio": (lambda v: round(sum(v) / len(v), 1) if v else None)(
            [r["tts_primer_audio_ms"] for r in latencias if r.get("tts_primer_audio_ms")]),
        "tts_total_ms_promedio": (lambda v: round(sum(v) / len(v), 1) if v else None)(
            [r["tts_total_ms"] for r in latencias if r.get("tts_total_ms")]),
        "por_condicion": por_condicion,
    }

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(json.dumps(resumen, indent=2, ensure_ascii=False))

    fecha = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    salida_json = _LOG_DIR / f"diagnostico_precision_{fecha}.json"
    salida_csv = _LOG_DIR / f"diagnostico_precision_{fecha}.csv"

    with open(salida_json, "w", encoding="utf-8") as f:
        json.dump({"resumen": resumen, "detalle": resultados}, f, ensure_ascii=False, indent=2)

    campos = ["id", "condicion", "categoria", "frase_esperada", "transcrito", "wer",
              "skill_esperada", "intent_correcto_voz", "intent_correcto_texto",
              "stt_ms", "router_ms", "tts_primer_audio_ms", "tts_total_ms", "resultado"]
    with open(salida_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(resultados)

    print(f"\nGuardado en:\n  {salida_json}\n  {salida_csv}")


if __name__ == "__main__":
    main()
