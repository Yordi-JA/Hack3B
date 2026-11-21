# Hack3B · Reto 1 Expedientes

Sistema multiagente en LangChain que revisa el expediente legal de un inmueble, detecta faltantes e inconsistencias y emite una recomendación con evidencia: **Cumple / Requiere revisión / No cumple**. El enunciado está en [CONTEXT.md](CONTEXT.md).

**Entrega: hoy a las 17:00.**

## Decisiones pendientes

Que cada responsable la resuelva, la anote aquí y avise en el grupo.

| # | Decisión | Responsable | Para | Estado |
| :- | :--- | :--- | :--- | :--- |
| 1 | Proveedor y modelo del LLM, y de quién es la API key con créditos. | Carlos | 10:15 | **Resuelto**: Anthropic, `claude-haiku-5-5` con `effort="low"` y `max_tokens=4000`. Key cargada por el equipo. |
| 2 | Langfuse: instancia de la organización, cloud propia o local con Docker. Una cuenta cloud propia recibiría el contenido de los documentos (regla 06). | Juan Pablo | 10:30 | Pendiente |
| 3 | Orquestador con LangGraph o con LangChain puro. | Carlos | 11:00 | **Resuelto**: LangChain puro. El orquestador es un pipeline determinista con `ThreadPoolExecutor(max_workers=5)` para paralelizar los 4 agentes por tipo; el flujo es lineal y no requiere grafo. |
| 4 | UI en Streamlit (llama directo a `analizar_expediente`, sin API). | Yordi | 10:15 | Propuesto |
| 5 | Guías y criterios oficiales por tipo: ¿dónde están? Sin ellas las reglas son suposiciones. | Todos | Ya | Pendiente |
| 6 | Tope de páginas por escritura (hay de 50 páginas). | Carlos + Julián | 11:00 | **Resuelto**: 15 páginas máximo (primeras 5 + hasta 10 con palabras clave: superficie, colindancias, catastral, folio real, gravamen, notario, etc.). |
| 7 | Tolerancia de superficie para la validación cruzada. | Diego | 12:00 | Pendiente |

Nota sobre el LLM: 57 de 62 PDFs son escaneos, así que el modelo tiene que tener visión. Cambiar de proveedor es cambiar `LLM_PROVIDER` y `LLM_MODEL` en el `.env` (`expedientes/config.py`). Una key nueva tiene límites bajos por minuto: el OCR masivo debe correr con 5-10 llamadas en paralelo como máximo.

## Equipo y ramas

Cada quien trabaja en su rama y hace push directo. Para traer cambios del contrato: `git merge main`.

| Persona | Rama | Archivos |
| :--- | :--- | :--- |
| Juan Pablo | `juanpablo/uso-suelo` | `agentes/uso_suelo.py`, `agentes/dictamen.py`, Langfuse |
| Julián | `julian/predial` | `agentes/predial.py`, `agentes/ingesta.py`, caché OCR |
| Diego | `diego/alineamiento` | `agentes/alineamiento.py`, `agentes/cruce.py` |
| Carlos | `carlos/escrituras` | `agentes/escritura.py`, `orquestador.py`, `config.py` |
| Yordi | `yordi/ui` | `app.py` |

Cada quien toca solo sus archivos. `schemas.py` es de todos: si hay que cambiarlo, se avisa, se cambia en `main` y todos hacen `git merge main`.

## Contrato

`expedientes/schemas.py` es la fuente de verdad. Resumen del flujo:

```
archivo ─► ingesta.leer_documento()      ─► DocumentoLeido       (texto por página, tipo, legibilidad)
        ─► <tipo>.analizar(doc, ctx)     ─► DocumentoAnalizado   (datos con evidencia + hallazgos del documento)
        ─► cruce.validar_cruzado(docs)   ─► list[Inconsistencia] (qué dice cada documento y dónde)
        ─► dictamen.dictaminar(...)      ─► Dictamen             (recomendación, confianza, explicación)
orquestador.analizar_expediente(rutas) encadena todo. La UI solo consume Dictamen.
```

Reglas del contrato:

- **Todo dato y todo hallazgo lleva `Evidencia`** (archivo, página, cita literal). Sin evidencia no hay hallazgo.
- **Los campos comunes** (`propietario`, `direccion`, `superficie_terreno_m2`, `clave_catastral`, `numero_oficial`, fechas y autoridad) se llaman igual en los 4 tipos y se llenan con `valor` y `normalizado`. La validación cruzada compara `normalizado`.
- **Lo específico de un tipo** va en `datos.especificos` con claves en snake_case (sugerencias en el docstring de cada agente).
- **Las vigencias se evalúan contra `ctx.fecha_referencia`**, nunca contra `date.today()` dentro de un agente.
- **Prefijos de reglas:** `ESC-`, `PRE-`, `ALI-`, `USO-`, `CRU-`, `EXP-`.
- Un documento `ILEGIBLE` no extrae datos inventados: sus reglas salen `NO_EVALUABLE`.

`ejemplos/dictamen_ejemplo.json` es un dictamen completo con datos inventados. La UI se construye sobre él con `analizar_expediente([], usar_ejemplo=True)`.

## Arranque

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # y llenar las llaves
python -m pytest -q         # valida que el ejemplo cumple el contrato
```

## Documentos (regla 06)

Los documentos del reto van en `Documentos/` (subcarpetas por tipo) y el texto OCR en `cache/`. Ambos están en `.gitignore`: **no se suben al repo ni a ningún servicio fuera del equipo**. El caché se comparte por USB o Drive del equipo.

Datos útiles del set:

- 62 PDFs + 1 JPEG, 249 páginas. Solo 5 PDFs tienen capa de texto.
- Los archivos `01–04` con sufijo vacío, `!!`, `...` y `v` son 4 expedientes sintéticos completos con errores plantados (vigencias vencidas, adeudos de predial, afectaciones en alineamiento, encabezado que no cuadra con la fecha). El de `...` está borroso a propósito. Son el mejor set de prueba y de demo.
- Los demás son expedientes reales parciales.

## Plan del día

| Hora | Hito |
| :--- | :--- |
| 10:30 | Caché OCR listo (Julián) y decisiones 1, 2 y 4 resueltas |
| 13:00 | **Integración**: un expediente real de punta a punta hasta la UI, aunque sea feo |
| 15:30 | Se congelan funcionalidades |
| 16:30 | Demo grabada de respaldo |
| 17:00 | Entrega y pitch |
