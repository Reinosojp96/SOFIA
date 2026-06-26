"""
Interfaz grafica de SOFIA con PyQt6: ventana sin bordes, fondo
semitransparente, esquinas redondeadas y estetica "futurista" tipo
asistente flotante.

Notas de diseno:
- La ventana es frameless + translucida (WA_TranslucentBackground).
  El panel principal tiene su propio fondo semitransparente con
  border-radius via QSS; la ventana detras queda completamente
  transparente.
- Como no hay barra de titulo, se puede arrastrar la ventana
  haciendo click y arrastrando (mousePressEvent / mouseMoveEvent).
- on_comando / on_hablar_voz se ejecutan en hilos; usan senales
  (pyqtSignal) para volver al hilo principal antes de tocar widgets,
  que es obligatorio en Qt.
"""

import os
import threading
from datetime import datetime

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QFrame, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QTextEdit, QGraphicsDropShadowEffect,
)
from PyQt6.QtGui import QColor

try:
    from skills import clima as _clima
except Exception:
    _clima = None

try:
    from core import memoria as _memoria
except Exception:
    _memoria = None


# Paleta
BG_PANEL = "rgba(15, 18, 32, 200)"
BG_CARD = "rgba(255, 255, 255, 18)"
FG_TEXT = "#e6e8f0"
FG_MUTED = "#8a93ad"
ACCENT = "#7c5cff"
ACCENT_2 = "#4cc9f0"
GREEN = "#3fb950"
AMBER = "#d29922"


class _Senales(QObject):
    """Senales para actualizar la UI desde hilos secundarios."""
    mensaje = pyqtSignal(str, str)
    estado = pyqtSignal(str, str)
    tarjetas = pyqtSignal(object, object, object)
    ventana_activa = pyqtSignal(str, str, str, object)  # app, titulo, resumen, sugerencias


