"""
SOFÍA — Instalador gráfico (wizard)

Punto de entrada para el .exe generado por build_installer.py (PyInstaller
--windowed). Reemplaza la experiencia de consola de instalar_sofia.py por
una ventana con pasos, formularios y barra de progreso.

Dos fases, dos mecanismos de comunicación distintos:

  FASE A (bootstrap): corre embebida en este mismo proceso. Reutiliza las
  funciones de instalar_sofia.py (localizar_python_sistema, detectar_cuda,
  descargar_repo, extraer_repo, crear_venv, instalar_dependencias) pasando
  un adaptador `ui` que en vez de imprimir por consola encola actualizaciones
  para la ventana.

  FASE B (setup del proyecto): corre en un proceso aparte, con el Python
  del venv (setup.py --desde-bootstrap). Esta ventana lo lanza con
  SOFIA_GUI=1 y lee su stdout línea por línea: las líneas "@@ASK@@..."
  son preguntas (ver gui_protocol.py) que se muestran como formulario y
  cuya respuesta se escribe de vuelta a stdin; las líneas "@@PROGRESS@@a/b"
  actualizan la barra de progreso; el resto son líneas de log normales.
"""

import os
import sys
import queue
import threading
import traceback
import subprocess
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import instalar_sofia as boot

IS_WIN = sys.platform == "win32"
APP_DIR = Path(__file__).resolve().parent
LOG_FILE = APP_DIR / "instalador_error.log"


# ─────────────────────────────────────────────
# Adaptador de UI para las funciones de instalar_sofia.py (fase A)
# ─────────────────────────────────────────────
class UiAdapter:
    """Pasado como `ui=` a las funciones de instalar_sofia.py: en vez de
    imprimir, encola eventos que la ventana drena en el hilo principal."""

    def __init__(self, eventos: "queue.Queue"):
        self._eventos = eventos

    def status(self, texto: str):
        self._eventos.put(("status", texto))

    def log(self, mensaje: str, level: str = "info"):
        self._eventos.put(("log", mensaje, level))

    def progress(self, actual: int, total: int):
        self._eventos.put(("progress", actual, total))


