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

KEYWORDS = [
    "abrir", "abre", "cerrar", "cierra",
    "crear archivo", "crear carpeta", "nuevo archivo", "nueva carpeta",
    "borrar", "eliminar", "copiar", "mover", "duplicar", "ejecutar archivo",
    "renombrar",
]

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


def abrir_app(texto):
    nombre = texto.replace("abrir", "").replace("abre", "").strip()

    # 1) ¿está en nuestro diccionario de alias?
    for clave, cmd in APPS.items():
        if clave in nombre or nombre in clave:
            if _ejecutar(cmd):
                return f"Abriendo {clave}."
            return f"No pude abrir {clave}."

    # 2) intento genérico: buscar el ejecutable en el PATH
    #    quitamos espacios para probar nombres como "word" -> "word"
    candidatos = [nombre, nombre.replace(" ", "")]
    for candidato in candidatos:
        if shutil.which(candidato):
            if _ejecutar(candidato):
                return f"Abriendo {nombre}."

    # 3) en Windows, os.startfile suele encontrar apps instaladas
    #    aunque no estén en el PATH (ej: "spotify", "calc")
    if sys.platform == "win32":
        try:
            os.startfile(nombre)
            return f"Abriendo {nombre}."
        except Exception:
            pass

    return (
        f"No encontré '{nombre}' instalado o no sé su nombre exacto. "
        f"Si tiene un nombre distinto al que dijiste, agrégalo al "
        f"diccionario APPS en skills/sistema.py."
    )


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


def manejar(texto):
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

    if "duplicar" in texto:
        return duplicar_archivo(texto)

    if "eliminar" in texto or "borrar" in texto:
        return eliminar_archivo(texto)

    return "No entendí la operación de sistema o archivos."
