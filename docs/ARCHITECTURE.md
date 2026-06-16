# Arquitectura de SOFÍA — Documentación para Sustentación

> Este documento acompaña los diagramas UML ubicados en [`docs/uml/`](uml/)
> y está redactado para apoyar una presentación académica y comercial del
> producto ante una empresa consolidada. Cada sección describe un diagrama,
> su propósito de modelado y las decisiones de arquitectura que justifica.
> Todos los diagramas están escritos en PlantUML y fueron extraídos
> directamente del código fuente del repositorio, sin componentes
> hipotéticos.

## 1. Resumen ejecutivo

SOFÍA es un asistente de voz personal **offline-first**, desarrollado en
Python para Windows. Su propuesta de valor diferencial frente a asistentes
basados en nube (Alexa, Google Assistant, Siri) es que el reconocimiento de
voz (STT), la síntesis de voz (TTS) y el razonamiento conversacional (LLM)
se ejecutan **100% en el equipo del usuario**, sin dependencia de una API de
pago ni de conectividad permanente a Internet. Esto resuelve dos
preocupaciones críticas para clientes empresariales: **privacidad de los
datos de voz** (nunca salen del dispositivo) y **costo operativo
recurrente** (no hay tarifas por consulta ni por minuto de audio).

La arquitectura combina:

- Un **pipeline de voz en dos etapas** (detección ligera de palabra de
  activación + transcripción precisa del comando) que optimiza latencia
  percibida y consumo de recursos.
- Un **router de intenciones por palabras clave**, deliberadamente simple,
  que resuelve la mayoría de comandos sin necesidad de un modelo de lenguaje,
  reservando el LLM local (Qwen3-8B) solo para conversación libre.
- Un **subsistema de control de escritorio** que permite a SOFÍA actuar
  sobre el sistema operativo (abrir/cerrar aplicaciones, leer contenido de
  ventanas, resolver referencias implícitas como "ciérrala").

## 2. Diagrama de casos de uso — [`use_cases.puml`](uml/use_cases.puml)

**Propósito.** Presentar, desde la perspectiva del usuario final, el
catálogo funcional completo de SOFÍA y los actores externos con los que
interactúa.

**Actores identificados:**

| Actor | Rol |
|---|---|
| Usuario | Actor principal: emite comandos por voz o texto. |
| Sistema Operativo (Windows) | Ejecuta acciones de control de aplicaciones, ventanas y archivos. |
| Servicio Open-Meteo | Provee datos meteorológicos sin necesidad de API key. |
| Hugging Face Hub | Origen de la descarga automática del modelo LLM la primera vez. |
| Reloj del sistema (hilo de alarmas) | Actor temporal que dispara la verificación periódica de alarmas. |

**Relaciones `include`/`extend` relevantes:**

- Los tres canales de entrada (activación por voz, texto, botón "Hablar")
  **incluyen** siempre el caso de uso central *Procesar comando (Router)*,
  reflejando que `main.procesar_comando()` es el único punto de entrada al
  despacho de intenciones, sin importar el origen.
- *Procesar comando* **incluye** cada una de las skills de dominio (clima,
  agenda, sistema, web, notas, ventana) y, como camino final, *Conversar
  libremente*, modelando el patrón de **fallback determinista → IA
  generativa** que es central en el diseño.
- *Ejecutar rutina diaria* **incluye** *Consultar clima* y *Gestionar
  agenda*, mostrando cómo una skill compuesta reutiliza otras sin
  duplicar lógica.
- *Controlar ventana activa* **extiende** hacia *Resolver referencia
  implícita* y *Leer contenido de ventana activa*: estas son
  funcionalidades opcionales que solo se activan cuando el comando lo
  requiere (p. ej. "ciérrala" necesita saber qué ventana está activa).
- *Conversar libremente* **extiende** hacia *Registrar frase fallida* y
  *Descargar modelo LLM*: el aprendizaje pasivo y la descarga del modelo
  son comportamientos secundarios del fallback conversacional, no flujos
  independientes que el usuario invoque directamente.

