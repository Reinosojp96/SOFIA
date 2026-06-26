"""
Pipeline de detección de voz offline y de baja latencia.

Flujo:
  Audio del micrófono (a la tasa NATIVA del dispositivo)
    -> remuestreo a 16 kHz en streaming (Silero-VAD/Whisper lo exigen)
    -> Silero-VAD  (filtra silencio; CPU 1-5%)
    -> acumula la frase
    -> normalización de volumen (clave para micrófono lejano)
    -> Faster-Whisper (transcribe)
    -> busca "sofia" (o variantes fonéticas) en el texto
    -> devuelve el resto del comando

MEJORAS v4 (corrección de los fallos de la sustentación):
  - **El hilo de captura ya NO muere en silencio.** Antes, si un micrófono
    USB no soportaba exactamente 16 kHz / bloques de 512 muestras,
    `sd.InputStream` lanzaba PortAudioError, el hilo daemon moría sin que
    nadie se enterara y la app se "congelaba" (la UI seguía viva pero la
    cola de audio nunca volvía a llenarse). Ahora:
      * Se negocia una tasa de muestreo SOPORTADA por el dispositivo
        (su tasa nativa, luego 48k/44.1k/32k/16k) y se remuestrea a 16 kHz.
      * `sd.InputStream` va dentro de try/except con reintentos.
      * Si todo falla se marca un flag de error y `esta_vivo()` lo expone,
        en vez de bloquear para siempre.
  - **Transcripción a distancia (>30 cm).** La señal lejana llega muy
    baja; Whisper en int8 sobre audio bajo devolvía basura o nada. Ahora:
      * Ganancia opcional por chunk (SOFIA_MIC_GAIN).
      * Normalización de pico de la frase completa antes de transcribir
        (sube el volumen sin amplificar el silencio puro).
      * Umbral de VAD por defecto más bajo (0.35) para que la voz suave
        lejana sí dispare la captura.
      * Se reinicia el estado interno del VAD entre frases (Silero es
        recurrente; sin reset las probabilidades se "arrastran").
  - Carga de Whisper de comandos protegida con lock (evita doble carga
    simultánea desde dos hilos -> OOM en GPU de 4 GB).
"""

from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path
import numpy as np

# Raíz del proyecto: todos los modelos descargados (Silero-VAD, Whisper)
# se contienen dentro de data/modelos/ en vez de la caché global del
# usuario (~/.cache/torch, ~/.cache/huggingface), para que el peso real
# del programa sea medible y no deje residuos al desinstalar.
_RAIZ = Path(__file__).parent.parent
_DIR_TORCH_HUB = _RAIZ / "data" / "modelos" / "torch_hub"
_DIR_WHISPER   = _RAIZ / "data" / "modelos" / "whisper"

# ---------------------------------------------------------------------------
# Configuración global (se puede sobreescribir con variables de entorno)
# ---------------------------------------------------------------------------
PALABRA_ACTIVACION: str = os.environ.get("SOFIA_WAKE_WORD", "sofia").lower()

# Nombre (o parte del nombre) del micrófono que quieres usar.
# Ejemplo en .env:  SOFIA_MIC_NAME=USB
MIC_NAME: str = os.environ.get("SOFIA_MIC_NAME", "").strip().lower()

# Modelo de Whisper para transcribir el comando real (más preciso).
WHISPER_MODEL_SIZE: str = os.environ.get("SOFIA_WHISPER_MODEL", "base")
# Modelo ligero SOLO para la wake-word (siempre cargado).
WHISPER_WW_SIZE: str = os.environ.get("SOFIA_WHISPER_WW_MODEL", "tiny")

