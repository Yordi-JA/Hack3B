# Hack3B · Reto 1 Expedientes

Sistema multiagente en LangChain que revisa el expediente legal de un inmueble, detecta faltantes e inconsistencias y emite una recomendación con evidencia: **Cumple / Requiere revisión / No cumple**. El enunciado está en [CONTEXT.md](CONTEXT.md).

**Entrega: hoy a las 17:00.**

## Decisiones pendientes

Que cada responsable la resuelva, la anote aquí y avise en el grupo.

| # | Decisión | Responsable | Para | Estado |
| :- | :--- | :--- | :--- | :--- |
| 1 | Proveedor y modelo del LLM, y de quién es la API key con créditos. | Carlos | 10:15 | **Resuelto:** Anthropic `claude-haiku-5-5` (~40 veces más barato que Opus, ~$2 USD el día). Key de Julián con $5 prepagados, sin recarga automática. Ver [Uso de la API](#uso-de-la-api-créditos). |
| 2 | Langfuse: instancia de la organización, cloud propia o local con Docker. Una cuenta cloud propia recibiría el contenido de los documentos (regla 06). | Juan Pablo | 10:30 | Pendiente |
| 3 | Orquestador con LangGraph o con LangChain puro. Confirmar con los jueces que LangGraph cuenta como "sobre LangChain". | Carlos | 11:00 | Pendiente |
| 4 | UI en Streamlit (llama directo a `analizar_expediente`, sin API). | Yordi | 10:15 | Propuesto |
| 5 | Guías y criterios oficiales por tipo: ¿dónde están? Sin ellas las reglas son suposiciones. | Todos | Ya | Pendiente |
| 6 | Tope de páginas por escritura (hay de 50 páginas). | Carlos + Julián | 11:00 | Pendiente |
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

## Uso de la API (créditos)

Hay **$5 USD prepagados para todo el equipo** y no se recargan solos: si se acaban, la API deja de responder para los 5. Con estas reglas el día completo cuesta ~$2.

**Modelo**

1. **`claude-haiku-5-5` para todo** (`LLM_MODEL` en el `.env`). Subir un agente a Sonnet u Opus solo si se demuestra que Haiku falla en ese caso, y avisando antes en el grupo: Opus cuesta 40 veces más.
2. **`effort="low"` y `max_tokens` acotado** (≈4000 para extracción) al pedir el modelo: `get_llm(effort="low", max_tokens=4000)`.

**No repetir trabajo**

3. **Nadie corre OCR.** El texto de los 63 documentos ya está en `cache/` (se comparte por Drive). Las imágenes nunca se vuelven a mandar al modelo; los agentes trabajan sobre el texto.
4. **Desarrollar contra un solo expediente** (los sintéticos `01–04` son ideales). Correr los 63 documentos solo en la integración de las 13:00 y en la demo.
5. **Guardar en disco lo que ya respondió el modelo** mientras se desarrolla (ej. `cache/analisis/<archivo>.json`) y leerlo de ahí si el documento y el prompt no cambiaron. Cambiar código que no toca el prompt no debe costar llamadas.
6. **`pytest` nunca llama a la API**: las pruebas usan `cache/` o `ejemplos/`.

**Llamadas eficientes**

7. **Una llamada por documento** con todos los campos juntos (`with_structured_output(..., method="json_schema")`), no una por campo.
8. **Mandar solo el texto necesario**: las páginas que tienen datos del inmueble, no anexos, planos ni hojas en blanco (`notas` del caché dice qué páginas son de otro tipo o ilegibles).
9. **Lo que se resuelve con código no va al LLM**: fechas, vigencias, aritmética de superficies, normalización de nombres y direcciones, comparaciones exactas. El LLM solo extrae y juzga casos ambiguos.
10. **Máximo 6 llamadas en paralelo y sin bucles de reintento propios** (LangChain ya reintenta los 429). Un bucle sin tope es la forma más rápida de vaciar el saldo.

**Vigilar**

11. Antes de una corrida grande, avisar en el grupo. El saldo y el gasto se ven en la consola (`Spending & usage`); si se pasa de **$3**, Julián avisa y se para todo lo que no sea demo.

## Arranque

**Un solo comando, Windows o Mac** (crea `.venv`, instala dependencias, crea `.env`, descomprime los zip con los nombres bien y corre la prueba):

```bash
python configurar.py --zips RUTA/A/LA/CARPETA/DE/LOS/ZIP     # en Windows, si no hay "python": py configurar.py ...
```

Luego: pegar la `ANTHROPIC_API_KEY` en `.env` y copiar la carpeta `cache/` compartida. Pasos manuales equivalentes:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # y llenar las llaves
python -m pytest -q         # valida que el ejemplo cumple el contrato
```

En macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # y llenar ANTHROPIC_API_KEY
python -m pytest -q
```

## Caché OCR (Julián)

Nadie necesita correr el OCR: se comparte la carpeta `cache/` por USB o Drive y se copia en la raíz del repo. `leer_documento()` la usa sola.

Para regenerarlo (solo quien lo genera):

```bash
python -m expedientes.agentes.ingesta                     # Claude con visión, llena cache/
python -m expedientes.agentes.ingesta --motor tesseract   # respaldo local sin API key (brew install tesseract tesseract-lang; pip install pytesseract)
```

- Se puede interrumpir y volver a correr: solo procesa lo que falta.
- Tope de 15 páginas por documento (`--max-paginas`, decisión 6), anotado en `notas` del `DocumentoLeido`.
- Páginas borrosas: se mide la nitidez de cada página localmente; bajo el umbral (5.0, calibrado con el set) la página queda `ILEGIBLE` y su texto se descarta, porque el modelo "lee" páginas borrosas inventando datos. Así los 3 sintéticos `...` salen `ILEGIBLE`.
- `notas` también dice qué páginas son de otro tipo (ej. un predial con la escritura anexa en p2-p4).
- Resultado con `claude-haiku-5-5`: 63/63 tipos correctos, ~4 min, ~$0.15 USD.
- Las llamadas del OCR no se mandan a Langfuse salvo con `OCR_LANGFUSE=1` (la traza llevaría la imagen del documento).
- Para descomprimir los zip en Mac usar doble clic o `ditto -x -k archivo.zip Documentos/`: así los nombres con acento coinciden con las llaves del caché.

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
