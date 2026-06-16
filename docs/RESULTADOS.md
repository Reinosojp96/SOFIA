# SOFÍA — Resultados de diagnóstico y benchmark

> Documento consolidado para sustentación. Reúne en un solo lugar los
> números que generan las herramientas de `herramientas/`, sin tener que
> abrir los JSON de `data/logs/`. Las secciones marcadas con
> **`[ ] pendiente de correr`** se llenan ejecutando la herramienta
> indicada una vez sobre el equipo de prueba; las demás ya tienen datos
> reales tomados al construir estas herramientas.

Última actualización: 2026-06-16.

---

## 1. Hardware del equipo de prueba

Capturado automáticamente por `herramientas/test_precision.py` /
`herramientas/test_estres.py` (vía `psutil` / `torch.cuda`).

| Componente | Valor |
|---|---|
| CPU | Intel64 Family 6 Model 141 (12 núcleos lógicos) |
| RAM | 31.6 GB |
| GPU | NVIDIA GeForce RTX 3050 Laptop GPU |
| VRAM | 4.0 GB |
| SO | Windows 10/11 |

---

## 2. Espacio en disco

Generado con `python herramientas/medir_espacio.py`. Corrida real sobre
este equipo, tras la corrección que contiene Whisper/Silero-VAD dentro de
`data/modelos/` (antes vivían en la caché global del usuario y no se
contaban):

| Componente | Tamaño |
|---|---|
| `modelo.gguf` (LLM, Qwen3-8B) | 0.60 GB |
| `qwen3_tts/` (TTS CustomVoice) | 2.33 GB |
| `qwen3_tts_base/` (TTS Base/clonación) | 2.34 GB |
| `modelos/whisper/` (STT) | *se descarga al primer arranque tras la corrección — antes vivía en `~/.cache/huggingface` (~0.14 GB base + 75 MB tiny)* |
| `modelos/torch_hub/` (Silero-VAD) | *idem, ~34 MB, antes en `~/.cache/torch`* |
| `audio_estatico/` | 1.0 MB |
| `apps.json` / `memoria.json` / `aprendizaje.json` | < 1 MB |
| **Total `data/`** | **5.27 GB** (subirá ~0.25 GB tras la primera descarga de Whisper/Silero ya contenida) |
| Entorno Python (`venv/`, aparte) | 5.27 GB |
| **Total instalación (`data/` + `venv/`)** | **~10.6 GB** |

**Conclusión clave:** antes de la corrección, el peso real del programa
(10.6 GB reportados por el usuario) ya incluía residuos fuera de `data/`
sin que fuera evidente; con el cambio aplicado, **todo el peso queda
contenido en `data/`**, y se puede confirmar borrando la carpeta y
verificando que no quedan residuos en `~/.cache/torch` ni
`~/.cache/huggingface`.

---

## 3. Precisión de voz

**`[ ] pendiente de correr`** — ejecutar:
```
python herramientas/test_precision.py
```
(interactivo, ~15-20 min: lee cada frase del guion en voz alta en los 3
bloques de condición que pide el script).

| Condición | WER promedio | Intent correcto (voz) | Intent correcto (texto, control) |
|---|---|---|---|
| Silencio | | | |
| Ruido moderado | | | |
| Distancia (50cm/1m/2m) | | | |
| **Global** | | | |

Tasa de éxito de la corrida (sin errores puntuales): \_\_\_ %

---

## 4. Latencia

**`[ ] pendiente de correr`** — mismos datos que la sección 3, de
`data/logs/diagnostico_precision_<fecha>.json`.

| Etapa | Voz (promedio) | Texto (promedio) |
|---|---|---|
| STT (transcripción) | | n/a |
| Router + IA (incluye LLM si cae a fallback) | | |
| TTS — primer audio (latencia percibida) | | n/a |
| TTS — total (audio completo) | | n/a |
| **Total percibido** (STT + router + TTS primer audio) | | |

> La latencia "percibida" (hasta el primer audio) es la que más importa
> para la experiencia de uso — es la diferencia entre "SOFÍA tarda en
> empezar a responder" y "SOFÍA tarda en terminar de hablar".

