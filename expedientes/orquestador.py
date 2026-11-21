"""Orquestador multiagente con LangGraph. Dueño: Julián (antes Carlos).

Punto de entrada único para la UI: `analizar_expediente(rutas, ctx)`.

Grafo (ver `diagrama()`):

    START -> ingesta -> agente x N (uno por documento, en paralelo) -> consolidar -> cruce -> auditor
                                                                                     ^         |
                                                                                     +---------+  si el auditor descartó
                                                                                               |  datos que se cruzan
                                                                                               v
                                                                                           dictamen -> END

- ingesta: OCR / caché de cada archivo (secuencial: la ingesta ya paraleliza sus llamadas).
- agente: el especialista de cada tipo (escritura, predial, alineamiento, uso de suelo) extrae
  con evidencia y evalúa sus reglas. LangGraph los corre en paralelo (`Send`), con un tope de
  MAX_AGENTES_PARALELO llamadas simultáneas.
- cruce: compara los datos entre documentos (Diego).
- auditor: revisa lo que reportaron los agentes contra el texto original (AUD-01..03). Si descarta
  datos que se cruzan, el cruce se repite con los datos limpios (máximo MAX_RONDAS_AUDITORIA).
- dictamen: decide Cumple / Requiere revisión / No cumple (Juan Pablo).

Un agente o una ingesta que fallan no tumban el expediente: el documento sale con un hallazgo
EXP-ERROR / EXP-INGESTA. El estado del grafo no se manda a Langfuse (contiene el texto de los
documentos, regla 06); cada agente traza solo su propia llamada al LLM.
"""
from __future__ import annotations

import logging
import operator
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .agentes import alineamiento, auditor, cruce, dictamen, escritura, ingesta, predial, uso_suelo
from .cache import nombre_archivo
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
    Inconsistencia,
    Legibilidad,
    Severidad,
    TipoDocumento,
)

log = logging.getLogger(__name__)

# Prefijo en `DocumentoLeido.notas` para marcar que la ingesta falló; `_analizar` lo detecta y
# emite EXP-INGESTA en lugar de EXP-TIPO.
_PREFIJO_INGESTA_ROTA = "[ingesta-fallida] "

AGENTES_POR_TIPO = {
    TipoDocumento.ESCRITURA: escritura.analizar,
    TipoDocumento.PREDIAL: predial.analizar,
    TipoDocumento.ALINEAMIENTO: alineamiento.analizar,
    TipoDocumento.USO_SUELO: uso_suelo.analizar,
}

EJEMPLO = RAIZ / "ejemplos" / "dictamen_ejemplo.json"

# Llamadas simultáneas al LLM (README: 5-10 como máximo con una key nueva).
MAX_AGENTES_PARALELO = int(os.getenv("MAX_AGENTES_PARALELO", "5"))
MAX_RONDAS_AUDITORIA = 2


# ---------------------------------------------------------------- pasos (también usados por las pruebas)

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


def _leer(ruta: Path) -> DocumentoLeido:
    """`ingesta.leer_documento` tolerante a fallas (timeout, 429, PDF dañado)."""
    try:
        return ingesta.leer_documento(ruta)
    except Exception as e:
        log.exception("Falló la ingesta de %s", ruta)
        return DocumentoLeido(
            archivo=nombre_archivo(ruta),
            tipo=TipoDocumento.OTRO,
            confianza_tipo=0.0,
            legibilidad=Legibilidad.ILEGIBLE,
            paginas=[],
            paginas_totales=0,
            notas=f"{_PREFIJO_INGESTA_ROTA}{type(e).__name__}: {e}",
        )


def _analizar(doc: DocumentoLeido, ctx: Contexto) -> DocumentoAnalizado:
    if doc.notas and doc.notas.startswith(_PREFIJO_INGESTA_ROTA):
        razon = doc.notas[len(_PREFIJO_INGESTA_ROTA):]
        return _sin_analisis(doc, "EXP-INGESTA", f"Falló la lectura del documento: {razon}.")
    agente = AGENTES_POR_TIPO.get(doc.tipo)
    if agente is None:
        return _sin_analisis(doc, "EXP-TIPO", "No se reconoció como uno de los 4 tipos requeridos.")
    try:
        return agente(doc, ctx)
    except Exception as e:  # un agente roto no debe tumbar el expediente completo
        log.exception("Falló el agente de %s con %s", doc.tipo.value, doc.archivo)
        return _sin_analisis(doc, "EXP-ERROR", f"Falló el análisis automático: {type(e).__name__}: {e}")


# ---------------------------------------------------------------- estado del grafo

class _EstadoAgentes(TypedDict, total=False):
    leidos: list[DocumentoLeido]
    ctx: Contexto
    # Cada agente agrega (índice, resultado); el índice conserva el orden de `rutas`.
    resultados: Annotated[list[tuple[int, DocumentoAnalizado]], operator.add]


class Estado(_EstadoAgentes, total=False):
    rutas: list[Path]
    expediente_id: str
    analizados: list[DocumentoAnalizado]
    inconsistencias: list[Inconsistencia]
    rondas_auditoria: int
    reabrir_cruce: bool
    bitacora: Annotated[list[str], operator.add]
    dictamen: Dictamen


# ---------------------------------------------------------------- nodos

