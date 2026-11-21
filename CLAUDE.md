# Instrucciones para asistentes de código (Claude Code u otros)

Proyecto de hackathon con entrega hoy. Lee `README.md` (contrato, equipo, reglas) antes de cambiar algo.

## Créditos de la API: hay $5 USD para todo el equipo

Sigue la sección "Uso de la API (créditos)" del README. En especial:

- No ejecutes nada que llame a la API de Anthropic (OCR, agentes, orquestador, scripts de prueba) sin que la persona lo pida explícitamente. Para probar código, usa `cache/` y `ejemplos/`.
- Nunca corras `python -m expedientes.agentes.ingesta`: el caché OCR ya existe y solo Julián lo regenera.
- Modelo `claude-haiku-5-5` con `effort="low"`. No cambies `LLM_MODEL` ni pidas otro modelo en el código sin que la persona lo pida.
- Una llamada por documento con salida estructurada; nada de llamadas por campo, bucles sin tope ni reintentos propios. Máximo 6 en paralelo.
- Lo determinista (fechas, vigencias, superficies, normalización, comparaciones) se resuelve en Python, no con el LLM.
- `pytest` no debe llamar a la API.

## Reglas del proyecto

- Cada persona toca solo sus archivos (tabla "Equipo y ramas" del README). `expedientes/schemas.py` es el contrato compartido: no lo cambies sin avisar.
- Documentos y caché no salen del equipo (regla 06): nunca subas `Documentos/`, `cache/` ni `.env` al repo ni a otro servicio.
- Todo dato y hallazgo lleva `Evidencia` (archivo, página, cita literal). Un documento `ILEGIBLE` no extrae datos.
