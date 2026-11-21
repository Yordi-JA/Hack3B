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

import hashlib
import json
import logging
import re
import unicodedata
from typing import Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, model_validator

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
    Pagina,
    Severidad,
)

log = logging.getLogger(__name__)

# Caché de respuestas del LLM (regla 5 del equipo): clave = hash de
# modelo + prompt + esquema + texto. Repetir una corrida no gasta créditos.
DIR_ANALISIS = CACHE_DIR / "analisis" / "escritura"

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

# Todos los campos del schema son REQUIRED (sin default). Anthropic con tool_use
# acepta como máximo 24 parámetros opcionales en el schema; haciéndolos obligatorios
# con valor null posible, el límite no aplica.

class _CampoLLM(BaseModel):
    valor: Optional[str] = Field(description="Dato tal como aparece en el documento. null si no aparece.")
    cita: Optional[str] = Field(description="Texto literal del documento que sustenta el dato (3-20 palabras). null si no aparece.")
    pagina: Optional[int] = Field(description="Número de página 1-indexado donde aparece la cita. null si no aparece.")
    # Sin ge/le: method="json_schema" no acepta constraints numéricos; se clippea al construir Campo.
    confianza: float = Field(description="Confianza del extractor sobre este campo (0..1). 0.0 si no aparece.")


_CAMPOS_ESCRITURA_LLM = (
    "propietario", "direccion", "entidad_federativa", "municipio",
    "superficie_terreno_m2", "clave_catastral",
    "numero_oficial", "fecha_emision", "autoridad_emisora",
    "numero_escritura", "volumen", "notario", "fecha_escritura",
    "tipo_acto", "folio_real", "inscripcion_rpp", "medidas_colindancias",
    "gravamenes", "regimen_propiedad", "copropiedad", "embargo_o_litigio",
    "usufructo",
)


class _EscrituraLLM(BaseModel):
    """Extracción cruda de la escritura antes de normalización y verificación.

    Todos los campos son obligatorios. Cuando un dato no aparece en el documento,
    el LLM debe devolver {valor: null, cita: null, pagina: null, confianza: 0.0}.
    """

    @model_validator(mode="before")
    @classmethod
    def _normalizar_nulos(cls, data):
        # Claude a veces devuelve el campo entero como string "null" o lo omite
        # en vez de un objeto con valor=null. Lo mapeamos a un _CampoLLM vacío
        # para que Pydantic valide y el campo salga como "no encontrado".
        vacio = {"valor": None, "cita": None, "pagina": None, "confianza": 0.0}
        if isinstance(data, dict):
            for clave in _CAMPOS_ESCRITURA_LLM:
                v = data.get(clave)
                if v is None or (isinstance(v, str) and v.strip().lower() in ("null", "none", "")):
                    data[clave] = dict(vacio)
        return data

    propietario: _CampoLLM
    direccion: _CampoLLM
    entidad_federativa: _CampoLLM
    municipio: _CampoLLM
    superficie_terreno_m2: _CampoLLM
    clave_catastral: _CampoLLM
    numero_oficial: _CampoLLM
    fecha_emision: _CampoLLM
    autoridad_emisora: _CampoLLM
    numero_escritura: _CampoLLM
    volumen: _CampoLLM
    notario: _CampoLLM
    fecha_escritura: _CampoLLM
    tipo_acto: _CampoLLM
    folio_real: _CampoLLM
    inscripcion_rpp: _CampoLLM
    medidas_colindancias: _CampoLLM
    gravamenes: _CampoLLM
    regimen_propiedad: _CampoLLM
    copropiedad: _CampoLLM
    embargo_o_litigio: _CampoLLM
    usufructo: _CampoLLM


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
    """Busca la cita en cada página.

    - Cita corta (<=6 palabras): acepta si APARECE COMPLETA y textual en alguna página
      (necesario para datos como "300.00 m²" o "Notaría 101" que el matcher antes rechazaba).
    - Cita larga: basta con que las primeras 6 palabras aparezcan en alguna página; se
      queda con la página de ese primer match.

    Devuelve (num_pagina, cita_original_strip) o None si no encaja en ninguna página.
    """
    if not cita or not cita.strip():
        return None
    limpio = _limpia_para_match(cita)
    palabras = limpio.split()
    if not palabras:
        return None
    # Cita corta: debe aparecer literal y completa.
    if len(palabras) <= 6:
        if len(limpio) < 3:
            return None
        for p in paginas:
            if limpio in _limpia_para_match(p.texto):
                return (p.numero, cita.strip())
        return None
    # Cita larga: validamos por firma de 6 palabras iniciales.
    firma = " ".join(palabras[:6])
    firma_amplia = " ".join(palabras[: min(10, len(palabras))])
    for p in paginas:
        tx = _limpia_para_match(p.texto)
        if firma in tx or firma_amplia in tx:
            return (p.numero, cita.strip())
    return None