**Valor para la sustentación.** Este diagrama es el más adecuado para abrir
una presentación a un público no técnico (dirección comercial, producto):
comunica el alcance funcional sin exponer detalles de implementación.

## 3. Diagrama de componentes — [`components.puml`](uml/components.puml)

**Propósito.** Mostrar los módulos de software como cajas negras con
contratos de interfaz, y las dependencias de invocación entre ellos.

**Lectura del diagrama.** `main.py` actúa como **orquestador**: instancia
la interfaz (`ui.widget`), registra las skills en el `Router`, arranca el
subsistema de voz (`voz.escuchar`, `voz.hablar`) y lanza el hilo de
verificación de alarmas sobre `core.memoria`. El `Router` es el único
componente que conoce a todas las skills; ninguna skill conoce a otra
directamente (con la única excepción documentada de `skills.rutina`, que
reutiliza `skills.clima` para componer su resumen diario). Los servicios
externos están aislados en la frontera derecha del diagrama
(`Open-Meteo`, `Hugging Face Hub`, `Windows`, `NebulaNotes`), reforzando
visualmente que SOFÍA solo cruza esa frontera cuando es estrictamente
necesario (clima, descarga inicial del modelo, control de SO, e
interoperabilidad de notas).

**Decisión arquitectónica destacada.** `core.ia` no depende de
`core.memoria`: el aprendizaje conversacional (`data/aprendizaje.json`) es
un almacén independiente del almacén de agenda/tareas
(`data/memoria.json`), lo que permite evolucionar o vaciar uno sin afectar
al otro.

## 4. Diagrama de paquetes — [`packages.puml`](uml/packages.puml)

**Propósito.** Representar la organización física del código en paquetes
Python (`main`, `ui`, `core`, `skills`, `voz`, `data`) y las dependencias
permitidas entre ellos, como referencia para mantenibilidad y onboarding
de nuevos desarrolladores.

**Regla de dependencia observada en el código:** `skills` depende de
`core`, nunca al revés. Esto es importante para la tesis de
extensibilidad del producto: **agregar una nueva skill no requiere tocar
`core`**, solo registrar el nuevo módulo en `main.registrar_skills()`. Esta
propiedad de bajo acoplamiento es un argumento de venta técnico: el costo
de incorporar nuevas integraciones (ERP interno, CRM, sistemas
propietarios del cliente) es marginal y no invasivo sobre el núcleo ya
probado.

## 5. Diagrama de despliegue — [`deployment.puml`](uml/deployment.puml)

**Propósito.** Mostrar la topología física de ejecución en una sola
estación de trabajo Windows, distinguiendo qué cargas computacionales
corren en CPU de forma permanente y cuáles se delegan opcionalmente a GPU.

**Punto clave para la sustentación comercial:** el diagrama documenta
explícitamente que **la GPU es opcional**. Sin una GPU NVIDIA con CUDA,
SOFÍA degrada automáticamente a Whisper "base" en modo `int8` sobre CPU y
a síntesis de voz `pyttsx3`, sin que el producto deje de funcionar. Esto
reduce la barrera de adopción en parques de equipos corporativos
heterogéneos, donde no todas las estaciones tienen GPU dedicada.

El despliegue también visualiza la **única dependencia de red
obligatoria**: la descarga inicial del modelo `Qwen3-8B-Q4_K_M.gguf`
(~4.5 GB) desde Hugging Face Hub. Una vez descargado, el modelo reside en
`data/modelo.gguf` y toda inferencia posterior es local.

## 6. Diagrama de actividades — [`activity_voice_flow.puml`](uml/activity_voice_flow.puml)

**Propósito.** Detallar el flujo de control completo desde que el usuario
pronuncia la palabra de activación hasta que recibe la respuesta hablada,
incluyendo las bifurcaciones de decisión y el paralelismo real del código.

**Aspectos técnicos que el diagrama hace explícitos:**

- El **doble modelo Whisper** ("tiny" siempre activo para la wake-word,
  "base" cargado de forma perezosa para el comando real) se representa
  como dos etapas de transcripción separadas por la decisión de "¿contiene
  la palabra de activación?".
