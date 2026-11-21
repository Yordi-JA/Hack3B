"""Orquestador multiagente. Dueño: Carlos.

Punto de entrada único para la UI: `analizar_expediente(rutas, ctx)`.

PENDIENTE (Carlos): LangGraph o cadena de LangChain. El reto exige "arquitectura multiagente
sobre LangChain"; LangGraph es parte del ecosistema, confirmar con los jueces si cuenta.

Mientras los agentes no existan, `usar_ejemplo=True` devuelve `ejemplos/dictamen_ejemplo.json`
para que la UI pueda trabajar desde ya.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from .agentes import alineamiento, cruce, dictamen, escritura, ingesta, predial, uso_suelo
from .config import RAIZ
from .schemas import TIPOS_REQUERIDOS, Contexto, Dictamen, TipoDocumento

AGENTES_POR_TIPO = {
    TipoDocumento.ESCRITURA: escritura.analizar,
    TipoDocumento.PREDIAL: predial.analizar,
    TipoDocumento.ALINEAMIENTO: alineamiento.analizar,
    TipoDocumento.USO_SUELO: uso_suelo.analizar,
}

EJEMPLO = RAIZ / "ejemplos" / "dictamen_ejemplo.json"


def analizar_expediente(
    rutas: list[Path],
    ctx: Optional[Contexto] = None,
    expediente_id: Optional[str] = None,
    usar_ejemplo: bool = False,
) -> Dictamen:
    ctx = ctx or Contexto()
    if usar_ejemplo:
        return Dictamen.model_validate_json(EJEMPLO.read_text(encoding="utf-8"))

    expediente_id = expediente_id or datetime.now().strftime("EXP-%Y%m%d-%H%M%S")
    leidos = [ingesta.leer_documento(Path(r)) for r in rutas]
    analizados = [AGENTES_POR_TIPO[d.tipo](d, ctx) for d in leidos if d.tipo in AGENTES_POR_TIPO]
    presentes = {d.tipo for d in leidos}
    faltantes = [t for t in TIPOS_REQUERIDOS if t not in presentes]
    inconsistencias = cruce.validar_cruzado(analizados, ctx)
    return dictamen.dictaminar(expediente_id, analizados, faltantes, inconsistencias, ctx)
