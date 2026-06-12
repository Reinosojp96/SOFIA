"""
Pipeline de detección de voz offline y de baja latencia.

Flujo:
  Audio (chunks de 512 muestras)
    -> Silero-VAD  (filtra silencio; CPU 1-5%)
    -> acumula hasta ~2 s de voz continua
    -> Faster-Whisper "tiny" (transcribe; CPU 10-20%)
    -> busca "sofia" (o variantes fonéticas) en el texto
    -> devuelve el resto del comando

MEJORAS v2:
  - Variantes fonéticas ampliadas para "sofia" (cubre todos los errores del log)
  - Matching difuso: distancia de edición para capturar "sopilla", "sofilla", etc.
  - Cola de audio con maxsize para evitar acumulación de audio viejo
  - Constantes documentadas y ajustables desde .env
  - cerrar() robusto (no cuelga si el hilo ya terminó)
"""

from __future__ import annotations

import os
import queue
import threading
import numpy as np

# ---------------------------------------------------------------------------
# Configuración global (se puede sobreescribir con variables de entorno)
# ---------------------------------------------------------------------------
PALABRA_ACTIVACION: str = os.environ.get("SOFIA_WAKE_WORD", "sofia").lower()

# Variantes fonéticas que el STT puede devolver al oír "sofia".
# Se amplió para cubrir TODOS los errores vistos en el log:
# sopilla, soquía, sofi, sophia, fía, etc.
VARIANTES: dict[str, list[str]] = {
    "sofia": [
        "sofia", "sofía", "sophie", "sofie", "sofi", "sofiá", "sophia",
        "sopilla", "sopía", "soquía", "soquía", "sofilla", "sofía",
        "fía", "sofiy", "sofı", "so fia", "so fía",
    ],
    "nova":   ["nova", "nove", "noba", "nóva"],
    "ale":    ["ale", "alé", "allé", "halle"],
    "jarvis": ["jarvis", "yarvis", "harvis"],
}

# Audio
SAMPLE_RATE       = 16_000   # Hz requerido por Silero-VAD y Whisper
CHUNK_SAMPLES     = 512      # ~32 ms por chunk a 16 kHz
VAD_THRESHOLD     = float(os.environ.get("SOFIA_VAD_THRESHOLD", "0.45"))
SILENCE_CHUNKS    = 20       # chunks de silencio para fin de frase (~640 ms)
MAX_VOICE_SECONDS = 8
# Cola con tamaño máximo: descarta audio viejo si nadie lo consume
# evita que el wake-word se active sobre audio acumulado de hace 2 segundos
_AUDIO_QUEUE_MAXSIZE = 200

# Umbral de similitud difusa (0-1). Si la distancia de Levenshtein normalizada
# es <= este valor, se considera que el usuario dijo la palabra de activación.
_FUZZY_THRESHOLD = float(os.environ.get("SOFIA_FUZZY_THRESHOLD", "0.35"))


# ---------------------------------------------------------------------------
# Carga perezosa de modelos
# ---------------------------------------------------------------------------

def _cargar_modelos():
    """Carga Silero-VAD y Faster-Whisper. Puede tardar 2-5 s la primera vez."""
    import torch
    from faster_whisper import WhisperModel

    vad_model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        onnx=False,
    )
    get_speech_prob = utils[0]

    device  = "cuda" if _gpu_disponible() else "cpu"
    compute = "float16" if device == "cuda" else "int8"
    whisper = WhisperModel("tiny", device=device, compute_type=compute)

    return vad_model, get_speech_prob, whisper, device


def _gpu_disponible() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Utilidad: similitud difusa (Levenshtein normalizado)
# ---------------------------------------------------------------------------

