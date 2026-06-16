# SOFÍA — Contexto persistente del proyecto

> Léeme antes de explorar el código. El objetivo de este archivo es que puedas
> entender la arquitectura completa de SOFÍA sin tener que abrir decenas de
> archivos. Está escrito para servir como contexto de Claude Code en futuras
> sesiones.

## 1. Resumen general

SOFÍA es un **asistente de voz personal offline-first para Windows**, escrito
en Python. Corre 100% en local (sin nube, sin API keys obligatorias): STT,
TTS e IA conversacional son modelos locales. Tiene una interfaz gráfica
flotante (PyQt6) tipo "asistente futurista" y se activa diciendo su nombre
("Sofía") o por botón/texto.

## 2. Objetivo de SOFÍA

Ser un asistente de escritorio en **español** que:
- Responde por voz a comandos de agenda, clima, sistema operativo, web y notas.
- Controla el escritorio (abrir/cerrar apps, leer ventanas activas) para
  resolver referencias implícitas ("ciérrala", "minimízala").
- Conversa libremente cuando ningún comando concreto matchea, usando un LLM
  local (Qwen3-8B vía llama.cpp).
- Aprende de sus fallos: registra preguntas sin respuesta y correcciones
  manuales para mejorar con el tiempo (sin fine-tuning automático aún).

## 3. Estructura de carpetas y responsabilidades

```
SOFIA/
├── main.py                  # Punto de entrada. Orquesta voz, UI, router, alarmas.
├── setup.py / paso_voz.py   # Instalador interactivo (dos fases, ver §7).
├── core/
│   ├── router.py            # Despachador de intents por keywords (sin NLU real).
│   ├── ia.py                 # Wrapper de llama.cpp: fallback conversacional + aprendizaje.
│   ├── memoria.py            # Persistencia JSON: eventos, alarmas, tareas, notas.
│   └── context_manager.py   # Estado de la app/ventana activa en el escritorio.
├── skills/                   # Un módulo por dominio de intención (ver §5).
│   ├── rutina.py, clima.py, tiempo.py, sistema.py, web.py,
│   │   notas.py, aprendizaje.py, control_escritorio.py
├── voz/
│   ├── escuchar.py           # VAD + wake-word + STT (Silero-VAD, faster-whisper).
│   ├── hablar.py              # Fachada de TTS (elige motor por .env).
│   └── hablar_qwen.py        # Motor TTS con Qwen3-TTS (GPU, voces clonadas/preset).
├── ui/widget.py               # Ventana PyQt6 frameless/translúcida.
├── data/                      # Estado runtime: modelo.gguf, memoria.json,
│                                aprendizaje.json, audio_estatico/*.wav, .env
└── venv/                      # Entorno virtual (no tocar/analizar).
```

## 4. Flujo completo de voz (end-to-end)

```
Micrófono (sounddevice, 16kHz, chunks de 512 muestras)
   │
   ▼
Silero-VAD (CPU, siempre cargado) — filtra silencio
   │ (cuando detecta voz, acumula ~2s)
   ▼
Faster-Whisper "tiny" (wake-word, siempre cargado, 0 VRAM extra)
   │ busca "sofia" (match exacto o difuso por Levenshtein)
   ▼  [activación detectada]
Reproduce "Dime" desde .wav pre-renderizado (sin GPU, instantáneo)
   │
   ├─ EN PARALELO: hilo de fondo carga Whisper "base" + Qwen3-TTS (lazy, GPU)
   │
   ▼
Faster-Whisper "base" transcribe el comando real (más preciso que tiny)
   │
   ▼
main.procesar_comando(texto) → core.router.procesar(texto)
   │
   ├─ normaliza texto (sin tildes, sin puntuación)
   ├─ recorre skills registradas en orden; primer keyword-match gana
   │     (rutina → clima → tiempo → sistema → web → notas →
   │      aprendizaje → control_escritorio)
   └─ si nada matchea → fallback: core.ia.preguntar() (LLM local Qwen3-8B,
        enriquecido con contexto de escritorio vía context_manager)
   │
   ▼
Respuesta de texto → UI (widget.agregar_mensaje) + TTS
   │
   ▼
voz.hablar.hablar(texto)
   ├─ motor "pyttsx3" (offline, rápido, voz robótica) — default
   └─ motor "qwen" (GPU, voz natural/clonada) — opcional vía SOFIA_TTS_MOTOR
   │  (mientras habla, el micrófono se pausa para evitar que se "escuche a sí misma")
   ▼
Micrófono se reanuda tras ~0.35s de margen (disipar eco)
```

