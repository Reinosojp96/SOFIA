# SOFÍA — Guion de Presentación
### Julián Reinoso · 15 minutos · Jurado mixto (académico + empresarial)

---

> **Cómo leer este guion:**
> Las líneas en *cursiva* son acotaciones de escena, no se dicen en voz alta.
> Los tiempos entre corchetes son orientativos.
> El texto en negrita indica énfasis de voz.

---

## [00:00 – 02:30] APERTURA · *Slides 1 y 2*

*Entrar con calma. Esperar un segundo antes de hablar. No saludar todavía.*

¿Cuántas aplicaciones utilizan cada día?

Correo electrónico, navegador, almacenamiento en la nube, herramientas de trabajo, asistentes virtuales, dispositivos inteligentes...

Ahora piensen en esto: toda esa tecnología fue creada para ayudarnos. Pero cada vez invertimos más tiempo **administrándola**.

Buscamos archivos que sabemos que existen. Repetimos tareas que una máquina podría realizar en segundos. Abrimos decenas de ventanas para obtener una respuesta simple.

La información está disponible. La tecnología también.

**Lo que falta es una forma más inteligente de conectarlas.**

Y eso nos lleva a una pregunta interesante:

*Pausa. Mirar al público.*

**¿Qué pasaría si mañana desaparecieran todas las interfaces?**

No habría menús. No habría ventanas. No habría configuraciones complejas.

Solo existiría una conversación.

Necesitas un archivo, lo pides. Necesitas ejecutar una tarea, la describes. Necesitas coordinar varios dispositivos, simplemente lo solicitas.

Suena futurista.

Sin embargo, la tecnología necesaria para lograrlo **ya existe**.

El verdadero desafío consiste en integrarla de forma útil, accesible y realmente inteligente.

Ese desafío es precisamente el que aborda **SOFÍA**.

*Avanzar al slide del problema. No presentarse todavía.*

---

## [02:30 – 03:30] EL PROBLEMA · *Slide 2*

Y antes de hablarles de SOFÍA, necesito ser honesto sobre el problema real.

Alexa, Google Assistant, Siri, Cortana. Los asistentes de voz ya existen, llevan años en el mercado.

¿Entonces por qué seguimos sintiéndonos esclavos de la tecnología?

Porque **cada vez que le hablan a uno de esos asistentes, su voz viaja a un servidor en otro continente**. Queda registrada. Se analiza. Alimenta modelos que no les pertenecen.

Porque funcionan perfectamente... mientras tengan señal. En zonas industriales, en viajes, en un corte de servicio, son inútiles.

Porque son cajas cerradas. No pueden integrarse con sus sistemas internos, con sus procesos propios, con lo que ya tienen construido.

Y porque están pensados para el mercado anglosajón. El español es un ciudadano de segunda categoría en esos ecosistemas.

**SOFÍA nació para resolver exactamente eso.**

---

## [03:30 – 04:00] PRESENTACIÓN · *Slide 3*

Mi nombre es **Julián Reinoso** y durante los últimos meses he estado desarrollando este proyecto con una idea clara:

Que la tecnología deje de ser algo que administramos constantemente y empiece a trabajar para nosotros.

SOFÍA es un **asistente de voz personal en español**, diseñado para correr **100% en tu equipo**, sin Internet, sin suscripciones, sin comprometer ni un byte de privacidad.

Hoy puede comprender instrucciones, acceder a información y realizar tareas dentro del computador donde se encuentra instalada.

Y la visión va mucho más allá: convertirse en el centro de un ecosistema conectado, donde las personas interactúen con toda su tecnología de la misma forma en que interactúan con otra persona: **mediante una conversación**.

Permítanme mostrársela.

---

## [04:00 – 08:30] DEMOSTRACIÓN EN VIVO · *Slide 4*

*Abrir SOFÍA en el equipo. Hablar con naturalidad, sin apresurarse.*

Esto que ven en pantalla es la interfaz de SOFÍA. Una ventana flotante, semitransparente, que se mantiene sobre las demás aplicaciones sin interferir con el trabajo.

Vamos a empezar con algo simple.

*Decir al micrófono:* **"Sofía, buenos días."**

*Esperar respuesta. Comentar:*

Nótese algo importante: desde el momento en que dije "Sofía" hasta que respondió, todo ocurrió localmente. Ningún audio salió de este equipo.

Ahora una consulta de información en tiempo real:

*Decir:* **"Sofía, ¿qué clima hay en Ibagué?"**

*Esperar respuesta. Comentar:*

Está consultando una API de clima —Open-Meteo— que no requiere ninguna clave de acceso y no recibe datos personales. Solo coordenadas geográficas.