class AleWidget(QWidget):
    def __init__(self, on_comando, on_hablar_voz):
        super().__init__()
        self.on_comando = on_comando
        self.on_hablar_voz = on_hablar_voz

        self.senales = _Senales()
        self.senales.mensaje.connect(self._agregar_mensaje_ui)
        self.senales.estado.connect(self._set_estado_ui)
        self.senales.tarjetas.connect(self._aplicar_tarjetas)
        self.senales.ventana_activa.connect(self._aplicar_ventana_activa)
        self._polling_escritorio = False

        self._drag_pos = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(420, 760)

        self._construir_ui()
        self._actualizar_tarjetas_async()
        self._iniciar_timer_escritorio()

    # ------------------------------------------------------------
    # Construccion de la interfaz
    # ------------------------------------------------------------

    def _construir_ui(self):
        panel = QFrame(self)
        panel.setObjectName("panel")
        panel.setStyleSheet(f"""
            #panel {{
                background-color: {BG_PANEL};
                border-radius: 18px;
                border: 1px solid rgba(255,255,255,25);
            }}
        """)

        sombra = QGraphicsDropShadowEffect()
        sombra.setBlurRadius(30)
        sombra.setColor(QColor(0, 0, 0, 160))
        sombra.setOffset(0, 6)
        panel.setGraphicsEffect(sombra)

        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(14, 14, 14, 14)  # margen para QGraphicsDropShadowEffect
        layout_externo.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self._construir_header(layout)
        self._construir_saludo(layout)
        self._construir_tarjetas(layout)
        self._construir_panel_ventana_activa(layout)
        self._construir_panel_sugerencias(layout)
        self._construir_chat(layout)
        self._construir_barra_inferior(layout)

    def _construir_header(self, layout):
        header = QHBoxLayout()

        titulo = QLabel("●  SOFÍA")
        titulo.setStyleSheet(f"color: {ACCENT}; font-size: 16px; font-weight: 700; background: transparent;")
        header.addWidget(titulo)

        header.addStretch()

        btn_cerrar = QPushButton("✕")
        btn_cerrar.setFixedSize(28, 28)
        btn_cerrar.setStyleSheet(f"""
            QPushButton {{
                color: {FG_MUTED}; background: transparent;
                border: none; font-size: 13px;
            }}
            QPushButton:hover {{ color: {FG_TEXT}; }}
        """)
        btn_cerrar.clicked.connect(self.close)
        header.addWidget(btn_cerrar)

        layout.addLayout(header)

    def _construir_saludo(self, layout):
        nombre = os.environ.get("SOFIA_USER_NAME", "Julián")
        saludo = self._saludo_segun_hora()

        titulo = QLabel(f"{saludo}, {nombre} 👋")
        titulo.setStyleSheet(f"color: {FG_TEXT}; font-size: 18px; font-weight: 700; background: transparent;")
        layout.addWidget(titulo)

        subtitulo = QLabel("¿Qué deseas hacer hoy?")
        subtitulo.setStyleSheet(f"color: {FG_MUTED}; font-size: 11px; background: transparent;")
        layout.addWidget(subtitulo)

        self.estado_label = QLabel("● Lista")
        self.estado_label.setStyleSheet(f"color: {GREEN}; font-size: 11px; font-weight: 600; background: transparent;")
        layout.addWidget(self.estado_label)

    def _construir_tarjetas(self, layout):
        fila = QHBoxLayout()
        fila.setSpacing(10)

        self.card_tareas = self._crear_tarjeta("✅ Tareas pendientes")
        self.card_clima = self._crear_tarjeta("⛅ Clima actual")
        self.card_recordatorios = self._crear_tarjeta("🔔 Recordatorios hoy")

        for card in (self.card_tareas, self.card_clima, self.card_recordatorios):
            fila.addWidget(card["frame"])

        layout.addLayout(fila)

    def _crear_tarjeta(self, titulo_texto):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border-radius: 12px;
            }}
        """)
        v = QVBoxLayout(frame)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(2)

        titulo = QLabel(titulo_texto)
        titulo.setStyleSheet(f"color: {FG_MUTED}; font-size: 9px; background: transparent;")
        v.addWidget(titulo)

        valor = QLabel("—")
        valor.setStyleSheet(f"color: {FG_TEXT}; font-size: 18px; font-weight: 700; background: transparent;")
        v.addWidget(valor)

        sub = QLabel("")
        sub.setStyleSheet(f"color: {FG_MUTED}; font-size: 9px; background: transparent;")
        v.addWidget(sub)

        return {"frame": frame, "valor": valor, "sub": sub}

    def _construir_panel_ventana_activa(self, layout):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border-radius: 12px;
            }}
        """)
        v = QVBoxLayout(frame)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(3)

        cabecera = QLabel("🖥  Ventana Activa")
        cabecera.setStyleSheet(f"color: {FG_MUTED}; font-size: 9px; background: transparent;")
        v.addWidget(cabecera)

        self._lbl_ventana_app = QLabel("—")
        self._lbl_ventana_app.setStyleSheet(
            f"color: {ACCENT_2}; font-size: 12px; font-weight: 700; background: transparent;"
        )
        v.addWidget(self._lbl_ventana_app)

        self._lbl_ventana_resumen = QLabel("Sin información disponible")
        self._lbl_ventana_resumen.setStyleSheet(
            f"color: {FG_MUTED}; font-size: 10px; background: transparent;"
        )
        self._lbl_ventana_resumen.setWordWrap(True)
        v.addWidget(self._lbl_ventana_resumen)

        layout.addWidget(frame)

    def _construir_panel_sugerencias(self, layout):
        self._frame_sugerencias = QFrame()
        self._frame_sugerencias.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border-radius: 12px;
            }}
        """)
        v = QVBoxLayout(self._frame_sugerencias)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)

        self._lbl_sugerencias_titulo = QLabel("💡 Sugerencias")
        self._lbl_sugerencias_titulo.setStyleSheet(
            f"color: {FG_MUTED}; font-size: 9px; background: transparent;"
        )
        v.addWidget(self._lbl_sugerencias_titulo)

        self._fila_sugerencias = QHBoxLayout()
        self._fila_sugerencias.setSpacing(6)
        v.addLayout(self._fila_sugerencias)

        layout.addWidget(self._frame_sugerencias)

    def _construir_chat(self, layout):
        self.area_chat = QTextEdit()
        self.area_chat.setReadOnly(True)
        self.area_chat.setStyleSheet(f"""
            QTextEdit {{
                background-color: rgba(255,255,255,10);
                color: {FG_TEXT};
                border-radius: 12px;
                border: none;
                padding: 10px;
                font-size: 11px;
            }}
        """)
        layout.addWidget(self.area_chat, stretch=1)

    def _construir_barra_inferior(self, layout):
        barra = QHBoxLayout()
        barra.setSpacing(8)

        btn_mic = QPushButton("🎤")
        btn_mic.setFixedSize(38, 38)
        btn_mic.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_CARD};
                border-radius: 19px;
                font-size: 15px;
                color: {ACCENT_2};
                border: none;
            }}
            QPushButton:hover {{ background-color: rgba(255,255,255,35); }}
        """)
        btn_mic.clicked.connect(self._activar_voz)
        barra.addWidget(btn_mic)

        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Escribe o habla...")
        self.entrada.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_CARD};
                color: {FG_TEXT};
                border-radius: 19px;
                padding: 0 14px;
                font-size: 11px;
                border: none;
            }}
        """)
        self.entrada.setFixedHeight(38)
        self.entrada.returnPressed.connect(self._enviar_texto)
        barra.addWidget(self.entrada, stretch=1)

        btn_enviar = QPushButton("Enviar")
        btn_enviar.setFixedHeight(38)
        btn_enviar.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: white;
                border-radius: 19px;
                padding: 0 16px;
                font-size: 11px;
                font-weight: 700;
                border: none;
            }}
            QPushButton:hover {{ background-color: #6a4ce0; }}
        """)
        btn_enviar.clicked.connect(self._enviar_texto)
        barra.addWidget(btn_enviar)

        layout.addLayout(barra)

    # ------------------------------------------------------------
    # Arrastrar ventana sin bordes
    # ------------------------------------------------------------

    def mousePressEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = evento.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evento):
        if self._drag_pos is not None and evento.buttons() == Qt.MouseButton.LeftButton:
            self.move(evento.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, evento):
        self._drag_pos = None

    # ------------------------------------------------------------
    # API publica (llamada desde main.py, posiblemente desde hilos)
    # ------------------------------------------------------------

    def agregar_mensaje(self, autor, texto):
        """Seguro de llamar desde cualquier hilo."""
        self.senales.mensaje.emit(autor, texto)

    def set_estado(self, texto, color=GREEN):
        """Seguro de llamar desde cualquier hilo."""
        self.senales.estado.emit(texto, color)

    def refrescar_tarjetas(self):
        self._actualizar_tarjetas_async()

    # ------------------------------------------------------------
    # Slots (corren en el hilo principal de Qt)
    # ------------------------------------------------------------

    def _agregar_mensaje_ui(self, autor, texto):
        self.area_chat.append(f"<b>{autor}:</b> {texto}")

    def _set_estado_ui(self, texto, color):
        self.estado_label.setText(f"● {texto}")
        self.estado_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600; background: transparent;")

    # ------------------------------------------------------------
    # Eventos internos
    # ------------------------------------------------------------

    def _saludo_segun_hora(self):
        hora = datetime.now().hour
        if hora < 12:
            return "Buenos días"
        if hora < 19:
            return "Buenas tardes"
        return "Buenas noches"

    def _enviar_texto(self):
        texto = self.entrada.text().strip()
        if not texto:
            return
        self.entrada.clear()
        self.agregar_mensaje("Tú", texto)
        self.set_estado("Procesando...", AMBER)

        def trabajo():
            respuesta = self.on_comando(texto)
            self.agregar_mensaje("SOFÍA", respuesta)
            self.set_estado("Lista", GREEN)
            self.refrescar_tarjetas()

        threading.Thread(target=trabajo, daemon=True).start()

    def _activar_voz(self):
        self.set_estado("Escuchando...", ACCENT)

        def trabajo():
            self.on_hablar_voz()
            self.set_estado("Lista", GREEN)
            self.refrescar_tarjetas()

        threading.Thread(target=trabajo, daemon=True).start()

    # ------------------------------------------------------------
    # Ventana activa + sugerencias (timer cada 3s)
    # ------------------------------------------------------------

    def _iniciar_timer_escritorio(self):
        self._timer_escritorio = QTimer(self)
        self._timer_escritorio.timeout.connect(self._poll_ventana_activa_async)
        self._timer_escritorio.start(3000)

    def _poll_ventana_activa_async(self):
        if self._polling_escritorio:
            return
        self._polling_escritorio = True

        def trabajo():
            try:
                from skills.control_escritorio import desktop, obtener_sugerencias
                from core.context_manager import contexto as ctx_global
                info = desktop.obtener_ventana_activa()
                app = info.get("app") or ""
                titulo = info.get("titulo") or ""
                resumen = desktop.leer_contenido_ventana() if app else ""
                sugerencias = obtener_sugerencias(app) if app else []
                ctx_global.actualizar(app, titulo, contenido=resumen)
                self.senales.ventana_activa.emit(app, titulo, resumen, sugerencias)
            except Exception:
                pass
            finally:
                self._polling_escritorio = False

        threading.Thread(target=trabajo, daemon=True).start()

    def _aplicar_ventana_activa(self, app, titulo, resumen, sugerencias):
        nombre_display = app.replace(".exe", "") if app else "—"
        if titulo:
            self._lbl_ventana_app.setText(f"{nombre_display}  ·  {titulo[:40]}")
        else:
            self._lbl_ventana_app.setText(nombre_display or "—")

        self._lbl_ventana_resumen.setText(resumen[:120] if resumen else "Sin información disponible")

        # Actualizar título del panel sugerencias
        self._lbl_sugerencias_titulo.setText(
            f"💡 Sugerencias para {nombre_display}" if nombre_display != "—" else "💡 Sugerencias"
        )

        # Reconstruir botones de sugerencias
        while self._fila_sugerencias.count():
            item = self._fila_sugerencias.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for sug in (sugerencias or [])[:4]:
            btn = QPushButton(sug)
            btn.setFixedHeight(26)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(124, 92, 255, 40);
                    color: {ACCENT_2};
                    border-radius: 13px;
                    padding: 0 10px;
                    font-size: 9px;
                    border: 1px solid rgba(124, 92, 255, 80);
                }}
                QPushButton:hover {{
                    background-color: rgba(124, 92, 255, 100);
                    color: white;
                }}
            """)
            btn.clicked.connect(lambda checked, t=sug: self._inyectar_sugerencia(t))
            self._fila_sugerencias.addWidget(btn)

        self._fila_sugerencias.addStretch()

    def _inyectar_sugerencia(self, texto: str):
        """Pone el texto de la sugerencia en el campo y lo envía."""
        self.entrada.setText(texto)
        self._enviar_texto()

    # ------------------------------------------------------------
    # Tarjetas de resumen
    # ------------------------------------------------------------

    def _actualizar_tarjetas_async(self):
        def trabajo():
            try:
                n_tareas = _memoria.contar_tareas_pendientes() if _memoria else None
            except Exception:
                n_tareas = None

            try:
                n_record = _memoria.contar_eventos_hoy() if _memoria else None
            except Exception:
                n_record = None

            try:
                clima_info = _clima.obtener_resumen() if _clima else None
            except Exception:
                clima_info = None

            self.senales.tarjetas.emit(n_tareas, n_record, clima_info)

        threading.Thread(target=trabajo, daemon=True).start()

    def _aplicar_tarjetas(self, n_tareas, n_record, clima_info):
        self.card_tareas["valor"].setText("--" if n_tareas is None else str(n_tareas))
        self.card_recordatorios["valor"].setText("--" if n_record is None else str(n_record))

        if clima_info and clima_info.get("ok"):
            self.card_clima["valor"].setText(f"{clima_info['temp']}°C")
            self.card_clima["sub"].setText(f"{clima_info['descripcion']} · {clima_info['ciudad']}")
        else:
            mensaje = "Sin conexión"
            if clima_info and clima_info.get("mensaje"):
                mensaje = clima_info["mensaje"]
            self.card_clima["valor"].setText(mensaje)
            self.card_clima["valor"].setStyleSheet(
                f"color: {FG_TEXT}; font-size: 13px; font-weight: 700; background: transparent;"
            )
            self.card_clima["sub"].setText("")


def ejecutar_app(on_comando, on_hablar_voz, post_init=None):
    """
    Helper para main.py: crea la QApplication, la ventana y arranca el
    event loop. post_init(widget) se llama justo despues de crear la
    ventana (para lanzar hilos de fondo, mensajes de bienvenida, etc.)
    """
    app = QApplication([])
    widget = AleWidget(on_comando, on_hablar_voz)

    if post_init:
        post_init(widget)

    widget.show()
    app.exec()