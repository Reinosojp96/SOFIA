"""
Skill de control de escritorio — V1.

Arquitectura:
  voz → router (intent) → DesktopController → pywinauto / psutil / Windows

Prioridad de acción:
  1. pywinauto  (accesibilidad UIA — lo más robusto)
  2. Atajos de teclado estándar
  3. subprocess / os.startfile
  (OCR y pyautogui quedan para versiones futuras)

El ContextManager (core/context_manager.py) guarda qué app/ventana
estaba activa para resolver referencias implícitas ("ciérrala", etc.).
"""

import re
import subprocess
import sys

import psutil

from core.context_manager import contexto

# ---------------------------------------------------------------------------
# Palabras clave que activan esta skill
# ---------------------------------------------------------------------------
KEYWORDS = [
    "ventana", "aplicacion", "aplicación",
    "minimizar", "minimiza", "maximizar", "maximiza",
    "cerrar ventana", "cierra ventana",
    "cambiar ventana", "cambiar de ventana", "siguiente ventana",
    "app activa", "que app", "qué app", "qué tienes abierto",
    "guardar", "deshacer", "rehacer", "copiar todo", "seleccionar todo",
    "nueva pestaña", "cerrar pestaña", "siguiente pestaña",
    "subir volumen", "bajar volumen", "silenciar",
    "siguiente cancion", "siguiente canción", "anterior cancion", "anterior canción",
    "pausa", "reproducir", "pausar",
    "escritorio", "mostrar escritorio",
    "que hay abierto", "qué hay abierto", "apps abiertas",
]

# ---------------------------------------------------------------------------
# DesktopController
# ---------------------------------------------------------------------------