Ahora control de escritorio:

*Decir:* **"Sofía, abre el bloc de notas."**

*Esperar. Comentar:*

Eso es control real del sistema operativo. No está simulado.

Y para cerrar la demo, una pregunta libre:

*Decir:* **"Sofía, ¿cuál es la diferencia entre inteligencia artificial y machine learning?"**

*Esperar respuesta. Comentar:*

Esa respuesta la generó un modelo de lenguaje —Qwen3-8B— corriendo en la GPU de este equipo. Sin OpenAI, sin Anthropic, sin ningún servicio externo. **Completamente local.**

*Volver a las diapositivas.*

---

## [08:30 – 10:00] CÓMO FUNCIONA · *Slides 5 y 6*

Bien, ahora déjenme explicarles **por qué funciona así de bien**.

Cuando dicen "Sofía", este equipo está haciendo varias cosas al mismo tiempo.

Primero, hay un modelo de detección de voz —Silero-VAD— que filtra el silencio de forma continua. Es liviano, corre en CPU, siempre encendido.

Cuando detecta que alguien habla, entra en juego un primer modelo de transcripción: **Whisper "tiny"**. Su único trabajo es buscar la palabra "Sofía". Es pequeño, rápido, barato.

¿Por qué no usar un solo modelo para todo? Porque en producción real, el modelo pequeño confundía "Sofía" con "novia" o "vía". Lo documentamos, lo medimos, y la solución fue usar **dos modelos separados**: uno barato para la detección, uno más preciso para el comando real.

*Señalar el slide del pipeline.*

En el momento en que se detecta la wake-word, ocurren tres cosas en paralelo: se reproduce un audio pre-grabado que dice "Dime", y mientras el usuario termina de formular su pregunta, el sistema ya está cargando el modelo grande en segundo plano.

**El usuario nunca espera la carga del modelo. Esa espera está oculta en su propio tiempo de pronunciación.**

Una vez transcrito el comando, entra el **Router**: un despachador que revisa las skills registradas en orden de prioridad. El primer match gana. Sin redes neuronales, sin embeddings, sin ambigüedad.

Si ninguna skill reconoce el comando, recién ahí se activa el LLM local —Qwen3-8B cuantizado— como fallback conversacional.

---

## [10:00 – 11:00] ARQUITECTURA Y DIAGRAMAS · *Slides 7–11*

*Avanzar rápido por los diagramas. Uno o dos puntos por slide, no leer el diagrama completo.*

Este es el **diagrama de componentes**. La regla central: las skills dependen del núcleo, nunca al revés. Agregar una skill nueva es crear un archivo y una línea de registro. El núcleo no cambia.

El **diagrama de casos de uso** muestra los tres canales de entrada: voz, texto y botón. Los tres pasan siempre por el mismo Router. El LLM aparece como extensión del caso "Conversar libremente", lo que confirma que es la última instancia, no la primera.

El **diagrama de secuencia** traza un comando real de principio a fin. El bloque ALT al final es el punto clave: el LLM solo se activa cuando ningún skill resuelve el comando. Eso tiene un impacto directo en el rendimiento.

---

## [11:00 – 12:30] DECISIONES TÉCNICAS · *Slide 12*

Este proyecto no solo implementa tecnología. **Documenta por qué tomó cada decisión**.

Tenemos doce registros de decisiones de arquitectura —ADRs— que detallan no solo lo que elegimos, sino lo que descartamos y por qué.

Algunos ejemplos:

**Router por keywords, no por NLU.** Podríamos haber usado clasificadores semánticos con embeddings. Son más potentes. Pero también son más lentos, más difíciles de depurar y más costosos en hardware. Para el caso de uso actual, un matcher determinista con cero ambigüedad es la mejor decisión. Si la necesidad cambia, el ADR está documentado.

**Open-Meteo en lugar de OpenWeatherMap.** No requiere API key, no tiene límite de peticiones gratuitas, y para el propósito del proyecto es igual de preciso. Una dependencia menos que gestionar.

**JSON plano en lugar de base de datos.** Un usuario, decenas de registros. SQLite sería overhead injustificado. La decisión puede revisarse si el volumen crece, y el ADR registra exactamente cuándo tiene sentido hacerlo.

Estas decisiones no son improvisación. Son **ingeniería documentada**.

---

## [12:30 – 13:30] RESULTADOS · *Slide 16*

En pruebas realizadas con el hardware de este equipo —Intel de 12 núcleos, 31 gigabytes de RAM, GPU RTX 3050 de 4 gigabytes— los resultados son los siguientes.