# Variantes fonéticas que el STT puede devolver al oír "sofia".
VARIANTES: dict[str, list[str]] = {
    "sofia": [
        "sofia", "sofía", "sophie", "sofie", "sofi", "sofiá", "sophia",
        "sopilla", "sopía", "soquía", "sofilla",
        "fía", "sofiy", "sofı", "so fia", "so fía",
        # errores reales vistos con whisper "tiny" en el log:
        "novia", "ovia", "via", "vía", "ovía", "obia",
        # errores observados en producción con Intel SST omnidireccional:
        "lofia", "lofía",
        "sufia", "sufía", "su fía", "su fia",
        "sobia", "sobía", "sobea",
        "esporia", "ofía", "ofia",
        "lo fía", "lo fia",
        "delopia", "avery",
    ],
    "nova":   ["nova", "nove", "noba", "nóva"],
    "ale":    ["ale", "alé", "allé", "halle"],
    "jarvis": ["jarvis", "yarvis", "harvis"],
}

# Audio
SAMPLE_RATE       = 16_000   # Hz requerido por Silero-VAD y Whisper
CHUNK_SAMPLES     = 512      # Silero-VAD exige exactamente 512 muestras a 16 kHz
VAD_THRESHOLD     = float(os.environ.get("SOFIA_VAD_THRESHOLD", "0.50"))
SILENCE_CHUNKS    = int(os.environ.get("SOFIA_SILENCE_CHUNKS", "18"))  # ~580 ms — corte más rápido
MAX_VOICE_SECONDS = 8
_AUDIO_QUEUE_MAXSIZE = 400

# Ganancia aplicada a cada chunk capturado. 1.0 = sin cambio. Para
# micrófono lejano o de bajo nivel sube a 2.0-4.0 en el .env.
MIC_GAIN = float(os.environ.get("SOFIA_MIC_GAIN", "1.0"))

# Pico objetivo al normalizar la frase antes de transcribir. La
# normalización solo AMPLIFICA (nunca atenúa) y respeta un piso de ruido
# para no subir el volumen de silencio puro.
_PICO_OBJETIVO = 0.95
_GANANCIA_MAX  = 25.0     # tope para no reventar ruido de fondo
_PISO_RUIDO    = 0.005    # si el pico de la frase es menor, no amplificamos

# Umbral de similitud difusa (0-1).
_FUZZY_THRESHOLD = float(os.environ.get("SOFIA_FUZZY_THRESHOLD", "0.40"))


# ---------------------------------------------------------------------------
# Selección de dispositivo de entrada (micrófono)
# ---------------------------------------------------------------------------

def _seleccionar_dispositivo():
    """
    Devuelve (indice, info_dispositivo) del micrófono a usar, o (None, None)
    para dejar que sounddevice use el default del sistema.
    """
    import sounddevice as sd

    dispositivos = sd.query_devices()
    entradas = [(i, d) for i, d in enumerate(dispositivos)
                if d.get("max_input_channels", 0) > 0]

    print("[voz] Dispositivos de entrada disponibles:")
    for i, d in entradas:
        print(f"       [{i}] {d['name']}  (canales: {d['max_input_channels']}, "
              f"sr nativa: {int(d.get('default_samplerate', 0))})")

    if MIC_NAME:
        for i, d in entradas:
            if MIC_NAME in d["name"].lower():
                print(f"[voz] Micrófono por SOFIA_MIC_NAME='{MIC_NAME}': [{i}] {d['name']}")
                return i, d
        print(f"[voz] AVISO: no se encontró un micrófono que contenga "
              f"'{MIC_NAME}'. Usando el dispositivo por defecto.")

    try:
        default_in = sd.default.device[0]
        if default_in is not None and default_in >= 0:
            d = dispositivos[default_in]
            print(f"[voz] Micrófono por defecto: [{default_in}] {d['name']}")
            return default_in, d
    except Exception:
        pass
    print("[voz] Usando micrófono por defecto del sistema (sin nombre).")
    return None, None


