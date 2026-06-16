"""
Reporta cuánto espacio en disco usa SOFÍA realmente.

Recorre data/ (donde deberían vivir todos los modelos tras la corrección
de voz/escuchar.py y setup.py) y muestra un desglose por componente, más
el total. También avisa si quedan residuos en las cachés globales que se
usaban antes de esa corrección (~/.cache/torch, ~/.cache/huggingface), y
reporta el tamaño de venv/ por separado (no es parte de los "datos").

Uso:
    python herramientas/medir_espacio.py
"""

import os
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

_RAIZ = Path(__file__).parent.parent
_DATA = _RAIZ / "data"


def _tamano(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for raiz, _, archivos in os.walk(path):
        for nombre in archivos:
            p = Path(raiz) / nombre
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _fmt(bytes_: int) -> str:
    gb = bytes_ / (1024 ** 3)
    if gb >= 0.1:
        return f"{gb:.2f} GB"
    return f"{bytes_ / (1024 ** 2):.1f} MB"


def _imprimir_tabla(filas):
    ancho = max((len(n) for n, _ in filas), default=10)
    for nombre, tamano in filas:
        print(f"  {nombre:<{ancho}}  {_fmt(tamano):>10}")


def main():
    print("=" * 60)
    print("SOFÍA — Reporte de espacio en disco")
    print("=" * 60)

    componentes = [
        ("modelo.gguf (LLM)", _DATA / "modelo.gguf"),
        ("qwen3_tts/ (TTS CustomVoice)", _DATA / "qwen3_tts"),
        ("qwen3_tts_base/ (TTS Base/clonación)", _DATA / "qwen3_tts_base"),
        ("modelos/whisper/ (STT)", _DATA / "modelos" / "whisper"),
        ("modelos/torch_hub/ (Silero-VAD)", _DATA / "modelos" / "torch_hub"),
        ("audio_estatico/", _DATA / "audio_estatico"),
        ("logs/ (diagnóstico)", _DATA / "logs"),
        ("apps.json", _DATA / "apps.json"),
        ("memoria.json", _DATA / "memoria.json"),
        ("aprendizaje.json", _DATA / "aprendizaje.json"),
        ("voz_referencia.wav", _DATA / "voz_referencia.wav"),
    ]

    filas = [(nombre, _tamano(ruta)) for nombre, ruta in componentes]
    total_data = _tamano(_DATA)

    print("\nContenido de data/:")
    _imprimir_tabla(filas)
    print("  " + "-" * 40)
    print(f"  {'TOTAL data/':<38}  {_fmt(total_data):>10}")

    # venv aparte: es el entorno Python, no "datos" del programa
    venv = _RAIZ / "venv"
    if venv.exists():
        print(f"\nEntorno Python (venv/, no se borra junto con data/): {_fmt(_tamano(venv))}")

    print(f"\nTOTAL SOFÍA (data/ + venv/): {_fmt(total_data + _tamano(venv))}")

    # Residuos en cachés globales (rutas usadas antes de contener los
    # modelos en data/modelos/) — informativo, para que el usuario sepa
    # qué puede borrar manualmente tras actualizar.
    print("\n" + "-" * 60)
    print("Residuos en cachés globales del sistema (rutas antiguas):")
    home = Path.home()
    residuos = []

    hf_cache = home / ".cache" / "huggingface" / "hub"
    if hf_cache.exists():
        for carpeta in hf_cache.glob("models--*whisper*"):
            residuos.append((f"~/.cache/huggingface/hub/{carpeta.name}", _tamano(carpeta)))

    torch_cache = home / ".cache" / "torch" / "hub"
    if torch_cache.exists():
        for carpeta in torch_cache.glob("*silero*"):
            residuos.append((f"~/.cache/torch/hub/{carpeta.name}", _tamano(carpeta)))

    if residuos:
        _imprimir_tabla(residuos)
        print("  (Pueden borrarse manualmente: ya no se usan tras la corrección")
        print("   que contiene Whisper/Silero-VAD dentro de data/modelos/.)")
    else:
        print("  Ninguno encontrado — todo está contenido en data/.")

    print("=" * 60)


if __name__ == "__main__":
    main()
