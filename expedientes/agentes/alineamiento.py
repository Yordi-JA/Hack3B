"""Agente Alineamiento y Número Oficial. Dueño: Diego.

Extraer (CONTEXT.md): dirección oficial, número oficial asignado, identificación del predio,
alineamiento determinado por la autoridad, fecha de emisión y vigencia, autoridad emisora.

Cómo trabaja:
1. `extraer()`: el LLM lee la transcripción y devuelve cada dato con página y cita literal.
2. `verificar_citas()`: cada cita se busca en el texto de su página. Si no aparece, se busca en
   las demás; si no está en ninguna, el dato pierde confianza (el LLM pudo inventarlo).
3. `evaluar()`: las reglas ALI- son deterministas, en Python, sobre lo ya verificado.

Claves en `datos.especificos`: folio, alineamiento, restricciones_construccion, seccion_vial,
afectaciones, superficie_afectada_m2, vigencia_texto, administracion.

Alineamiento y Número Oficial pueden venir en dos archivos separados: a cada uno le faltan los
datos del otro y esas reglas salen NO_EVALUABLE (el dictamen consolida por tipo).

Prefijo de reglas: ALI-.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from ..cache import nombre_archivo
from ..config import CACHE_DIR, LLM_MODEL, get_callbacks, get_llm
from ..schemas import (
    Campo,
    Contexto,
    DatosInmueble,
    DocumentoAnalizado,
    DocumentoLeido,
    EstadoRegla,
    Evidencia,
    Hallazgo,
    Legibilidad,
    Severidad,
    TipoDocumento,
)
from . import normalizar as nz

log = logging.getLogger(__name__)

# Severidades configurables. El reto castiga descartar expedientes que sí podían continuar,
# así que lo que se resuelve con un trámite (renovar la constancia) es REVISION, no BLOQUEANTE.
SEVERIDAD_VENCIDA = Severidad.REVISION
SEVERIDAD_AFECTACION = Severidad.REVISION
SEVERIDAD_SIN_NUMERO = Severidad.REVISION


# ---------------------------------------------------------------- salida estructurada del LLM

class DatoExtraido(BaseModel):
    valor: str = Field(description="Tal como aparece en el documento")
    normalizado: Optional[str] = Field(default=None, description="Forma comparable (ver instrucciones)")
    pagina: int = Field(ge=1, description="Página donde aparece")
    cita: str = Field(description="Fragmento LITERAL copiado del texto que contiene el dato, máx. 200 caracteres")
    confianza: float = Field(ge=0, le=1)


class ExtraccionAlineamiento(BaseModel):
    contiene_alineamiento: bool = Field(description="El documento determina el alineamiento del predio")
    contiene_numero_oficial: bool = Field(description="El documento asigna o consigna un número oficial")
    propietario: Optional[DatoExtraido] = Field(default=None, description="Propietario, poseedor o solicitante a cuyo favor se expide")
    direccion: Optional[DatoExtraido] = Field(default=None, description="Calle, número, colonia, municipio y estado del predio")
    municipio: Optional[DatoExtraido] = Field(default=None, description="Municipio del predio. Si no viene en la dirección, el del ayuntamiento que expide. normalizado: mayúsculas sin acentos")
    entidad_federativa: Optional[DatoExtraido] = Field(default=None, description="Estado del predio. Puede venir solo en encabezado, sello, lugar y fecha o texto legal: búscalo en todo el documento. normalizado: 'HIDALGO', 'MEXICO' (Estado de México), etc.")
    superficie_terreno_m2: Optional[DatoExtraido] = Field(default=None, description="Superficie del predio. normalizado: solo el número en m², punto decimal")
    clave_catastral: Optional[DatoExtraido] = Field(default=None, description="Clave catastral o cuenta predial. normalizado: solo dígitos")
    numero_oficial: Optional[DatoExtraido] = Field(default=None, description="Número oficial asignado. normalizado: '28', '104A' o 'SN' si dice sin número")
    fecha_emision: Optional[DatoExtraido] = Field(default=None, description="Fecha de expedición. normalizado: AAAA-MM-DD")
    vigencia_texto: Optional[DatoExtraido] = Field(default=None, description="Lo que diga el documento sobre su vigencia, literal")
    vigencia_hasta: Optional[DatoExtraido] = Field(default=None, description="Solo si el documento trae una fecha de vencimiento explícita. normalizado: AAAA-MM-DD")
    autoridad_emisora: Optional[DatoExtraido] = Field(default=None, description="Ayuntamiento y dirección que expide, ej. 'Dirección de Desarrollo Urbano, H. Ayuntamiento de Tultepec'")
    administracion: Optional[DatoExtraido] = Field(default=None, description="Periodo de gobierno del encabezado. normalizado: 'AAAA-AAAA'")
    folio: Optional[DatoExtraido] = None
    alineamiento: Optional[DatoExtraido] = Field(default=None, description="Alineamiento determinado: metros de frente, a qué vialidad, o 'correctamente alineado'")
    restricciones_construccion: Optional[DatoExtraido] = Field(default=None, description="Restricción de construcción al frente, derecho de vía, etc.")
    seccion_vial: Optional[DatoExtraido] = None
    afectaciones: Optional[DatoExtraido] = Field(default=None, description="Afectaciones al predio (ampliación de vialidad, derecho de vía, franja no construible). null si no hay")
    superficie_afectada_m2: Optional[DatoExtraido] = Field(default=None, description="normalizado: solo el número en m²")


INSTRUCCIONES = """Eres el agente extractor de Constancias de Alineamiento y Número Oficial de inmuebles en México \
(municipios de Hidalgo y Estado de México). Recibes la transcripción de un documento, página por página.