# ---------------------------------------------------------------- construcción de Campo

def _construir_campo(
    extraido: _CampoLLM,
    archivo: str,
    paginas: list[Pagina],
    normalizador: Optional[Callable[[Optional[str]], Optional[str]]] = None,
) -> Campo:
    """Convierte un _CampoLLM a Campo del contrato, verificando evidencia.

    Regla 4 del equipo: si la cita no se verifica, el campo queda SIN evidencia y
    SIN normalizado. Así `cruce.validar_cruzado` ignora el dato posiblemente inventado
    (ignora campos con `normalizado is None`). El valor literal se conserva solo
    para mostrarlo al revisor humano.
    """
    if not extraido.valor or not extraido.valor.strip():
        return Campo()

    match = _verificar_cita(extraido.cita, paginas)
    conf_cruda = max(0.0, min(1.0, float(extraido.confianza)))  # clip a [0,1]: el schema no lo valida

    if match is None:
        # Sin evidencia confirmada: el dato NO entra al cruce ni al dictamen cruzado.
        return Campo(
            valor=extraido.valor,
            normalizado=None,
            evidencia=None,
            confianza=round(max(0.0, conf_cruda - 0.4), 2),
        )

    pagina, cita = match
    normalizado = normalizador(extraido.valor) if normalizador else _upper_sin_acentos(extraido.valor)
    return Campo(
        valor=extraido.valor,
        normalizado=normalizado,
        evidencia=Evidencia(archivo=archivo, pagina=pagina, cita=cita),
        confianza=round(conf_cruda, 2),
    )


# ---------------------------------------------------------------- prompt

