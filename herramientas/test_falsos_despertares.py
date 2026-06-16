"""
Mide la tasa de falsos despertares del wake-word de SOFÍA.

Corre el mismo bucle de activación continua que usa main.py
(Escuchador.esperar_activacion()) durante una ventana de tiempo
configurable, sin ejecutar ningún comando real. Cada vez que el bucle
detecta la wake-word sin que el usuario la haya dicho intencionalmente,
es un falso despertar.

Un falso despertar es un evento raro: en una ventana corta (30 min) es
fácil obtener "0" por simple azar sin que la tasa real sea cero. Por eso
el default es 30 min (mínimo aceptable para una primera idea) pero se
recomienda correrlo 2 horas para un dato confiable de cara al informe
final.

Uso:
    python herramientas/test_falsos_despertares.py --minutos 30
    python herramientas/test_falsos_despertares.py --minutos 120   (recomendado)

Durante la prueba, reproduce audio ambiente normal: conversación sin
decir "Sofía", música, un video de YouTube o la TV. Si en algún momento
SÍ quieres decir la wake-word intencionalmente (para medir también la
tasa de activación correcta), dilo y confírmalo cuando el script te
pregunte al final.
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

_RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(_RAIZ))

from voz.escuchar import Escuchador, PALABRA_ACTIVACION  # noqa: E402

_LOG_DIR = _RAIZ / "data" / "logs"


def main():
    parser = argparse.ArgumentParser(description="Mide falsos despertares del wake-word de SOFÍA")
    parser.add_argument("--minutos", type=float, default=30,
                         help="Duración de la prueba en minutos (default 30, recomendado 120)")
    args = parser.parse_args()

    if args.minutos < 120:
        print(f"AVISO: estás corriendo {args.minutos} min. Para un dato confiable de cara")
        print("al informe final se recomiendan 2 horas (--minutos 120); los falsos")
        print("despertares son eventos raros y en ventanas cortas puede salir '0' por azar.\n")

    print("=" * 70)
    print("SOFÍA — Test de falsos despertares")
    print("=" * 70)
    print(f"Duración: {args.minutos} min. Palabra de activación: '{PALABRA_ACTIVACION}'")
    print("Reproduce audio ambiente normal (conversación, música, TV, YouTube)")
    print("SIN decir la wake-word, salvo que quieras medir también activaciones reales.")
    print("Presiona Ctrl+C para terminar antes de tiempo.\n")

    escuchador = Escuchador()
    fin = time.time() + args.minutos * 60

    eventos = []  # (timestamp, tipo) tipo in {despertar, error}
    n_despertares = 0
    n_errores = 0
    n_iteraciones = 0

    try:
        while time.time() < fin:
            n_iteraciones += 1
            try:
                escuchador.esperar_activacion()
                n_despertares += 1
                ahora = datetime.now()
                eventos.append((ahora.isoformat(), "despertar"))
                restante = max(0, fin - time.time())
                print(f"  [{ahora.strftime('%H:%M:%S')}] Activación detectada. "
                      f"Restan {restante / 60:.1f} min. Total: {n_despertares}")
            except Exception as e:
                n_errores += 1
                eventos.append((datetime.now().isoformat(), "error"))
                print(f"  ERROR puntual (se continúa): {e}")
    except KeyboardInterrupt:
        print("\nPrueba interrumpida por el usuario.")

    duracion_real_min = args.minutos - max(0, (fin - time.time()) / 60)

    print("\n" + "-" * 70)
    print(f"Activaciones detectadas durante la ventana pasiva: {n_despertares}")
    print("¿Cuántas de esas activaciones fueron porque TÚ dijiste la wake-word")
    intencionales = input("intencionalmente durante la prueba? (número, 0 si ninguna): ").strip()
    try:
        intencionales = int(intencionales)
    except ValueError:
        intencionales = 0

    falsos_despertares = max(0, n_despertares - intencionales)
    tasa_exito = (n_iteraciones - n_errores) / n_iteraciones if n_iteraciones else 1.0

    resumen = {
        "fecha": datetime.now().isoformat(),
        "duracion_min_objetivo": args.minutos,
        "duracion_min_real": round(duracion_real_min, 1),
        "activaciones_totales": n_despertares,
        "activaciones_intencionales": intencionales,
        "falsos_despertares": falsos_despertares,
        "falsos_despertares_por_hora": round(falsos_despertares / (duracion_real_min / 60), 2) if duracion_real_min > 0 else None,
        "errores_puntuales": n_errores,
        "tasa_exito_pct": round(tasa_exito * 100, 1),
    }

    print("\n" + "=" * 70)
    print("RESUMEN")
    print(json.dumps(resumen, indent=2, ensure_ascii=False))

    fecha = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    salida_json = _LOG_DIR / f"diagnostico_falsos_despertares_{fecha}.json"
    salida_csv = _LOG_DIR / f"diagnostico_falsos_despertares_{fecha}.csv"

    with open(salida_json, "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)

    with open(salida_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "evento"])
        writer.writerows(eventos)

    print(f"\nGuardado en:\n  {salida_json}\n  {salida_csv}")


if __name__ == "__main__":
    main()
