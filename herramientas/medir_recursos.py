"""
Mide CPU/RAM/VRAM de SOFÍA por etapa del pipeline (reposo, escuchando,
procesando, hablando).

Requiere que SOFÍA esté corriendo con SOFIA_DIAGNOSTICO=1 (para que
main.py escriba data/logs/diagnostico_estados.jsonl en cada transición de
estado). Este script muestrea CPU/RAM/VRAM del proceso de SOFÍA cada
~1-2s de forma independiente y, al terminar (Ctrl+C), cruza ambas series
por tiempo para reportar promedio y pico por etapa.

Uso:
    # Terminal 1:
    set SOFIA_DIAGNOSTICO=1   (PowerShell: $env:SOFIA_DIAGNOSTICO="1")
    python main.py

    # Terminal 2, mientras interactúas con SOFÍA por voz:
    python herramientas/medir_recursos.py
"""

import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

_RAIZ = Path(__file__).parent.parent
_LOG_ESTADOS = _RAIZ / "data" / "logs" / "diagnostico_estados.jsonl"
_LOG_DIR = _RAIZ / "data" / "logs"

INTERVALO_S = 1.5


def _encontrar_proceso_sofia():
    import psutil
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if "main.py" in cmdline and proc.pid != __import__("os").getpid():
                return psutil.Process(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def _vram_mb_sistema() -> float | None:
    try:
        import subprocess
        salida = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            timeout=2,
        )
        return float(salida.decode().strip().splitlines()[0])
    except Exception:
        return None


def _leer_estados():
    """Devuelve lista de (datetime, estado) leídos del log de main.py."""
    eventos = []
    if not _LOG_ESTADOS.exists():
        return eventos
    with open(_LOG_ESTADOS, encoding="utf-8") as f:
        for linea in f:
            try:
                d = json.loads(linea)
                eventos.append((datetime.fromisoformat(d["ts"]), d["estado"]))
            except Exception:
                continue
    return eventos


def main():
    print("=" * 60)
    print("SOFÍA — Monitor de recursos por etapa")
    print("=" * 60)

    proc = _encontrar_proceso_sofia()
    if proc is None:
        print("No se encontró un proceso 'main.py' corriendo. Inicia SOFÍA primero")
        print("(idealmente con SOFIA_DIAGNOSTICO=1) y vuelve a correr este script.")
        return

    print(f"Proceso de SOFÍA encontrado: PID {proc.pid}")
    print("Muestreando cada", INTERVALO_S, "s. Presiona Ctrl+C para terminar y ver el resumen.\n")

    muestras = []  # (datetime, cpu_pct, ram_mb, vram_mb)
    proc.cpu_percent()  # calienta la medición

    try:
        while True:
            time.sleep(INTERVALO_S)
            try:
                cpu = proc.cpu_percent()
                ram = proc.memory_info().rss / (1024 ** 2)
            except Exception:
                break
            vram = _vram_mb_sistema()
            muestras.append((datetime.now(), cpu, ram, vram))
            print(f"\rCPU: {cpu:5.1f}%  RAM: {ram:7.1f} MB  VRAM: {vram if vram is not None else '-':>7} MB", end="")
    except KeyboardInterrupt:
        print("\n\nFinalizando muestreo...")

    if not muestras:
        print("No se tomaron muestras.")
        return

    eventos_estado = _leer_estados()
    if not eventos_estado:
        print("\nAVISO: no se encontró data/logs/diagnostico_estados.jsonl.")
        print("¿Corriste SOFÍA con SOFIA_DIAGNOSTICO=1? Se reporta solo el agregado global.")
        eventos_estado = [(muestras[0][0], "desconocido")]

    def _estado_en(ts):
        estado = eventos_estado[0][1]
        for ts_evento, nombre in eventos_estado:
            if ts_evento <= ts:
                estado = nombre
            else:
                break
        return estado

    por_etapa = defaultdict(list)
    filas_csv = []
    for ts, cpu, ram, vram in muestras:
        etapa = _estado_en(ts)
        por_etapa[etapa].append((cpu, ram, vram))
        filas_csv.append([ts.isoformat(), etapa, cpu, ram, vram])

    print("\n" + "-" * 60)
    print(f"{'Etapa':<14} {'CPU prom%':>10} {'CPU pico%':>10} {'RAM prom MB':>12} {'RAM pico MB':>12} {'VRAM prom MB':>13}")
    resumen = {}
    for etapa, valores in por_etapa.items():
        cpus = [v[0] for v in valores]
        rams = [v[1] for v in valores]
        vrams = [v[2] for v in valores if v[2] is not None]
        fila = {
            "n_muestras": len(valores),
            "cpu_prom": sum(cpus) / len(cpus),
            "cpu_pico": max(cpus),
            "ram_prom_mb": sum(rams) / len(rams),
            "ram_pico_mb": max(rams),
            "vram_prom_mb": (sum(vrams) / len(vrams)) if vrams else None,
        }
        resumen[etapa] = fila
        vram_str = f"{fila['vram_prom_mb']:.1f}" if fila["vram_prom_mb"] is not None else "-"
        print(f"{etapa:<14} {fila['cpu_prom']:>10.1f} {fila['cpu_pico']:>10.1f} {fila['ram_prom_mb']:>12.1f} {fila['ram_pico_mb']:>12.1f} {vram_str:>13}")

    fecha = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    salida_json = _LOG_DIR / f"diagnostico_recursos_{fecha}.json"
    salida_csv = _LOG_DIR / f"diagnostico_recursos_{fecha}.csv"

    with open(salida_json, "w", encoding="utf-8") as f:
        json.dump({"resumen_por_etapa": resumen, "n_muestras_total": len(muestras)}, f, ensure_ascii=False, indent=2)

    with open(salida_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "estado", "cpu_pct", "ram_mb", "vram_mb"])
        writer.writerows(filas_csv)

    print(f"\nGuardado en:\n  {salida_json}\n  {salida_csv}")


if __name__ == "__main__":
    main()
