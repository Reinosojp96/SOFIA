# SOFÍA - versión mínima funcional

Esqueleto reorganizado: 12 archivos, sin módulos muertos. Diseñado para
arreglar los 3 problemas que tenías:

1. **Un solo router** (`core/router.py`): cada skill se registra una vez
   con sus keywords. Ya no hay dos clasificadores compitiendo, así que
   "clima en Ibagué" siempre va por el mismo camino, sin importar cómo
   esté redactada la frase.

2. **Voz**: `voz/escuchar.py` calibra el ruido ambiental una sola vez al
   inicio (no en cada intento), y usa `phrase_time_limit` para no cortar
   la frase. Eso reduce mucho los "tengo que repetirlo".

3. **GUI separada de la lógica**: `ui/widget.py` solo dibuja y llama a
   `on_comando(texto)` / `on_hablar_voz()`. La lógica vive en `core/` y
   `skills/`, así que la GUI nunca puede "romper" el procesamiento.

## Instalación

```bash
python -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### IA local (llama.cpp)

Coloca tu modelo `.gguf` en `data/modelo.gguf`, o define la variable de
entorno `SOFÍA_MODEL_PATH` apuntando a tu archivo .gguf.

Si no tienes GPU o no quieres instalar la versión CUDA de torch, NO la
necesitas para este esqueleto: `llama-cpp-python` corre en CPU sin
problema (más lento, pero funciona). El `pip install torch ... cu118`
que tenías solo es necesario si usas otra librería con torch+CUDA
directamente (por ejemplo modelos de visión), que en este esqueleto no
están incluidos.

### Clima

Define la variable de entorno `OPENWEATHER_API_KEY` con tu clave de
OpenWeatherMap (gratis). Si no la defines, SOFÍA te avisará que no puede
consultar el clima real, en vez de inventar datos.

```bash
export OPENWEATHER_API_KEY="tu_clave_aqui"
```

## Ejecutar

```bash
python main.py
```

## Cómo agregar una skill nueva

1. Crea `skills/mi_skill.py` con:
   - `KEYWORDS = ["palabra1", "palabra2"]`
   - una función `manejar(texto) -> str` (o el nombre que quieras)
2. En `main.py`, dentro de `registrar_skills()`:
   ```python
   from skills import mi_skill
   router.registrar("mi_skill", mi_skill.KEYWORDS, mi_skill.manejar)
   ```

Así escalas sin tocar el router ni el resto del código.

## Qué falta / próximos pasos sugeridos

- `skills/sistema.py` tiene un mapa `APPS` con nombres de ejemplo para
  Linux/Windows: ajústalo a las apps resofias de tu equipo para la demo.
- Las alarmas se guardan en `data/memoria.json` pero todavía no hay un
  "reloj" que las dispare; si quieres que suenen, se puede agregar un
  hilo que revise cada minuto.
- Recordatorios/eventos: `core/memoria.py` ya guarda todo en JSON, solo
  falta una skill que los liste por voz ("qué tengo agendado hoy").
