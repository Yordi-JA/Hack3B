"""Agente dictaminador. Dueño: Juan Pablo.

Junta todo y decide Cumple / Requiere revisión / No cumple, con confianza y una explicación
clara para el equipo legal. Es determinista y no llama al LLM: la decisión debe ser repetible
y el resumen se arma con los hallazgos, que ya traen su explicación y evidencia.

Decisión:
1. Consolidar por tipo (contrato): si un archivo de un tipo CUMPLE una regla, los NO_CUMPLE /
   NO_EVALUABLE de esa misma regla en otros archivos del mismo tipo no cuentan. Caso típico:
   Alineamiento y Número Oficial en dos archivos, a cada uno le faltan los datos del otro.
2. Cualquier hallazgo o inconsistencia BLOQUEANTE que no se cumple -> No cumple.
3. Faltantes, ilegibles o cualquier hallazgo / inconsistencia de severidad REVISION -> Requiere revisión.
4. Todo lo demás -> Cumple.

Matriz de inconsistencias cruzadas de los criterios de Tiendas 3B: cada inconsistencia de `cruce`
se acompaña de la acción que pide la matriz (revisión legal, levantamiento topográfico, ...).

Reglas de expediente (prefijo EXP-):
    EXP-01  El expediente trae los 4 tipos documentales requeridos
    EXP-02  Documentos ilegibles (uno por archivo)
"""
from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Optional

from ..schemas import (
    CAMPOS_CRUZABLES,
    TIPOS_REQUERIDOS,
    Contexto,
    Dictamen,
    DocumentoAnalizado,
    EstadoRegla,
    Hallazgo,
    Inconsistencia,
    Legibilidad,
    Recomendacion,
    Severidad,
    TipoDocumento,
)

NOMBRE_TIPO = {
    TipoDocumento.ESCRITURA: "Escritura",
    TipoDocumento.PREDIAL: "Predial",
    TipoDocumento.ALINEAMIENTO: "Alineamiento y Número Oficial",
    TipoDocumento.USO_SUELO: "Uso de Suelo",
    TipoDocumento.OTRO: "Otro",
}

# Cada tipo faltante quita esto a la confianza: con menos documentos hay menos que cruzar.
PENALIZACION_FALTANTE = 0.15
# Diferencia de superficie Escritura vs Alineamiento que pide levantamiento topográfico (matriz).
TOLERANCIA_SUP_TOPOGRAFICO = 0.05
MAX_RAZONES = 8

_RANGO_ESTADO = {EstadoRegla.CUMPLE: 0, EstadoRegla.NO_EVALUABLE: 1, EstadoRegla.NO_CUMPLE: 2}


# ---------------------------------------------------------------- consolidación

def consolidar(documentos: list[DocumentoAnalizado]) -> list[tuple[DocumentoAnalizado, Hallazgo]]:
    """Hallazgos que cuentan para la decisión, con el documento de donde salen.

    Por (tipo, regla) gana el mejor estado entre los archivos de ese tipo. Los avisos de proceso
    (EXP-TIPO, EXP-ERROR) y los documentos OTRO se conservan tal cual.
    """
    mejor: dict[tuple[TipoDocumento, str], EstadoRegla] = {}
    for d in documentos:
        for h in d.hallazgos:
            clave = (d.tipo, h.id_regla)
            if clave not in mejor or _RANGO_ESTADO[h.estado] < _RANGO_ESTADO[mejor[clave]]:
                mejor[clave] = h.estado

    out = []
    for d in documentos:
        for h in d.hallazgos:
            proceso = d.tipo == TipoDocumento.OTRO or h.id_regla.startswith("EXP-")
            if proceso or h.estado == mejor[(d.tipo, h.id_regla)]:
                out.append((d, h))
    return out


# ---------------------------------------------------------------- reglas EXP-

