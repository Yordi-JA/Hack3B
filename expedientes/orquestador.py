"""Orquestador multiagente. Dueño: Carlos.

Punto de entrada único para la UI: `analizar_expediente(rutas, ctx)`.

Arquitectura: LangChain puro (sin LangGraph). El flujo es lineal con un único
paralelismo en los agentes por tipo:

    ingesta (secuencial, ya hace sus propias llamadas) ─┐
                                                        │
    ┌───────────────────────────────────────────────────┘
    │
    ├─► escritura.analizar()   ┐
    ├─► predial.analizar()     │  en paralelo con
    ├─► alineamiento.analizar()│  ThreadPoolExecutor(max_workers=5)
    └─► uso_suelo.analizar()   ┘
                                │
    cruce.validar_cruzado()  ◄──┘  (secuencial, necesita todos)
    dictamen.dictaminar()       (secuencial)

El tope de 5 workers respeta el rate limit que señala el README línea 21:
"el OCR masivo debe correr con 5-10 llamadas en paralelo como máximo".

Mientras los agentes no existan, `usar_ejemplo=True` devuelve `ejemplos/dictamen_ejemplo.json`
para que la UI pueda trabajar desde ya.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

from .agentes import alineamiento, cruce, dictamen, escritura, ingesta, predial, uso_suelo
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
    Legibilidad,
    Severidad,
    TipoDocumento,
)

# Prefijo en `DocumentoLeido.notas` para marcar que la ingesta falló; `_analizar`
# lo detecta y emite el hallazgo EXP-INGESTA en lugar de EXP-TIPO.
_PREFIJO_INGESTA_ROTA = "[ingesta-fallida] "

log = logging.getLogger(__name__)

AGENTES_POR_TIPO = {
    TipoDocumento.ESCRITURA: escritura.analizar,
    TipoDocumento.PREDIAL: predial.analizar,
    TipoDocumento.ALINEAMIENTO: alineamiento.analizar,
    TipoDocumento.USO_SUELO: uso_suelo.analizar,
}

EJEMPLO = RAIZ / "ejemplos" / "dictamen_ejemplo.json"

# Tope de agentes corriendo al mismo tiempo. Respeta el rate limit del README
# (5-10 llamadas simultáneas). Para bajar sin tocar código, setear la env var.
import os as _os
MAX_AGENTES_PARALELO = int(_os.getenv("MAX_AGENTES_PARALELO", "5"))


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
    """Wrap de `ingesta.leer_documento` que tolera fallas (timeout, 429, PDF dañado).

    Si la ingesta explota, devuelve un DocumentoLeido de tipo OTRO con las notas
    marcadas con `_PREFIJO_INGESTA_ROTA` para que `_analizar` emita EXP-INGESTA
    y el revisor humano sepa que el problema fue el OCR, no el agente.
    """
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
    # La ingesta puede haber fallado antes del clasificador; lo detectamos por las notas
    # para dar una explicación precisa al revisor.
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


def _analizar_en_paralelo(leidos: list[DocumentoLeido], ctx: Contexto) -> list[DocumentoAnalizado]:
    """Corre `_analizar` sobre cada DocumentoLeido en paralelo.

    - Preserva el orden de `leidos` (executor.map es ordenado).
    - Como `_analizar` ya captura excepciones por agente, un agente lento o
      roto no bloquea a los otros.
    - Si hay un solo doc no vale la pena el overhead del executor.
    """
    if not leidos:
        return []
    if len(leidos) == 1:
        return [_analizar(leidos[0], ctx)]
    workers = min(MAX_AGENTES_PARALELO, len(leidos))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="agente") as pool:
        return list(pool.map(lambda d: _analizar(d, ctx), leidos))


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
    leidos = [_leer(Path(r)) for r in rutas]
    analizados = _analizar_en_paralelo(leidos, ctx)
    presentes = {d.tipo for d in leidos}
    faltantes = [t for t in TIPOS_REQUERIDOS if t not in presentes]
    inconsistencias = cruce.validar_cruzado(analizados, ctx)
    return dictamen.dictaminar(expediente_id, analizados, faltantes, inconsistencias, ctx)