**Ocho skills funcionales**: clima, agenda, sistema, notas, web, tiempo, rutina y control de escritorio.

**Tasa de éxito del 100%** en una prueba de cinco consultas variadas.

**Consumo de RAM**: 41 megabytes en reposo, 543 megabytes con todos los modelos cargados. El incremento corresponde a la carga inicial de módulos, no a una fuga de memoria.

**Espacio en disco**: aproximadamente 11 gigabytes, incluyendo el modelo de lenguaje cuantizado, los modelos de voz y el entorno Python.

Y lo más importante: **todo eso con cero costo operativo recurrente**. Sin suscripciones, sin APIs de pago, sin infraestructura en la nube.

---

## [13:30 – 14:30] PRIVACIDAD Y VISIÓN · *Slides 14 y 18*

Antes de cerrar, quiero destacar algo que no suele mencionarse en este tipo de proyectos.

La privacidad de SOFÍA no es una característica. Es una **consecuencia de la arquitectura**.

Cuando todo corre localmente, la privacidad no depende de las políticas de una empresa ni de sus términos de servicio. Depende de la física: el audio no puede filtrarse si nunca sale del equipo.

Para entornos corporativos, esto no es un detalle menor. Es un requisito de compliance que SOFÍA cumple por diseño.

Y en cuanto al camino hacia adelante:

El aprendizaje activo —aplicar automáticamente las correcciones que el sistema registra— es el siguiente paso inmediato. Los datos ya se están acumulando.

La clonación de voz con Qwen3-TTS-Base permitirá que SOFÍA hable con la voz del usuario.

Y la extensión a múltiples dispositivos en red es la visión a mediano plazo: un ecosistema donde todas las pantallas, todos los dispositivos, responden a la misma conversación.

---

## [14:30 – 15:00] CIERRE · *Slide 19*

SOFÍA demuestra que construir un asistente de voz serio, en español, que corra completamente offline, con control real del escritorio y conversación libre, **es posible hoy**.

No en el futuro. Hoy.

Con tecnología abierta, sin depender de grandes plataformas, y con una arquitectura que cualquier equipo puede extender, auditar y adaptar.

*Pausa breve.*

Hoy puede comprender instrucciones, acceder a información y realizar tareas dentro del computador donde está instalada.

Mañana, puede ser el centro de todo lo demás.

Mi nombre es **Julián Reinoso**. Esto es **SOFÍA**.

Gracias.

*Esperar aplauso. Luego abrir a preguntas.*

---

## PREGUNTAS FRECUENTES DEL JURADO

*Tenerlas memorizadas. No improvisar en caliente.*

---

**"¿Por qué Python y no Rust o C++?"**

Python tiene el ecosistema de IA más maduro del mundo. faster-whisper, llama-cpp-python, Silero-VAD, PyQt6: todas estas librerías existen en Python y no tienen equivalente inmediato en otros lenguajes. Para un prototipo funcional en meses, Python fue la decisión correcta. Si la siguiente fase requiere mayor rendimiento en partes específicas, se pueden reemplazar módulos puntuales, no todo el sistema.

---

**"¿Qué tan preciso es el reconocimiento de voz en español?"**

Whisper "base" fue entrenado en audio multilingüe que incluye español. En pruebas con acento colombiano, el reconocimiento es sólido para comandos directos. El mayor riesgo es en entornos ruidosos o con acento muy marcado. Ese es un vector claro de mejora para la siguiente versión: benchmark formal de WER en condiciones reales.

---

**"¿Puede escalar a múltiples usuarios?"**

El diseño actual es deliberadamente de un solo usuario: un archivo JSON, un hilo de escucha, una instancia. Escalar implicaría separar el estado por sesión y paralelizar el pipeline. Es factible, pero requiere rediseño de la capa de persistencia. El ADR correspondiente documenta exactamente ese punto de decisión.

---

**"¿Qué diferencia a SOFÍA de una integración de ChatGPT con comandos de voz?"**

Tres cosas fundamentales: privacidad total —no hay ninguna llamada a APIs externas para las conversaciones—, funcionamiento sin Internet, y control real del sistema operativo mediante pywinauto. ChatGPT con voz puede responder preguntas; SOFÍA puede abrir, cerrar y controlar aplicaciones en tu equipo.

---

**"¿Cuánto cuesta el hardware mínimo para usarla?"**

Para el modo básico —sin GPU, con pyttsx3 en lugar de Qwen-TTS— cualquier PC con 8 GB de RAM y un procesador de los últimos 8 años es suficiente. El modelo de lenguaje corre en CPU, más lento pero funcional. La GPU solo es necesaria para la síntesis de voz de alta calidad.

---

*Fin del guion.*
