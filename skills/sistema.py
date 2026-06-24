"""
Skill de sistema: abrir/cerrar aplicaciones y operaciones básicas con archivos.

Multiplataforma básico (Windows / Linux). Las rutas y nombres de apps
se configuran en APPS más abajo — ajústalo a tu equipo.

MEJORAS v2:
  - Agrega Word, Excel, PowerPoint, Paint al diccionario APPS
  - crear_documento(): abre Word/Excel con documento nuevo en blanco (via win32com)
  - buscar_y_abrir_archivo(): busca archivos por nombre parcial en carpetas comunes
  - toggle_dictado(): activa/desactiva el dictado de voz con Win+H (ctypes)
  - Fix: duplicar_archivo() ahora tiene su línea def correctamente definida
"""

import os
import re
import shutil
import subprocess
import sys
import json

KEYWORDS = [
    "abrir", "abre", "cerrar", "cierra",
    "crear archivo", "crear carpeta", "nuevo archivo", "nueva carpeta",
    "borrar", "eliminar", "copiar", "copia", "mover", "mueve",
    "cortar", "corta", "duplicar", "ejecutar archivo",
    "renombrar", "escanear aplicaciones", "buscar aplicaciones",
    # creación de documentos
    "crea un documento", "nuevo documento", "documento en word",
    "documento en excel", "documento en blanco", "crear documento",
    # búsqueda de archivos (incluye "busca el" genérico para capturar errores de STT como "pf" por "pdf")
    "busca el", "busca la", "busca el archivo", "busca el documento", "busca el pdf",
    "busca el word", "busca el excel", "encuentra el archivo",
    "donde esta el", "dónde está el",
    # dictado
    "activa dictar", "activa la opcion dictar", "activa dictado",
    "desactiva dictar", "desactiva dictado", "modo dictado", "opcion dictar",
]

# Archivo donde se guarda el catálogo de apps detectadas automáticamente.
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_APPS_JSON = os.path.join(_DATA_DIR, "apps.json")

# Mapa de nombre hablado -> comando del sistema
APPS = {
    "navegador":              "firefox" if sys.platform != "win32" else "start chrome",
    "chrome":                 "google-chrome" if sys.platform != "win32" else "start chrome",
    "calculadora":            "gnome-calculator" if sys.platform != "win32" else "calc",
    "bloc de notas":          "gedit" if sys.platform != "win32" else "notepad",
    "explorador de archivos": "nautilus ." if sys.platform != "win32" else "explorer .",
    "terminal":               "x-terminal-emulator" if sys.platform != "win32" else "start cmd",
    "vscode":                 "code",
    "visual studio code":     "code",
    "word":                   "start winword" if sys.platform == "win32" else "libreoffice --writer",
    "microsoft word":         "start winword" if sys.platform == "win32" else "libreoffice --writer",
    "excel":                  "start excel"   if sys.platform == "win32" else "libreoffice --calc",
    "microsoft excel":        "start excel"   if sys.platform == "win32" else "libreoffice --calc",
    "powerpoint":             "start powerpnt" if sys.platform == "win32" else "libreoffice --impress",
    "microsoft powerpoint":   "start powerpnt" if sys.platform == "win32" else "libreoffice --impress",
    "paint":                  "mspaint" if sys.platform == "win32" else "gimp",
}

# Prefijos a quitar para extraer el nombre de archivo (ordenados de más largo a más corto)
_PREFIJOS_BUSQUEDA = [
    "busca el pdf", "busca el word", "busca el excel",
    "busca el archivo", "busca el documento", "busca la",
    "encuentra el archivo", "encuentra el documento",
    "abre el archivo", "abre el documento", "abre el pdf",
    "abre la", "abre el", "donde esta el", "donde esta la",
    "donde esta", "dónde está el", "dónde está la",
    "busca", "encuentra",
]

_MAX_RESULTADOS = 20
_MAX_PROFUNDIDAD = 4


def _ejecutar(cmd):
    try:
        subprocess.Popen(cmd, shell=True)
        return True
    except Exception:
        return False


