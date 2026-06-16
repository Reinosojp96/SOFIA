# SOFÍA — Historial de decisiones arquitectónicas (ADR)

> Registro de decisiones técnicas relevantes y su razonamiento. El objetivo
> es que una sesión nueva (humana o IA) entienda *por qué* el proyecto está
> construido así sin tener que reconstruir el razonamiento desde el código.
> Para el mapa general de arquitectura, ver [../CLAUDE.md](../CLAUDE.md).

Formato de cada entrada: **Decisión / Por qué / Alternativas consideradas /
Impacto**.

---

## 1. Arquitectura basada en "skills" + router por keywords

**Decisión:** Cada dominio de funcionalidad (clima, tiempo, sistema, web,
notas, rutina, aprendizaje, control de escritorio) vive en su propio módulo
de `skills/`, que expone una lista `KEYWORDS` y una función `manejar(texto)`.
Un único `Router` (`core/router.py`) normaliza el texto (sin tildes, sin
puntuación) y recorre las skills registradas en orden; la primera cuyo
keyword aparezca en el texto gana. Si ninguna matchea, cae a un fallback
conversacional (LLM local).

**Por qué:** Es el enfoque más simple y predecible para un asistente offline
de un solo usuario, con latencia mínima (no hay inferencia de un clasificador
de intents, es comparación de substrings). Permite añadir/quitar capacidades
sin tocar las demás, y depurar fácilmente "por qué SOFÍA respondió esto"
(`Router.stats()` ya expone qué skill se usó cuántas veces).

**Alternativas consideradas:**
- **NLU/clasificador de intents con embeddings** (ej. similitud semántica o
  un modelo pequeño de clasificación): descartado por complejidad y costo de
  cómputo extra para un proyecto que ya corre varios modelos locales (VAD,
  Whisper x2, LLM, TTS); el beneficio de entender frases no literales no
  justificaba la latencia y RAM adicionales en esta etapa.
- **Un único árbol de reglas / if-elif gigante en `main.py`**: descartado
  porque no escala ni se puede extender sin tocar un archivo central cada
  vez.

**Impacto:** El orden de `router.registrar()` en `main.registrar_skills()`
**es** la prioridad de desambiguación (ej. `rutina` se registra primero para
que "buenos días" no caiga en otra skill con keywords parecidas). Cualquier
nueva skill con keywords que se solapen con una existente debe registrarse
considerando este orden. Es también la razón de que SOFÍA no entienda
paráfrasis: las keywords deben anticiparse explícitamente.

---

## 2. IA conversacional local (Qwen3-8B vía llama.cpp) solo como fallback

**Decisión:** El LLM local solo se invoca cuando ninguna skill matchea
(`core/ia.py`, registrado como fallback del router). No se usa para
interpretar todos los comandos.

**Por qué:** Las skills determinísticas son más rápidas, predecibles y
gratuitas en cómputo que una llamada a un LLM de 8B en CPU/GPU local. Reservar
el LLM para conversación libre evita pagar el costo de inferencia (segundos)
en comandos triviales como "qué hora es".

**Alternativas consideradas:**
- **LLM como router universal** (le delegamos también el intent-matching):
  descartado por latencia y porque añade un punto de fallo no determinístico
  a funciones críticas (alarmas, abrir apps).
- **Modelo en la nube (OpenAI/Anthropic API)**: descartado por la restricción
  de diseño "offline-first / sin API keys obligatorias" (ver
  [CLAUDE.md §7](../CLAUDE.md)).

**Impacto:** El system prompt fuerza respuestas cortas en español y se
prefillea `<think>\n\n</think>\n` para desactivar el modo "thinking" de
Qwen3, que filtraba razonamiento en inglés al usuario. Hay una heurística
(`_es_incoherente`) que descarta respuestas en inglés o con razonamiento
visible y le pide al usuario repetir. Todo fallo de inferencia (modelo
faltante, error de llama.cpp) se registra en `data/aprendizaje.json` como
"frase fallida" para revisión manual — no hay reintento automático ni
fine-tuning.

---

## 3. Doble modelo Whisper: "tiny" para wake-word, "base" para comandos

**Decisión:** Dos instancias de Faster-Whisper conviven: "tiny" se carga
siempre al iniciar (barata, ~75MB) y solo se usa para detectar la palabra de
activación "sofia"; "base" se carga de forma perezosa (lazy) y solo cuando
hace falta transcribir el comando real.

**Por qué:** Se probó usar solo "tiny" para todo y confundía consistentemente
"sofia" con "novia", "vía", "ovia" en producción (observado en logs reales,
documentado en los comentarios de `voz/escuchar.py`). "base" es notablemente
más preciso pero más pesado — no tiene sentido pagar ese costo mientras solo
se está esperando el nombre de activación, que es el 99% del tiempo de
escucha continua.

