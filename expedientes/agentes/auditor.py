"""Agente auditor. Dueño: Julián.

Contrasta lo que reportan los agentes por tipo contra el texto ORIGINAL de cada documento
(`DocumentoLeido`) antes del dictamen. Es independiente de cómo verificó cada agente y aplica
el mismo estándar a todos. Determinista: no llama al LLM.

    AUD-01  Evidencia de datos: la cita de cada dato tiene que estar en la página que dice el agente
            (si está en otra página del mismo documento, se corrige la página). Si no está, el dato
            se queda sin evidencia ni `normalizado`.
    AUD-02  Valor en el documento: en los datos que se cruzan entre documentos, el valor tiene que
            aparecer en la página citada. Atrapa una cita real con un valor inventado
            ("SUPERFICIE TOTAL DE 300.00 M2" con valor "350.00").
    AUD-03  Hallazgo bloqueante con evidencia: un NO_CUMPLE BLOQUEANTE cuya evidencia no aparece en
            el documento baja a NO_EVALUABLE / REVISION (contrato: sin evidencia no hay hallazgo, y
            el reto castiga descartar expedientes sin sustento).

Cada intervención queda en el documento como hallazgo `EXP-AUD`. Si se descartaron datos que se
cruzan, el orquestador vuelve a correr la validación cruzada con los datos limpios.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from ..schemas import (
    CAMPOS_CRUZABLES,
    Campo,
    DocumentoAnalizado,
    DocumentoLeido,
    EstadoRegla,
    Evidencia,
    Hallazgo,
    Severidad,
)

FIRMA_PALABRAS = 6          # una cita larga calza si sus primeras 6 palabras están seguidas en la página
PROPORCION_PALABRAS = 0.85  # o si el 85 % de sus palabras está en la página (OCR que rompe el orden)
PROPORCION_VALOR = 0.75     # palabras del valor que deben estar en la página (abreviaturas: MA. / MARIA)
CONFIANZA_DESCARTADO = 0.3
_UNIDADES = {"M", "M2", "MTS", "MT", "METROS", "CUADRADOS", "MXN", "PESOS"}


# ---------------------------------------------------------------- texto

def _tokens(s: Optional[str]) -> list[str]:
    plano = "".join((unicodedata.normalize("NFKD", c)[:1] or c) for c in (s or "")).upper()
    return re.findall(r"[A-Z0-9]+", plano)


def _cita_en(cita: Optional[str], texto: str) -> bool:
    toks = _tokens(cita)
    if not toks:
        return False
    pagina = _tokens(texto)
    firma = " ".join(toks[:FIRMA_PALABRAS])
    if f" {firma} " in f" {' '.join(pagina)} ":
        return True
    presentes = set(pagina)
    return len(toks) >= 3 and sum(t in presentes for t in toks) / len(toks) >= PROPORCION_PALABRAS


def _valor_en(valor: Optional[str], texto: str) -> bool:
    """Los números del valor (sin ceros de relleno ni unidades) tienen que estar todos en la página;
    las palabras, al menos el 75 %."""
    toks = [t for t in _tokens(valor) if t not in _UNIDADES and not re.fullmatch(r"0+", t)]
    if not toks:
        return True
    pagina = set(_tokens(texto))
    numeros = [t for t in toks if t.isdigit()]
    palabras = [t for t in toks if not t.isdigit() and len(t) > 1]
    if any(n not in pagina and n.lstrip("0") not in pagina for n in numeros):
        return False
    return not palabras or sum(p in pagina for p in palabras) / len(palabras) >= PROPORCION_VALOR


def _textos(leido: DocumentoLeido) -> dict[int, str]:
    return {p.numero: p.texto for p in leido.paginas}


def _ubicar(evidencia: Evidencia, textos: dict[int, str]) -> Optional[int]:
    """Página donde está la cita: la que dice la evidencia o, si no, otra del mismo documento."""
    if _cita_en(evidencia.cita, textos.get(evidencia.pagina, "")):
        return evidencia.pagina
    return next((n for n, t in textos.items() if _cita_en(evidencia.cita, t)), None)


# ---------------------------------------------------------------- auditoría

@dataclass
class ResultadoAuditoria:
    documentos: list[DocumentoAnalizado]
    reabrir_cruce: bool = False  # se descartaron datos que se cruzan: hay que repetir el cruce
    intervenciones: list[str] = field(default_factory=list)  # para la bitácora del orquestador


def _auditar_campo(nombre: str, campo: Campo, textos: dict[int, str]) -> tuple[Campo, Optional[str]]:
    """Devuelve el campo (corregido o descartado) y el motivo si el auditor intervino."""
    if not campo.evidencia:
        return campo, None
    pagina = _ubicar(campo.evidencia, textos)
    if pagina is None:
        motivo = f"{nombre}: la cita «{campo.evidencia.cita[:60]}» no aparece en el documento (AUD-01)"
    elif nombre in CAMPOS_CRUZABLES and not _valor_en(campo.valor, textos[pagina]):
        motivo = f"{nombre}: el valor «{campo.valor}» no aparece en la página {pagina} citada (AUD-02)"
    else:
        if pagina != campo.evidencia.pagina:
            campo = campo.model_copy(update={"evidencia": campo.evidencia.model_copy(update={"pagina": pagina})})
        return campo, None
    return Campo(valor=campo.valor, confianza=min(campo.confianza, CONFIANZA_DESCARTADO)), motivo


def _auditar_hallazgo(h: Hallazgo, textos_por_archivo: dict[str, dict[int, str]]) -> tuple[Hallazgo, Optional[str]]:
    if not (h.estado == EstadoRegla.NO_CUMPLE and h.severidad == Severidad.BLOQUEANTE):
        return h, None
    if any(_ubicar(e, textos_por_archivo.get(e.archivo, {})) for e in h.evidencias):
        return h, None
    nuevo = h.model_copy(update={
        "estado": EstadoRegla.NO_EVALUABLE,
        "severidad": Severidad.REVISION,
        "explicacion": h.explicacion + " [Auditor: la evidencia de este rechazo no se encontró en el documento; "
                                       "se baja a revisión manual en vez de descartar el expediente.]",
        "evidencias": [],
    })
    return nuevo, f"{h.id_regla}: rechazo sin evidencia verificable, baja a revisión (AUD-03)"


def auditar(leidos: list[DocumentoLeido], analizados: list[DocumentoAnalizado]) -> ResultadoAuditoria:
    """`leidos[i]` es el documento original de `analizados[i]` (el orquestador conserva el orden)."""
    textos_por_archivo = {l.archivo: _textos(l) for l in leidos}
    resultado = ResultadoAuditoria(documentos=[])
    for leido, doc in zip(leidos, analizados):
        textos = _textos(leido)
        datos = doc.datos.model_copy(deep=True)
        motivos: list[str] = []
        cruzable_descartado = False

        for nombre in type(datos).model_fields:
            if nombre == "especificos":
                continue
            campo, motivo = _auditar_campo(nombre, getattr(datos, nombre), textos)
            setattr(datos, nombre, campo)
            if motivo:
                motivos.append(motivo)
                cruzable_descartado |= nombre in CAMPOS_CRUZABLES
        for nombre, c in list(datos.especificos.items()):
            campo, motivo = _auditar_campo(nombre, c, textos)
            datos.especificos[nombre] = campo
            if motivo:
                motivos.append(motivo)

        hallazgos, bajados = [], False
        for h in doc.hallazgos:
            h2, motivo = _auditar_hallazgo(h, textos_por_archivo)
            hallazgos.append(h2)
            if motivo:
                motivos.append(motivo)
                bajados = True

        if motivos:
            hallazgos.append(Hallazgo(
                id_regla="EXP-AUD",
                descripcion="Auditoría de evidencia contra el documento original",
                estado=EstadoRegla.NO_EVALUABLE,
                severidad=Severidad.REVISION if (cruzable_descartado or bajados) else Severidad.INFO,
                explicacion="El auditor revisó lo que reportó el agente contra el texto del documento y "
                            "corrigió: " + "; ".join(motivos) + ".",
            ))
            resultado.intervenciones += [f"{doc.archivo}: {m}" for m in motivos]
            resultado.reabrir_cruce |= cruzable_descartado
        if motivos or datos != doc.datos:  # también una página corregida sin otra intervención
            doc = doc.model_copy(update={"datos": datos, "hallazgos": hallazgos})
        resultado.documentos.append(doc)
    return resultado