class DesktopController:
    """
    Capa de ejecución determinista.
    Recibe un intent (string) y lo traduce a acciones concretas
    usando pywinauto para ventanas específicas, o atajos de teclado
    como fallback universal.
    """

    def __init__(self):
        self._pywinauto_ok = self._check_pywinauto()

    @staticmethod
    def _check_pywinauto() -> bool:
        try:
            import pywinauto  # noqa: F401
            return True
        except ImportError:
            return False

    # ── Lectura de contenido ───────────────────────────────────────────────

    def leer_contenido_ventana(self) -> str:
        """
        Devuelve resumen del contenido visible de la ventana activa.
        Prioridad: extractor específico por app → árbol UIA genérico → vacío.
        """
        info = self.obtener_ventana_activa()
        proceso = (info.get("app") or "").lower().replace(".exe", "")
        pid = info.get("pid")
        if not pid:
            return ""

        extractor = self._extractor_para(proceso)
        if extractor:
            try:
                return extractor(pid) or ""
            except Exception:
                pass

        # Fallback genérico: árbol UIA nivel 2
        return self._leer_uia_generico(pid)

    def _extractor_para(self, proceso: str):
        """Devuelve la función extractora específica o None."""
        mapa = {
            "whatsapp":   self._leer_whatsapp,
            "telegram":   self._leer_telegram,
            "chrome":     self._leer_navegador,
            "msedge":     self._leer_navegador,
            "firefox":    self._leer_navegador,
            "notepad":    self._leer_notepad,
            "notepad++":  self._leer_notepad,
            "explorer":   self._leer_explorer,
            "winword":    self._leer_titulo_ventana,
            "excel":      self._leer_titulo_ventana,
            "spotify":    self._leer_titulo_ventana,
            "code":       self._leer_titulo_ventana,
        }
        for clave, func in mapa.items():
            if clave in proceso:
                return func
        return None

    def _app_por_pid(self, pid: int):
        if not self._pywinauto_ok:
            return None
        try:
            from pywinauto import Application
            return Application(backend="uia").connect(process=pid)
        except Exception:
            return None

    def _leer_whatsapp(self, pid: int) -> str:
        app = self._app_por_pid(pid)
        if not app:
            return ""
        try:
            win = app.top_window()
            # Buscar lista de conversaciones con badges de no leídos
            chats_nuevos = []
            for elem in win.descendants(control_type="ListItem"):
                try:
                    texto = elem.window_text().strip()
                    if texto:
                        chats_nuevos.append(texto)
                except Exception:
                    continue
            if chats_nuevos:
                muestra = chats_nuevos[:5]
                return f"{len(chats_nuevos)} conversaciones visibles: {', '.join(muestra)}"
        except Exception:
            pass
        return ""

    def _leer_telegram(self, pid: int) -> str:
        app = self._app_por_pid(pid)
        if not app:
            return ""
        try:
            win = app.top_window()
            items = []
            for elem in win.descendants(control_type="ListItem"):
                try:
                    t = elem.window_text().strip()
                    if t:
                        items.append(t)
                except Exception:
                    continue
            if items:
                return f"Chats visibles: {', '.join(items[:5])}"
        except Exception:
            pass
        return ""

    def _leer_navegador(self, pid: int) -> str:
        info = self.obtener_ventana_activa()
        titulo = info.get("titulo", "")
        if not self._pywinauto_ok:
            return titulo
        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(process=pid)
            win = app.top_window()
            # Intentar leer barra de direcciones
            for elem in win.descendants(control_type="Edit"):
                try:
                    val = elem.get_value()
                    if val and ("http" in val or "." in val):
                        return f"Página: {val} — {titulo}"
                except Exception:
                    continue
        except Exception:
            pass
        return f"Título: {titulo}" if titulo else ""

    def _leer_notepad(self, pid: int) -> str:
        if not self._pywinauto_ok:
            return ""
        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(process=pid)
            win = app.top_window()
            for elem in win.descendants(control_type="Document"):
                try:
                    texto = elem.window_text()
                    if texto:
                        return texto[:300] + ("…" if len(texto) > 300 else "")
                except Exception:
                    continue
            # fallback Edit control
            for elem in win.descendants(control_type="Edit"):
                try:
                    texto = elem.window_text()
                    if texto:
                        return texto[:300] + ("…" if len(texto) > 300 else "")
                except Exception:
                    continue
        except Exception:
            pass
        return ""

    def _leer_explorer(self, pid: int) -> str:
        if not self._pywinauto_ok:
            return ""
        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(process=pid)
            win = app.top_window()
            for elem in win.descendants(control_type="Edit"):
                try:
                    val = elem.get_value()
                    if val and "\\" in val:
                        return f"Carpeta: {val}"
                except Exception:
                    continue
        except Exception:
            pass
        return ""

    def _leer_titulo_ventana(self, pid: int) -> str:
        info = self.obtener_ventana_activa()
        return info.get("titulo", "")

    def _leer_uia_generico(self, pid: int) -> str:
        if not self._pywinauto_ok:
            return ""
        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(process=pid)
            win = app.top_window()
            textos = []
            for hijo in win.children():
                try:
                    t = hijo.window_text().strip()
                    if t and len(t) > 2:
                        textos.append(t)
                except Exception:
                    continue
            resultado = " · ".join(textos[:8])
            return resultado[:300] if resultado else ""
        except Exception:
            return ""

    # ── Introspección ──────────────────────────────────────────────────────

    def obtener_ventana_activa(self) -> dict:
        """
        Devuelve {app, titulo, pid} de la ventana en primer plano.
        Usa pywinauto si está disponible; si no, ctypes como fallback.
        """
        if self._pywinauto_ok:
            try:
                from pywinauto import Desktop
                win = Desktop(backend="uia").get_active()
                pid = win.process_id()
                nombre_proc = psutil.Process(pid).name() if pid else "desconocido"
                titulo = win.window_text()
                return {"app": nombre_proc, "titulo": titulo, "pid": pid}
            except Exception:
                pass

        # Fallback: ctypes puro (solo Windows)
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            titulo = buf.value or ""
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            nombre_proc = psutil.Process(pid.value).name() if pid.value else "desconocido"
            return {"app": nombre_proc, "titulo": titulo, "pid": pid.value}
        except Exception as e:
            return {"app": None, "titulo": None, "pid": None, "error": str(e)}

    def listar_ventanas_abiertas(self) -> list[str]:
        """Devuelve una lista de títulos de ventanas visibles no vacías."""
        if self._pywinauto_ok:
            try:
                from pywinauto import Desktop
                wins = Desktop(backend="uia").windows()
                titulos = [w.window_text() for w in wins if w.window_text().strip()]
                return titulos
            except Exception:
                pass

        # Fallback: psutil (solo nombre de procesos, sin título)
        nombres = set()
        for proc in psutil.process_iter(["name"]):
            try:
                nombres.add(proc.info["name"])
            except Exception:
                pass
        return sorted(nombres)

    # ── Acciones sobre ventana activa ──────────────────────────────────────

    def minimizar(self) -> bool:
        return self._accion_ventana("minimize")

    def maximizar(self) -> bool:
        return self._accion_ventana("maximize")

    def restaurar(self) -> bool:
        return self._accion_ventana("restore")

    def cerrar_ventana_activa(self) -> bool:
        return self._accion_ventana("close")

    def _accion_ventana(self, accion: str) -> bool:
        if self._pywinauto_ok:
            try:
                from pywinauto import Desktop
                win = Desktop(backend="uia").get_active()
                getattr(win, accion)()
                return True
            except Exception:
                pass

        # Fallback: atajos de teclado
        import ctypes
        import ctypes.wintypes
        VK = {"minimize": 0x5B, "close": None}  # Win+D no aplica; usamos SendInput
        atajos_fallback = {
            "minimize": ("win", "down"),
            "maximize": ("win", "up"),
            "cerrar":   ("alt", "F4"),
            "close":    ("alt", "F4"),
        }
        atajo = atajos_fallback.get(accion)
        if atajo:
            return self._enviar_atajo(*atajo)
        return False

    # ── Atajos de teclado ──────────────────────────────────────────────────

    def _enviar_atajo(self, *teclas: str) -> bool:
        """
        Envía una combinación de teclas usando SendInput (ctypes) para
        evitar dependencia de pyautogui en el camino principal.
        Acepta nombres como 'ctrl', 'alt', 'shift', 'win', 'F4', 'a', etc.
        """
        try:
            import ctypes
            import ctypes.wintypes

            INPUT_KEYBOARD = 1
            KEYEVENTF_KEYUP = 0x0002
            KEYEVENTF_EXTENDEDKEY = 0x0001

            VK_MAP = {
                "ctrl": 0x11, "control": 0x11,
                "alt": 0x12, "shift": 0x10,
                "win": 0x5B,
                "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
                "enter": 0x0D, "return": 0x0D,
                "space": 0x20, "spacebar": 0x20,
                "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
                "home": 0x24, "end": 0x23,
                "delete": 0x2E, "del": 0x2E,
                "backspace": 0x08,
                "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
                "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
                "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
            }

            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", ctypes.wintypes.WORD),
                    ("wScan", ctypes.wintypes.WORD),
                    ("dwFlags", ctypes.wintypes.DWORD),
                    ("time", ctypes.wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
                ]

            class INPUT(ctypes.Structure):
                class _INPUT(ctypes.Union):
                    _fields_ = [("ki", KEYBDINPUT)]
                _anonymous_ = ("_input",)
                _fields_ = [("type", ctypes.wintypes.DWORD), ("_input", _INPUT)]

            def vk(t: str) -> int:
                t_lower = t.lower()
                if t_lower in VK_MAP:
                    return VK_MAP[t_lower]
                if len(t) == 1:
                    return ctypes.windll.user32.VkKeyScanW(ord(t)) & 0xFF
                return 0

            inputs = []
            vks = [vk(t) for t in teclas]
            # key down para todas
            for k in vks:
                i = INPUT(type=INPUT_KEYBOARD)
                i.ki.wVk = k
                inputs.append(i)
            # key up en orden inverso
            for k in reversed(vks):
                i = INPUT(type=INPUT_KEYBOARD)
                i.ki.wVk = k
                i.ki.dwFlags = KEYEVENTF_KEYUP
                inputs.append(i)

            arr = (INPUT * len(inputs))(*inputs)
            ctypes.windll.user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
            return True
        except Exception:
            return False

    # ── Atajos semánticos ──────────────────────────────────────────────────

    def guardar(self) -> bool:
        return self._enviar_atajo("ctrl", "s")

    def deshacer(self) -> bool:
        return self._enviar_atajo("ctrl", "z")

    def rehacer(self) -> bool:
        return self._enviar_atajo("ctrl", "y")

    def copiar_todo(self) -> bool:
        return self._enviar_atajo("ctrl", "a") and self._enviar_atajo("ctrl", "c")

    def seleccionar_todo(self) -> bool:
        return self._enviar_atajo("ctrl", "a")

    def nueva_pestana(self) -> bool:
        return self._enviar_atajo("ctrl", "t")

    def cerrar_pestana(self) -> bool:
        return self._enviar_atajo("ctrl", "w")

    def siguiente_pestana(self) -> bool:
        return self._enviar_atajo("ctrl", "tab")

    def mostrar_escritorio(self) -> bool:
        return self._enviar_atajo("win", "d")

    def cambiar_ventana(self) -> bool:
        return self._enviar_atajo("alt", "tab")

    # ── Media ──────────────────────────────────────────────────────────────

    def subir_volumen(self) -> bool:
        # VK_VOLUME_UP = 0xAF
        return self._enviar_atajo_vk(0xAF)

    def bajar_volumen(self) -> bool:
        return self._enviar_atajo_vk(0xAE)

    def silenciar(self) -> bool:
        return self._enviar_atajo_vk(0xAD)

    def siguiente_cancion(self) -> bool:
        return self._enviar_atajo_vk(0xB0)

    def anterior_cancion(self) -> bool:
        return self._enviar_atajo_vk(0xB1)

    def play_pause(self) -> bool:
        return self._enviar_atajo_vk(0xB3)

    def _enviar_atajo_vk(self, vk_code: int) -> bool:
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)
            return True
        except Exception:
            return False