# ─────────────────────────────────────────────
# Ventana principal
# ─────────────────────────────────────────────
class InstaladorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SOFÍA — Instalador")
        self.geometry("640x480")
        self.minsize(560, 420)
        self.resizable(True, True)

        self._eventos: "queue.Queue" = queue.Queue()
        self.directorio: Path | None = None
        self.python_sistema: Path | None = None
        self.cuda_tag = "cpu"
        self.venv_python: Path | None = None
        self.venv_pip: Path | None = None
        self.proc_setup: subprocess.Popen | None = None
        self._respuesta_pendiente: "queue.Queue[str]" = queue.Queue()

        self._contenedor = ttk.Frame(self, padding=16)
        self._contenedor.pack(fill="both", expand=True)
        self._pagina_actual: ttk.Frame | None = None

        self._estilo()
        self.mostrar_bienvenida()
        self.after(80, self._drenar_eventos)

    # ── estilo básico ──
    def _estilo(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista" if IS_WIN else "clam")
        except Exception:
            pass
        style.configure("Titulo.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("Sub.TLabel", font=("Segoe UI", 10))

    def _limpiar(self) -> ttk.Frame:
        if self._pagina_actual is not None:
            self._pagina_actual.destroy()
        pagina = ttk.Frame(self._contenedor)
        pagina.pack(fill="both", expand=True)
        self._pagina_actual = pagina
        return pagina

    # ─────────────────────────────────────────────
    # Página 1 — Bienvenida
    # ─────────────────────────────────────────────
    def mostrar_bienvenida(self):
        p = self._limpiar()
        ttk.Label(p, text="Bienvenido al instalador de SOFÍA", style="Titulo.TLabel").pack(
            anchor="w", pady=(0, 8))
        ttk.Label(
            p,
            style="Sub.TLabel",
            wraplength=560,
            justify="left",
            text=("Este asistente instalará SOFÍA, tu asistente de voz personal "
                  "100% local. Se descargará el código, se creará un entorno "
                  "aislado y se descargarán los modelos necesarios.\n\n"
                  "El proceso puede tardar varios minutos dependiendo de tu "
                  "conexión y de si descargas los modelos de IA."),
        ).pack(anchor="w", pady=(0, 24))

        botones = ttk.Frame(p)
        botones.pack(side="bottom", fill="x")
        ttk.Button(botones, text="Comenzar →", command=self.mostrar_directorio).pack(side="right")
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="right", padx=(0, 8))

    # ─────────────────────────────────────────────
    # Página 2 — Directorio de instalación
    # ─────────────────────────────────────────────
    def mostrar_directorio(self):
        p = self._limpiar()
        ttk.Label(p, text="Directorio de instalación", style="Titulo.TLabel").pack(
            anchor="w", pady=(0, 8))
        ttk.Label(
            p, style="Sub.TLabel",
            text="Elige dónde quieres instalar SOFÍA:",
        ).pack(anchor="w", pady=(0, 8))

        fila = ttk.Frame(p)
        fila.pack(fill="x", pady=(0, 16))
        entry_var = tk.StringVar(value=str(boot.DIR_DEFECTO))
        entry = ttk.Entry(fila, textvariable=entry_var)
        entry.pack(side="left", fill="x", expand=True)

        def elegir_carpeta():
            elegida = filedialog.askdirectory(initialdir=entry_var.get() or str(Path.home()))
            if elegida:
                entry_var.set(elegida)

        ttk.Button(fila, text="Elegir...", command=elegir_carpeta).pack(side="left", padx=(8, 0))

        botones = ttk.Frame(p)
        botones.pack(side="bottom", fill="x")

        def continuar():
            destino = Path(entry_var.get().strip() or str(boot.DIR_DEFECTO))
            try:
                destino.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                messagebox.showerror(
                    "Sin permisos",
                    f"No se pudo crear:\n{destino}\n\nIntenta ejecutar como "
                    "administrador o elige otra carpeta.")
                return
            self.directorio = destino
            self.mostrar_preparando()

        ttk.Button(botones, text="Siguiente →", command=continuar).pack(side="right")
        ttk.Button(botones, text="← Atrás", command=self.mostrar_bienvenida).pack(
            side="right", padx=(0, 8))

    # ─────────────────────────────────────────────
    # Página de progreso/log (reutilizada en fase A y B)
    # ─────────────────────────────────────────────
    def _pagina_progreso(self, titulo_texto: str):
        p = self._limpiar()
        ttk.Label(p, text=titulo_texto, style="Titulo.TLabel").pack(anchor="w", pady=(0, 8))

        self._lbl_status = ttk.Label(p, style="Sub.TLabel", text="Iniciando...")
        self._lbl_status.pack(anchor="w", pady=(0, 8))

        self._barra = ttk.Progressbar(p, mode="indeterminate")
        self._barra.pack(fill="x", pady=(0, 12))
        self._barra.start(12)
        self._barra_modo = "indeterminate"

        log_frame = ttk.Frame(p)
        log_frame.pack(fill="both", expand=True)
        self._log_text = tk.Text(log_frame, height=14, wrap="word", state="disabled",
                                  bg="#1e1e1e", fg="#dddddd", insertbackground="#dddddd")
        scroll = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scroll.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._log_text.tag_configure("ok", foreground="#7ee787")
        self._log_text.tag_configure("warn", foreground="#e3b341")
        self._log_text.tag_configure("error", foreground="#ff7b72")
        self._log_text.tag_configure("info", foreground="#79c0ff")
        return p

    def _agregar_log(self, mensaje: str, level: str = "info"):
        self._log_text.configure(state="normal")
        self._log_text.insert("end", mensaje.rstrip() + "\n", level)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _set_status(self, texto: str):
        self._lbl_status.configure(text=texto)

    def _set_progress(self, actual: int, total: int):
        if total <= 0:
            return
        if self._barra_modo != "determinate":
            self._barra.stop()
            self._barra.configure(mode="determinate", maximum=total)
            self._barra_modo = "determinate"
        self._barra["value"] = min(actual, total)

    # ─────────────────────────────────────────────
    # Fase A — bootstrap (mismo proceso, en un hilo de fondo)
    # ─────────────────────────────────────────────
    def mostrar_preparando(self):
        self._pagina_progreso("Preparando la instalación")
        hilo = threading.Thread(target=self._trabajo_fase_a, daemon=True)
        hilo.start()

    def _trabajo_fase_a(self):
        ui = UiAdapter(self._eventos)
        try:
            ui.status("Buscando Python instalado...")
            self.python_sistema = boot.localizar_python_sistema()
            if self.python_sistema is None:
                ui.log(
                    "No se encontró un Python 3.10-3.12 instalado. Instala uno "
                    "desde https://www.python.org/downloads/ (marca 'Add Python "
                    "to PATH') y vuelve a ejecutar el instalador.",
                    level="error",
                )
                self._eventos.put(("fase_a_error",))
                return
            ui.log(f"Python encontrado: {self.python_sistema}")

            ui.status("Detectando hardware (GPU/CUDA)...")
            self.cuda_tag = boot.detectar_cuda()
            if self.cuda_tag != "cpu":
                ui.log(f"GPU NVIDIA detectada → usando {self.cuda_tag}")
            else:
                ui.log("Sin GPU NVIDIA detectada → se usará CPU (más lento)", level="warn")

            zip_temporal = self.directorio / "_sofia_download.zip"
            ui.status("Descargando código de SOFÍA...")
            if not boot.descargar_repo(zip_temporal, ui=ui):
                self._eventos.put(("fase_a_error",))
                return

            ui.status("Extrayendo archivos...")
            if not boot.extraer_repo(zip_temporal, self.directorio, ui=ui):
                self._eventos.put(("fase_a_error",))
                return
            try:
                zip_temporal.unlink()
            except Exception:
                pass

            ui.status("Creando entorno virtual...")
            self.venv_python, self.venv_pip = boot.crear_venv(
                self.directorio, self.python_sistema, ui=ui)

            ui.status("Instalando dependencias base (puede tardar varios minutos)...")
            boot.instalar_dependencias(self.venv_pip, self.venv_python, self.cuda_tag, ui=ui)

            self._eventos.put(("fase_a_ok",))
        except Exception:
            ui.log(traceback.format_exc(), level="error")
            self._eventos.put(("fase_a_error",))

    # ─────────────────────────────────────────────
    # Fase B — setup.py del proyecto (subproceso con protocolo)
    # ─────────────────────────────────────────────
    def _iniciar_fase_b(self):
        self._pagina_progreso("Configurando SOFÍA")
        hilo = threading.Thread(target=self._trabajo_fase_b, daemon=True)
        hilo.start()

    def _trabajo_fase_b(self):
        setup_path = self.directorio / "setup.py"
        if not setup_path.exists():
            self._eventos.put(("log", "No se encontró setup.py — el repositorio "
                                       "puede estar incompleto.", "error"))
            self._eventos.put(("fase_b_fin", 1))
            return

        creationflags = subprocess.CREATE_NO_WINDOW if IS_WIN else 0
        try:
            self.proc_setup = subprocess.Popen(
                [str(self.venv_python), str(setup_path), "--desde-bootstrap"],
                cwd=str(self.directorio),
                env={**os.environ, "SOFIA_GUI": "1", "PYTHONUNBUFFERED": "1",
                     "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                     "PYTHONPATH": str(self.directorio)},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True, bufsize=1, encoding="utf-8", errors="replace",
                creationflags=creationflags,
            )
        except Exception as e:
            self._eventos.put(("log", f"No se pudo iniciar setup.py: {e}", "error"))
            self._eventos.put(("fase_b_fin", 1))
            return

        for linea in self.proc_setup.stdout:
            linea = linea.rstrip("\n")
            if linea.startswith("@@ASK@@"):
                self._eventos.put(("ask", linea[len("@@ASK@@"):]))
                respuesta = self._respuesta_pendiente.get()  # bloquea este hilo, no la GUI
                try:
                    self.proc_setup.stdin.write(respuesta + "\n")
                    self.proc_setup.stdin.flush()
                except Exception:
                    pass
            elif linea.startswith("@@PROGRESS@@"):
                try:
                    actual_s, total_s = linea[len("@@PROGRESS@@"):].split("/", 1)
                    self._eventos.put(("progress", int(actual_s), int(total_s)))
                except Exception:
                    pass
            elif linea.strip():
                nivel = "info"
                if "✗" in linea or "ERROR" in linea.upper():
                    nivel = "error"
                elif "⚠" in linea:
                    nivel = "warn"
                elif "✓" in linea:
                    nivel = "ok"
                self._eventos.put(("log", linea, nivel))

        codigo = self.proc_setup.wait()
        self._eventos.put(("fase_b_fin", codigo))

    # ─────────────────────────────────────────────
    # Página de pregunta dinámica (fase B)
    # ─────────────────────────────────────────────
    def _mostrar_pregunta(self, prompt: str):
        p = self._limpiar()
        ttk.Label(p, text="SOFÍA necesita una respuesta", style="Titulo.TLabel").pack(
            anchor="w", pady=(0, 12))
        ttk.Label(p, style="Sub.TLabel", wraplength=560, justify="left", text=prompt).pack(
            anchor="w", pady=(0, 12))

        entry_var = tk.StringVar()
        entry = ttk.Entry(p, textvariable=entry_var, width=60)
        entry.pack(anchor="w", fill="x", pady=(0, 16))
        entry.focus_set()

        def enviar(_evento=None):
            self._respuesta_pendiente.put(entry_var.get())
            self.mostrar_progreso_fase_b()

        entry.bind("<Return>", enviar)

        botones = ttk.Frame(p)
        botones.pack(side="bottom", fill="x")
        ttk.Button(botones, text="Continuar →", command=enviar).pack(side="right")

    def mostrar_progreso_fase_b(self):
        self._pagina_progreso("Configurando SOFÍA")

    # ─────────────────────────────────────────────
    # Página final
    # ─────────────────────────────────────────────
    def _mostrar_final(self, exito: bool):
        p = self._limpiar()
        if exito:
            ttk.Label(p, text="¡SOFÍA instalada correctamente!", style="Titulo.TLabel").pack(
                anchor="w", pady=(0, 12))
            ttk.Label(
                p, style="Sub.TLabel", wraplength=560, justify="left",
                text=f"Instalada en: {self.directorio}\n\n"
                     "Puedes iniciar SOFÍA ahora o más tarde haciendo doble clic "
                     "en 'iniciar_sofia.bat'.",
            ).pack(anchor="w", pady=(0, 24))

            def iniciar():
                bat = self.directorio / "iniciar_sofia.bat"
                try:
                    os.startfile(str(bat))
                except Exception as e:
                    messagebox.showerror("Error", f"No se pudo iniciar SOFÍA: {e}")
                self.destroy()

            botones = ttk.Frame(p)
            botones.pack(side="bottom", fill="x")
            ttk.Button(botones, text="Iniciar SOFÍA", command=iniciar).pack(side="right")
            ttk.Button(botones, text="Cerrar", command=self.destroy).pack(side="right", padx=(0, 8))
        else:
            ttk.Label(p, text="La instalación no terminó correctamente",
                      style="Titulo.TLabel").pack(anchor="w", pady=(0, 12))
            ttk.Label(
                p, style="Sub.TLabel", wraplength=560, justify="left",
                text="Revisa el detalle abajo. Puedes cerrar esta ventana y volver "
                     "a intentarlo.",
            ).pack(anchor="w", pady=(0, 8))

            texto = tk.Text(p, height=14, wrap="word", bg="#1e1e1e", fg="#ff7b72")
            texto.insert("end", "\n".join(self._ultimas_lineas))
            texto.configure(state="disabled")
            texto.pack(fill="both", expand=True, pady=(0, 12))

            ttk.Button(p, text="Cerrar", command=self.destroy).pack(side="bottom", anchor="e")

    # ─────────────────────────────────────────────
    # Bucle de drenado de eventos (hilo principal de Tk)
    # ─────────────────────────────────────────────
    def _drenar_eventos(self):
        self._ultimas_lineas = getattr(self, "_ultimas_lineas", [])
        try:
            while True:
                evento = self._eventos.get_nowait()
                tipo = evento[0]

                if tipo == "status" and hasattr(self, "_lbl_status"):
                    self._set_status(evento[1])
                elif tipo == "log" and hasattr(self, "_log_text"):
                    self._agregar_log(evento[1], evento[2])
                    self._ultimas_lineas.append(evento[1])
                    self._ultimas_lineas = self._ultimas_lineas[-200:]
                elif tipo == "progress" and hasattr(self, "_barra"):
                    self._set_progress(evento[1], evento[2])
                elif tipo == "fase_a_ok":
                    self._iniciar_fase_b()
                elif tipo == "fase_a_error":
                    self._mostrar_final(exito=False)
                elif tipo == "ask":
                    self._mostrar_pregunta(evento[1])
                elif tipo == "fase_b_fin":
                    self._mostrar_final(exito=(evento[1] == 0))
        except queue.Empty:
            pass
        self.after(80, self._drenar_eventos)


def main():
    app = InstaladorApp()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        try:
            LOG_FILE.write_text(tb, encoding="utf-8")
        except Exception:
            pass
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Error inesperado", tb[-1500:])
        except Exception:
            pass
        sys.exit(1)
