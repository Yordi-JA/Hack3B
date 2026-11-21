"""Agente Escrituras. Dueño: Carlos.

Extraer (CONTEXT.md): propietario o titular, dirección e identificación del inmueble,
superficie del terreno, datos relevantes, información que lo relaciona con el expediente.

Claves sugeridas para `datos.especificos`: numero_escritura, volumen, notario, fecha_escritura,
tipo_acto (compraventa, fusión, lotificación...), folio_real, medidas_colindancias, gravamenes.

Ojo: son las más largas (hasta 50 páginas). Los datos clave suelen estar en el proemio,
antecedentes y cláusulas; no mandar las 50 páginas al modelo.

Prefijo de reglas: ESC-.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, model_validator

from ..config import get_callbacks, get_llm
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
    Pagina,
    Severidad,
)

log = logging.getLogger(__name__)

# Palabras cuya presencia en una página sugiere datos clave del inmueble
PALABRAS_CLAVE_PAGINA = (
    "superficie", "colindanc", "catastral", "folio real",
    "gravamen", "hipotec", "numero oficial", "número oficial",
    "medida", "predio", "escritura", "notario",
)

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}

MAX_PAGINAS_LLM = 15
PRIMERAS_PAGINAS = 5

TIPOS_ACTO_TRASLATIVOS = {
    "COMPRAVENTA", "DONACION", "PERMUTA", "APORTACION",
    "DACION EN PAGO", "ADJUDICACION", "FUSION", "LOTIFICACION",
    "SUBDIVISION", "CESION DE DERECHOS",
}


# ---------------------------------------------------------------- modelo interno LLM

class _CampoLLM(BaseModel):
    valor: Optional[str] = Field(default=None, description="Dato tal como aparece en el documento")
    cita: Optional[str] = Field(default=None, description="Texto literal del documento que sustenta el dato (5-20 palabras)")
    pagina: Optional[int] = Field(default=None, description="Número de página donde aparece la cita")
    confianza: float = Field(default=0.0, ge=0, le=1)


class _EscrituraLLM(BaseModel):
    """Extracción cruda de la escritura antes de normalización y verificación."""

    @model_validator(mode="before")
    @classmethod
    def _normalizar_nulos(cls, data):
        # Claude a veces devuelve el campo entero como string "null" en lugar de
        # un objeto con valor=null. Lo mapeamos a un _CampoLLM vacío para que
        # Pydantic no explote y el campo salga como "no encontrado".
        if isinstance(data, dict):
            for clave, v in list(data.items()):
                if v is None:
                    data[clave] = {}
                elif isinstance(v, str) and v.strip().lower() in ("null", "none", ""):
                    data[clave] = {}
        return data

    propietario: _CampoLLM = Field(default_factory=_CampoLLM)
    direccion: _CampoLLM = Field(default_factory=_CampoLLM)
    superficie_terreno_m2: _CampoLLM = Field(default_factory=_CampoLLM)
    clave_catastral: _CampoLLM = Field(default_factory=_CampoLLM)
    numero_oficial: _CampoLLM = Field(default_factory=_CampoLLM)
    fecha_emision: _CampoLLM = Field(default_factory=_CampoLLM)
    autoridad_emisora: _CampoLLM = Field(default_factory=_CampoLLM)
    numero_escritura: _CampoLLM = Field(default_factory=_CampoLLM)
    volumen: _CampoLLM = Field(default_factory=_CampoLLM)
    notario: _CampoLLM = Field(default_factory=_CampoLLM)
    fecha_escritura: _CampoLLM = Field(default_factory=_CampoLLM)
    tipo_acto: _CampoLLM = Field(default_factory=_CampoLLM)
    folio_real: _CampoLLM = Field(default_factory=_CampoLLM)
    medidas_colindancias: _CampoLLM = Field(default_factory=_CampoLLM)
    gravamenes: _CampoLLM = Field(default_factory=_CampoLLM)


# ---------------------------------------------------------------- normalizadores

def _upper_sin_acentos(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s).strip()
    return s.upper() or None


def _normalizar_nombre(s: Optional[str]) -> Optional[str]:
    """Pasa 'Claudia Alejandra Méndez Salazar' a 'MENDEZ SALAZAR CLAUDIA ALEJANDRA'."""
    base = _upper_sin_acentos(s)
    if not base:
        return None
    base = re.sub(r"\b(C\.?|SR\.?|SRA\.?|LIC\.?|LICENCIADO|LICENCIADA|ING\.?|ARQ\.?|MTRO\.?|DR\.?)\s+", "", base)
    base = re.sub(r"\s+", " ", base).strip()
    tokens = base.split()
    if not tokens:
        return None
    if len(tokens) == 1:
        return tokens[0]
    if len(tokens) == 2:
        # Un apellido + un nombre: invertimos para quedar "APELLIDO NOMBRE".
        return f"{tokens[1]} {tokens[0]}"
    # Heurística conservadora: últimos 2 tokens = apellidos, resto = nombres.
    # Para nombres compuestos ("DE LA CRUZ") esto falla; con tiempo se mejora con un diccionario.
    apellidos = tokens[-2:]
    nombres = tokens[:-2]
    return " ".join(apellidos + nombres)


def _normalizar_direccion(s: Optional[str]) -> Optional[str]:
    base = _upper_sin_acentos(s)
    if not base:
        return None
    # Los punto/espacio opcionales van DENTRO del match para que no queden colgados.
    base = re.sub(r"\bNUM(?:ERO)?\.?\s*", "", base)
    base = re.sub(r"\bNO\.?\s+", "", base)
    base = re.sub(r"\bCOL(?:ONIA)?\.?\s*", "", base)
    base = re.sub(r"\bEXT(?:ERIOR)?\.?\s*", "", base)
    base = re.sub(r"\bINT(?:ERIOR)?\.?\s*", "", base)
    base = re.sub(r"\s+", " ", base).strip(", .")
    return base or None


def _normalizar_superficie(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    # Quitar espacios y separadores de miles antes de parsear.
    limpio = s.replace(" ", "")
    # Si el patrón es "1,250.50" (coma como miles) quitamos las comas.
    if re.match(r"^\d{1,3}(,\d{3})+(\.\d+)?", limpio):
        limpio = limpio.replace(",", "")
    # Si el patrón es "1250,50" (coma como decimal) la cambiamos a punto.
    elif re.match(r"^\d+,\d{1,3}$", limpio):
        limpio = limpio.replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", limpio)
    if not m:
        return None
    try:
        return f"{float(m.group(0)):.2f}"
    except ValueError:
        return None


def _normalizar_clave_catastral(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    limpio = re.sub(r"[^0-9A-Z]", "", s.upper())
    return limpio or None


def _normalizar_numero(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    m = re.search(r"\d+", s)
    return m.group(0) if m else None


def _normalizar_fecha(s: Optional[str]) -> Optional[str]:
    """ISO YYYY-MM-DD. Acepta '15 de marzo de 2019', '15/03/2019', '2019-03-15'."""
    if not s:
        return None
    low = s.lower().strip()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", low)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", low)
    if m:
        d, mo, y = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", low)
    if m:
        d, mes_txt, y = m.groups()
        mes_norm = _upper_sin_acentos(mes_txt).lower() if _upper_sin_acentos(mes_txt) else ""
        mo = MESES_ES.get(mes_norm)
        if mo:
            return f"{int(y):04d}-{mo:02d}-{int(d):02d}"
    return None


# ---------------------------------------------------------------- selección de páginas

def _seleccionar_paginas(doc: DocumentoLeido, maximo: int = MAX_PAGINAS_LLM) -> list[Pagina]:
    """Primeras N páginas + páginas con palabras clave, hasta `maximo` en total."""
    paginas = list(doc.paginas)
    if len(paginas) <= maximo:
        return paginas
    primeras = paginas[:PRIMERAS_PAGINAS]
    cupo = maximo - len(primeras)
    extra: list[Pagina] = []
    for p in paginas[PRIMERAS_PAGINAS:]:
        texto_bajo = p.texto.lower()
        if any(k in texto_bajo for k in PALABRAS_CLAVE_PAGINA):
            extra.append(p)
        if len(extra) >= cupo:
            break
    return primeras + extra


# ---------------------------------------------------------------- verificación de cita

def _limpia_para_match(s: str) -> str:
    base = _upper_sin_acentos(s) or ""
    return re.sub(r"[^A-Z0-9 ]", " ", re.sub(r"\s+", " ", base)).strip()


def _verificar_cita(cita: Optional[str], paginas: list[Pagina]) -> Optional[tuple[int, str]]:
    """Busca la cita en cada página. Devuelve (pagina, cita_original) si una firma de 6+ palabras calza."""
    if not cita or not cita.strip():
        return None
    limpio = _limpia_para_match(cita)
    palabras = limpio.split()
    if len(palabras) < 4:
        return None
    firma = " ".join(palabras[: min(10, len(palabras))])
    firma_corta = " ".join(palabras[:6])
    for p in paginas:
        tx = _limpia_para_match(p.texto)
        if firma in tx or firma_corta in tx:
            return (p.numero, cita.strip())
    return None


# ---------------------------------------------------------------- construcción de Campo

def _construir_campo(
    extraido: _CampoLLM,
    archivo: str,
    paginas: list[Pagina],
    normalizador: Optional[Callable[[Optional[str]], Optional[str]]] = None,
) -> Campo:
    """Convierte un _CampoLLM a Campo del contrato, verificando evidencia."""
    if not extraido.valor or not extraido.valor.strip():
        return Campo()

    match = _verificar_cita(extraido.cita, paginas)
    if match is not None:
        pagina, cita = match
        evidencia = Evidencia(archivo=archivo, pagina=pagina, cita=cita)
        confianza = extraido.confianza
    else:
        # La cita del LLM no se encontró en el texto: la evidencia es inválida.
        # Degradamos la confianza; el valor se conserva pero sin evidencia que lo respalde.
        evidencia = None
        confianza = max(0.0, extraido.confianza - 0.4)

    normalizado = normalizador(extraido.valor) if normalizador else _upper_sin_acentos(extraido.valor)
    return Campo(
        valor=extraido.valor,
        normalizado=normalizado,
        evidencia=evidencia,
        confianza=round(confianza, 2),
    )


# ---------------------------------------------------------------- prompt

_PROMPT_SISTEMA = """Eres un extractor de datos de ESCRITURAS PÚBLICAS mexicanas para el equipo legal de Tiendas 3B.