# Instancia global reutilizable
desktop = DesktopController()

# ---------------------------------------------------------------------------
# Sugerencias por app
# ---------------------------------------------------------------------------

_SUGERENCIAS_POR_APP: dict[str, list[str]] = {
    "whatsapp":  ["lee mis mensajes", "responde el último mensaje", "¿qué dice el último mensaje?"],
    "telegram":  ["lee mis mensajes", "responde el último mensaje"],
    "chrome":    ["dime qué página tengo abierta", "nueva pestaña", "cierra la pestaña"],
    "msedge":    ["dime qué página tengo abierta", "nueva pestaña", "cierra la pestaña"],
    "firefox":   ["dime qué página tengo abierta", "nueva pestaña", "cierra la pestaña"],
    "notepad":   ["lee el texto", "guarda el archivo"],
    "winword":   ["guarda el documento", "lee lo que escribí"],
    "excel":     ["guarda el archivo", "dime qué hoja tengo abierta"],
    "explorer":  ["dime qué carpeta tengo abierta"],
    "spotify":   ["siguiente canción", "pausa", "sube el volumen", "baja el volumen"],
    "code":      ["guarda el archivo", "dime qué archivo tengo abierto"],
    "discord":   ["lee mis mensajes", "¿qué dice el último mensaje?"],
}

