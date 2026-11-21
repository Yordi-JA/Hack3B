"""Motivos de descarte para el seguimiento de expedientes. Dueño: Juan Pablo.

Traduce cada hallazgo e inconsistencia del `Dictamen` a una categoría de negocio ("Descartado por
uso de suelo", "Descartado por falta de claridad del documento", ...) para que el front agrupe,
filtre y cuente expedientes por motivo. Determinista, no llama al LLM y no cambia el contrato:

    from expedientes.motivos import motivos, resumen_por_categoria
    for m in motivos(dictamen):
        m.categoria, m.etiqueta, m.archivo, m.id_regla, m.explicacion

- Solo cuentan los hallazgos que pesan en la decisión: NO_CUMPLE o NO_EVALUABLE con severidad
  BLOQUEANTE o REVISION, después de consolidar por tipo como el dictamen (si otro archivo del mismo
  tipo cumple la regla, el fallo no es motivo).
- BLOQUEANTE -> "Descartado por ..."; REVISION -> "En revisión por ...".
- Toda regla nueva debe agregarse a CATEGORIA_POR_REGLA (lo exige tests/test_motivos.py).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .agentes.dictamen import consolidar
from .schemas import Dictamen, EstadoRegla, Evidencia, Hallazgo, Severidad, TipoDocumento


class Categoria(str, Enum):
    USO_SUELO = "uso_suelo"
    VIGENCIA = "vigencia"
    CLARIDAD = "claridad_documento"
    EXPEDIENTE_INCOMPLETO = "expediente_incompleto"
    SITUACION_JURIDICA = "situacion_juridica"
    ADEUDO_FISCAL = "adeudo_fiscal"
    AFECTACION_PREDIO = "afectacion_predio"
    DATOS_NO_COINCIDEN = "datos_no_coinciden"
    IDENTIFICACION = "identificacion"
    FORMALIDADES = "formalidades"
    VERIFICACION_MANUAL = "verificacion_manual"


# Texto que va después de "Descartado por" / "En revisión por".
MOTIVO = {
    Categoria.USO_SUELO: "uso de suelo",
    Categoria.VIGENCIA: "documento vencido",
    Categoria.CLARIDAD: "falta de claridad del documento",
    Categoria.EXPEDIENTE_INCOMPLETO: "expediente incompleto",
    Categoria.SITUACION_JURIDICA: "situación jurídica del inmueble",
    Categoria.ADEUDO_FISCAL: "adeudos de predial",
    Categoria.AFECTACION_PREDIO: "afectaciones o restricciones del predio",
    Categoria.DATOS_NO_COINCIDEN: "datos que no coinciden entre documentos",
    Categoria.IDENTIFICACION: "datos de identificación incompletos",
    Categoria.FORMALIDADES: "formalidades del documento",
    Categoria.VERIFICACION_MANUAL: "datos que requieren verificación manual",
}

C = Categoria
CATEGORIA_POR_REGLA: dict[str, Categoria] = {
    # Escritura
    "ESC-01": C.IDENTIFICACION,       # titular
    "ESC-02": C.IDENTIFICACION,       # dirección
    "ESC-03": C.IDENTIFICACION,       # superficie
    "ESC-04": C.IDENTIFICACION,       # clave catastral
    "ESC-05": C.SITUACION_JURIDICA,   # acto traslativo de dominio
    "ESC-06": C.SITUACION_JURIDICA,   # gravámenes / hipoteca
    "ESC-07": C.FORMALIDADES,         # notario y número de escritura
    "ESC-08": C.SITUACION_JURIDICA,   # inscripción en el RPP
    "ESC-09": C.SITUACION_JURIDICA,   # régimen ejidal / comunal / condominio
    "ESC-10": C.SITUACION_JURIDICA,   # copropiedad sin poder unificado
    "ESC-11": C.SITUACION_JURIDICA,   # embargo o litigio
    "ESC-12": C.SITUACION_JURIDICA,   # usufructo
    "ESC-ILEG": C.CLARIDAD,
    # Predial
    "PRE-01": C.IDENTIFICACION,       # contribuyente
    "PRE-02": C.IDENTIFICACION,       # clave catastral o cuenta
    "PRE-03": C.FORMALIDADES,         # fecha de pago
    "PRE-04": C.ADEUDO_FISCAL,        # adeudos
    "PRE-05": C.FORMALIDADES,         # fecha de pago vs sello de caja
    "PRE-06": C.IDENTIFICACION,       # superficie registrada
    "PRE-07": C.IDENTIFICACION,       # un solo predio
    "PRE-08": C.USO_SUELO,            # uso registrado compatible con comercio
    "PRE-09": C.VERIFICACION_MANUAL,  # datos sin evidencia literal
    "PRE-10": C.SITUACION_JURIDICA,   # embargo / PAE
    "PRE-11": C.IDENTIFICACION,       # construcción registrada
    "PRE-ILEG": C.CLARIDAD,
    # Alineamiento y número oficial
    "ALI-01": C.IDENTIFICACION,       # número oficial asignado
    "ALI-02": C.VIGENCIA,
    "ALI-03": C.AFECTACION_PREDIO,    # afectación vial
    "ALI-04": C.AFECTACION_PREDIO,    # alineamiento determinado
    "ALI-05": C.IDENTIFICACION,       # clave catastral o cuenta
    "ALI-06": C.FORMALIDADES,         # autoridad emisora
    "ALI-07": C.FORMALIDADES,         # fecha de emisión coherente
    "ALI-08": C.AFECTACION_PREDIO,    # CFE, Pemex, Conagua, vías férreas
    "ALI-09": C.AFECTACION_PREDIO,    # invasión de vía pública
    "ALI-10": C.AFECTACION_PREDIO,    # lotes sin fusionar
    "ALI-11": C.AFECTACION_PREDIO,    # restricción al frente
    "ALI-EVI": C.VERIFICACION_MANUAL,
    "ALI-LEG": C.CLARIDAD,
    # Uso de suelo
    "USO-00": C.CLARIDAD,
    "USO-01": C.USO_SUELO,            # autoriza el uso comercial
    "USO-02": C.VIGENCIA,
    "USO-03": C.FORMALIDADES,         # fechas coherentes
    "USO-04": C.USO_SUELO,            # condicionantes
    "USO-05": C.IDENTIFICACION,       # identifica el predio
    "USO-06": C.FORMALIDADES,         # autoridad emisora
    "USO-07": C.USO_SUELO,            # superficie comercial suficiente
    "USO-08": C.USO_SUELO,            # prohibiciones (autoservicio, alcohol, carga)
    "USO-09": C.USO_SUELO,            # área libre exigida
    "USO-10": C.USO_SUELO,            # derechos adquiridos
    "USO-11": C.AFECTACION_PREDIO,    # zona de conservación o patrimonio
    # Validación cruzada
    "CRU-PROP": C.DATOS_NO_COINCIDEN,
    "CRU-DIR": C.DATOS_NO_COINCIDEN,
    "CRU-SUP": C.DATOS_NO_COINCIDEN,
    "CRU-CLAVE": C.DATOS_NO_COINCIDEN,
    "CRU-NUM": C.DATOS_NO_COINCIDEN,
    "CRU-INM": C.DATOS_NO_COINCIDEN,  # documento de otro inmueble
    # Expediente y proceso
    "EXP-01": C.EXPEDIENTE_INCOMPLETO,
    "EXP-02": C.CLARIDAD,
    "EXP-TIPO": C.EXPEDIENTE_INCOMPLETO,  # archivo que no es de ningún tipo requerido
    "EXP-INGESTA": C.CLARIDAD,            # no se pudo leer el archivo
    "EXP-ERROR": C.VERIFICACION_MANUAL,   # falló el análisis automático
    "EXP-AUD": C.VERIFICACION_MANUAL,     # el auditor descartó datos sin sustento
}

# Respaldo para una regla nueva que aún no está en el catálogo.
_POR_PREFIJO = {"CRU": C.DATOS_NO_COINCIDEN, "EXP": C.VERIFICACION_MANUAL}


def categoria(id_regla: str) -> Categoria:
    if id_regla in CATEGORIA_POR_REGLA:
        return CATEGORIA_POR_REGLA[id_regla]
    return _POR_PREFIJO.get(id_regla.split("-")[0], C.VERIFICACION_MANUAL)


def etiqueta(cat: Categoria, severidad: Severidad) -> str:
    inicio = "Descartado por" if severidad == Severidad.BLOQUEANTE else "En revisión por"
    return f"{inicio} {MOTIVO[cat]}"


class Motivo(BaseModel):
    categoria: Categoria
    etiqueta: str = Field(description="'Descartado por uso de suelo', 'En revisión por documento vencido', ...")
    severidad: Severidad
    estado: EstadoRegla
    id_regla: str
    descripcion: str
    explicacion: str
    archivo: Optional[str] = Field(default=None, description="None si el motivo es del expediente")
    tipo: Optional[TipoDocumento] = None
    archivos: list[str] = Field(default_factory=list, description="Documentos involucrados (inconsistencias)")
    evidencias: list[Evidencia] = Field(default_factory=list)


class ResumenCategoria(BaseModel):
    categoria: Categoria
    etiqueta: str
    severidad: Severidad = Field(description="La más grave de la categoría")
    total: int
    archivos: list[str]


def _cuenta(h: Hallazgo) -> bool:
    return h.estado != EstadoRegla.CUMPLE and h.severidad in (Severidad.BLOQUEANTE, Severidad.REVISION)


def _motivo(h: Hallazgo, archivo: Optional[str], tipo: Optional[TipoDocumento]) -> Motivo:
    cat = categoria(h.id_regla)
    return Motivo(categoria=cat, etiqueta=etiqueta(cat, h.severidad), severidad=h.severidad, estado=h.estado,
                  id_regla=h.id_regla, descripcion=h.descripcion, explicacion=h.explicacion, archivo=archivo,
                  tipo=tipo, archivos=[archivo] if archivo else [], evidencias=h.evidencias)


def motivos(d: Dictamen) -> list[Motivo]:
    """Todos los motivos del expediente, primero los que descartan y después los de revisión."""
    out = [_motivo(h, doc.archivo, doc.tipo) for doc, h in consolidar(d.documentos) if _cuenta(h)]
    out += [_motivo(h, None, None) for h in d.hallazgos_expediente if _cuenta(h)]
    for i in d.inconsistencias:
        if i.severidad not in (Severidad.BLOQUEANTE, Severidad.REVISION):
            continue
        cat = categoria(i.id_regla)
        out.append(Motivo(
            categoria=cat, etiqueta=etiqueta(cat, i.severidad), severidad=i.severidad,
            estado=EstadoRegla.NO_CUMPLE, id_regla=i.id_regla, descripcion=i.descripcion,
            explicacion=i.descripcion, archivos=sorted({v.archivo for v in i.valores}),
            evidencias=[v.evidencia for v in i.valores if v.evidencia],
        ))
    return sorted(out, key=lambda m: m.severidad != Severidad.BLOQUEANTE)  # estable: conserva el orden


def resumen_por_categoria(d: Dictamen) -> list[ResumenCategoria]:
    """Un renglón por categoría (para el tablero de seguimiento), las que descartan primero."""
    grupos: dict[Categoria, list[Motivo]] = {}
    for m in motivos(d):
        grupos.setdefault(m.categoria, []).append(m)
    filas = []
    for cat, ms in grupos.items():
        sev = Severidad.BLOQUEANTE if any(m.severidad == Severidad.BLOQUEANTE for m in ms) else Severidad.REVISION
        filas.append(ResumenCategoria(categoria=cat, etiqueta=etiqueta(cat, sev), severidad=sev, total=len(ms),
                                      archivos=sorted({a for m in ms for a in m.archivos})))
    return sorted(filas, key=lambda f: (f.severidad != Severidad.BLOQUEANTE, -f.total))