Detalles clave del flujo:
- **Doble Whisper**: "tiny" para wake-word (barato, siempre activo) y "base"
  para comandos (más preciso, carga perezosa). Evita gastar VRAM/CPU cuando
  solo se está esperando el nombre.
- **Audio estático pre-renderizado** (`data/audio_estatico/*.wav`): frases
  fijas ("Dime", "Listo", saludos) generadas una vez con Qwen-TTS para
  responder sin esperar a que cargue el modelo grande cada vez.
- **Anti-feedback**: el micrófono se pausa explícitamente durante el TTS
  (`Escuchador.pausar()/reanudar()`), porque los altavoces pueden hacer que
  SOFÍA se transcriba a sí misma.

## 5. Componentes principales

| Componente | Archivo | Responsabilidad |
|---|---|---|
| **Router** | `core/router.py` | Única fuente de verdad de intents. Matching por keywords normalizadas (sin tildes/puntuación), no NLU. Primer match gana; orden de registro importa. |
| **IA conversacional** | `core/ia.py` | Wrapper de llama.cpp sobre Qwen3-8B-GGUF. Descarga el modelo automáticamente desde HF si falta. Filtra respuestas incoherentes/en inglés (heurística), fuerza `/no_think` para desactivar el modo thinking de Qwen3. |
| **Memoria persistente** | `core/memoria.py` | JSON plano en `data/memoria.json`: eventos, alarmas, tareas. Notas se comparten con la app externa NebulaNotes vía `~/Documentos/nebula_notes.json`. |
| **Context manager** | `core/context_manager.py` | Singleton en memoria (no persiste a disco) con la app/ventana activa, para resolver referencias implícitas y enriquecer el fallback de IA. |
| **Escuchador** | `voz/escuchar.py` | Pipeline VAD→STT completo, hilo de captura continuo, selección de micrófono por nombre, matching difuso de wake-word. |
| **Hablador** | `voz/hablar.py` + `hablar_qwen.py` | Fachada que elige motor TTS por env var; Qwen3-TTS soporta voces preset o clonación con `voz_referencia.wav`; descarga de VRAM tras inactividad (timer). |
| **UI** | `ui/widget.py` | Ventana PyQt6 frameless/translúcida; comunica con el hilo de lógica vía señales Qt (obligatorio porque Qt no permite tocar widgets desde otro hilo). |
| **Skills** | `skills/*.py` | Cada una expone `KEYWORDS: list[str]` y `manejar(texto) -> str` (o nombre equivalente). Se registran en `main.registrar_skills()`. |

## 6. Dependencias críticas

- **sounddevice + numpy** — captura de audio en tiempo real (reemplaza PyAudio).
- **torch + torchaudio (CPU)** — backend de Silero-VAD (descargado vía `torch.hub`).
- **faster-whisper** — STT (CTranslate2), modelos "tiny" y "base" descargados automáticamente.
- **llama-cpp-python** — inferencia del LLM local (Qwen3-8B-Q4_K_M.gguf, ~4.5GB, se descarga sola de HF si falta).
- **pyttsx3** — TTS offline por defecto (sin GPU).
- **qwen_tts + huggingface_hub** (opcional) — TTS de alta calidad con GPU, requiere CUDA.
- **PyQt6** — interfaz gráfica.
- **psutil + pywinauto** — control de escritorio (detección de procesos, automatización UIA en Windows).
- **requests** — clima (Open-Meteo) y otras skills de red.
- **python-dotenv** — configuración vía `.env` (no obligatorio).

## 7. Decisiones arquitectónicas importantes

1. **Router por keywords, no NLU/embeddings.** Simplicidad y latencia mínima
   (offline, CPU). El orden de registro decide prioridad cuando hay
   solapamiento (ej. "rutina" se registra primero para que "buenos días" no
   caiga en otra skill).
2. **Todo offline por defecto.** STT, TTS e IA corren localmente; la única
   llamada de red obligatoria es la descarga inicial de modelos. Clima usa
   Open-Meteo (sin API key) en vez de OpenWeatherMap precisamente para no
   requerir configuración.
3. **Doble modelo Whisper (tiny/base)** para separar el costo de "esperar el
   nombre" (barato, siempre encendido) del costo de "transcribir el comando"
   (más caro, carga perezosa). Decisión tomada tras observar que "tiny"
   confundía "sofia" con "novia"/"vía" en producción (ver comentarios en
   `voz/escuchar.py`).
