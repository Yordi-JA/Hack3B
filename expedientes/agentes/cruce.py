"""Agente de validación cruzada. Dueño: Diego.

Compara los `CAMPOS_CRUZABLES` entre todos los documentos del expediente y reporta cada
diferencia con qué dice cada documento y dónde (CONTEXT.md, sección "Validaciones cruzadas").

Cómo compara (siempre sobre `normalizado`, con `valor` de respaldo; se re-normaliza aquí):
- clave_catastral: solo dígitos; iguales o iguales salvo ceros de relleno.
- numero_oficial:  '28' == 'No. 28'; 'SN' (sin número) contra un número es diferencia.
- superficie:      tolerancia TOLERANCIA_SUP_REL (o TOLERANCIA_SUP_ABS_M2, la mayor). Decisión #7.
- propietario:     mismos nombres en cualquier orden; tolera copropietarios listados en un solo documento.
- direccion:       palabras clave en común; en la zona gris decide el LLM (si está configurado).

Además detecta documentos que posiblemente correspondan a otro inmueble (CRU-INM): los que
difieren del resto en la clave catastral y en la dirección o el propietario.

Los valores se agrupan: cada grupo es un conjunto de documentos que dicen lo mismo. Si hay más
de un grupo hay inconsistencia, y se listan todos los documentos con su evidencia.

Prefijo de reglas: CRU-.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Optional

from pydantic import BaseModel, Field

from ..schemas import (
    CAMPOS_CRUZABLES,
    Contexto,
    DocumentoAnalizado,
    Inconsistencia,
    Severidad,
    TipoDocumento,
    ValorEncontrado,
)
from . import normalizar as nz

log = logging.getLogger(__name__)

# Decisión #7 (Diego): diferencia de superficie tolerada. Las superficies de escritura, predial y
# constancias suelen diferir por redondeo o medición; más de 2 % ya amerita revisión.
TOLERANCIA_SUP_REL = 0.02
TOLERANCIA_SUP_ABS_M2 = 1.0

# Zona gris de direcciones: por encima de ALTA son la misma; por debajo de BAJA, distintas.
DIR_ALTA, DIR_BAJA = 0.6, 0.3
USAR_LLM = os.getenv("CRUCE_USAR_LLM", "1") == "1"

REGLA = {
    "propietario": "CRU-PROP",
    "direccion": "CRU-DIR",
    "superficie_terreno_m2": "CRU-SUP",
    "clave_catastral": "CRU-CLAVE",
    "numero_oficial": "CRU-NUM",
}
NOMBRE = {
    "propietario": "propietario",
    "direccion": "dirección",
    "superficie_terreno_m2": "superficie del terreno",
    "clave_catastral": "clave catastral",
    "numero_oficial": "número oficial",
}
TIPO_LEGIBLE = {
    TipoDocumento.ESCRITURA: "Escritura",
    TipoDocumento.PREDIAL: "Predial",
    TipoDocumento.ALINEAMIENTO: "Alineamiento",
    TipoDocumento.USO_SUELO: "Uso de Suelo",
    TipoDocumento.OTRO: "Otro",
}


@dataclass
class _Item:
    doc: DocumentoAnalizado
    campo: str
    crudo: str          # lo que se muestra
    comparable: object  # lo que se compara


# ---------------------------------------------------------------- equivalencias por campo

def _comparable(campo: str, normalizado: Optional[str], valor: Optional[str]):
    base = normalizado or valor
    if campo == "clave_catastral":
        return nz.clave_catastral(base)
    if campo == "numero_oficial":
        return nz.numero_oficial(base)
    if campo == "superficie_terreno_m2":
        return nz.superficie(base)
    if campo == "propietario":
        return (valor or normalizado) if nz.tokens_nombre(base) else None
    if campo == "direccion":
        return base if nz.tokens_direccion(base) else None
    return nz.texto(base) or None


def _sup_equiv(a: float, b: float) -> bool:
    return abs(a - b) <= max(TOLERANCIA_SUP_ABS_M2, TOLERANCIA_SUP_REL * max(a, b))


class _Veredicto(BaseModel):
    misma_direccion: bool = Field(description="True si ambas describen el mismo predio")
    razon: str


@lru_cache(maxsize=256)
def _direcciones_llm(a: str, b: str) -> Optional[bool]:
    if not USAR_LLM:
        return None
    try:
        from ..config import get_callbacks, get_llm
        llm = get_llm().with_structured_output(_Veredicto, method="json_schema")
        r = llm.invoke(
            [("system", "Eres el agente de validación cruzada de un expediente inmobiliario en México. "
                        "Decide si dos direcciones, escritas por documentos distintos, describen el mismo predio. "
                        "Considera abreviaturas, nombres de colonia o municipio omitidos, 'S/N' vs lote/manzana "
                        "y errores de captura. Si el número o la calle son claramente distintos, no es el mismo."),
             ("human", f"Dirección A: {a}\nDirección B: {b}")],
            config={"callbacks": get_callbacks(), "run_name": "cruce:direccion"},
        )
        return r.misma_direccion
    except Exception:
        log.warning("No se pudo consultar al LLM para comparar direcciones", exc_info=True)
        return None


def _dir_equiv(a: str, b: str) -> bool:
    ta, tb = nz.tokens_direccion(a), nz.tokens_direccion(b)
    s = nz.solapamiento(ta, tb)
    na, nb = {t for t in ta if t.isdigit()}, {t for t in tb if t.isdigit()}
    if s >= DIR_ALTA and (not na or not nb or na & nb):
        return True
    if s < DIR_BAJA:
        return False
    veredicto = _direcciones_llm(*sorted((a, b)))
    return True if veredicto is None else veredicto  # sin LLM, la zona gris no se marca


EQUIVALENTE: dict[str, Callable[[object, object], bool]] = {
    "clave_catastral": nz.claves_equivalentes,
    "numero_oficial": lambda a, b: a == b,
    "superficie_terreno_m2": _sup_equiv,
    "propietario": nz.nombres_equivalentes,
    "direccion": _dir_equiv,
}


# ---------------------------------------------------------------- agrupación

def _items(documentos: list[DocumentoAnalizado], campo: str) -> list[_Item]:
    out = []
    for d in documentos:
        if d.tipo == TipoDocumento.OTRO:
            continue
        c = getattr(d.datos, campo)
        if c.normalizado is None:  # contrato: cruce ignora campos sin normalizar
            continue
        comp = _comparable(campo, c.normalizado, c.valor)
        if comp is not None:
            out.append(_Item(d, campo, c.valor or c.normalizado, comp))
    return out


def _agrupar(items: list[_Item]) -> list[list[_Item]]:
    grupos: list[list[_Item]] = []
    eq = EQUIVALENTE[items[0].campo] if items else None
    for it in items:
        for g in grupos:
            if eq(g[0].comparable, it.comparable):
                g.append(it)
                break
        else:
            grupos.append([it])
    return sorted(grupos, key=len, reverse=True)


def _valores(items: list[_Item]) -> list[ValorEncontrado]:
    return [
        ValorEncontrado(
            archivo=it.doc.archivo, tipo=it.doc.tipo, valor=it.crudo,
            evidencia=getattr(it.doc.datos, it.campo).evidencia,
        )
        for it in items
    ]


def _docs(grupo: list[_Item]) -> str:
    return ", ".join(f"{TIPO_LEGIBLE[it.doc.tipo]} ({it.doc.archivo})" for it in grupo)


def _describir(campo: str, grupos: list[list[_Item]]) -> str:
    partes = [f"«{g[0].crudo}» en {_docs(g)}" for g in grupos]
    texto = f"La {NOMBRE[campo]} no coincide entre documentos: " + "; ".join(partes) + "."
    if campo == "superficie_terreno_m2":
        vals = [g[0].comparable for g in grupos]
        dif = max(vals) - min(vals)
        texto += f" Diferencia de {dif:,.2f} m² ({dif / max(vals):.0%}); tolerancia {TOLERANCIA_SUP_REL:.0%}."
    if campo == "numero_oficial" and any(g[0].comparable == nz.SIN_NUMERO for g in grupos):
        texto += " Un documento lo consigna sin número oficial."
    if campo == "propietario":
        texto += " Puede deberse a una compraventa posterior o a que el contribuyente no es el titular: verificar."
    return texto


# ---------------------------------------------------------------- agente

def validar_cruzado(documentos: list[DocumentoAnalizado], ctx: Contexto) -> list[Inconsistencia]:
    inconsistencias: list[Inconsistencia] = []
    discrepa: dict[str, set[str]] = {}  # archivo -> campos en los que está fuera del grupo mayoritario

    for campo in CAMPOS_CRUZABLES:
        items = _items(documentos, campo)
        if len({it.doc.archivo for it in items}) < 2:
            continue
        grupos = _agrupar(items)
        if len(grupos) < 2:
            continue
        inconsistencias.append(Inconsistencia(
            id_regla=REGLA[campo], campo=campo, descripcion=_describir(campo, grupos),
            severidad=Severidad.REVISION, valores=_valores(items),
        ))
        mayor = grupos[0]
        if len(mayor) > max(len(g) for g in grupos[1:]):  # solo hay "mayoría" si no hay empate
            for g in grupos[1:]:
                for it in g:
                    discrepa.setdefault(it.doc.archivo, set()).add(campo)

    inconsistencias.extend(_otro_inmueble(documentos, discrepa))
    return inconsistencias


def _otro_inmueble(documentos: list[DocumentoAnalizado], discrepa: dict[str, set[str]]) -> list[Inconsistencia]:
    """CRU-INM: un documento difiere del resto en la clave catastral y además en dirección o propietario."""
    out = []
    for d in documentos:
        campos = discrepa.get(d.archivo, set())
        if "clave_catastral" in campos and campos & {"direccion", "propietario"}:
            campos_ord = [c for c in CAMPOS_CRUZABLES if c in campos]
            valores = [
                ValorEncontrado(archivo=d.archivo, tipo=d.tipo, valor=getattr(d.datos, c).valor,
                                evidencia=getattr(d.datos, c).evidencia)
                for c in campos_ord
            ]
            out.append(Inconsistencia(
                id_regla="CRU-INM", campo="inmueble",
                descripcion=(f"El documento {TIPO_LEGIBLE[d.tipo]} ({d.archivo}) posiblemente corresponde a otro "
                             f"inmueble: no coincide con el resto del expediente en "
                             f"{', '.join(NOMBRE[c] for c in campos_ord)}. Confirmar que se integró el documento correcto."),
                severidad=Severidad.REVISION, valores=valores,
            ))
    return out