def _cargar_apps_json():
    if not os.path.exists(_APPS_JSON):
        return {}
    try:
        with open(_APPS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_apps_json(catalogo):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_APPS_JSON, "w", encoding="utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)


def escanear_apps():
    """
    Escanea las aplicaciones instaladas en el equipo y guarda un
    catálogo nombre -> ruta/comando en data/apps.json.
    """
    catalogo = {}

    if sys.platform == "win32":
        carpetas = [
            os.path.join(os.environ.get("APPDATA", ""),
                         r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("PROGRAMDATA", ""),
                         r"Microsoft\Windows\Start Menu\Programs"),
        ]
        for carpeta in carpetas:
            if not os.path.isdir(carpeta):
                continue
            for raiz, _dirs, archivos in os.walk(carpeta):
                for archivo in archivos:
                    if archivo.lower().endswith(".lnk"):
                        nombre = os.path.splitext(archivo)[0].strip().lower()
                        ruta = os.path.join(raiz, archivo)
                        catalogo[nombre] = ruta

    else:
        carpetas = [
            "/usr/share/applications",
            os.path.expanduser("~/.local/share/applications"),
        ]
        for carpeta in carpetas:
            if not os.path.isdir(carpeta):
                continue
            for archivo in os.listdir(carpeta):
                if not archivo.endswith(".desktop"):
                    continue
                ruta_completa = os.path.join(carpeta, archivo)
                nombre = None
                comando = None
                try:
                    with open(ruta_completa, "r", encoding="utf-8", errors="ignore") as f:
                        for linea in f:
                            if linea.startswith("Name=") and nombre is None:
                                nombre = linea.split("=", 1)[1].strip().lower()
                            elif linea.startswith("Exec=") and comando is None:
                                comando = linea.split("=", 1)[1].strip()
                                comando = re.sub(r"%[a-zA-Z]", "", comando).strip()
                except Exception:
                    continue
                if nombre and comando:
                    catalogo[nombre] = comando

    _guardar_apps_json(catalogo)
    return catalogo


def abrir_app(texto):
    nombre = texto.replace("abrir", "").replace("abre", "").strip()

    # 1) ¿está en nuestro diccionario de alias manuales?
    for clave, cmd in APPS.items():
        if clave in nombre or nombre in clave:
            if _ejecutar(cmd):
                return f"Abriendo {clave}."
            return f"No pude abrir {clave}."

    # 2) ¿está en el catálogo escaneado automáticamente?
    catalogo = _cargar_apps_json()
    if catalogo:
        ruta = catalogo.get(nombre)
        if not ruta:
            for clave, valor in catalogo.items():
                if nombre in clave or clave in nombre:
                    ruta = valor
                    break

        if ruta:
            try:
                if sys.platform == "win32":
                    os.startfile(ruta)
                else:
                    subprocess.Popen(ruta, shell=True)
                return f"Abriendo {nombre}."
            except Exception:
                pass

    # 3) intento genérico: buscar el ejecutable en el PATH
    for candidato in [nombre, nombre.replace(" ", "")]:
        if shutil.which(candidato):
            if _ejecutar(candidato):
                return f"Abriendo {nombre}."

    # 4) en Windows, os.startfile suele encontrar apps instaladas
    if sys.platform == "win32":
        try:
            os.startfile(nombre)
            return f"Abriendo {nombre}."
        except Exception:
            pass

    sugerencia = "" if catalogo else " Di 'escanear aplicaciones' para que detecte automáticamente lo que tienes instalado."
    return f"No encontré '{nombre}' instalado o no sé su nombre exacto.{sugerencia}"


def cerrar_app(texto):
    nombre = texto.replace("cerrar", "").replace("cierra", "").strip()
    alias = {"navegador": "firefox", "chrome": "chrome", "vscode": "code"}
    proceso = alias.get(nombre, nombre)

    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", f"{proceso}.exe"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", proceso], capture_output=True)
        return f"Cerrando {nombre}."
    except Exception as e:
        return f"No pude cerrar {nombre}: {e}"


def crear_documento(texto):
    """Abre Word o Excel con un documento/libro nuevo en blanco."""
    es_excel = "excel" in texto
    try:
        import win32com.client
        if es_excel:
            app = win32com.client.Dispatch("Excel.Application")
            app.Visible = True
            app.Workbooks.Add()
            return "Creando libro nuevo en Excel."
        else:
            app = win32com.client.Dispatch("Word.Application")
            app.Visible = True
            app.Documents.Add()
            return "Creando documento nuevo en Word."
    except ImportError:
        # pywin32 no disponible, fallback a abrir la app sin documento nuevo
        if es_excel:
            subprocess.Popen("start excel", shell=True)
            return "Abriendo Excel."
        else:
            subprocess.Popen("start winword", shell=True)
            return "Abriendo Word."
    except Exception as e:
        return f"No pude crear el documento: {e}"