- El **fork/join** modela fielmente que, mientras se reproduce el audio
  estático "Dime", un hilo en segundo plano ya está cargando Whisper
  "base" y, si aplica, Qwen3-TTS — el usuario nunca percibe ese tiempo de
  carga como latencia de espera.
- El bucle de evaluación de skills refleja la semántica real del
  `Router.procesar()`: **primer match gana**, por orden de registro.
- El paso final de "pausar micrófono" antes del TTS y "reanudar con
  retardo" documenta la mitigación de **retroalimentación acústica**
  (SOFÍA "escuchándose a sí misma"), un riesgo real en cualquier sistema de
  voz bidireccional con micrófono y altavoces compartiendo el mismo
  espacio físico.

## 7. Diagrama de secuencia — [`sequence_voice_command.puml`](uml/sequence_voice_command.puml)

**Propósito.** Ilustrar la interacción temporal entre objetos para un caso
de uso concreto y representativo: una consulta de clima por voz. Se eligió
este escenario porque ejercita la mayoría de los componentes clave del
sistema (voz, router, skill de dominio, servicio externo, y la rama
alternativa del fallback de IA) en una sola traza.

**Aspectos relevantes del diagrama:**

- El bloque `par` (paralelo) entre la reproducción del audio estático
  "Dime" y la carga de modelos pesados es la misma optimización de
  latencia descrita en el diagrama de actividades, ahora a nivel de
  mensajes entre objetos concretos.
- El bloque `alt` final muestra que la llamada a `core.ia.preguntar()`
  **solo ocurre si ninguna skill determinista hizo match** — es la
  representación a nivel de secuencia del patrón "fallback conversacional"
  que es central en el pitch de producto: el LLM es la última instancia,
  no la primera, lo que reduce el costo computacional promedio por
  comando.

## 8. Diagrama de clases — [`class_diagram_core.puml`](uml/class_diagram_core.puml)

**Propósito.** Documentar el diseño interno del núcleo (`core/`) y de las
clases con estado relevante en `voz/` y `ui/`, distinguiendo
explícitamente entre **clases reales** (`Router`, `ContextManager`,
`DesktopController`, `Escuchador`, `HabladorQwen`, `AleWidget`) y
**módulos funcionales** (`core.ia`, `core.memoria`, y cada skill), que en
Python no se implementan como clases sino como colecciones de funciones
con estado a nivel de módulo. Esta distinción se preserva intencionalmente
en el diagrama porque refleja una decisión de diseño consciente: el
proyecto evita la sobre-ingeniería orientada a objetos donde no aporta
valor (persistencia simple, wrappers de modelos), reservando clases para
los casos con estado complejo y ciclo de vida propio (hilos de captura de
audio, estado de ventana de escritorio, widgets de UI).

**Relación destacada:** `Router` mantiene una composición lógica
(`"1" o-- "many"`) con las funciones de skill registradas, modelando el
patrón de **registro de comportamiento (callback registry)** en lugar de
herencia o interfaces formales — coherente con la filosofía de simplicidad
del proyecto descrita en `CLAUDE.md`.

## 9. Conclusiones para la sustentación

1. **Privacidad por diseño**: la arquitectura de despliegue demuestra que
   ningún audio ni texto conversacional sale del equipo del usuario, salvo
   la consulta meteorológica (sin datos personales) y la descarga inicial
   del modelo.
2. **Costo operativo nulo por uso**: al no depender de APIs de pago por
   consulta, el costo marginal de cada interacción es energético/de
   cómputo local, no monetario.
3. **Extensibilidad de bajo riesgo**: el diagrama de paquetes y el de
   componentes muestran que nuevas integraciones (skills) se añaden sin
   modificar el núcleo, reduciendo el riesgo de regresión en
   implementaciones a medida para un cliente corporativo.
4. **Degradación elegante**: tanto el diagrama de despliegue (GPU
   opcional) como el de actividades (manejo de excepciones en cada capa)
   evidencian que el producto fue diseñado para seguir funcionando ante
   ausencia de hardware especializado o fallos puntuales de un componente,
   un requisito no funcional crítico para entornos empresariales.
