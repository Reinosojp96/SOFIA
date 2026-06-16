# SOFÍA

Asistente de voz personal **offline-first** para Windows, en español. STT,
TTS e IA conversacional corren 100% en local (sin nube, sin API keys
obligatorias). Interfaz flotante con PyQt6, activación por voz diciendo
"Sofía" o por botón/texto.

Para el detalle completo de arquitectura, decisiones de diseño y
diagramas UML, ver [CLAUDE.md](CLAUDE.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
y [docs/uml/](docs/uml/). Para los resultados de benchmark (precisión,
latencia, recursos, falsos despertares, estrés), ver
[docs/RESULTADOS.md](docs/RESULTADOS.md).

## Instalación

### Camino recomendado: instalador

```bash
python setup.py
```

El instalador detecta tu hardware (RAM, GPU/CUDA), crea el entorno
virtual, instala dependencias, descarga los modelos (Whisper, Silero-VAD,
Qwen3-TTS y el LLM local) y genera `.env` + un acceso directo
`iniciar_sofia.bat`.

### Camino manual

```bash
python -m venv venv
venv\Scripts\activate        # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
```

#### IA local (llama.cpp)

Coloca tu modelo `.gguf` en `data/modelo.gguf`, o define
`SOFIA_MODEL_PATH` apuntando a tu archivo. Si no existe, `core/ia.py` lo
descarga automáticamente desde Hugging Face (Qwen3-8B-GGUF, ~4.5 GB) la
primera vez que se usa.

`llama-cpp-python` corre en CPU sin problema (más lento, pero funciona)
si no tienes GPU.

#### Clima

No requiere configuración: usa [Open-Meteo](https://open-meteo.com/), que
no necesita API key.

## Ejecutar

```bash
python main.py
```

## Modelos y almacenamiento

Todos los modelos viven dentro de `data/`, así que borrar esa carpeta
(junto con `venv/`) desinstala SOFÍA por completo sin dejar residuos:

| Modelo | Ubicación | Tamaño aprox. |
|---|---|---|
| LLM conversacional (Qwen3-8B) | `data/modelo.gguf` | ~0.6-4.7 GB según variante |
| TTS Qwen3-TTS CustomVoice | `data/qwen3_tts/` | ~2.3 GB |
| TTS Qwen3-TTS Base (clonación de voz) | `data/qwen3_tts_base/` | ~2.3 GB |
| STT Faster-Whisper (tiny + base) | `data/modelos/whisper/` | ~0.2 GB |
| Silero-VAD | `data/modelos/torch_hub/` | ~35 MB |
| Audio pre-renderizado (frases fijas) | `data/audio_estatico/` | ~1 MB |

Usa `python herramientas/medir_espacio.py` para ver el desglose real en
tu instalación y confirmar que no quedan residuos fuera de `data/`.

## Skills disponibles

| Skill | Qué hace |
|---|---|
| `rutina` | Saludo según la hora + resumen de clima y agenda |
| `clima` | Clima actual por ciudad (Open-Meteo) |
| `tiempo` | Hora, fecha, alarmas, eventos y tareas pendientes |
| `sistema` | Abrir/cerrar apps, crear/copiar/mover/eliminar archivos y carpetas |
| `web` | Búsqueda en Google, reproducir en YouTube, noticias |
| `notas` | Crear y leer notas (compatibles con NebulaNotes) |
| `aprendizaje` | Estadísticas de uso y registro de correcciones manuales |
| `control_escritorio` | Minimizar/maximizar/cerrar ventanas, leer contenido de la app activa, resolver referencias implícitas ("ciérrala") |

Si ninguna skill matchea, cae al fallback conversacional con el LLM local.

## Herramientas de diagnóstico

En `herramientas/` — pensadas para auditar el producto antes de una
entrega o sustentación. Cada una guarda su reporte en `data/logs/` (JSON +
CSV, para poder graficar fácilmente en Excel/Sheets):

| Herramienta | Qué mide |
|---|---|
| `python herramientas/medir_espacio.py` | Desglose de espacio en disco por componente, y residuos en cachés globales antiguas |
| `python herramientas/medir_recursos.py` | CPU/RAM/VRAM por etapa del pipeline (reposo/escuchando/procesando/hablando) — requiere correr SOFÍA con `SOFIA_DIAGNOSTICO=1` en paralelo |
| `python herramientas/test_precision.py` | WER, precisión de intents y latencia (STT/router+IA/TTS) en silencio, ruido moderado y a distancia, con guion interactivo en `herramientas/guion_pruebas.json` |
| `python herramientas/test_falsos_despertares.py --minutos 120` | Tasa de falsos despertares del wake-word durante audio ambiente |
| `python herramientas/test_estres.py --consultas 50` | RAM/VRAM inicial vs. final tras N consultas seguidas, para detectar fugas de memoria |

Ver [docs/RESULTADOS.md](docs/RESULTADOS.md) para el informe consolidado
con los datos ya obtenidos en este equipo.

## Requisitos de hardware

Basado en los datos de [docs/RESULTADOS.md](docs/RESULTADOS.md) (equipo de
prueba: 12 núcleos, 32 GB RAM, RTX 3050 4GB):

| | Mínimos | Recomendados |
|---|---|---|
| CPU | 4 núcleos | 8+ núcleos |
| RAM | 8 GB | 16 GB+ |
| GPU | Opcional (CPU funciona, más lento) | NVIDIA con 4 GB+ VRAM (Whisper base + Qwen-TTS) |
| Espacio en disco | 15 GB | 20 GB+ |

## Cómo agregar una skill nueva

1. Crea `skills/mi_skill.py` con:
   - `KEYWORDS = ["palabra1", "palabra2"]`
   - una función `manejar(texto) -> str` (o el nombre que quieras)
2. En `main.py`, dentro de `registrar_skills()`:
   ```python
   from skills import mi_skill
   router.registrar("mi_skill", mi_skill.KEYWORDS, mi_skill.manejar)
   ```

Así escalas sin tocar el router ni el resto del código. El orden de
registro importa: si dos skills comparten una keyword, gana la que se
registró primero.