def hallazgos_expediente(documentos: list[DocumentoAnalizado], faltantes: list[TipoDocumento]) -> list[Hallazgo]:
    hs: list[Hallazgo] = []
    recibidos = [t for t in TIPOS_REQUERIDOS if t not in faltantes]
    if faltantes:
        hs.append(Hallazgo(
            id_regla="EXP-01", descripcion="El expediente trae los 4 tipos documentales requeridos",
            estado=EstadoRegla.NO_CUMPLE, severidad=Severidad.REVISION,
            explicacion=f"Falta: {_lista(NOMBRE_TIPO[t] for t in faltantes)}. Sin ese documento no se pueden "
                        "validar sus requisitos ni cruzarlo con el resto; hay que solicitarlo.",
        ))
    else:
        hs.append(Hallazgo(
            id_regla="EXP-01", descripcion="El expediente trae los 4 tipos documentales requeridos",
            estado=EstadoRegla.CUMPLE, severidad=Severidad.INFO,
            explicacion=f"Se recibieron {_lista(NOMBRE_TIPO[t] for t in recibidos)}.",
        ))
    for d in documentos:
        if d.legibilidad == Legibilidad.ILEGIBLE:
            hs.append(Hallazgo(
                id_regla="EXP-02", descripcion=f"Documento legible: {d.archivo}",
                estado=EstadoRegla.NO_EVALUABLE, severidad=Severidad.REVISION,
                explicacion=f"El documento de {NOMBRE_TIPO[d.tipo]} «{d.archivo}» no se puede leer; no se "
                            "evaluaron sus requisitos. Solicitar una copia legible.",
            ))
    return hs


# ---------------------------------------------------------------- matriz de inconsistencias cruzadas

def accion_inconsistencia(inc: Inconsistencia) -> Optional[str]:
    """Acción que pide la matriz de criterios de Tiendas 3B para esta inconsistencia."""
    tipos = {v.tipo for v in inc.valores}
    T = TipoDocumento
    if inc.id_regla == "CRU-INM":
        return "Confirmar que se integró el documento del inmueble correcto."
    if inc.campo == "propietario" and {T.ESCRITURA, T.PREDIAL} <= tipos:
        return "Revisión legal requerida: titular del predial distinto al de la escritura (compraventa no " \
               "actualizada o sucesión no concluida)."
    if inc.campo == "superficie_terreno_m2" and {T.ESCRITURA, T.ALINEAMIENTO} <= tipos:
        dif = _diferencia_superficie(inc, T.ESCRITURA, T.ALINEAMIENTO)
        if dif is None or dif > TOLERANCIA_SUP_TOPOGRAFICO:
            return "Solicitar levantamiento topográfico: la superficie difiere más de 5 % entre escritura y alineamiento."
    if inc.campo in ("direccion", "numero_oficial") and {T.USO_SUELO, T.ALINEAMIENTO} <= tipos:
        return "Alerta de datos: la ubicación del uso de suelo no coincide con la del alineamiento."
    if inc.campo in ("direccion", "numero_oficial"):
        return "Discrepancia nominativa de dirección: bloquea acometida CFE y licencias municipales hasta corregirla."
    return None


def _diferencia_superficie(inc: Inconsistencia, a: TipoDocumento, b: TipoDocumento) -> Optional[float]:
    def m2(tipo):
        for v in inc.valores:
            if v.tipo == tipo and v.valor:
                try:
                    return float(v.valor.replace(",", "").split()[0])
                except ValueError:
                    return None
        return None
    x, y = m2(a), m2(b)
    if not x or not y:
        return None
    return abs(x - y) / max(x, y)


# ---------------------------------------------------------------- decisión y redacción

def _lista(items) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1] if items else ""


def _cuenta_para_revision(h: Hallazgo) -> bool:
    return h.severidad == Severidad.REVISION


def _confianza(documentos: list[DocumentoAnalizado], faltantes: list[TipoDocumento]) -> float:
    requeridos = [d for d in documentos if d.tipo in TIPOS_REQUERIDOS]
    base = mean(d.confianza for d in requeridos) if requeridos else 0.0
    return round(max(0.0, base - PENALIZACION_FALTANTE * len(faltantes)), 2)


def _con_datos_cruzables(documentos: list[DocumentoAnalizado]) -> int:
    """Documentos con al menos un campo que `cruce` pudo comparar."""
    return sum(1 for d in documentos
               if any(getattr(d.datos, c).normalizado for c in CAMPOS_CRUZABLES))


