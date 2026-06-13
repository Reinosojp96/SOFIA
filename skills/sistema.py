"""
Skill de sistema: abrir/cerrar aplicaciones y operaciones básicas con archivos.

Multiplataforma básico (Windows / Linux). Las rutas y nombres de apps
se configuran en APPS más abajo — ajústalo a tu equipo.
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
]

# Archivo donde se guarda el catálogo de apps detectadas automáticamente.
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_APPS_JSON = os.path.join(_DATA_DIR, "apps.json")

# Mapa de nombre hablado -> comando del sistema
APPS = {
    "navegador": "firefox" if sys.platform != "win32" else "start chrome",
    "chrome": "google-chrome" if sys.platform != "win32" else "start chrome",
    "calculadora": "gnome-calculator" if sys.platform != "win32" else "calc",
    "bloc de notas": "gedit" if sys.platform != "win32" else "notepad",
    "explorador de archivos": "nautilus ." if sys.platform != "win32" else "explorer .",
    "terminal": "x-terminal-emulator" if sys.platform != "win32" else "start cmd",
    "vscode": "code",
    "visual studio code": "code",
}


def _ejecutar(cmd):
    try:
        if sys.platform == "win32":
            subprocess.Popen(cmd, shell=True)
        else:
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

    - Windows: recorre los accesos directos (.lnk) del Menú Inicio
      (tanto del usuario actual como de todos los usuarios). No hace
      falta resolver el .lnk: Windows puede abrirlo directamente con
      os.startfile().
    - Linux: recorre los archivos .desktop de /usr/share/applications
      y ~/.local/share/applications, leyendo Name= y Exec=.

    Devuelve el catálogo (dict) generado.
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
                                # quitar parametros tipo %u, %f
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
        if nombre in catalogo:
            ruta = catalogo[nombre]
        else:
            ruta = None
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
    candidatos = [nombre, nombre.replace(" ", "")]
    for candidato in candidatos:
        if shutil.which(candidato):
            if _ejecutar(candidato):
                return f"Abriendo {nombre}."

    # 4) en Windows, os.startfile suele encontrar apps instaladas
    #    aunque no estén en el PATH (ej: "spotify", "calc")
    if sys.platform == "win32":
        try:
            os.startfile(nombre)
            return f"Abriendo {nombre}."
        except Exception:
            pass

    sugerencia = ""
    if not catalogo:
        sugerencia = " Di 'escanear aplicaciones' para que detecte automáticamente lo que tienes instalado."

    return f"No encontré '{nombre}' instalado o no sé su nombre exacto.{sugerencia}"


def cerrar_app(texto):
    nombre = texto.replace("cerrar", "").replace("cierra", "").strip()
    proceso = nombre
    # algunos alias comunes
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


# ---------- Archivos ----------

def _extraer_ruta(texto, palabra_clave):
    """Extrae lo que viene después de la palabra clave como ruta/nombre."""
    idx = texto.find(palabra_clave)
    if idx == -1:
        return ""
    resto = texto[idx + len(palabra_clave):].strip()
    # quitar conectores comunes
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
    """
    Extrae (origen, destino) de frases como:
      "mueve informe.pdf a Documentos"
      "copia foto.jpg a la carpeta Fotos"
      "mover informe.pdf hacia escritorio"

    verbos: lista de palabras clave que inician el comando (ej. ["mover", "mueve"])
    Devuelve (origen, destino) o (origen, None) si no hay destino.
    """
    resto = texto
    for verbo in verbos:
        if verbo in resto:
            resto = resto.split(verbo, 1)[-1].strip()
            break

    # separador entre origen y destino: "a", "hacia", "a la carpeta", "al"
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


def manejar(texto):
    if "escanear aplicaciones" in texto or "buscar aplicaciones" in texto:
        catalogo = escanear_apps()
        return f"Listo, encontré {len(catalogo)} aplicaciones instaladas."

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