**Alternativas consideradas:**
- **Solo "tiny"** (estado inicial): descartado por la tasa de falsos
  negativos/positivos en la wake-word.
- **Solo "base" todo el tiempo**: descartado por el costo de CPU/RAM de
  tenerlo siempre cargado solo para esperar una palabra.
- **Matching exclusivamente exacto de la wake-word** (sin tolerancia a
  errores fonéticos): insuficiente, complementado con búsqueda difusa
  (Levenshtein normalizado, umbral configurable `SOFIA_FUZZY_THRESHOLD`).

**Impacto:** Mayor complejidad en `voz/escuchar.py` (dos modelos, dos rutas
de transcripción) a cambio de mucho mejor balance latencia/precisión. Define
también el patrón de "lazy loading" que se repite en el resto del proyecto
(ver decisión #4).

---

## 4. Lazy loading agresivo de modelos pesados (Whisper "base" y Qwen3-TTS)

**Decisión:** Los modelos costosos (Whisper "base", Qwen3-TTS) no se cargan
al arrancar la aplicación ni de forma síncrona durante la interacción. Se
cargan en un **hilo de fondo** justo después de detectar la wake-word,
mientras el usuario todavía está formulando su comando en voz alta, y se
"unen" (`thread.join(timeout=...)`) solo cuando ya se necesitan.

**Por qué:** Minimizar el tiempo entre que el usuario termina de hablar y
SOFÍA responde. Cargar Qwen3-TTS en GPU puede tardar varios segundos; hacerlo
en paralelo a que el usuario habla "esconde" esa latencia en vez de sumarla
al tiempo de respuesta percibido.

**Alternativas consideradas:**
- **Carga eager de todos los modelos al iniciar `main.py`**: descartado
  porque suma decenas de segundos al arranque de la app y consume VRAM/RAM
  incluso si el usuario solo usa comandos de texto o skills triviales.
- **Carga síncrona bajo demanda (sin hilo de fondo)**: descartado porque
  añade el tiempo de carga del modelo directamente a la latencia de
  respuesta, justo en el momento más sensible (después de que el usuario ya
  habló).

**Impacto:** Patrón repetido en todo el código de voz: `_ensure_qwen()`,
`cargar_whisper_cmd()`, `_cargar_modelos_voz()` en `main.py`. Cualquier
cambio al flujo de voz debe preservar esta carga en paralelo — moverla a
síncrona rompe la latencia percibida aunque funcionalmente sea "correcto".
Se complementa con descarga automática por inactividad (decisión #5) y con
audio pre-renderizado para frases fijas (decisión #6).

---

## 5. Descarga de modelos de VRAM por inactividad (timer)

**Decisión:** `HabladorQwen` (`voz/hablar_qwen.py`) arranca un
`threading.Timer` cada vez que genera audio; si pasa `SOFIA_MODELO_TIMEOUT`
segundos (default 1800 = 30 min) sin uso, se descarga el modelo de VRAM y se
limpia la caché de CUDA.

**Por qué:** SOFÍA suele quedar abierta indefinidamente como app de
escritorio flotante. Sin este mecanismo, monopolizaría GPU para un modelo que
quizás no se vuelve a usar en horas, afectando a otras apps (juegos, edición
de video, etc.) que el usuario quiera correr mientras tanto.

**Alternativas consideradas:**
- **Nunca descargar** (mantener el modelo en VRAM mientras la app viva):
  descartado por el conflicto de recursos con GPU en un equipo personal.
- **Descargar inmediatamente después de cada uso**: descartado porque
  recargar el modelo en cada interacción anularía el beneficio del lazy
  loading y empeoraría la latencia percibida en uso conversacional continuo.

**Impacto:** Cualquier cambio al ciclo de vida de `HabladorQwen` debe
respetar `cargar()/descargar()/esta_cargado()` como API explícita, y
reiniciar el timer en cada generación de audio (`_reiniciar_timer()`).

---

## 6. Audio estático pre-renderizado para frases fijas

**Decisión:** Frases que se repiten siempre igual ("Dime", "Listo",
saludos según hora del día) se generan **una sola vez** con Qwen3-TTS y se
guardan como `.wav` en `data/audio_estatico/`. En tiempo real, SOFÍA las
reproduce directamente con `sounddevice`/`soundfile`, sin pasar por el
modelo TTS.

**Por qué:** Son justo las frases que se necesitan **antes** de que termine
de cargar Qwen3-TTS en GPU (ej. el "Dime" inmediato tras detectar la
wake-word, mientras el modelo carga en paralelo). Pre-renderizarlas elimina
por completo la espera de GPU para esas respuestas.

**Alternativas consideradas:**
- **Generar siempre con el motor TTS activo** (pyttsx3 o Qwen): descartado
  para estas frases puntuales porque añade latencia justo en el momento más
  crítico (la primera respuesta tras la activación).
- **Usar solo pyttsx3 para la respuesta inmediata, Qwen para el resto**: era
  una opción más simple, pero rompe la consistencia de voz/tono entre la
  respuesta inmediata y el resto de la conversación.

**Impacto:** Existe un comando explícito `python main.py --prerender` y una
función `prerender_frases_estaticas()` que se ejecuta automáticamente en el
primer arranque con `SOFIA_TTS_MOTOR=qwen` si el marcador `dime.wav` no
existe. Si se agregan nuevas frases fijas frecuentes, deben sumarse al
diccionario `frases` en `voz/hablar.py` y regenerarse con `--prerender`.

---

## 7. PyQt6 para la interfaz gráfica

**Decisión:** La UI (`ui/widget.py`) es una ventana **frameless y
translúcida** construida con PyQt6, con estética de "asistente flotante"
(sin barra de título, arrastrable a mano, esquinas redondeadas vía QSS).

**Por qué:** PyQt6 da control fino sobre transparencia (`WA_TranslucentBackground`)
y estilos custom (QSS) necesarios para el look "futurista" deseado, algo que
toolkits más simples (Tkinter) no logran sin mucho esfuerzo adicional. Es
además la opción con mejor soporte de señales/threads (`pyqtSignal`) para
integrar de forma segura el procesamiento en segundo plano (voz, alarmas)
con una UI que debe actualizarse solo desde el hilo principal de Qt.

**Alternativas consideradas:**
- **Tkinter**: descartado por las limitaciones para lograr ventanas
  translúcidas/sin bordes con buena estética sin mucho código de bajo nivel.
- **Web UI (Electron-like, ej. pywebview)**: descartado por overhead de
  recursos (Chromium embebido) en un proyecto que ya corre varios modelos
  pesados localmente; no se justifica el costo de RAM extra.

**Impacto:** Toda comunicación entre los hilos de voz/alarmas y la UI debe
pasar por señales Qt (`pyqtSignal`), nunca tocar widgets directamente desde
un hilo secundario — está documentado explícitamente en el docstring de
`ui/widget.py` y es una restricción dura de PyQt6, no solo de estilo.

---

## 8. Control de escritorio: pywinauto > atajos de teclado > subprocess (OCR descartado por ahora)

**Decisión:** `skills/control_escritorio.py` implementa una cadena de
prioridad explícita para ejecutar acciones sobre el escritorio:
1. `pywinauto` (accesibilidad UIA de Windows) — el método más robusto.
2. Atajos de teclado estándar.
3. `subprocess` / `os.startfile` como último recurso.

OCR y `pyautogui` (automatización por coordenadas de píxel) quedan
explícitamente fuera de esta versión.

**Por qué:** `pywinauto` interactúa con la **estructura semántica** de las
ventanas (nombres de controles, jerarquía UIA) en vez de píxeles, lo que lo
hace resistente a cambios de resolución, tema o escalado de DPI. OCR y
automatización por coordenadas son frágiles ante cualquier cambio visual y
mucho más costosos en CPU (captura de pantalla + reconocimiento de imagen
en cada acción).

**Alternativas consideradas:**
- **OCR (leer la pantalla y ubicar texto/botones)**: descartado para esta
  versión por fragilidad y costo de cómputo; queda anotado en el propio
  código como trabajo futuro si `pywinauto` no alcanza para casos
  específicos (apps sin soporte UIA decente).
- **`pyautogui` (clicks por coordenadas fijas)**: mismo problema de
  fragilidad ante cualquier cambio de layout; descartado por ahora.
- **Solo atajos de teclado** (sin pywinauto): insuficiente para acciones que
  requieren identificar qué ventana/app está activa primero.

**Impacto:** Esta skill es la única atada fuertemente a Windows (vía
`pywinauto`); es la razón principal por la que el proyecto se considera
"solo Windows en la práctica" (ver [CLAUDE.md §8](../CLAUDE.md)). Si se
agregan más acciones de escritorio, deben seguir el mismo orden de
fallback (UIA → teclado → proceso) en vez de saltar directo a soluciones
frágiles.

---

## 9. Contexto de escritorio compartido (`ContextManager`)

**Decisión:** Existe un singleton en memoria (`contexto`, en
`core/context_manager.py`) que guarda qué app/ventana está activa, su
título, la última acción ejecutada y un resumen de contenido visible. No
persiste a disco — vive solo mientras el proceso corre.

**Por qué:** Permite resolver referencias implícitas en lenguaje natural
("ciérrala", "minimízala") sin que el usuario repita el nombre de la
aplicación cada vez, y enriquecer el fallback conversacional del LLM con
información de qué está haciendo el usuario en ese momento (ej. "App activa:
Word. Contenido visible: ...").

**Alternativas consideradas:**
- **Pasar el contexto explícitamente como parámetro en cada llamada de
  skill/router**: descartado porque obligaría a enhebrar el estado por todo
  el árbol de llamadas (router → skill → ia), ensuciando firmas de función
  que hoy son simples `texto -> str`.
- **Persistir el contexto a disco** (como `memoria.json`): descartado
  porque es estado transitorio de sesión, no datos del usuario que deban
  sobrevivir un reinicio.

**Impacto:** Es un estado mutable global compartido entre el router, las
skills (especialmente `control_escritorio.py`) y el fallback de IA
(`main._fallback_con_contexto`). Cualquier nueva skill que necesite saber
"qué hay activo" debe leer este singleton en vez de inventar su propio
mecanismo de estado.

---

## 10. Persistencia en JSON plano, sin base de datos

**Decisión:** Todo el estado persistente de la app (eventos, alarmas,
tareas, registro de aprendizaje) se guarda en archivos JSON simples bajo
`data/`, leídos y reescritos por completo en cada operación
(`core/memoria.py`, `core/ia.py`).

**Por qué:** El volumen de datos es trivial (un usuario, decenas de
registros), por lo que el overhead de una base de datos (SQLite siquiera)
no se justifica frente a la simplicidad de depurar/editar JSON a mano.

**Alternativas consideradas:**
- **SQLite**: descartado por overhead innecesario para este volumen de
  datos y por la fricción extra de definir esquema/migraciones para un
  proyecto de un solo usuario.
- **Base de datos en la nube**: incompatible con la restricción de diseño
  offline-first.

**Impacto:** No hay control de concurrencia (lecturas/escrituras completas
del archivo); aceptable porque solo hay un proceso de SOFÍA corriendo a la
vez. Si en el futuro se necesita compartir estado entre procesos o crece el
volumen de datos, esta decisión debería revisarse.

---

## 11. Notas compartidas con la app externa NebulaNotes

**Decisión:** `skills/notas.py` no usa un archivo propio, sino el mismo
`~/Documentos/nebula_notes.json` que usa una app de escritorio externa
("NebulaNotes", un `.pyw` separado), respetando su formato exacto (clave
`"notes"`, campos `id`/`title`/`content`/`created`/`modified`).

**Por qué:** Permite que las notas creadas por voz en SOFÍA aparezcan
automáticamente en NebulaNotes y viceversa, sin necesidad de sincronización
ni de una capa de integración adicional — comparten el archivo como medio.

**Alternativas consideradas:**
- **Archivo de notas propio de SOFÍA** (en `data/`): descartado porque
  duplicaría la información y obligaría a sincronizar manualmente con
  NebulaNotes, que el usuario ya usa para notas.

**Impacto:** SOFÍA depende de un detalle de implementación de una app
externa (su formato de JSON). Si NebulaNotes cambia su esquema, `notas.py`
debe actualizarse en consonancia. El código es explícito en no tocar otras
claves del archivo (ej. la papelera de NebulaNotes) para no romper esa app.

---

## 12. Variables de entorno con alias retrocompatibles

**Decisión:** Configuración centralizada en variables `SOFIA_*` con
defaults seguros, pero se mantienen alias legados donde el proyecto cambió
de nombre (ej. `ALE_MODEL_PATH` como fallback de `SOFIA_MODEL_PATH`; el
diccionario `ALIAS_VOCES` que mapea nombres de voces del setup antiguo
—Lucia, Isabella, Diego...— a las voces reales del modelo Qwen3-TTS 0.6B
—serena, vivian, aiden...—).

**Por qué:** El proyecto se llamó "ALE" antes de renombrarse a "SOFÍA", y el
setup antiguo ofrecía nombres de voces "amigables" que no corresponden a
los IDs reales que acabó soportando el modelo 0.6B-CustomVoice. Mantener
alias evita romper instalaciones existentes de usuarios que ya configuraron
su `.env` con los nombres viejos.

**Alternativas consideradas:**
- **Migración forzada** (exigir que el usuario actualice su `.env`
  manualmente): descartado por fricción innecesaria para una decisión de
  naming interna que no debería ser un problema del usuario.

**Impacto:** Código nuevo no debe usar `ALE_MODEL_PATH` ni los nombres de
voz legados — son solo capas de compatibilidad. Si se elimina soporte para
instalaciones muy antiguas en el futuro, estos alias son candidatos claros
a limpieza.