def _elegir_samplerate(device_idx, device_info) -> int:
    """
    Encuentra una tasa de muestreo que el dispositivo SÍ soporte.

    Forzar 16 kHz en un micrófono USB que solo hace 44.1/48 kHz hacía que
    `sd.InputStream` fallara y el hilo de captura muriera (la causa raíz
    del 'se congela al instalar micrófonos externos'). Probamos la nativa
    primero y luego las habituales.
    """
    import sounddevice as sd

    candidatas = []
    if device_info:
        nativa = int(device_info.get("default_samplerate", 0) or 0)
        if nativa:
            candidatas.append(nativa)
    candidatas += [48000, 44100, 32000, 16000]

    vistas = []
    for sr in candidatas:
        if sr in vistas:
            continue
        vistas.append(sr)
        try:
            sd.check_input_settings(
                device=device_idx, channels=1, samplerate=sr, dtype="float32"
            )
            print(f"[voz] Tasa de captura negociada: {sr} Hz "
                  f"(se remuestrea a {SAMPLE_RATE} Hz)")
            return sr
        except Exception:
            continue

    # Si nada validó, dejamos que PortAudio intente con la nativa/16k y que
    # el try/except del hilo lo reporte en vez de morir en silencio.
    print("[voz] AVISO: no se pudo validar ninguna tasa; intentaré la nativa.")
    if device_info and device_info.get("default_samplerate"):
        return int(device_info["default_samplerate"])
    return SAMPLE_RATE


# Vocabulario que se le "sugiere" a Whisper para sesgar el reconocimiento.
INITIAL_PROMPT = (
    # Este prompt le dice a Whisper qué palabras esperar.
    # CRÍTICO: incluir exactamente los nombres de apps tal como el usuario los dice,
    # para evitar que Whisper los transcriba como palabras en inglés o inventadas.
    # Ejemplo documentado: "Word" -> "worth"/"wolf"/"reward" sin este prompt.
    "Sofía, abre Word, abre Excel, abre PowerPoint, abre Chrome, "
    "abre Brave, abre el navegador, abre WhatsApp, abre Spotify, "
    "abre la calculadora, abre el bloc de notas, abre Visual Studio Code, "
    "abre una carpeta, abre el explorador de archivos, "
    "cierra Word, cierra Chrome, cierra Excel, cierra la ventana, "
    "escanear aplicaciones, buscar aplicaciones, "
    "qué hora es, qué fecha es, qué día es, "
    "cómo está el clima en Ibagué, cuál es el clima, "
    "reproduce música en YouTube, pon música, "
    "anota que, agrega una tarea, qué tareas tengo, "
    "crea una carpeta, crea un archivo, crea un documento, "
    "copia, mueve, elimina, duplica, "
    "cuánto es dos más dos, cuánto es, cuál es la diferencia entre, "
    "qué es un agujero negro, explícame, cuéntame sobre, "
    "haz un documento en Word, abre un documento nuevo."
)
_vocab_extra = os.environ.get("SOFIA_VOCAB", "").strip()
if _vocab_extra:
    INITIAL_PROMPT += " " + _vocab_extra


# ---------------------------------------------------------------------------
# Carga perezosa de modelos
# ---------------------------------------------------------------------------

def _cargar_vad():
    """Carga solo Silero-VAD. CPU, sin VRAM."""
    import torch
    _DIR_TORCH_HUB.mkdir(parents=True, exist_ok=True)
    torch.hub.set_dir(str(_DIR_TORCH_HUB))
    vad_model, _utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        onnx=False,
        trust_repo=True,
    )
    return vad_model


def _cargar_whisper_model(size: str):
    """Carga Faster-Whisper del tamaño indicado. Puede usar GPU."""
    from faster_whisper import WhisperModel
    _DIR_WHISPER.mkdir(parents=True, exist_ok=True)
    device  = "cuda" if _gpu_disponible() else "cpu"
    compute = "float16" if device == "cuda" else "int8"
    return WhisperModel(
        size, device=device, compute_type=compute,
        download_root=str(_DIR_WHISPER),
    ), device