_SUGERENCIAS_GENERICAS = ["minimiza esta ventana", "cierra esta ventana", "guarda"]


def obtener_sugerencias(proceso: str) -> list[str]:
    """Devuelve lista de sugerencias de voz para la app indicada."""
    proceso_limpio = proceso.lower().replace(".exe", "")
    for clave, sugs in _SUGERENCIAS_POR_APP.items():
        if clave in proceso_limpio:
            return sugs
    return _SUGERENCIAS_GENERICAS

# ---------------------------------------------------------------------------
# Tabla de intents → acción
# Separa "el qué" (intent) del "el cómo" (controlador).
# El router/IA produce el intent; esta tabla decide la ejecución.
# ---------------------------------------------------------------------------

_INTENT_MAP: dict[str, tuple[callable, str]] = {
    # (funcion, mensaje_ok)
    "minimizar":        (desktop.minimizar,           "Ventana minimizada."),
    "maximizar":        (desktop.maximizar,            "Ventana maximizada."),
    "restaurar":        (desktop.restaurar,            "Ventana restaurada."),
    "cerrar_ventana":   (desktop.cerrar_ventana_activa,"Ventana cerrada."),
    "cambiar_ventana":  (desktop.cambiar_ventana,      "Cambiando de ventana."),
    "mostrar_escritorio": (desktop.mostrar_escritorio, "Mostrando escritorio."),
    "guardar":          (desktop.guardar,              "Guardando."),
    "deshacer":         (desktop.deshacer,             "Deshecho."),
    "rehacer":          (desktop.rehacer,              "Rehecho."),
    "seleccionar_todo": (desktop.seleccionar_todo,     "Todo seleccionado."),
    "copiar_todo":      (desktop.copiar_todo,          "Copiado todo."),
    "nueva_pestana":    (desktop.nueva_pestana,        "Nueva pestaña abierta."),
    "cerrar_pestana":   (desktop.cerrar_pestana,       "Pestaña cerrada."),
    "siguiente_pestana":(desktop.siguiente_pestana,    "Siguiente pestaña."),
    "subir_volumen":    (desktop.subir_volumen,        "Volumen subido."),
    "bajar_volumen":    (desktop.bajar_volumen,        "Volumen bajado."),
    "silenciar":        (desktop.silenciar,            "Audio silenciado."),
    "siguiente_cancion":(desktop.siguiente_cancion,    "Siguiente canción."),
    "anterior_cancion": (desktop.anterior_cancion,     "Canción anterior."),
    "play_pause":       (desktop.play_pause,           "Reproducción pausada/reanudada."),
}

