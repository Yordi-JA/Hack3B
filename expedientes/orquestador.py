"""Orquestador multiagente. Dueño: Carlos.

Punto de entrada único para la UI: `analizar_expediente(rutas, ctx)`.

PENDIENTE (Carlos): LangGraph o cadena de LangChain. El reto exige "arquitectura multiagente
sobre LangChain"; LangGraph es parte del ecosistema, confirmar con los jueces si cuenta.

Mientras los agentes no existan, `usar_ejemplo=True` devuelve `ejemplos/dictamen_ejemplo.json`
para que la UI pueda trabajar desde ya.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .agentes import alineamiento, cruce, dictamen, escritura, ingesta, predial, uso_suelo
from .config import RAIZ
from .schemas import (
    TIPOS_REQUERIDOS,
    Contexto,
    DatosInmueble,
    Dictamen,
    DocumentoAnalizado,
    DocumentoLeido,
    EstadoRegla,
    Hallazgo,
    Severidad,
    TipoDocumento,
)

log = logging.getLogger(__name__)

AGENTES_POR_TIPO = {
    TipoDocumento.ESCRITURA: escritura.analizar,
    TipoDocumento.PREDIAL: predial.analizar,
    TipoDocumento.ALINEAMIENTO: alineamiento.analizar,
    TipoDocumento.USO_SUELO: uso_suelo.analizar,
}

EJEMPLO = RAIZ / "ejemplos" / "dictamen_ejemplo.json"


def _sin_analisis(doc: DocumentoLeido, id_regla: str, explicacion: str) -> DocumentoAnalizado:
    """Documento recibido que no se pudo analizar: se muestra igual, con un hallazgo de revisión."""
    return DocumentoAnalizado(
        archivo=doc.archivo,
        tipo=doc.tipo,
        confianza_tipo=doc.confianza_tipo,
        legibilidad=doc.legibilidad,
        datos=DatosInmueble(),
        hallazgos=[
            Hallazgo(
                id_regla=id_regla,
                descripcion="Documento recibido sin análisis",
                estado=EstadoRegla.NO_EVALUABLE,
                severidad=Severidad.REVISION,
                explicacion=explicacion,
            )
        ],
        confianza=0.0,
    )


def _analizar(doc: DocumentoLeido, ctx: Contexto) -> DocumentoAnalizado:
    agente = AGENTES_POR_TIPO.get(doc.tipo)
    if agente is None:
        return _sin_analisis(doc, "EXP-TIPO", "No se reconoció como uno de los 4 tipos requeridos.")
    try:
        return agente(doc, ctx)
    except Exception as e:  # un agente roto no debe tumbar el expediente completo
        log.exception("Falló el agente de %s con %s", doc.tipo.value, doc.archivo)
        return _sin_analisis(doc, "EXP-ERROR", f"Falló el análisis automático: {type(e).__name__}: {e}")


def analizar_expediente(
    rutas: list[Path],
    ctx: Optional[Contexto] = None,
    expediente_id: Optional[str] = None,
    usar_ejemplo: bool = False,
) -> Dictamen:
    """Analiza un expediente completo.

    `rutas` debe conservar el nombre original de cada archivo: la evidencia y el caché usan
    ese nombre. Desde Streamlit, guardar cada subida como `tmpdir / uploaded.name`.
    """
    ctx = ctx or Contexto()
    if usar_ejemplo:
        return Dictamen.model_validate_json(EJEMPLO.read_text(encoding="utf-8"))

    expediente_id = expediente_id or datetime.now().strftime("EXP-%Y%m%d-%H%M%S")
    leidos = [ingesta.leer_documento(Path(r)) for r in rutas]
    analizados = [_analizar(d, ctx) for d in leidos]
    presentes = {d.tipo for d in leidos}
    faltantes = [t for t in TIPOS_REQUERIDOS if t not in presentes]
    inconsistencias = cruce.validar_cruzado(analizados, ctx)
    return dictamen.dictaminar(expediente_id, analizados, faltantes, inconsistencias, ctx)
