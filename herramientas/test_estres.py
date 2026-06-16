"""
Prueba de estrés / fugas de memoria de SOFÍA.

Ejecuta N consultas seguidas directamente contra el router (sin pasar por
voz, para que sea repetible sin desgastar al usuario), tomando las frases
de herramientas/guion_pruebas.json en ciclo. Mide RAM (y VRAM si hay GPU)
del propio proceso al inicio, cada cierto número de consultas, y al final.

Un delta_mb alto y sostenido entre el inicio y el final indica una fuga
de memoria a investigar (en core.ia, voz.hablar_qwen, etc).

Uso:
    python herramientas/test_estres.py --consultas 50
    python herramientas/test_estres.py --minutos 30
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

_RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(_RAIZ))

import main as sofia_main  # noqa: E402
from core.router import router  # noqa: E402

_GUION_PATH = Path(__file__).parent / "guion_pruebas.json"
_LOG_DIR = _RAIZ / "data" / "logs"


def _ram_mb(proc) -> float:
    return proc.memory_info().rss / (1024 ** 2)


def _vram_mb() -> float | None:
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / (1024 ** 2)
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Prueba de estrés/fugas de memoria de SOFÍA")
    parser.add_argument("--consultas", type=int, default=50, help="Número de consultas a ejecutar (default 50)")
    parser.add_argument("--minutos", type=float, default=None,
                         help="Si se indica, ignora --consultas y corre por tiempo fijo en minutos")
    args = parser.parse_args()

    print("=" * 70)
    print("SOFÍA — Test de estrés / fugas de memoria")
    print("=" * 70)

    sofia_main.registrar_skills()

    with open(_GUION_PATH, encoding="utf-8") as f:
        frases = [c["frase_esperada"] for c in json.load(f)["casos"]]

    import psutil
    proc = psutil.Process(os.getpid())
    proc.cpu_percent()

    ram_inicial = _ram_mb(proc)
    vram_inicial = _vram_mb()
    print(f"RAM inicial: {ram_inicial:.1f} MB  VRAM inicial: {vram_inicial} MB")

    filas = []
    n = 0
    completadas = 0
    fin = time.time() + args.minutos * 60 if args.minutos else None

    while True:
        if fin is not None:
            if time.time() >= fin:
                break
        elif n >= args.consultas:
            break

        frase = frases[n % len(frases)]
        n += 1
        resultado = "ok"
        tipo_error = ""
        try:
            t0 = time.perf_counter()
            router.procesar(frase)
            latencia_ms = (time.perf_counter() - t0) * 1000
            completadas += 1
        except Exception as e:
            latencia_ms = None
            resultado = "error"
            tipo_error = type(e).__name__
            print(f"  [{n}] ERROR ({tipo_error}): {e}")

        ram = _ram_mb(proc)
        vram = _vram_mb()
        filas.append({
            "n_consulta": n, "timestamp": datetime.now().isoformat(),
            "ram_mb": round(ram, 1), "vram_mb": round(vram, 1) if vram is not None else None,
            "latencia_ms": round(latencia_ms, 1) if latencia_ms is not None else None,
            "resultado": resultado, "tipo_error": tipo_error,
        })

        if n % 10 == 0 or n == 1:
            print(f"  [{n}] RAM: {ram:.1f} MB  VRAM: {vram if vram is not None else '-'} MB")

    ram_final = _ram_mb(proc)
    vram_final = _vram_mb()
    tasa_exito = completadas / n if n else 0.0

    resumen = {
        "fecha": datetime.now().isoformat(),
        "n_consultas": n,
        "n_completadas": completadas,
        "tasa_exito_pct": round(tasa_exito * 100, 1),
        "ram_inicial_mb": round(ram_inicial, 1),
        "ram_final_mb": round(ram_final, 1),
        "ram_delta_mb": round(ram_final - ram_inicial, 1),
        "vram_inicial_mb": round(vram_inicial, 1) if vram_inicial is not None else None,
        "vram_final_mb": round(vram_final, 1) if vram_final is not None else None,
        "vram_delta_mb": round(vram_final - vram_inicial, 1) if (vram_inicial is not None and vram_final is not None) else None,
    }

    print("\n" + "=" * 70)
    print("RESUMEN")
    print(json.dumps(resumen, indent=2, ensure_ascii=False))

    fecha = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    salida_json = _LOG_DIR / f"diagnostico_estres_{fecha}.json"
    salida_csv = _LOG_DIR / f"diagnostico_estres_{fecha}.csv"

    with open(salida_json, "w", encoding="utf-8") as f:
        json.dump({"resumen": resumen, "detalle": filas}, f, ensure_ascii=False, indent=2)

    with open(salida_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["n_consulta", "timestamp", "ram_mb", "vram_mb", "latencia_ms", "resultado", "tipo_error"])
        writer.writeheader()
        writer.writerows(filas)

    print(f"\nGuardado en:\n  {salida_json}\n  {salida_csv}")


if __name__ == "__main__":
    main()
