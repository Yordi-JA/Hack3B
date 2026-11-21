"""Agente de validación cruzada. Dueño: Diego.

Compara los `CAMPOS_CRUZABLES` entre todos los documentos del expediente y reporta
cada diferencia con qué dice cada documento y dónde (CONTEXT.md, sección "Validaciones cruzadas").

Comparar sobre `Campo.normalizado`, no sobre `valor`: "Avenida de las Torres No. S/N" y
"AV DE LAS TORRES SN" son la misma dirección. Cuando la normalización no alcance, el LLM decide
si dos valores son equivalentes. Superficie con tolerancia (definir cuánta).

También: documentos que posiblemente correspondan a inmuebles diferentes.
Prefijo de reglas: CRU-.
"""
from ..schemas import Contexto, DocumentoAnalizado, Inconsistencia


def validar_cruzado(documentos: list[DocumentoAnalizado], ctx: Contexto) -> list[Inconsistencia]:
    raise NotImplementedError
