"""
Protocolo mínimo de comunicación entre setup.py/paso_voz.py (que corren
con el Python del venv, en un proceso aparte) y installer_gui.py (la
ventana del instalador).

Cuando SOFIA_GUI=1 está en el entorno, `pedir()` sustituye a input():
en vez de bloquear esperando texto en una terminal (que no existe, porque
el instalador corre con --windowed), emite un marcador por stdout y lee
la respuesta de stdin, que installer_gui.py escribe tras mostrar un
formulario al usuario.

Sin SOFIA_GUI=1 (ejecución normal por consola) todo se comporta exactamente
como input()/print() de siempre.
"""

import os
import sys

GUI_MODE = os.environ.get("SOFIA_GUI") == "1"


def pedir(prompt: str = "") -> str:
    if GUI_MODE:
        # El protocolo manda una línea por mensaje: cualquier salto de
        # línea incrustado en el prompt (común en los input() del setup,
        # ej. "\n  ¿Cómo te llamas?...") rompe el parseo en la GUI, así
        # que se colapsa a espacios antes de enviarlo.
        prompt_plano = " ".join(prompt.splitlines()).strip()
        sys.stdout.write(f"@@ASK@@{prompt_plano}\n")
        sys.stdout.flush()
        return sys.stdin.readline().rstrip("\n")
    return input(prompt)


def progreso(actual: int, total: int):
    if GUI_MODE:
        print(f"@@PROGRESS@@{actual}/{total}", flush=True)


def crear_tqdm_gui():
    """Clase tqdm que reporta progreso real al protocolo de la GUI en vez
    de dibujar una barra ASCII. Pensada para pasarla como `tqdm_class=`
    a huggingface_hub.snapshot_download/hf_hub_download, que sí conocen
    el tamaño total del archivo (a diferencia de Whisper/Silero-VAD, que
    no expone esa información y solo recibe el "latido" del Spinner)."""
    import os
    from tqdm.auto import tqdm as _tqdm

    class _GuiTqdm(_tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["file"] = open(os.devnull, "w")
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            resultado = super().update(n)
            if self.total:
                progreso(self.n, self.total)
            return resultado

    return _GuiTqdm