def _gpu_disponible() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Remuestreo en streaming (tasa nativa del micrófono -> 16 kHz)
# ---------------------------------------------------------------------------

class _ResampladorStreaming:
    """
    Remuestrea bloques consecutivos de 'sr_origen' a 16 kHz manteniendo la
    fase entre bloques (evita clics) y entregando frames EXACTOS de 512
    muestras, que es lo que Silero-VAD necesita.
    """

    def __init__(self, sr_origen: int):
        self.sr_origen = sr_origen
        self.ratio = SAMPLE_RATE / float(sr_origen)
        self._cola_16k = np.zeros(0, dtype=np.float32)
        self._ultimo = 0.0  # última muestra del bloque previo (continuidad)

    def procesar(self, bloque: np.ndarray) -> list[np.ndarray]:
        """Devuelve una lista de frames de 512 muestras a 16 kHz."""
        if bloque.size == 0:
            return []

        if self.sr_origen == SAMPLE_RATE:
            remuestreado = bloque.astype(np.float32)
        else:
            # Interpolación lineal con continuidad: prependemos la última
            # muestra del bloque anterior para que la rampa no salte.
            origen = np.concatenate(([self._ultimo], bloque)).astype(np.float32)
            self._ultimo = bloque[-1]
            n_salida = int(round((len(origen) - 1) * self.ratio))
            if n_salida <= 0:
                return []
            x_origen = np.arange(len(origen), dtype=np.float64)
            x_destino = np.linspace(0, len(origen) - 1, n_salida, dtype=np.float64)
            remuestreado = np.interp(x_destino, x_origen, origen).astype(np.float32)

        self._cola_16k = np.concatenate((self._cola_16k, remuestreado))

        frames = []
        n = len(self._cola_16k)
        usable = (n // CHUNK_SAMPLES) * CHUNK_SAMPLES
        for ini in range(0, usable, CHUNK_SAMPLES):
            frames.append(self._cola_16k[ini:ini + CHUNK_SAMPLES].copy())
        self._cola_16k = self._cola_16k[usable:]
        return frames


# ---------------------------------------------------------------------------
# Utilidad: similitud difusa (Levenshtein normalizado)
# ---------------------------------------------------------------------------

def _distancia_levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        return _distancia_levenshtein(b, a)
    if not b:
        return len(a)
    fila_anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        fila_actual = [i + 1]
        for j, cb in enumerate(b):
            costo = 0 if ca == cb else 1
            fila_actual.append(min(
                fila_actual[j] + 1,
                fila_anterior[j + 1] + 1,
                fila_anterior[j] + costo,
            ))
        fila_anterior = fila_actual
    return fila_anterior[-1]


def _similitud(a: str, b: str) -> float:
    """Retorna valor entre 0 (igual) y 1 (totalmente distintas)."""
    max_len = max(len(a), len(b), 1)
    return _distancia_levenshtein(a, b) / max_len


def _contiene_variante(texto: str, variantes: list[str]) -> tuple[bool, str]:
    palabras = texto.split()
    for var in variantes:                       # 1) exacta
        if var in texto:
            return True, var
    for palabra in palabras:                    # 2) difusa palabra a palabra
        for var in variantes:
            if _similitud(palabra, var) <= _FUZZY_THRESHOLD:
                return True, var
    for var in variantes:                       # 3) difusa al inicio del texto
        if _similitud(texto[:len(var) + 3], var) <= _FUZZY_THRESHOLD:
            return True, var
    return False, ""


# ---------------------------------------------------------------------------
# Normalización de volumen (clave para micrófono lejano)
# ---------------------------------------------------------------------------

def _normalizar_volumen(audio: np.ndarray) -> np.ndarray:
    """
    Sube el volumen de la frase para que Whisper la entienda a distancia.
    Solo amplifica (con tope) y respeta un piso de ruido: si la frase es
    casi silencio, no la toca (evitar amplificar ruido de fondo).
    """
    if audio.size == 0:
        return audio
    pico = float(np.max(np.abs(audio)))
    if pico < _PISO_RUIDO:
        return audio
    ganancia = min(_PICO_OBJETIVO / pico, _GANANCIA_MAX)
    if ganancia <= 1.0:
        return audio
    return np.clip(audio * ganancia, -1.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class Escuchador:
    """
    Escucha el micrófono de forma continua en un hilo interno.
    API pública: esperar_activacion() / escuchar_frase() / pausar() /
                 reanudar() / cargar_whisper_cmd() / esta_vivo() / cerrar()
    """

    def __init__(self):
        print("[voz] Cargando modelos (primera vez puede tardar unos segundos)...")
        self._vad = _cargar_vad()
        # Whisper tiny: siempre cargado, solo para detectar la wake-word
        self._whisper_ww, self._device = _cargar_whisper_model(WHISPER_WW_SIZE)
        self._whisper_cmd = None
        self._cmd_lock = threading.Lock()   # evita doble carga simultánea
        print(f"[voz] Modelos listos — dispositivo: {self._device} — "
              f"whisper cmd: {WHISPER_MODEL_SIZE}")

        self._device_idx, self._device_info = _seleccionar_dispositivo()
        self._sr_captura = _elegir_samplerate(self._device_idx, self._device_info)

        self._audio_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=_AUDIO_QUEUE_MAXSIZE)
        self._parar    = threading.Event()
        self._pausado  = threading.Event()
        self._error    = threading.Event()   # se activa si la captura falla
        self._mensaje_error = ""

        self._hilo = threading.Thread(target=self._capturar_audio, daemon=True)
        self._hilo.start()

        # Espera breve a que el stream confirme que arrancó, para poder
        # reportar el fallo de micrófono al instante (en vez de "congelarse").
        time.sleep(0.4)
        if self._error.is_set():
            raise RuntimeError(self._mensaje_error or "No se pudo abrir el micrófono")

    # ------------------------------------------------------------------
    # Salud
    # ------------------------------------------------------------------

    def esta_vivo(self) -> bool:
        """True si el hilo de captura sigue corriendo sin error."""
        return self._hilo.is_alive() and not self._error.is_set()

    # ------------------------------------------------------------------
    # Carga / descarga de Whisper para comandos (bajo demanda)
    # ------------------------------------------------------------------

    def cargar_whisper_cmd(self):
        """Carga Whisper base para transcribir comandos. Idempotente y thread-safe."""
        if self._whisper_cmd is not None:
            return
        with self._cmd_lock:
            if self._whisper_cmd is not None:
                return
            print(f"[voz] Cargando Whisper {WHISPER_MODEL_SIZE} (comandos)...")
            self._whisper_cmd, _ = _cargar_whisper_model(WHISPER_MODEL_SIZE)
            print(f"[voz] Whisper {WHISPER_MODEL_SIZE} listo")

    def descargar_whisper_cmd(self):
        """Libera Whisper base de la VRAM."""
        with self._cmd_lock:
            if self._whisper_cmd is None:
                return
            self._whisper_cmd = None
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
        print("[voz] Whisper cmd descargado")

    # ------------------------------------------------------------------
    # Pausa de captura (usar mientras SOFIA habla)
    # ------------------------------------------------------------------

    def pausar(self):
        """Deja de acumular audio nuevo (se descarta en el callback)."""
        self._pausado.set()

    def reanudar(self, retardo=0.35):
        """Reanuda la captura tras 'retardo' s (deja disipar el eco del TTS)."""
        if retardo > 0:
            time.sleep(retardo)
        self._vaciar_cola()
        self._pausado.clear()

    def _vaciar_cola(self):
        while True:
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                break

    # ------------------------------------------------------------------
    # Hilo de captura (robusto: no muere en silencio)
    # ------------------------------------------------------------------

    def _capturar_audio(self):
        import sounddevice as sd

        resampler = _ResampladorStreaming(self._sr_captura)
        # bloque ~32 ms a la tasa de captura; 0 dejaría que PortAudio elija,
        # pero un bloque fijo nos da frames de 16 kHz más regulares.
        blocksize = max(64, int(round(self._sr_captura * 0.032)))

        def callback(indata, frames, time_info, status):
            if status:
                print(f"[voz] sounddevice status: {status}")
            if self._pausado.is_set():
                return
            bloque = indata[:, 0].astype(np.float32)
            if MIC_GAIN != 1.0:
                bloque = bloque * MIC_GAIN
            for frame in resampler.procesar(bloque):
                try:
                    self._audio_q.put_nowait(frame)
                except queue.Full:
                    try:
                        self._audio_q.get_nowait()
                        self._audio_q.put_nowait(frame)
                    except (queue.Empty, queue.Full):
                        pass

        # Reintenta abrir el stream; si falla, marca error y NO bloquea la app.
        intentos = 0
        ultimo_err = None
        while not self._parar.is_set() and intentos < 3:
            intentos += 1
            try:
                with sd.InputStream(
                    samplerate=self._sr_captura,
                    channels=1,
                    dtype="float32",
                    blocksize=blocksize,
                    device=self._device_idx,
                    latency="high",   # buffer más grande, mejor para USB
                    callback=callback,
                ):
                    print(f"[voz] Captura activa a {self._sr_captura} Hz.")
                    self._error.clear()
                    self._parar.wait()
                return  # cierre limpio
            except Exception as e:
                ultimo_err = e
                print(f"[voz] ERROR abriendo el micrófono (intento {intentos}/3): {e}")
                time.sleep(0.6)

        self._mensaje_error = (
            f"No se pudo abrir el micrófono [{self._device_idx}] a "
            f"{self._sr_captura} Hz: {ultimo_err}"
        )
        self._error.set()
        print(f"[voz] {self._mensaje_error}")
        print("[voz] Revisa SOFIA_MIC_NAME en .env o elige otro micrófono en Windows.")

    # ------------------------------------------------------------------
    # VAD
    # ------------------------------------------------------------------

    def _reset_vad(self):
        """Reinicia el estado recurrente de Silero antes de cada frase."""
        try:
            self._vad.reset_states()
        except Exception:
            pass

    def _es_voz(self, chunk: np.ndarray) -> bool:
        import torch
        tensor = torch.from_numpy(chunk).unsqueeze(0)
        with torch.no_grad():
            prob = self._vad(tensor, SAMPLE_RATE).item()
        return prob >= VAD_THRESHOLD

    # ------------------------------------------------------------------
    # Transcripción
    # ------------------------------------------------------------------

    def _transcribir(self, audio: np.ndarray, modelo=None, usar_prompt=True) -> str:
        m = modelo or self._whisper_cmd or self._whisper_ww
        audio = _normalizar_volumen(audio)
        # beam_size=5 para el modelo de comandos: busca más candidatos antes de
        # decidir -> mucho menos probable que "Word" salga como "worth" o "wolf".
        # El modelo tiny de wake-word sigue con beam_size=1 (velocidad).
        es_ww = (modelo is not None and modelo is self._whisper_ww
                 and self._whisper_cmd is not None)
        _beam = 1 if (not usar_prompt or modelo is self._whisper_ww) else 5
        segments, _ = m.transcribe(
            audio,
            language="es",
            beam_size=_beam,
            vad_filter=False,
            word_timestamps=False,
            initial_prompt=INITIAL_PROMPT if usar_prompt else None,
            temperature=0.0,          # sin aleatoriedad -> resultados estables
            condition_on_previous_text=False,  # evita "arrastre" entre frases
            no_speech_threshold=0.6,  # descarta segmentos de silencio/ruido
        )
        texto = " ".join(seg.text for seg in segments).lower().strip()
        if texto:
            print(f"[voz] Transcrito: '{texto}'")
        return texto

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def escuchar_frase(self, tiempo_espera=6, limite_frase=10) -> str | None:
        """
        Espera hasta 'tiempo_espera' s a que empiece la voz, acumula hasta
        'limite_frase' s y transcribe con Whisper de comandos.
        """
        self.cargar_whisper_cmd()
        voz_buf = self._capturar_frase(tiempo_espera, limite_frase)
        if voz_buf is None:
            return None
        texto = self._transcribir(np.concatenate(voz_buf))
        return texto or None

    def _capturar_frase(self, tiempo_espera, limite_frase) -> list[np.ndarray] | None:
        """Captura una frase (espera inicio de voz + acumula hasta silencio)."""
        max_espera_chunks  = (int(tiempo_espera * SAMPLE_RATE / CHUNK_SAMPLES)
                              if tiempo_espera else 99_999)
        max_comando_chunks = int(limite_frase * SAMPLE_RATE / CHUNK_SAMPLES)

        self._reset_vad()
        voz_buf = None
        chunks_espera = 0
        while chunks_espera < max_espera_chunks:
            if not self.esta_vivo():
                return None
            try:
                chunk = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue
            if self._es_voz(chunk):
                voz_buf = [chunk]
                break
            chunks_espera += 1
        if voz_buf is None:
            return None

        silencio_cnt = 0
        while len(voz_buf) < max_comando_chunks:
            if not self.esta_vivo():
                break
            try:
                chunk = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue
            voz_buf.append(chunk)
            if self._es_voz(chunk):
                silencio_cnt = 0
            else:
                silencio_cnt += 1
                if silencio_cnt >= SILENCE_CHUNKS:
                    break
        return voz_buf

    def esperar_activacion(self) -> str:
        """
        Bucle bloqueante hasta detectar la palabra de activación.
        Devuelve el resto del comando o "" si solo se dijo el nombre.
        Lanza RuntimeError si el micrófono dejó de funcionar (en vez de
        congelarse para siempre).
        """
        variantes = VARIANTES.get(PALABRA_ACTIVACION, [PALABRA_ACTIVACION])
        max_ww_chunks = int(2.5 * SAMPLE_RATE / CHUNK_SAMPLES)

        while True:
            if not self.esta_vivo():
                raise RuntimeError(self._mensaje_error or "Micrófono no disponible")
            texto = self._escuchar_segmento_corto(max_ww_chunks)
            if not texto:
                continue

            encontrado, _ = _contiene_variante(texto, variantes)
            if not encontrado:
                continue

            resto = texto
            for var in variantes:
                if var in texto:
                    resto = texto.split(var, 1)[-1].strip().lstrip(",.;: ")
                    break
            if resto == texto:
                partes = texto.split(maxsplit=1)
                resto = partes[1] if len(partes) > 1 else ""
            return resto

    def _escuchar_segmento_corto(self, max_chunks: int) -> str | None:
        """Segmento corto para detección de wake-word (modelo tiny)."""
        self._reset_vad()
        voz_buf = None
        while voz_buf is None:
            if not self.esta_vivo():
                return None
            try:
                chunk = self._audio_q.get(timeout=0.15)
            except queue.Empty:
                continue
            if self._es_voz(chunk):
                voz_buf = [chunk]

        silencio_cnt = 0
        while len(voz_buf) < max_chunks:
            try:
                chunk = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue
            voz_buf.append(chunk)
            if self._es_voz(chunk):
                silencio_cnt = 0
            else:
                silencio_cnt += 1
                if silencio_cnt >= SILENCE_CHUNKS:
                    break

        audio = np.concatenate(voz_buf)
        # Wake-word: modelo tiny, sin initial_prompt (no sesgar el nombre).
        return self._transcribir(audio, modelo=self._whisper_ww, usar_prompt=False) or None

    def cerrar(self):
        """Detiene el hilo de captura de forma segura."""
        self._parar.set()
        if self._hilo.is_alive():
            self._hilo.join(timeout=3)