_RE_SUFIJO_CARPETA = re.compile(
    r"\s+(?:en|de|de la|de los|en la|en los)?\s*"
    r"(?:documentos?|escritorio|descargas?|documents?|desktop|downloads?)"
    r"\s*$",
    re.IGNORECASE,
)

def _extraer_nombre_archivo(texto):
    """Quita el prefijo de búsqueda más largo que coincida y devuelve el nombre limpio."""
    for prefijo in _PREFIJOS_BUSQUEDA:
        if texto.startswith(prefijo):
            nombre = texto[len(prefijo):].strip()
            # quitar "de la carpeta documentos", "en documentos", etc. al final
            nombre = re.sub(r"\s+de la carpeta\s+\w+$", "", nombre)
            nombre = _RE_SUFIJO_CARPETA.sub("", nombre).strip()
            return nombre
    # sin prefijo reconocido: limpiar sufijos de carpeta igualmente
    return _RE_SUFIJO_CARPETA.sub("", texto).strip()


def buscar_y_abrir_archivo(nombre_parcial):
    """Busca un archivo por nombre parcial en carpetas comunes y lo abre."""
    if not nombre_parcial:
        return "¿Cómo se llama el archivo que buscas?"

    carpetas = [
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/Downloads"),
    ]
    onedrive = os.path.expanduser("~/OneDrive")
    if os.path.isdir(onedrive):
        carpetas.append(onedrive)

    encontrados = []
    for carpeta in carpetas:
        if not os.path.isdir(carpeta):
            continue
        base_depth = carpeta.count(os.sep)
        for root, dirs, files in os.walk(carpeta):
            if root.count(os.sep) - base_depth >= _MAX_PROFUNDIDAD:
                dirs[:] = []
            for f in files:
                if nombre_parcial.lower() in f.lower():
                    encontrados.append(os.path.join(root, f))
            if len(encontrados) >= _MAX_RESULTADOS:
                break
        if len(encontrados) >= _MAX_RESULTADOS:
            break

    if not encontrados:
        return f"No encontré archivos con '{nombre_parcial}'."

    try:
        os.startfile(encontrados[0])
    except Exception as e:
        return f"Encontré el archivo pero no pude abrirlo: {e}"

    nombre_base = os.path.basename(encontrados[0])
    if len(encontrados) > 1:
        return f"Encontré {len(encontrados)} archivos. Abriendo el primero: {nombre_base}."
    return f"Abriendo {nombre_base}."