_PROMPT_SISTEMA = """Eres un extractor de datos de ESCRITURAS PÚBLICAS mexicanas para el equipo legal de Tiendas 3B.

Tu tarea: leer el texto transcrito de una escritura (viene de OCR, puede traer errores) y llenar un objeto estructurado con los datos del INMUEBLE OBJETO de la escritura.

REGLAS DURAS (si las rompes, el dictamen pierde confianza):
1. Solo extraes lo que aparece LITERAL en el texto. No infieres, no deduces, no completas.
2. Para cada campo devuelves SIEMPRE un objeto con las claves `valor`, `cita`, `pagina` y `confianza` (TODOS obligatorios).
3. Si un dato no aparece en el documento: `valor=null`, `cita=null`, `pagina=null`, `confianza=0.0`. NUNCA lo inventes ni lo omitas.
4. Si el dato aparece: `valor` tal cual (incluye unidades/puntuación), `cita` es texto EXACTO del documento (5-20 palabras, que un Ctrl+F encontraría), `pagina` es el número 1-indexado donde está la cita, `confianza` entre 0 y 1.
5. Si hay varias ocurrencias (p.ej. varios domicilios), eliges la que corresponde al INMUEBLE OBJETO, no al del vendedor, representante, notaría ni testigos.

CAMPOS (descripciones precisas):
- propietario: nombre completo del ADQUIRENTE / comprador / beneficiario (quien queda como titular tras la escritura). Si son varios copropietarios, pon el principal o "COPROPIEDAD: nombre1 Y nombre2".
- direccion: dirección completa del inmueble (calle, número, colonia, municipio, estado).
- entidad_federativa: Estado de la República del inmueble (ej. "Hidalgo", "Estado de México", "Ciudad de México"). Puede venir solo en el encabezado, sello o texto legal, no en la dirección; búscala en todo el documento.
- municipio: municipio o alcaldía del inmueble.
- superficie_terreno_m2: superficie del TERRENO en metros cuadrados (con la unidad tal como aparece).
- clave_catastral: clave catastral o cuenta predial del inmueble.
- numero_oficial: número oficial exterior asignado al inmueble.
- fecha_emision: fecha de otorgamiento de la escritura ante el notario.
- autoridad_emisora: notaría pública (número + entidad federativa).
- numero_escritura: número de instrumento público / escritura.
- volumen: volumen o libro donde consta el instrumento.
- notario: nombre completo del notario público.
- fecha_escritura: igual que fecha_emision cuando solo hay una fecha.
- tipo_acto: naturaleza del acto (compraventa, donación, aportación, dación en pago, permuta, adjudicación, fusión, lotificación, cesión de derechos, información de dominio, testamento, etc.).
- folio_real: folio real electrónico o número de inscripción detallado del Registro Público de la Propiedad.
- inscripcion_rpp: literal del párrafo de inscripción en el RPP (fecha + libro + sección + volumen) o null si no aparece. Es diferente del folio_real.
- medidas_colindancias: resumen corto de medidas y colindancias (NORTE/SUR/ORIENTE/PONIENTE con metros y colindantes).
- gravamenes: hipotecas, servidumbres u otras cargas sobre el inmueble. Si el documento dice "libre de gravámenes" o similar, copia ese texto.
- regimen_propiedad: tipo de propiedad: "privada", "ejidal", "comunal", "condominio" o similar según el documento. null si no se indica.
- copropiedad: si hay DOS O MÁS copropietarios, copia el texto donde se nombran y si hay o no poder unificado para representarlos. null si es un solo titular.
- embargo_o_litigio: menciones de embargo judicial, juicio pendiente, demanda, anotación preventiva o litigio sobre el inmueble. null si no se menciona.
- usufructo: existencia de usufructo (vitalicio o temporal) o nuda propiedad que limite el uso del inmueble. null si no se menciona.

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


_REGIMENES_NO_PRIVADOS = ("EJIDAL", "EJIDO", "COMUNAL", "COMUNIDAD AGRARIA")


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

    # ESC-04 clave catastral del inmueble (sin confundir con inscripción en RPP)
    if datos.clave_catastral.valor:
        h.append(_h("ESC-04", "La escritura declara la clave catastral del inmueble",
                    EstadoRegla.CUMPLE, Severidad.INFO,
                    f"Clave catastral: {datos.clave_catastral.valor}.",
                    (datos.clave_catastral.evidencia,)))
    else:
        h.append(_h("ESC-04", "La escritura declara la clave catastral del inmueble",
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    "No se extrajo la clave catastral del inmueble."))

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

    # ESC-06 gravámenes (hipotecas, servidumbres u otras cargas; embargo/litigio va en ESC-11).
    # Si el modelo cita algo pero no se pudo verificar en el texto (evidencia=None), no afirmamos
    # ni descartamos: NO_EVALUABLE. Solo con evidencia verificada subimos a NO_CUMPLE.
    gravamenes = datos.especificos.get("gravamenes")
    if gravamenes and gravamenes.valor and gravamenes.evidencia:
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
    elif gravamenes and gravamenes.valor:  # citado pero cita no verificada
        h.append(_h("ESC-06", "Gravámenes o limitaciones al dominio",
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    "El modelo mencionó gravámenes pero la cita no se encontró en el documento; requiere verificación manual."))
    else:
        h.append(_h("ESC-06", "Gravámenes o limitaciones al dominio",
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    "No se extrajo información explícita sobre gravámenes; verificar en el documento original."))

    # ESC-07 datos del notario y número de escritura
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
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    f"No se extrajo: {', '.join(faltan)}."))

    # ESC-08 inscripción en el Registro Público de la Propiedad (folio real o párrafo de inscripción)
    folio = datos.especificos.get("folio_real")
    inscripcion = datos.especificos.get("inscripcion_rpp")
    tiene_folio = bool(folio and folio.valor)
    tiene_inscripcion = bool(inscripcion and inscripcion.valor)
    if tiene_folio or tiene_inscripcion:
        evs = []
        if folio and folio.evidencia:
            evs.append(folio.evidencia)
        if inscripcion and inscripcion.evidencia:
            evs.append(inscripcion.evidencia)
        h.append(_h("ESC-08", "La escritura se encuentra inscrita en el Registro Público de la Propiedad",
                    EstadoRegla.CUMPLE, Severidad.INFO,
                    "Se encontró folio real o constancia de inscripción en el RPP.",
                    tuple(evs)))
    else:
        h.append(_h("ESC-08", "La escritura se encuentra inscrita en el Registro Público de la Propiedad",
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    "No se extrajo folio real ni constancia de inscripción en el RPP; requiere verificación."))

    # ESC-09 régimen de propiedad (privada vs ejidal/comunal).
    # Solo marcamos BLOQUEANTE si hay evidencia LITERAL de ejidal/comunal en el documento;
    # ausencia o cita no verificada va a NO_EVALUABLE con severidad INFO (es el default urbano).
    regimen = datos.especificos.get("regimen_propiedad")
    if regimen and regimen.normalizado and regimen.evidencia:
        es_no_privado = any(t in regimen.normalizado for t in _REGIMENES_NO_PRIVADOS)
        # "Dominio pleno" dentro del texto significa ejido ya desincorporado -> no bloqueante.
        texto = (regimen.valor or "").lower()
        dominio_pleno = "dominio pleno" in texto or "desincorporad" in texto
        if es_no_privado and not dominio_pleno:
            h.append(_h("ESC-09", "Régimen de propiedad del inmueble",
                        EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE,
                        f"Régimen detectado: {regimen.valor}. Tiendas 3B requiere propiedad privada; el régimen ejidal o comunal exige procedimiento de desincorporación previa.",
                        (regimen.evidencia,)))
        else:
            explic = f"Régimen: {regimen.valor}."
            if es_no_privado and dominio_pleno:
                explic += " El documento indica dominio pleno (ejido ya desincorporado)."
            h.append(_h("ESC-09", "Régimen de propiedad del inmueble",
                        EstadoRegla.CUMPLE, Severidad.INFO,
                        explic, (regimen.evidencia,)))
    else:
        h.append(_h("ESC-09", "Régimen de propiedad del inmueble",
                    EstadoRegla.NO_EVALUABLE, Severidad.INFO,
                    "No se extrajo mención explícita del régimen; las escrituras urbanas suelen ser propiedad privada por default."))

    # ESC-10 copropiedad con poder unificado. Si el modelo citó algo pero no se verifica,
    # no asumimos copropiedad: queda como NO_EVALUABLE (y la regla no aplica si es titular único).
    copropiedad = datos.especificos.get("copropiedad")
    if copropiedad and copropiedad.valor and copropiedad.evidencia:
        t_low = copropiedad.valor.lower()
        hay_poder = any(k in t_low for k in ("poder", "representante común", "apoderado"))
        if hay_poder:
            h.append(_h("ESC-10", "Copropiedad con poder de representación unificado",
                        EstadoRegla.CUMPLE, Severidad.INFO,
                        "Existe copropiedad pero se designa poder/representación unificada.",
                        (copropiedad.evidencia,)))
        else:
            h.append(_h("ESC-10", "Copropiedad con poder de representación unificado",
                        EstadoRegla.NO_CUMPLE, Severidad.REVISION,
                        f"Se detectó copropiedad sin evidencia de poder unificado: {copropiedad.valor}. Se requiere consentimiento de todos los copropietarios.",
                        (copropiedad.evidencia,)))
    # Sin valor o sin evidencia: titular único (regla no aplica, no se emite hallazgo).

    # ESC-11 embargo o litigio. Solo NO_CUMPLE con evidencia verificada; ausencia =
    # NO_EVALUABLE INFO (no afirmamos que no haya embargo sin leer todo el documento).
    embargo = datos.especificos.get("embargo_o_litigio")
    if embargo and embargo.valor and embargo.evidencia:
        h.append(_h("ESC-11", "Embargo, juicio o anotación preventiva sobre el inmueble",
                    EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE,
                    f"Se detectó embargo o litigio: {embargo.valor}. Impide la libre disposición del inmueble.",
                    (embargo.evidencia,)))
    elif embargo and embargo.valor:
        h.append(_h("ESC-11", "Embargo, juicio o anotación preventiva sobre el inmueble",
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    "El modelo mencionó embargo o litigio pero la cita no se verificó en el documento; requiere revisión manual."))
    else:
        h.append(_h("ESC-11", "Embargo, juicio o anotación preventiva sobre el inmueble",
                    EstadoRegla.NO_EVALUABLE, Severidad.INFO,
                    "No se detectó mención de embargo o litigio en las páginas analizadas; confirmar con el RPP al cierre."))

    # ESC-12 usufructo o limitación del dominio. Mismo tratamiento: NO_CUMPLE solo con evidencia.
    usufructo = datos.especificos.get("usufructo")
    if usufructo and usufructo.valor and usufructo.evidencia:
        h.append(_h("ESC-12", "Usufructo u otra limitación al dominio",
                    EstadoRegla.NO_CUMPLE, Severidad.REVISION,
                    f"Se detectó usufructo o limitación al dominio: {usufructo.valor}. El titular no tiene disposición plena.",
                    (usufructo.evidencia,)))
    elif usufructo and usufructo.valor:
        h.append(_h("ESC-12", "Usufructo u otra limitación al dominio",
                    EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                    "El modelo mencionó usufructo pero la cita no se verificó en el documento; requiere revisión manual."))
    else:
        h.append(_h("ESC-12", "Usufructo u otra limitación al dominio",
                    EstadoRegla.NO_EVALUABLE, Severidad.INFO,
                    "No se detectó mención de usufructo ni limitación al dominio en las páginas analizadas."))

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

def _extraer(doc: DocumentoLeido, paginas: list[Pagina]) -> _EscrituraLLM:
    """Llama al LLM con caché por hash de (modelo + prompt + schema + texto).

    Patrón del equipo (igual al de predial.py y uso_suelo.py). Si existe el JSON
    en `cache/analisis/escritura/<archivo>.<hash12>.json` lo lee y evita el gasto
    de API. El hash incluye el texto completo enviado, así cambiar el OCR o el
    prompt invalida el caché automáticamente.
    """
    texto = _formatear_paginas(paginas)
    firma = json.dumps(
        [LLM_MODEL, _PROMPT_SISTEMA, _EscrituraLLM.model_json_schema(), texto],
        ensure_ascii=False,
        sort_keys=True,
    )
    hash12 = hashlib.sha256(firma.encode("utf-8")).hexdigest()[:12]
    ruta = DIR_ANALISIS / f"{doc.archivo}.{hash12}.json"
    if ruta.exists():
        log.info("Caché HIT para %s (hash %s)", doc.archivo, hash12)
        return _EscrituraLLM.model_validate_json(ruta.read_text(encoding="utf-8"))

    log.info("Caché MISS para %s (hash %s); llamando LLM", doc.archivo, hash12)
    llm = get_llm(effort="low", max_tokens=4000).with_structured_output(
        _EscrituraLLM, method="json_schema"
    )
    extraido: _EscrituraLLM = llm.invoke(
        [SystemMessage(content=_PROMPT_SISTEMA), HumanMessage(content=texto)],
        config={"callbacks": get_callbacks()},
    )
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(extraido.model_dump_json(indent=2), encoding="utf-8")
    except Exception:
        log.exception("No se pudo escribir cache de respuesta para %s", doc.archivo)
    return extraido


def analizar(doc: DocumentoLeido, ctx: Contexto) -> DocumentoAnalizado:
    if doc.legibilidad == Legibilidad.ILEGIBLE or not doc.paginas:
        return _resultado_ilegible(doc)

    paginas_para_llm = _seleccionar_paginas(doc)
    extraido = _extraer(doc, paginas_para_llm)

    datos = DatosInmueble(
        propietario=_construir_campo(extraido.propietario, doc.archivo, doc.paginas, _normalizar_nombre),
        direccion=_construir_campo(extraido.direccion, doc.archivo, doc.paginas, _normalizar_direccion),
        entidad_federativa=_construir_campo(extraido.entidad_federativa, doc.archivo, doc.paginas, _upper_sin_acentos),
        municipio=_construir_campo(extraido.municipio, doc.archivo, doc.paginas, _upper_sin_acentos),
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
        "inscripcion_rpp": _construir_campo(extraido.inscripcion_rpp, doc.archivo, doc.paginas),
        "medidas_colindancias": _construir_campo(extraido.medidas_colindancias, doc.archivo, doc.paginas),
        "gravamenes": _construir_campo(extraido.gravamenes, doc.archivo, doc.paginas),
        "regimen_propiedad": _construir_campo(extraido.regimen_propiedad, doc.archivo, doc.paginas),
        "copropiedad": _construir_campo(extraido.copropiedad, doc.archivo, doc.paginas),
        "embargo_o_litigio": _construir_campo(extraido.embargo_o_litigio, doc.archivo, doc.paginas),
        "usufructo": _construir_campo(extraido.usufructo, doc.archivo, doc.paginas),
    }

    hallazgos = _aplicar_reglas(datos)

    # Confianza global del análisis: promedio de confianzas de los campos poblados.
    campos_comunes = [
        datos.propietario, datos.direccion, datos.entidad_federativa, datos.municipio,
        datos.superficie_terreno_m2, datos.clave_catastral, datos.numero_oficial,
        datos.fecha_emision, datos.autoridad_emisora,
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