# ---------------------------------------------------------------------------
# Clasificador de intent por keywords
# La IA conversacional puede reemplazar esto devolviendo el intent directamente.
# ---------------------------------------------------------------------------

_KEYWORD_TO_INTENT: list[tuple[list[str], str]] = [
    (["minimizar", "minimiza"],                              "minimizar"),
    (["maximizar", "maximiza"],                              "maximizar"),
    (["restaurar", "restaura"],                              "restaurar"),
    (["cerrar ventana", "cierra ventana"],                   "cerrar_ventana"),
    (["cambiar ventana", "cambiar de ventana", "siguiente ventana", "alt tab"], "cambiar_ventana"),
    (["escritorio", "mostrar escritorio"],                   "mostrar_escritorio"),
    (["guardar"],                                            "guardar"),
    (["deshacer"],                                           "deshacer"),
    (["rehacer"],                                            "rehacer"),
    (["seleccionar todo", "selecciona todo"],                "seleccionar_todo"),
    (["copiar todo", "copia todo"],                         "copiar_todo"),
    (["nueva pestaña", "nueva pestana", "abrir pestaña"],   "nueva_pestana"),
    (["cerrar pestaña", "cerrar pestana"],                  "cerrar_pestana"),
    (["siguiente pestaña", "siguiente pestana"],             "siguiente_pestana"),
    (["subir volumen", "sube el volumen", "mas volumen"],   "subir_volumen"),
    (["bajar volumen", "baja el volumen", "menos volumen"], "bajar_volumen"),
    (["silenciar", "silencia", "mute"],                     "silenciar"),
    (["siguiente cancion", "siguiente canción", "next"],    "siguiente_cancion"),
    (["anterior cancion", "anterior canción", "prev"],      "anterior_cancion"),
    (["pausa", "pausar", "play", "reproducir", "reanudar"], "play_pause"),
]


def _clasificar_intent(texto: str) -> str | None:
    for keywords, intent in _KEYWORD_TO_INTENT:
        if any(kw in texto for kw in keywords):
            return intent
    return None


# ---------------------------------------------------------------------------
# Punto de entrada de la skill
# ---------------------------------------------------------------------------

def manejar(texto: str) -> str:
    # Consultas de estado (sin ejecutar acción)
    if any(p in texto for p in ["que app", "qué app", "app activa", "que hay abierto",
                                  "qué hay abierto", "apps abiertas"]):
        info = desktop.obtener_ventana_activa()
        if info.get("app"):
            contexto.actualizar(info["app"], info.get("titulo", ""))
            return f"App activa: {info['app']} — {info.get('titulo', 'sin título')}."
        return "No pude detectar la ventana activa."

    if "apps abiertas" in texto or "que hay abierto" in texto:
        ventanas = desktop.listar_ventanas_abiertas()
        if ventanas:
            return "Ventanas abiertas: " + ", ".join(ventanas[:10]) + "."
        return "No pude listar las ventanas abiertas."

    # Actualizar contexto antes de ejecutar
    info = desktop.obtener_ventana_activa()
    if info.get("app"):
        contexto.actualizar(info["app"], info.get("titulo", ""))

    # Clasificar intent y ejecutar
    intent = _clasificar_intent(texto)
    if intent and intent in _INTENT_MAP:
        funcion, mensaje = _INTENT_MAP[intent]
        exito = funcion()
        contexto.actualizar(
            contexto.app_activa() or "",
            contexto.titulo_activo() or "",
            accion=intent,
        )
        if exito:
            return mensaje
        return f"No pude ejecutar '{intent}'."

    return "No reconocí ese comando de escritorio."
