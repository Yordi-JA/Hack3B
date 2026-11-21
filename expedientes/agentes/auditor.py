"""Agente auditor. Dueño: Julián.

Contrasta lo que reportan los agentes por tipo contra el texto ORIGINAL de cada documento
(`DocumentoLeido`) antes del dictamen. Es independiente de cómo verificó cada agente y aplica
el mismo estándar a todos. Determinista: no llama al LLM.

    AUD-01  Evidencia de datos: la cita de cada dato tiene que estar en la página que dice el agente
            (si está en otra página del mismo documento, se corrige la página). Si no está, el dato
            se queda sin evidencia ni `normalizado`.
    AUD-02  Valor en el documento: solo para los datos puntuales que se copian literal
            (CAMPOS_VALOR_LITERAL: superficie, clave catastral, número oficial), el valor tiene que
            aparecer en la página citada, comparado por valor normalizado: superficie como número
            (acepta '1,250.50' por '1250.50' y hectáreas '1-25-00 HAS' por 12500 m²), clave por sus
            dígitos, número oficial con normalizar.numero_oficial. Atrapa una cita real con un valor
            inventado ("SUPERFICIE TOTAL DE 300.00 M2" con valor "350.00"). Dirección y propietario
            solo pasan por AUD-01: los agentes los arman con sus palabras o de varias páginas
            (`exigir_valor=False`), y exigirles el valor daba falsos positivos.
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

from . import normalizar as nz
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
CONFIANZA_DESCARTADO = 0.3
# AUD-02 solo para datos puntuales que se copian literal. Dirección y propietario no: el agente los
# redacta o los junta de varias páginas, y basta con que su cita exista (AUD-01).
CAMPOS_VALOR_LITERAL = ("superficie_terreno_m2", "clave_catastral", "numero_oficial")
TOLERANCIA_M2 = 0.01


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


_HECTAREAS = re.compile(r"(\d+)\s*-\s*(\d{1,2})\s*-\s*(\d{1,2}(?:\.\d+)?)\s*H", re.IGNORECASE)
_NUMERO = re.compile(r"\d[\d,.]*")


def _superficies_m2(texto: str) -> set[float]:
    """Todas las superficies que podría expresar el texto, en m²: cada número (con separador de
    miles o decimal, vía normalizar.superficie) y cada 'H-AA-CC HAS' convertido."""
    valores = {round(h * 10000 + a * 100 + float(c), 2) for h, a, c in
               ((int(m[1]), int(m[2]), m[3]) for m in _HECTAREAS.finditer(texto))}
    for m in _NUMERO.finditer(texto):
        x = nz.superficie(m.group(0))
        if x is not None:
            valores.add(round(x, 2))
    if re.search(r"\bH(A|AS|ECTAREAS?)\b", " ".join(_tokens(texto))):
        valores |= {round(v * 10000, 2) for v in list(valores)}
    return valores


def _digitos_en(digitos: str, texto: str) -> bool:
    """La clave aparece en el texto aunque cambien los separadores ('077-04-310-12' / '0770431012')."""
    corridas = [re.sub(r"\D", "", m) for m in re.findall(r"\d[\d\s./-]*\d|\d", texto)]
    clave = digitos.rstrip("0") or digitos
    return any(clave in c for c in corridas)


def _valor_en(nombre: str, valor: Optional[str], texto: str) -> bool:
    """AUD-02: el dato literal está en la página, comparado por su valor normalizado."""
    if nombre == "superficie_terreno_m2":
        objetivo = _superficies_m2(valor or "")
        return not objetivo or any(abs(a - b) <= TOLERANCIA_M2 for a in objetivo for b in _superficies_m2(texto))
    if nombre == "clave_catastral":
        digitos = re.sub(r"\D", "", valor or "")
        return len(digitos) < 4 or _digitos_en(digitos, texto)
    if nombre == "numero_oficial":
        numero = nz.numero_oficial(valor)
        if not numero:
            return True
        tokens = _tokens(texto)
        if numero == nz.SIN_NUMERO:
            return bool(re.search(r"\bS N\b|\bSN\b|SIN NUM", " ".join(tokens)))
        digitos = re.match(r"\d+", numero)
        return digitos is not None and (digitos.group(0) in tokens or numero in tokens)
    return True


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
    elif nombre in CAMPOS_VALOR_LITERAL and not _valor_en(nombre, campo.valor, textos[pagina]):
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
