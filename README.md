# Hack3B · Reto 1 Expedientes

Sistema multiagente (LangChain + LangGraph) que revisa el expediente legal de un inmueble
para Tiendas 3B, detecta faltantes e inconsistencias y emite una recomendación con evidencia:
**Cumple / Requiere revisión / No cumple**. El enunciado completo está en [CONTEXT.md](CONTEXT.md).

## Arquitectura de agentes

```
Expediente (PDFs) ─► Ingesta (PDF → páginas: texto + imagen)
                        │
                        ▼
             1. Agente Clasificador      ¿Escritura, Predial, Alineamiento, Uso de suelo?
                        │
                        ▼
             2. Agentes Extractores      uno por tipo documental; cada dato con evidencia (doc, pág, fragmento)
                        │
                        ▼
             3. Agente Validador         reglas oficiales por tipo (reto/)
                        │
                        ▼
             4. Agente de Cruce          dirección, propietario, superficie, clave catastral, número oficial
                        │
                        ▼
             5. Agente Revisor           contrasta hallazgos contra la evidencia y descarta los no sustentados
                        │
                        ▼
             6. Agente Dictaminador      recomendación + confianza + explicación para el equipo legal
```

## Estructura

| Ruta | Contenido |
|---|---|
| `src/expedientes/schemas.py` | Modelos Pydantic compartidos (extracción, hallazgo, dictamen) |
| `src/expedientes/ingest.py` | PDF/imagen → páginas con texto e imagen |
| `src/expedientes/agents/` | Un módulo por agente |
| `reto/` | Documentos oficiales: guías, reglas y expedientes. **No se suben a git** (regla 06) |
| `outputs/` | Dictámenes generados. No se suben |
| `app.py` | Interfaz Streamlit para la demo |

## Arranque

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # y poner la API key
streamlit run app.py
```

## Datos

Descargar los zips de https://hackaton3b.com/expedientes.html en `reto/`.
Solo se usan dentro del reto; no se suben a ningún servicio ni repositorio.

Ojo: 59 de los 63 PDFs de prueba son escaneos sin capa de texto, así que la extracción
necesita un modelo con visión (u OCR).