4. **Lazy loading agresivo de modelos pesados (Qwen-TTS, Whisper base).** Se
   cargan en un hilo de fondo *mientras el usuario termina de hablar*, no al
   arrancar la app. Reduce el tiempo hasta la primera interacción.
5. **Audio estático pre-renderizado** para frases fijas, evitando esperar la
   carga de Qwen-TTS en cada interacción inicial ("Dime", saludos).
6. **Descarga de VRAM por inactividad** (`HabladorQwen`, timer de 30 min por
   defecto) para no monopolizar GPU si el usuario deja SOFÍA abierta.
7. **Persistencia en JSON plano**, sin base de datos. Justificado por el
   volumen de datos (un usuario, pocas decenas de eventos/tareas).
8. **Compatibilidad de datos con apps externas**: las notas usan el mismo
   archivo/formato que la app de escritorio NebulaNotes
   (`~/Documentos/nebula_notes.json`) para interoperar sin sincronización.
9. **Prompt engineering para forzar español y respuestas cortas**: el
   `SYSTEM_PROMPT` y el prefill `<think>\n\n</think>\n` desactivan el modo
   "thinking" de Qwen3 (que filtraba razonamiento en inglés a la respuesta
   final). Hay una heurística (`_es_incoherente`) que detecta y descarta
   respuestas en inglés o con razonamiento visible.
10. **Variables de entorno con alias retrocompatibles**: `SOFIA_MODEL_PATH`
    tiene prioridad sobre `ALE_MODEL_PATH` (nombre legado de una versión
    anterior del proyecto, "Ale").

## 8. Restricciones del proyecto

- **Solo Windows** en la práctica: `pywinauto` (control de escritorio) y
  varios atajos de teclado son específicos de Windows, aunque `sistema.py`
  intenta soporte básico multiplataforma.
- **Python 3.10–3.12** requerido (ver `setup.py`).
- **GPU NVIDIA (CUDA) opcional** pero necesaria para Qwen3-TTS de calidad;
  sin GPU, cae a `pyttsx3`.
- **~4.5 GB de descarga** para el modelo LLM (Qwen3-8B-GGUF) la primera vez.
- **No hay NLU real**: las skills solo reconocen las keywords que tienen
  registradas; ampliarlas requiere editar `KEYWORDS` manualmente.
- **Sin lectura de WhatsApp**: la skill `rutina.py` solo *abre* WhatsApp, no
  lee mensajes (requeriría la API oficial de negocio, fuera de alcance).
- **Idioma fijo: español.** El `SYSTEM_PROMPT` y los filtros anti-inglés
  asumen este idioma como único soportado.

## 9. Convenciones de desarrollo

- **Idioma del código y comentarios: español.** Identificadores, docstrings
  y mensajes de usuario están en español (coherente con el dominio del
  proyecto).
- **Cada skill expone `KEYWORDS: list[str]`** y una función `manejar(texto)`
  (o nombre equivalente, ej. `consultar_clima`) que recibe el texto ya
  normalizado por el router y devuelve un `str` con la respuesta.
- **Registro centralizado**: nuevas skills se añaden en
  `main.registrar_skills()`, no se auto-descubren.
- **Manejo de errores con degradación elegante**: cada capa (router, ia,
  skills) atrapa excepciones y devuelve un mensaje hablable en vez de
  crashear — la app debe seguir funcionando aunque falte hardware (GPU,
  micrófono) o un servicio externo.
- **Sin tildes en el matching**: `_quitar_tildes()` normaliza tanto el
  texto del usuario como las keywords antes de comparar.
- **Variables de configuración vía `.env`**, prefijo `SOFIA_*`
  (`SOFIA_TTS_MOTOR`, `SOFIA_MIC_NAME`, `SOFIA_WAKE_WORD`,
  `SOFIA_MODEL_PATH`, `SOFIA_CUDA_DEVICE`, etc.). Todas tienen un default
  razonable para que la app funcione sin `.env`.
- **Comentarios de cabecera "MEJORAS vN"** documentan el historial de
  cambios de un módulo directamente en el docstring — sigue este patrón si
  modificas un archivo existente con ese formato (no lo elimines, agrega).

## 10. Componentes en desarrollo