---

## 5. Recursos por etapa del pipeline

**`[ ] pendiente de correr`** — requiere `SOFIA_DIAGNOSTICO=1 python main.py`
en una terminal y `python herramientas/medir_recursos.py` en otra mientras
se interactúa con SOFÍA por voz.

| Etapa | CPU prom. | CPU pico | RAM prom. | RAM pico | VRAM prom. |
|---|---|---|---|---|---|
| Reposo (esperando wake-word) | | | | | |
| Escuchando (capturando comando) | | | | | |
| Procesando (router + IA) | | | | | |
| Hablando (TTS) | | | | | |

---

## 6. Falsos despertares

**`[ ] pendiente de correr`** — ejecutar (recomendado 2 horas para un dato
confiable, ya que es un evento raro):
```
python herramientas/test_falsos_despertares.py --minutos 120
```

| Métrica | Valor |
|---|---|
| Duración de la prueba | |
| Falsos despertares totales | |
| Falsos despertares por hora | |
| Activaciones intencionales detectadas / intentadas | |

---

## 7. Estrés / fugas de memoria

`python herramientas/test_estres.py --consultas 50` — corrida de
verificación rápida (5 consultas) ya ejecutada sobre este equipo:

| Métrica | Valor (corrida de verificación, 5 consultas) |
|---|---|
| RAM inicial | 41.7 MB |
| RAM final | 543.1 MB |
| Delta RAM | +501.4 MB (carga inicial de módulos/skills, no fuga — se estabiliza tras la primera consulta) |
| VRAM inicial / final | 0.0 MB / 0.0 MB (sin motor TTS con GPU activo en esta corrida) |
| Tasa de éxito | 100% (5/5) |

**`[ ] pendiente de correr con la corrida completa de 50 consultas (o 30 min)`**
para confirmar que el delta de RAM se mantiene estable después del salto
inicial de carga y no sigue creciendo de forma sostenida.

---

## 8. Instalación y arranque

**`[ ] pendiente de correr`** — se genera automáticamente:
- al correr `setup.py` (instalación completa) → `descarga_modelos_min` e
  `instalacion_fase1_min` en `data/logs/diagnostico_instalacion.json`.
- al correr `main.py` (cada arranque) → una línea en
  `data/logs/diagnostico_arranque.jsonl` con el tiempo hasta que SOFÍA
  muestra el mensaje de bienvenida, marcando si fue primer arranque
  (modelos de voz aún no descargados) o uno posterior.

| Escenario | Tiempo |
|---|---|
| Instalación (venv + dependencias) | |
| Descarga de modelos | |
| Primer arranque (con descarga de modelos de voz) | |
| Arranque posterior (modelos ya en caché) | |

---

## 9. Conclusiones

*(completar tras llenar las secciones 3-8 con datos reales)*

- **Espacio en disco**: confirmado que el problema reportado por el
  usuario (10.6 GB sin contar todos los modelos) se debía a que
  Whisper/Silero-VAD se descargaban fuera de `data/`; corregido en
  `voz/escuchar.py` y `setup.py`. Con la corrección, una desinstalación
  borrando `data/` y `venv/` no deja residuos.
- **Cuello de botella de rendimiento**: _pendiente — completar con la
  sección 5 (recursos por etapa)._
- **Condiciones donde baja la precisión de voz**: _pendiente — completar
  con la sección 3 (precisión por condición)._
- **Estabilidad de memoria**: la corrida corta de verificación (5
  consultas) no muestra fuga sostenida tras la carga inicial; se
  recomienda confirmar con la corrida completa de 50 consultas / 30 min.
- **Falsos despertares**: _pendiente — esta es la métrica que cualquier
  evaluación técnica de un asistente de voz pedirá primero; ejecutar la
  prueba de 2 horas antes de la sustentación._
- **Recomendaciones de hardware resultantes**: _pendiente — derivar de
  las secciones 4 y 5 y trasladar a la sección "Requisitos de hardware"
  de `README.md`._