def _distancia_levenshtein(a: str, b: str) -> int:
    """Calcula la distancia de edición entre dos cadenas."""
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
    """
    Busca una variante exacta o difusa en el texto.
    Retorna (encontrado, variante_hallada).
    """
    palabras = texto.split()

    # 1) Búsqueda exacta (más rápida)
    for var in variantes:
        if var in texto:
            return True, var

    # 2) Búsqueda difusa palabra por palabra
    for palabra in palabras:
        for var in variantes:
            if _similitud(palabra, var) <= _FUZZY_THRESHOLD:
                return True, var

    # 3) Búsqueda difusa sobre el texto completo (cubre "sofía" partido en tokens)
    for var in variantes:
        if _similitud(texto[:len(var) + 3], var) <= _FUZZY_THRESHOLD:
            return True, var

    return False, ""


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class Escuchador:
    """
    Escucha el micrófono de forma continua en un hilo interno.
    API pública: esperar_activacion() / escuchar_frase() / cerrar()
    """

    def __init__(self):
        print("[voz] Cargando modelos (primera vez puede tardar unos segundos)...")
        self._vad, self._get_prob, self._whisper, self._device = _cargar_modelos()
        print(f"[voz] Modelos listos — dispositivo: {self._device}")

        # maxsize evita acumular audio viejo en cola
        self._audio_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=_AUDIO_QUEUE_MAXSIZE)
        self._parar   = threading.Event()
        self._hilo    = threading.Thread(target=self._capturar_audio, daemon=True)
        self._hilo.start()

    # ------------------------------------------------------------------
    # Hilo de captura
    # ------------------------------------------------------------------

    def _capturar_audio(self):
        import sounddevice as sd

        def callback(indata, frames, time_info, status):
            if status:
                print(f"[voz] sounddevice status: {status}")
            chunk = indata[:, 0].copy().astype(np.float32)
            try:
                self._audio_q.put_nowait(chunk)
            except queue.Full:
                # descartamos el chunk más viejo y metemos el nuevo
                try:
                    self._audio_q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._audio_q.put_nowait(chunk)
                except queue.Full:
                    pass

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_SAMPLES,
            callback=callback,
        ):
            self._parar.wait()

    # ------------------------------------------------------------------
    # VAD
    # ------------------------------------------------------------------

    def _es_voz(self, chunk: np.ndarray) -> bool:
        import torch
        tensor = torch.from_numpy(chunk).unsqueeze(0)
        with torch.no_grad():
            prob = self._vad(tensor, SAMPLE_RATE).item()
        return prob >= VAD_THRESHOLD

    # ------------------------------------------------------------------
    # Transcripción
    # ------------------------------------------------------------------

    def _transcribir(self, audio: np.ndarray) -> str:
        segments, _ = self._whisper.transcribe(
            audio,
            language="es",
            beam_size=1,
            vad_filter=False,
            word_timestamps=False,
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
        Espera hasta 'tiempo_espera' segundos a que empiece la voz,
        luego acumula hasta 'limite_frase' segundos y transcribe.
        """
        max_espera_chunks  = int(tiempo_espera * SAMPLE_RATE / CHUNK_SAMPLES) if tiempo_espera else 99_999
        max_comando_chunks = int(limite_frase  * SAMPLE_RATE / CHUNK_SAMPLES)

        chunks_espera = 0
        while chunks_espera < max_espera_chunks:
            try:
                chunk = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue
            if self._es_voz(chunk):
                voz_buf = [chunk]
                break
            chunks_espera += 1
        else:
            return None

        silencio_cnt = 0
        while len(voz_buf) < max_comando_chunks:
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
        texto = self._transcribir(audio)
        return texto if texto else None

    def esperar_activacion(self) -> str:
        """
        Bucle bloqueante hasta detectar la palabra de activación (exacta o difusa).
        Devuelve el resto del comando o "" si solo se dijo el nombre.
        """
        variantes = VARIANTES.get(PALABRA_ACTIVACION, [PALABRA_ACTIVACION])
        max_ww_chunks = int(2.5 * SAMPLE_RATE / CHUNK_SAMPLES)

        while True:
            texto = self._escuchar_segmento_corto(max_ww_chunks)
            if not texto:
                continue

            encontrado, variante_hallada = _contiene_variante(texto, variantes)
            if encontrado:
                # extraer lo que vino después del nombre
                resto = texto
                for var in variantes:
                    if var in texto:
                        resto = texto.split(var, 1)[-1].strip().lstrip(",.;: ")
                        break
                # si no se encontró variante exacta, devolver texto completo sin la primera palabra
                if resto == texto:
                    partes = texto.split(maxsplit=1)
                    resto = partes[1] if len(partes) > 1 else ""
                return resto

    def _escuchar_segmento_corto(self, max_chunks: int) -> str | None:
        """Versión interna para detección de wake-word: segmento corto."""
        while True:
            try:
                chunk = self._audio_q.get(timeout=0.15)
            except queue.Empty:
                continue
            if self._es_voz(chunk):
                voz_buf = [chunk]
                break

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
        return self._transcribir(audio) or None

    def cerrar(self):
        """Detiene el hilo de captura de forma segura."""
        self._parar.set()
        if self._hilo.is_alive():
            self._hilo.join(timeout=3)