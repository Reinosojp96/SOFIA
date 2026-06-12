"""
Interfaz grafica de SOFIA con Tkinter.

- Caja de texto para escribir comandos (siempre funciona, sin microfono).
- Boton "Hablar" para activar el microfono una vez.
- Area de conversacion con el historial.
- Estado visual (Escuchando / Procesando / Listo).
"""

import tkinter as tk
from tkinter import scrolledtext
import threading


class AleWidget(tk.Tk):
    def __init__(self, on_comando, on_hablar_voz):
        """
        on_comando: funcion(texto) -> str  (procesa un comando de texto)
        on_hablar_voz: funcion() -> None   (activa el microfono en un hilo aparte)
        """
        super().__init__()
        self.on_comando = on_comando
        self.on_hablar_voz = on_hablar_voz

        self.title("SOFÍA")
        self.geometry("440x580")
        self.configure(bg="#0d1117")
        self.resizable(False, False)

        self._construir_ui()

    def _construir_ui(self):
        # Encabezado
        header = tk.Frame(self, bg="#0d1117")
        header.pack(fill="x", padx=16, pady=(16, 8))

        # Logo / nombre
        tk.Label(
            header, text="SOFÍA", fg="#c084fc", bg="#0d1117",
            font=("Segoe UI", 20, "bold")
        ).pack(side="left")

        tk.Label(
            header, text="IA de voz", fg="#6e7681", bg="#0d1117",
            font=("Segoe UI", 9)
        ).pack(side="left", padx=(8, 0), pady=(6, 0))

        self.estado_var = tk.StringVar(value="Lista")
        self.estado_label = tk.Label(
            header, textvariable=self.estado_var,
            fg="#3fb950", bg="#0d1117", font=("Segoe UI", 10)
        )
        self.estado_label.pack(side="right")

        # Area de conversacion
        self.area_chat = scrolledtext.ScrolledText(
            self, bg="#161b22", fg="#c9d1d9",
            insertbackground="#c9d1d9",
            font=("Segoe UI", 10), wrap="word",
            relief="flat", padx=10, pady=10
        )
        self.area_chat.pack(fill="both", expand=True, padx=16, pady=8)
        self.area_chat.configure(state="disabled")

        # Barra inferior: entrada de texto + botones
        barra = tk.Frame(self, bg="#0d1117")
        barra.pack(fill="x", padx=16, pady=(0, 16))

        self.entrada = tk.Entry(
            barra, bg="#161b22", fg="#c9d1d9",
            insertbackground="#c9d1d9", font=("Segoe UI", 11),
            relief="flat"
        )
        self.entrada.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.entrada.bind("<Return>", self._enviar_texto)

        btn_enviar = tk.Button(
            barra, text="Enviar", command=self._enviar_texto,
            bg="#238636", fg="white", relief="flat", font=("Segoe UI", 10, "bold")
        )
        btn_enviar.pack(side="left", padx=(0, 8))

        btn_hablar = tk.Button(
            barra, text="🎤 Hablar", command=self._activar_voz,
            bg="#7c3aed", fg="white", relief="flat", font=("Segoe UI", 10, "bold")
        )
        btn_hablar.pack(side="left")

        self.agregar_mensaje("SOFÍA", "Hola, soy Sofía. Escribe un comando o presiona Hablar.")

    # ---------- API publica ----------

    def agregar_mensaje(self, autor, texto):
        self.area_chat.configure(state="normal")
        self.area_chat.insert("end", f"{autor}: {texto}\n\n")
        self.area_chat.see("end")
        self.area_chat.configure(state="disabled")

    def set_estado(self, texto, color="#3fb950"):
        self.estado_var.set(texto)
        self.estado_label.configure(fg=color)

    # ---------- Eventos internos ----------

    def _enviar_texto(self, _evento=None):
        texto = self.entrada.get().strip()
        if not texto:
            return
        self.entrada.delete(0, "end")
        self.agregar_mensaje("Tú", texto)
        self.set_estado("Procesando...", "#d29922")

        def trabajo():
            respuesta = self.on_comando(texto)
            self.after(0, lambda: self._mostrar_respuesta(respuesta))

        threading.Thread(target=trabajo, daemon=True).start()

    def _mostrar_respuesta(self, respuesta):
        self.agregar_mensaje("SOFÍA", respuesta)
        self.set_estado("Lista", "#3fb950")

    def _activar_voz(self):
        self.set_estado("Escuchando...", "#7c3aed")

        def trabajo():
            self.on_hablar_voz()
            self.after(0, lambda: self.set_estado("Lista", "#3fb950"))

        threading.Thread(target=trabajo, daemon=True).start()