Tu tarea: leer el texto transcrito de una escritura (viene de OCR, puede traer errores) y llenar un objeto estructurado con los datos del INMUEBLE OBJETO de la escritura.

REGLAS DURAS (si las rompes, el dictamen pierde confianza):
1. Solo extraes lo que aparece LITERAL en el texto. No infieres, no deduces, no completas.
2. Para cada dato devuelves: `valor` (como aparece en el documento), `cita` (texto EXACTO del documento donde está, 5-20 palabras), `pagina` (número 1-indexado) y `confianza` entre 0 y 1.
3. Si un dato no aparece claramente, devuelves `valor=null`, `cita=null`, `confianza=0`. NUNCA inventas una cita.
4. Si hay varias ocurrencias de un concepto (p.ej. varios domicilios), eliges la que corresponde al INMUEBLE OBJETO de la escritura, no al del vendedor, representante, notaría ni testigos.
5. `cita` debe ser una subcadena que un `Ctrl+F` en el documento encontraría — no la reescribas.

CAMPOS (descripciones precisas):
- propietario: nombre completo del ADQUIRENTE / comprador / beneficiario (quien QUEDA como titular tras la escritura).
- direccion: dirección completa del inmueble (calle, número, colonia, municipio, estado).
- superficie_terreno_m2: superficie del TERRENO en metros cuadrados (devuélvela como aparece, con unidad).
- clave_catastral: clave catastral o cuenta predial del inmueble.
- numero_oficial: número oficial exterior asignado.
- fecha_emision: fecha de otorgamiento de la escritura ante el notario.
- autoridad_emisora: notaría pública (número + entidad federativa).
- numero_escritura: número de instrumento público / escritura.
- volumen: volumen o libro donde consta el instrumento.
- notario: nombre completo del notario público.
- fecha_escritura: igual que fecha_emision cuando solo hay una fecha.
- tipo_acto: naturaleza del acto (compraventa, donación, aportación, dación en pago, permuta, adjudicación, fusión, lotificación, cesión de derechos).
- folio_real: folio real electrónico o inscripción en el Registro Público de la Propiedad.
- medidas_colindancias: resumen corto de medidas y colindancias (NORTE, SUR, ORIENTE, PONIENTE).
- gravamenes: hipotecas, usufructos, servidumbres u otras cargas; si el documento dice "libre de gravámenes" o similar, pon ese texto.