Reglas estrictas:
- Extrae SOLO lo que está escrito en el texto. Si un dato no aparece, déjalo en null. Nunca lo deduzcas ni lo inventes.
- `cita` debe ser un fragmento copiado LITERALMENTE del texto (mismas palabras), que contenga el dato. Máximo 200 caracteres.
- `pagina` es el número de la página donde está la cita.
- `confianza` baja (< 0.6) si el texto está cortado, dudoso o con errores de OCR.
- El documento puede ser solo de Alineamiento, solo de Número Oficial, o ambos.
- `propietario`: la persona o empresa a cuyo favor se expide. Suele aparecer como "C. NOMBRE" justo antes de \
"Esta Dirección en contestación a su solicitud", o en un campo "Nombre del propietario / poseedor".
- `afectaciones`: solo si el documento dice que una parte del predio queda afectada o no se puede construir en ella: \
"el predio presenta afectación", ampliación de calle sobre el predio, o una restricción de construcción con metros \
MAYORES a 0 ("la restricción para este predio es de 3.00 m"). NO son afectaciones: mencionar el derecho de vía o su \
ancho, el frente del predio al derecho de vía, una restricción de 0.00 m, títulos genéricos como "restricción por \
derecho de vía" sin medida aplicada al predio, ni la frase "no constituye autorización".
- `numero_oficial`: el número asignado al predio. Si el documento no asigna número pero la dirección del predio trae \
uno ("Josefa Ortiz de Domínguez, número 24"), usa ese con confianza menor. Si dice "sin número", "S/N" o "SN", normalizado = "SN".
- `clave_catastral`: la clave catastral; si no hay, la cuenta predial o el número de boleta predial (ej. "U-04817").
- `vigencia_texto`: cópialo aunque sea un plazo ("365 días a partir de su expedición", "seis meses").
- Fechas escritas con letra ("Veinticuatro de Enero del año dos mil Ocho") se normalizan igual a AAAA-MM-DD."""


def _paginas_como_texto(doc: DocumentoLeido) -> str:
    # Regla 8 del README: solo páginas con texto (la ingesta vacía las borrosas).
    return "\n\n".join(f"=== PÁGINA {p.numero} ===\n{p.texto}" for p in doc.paginas if p.texto.strip())


# La salida estructurada de Claude admite como máximo 16 campos anulables por esquema. Al LLM se le
# pide una versión sin nulos (cada dato con `encontrado`) y luego se convierte a ExtraccionAlineamiento.

class _DatoLLM(BaseModel):
    encontrado: bool = Field(description="false si el dato no aparece en el documento; entonces deja los demás vacíos")
    valor: str = Field(description="Tal como aparece en el documento; '' si no se encontró")
    normalizado: str = Field(description="Forma comparable (ver la descripción del campo); '' si no aplica")
    pagina: int = Field(description="Página donde aparece; 0 si no se encontró")
    cita: str = Field(description="Fragmento LITERAL copiado del texto que contiene el dato, máx. 200 caracteres; '' si no se encontró")
    confianza: float = Field(description="0 a 1")


def _modelo_llm() -> type[BaseModel]:
    from pydantic import create_model
    campos = {}
    for nombre, f in ExtraccionAlineamiento.model_fields.items():
        if f.annotation is bool:
            campos[nombre] = (bool, Field(description=f.description))
        else:
            campos[nombre] = (_DatoLLM, Field(description=f.description or nombre))
    return create_model("ExtraccionAlineamientoLLM", **campos)


_ExtraccionLLM = _modelo_llm()


def _desde_llm(r: BaseModel) -> ExtraccionAlineamiento:
    datos = {}
    for nombre, valor in r:
        if isinstance(valor, _DatoLLM):
            if valor.encontrado and valor.valor.strip():
                datos[nombre] = DatoExtraido(
                    valor=valor.valor, normalizado=valor.normalizado or None, pagina=max(valor.pagina, 1),
                    cita=valor.cita or valor.valor, confianza=min(max(valor.confianza, 0.0), 1.0),
                )
        else:
            datos[nombre] = valor
    return ExtraccionAlineamiento(**datos)


def _ruta_respuesta(doc: DocumentoLeido, entrada: str) -> tuple[Path, str]:
    """Caché de respuestas del LLM (regla 5 del README): misma entrada, mismo modelo, mismo prompt
    y mismo esquema -> se reutiliza la respuesta guardada sin llamar a la API."""
    huella = hashlib.sha256("\n".join([
        LLM_MODEL, INSTRUCCIONES, json.dumps(_ExtraccionLLM.model_json_schema(), sort_keys=True), entrada,
    ]).encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / "analisis" / "alineamiento" / f"{nombre_archivo(doc.archivo)}.json", huella


def extraer(doc: DocumentoLeido) -> ExtraccionAlineamiento:
    entrada = f"Archivo: {doc.archivo}\n\n{_paginas_como_texto(doc)}"
    ruta, huella = _ruta_respuesta(doc, entrada)
    if ruta.exists():
        guardado = json.loads(ruta.read_text(encoding="utf-8"))
        if guardado.get("huella") == huella:
            return _desde_llm(_ExtraccionLLM.model_validate(guardado["respuesta"]))

    # json_schema = salida estructurada nativa de Claude: el JSON siempre cumple el esquema.
    # El modo por defecto (tool calling) no puede forzarse en Opus 5.5 / Sonnet 5.5.
    llm = get_llm(effort="low", max_tokens=4000).with_structured_output(_ExtraccionLLM, method="json_schema")
    r = llm.invoke([("system", INSTRUCCIONES), ("human", entrada)],
                   config={"callbacks": get_callbacks(), "run_name": f"alineamiento:{doc.archivo}"})
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"huella": huella, "modelo": LLM_MODEL, "respuesta": r.model_dump()},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return _desde_llm(r)


# ---------------------------------------------------------------- verificación de citas

def _cita_en(cita: str, texto_pagina: str) -> bool:
    c, t = nz.texto(cita), nz.texto(texto_pagina)
    if not c:
        return False
    if c in t:
        return True
    tokens = c.split()
    presentes = set(t.split())
    return len(tokens) >= 3 and sum(tok in presentes for tok in tokens) / len(tokens) >= 0.85


def verificar_citas(ext: ExtraccionAlineamiento, doc: DocumentoLeido) -> list[str]:
    """Corrige páginas mal atribuidas y castiga datos cuya cita no está en el documento.
    Devuelve los nombres de los datos que no se pudieron verificar."""
    textos = {p.numero: p.texto for p in doc.paginas}
    no_verificados = []
    for nombre in ExtraccionAlineamiento.model_fields:
        dato = getattr(ext, nombre)
        if not isinstance(dato, DatoExtraido):
            continue
        if _cita_en(dato.cita, textos.get(dato.pagina, "")):
            continue
        otra = next((n for n, t in textos.items() if _cita_en(dato.cita, t)), None)
        if otra:
            dato.pagina = otra
        else:
            dato.confianza = round(dato.confianza * 0.5, 2)
            no_verificados.append(nombre)
    return no_verificados


# ---------------------------------------------------------------- reglas

def _ev(doc: DocumentoLeido, dato: Optional[DatoExtraido]) -> list[Evidencia]:
    return [Evidencia(archivo=doc.archivo, pagina=dato.pagina, cita=dato.cita)] if dato else []


def _campo(doc: DocumentoLeido, dato: Optional[DatoExtraido], normalizado: Optional[str] = None) -> Campo:
    if dato is None:
        return Campo()
    return Campo(
        valor=dato.valor,
        normalizado=normalizado if normalizado is not None else dato.normalizado,
        evidencia=_ev(doc, dato)[0],
        confianza=dato.confianza,
    )


def _h(id_regla, descripcion, estado, severidad, explicacion, evidencias=()) -> Hallazgo:
    return Hallazgo(
        id_regla=id_regla, descripcion=descripcion, estado=estado, severidad=severidad,
        explicacion=explicacion, evidencias=list(evidencias),
    )


def _fmt(f: date) -> str:
    return f.strftime("%d/%m/%Y")


def calcular_vencimiento(ext: ExtraccionAlineamiento) -> tuple[Optional[date], str]:
    """Devuelve (fecha de vencimiento, modo). modo: 'explicita' | 'calculada' | 'indefinida' | 'sin_dato'."""
    if ext.vigencia_hasta:
        f = nz.fecha(ext.vigencia_hasta.normalizado) or nz.fecha(ext.vigencia_hasta.valor)
        if f:
            return f, "explicita"
    if ext.vigencia_texto:
        t = nz.texto(ext.vigencia_texto.valor)
        if re.search(r"EN TANTO|MIENTRAS NO|INDEFINID|PERMANENTE|SIN VENCIMIENTO", t):
            return None, "indefinida"
        emision = ext.fecha_emision and (nz.fecha(ext.fecha_emision.normalizado) or nz.fecha(ext.fecha_emision.valor))
        meses = None
        if re.search(r"\b(UN|1) ANO\b|DOCE MESES|12 MESES", t):
            meses = 12
        elif m := re.search(r"\b(\d+) MESES\b", t):
            meses = int(m.group(1))
        elif re.search(r"SEIS MESES", t):
            meses = 6
        elif m := re.search(r"\b(\d+) ANOS\b", t):
            meses = 12 * int(m.group(1))
        if meses and emision:
            return nz.sumar_meses(emision, meses), "calculada"
        if (m := re.search(r"\b(\d+) DIAS\b", t)) and emision:
            from datetime import timedelta
            return emision + timedelta(days=int(m.group(1))), "calculada"
        f = nz.fecha(ext.vigencia_texto.valor)
        if f:
            return f, "explicita"
    return None, "sin_dato"


def evaluar(ext: ExtraccionAlineamiento, doc: DocumentoLeido, ctx: Contexto) -> list[Hallazgo]:
    hs: list[Hallazgo] = []
    NE, C, NC = EstadoRegla.NO_EVALUABLE, EstadoRegla.CUMPLE, EstadoRegla.NO_CUMPLE

    # ALI-01 número oficial asignado
    no = ext.numero_oficial and nz.numero_oficial(ext.numero_oficial.normalizado or ext.numero_oficial.valor)
    if no and no != nz.SIN_NUMERO:
        hs.append(_h("ALI-01", "La autoridad asigna un número oficial al predio", C, Severidad.INFO,
                     f"Número oficial asignado: {ext.numero_oficial.valor}.", _ev(doc, ext.numero_oficial)))
    elif no == nz.SIN_NUMERO:
        hs.append(_h("ALI-01", "La autoridad asigna un número oficial al predio", NC, SEVERIDAD_SIN_NUMERO,
                     "La constancia consigna el predio como SIN NÚMERO: no hay número oficial asignado. "
                     "Verificar si existe una constancia de número oficial aparte.", _ev(doc, ext.numero_oficial)))
    else:
        hs.append(_h("ALI-01", "La autoridad asigna un número oficial al predio", NE,
                     Severidad.INFO if ext.contiene_alineamiento and not ext.contiene_numero_oficial else Severidad.REVISION,
                     "Este archivo no consigna número oficial (puede venir en una constancia separada)."))

    # ALI-02 vigencia
    vence, modo = calcular_vencimiento(ext)
    ev_vig = _ev(doc, ext.vigencia_hasta or ext.vigencia_texto)
    if modo == "indefinida":
        hs.append(_h("ALI-02", "Constancia vigente a la fecha de referencia", C, Severidad.INFO,
                     f"La vigencia no tiene fecha de vencimiento: «{ext.vigencia_texto.valor}».", ev_vig))
    elif vence:
        como = "según la fecha de vencimiento del documento" if modo == "explicita" else \
            f"calculado desde la emisión ({ext.fecha_emision.valor}) y la vigencia indicada"
        if vence >= ctx.fecha_referencia:
            hs.append(_h("ALI-02", "Constancia vigente a la fecha de referencia", C, Severidad.INFO,
                         f"Vigente hasta el {_fmt(vence)} ({como}).", ev_vig + _ev(doc, ext.fecha_emision)))
        else:
            hs.append(_h("ALI-02", "Constancia vigente a la fecha de referencia", NC, SEVERIDAD_VENCIDA,
                         f"Venció el {_fmt(vence)} ({como}), antes de la fecha de referencia "
                         f"{_fmt(ctx.fecha_referencia)}. Hay que solicitar una constancia actualizada.",
                         ev_vig + _ev(doc, ext.fecha_emision)))
    else:
        hs.append(_h("ALI-02", "Constancia vigente a la fecha de referencia", NE, Severidad.INFO,
                     "El documento no indica vigencia; la del alineamiento depende de la normativa municipal.",
                     _ev(doc, ext.fecha_emision)))

    # ALI-03 afectaciones
    if ext.afectaciones:
        sup = ext.superficie_afectada_m2
        extra = f" Superficie afectada: {sup.valor}." if sup else ""
        hs.append(_h("ALI-03", "El predio no tiene afectaciones", NC, SEVERIDAD_AFECTACION,
                     f"La autoridad señala una afectación al predio: «{ext.afectaciones.valor}».{extra} "
                     "Reduce la superficie aprovechable; revisar si la tienda cabe en la superficie restante.",
                     _ev(doc, ext.afectaciones) + _ev(doc, sup)))
    elif ext.contiene_alineamiento and ext.alineamiento:
        hs.append(_h("ALI-03", "El predio no tiene afectaciones", C, Severidad.INFO,
                     "La constancia determina el alineamiento sin señalar afectaciones.",
                     _ev(doc, ext.alineamiento)))
    else:
        hs.append(_h("ALI-03", "El predio no tiene afectaciones", NE, Severidad.INFO,
                     "Este archivo no determina alineamiento, así que no informa sobre afectaciones."))

    # ALI-04 alineamiento determinado
    if ext.alineamiento:
        hs.append(_h("ALI-04", "La autoridad determina el alineamiento del predio", C, Severidad.INFO,
                     f"Alineamiento: {ext.alineamiento.valor}.", _ev(doc, ext.alineamiento)))
    else:
        hs.append(_h("ALI-04", "La autoridad determina el alineamiento del predio", NE,
                     Severidad.INFO if ext.contiene_numero_oficial and not ext.contiene_alineamiento else Severidad.REVISION,
                     "Este archivo no determina el alineamiento (puede venir en una constancia separada)."))

    # ALI-05 identificación del predio
    if ext.clave_catastral:
        hs.append(_h("ALI-05", "El predio está identificado (clave catastral o cuenta predial)", C, Severidad.INFO,
                     f"Identificado con {ext.clave_catastral.valor}.", _ev(doc, ext.clave_catastral)))
    else:
        hs.append(_h("ALI-05", "El predio está identificado (clave catastral o cuenta predial)", NE, Severidad.REVISION,
                     "No se encontró clave catastral ni cuenta predial: la relación con el resto del expediente "
                     "depende solo de la dirección y el propietario."))

    # ALI-06 autoridad emisora
    if ext.autoridad_emisora:
        hs.append(_h("ALI-06", "Se identifica la autoridad emisora", C, Severidad.INFO,
                     f"Emitida por {ext.autoridad_emisora.valor}.", _ev(doc, ext.autoridad_emisora)))
    else:
        hs.append(_h("ALI-06", "Se identifica la autoridad emisora", NE, Severidad.REVISION,
                     "No se identificó qué autoridad expide la constancia."))

    # ALI-07 fecha de emisión coherente (no futura, dentro del periodo de la administración)
    emision = ext.fecha_emision and (nz.fecha(ext.fecha_emision.normalizado) or nz.fecha(ext.fecha_emision.valor))
    periodo = ext.administracion and re.findall(r"(\d{4})", ext.administracion.normalizado or ext.administracion.valor)
    if emision and emision > ctx.fecha_referencia:
        hs.append(_h("ALI-07", "Fecha de emisión coherente", NC, Severidad.REVISION,
                     f"La fecha de emisión ({_fmt(emision)}) es posterior a la fecha de referencia.",
                     _ev(doc, ext.fecha_emision)))
    elif emision and periodo and len(periodo) >= 2:
        ini, fin = int(periodo[0]), int(periodo[-1])
        if ini <= emision.year <= fin:
            hs.append(_h("ALI-07", "Fecha de emisión coherente", C, Severidad.INFO,
                         f"Emitida en {emision.year}, dentro del periodo de la administración {ini}-{fin}.",
                         _ev(doc, ext.fecha_emision) + _ev(doc, ext.administracion)))
        else:
            hs.append(_h("ALI-07", "Fecha de emisión coherente", NC, Severidad.REVISION,
                         f"El encabezado corresponde a la administración {ini}-{fin}, pero la constancia está fechada "
                         f"en {emision.year}. Posible documento alterado o formato reutilizado: verificar con el municipio.",
                         _ev(doc, ext.fecha_emision) + _ev(doc, ext.administracion)))
    return hs


# ---------------------------------------------------------------- agente

def entidad(s: Optional[str]) -> Optional[str]:
    """'Edo. Méx.', 'Estado de México' -> 'MEXICO'; 'Hgo.' -> 'HIDALGO' (formato del contrato)."""
    t = nz.texto(s)
    if not t:
        return None
    if re.search(r"\bHGO\b|HIDALGO", t):
        return "HIDALGO"
    if re.search(r"CIUDAD DE MEXICO|\bCDMX\b", t):
        return "CIUDAD DE MEXICO"
    if re.search(r"\bMEX\b|MEXICO", t):
        return "MEXICO"
    return re.sub(r"^(ESTADO|EDO)( LIBRE Y SOBERANO)? DE ", "", t)


def _vacio(doc: DocumentoLeido, hallazgos: list[Hallazgo]) -> DocumentoAnalizado:
    return DocumentoAnalizado(
        archivo=doc.archivo, tipo=TipoDocumento.ALINEAMIENTO, confianza_tipo=doc.confianza_tipo,
        legibilidad=doc.legibilidad, datos=DatosInmueble(), hallazgos=hallazgos, confianza=0.0,
    )


def construir(ext: ExtraccionAlineamiento, doc: DocumentoLeido, ctx: Contexto,
              no_verificados: Optional[list[str]] = None) -> DocumentoAnalizado:
    """Arma el DocumentoAnalizado a partir de una extracción ya verificada (sin llamar al LLM)."""
    vence, modo = calcular_vencimiento(ext)
    vigencia = _campo(doc, ext.vigencia_hasta or ext.vigencia_texto)
    if vigencia.valor is not None:
        vigencia.normalizado = vence.isoformat() if vence else ("INDEFINIDA" if modo == "indefinida" else None)

    sup = ext.superficie_terreno_m2 and nz.superficie(ext.superficie_terreno_m2.normalizado or ext.superficie_terreno_m2.valor)
    clave = ext.clave_catastral and nz.digitos(ext.clave_catastral.normalizado or ext.clave_catastral.valor)
    emision = ext.fecha_emision and (nz.fecha(ext.fecha_emision.normalizado) or nz.fecha(ext.fecha_emision.valor))
    datos = DatosInmueble(
        propietario=_campo(doc, ext.propietario, ext.propietario and nz.texto(ext.propietario.valor)),
        direccion=_campo(doc, ext.direccion, ext.direccion and nz.texto(ext.direccion.normalizado or ext.direccion.valor)),
        municipio=_campo(doc, ext.municipio, ext.municipio and nz.texto(ext.municipio.normalizado or ext.municipio.valor)),
        entidad_federativa=_campo(doc, ext.entidad_federativa, ext.entidad_federativa and entidad(
            ext.entidad_federativa.normalizado or ext.entidad_federativa.valor)),
        superficie_terreno_m2=_campo(doc, ext.superficie_terreno_m2, f"{sup:.2f}" if sup else None),
        clave_catastral=_campo(doc, ext.clave_catastral, clave or None),
        numero_oficial=_campo(doc, ext.numero_oficial, ext.numero_oficial and nz.numero_oficial(
            ext.numero_oficial.normalizado or ext.numero_oficial.valor)),
        fecha_emision=_campo(doc, ext.fecha_emision, emision.isoformat() if emision else None),
        vigencia_hasta=vigencia,
        autoridad_emisora=_campo(doc, ext.autoridad_emisora, ext.autoridad_emisora and nz.texto(ext.autoridad_emisora.valor)),
        especificos={
            k: _campo(doc, getattr(ext, k))
            for k in ("folio", "alineamiento", "restricciones_construccion", "seccion_vial", "afectaciones",
                      "superficie_afectada_m2", "vigencia_texto", "administracion")
            if getattr(ext, k) is not None
        },
    )
    hallazgos = evaluar(ext, doc, ctx)
    if no_verificados:
        hallazgos.append(_h("ALI-EVI", "Las citas de los datos extraídos están en el documento", EstadoRegla.NO_CUMPLE,
                            Severidad.REVISION,
                            f"No se encontró en el texto la cita de: {', '.join(no_verificados)}. "
                            "Esos datos tienen confianza reducida; confirmarlos contra el original."))
    if doc.legibilidad == Legibilidad.PARCIAL:
        # Solo pide revisión si la ilegibilidad se comió datos clave; si no, es una nota (evita falsas alarmas).
        faltan = [n for n, d in (("propietario", ext.propietario), ("dirección", ext.direccion),
                                 ("fecha de emisión", ext.fecha_emision)) if d is None]
        if not (ext.numero_oficial or ext.alineamiento):
            faltan.append("número oficial o alineamiento")
        if faltan:
            hallazgos.append(_h("ALI-LEG", "Documento legible", EstadoRegla.NO_CUMPLE, Severidad.REVISION,
                                f"El documento es parcialmente legible y no se pudo extraer: {', '.join(faltan)}."))
        else:
            hallazgos.append(_h("ALI-LEG", "Documento legible", EstadoRegla.CUMPLE, Severidad.INFO,
                                "El documento es parcialmente legible, pero se extrajeron todos los datos clave."))

    confs = [c.confianza for c in (datos.propietario, datos.direccion, datos.clave_catastral, datos.numero_oficial,
                                   datos.fecha_emision, datos.autoridad_emisora) if c.valor is not None]
    confianza = sum(confs) / len(confs) if confs else 0.0
    if doc.legibilidad == Legibilidad.PARCIAL:
        confianza *= 0.85
    return DocumentoAnalizado(
        archivo=doc.archivo, tipo=TipoDocumento.ALINEAMIENTO, confianza_tipo=doc.confianza_tipo,
        legibilidad=doc.legibilidad, datos=datos, hallazgos=hallazgos,
        confianza=round(min(confianza, doc.confianza_tipo), 2),
    )


def analizar(doc: DocumentoLeido, ctx: Contexto) -> DocumentoAnalizado:
    if doc.legibilidad == Legibilidad.ILEGIBLE or not any(p.texto.strip() for p in doc.paginas):
        return _vacio(doc, [_h("ALI-LEG", "Documento legible", EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                               "La constancia es ilegible: no se extrajo ningún dato para no inventar información. "
                               "Solicitar una copia legible.")])
    ext = extraer(doc)
    no_verificados = verificar_citas(ext, doc)
    return construir(ext, doc, ctx, no_verificados)


if __name__ == "__main__":
    # Prueba rápida contra el caché: python -m expedientes.agentes.alineamiento "<archivo.pdf>" [AAAA-MM-DD]
    from ..cache import leer_cache

    sys.stdout.reconfigure(encoding="utf-8")
    leido = leer_cache(sys.argv[1])
    if leido is None:
        sys.exit(f"No hay caché para {sys.argv[1]}")
    c = Contexto(fecha_referencia=date.fromisoformat(sys.argv[2])) if len(sys.argv) > 2 else Contexto()
    print(json.dumps(analizar(leido, c).model_dump(mode="json"), ensure_ascii=False, indent=2))