- `core/context_manager.py` y `skills/control_escritorio.py` (archivos
  nuevos, sin commitear según `git status`): ampliación del control de
  escritorio con resolución de referencias implícitas ("ciérrala").
  `control_escritorio.py` documenta explícitamente que OCR y `pyautogui`
  quedan pendientes para versiones futuras (actualmente usa
  `pywinauto` → atajos de teclado → `subprocess`/`os.startfile`, en ese
  orden de prioridad).
- `skills/aprendizaje.py`: el aprendizaje es solo de **registro** (guarda
  frases fallidas y correcciones en `data/aprendizaje.json`); no hay
  fine-tuning ni actualización automática de keywords todavía — está
  planteado como trabajo futuro en los propios comentarios del código.

## 11. Componentes pendientes / no implementados

- Lectura de mensajes de WhatsApp (requiere API oficial, fuera de alcance
  por decisión, no por limitación técnica).
- Aplicación automática de las "correcciones" registradas en
  `aprendizaje.json` (hoy quedan con `aplicada: false` indefinidamente).
- Soporte multiplataforma real para control de escritorio (hoy es
  Windows-only vía `pywinauto`).
- NLU/embeddings para reemplazar el matching por keywords (mencionado solo
  implícitamente por la limitación actual, no hay código en progreso).

## 12. Tecnologías descartadas y por qué

- **PyAudio** → reemplazado por `sounddevice` (más simple de instalar en
  Windows, sin dependencias de compilación con PortAudio).
- **Whisper "tiny" para comandos reales** → descartado en favor de "base"
  porque confundía consistentemente la wake-word "sofia" con "novia"/"vía"
  en producción; "tiny" se mantiene solo para la detección de wake-word
  donde el costo del error es menor y la velocidad es prioritaria.
- **OpenWeatherMap** → descartado en favor de **Open-Meteo**: no requiere
  API key, sin límite de peticiones, igual de preciso para el caso de uso.
- **Voces "Lucia/Isabella/Valentina/Sofia/Diego/Alejandro" del setup
  antiguo** → el modelo Qwen3-TTS-0.6B-CustomVoice real no las soporta; se
  mantiene un diccionario `ALIAS_VOCES` que las mapea a las voces reales
  del modelo (`serena`, `vivian`, `sohee`, `ono_anna`, `aiden`, `ryan`) para
  no romper instalaciones existentes.
- **Nombre de marca "ALE"** → el proyecto se renombró a "SOFÍA"; queda el
  alias `ALE_MODEL_PATH` en `core/ia.py` solo por retrocompatibilidad con
  instalaciones previas, no usar en código nuevo.
- **Fine-tuning del LLM local** → descartado por ahora por complejidad/costo;
  el "aprendizaje" actual es solo registro de datos para revisión manual.

## 13. Recomendaciones para futuros cambios

- **Nuevas skills**: crear `skills/nueva.py` con `KEYWORDS` + función
  `manejar`, registrarla en `main.registrar_skills()` **antes** del
  fallback y, si hay solapamiento de keywords con otra skill, ten en cuenta
  que el orden de registro decide cuál gana.
- **Si tocas el flujo de voz**, ten presente la separación tiny/base y el
  lazy-loading: no cargues Whisper "base" ni Qwen-TTS de forma síncrona en
  el hilo de detección de wake-word, rompe la latencia percibida.
- **Si agregas nuevas frases fijas frecuentes**, considera añadirlas a
  `prerender_frases_estaticas()` en `voz/hablar.py` en vez de generarlas
  con Qwen en caliente.
- **Si cambias el `SYSTEM_PROMPT` o el formato del prompt en `core/ia.py`**,
  vuelve a revisar `_es_incoherente()`: ambos están acoplados al formato
  ChatML de Qwen3 y al truco de prefill `<think>\n\n</think>\n`.
- **Antes de añadir una dependencia nueva**, evalúa si puede correr 100%
  offline/local — es una restricción de diseño explícita del proyecto, no
  solo una preferencia.
- **No analices `venv/`** al explorar el proyecto — es el entorno virtual,
  no código del proyecto.
- **Datos sensibles/runtime** (`data/modelo.gguf`, `data/aprendizaje.json`,
  `data/memoria.json`, `.env`) no deben commitearse; si los ves en
  `git status`, probablemente sea config local del usuario, no cambios de
  código a revisar.




# Instrucciones para Claude Code

Antes de modificar cualquier archivo:

1. Leer CLAUDE.md.
2. Respetar las decisiones arquitectónicas documentadas.
3. Proponer un plan antes de cambios grandes.
4. Evitar nuevas dependencias sin justificación.
5. Mantener compatibilidad con Windows 10/11.