def _nodo_ingesta(s: Estado) -> dict:
    leidos = [_leer(Path(r)) for r in s["rutas"]]
    tipos = ", ".join(f"{d.archivo} -> {d.tipo.value} ({d.legibilidad.value})" for d in leidos)
    return {"leidos": leidos, "bitacora": [f"ingesta: {len(leidos)} documentos. {tipos}"]}


def _repartir(siguiente: str):
    """Arista condicional: un `Send` por documento al agente de su tipo; sin documentos, sigue."""
    def repartir(s: _EstadoAgentes):
        sends = [Send("agente", {"indice": i, "doc": d, "ctx": s["ctx"]}) for i, d in enumerate(s.get("leidos") or [])]
        return sends or siguiente
    return repartir


def _nodo_agente(p: dict) -> dict:
    return {"resultados": [(p["indice"], _analizar(p["doc"], p["ctx"]))]}


def _nodo_consolidar(s: Estado) -> dict:
    analizados = [a for _, a in sorted(s.get("resultados") or [], key=lambda x: x[0])]
    resumen = "; ".join(f"{a.tipo.value}: {sum(h.estado == EstadoRegla.NO_CUMPLE for h in a.hallazgos)} no cumple"
                        for a in analizados)
    return {"analizados": analizados, "bitacora": [f"agentes: {resumen or 'sin documentos'}"]}


def _nodo_cruce(s: Estado) -> dict:
    inconsistencias = cruce.validar_cruzado(s["analizados"], s["ctx"])
    campos = ", ".join(i.campo for i in inconsistencias) or "ninguna"
    return {"inconsistencias": inconsistencias, "bitacora": [f"cruce: {len(inconsistencias)} inconsistencias ({campos})"]}


def _nodo_auditor(s: Estado) -> dict:
    r = auditor.auditar(s["leidos"], s["analizados"])
    ronda = s.get("rondas_auditoria", 0) + 1
    nota = f"auditor (ronda {ronda}): " + ("; ".join(r.intervenciones) if r.intervenciones else "sin correcciones")
    if r.reabrir_cruce:
        nota += " -> se repite el cruce con los datos verificados"
    return {"analizados": r.documentos, "reabrir_cruce": r.reabrir_cruce, "rondas_auditoria": ronda, "bitacora": [nota]}


def _despues_del_auditor(s: Estado) -> str:
    return "cruce" if s.get("reabrir_cruce") and s.get("rondas_auditoria", 0) < MAX_RONDAS_AUDITORIA else "dictamen"


def _nodo_dictamen(s: Estado) -> dict:
    presentes = {d.tipo for d in s["leidos"]}
    faltantes = [t for t in TIPOS_REQUERIDOS if t not in presentes]
    d = dictamen.dictaminar(s["expediente_id"], s["analizados"], faltantes, s["inconsistencias"], s["ctx"])
    return {"dictamen": d, "bitacora": [f"dictamen: {d.recomendacion.value} (confianza {d.confianza:.2f})"]}


# ---------------------------------------------------------------- grafos

def construir_grafo():
    g = StateGraph(Estado)
    g.add_node("ingesta", _nodo_ingesta)
    g.add_node("agente", _nodo_agente)
    g.add_node("consolidar", _nodo_consolidar)
    g.add_node("cruce", _nodo_cruce)
    g.add_node("auditor", _nodo_auditor)
    g.add_node("dictamen", _nodo_dictamen)
    g.add_edge(START, "ingesta")
    g.add_conditional_edges("ingesta", _repartir("consolidar"), ["agente", "consolidar"])
    g.add_edge("agente", "consolidar")
    g.add_edge("consolidar", "cruce")
    g.add_edge("cruce", "auditor")
    g.add_conditional_edges("auditor", _despues_del_auditor, ["cruce", "dictamen"])
    g.add_edge("dictamen", END)
    return g.compile()


def _construir_grafo_agentes():
    """Solo el abanico de agentes (lo usa `_analizar_en_paralelo`)."""
    g = StateGraph(_EstadoAgentes)
    g.add_node("agente", _nodo_agente)
    g.add_conditional_edges(START, _repartir(END), ["agente", END])
    g.add_edge("agente", END)
    return g.compile()


GRAFO = construir_grafo()
_GRAFO_AGENTES = _construir_grafo_agentes()


def diagrama() -> str:
    """Diagrama Mermaid del grafo (para el README y el pitch)."""
    return GRAFO.get_graph().draw_mermaid()


def _config() -> dict:
    return {"max_concurrency": MAX_AGENTES_PARALELO}


def _analizar_en_paralelo(leidos: list[DocumentoLeido], ctx: Contexto) -> list[DocumentoAnalizado]:
    """Corre los agentes por tipo en paralelo con LangGraph, conservando el orden de `leidos`."""
    if not leidos:
        return []
    if len(leidos) == 1:
        return [_analizar(leidos[0], ctx)]
    final = _GRAFO_AGENTES.invoke({"leidos": leidos, "ctx": ctx, "resultados": []}, config=_config())
    return [a for _, a in sorted(final["resultados"], key=lambda x: x[0])]


# ---------------------------------------------------------------- punto de entrada

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
    final = GRAFO.invoke(
        {"rutas": list(rutas), "ctx": ctx, "expediente_id": expediente_id, "resultados": [], "bitacora": []},
        config=_config(),
    )
    for paso in final.get("bitacora", []):
        log.info("[%s] %s", expediente_id, paso)
    return final["dictamen"]