Los párrafos del documento llegan con marcadores [P1], [P2], ... al inicio de cada página. Úsalos para llenar `pagina`.
"""


def _formatear_paginas(paginas: list[Pagina]) -> str:
    return "\n\n".join(f"[P{p.numero}]\n{p.texto}" for p in paginas)


# ---------------------------------------------------------------- reglas ESC-

def _h(id_regla: str, descripcion: str, estado: EstadoRegla, severidad: Severidad,
       explicacion: str, evidencias: tuple[Evidencia, ...] = ()) -> Hallazgo:
    return Hallazgo(
        id_regla=id_regla,
        descripcion=descripcion,
        estado=estado,
        severidad=severidad,
        explicacion=explicacion,
        evidencias=[e for e in evidencias if e is not None],
    )


def _aplicar_reglas(datos: DatosInmueble) -> list[Hallazgo]:
    h: list[Hallazgo] = []

    # ESC-01 identificación del titular
    if datos.propietario.valor:
        h.append(_h("ESC-01", "La escritura identifica al titular del inmueble",
                    EstadoRegla.CUMPLE, Severidad.INFO,
                    f"Titular identificado: {datos.propietario.valor}.",
                    (datos.propietario.evidencia,)))
    else:
        h.append(_h("ESC-01", "La escritura identifica al titular del inmueble",
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    "No se pudo extraer al titular del inmueble."))

    # ESC-02 dirección del inmueble
    if datos.direccion.valor:
        h.append(_h("ESC-02", "La escritura identifica la dirección del inmueble",
                    EstadoRegla.CUMPLE, Severidad.INFO,
                    f"Dirección: {datos.direccion.valor}.",
                    (datos.direccion.evidencia,)))
    else:
        h.append(_h("ESC-02", "La escritura identifica la dirección del inmueble",
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    "No se extrajo la dirección del inmueble."))

    # ESC-03 superficie del terreno
    if datos.superficie_terreno_m2.valor:
        h.append(_h("ESC-03", "La escritura declara la superficie del terreno",
                    EstadoRegla.CUMPLE, Severidad.INFO,
                    f"Superficie declarada: {datos.superficie_terreno_m2.valor}.",
                    (datos.superficie_terreno_m2.evidencia,)))
    else:
        h.append(_h("ESC-03", "La escritura declara la superficie del terreno",
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    "No se extrajo la superficie del terreno."))

    # ESC-04 identificación del predio (catastral o folio real)
    folio = datos.especificos.get("folio_real")
    tiene_cat = bool(datos.clave_catastral.valor)
    tiene_folio = bool(folio and folio.valor)
    if tiene_cat or tiene_folio:
        evs = []
        if datos.clave_catastral.evidencia:
            evs.append(datos.clave_catastral.evidencia)
        if folio and folio.evidencia:
            evs.append(folio.evidencia)
        h.append(_h("ESC-04", "Identificación registral del predio (catastral o folio real)",
                    EstadoRegla.CUMPLE, Severidad.INFO,
                    "El predio se identifica con clave catastral o folio real.",
                    tuple(evs)))
    else:
        h.append(_h("ESC-04", "Identificación registral del predio (catastral o folio real)",
                    EstadoRegla.NO_CUMPLE, Severidad.REVISION,
                    "La escritura no presenta clave catastral ni folio real extraíbles."))

    # ESC-05 acto traslativo de dominio
    tipo_acto = datos.especificos.get("tipo_acto")
    if tipo_acto and tipo_acto.normalizado:
        es_traslativo = any(t in tipo_acto.normalizado for t in TIPOS_ACTO_TRASLATIVOS)
        if es_traslativo:
            h.append(_h("ESC-05", "La escritura es un acto traslativo de dominio",
                        EstadoRegla.CUMPLE, Severidad.INFO,
                        f"Tipo de acto: {tipo_acto.valor}.",
                        (tipo_acto.evidencia,)))
        else:
            h.append(_h("ESC-05", "La escritura es un acto traslativo de dominio",
                        EstadoRegla.NO_CUMPLE, Severidad.REVISION,
                        f"El acto detectado ({tipo_acto.valor}) no es claramente traslativo de dominio.",
                        (tipo_acto.evidencia,)))
    else:
        h.append(_h("ESC-05", "La escritura es un acto traslativo de dominio",
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    "No se identificó el tipo de acto en la escritura."))

    # ESC-06 gravámenes
    gravamenes = datos.especificos.get("gravamenes")
    if gravamenes and gravamenes.valor:
        t_low = gravamenes.valor.lower()
        libre = any(k in t_low for k in ("libre", "no reporta", "sin gravamen", "sin carga"))
        hipoteca = "hipotec" in t_low
        if libre:
            h.append(_h("ESC-06", "Gravámenes o limitaciones al dominio",
                        EstadoRegla.CUMPLE, Severidad.INFO,
                        "La escritura declara el inmueble libre de gravámenes.",
                        (gravamenes.evidencia,)))
        else:
            h.append(_h("ESC-06", "Gravámenes o limitaciones al dominio",
                        EstadoRegla.NO_CUMPLE,
                        Severidad.BLOQUEANTE if hipoteca else Severidad.REVISION,
                        f"Se declaran gravámenes o limitaciones: {gravamenes.valor}.",
                        (gravamenes.evidencia,)))
    else:
        h.append(_h("ESC-06", "Gravámenes o limitaciones al dominio",
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    "No se extrajo información explícita sobre gravámenes."))

    # ESC-07 notario e instrumento
    num_esc = datos.especificos.get("numero_escritura")
    notario = datos.especificos.get("notario")
    tiene_num = bool(num_esc and num_esc.valor)
    tiene_not = bool(notario and notario.valor)
    if tiene_num and tiene_not:
        evs = []
        if num_esc and num_esc.evidencia:
            evs.append(num_esc.evidencia)
        if notario and notario.evidencia:
            evs.append(notario.evidencia)
        h.append(_h("ESC-07", "Datos del notario y número de escritura identificados",
                    EstadoRegla.CUMPLE, Severidad.INFO,
                    f"Instrumento {num_esc.valor} ante {notario.valor}.",
                    tuple(evs)))
    else:
        faltan = []
        if not tiene_num:
            faltan.append("número de escritura")
        if not tiene_not:
            faltan.append("notario")
        h.append(_h("ESC-07", "Datos del notario y número de escritura identificados",
                    EstadoRegla.NO_CUMPLE, Severidad.REVISION,
                    f"Falta extraer: {', '.join(faltan)}."))

    return h


def _resultado_ilegible(doc: DocumentoLeido) -> DocumentoAnalizado:
    hallazgo = _h(
        "ESC-ILEG",
        "Documento ilegible; no se extrae información",
        EstadoRegla.NO_EVALUABLE,
        Severidad.REVISION,
        "La ingesta marcó el documento como ILEGIBLE. No se intentó extracción para no inventar datos.",
    )
    return DocumentoAnalizado(
        archivo=doc.archivo,
        tipo=doc.tipo,
        confianza_tipo=doc.confianza_tipo,
        legibilidad=doc.legibilidad,
        datos=DatosInmueble(),
        hallazgos=[hallazgo],
        confianza=0.0,
    )


# ---------------------------------------------------------------- entry point

def analizar(doc: DocumentoLeido, ctx: Contexto) -> DocumentoAnalizado:
    if doc.legibilidad == Legibilidad.ILEGIBLE or not doc.paginas:
        return _resultado_ilegible(doc)

    paginas_para_llm = _seleccionar_paginas(doc)
    texto = _formatear_paginas(paginas_para_llm)

    llm = get_llm().with_structured_output(_EscrituraLLM)
    extraido: _EscrituraLLM = llm.invoke(
        [SystemMessage(content=_PROMPT_SISTEMA), HumanMessage(content=texto)],
        config={"callbacks": get_callbacks()},
    )

    datos = DatosInmueble(
        propietario=_construir_campo(extraido.propietario, doc.archivo, doc.paginas, _normalizar_nombre),
        direccion=_construir_campo(extraido.direccion, doc.archivo, doc.paginas, _normalizar_direccion),
        superficie_terreno_m2=_construir_campo(extraido.superficie_terreno_m2, doc.archivo, doc.paginas, _normalizar_superficie),
        clave_catastral=_construir_campo(extraido.clave_catastral, doc.archivo, doc.paginas, _normalizar_clave_catastral),
        numero_oficial=_construir_campo(extraido.numero_oficial, doc.archivo, doc.paginas, _normalizar_numero),
        fecha_emision=_construir_campo(extraido.fecha_emision, doc.archivo, doc.paginas, _normalizar_fecha),
        vigencia_hasta=Campo(),  # las escrituras no vencen; se deja vacío
        autoridad_emisora=_construir_campo(extraido.autoridad_emisora, doc.archivo, doc.paginas),
    )

    datos.especificos = {
        "numero_escritura": _construir_campo(extraido.numero_escritura, doc.archivo, doc.paginas, _normalizar_numero),
        "volumen": _construir_campo(extraido.volumen, doc.archivo, doc.paginas),
        "notario": _construir_campo(extraido.notario, doc.archivo, doc.paginas),
        "fecha_escritura": _construir_campo(extraido.fecha_escritura, doc.archivo, doc.paginas, _normalizar_fecha),
        "tipo_acto": _construir_campo(extraido.tipo_acto, doc.archivo, doc.paginas),
        "folio_real": _construir_campo(extraido.folio_real, doc.archivo, doc.paginas),
        "medidas_colindancias": _construir_campo(extraido.medidas_colindancias, doc.archivo, doc.paginas),
        "gravamenes": _construir_campo(extraido.gravamenes, doc.archivo, doc.paginas),
    }

    hallazgos = _aplicar_reglas(datos)

    # Confianza global del análisis: promedio de confianzas de los campos poblados.
    campos_comunes = [
        datos.propietario, datos.direccion, datos.superficie_terreno_m2,
        datos.clave_catastral, datos.numero_oficial, datos.fecha_emision,
        datos.autoridad_emisora,
    ]
    todos_campos = campos_comunes + list(datos.especificos.values())
    confianzas = [c.confianza for c in todos_campos if c.valor]
    conf_global = round(sum(confianzas) / len(confianzas), 2) if confianzas else 0.0

    return DocumentoAnalizado(
        archivo=doc.archivo,
        tipo=doc.tipo,
        confianza_tipo=doc.confianza_tipo,
        legibilidad=doc.legibilidad,
        datos=datos,
        hallazgos=hallazgos,
        confianza=conf_global,
    )
