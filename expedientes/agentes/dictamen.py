"""Agente dictaminador. Dueño: Juan Pablo.

Junta todo y decide Cumple / Requiere revisión / No cumple, con confianza y una explicación
clara para el equipo legal.

Regla base sugerida (ajustar con las guías oficiales):
- Cualquier hallazgo o inconsistencia BLOQUEANTE incumplido -> No cumple.
- Faltantes, documentos ilegibles, reglas NO_EVALUABLE o severidad REVISION -> Requiere revisión.
- Todo lo demás -> Cumple.
La decisión conviene que sea determinista; el LLM redacta `resumen` y `razones`.

También genera `hallazgos_expediente` (prefijo EXP-): documentos faltantes, ilegibles, etc.
"""
from ..schemas import Contexto, Dictamen, DocumentoAnalizado, Inconsistencia, TipoDocumento


def dictaminar(
    expediente_id: str,
    documentos: list[DocumentoAnalizado],
    faltantes: list[TipoDocumento],
    inconsistencias: list[Inconsistencia],
    ctx: Contexto,
) -> Dictamen:
    raise NotImplementedError