def toggle_dictado(_texto=None):
    """
    Activa o desactiva el dictado de voz.
    - Si Word está abierto: hace clic en el botón 'Dictar' de la cinta (pywinauto UIA).
    - En cualquier otro caso: envía Win+H (dictado nativo de Windows, es toggle).
    """
    try:
        from pywinauto import Application
        # Word usa la clase de ventana "OpusApp"
        app = Application(backend="uia").connect(class_name="OpusApp", timeout=2)
        win = app.top_window()
        win.set_focus()

        # Buscar el botón Dictar en todo el árbol de controles (búsqueda recursiva)
        for nombre_boton in ["Dictar", "Dictate"]:
            try:
                elementos = win.descendants(title=nombre_boton, control_type="Button")
                if elementos:
                    elementos[0].click_input()
                    return "Alternando el dictado en Word."
            except Exception:
                continue
    except Exception:
        pass

    # Fallback: Win+H (dictado nativo de Windows)
    import ctypes
    VK_LWIN, VK_H, KEYEVENTF_KEYUP = 0x5B, 0x48, 0x0002
    ku = ctypes.windll.user32.keybd_event
    ku(VK_LWIN, 0, 0, 0)
    ku(VK_H, 0, 0, 0)
    ku(VK_H, 0, KEYEVENTF_KEYUP, 0)
    ku(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
    return "Alternando el dictado de voz."


# ---------- Archivos ----------

def _extraer_ruta(texto, palabra_clave):
    """Extrae lo que viene después de la palabra clave como ruta/nombre."""
    idx = texto.find(palabra_clave)
    if idx == -1:
        return ""
    resto = texto[idx + len(palabra_clave):].strip()
    resto = re.sub(r"^(llamad[oa]|llamada|nombrad[oa]|con el nombre)\s+", "", resto)
    return resto.strip(' "\'')


def crear_archivo(texto):
    nombre = _extraer_ruta(texto, "archivo")
    if not nombre:
        return "¿Cómo quieres llamar el archivo?"
    try:
        if not os.path.splitext(nombre)[1]:
            nombre += ".txt"
        with open(nombre, "w", encoding="utf-8") as f:
            f.write("")
        return f"Archivo {nombre} creado."
    except Exception as e:
        return f"No pude crear el archivo: {e}"


def crear_carpeta(texto):
    nombre = _extraer_ruta(texto, "carpeta")
    if not nombre:
        return "¿Cómo quieres llamar la carpeta?"
    try:
        os.makedirs(nombre, exist_ok=True)
        return f"Carpeta {nombre} creada."
    except Exception as e:
        return f"No pude crear la carpeta: {e}"


def ejecutar_archivo(texto):
    nombre = _extraer_ruta(texto, "archivo")
    if not nombre or not os.path.exists(nombre):
        return f"No encuentro el archivo '{nombre}'."
    try:
        if sys.platform == "win32":
            os.startfile(nombre)
        else:
            subprocess.Popen(["xdg-open", nombre])
        return f"Ejecutando {nombre}."
    except Exception as e:
        return f"No pude ejecutar el archivo: {e}"


def _extraer_origen_destino(texto, verbos):
    resto = texto
    for verbo in verbos:
        if verbo in resto:
            resto = resto.split(verbo, 1)[-1].strip()
            break

    m = re.search(r"\s+(?:hacia|a la carpeta|al|a)\s+(.+)$", resto)
    if not m:
        return resto.strip(' "\''), None

    destino = m.group(1).strip(' "\'')
    origen = resto[:m.start()].strip(' "\'')
    destino = re.sub(r"^(la\s+)?carpeta\s+", "", destino)
    return origen, destino


def copiar_archivo(texto):
    origen, destino = _extraer_origen_destino(texto, ["copia", "copiar"])
    if not origen or not os.path.exists(origen):
        return f"No encuentro '{origen}' para copiar."
    if not destino:
        return "¿A dónde quieres copiarlo? Por ejemplo: 'copia informe.pdf a Documentos'."

    try:
        if os.path.isdir(destino):
            destino_final = os.path.join(destino, os.path.basename(origen))
        else:
            destino_final = destino

        if os.path.isdir(origen):
            shutil.copytree(origen, destino_final)
        else:
            os.makedirs(os.path.dirname(destino_final) or ".", exist_ok=True)
            shutil.copy(origen, destino_final)
        return f"Copiado {origen} a {destino_final}."
    except Exception as e:
        return f"No pude copiar: {e}"


def mover_archivo(texto):
    origen, destino = _extraer_origen_destino(texto, ["mueve", "mover", "corta", "cortar"])
    if not origen or not os.path.exists(origen):
        return f"No encuentro '{origen}' para mover."
    if not destino:
        return "¿A dónde quieres moverlo? Por ejemplo: 'mueve informe.pdf a Documentos'."

    try:
        if os.path.isdir(destino):
            destino_final = os.path.join(destino, os.path.basename(origen))
        else:
            os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
            destino_final = destino

        shutil.move(origen, destino_final)
        return f"Movido {origen} a {destino_final}."
    except Exception as e:
        return f"No pude mover: {e}"


def duplicar_archivo(texto):
    nombre = _extraer_ruta(texto, "duplicar")
    if not nombre or not os.path.exists(nombre):
        return f"No encuentro '{nombre}' para duplicar."
    try:
        base, ext = os.path.splitext(nombre)
        copia = f"{base}_copia{ext}"
        shutil.copy(nombre, copia)
        return f"Duplicado como {copia}."
    except Exception as e:
        return f"No pude duplicar: {e}"


def eliminar_archivo(texto):
    nombre = _extraer_ruta(texto, "eliminar") or _extraer_ruta(texto, "borrar")
    if not nombre or not os.path.exists(nombre):
        return f"No encuentro '{nombre}' para eliminar."
    try:
        if os.path.isdir(nombre):
            shutil.rmtree(nombre)
        else:
            os.remove(nombre)
        return f"{nombre} eliminado."
    except Exception as e:
        return f"No pude eliminar: {e}"


# Palabras que indican búsqueda de archivos (para detectar antes de "abre")
_KEYWORDS_BUSQUEDA = [
    "busca el pdf", "busca el word", "busca el excel", "busca el pf",
    "busca el archivo", "busca el documento", "busca la", "encuentra el",
    "donde esta", "dónde está",
]

# Palabras que indican que "busca el X" es búsqueda WEB, no de archivo
_PALABRAS_WEB = {
    "que", "qué", "como", "cómo", "cuando", "cuándo", "donde", "dónde",
    "por", "para", "cuanto", "cuánto", "quien", "quién", "cual", "cuál",
    "informacion", "información", "noticias", "precio", "receta",
}

# Patrones de "abre [nombre] de la carpeta" → también es búsqueda
_RE_ABRE_CARPETA = re.compile(r"abre\s+(.+?)\s+de la carpeta\s+\w+")
_RE_ABRE_ARCHIVO = re.compile(r"abre\s+(?:el|la|un|una)?\s*(?:archivo|documento|pdf|word|excel)\s+(.+)")


def _es_busqueda_archivo(texto):
    """Devuelve True si el texto parece una petición de búsqueda de archivo local."""
    if any(k in texto for k in _KEYWORDS_BUSQUEDA):
        return True
    if _RE_ABRE_CARPETA.search(texto):
        return True
    if _RE_ABRE_ARCHIVO.search(texto):
        return True
    # "busca el X" genérico: solo si la palabra después de "el/la" NO es una palabra de búsqueda web
    m = re.search(r"busca (?:el|la|un|una)\s+(\w+)", texto)
    if m:
        primera_palabra = m.group(1).lower()
        if primera_palabra not in _PALABRAS_WEB:
            return True
    return False


def manejar(texto):
    if "escanear aplicaciones" in texto or "buscar aplicaciones" in texto:
        catalogo = escanear_apps()
        return f"Listo, encontré {len(catalogo)} aplicaciones instaladas."

    # Dictado (antes de cualquier otro check para no colisionar con "activa X")
    if any(p in texto for p in ["activa dictar", "activa la opcion dictar", "activa dictado",
                                  "desactiva dictar", "desactiva dictado", "modo dictado", "opcion dictar"]):
        return toggle_dictado(texto)

    # Crear documento (antes de "abre"/"abrir" para evitar solapamiento)
    if any(p in texto for p in ["documento", "en blanco", "crear documento", "nuevo documento"]):
        if any(p in texto for p in ["crea", "crear", "nuevo", "nueva", "en blanco"]):
            return crear_documento(texto)

    # Búsqueda de archivos por nombre parcial (antes de "abre" genérico)
    if _es_busqueda_archivo(texto):
        # Intentar extraer el nombre con los patrones específicos
        m = _RE_ABRE_CARPETA.search(texto)
        if m:
            return buscar_y_abrir_archivo(m.group(1).strip())
        m = _RE_ABRE_ARCHIVO.search(texto)
        if m:
            return buscar_y_abrir_archivo(m.group(1).strip())
        nombre = _extraer_nombre_archivo(texto)
        return buscar_y_abrir_archivo(nombre)

    if any(p in texto for p in ["abrir", "abre"]):
        return abrir_app(texto)

    if any(p in texto for p in ["cerrar", "cierra"]):
        return cerrar_app(texto)

    if "crear archivo" in texto or "nuevo archivo" in texto:
        return crear_archivo(texto)

    if "crear carpeta" in texto or "nueva carpeta" in texto:
        return crear_carpeta(texto)

    if "ejecutar archivo" in texto or "abrir archivo" in texto:
        return ejecutar_archivo(texto)

    if any(p in texto for p in ["copia", "copiar"]):
        return copiar_archivo(texto)

    if any(p in texto for p in ["mueve", "mover", "corta", "cortar"]):
        return mover_archivo(texto)

    if "duplicar" in texto:
        return duplicar_archivo(texto)

    if "eliminar" in texto or "borrar" in texto:
        return eliminar_archivo(texto)

    return "No entendí la operación de sistema o archivos."