def _razon(d: Optional[DocumentoAnalizado], h: Hallazgo) -> str:
    origen = f" ({NOMBRE_TIPO[d.tipo]})" if d else ""
    return f"{h.descripcion}{origen}: {h.explicacion}"


def dictaminar(
    expediente_id: str,
    documentos: list[DocumentoAnalizado],
    faltantes: list[TipoDocumento],
    inconsistencias: list[Inconsistencia],
    ctx: Contexto,
) -> Dictamen:
    exp = hallazgos_expediente(documentos, faltantes)
    vigentes = consolidar(documentos) + [(None, h) for h in exp]

    bloqueantes = [(d, h) for d, h in vigentes
                   if h.severidad == Severidad.BLOQUEANTE and h.estado != EstadoRegla.CUMPLE]
    bloq_cruce = [i for i in inconsistencias if i.severidad == Severidad.BLOQUEANTE]
    revision = [(d, h) for d, h in vigentes if _cuenta_para_revision(h)]
    rev_cruce = [i for i in inconsistencias if i.severidad == Severidad.REVISION]

    if bloqueantes or bloq_cruce:
        recomendacion = Recomendacion.NO_CUMPLE
    elif revision or rev_cruce or faltantes:
        recomendacion = Recomendacion.REQUIERE_REVISION
    else:
        recomendacion = Recomendacion.CUMPLE

    razones: list[str] = []
    razones += [f"{_razon(d, h)} (bloqueante)" for d, h in bloqueantes]
    razones += [f"{i.descripcion} (bloqueante)" for i in bloq_cruce]
    razones += [_razon(d, h) for d, h in revision]
    for i in rev_cruce:
        accion = accion_inconsistencia(i)
        razones.append(i.descripcion + (f" Acción: {accion}" if accion else ""))
    if not razones:
        razones.append("Todos los requisitos evaluados se cumplen y los documentos coinciden entre sí.")
    if len(razones) > MAX_RAZONES:
        resto = len(razones) - (MAX_RAZONES - 1)
        razones = razones[:MAX_RAZONES - 1] + [f"Y {resto} puntos más en el detalle de hallazgos."]

    recibidos = len(TIPOS_REQUERIDOS) - len(faltantes)
    partes = [f"Se recibieron {recibidos} de {len(TIPOS_REQUERIDOS)} tipos documentales"
              + (f" (falta {_lista(NOMBRE_TIPO[t] for t in faltantes)})." if faltantes else ".")]
    if recomendacion == Recomendacion.NO_CUMPLE:
        partes.append(f"No cumple por {len(bloqueantes) + len(bloq_cruce)} motivo(s) de rechazo directo: "
                      + "; ".join(h.descripcion.lower() for _, h in bloqueantes[:3]) + ".")
    elif recomendacion == Recomendacion.REQUIERE_REVISION:
        partes.append("No hay motivos de rechazo directo, pero el equipo legal debe revisar "
                      f"{len(revision) + len(rev_cruce)} punto(s) antes de continuar.")
    else:
        partes.append("Cumple todos los requisitos evaluados y los documentos corresponden al mismo inmueble.")
    if inconsistencias:
        campos = sorted({i.campo for i in inconsistencias})
        partes.append(f"Entre documentos hay {len(inconsistencias)} inconsistencia(s) en: {', '.join(campos)}.")
    elif _con_datos_cruzables(documentos) >= 2:
        partes.append("Los datos comparables coinciden entre documentos.")
    else:
        partes.append("No hubo suficientes datos extraídos para comparar los documentos entre sí.")

    return Dictamen(
        expediente_id=expediente_id,
        fecha_analisis=datetime.now(),
        fecha_referencia=ctx.fecha_referencia,
        documentos=documentos,
        documentos_faltantes=faltantes,
        hallazgos_expediente=exp,
        inconsistencias=inconsistencias,
        recomendacion=recomendacion,
        confianza=_confianza(documentos, faltantes),
        resumen=" ".join(partes),
        razones=razones,
    )
