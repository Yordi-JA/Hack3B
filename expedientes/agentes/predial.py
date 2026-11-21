"""Agente Predial. Dueño: Julián.

Extrae del comprobante de impuesto predial (boleta, recibo, CFDI, certificado de no adeudo):
contribuyente, ubicación, clave catastral o cuenta predial, superficies, municipio, entidad,
ejercicio pagado, fechas, adeudos y uso registrado; y evalúa las reglas PRE-.

Diseño:
- Una sola llamada al LLM por documento (salida estructurada); todo lo demás es Python.
- Ningún dato pasa sin evidencia literal: la cita se recorta del texto del caché (no se confía en
  la que escribe el modelo). Si el valor no aparece en el documento, se descarta y se reporta en PRE-09.
- La confianza de cada campo se calcula: 0.9 si la cita del modelo se encontró y contiene el valor,
  0.7 si solo se encontró el valor; x0.85 si el documento es de legibilidad PARCIAL.
- La respuesta del modelo se guarda en `cache/analisis/predial/` (regla 5 de uso de la API):
  repetir una prueba no gasta créditos mientras no cambien el texto, el prompt o el modelo.

Reglas (las definitivas dependen de las guías oficiales del reto, decisión 5):
    PRE-01  Contribuyente identificado
    PRE-02  Predio identificado (clave catastral o cuenta predial)
    PRE-03  Fecha de pago identificada (el predial no tiene vigencia: solo se reporta la fecha)
    PRE-04  Adeudos o ejercicios pendientes
    PRE-05  Coherencia entre fecha de pago y sello de caja
    PRE-06  Superficie de terreno registrada (la usa la validación cruzada)
    PRE-07  El documento ampara un solo predio
    PRE-08  Uso registrado compatible (baldío, agropecuario, rústico o ejidal piden revisión)
    PRE-09  Datos descartados por no tener evidencia literal (informativo)
    PRE-10  Embargo o procedimiento administrativo de ejecución (rechazo directo)
    PRE-11  Construcción registrada (0 m² pide revisión)
    PRE-ILEG Documento ilegible: no se extrae nada
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from datetime import date
from typing import Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

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

MAX_PAGINAS_LLM = 8
DIR_ANALISIS = CACHE_DIR / "analisis" / "predial"
# Un adeudo de predial se puede regularizar antes de firmar: por defecto pide revisión, no descarta
# el expediente. Cambiar a BLOQUEANTE si las guías oficiales lo exigen.
SEVERIDAD_ADEUDO = Severidad.REVISION
# Criterio compartido por Juan Pablo: embargo o procedimiento de ejecución = rechazo directo;
# baldío / agropecuario / ejidal y construcción en 0 m² = revisión.
SEVERIDAD_EMBARGO = Severidad.BLOQUEANTE
SEVERIDAD_USO_RIESGO = Severidad.REVISION
SEVERIDAD_SIN_CONSTRUCCION = Severidad.REVISION
_EMBARGO = re.compile(r"EMBARG|EJECUCION|REQUERIMIENTO DE PAGO|CREDITO FISCAL")
# Uso registrado en catastro que no corresponde a un local comercial urbano construido.
_USOS_DE_RIESGO = [
    (r"EJID|COMUNAL", "Tierra ejidal o comunal: no puede venderse ni rentarse a largo plazo sin dominio pleno; "
                      "revisar el régimen de propiedad."),
    (r"AGRO|AGRIC|RUSTIC|FORESTAL|PECUARI", "Uso no urbano (rústico o agropecuario): confirmar que la licencia "
                                           "de uso de suelo autorice el uso comercial."),
    (r"BALDIO", "Registrado como baldío: confirmar contra la construcción actual y la licencia de uso de suelo."),
]
CONF_CITA, CONF_SOLO_VALOR, FACTOR_PARCIAL = 0.9, 0.7, 0.85


# ---------------------------------------------------------------- esquema que llena el LLM

class _Dato(BaseModel):
    valor: Optional[str] = Field(description="El dato tal como aparece en el documento; null si no aparece")
    cita: Optional[str] = Field(description="Fragmento copiado LITERAL del documento que contiene el dato (3 a 20 palabras)")
    pagina: Optional[int] = Field(description="Número de página [P#] donde está la cita")


class _PredialLLM(BaseModel):
    propietario: _Dato = Field(description="Propietario, contribuyente, poseedor o receptor a cuyo nombre está el predio")
    direccion: _Dato = Field(description="Ubicación del PREDIO (no el domicilio de la tesorería, del banco ni del receptor si es otro)")
    numero_oficial: _Dato = Field(description="Número exterior del predio dentro de su ubicación (ej. '28', 'S/N')")
    superficie_terreno_m2: _Dato = Field(description="Superficie de TERRENO en m²")
    superficie_construccion_m2: _Dato = Field(description="Superficie de construcción en m²")
    clave_catastral: _Dato = Field(description="Clave catastral del predio (suele tener 10 a 16 dígitos)")
    numero_cuenta: _Dato = Field(description="Número de cuenta predial o de predio cuando es distinto de la clave (ej. 'U-02946')")
    municipio: _Dato = Field(description="Municipio donde está el predio")
    entidad_federativa: _Dato = Field(description="Estado de la República (puede venir solo en el encabezado o en el sello)")
    autoridad_emisora: _Dato = Field(description="Quién expide el documento (ej. 'Tesorería Municipal de Tultepec')")
    fecha_pago: _Dato = Field(description="Fecha de pago o de facturación del recibo/CFDI; si no hay pago, fecha de emisión del documento")
    fecha_sello: _Dato = Field(description="Fecha que aparece en el sello de PAGADO o de caja, si existe")
    ejercicio_pagado: _Dato = Field(description="Año o periodo fiscal que cubre el pago (ej. '2025', 'ENE-DIC 2024', '2025-2025')")
    total_pagado: _Dato = Field(description="Importe total pagado")
    valor_catastral: _Dato = Field(description="Valor catastral del predio")
    uso_del_predio: _Dato = Field(description="Uso registrado del predio (ej. HABITACIONAL, BALDÍO URBANO, COMERCIAL)")
    folio: _Dato = Field(description="Folio del recibo, comprobante o CFDI")
    adeudos: _Dato = Field(
        description="Texto que mencione adeudos, ejercicios pendientes de pago o rezagos, o al contrario que NO "
        "presenta adeudo. null si el documento no dice nada al respecto"
    )
    embargo: _Dato = Field(
        description="Solo si el documento AFIRMA que este predio tiene embargo, procedimiento administrativo de "
        "ejecución, requerimiento de pago o crédito fiscal en cobro. null si no, y también si solo es una leyenda "
        "genérica (ej. 'el pago extemporáneo dará lugar al procedimiento administrativo de ejecución')"
    )
    otras_cuentas: _Dato = Field(
        description="Solo si el documento ampara MÁS DE UN predio: SOLO la otra clave o cuenta, copiada literal "
        "(ej. 'U-02946'), sin descripción. null si hay uno solo"
    )


_PROMPT = """Eres un extractor de datos de comprobantes de IMPUESTO PREDIAL mexicanos (boletas, recibos de \
tesorería, CFDI de pago, comprobantes bancarios, certificados de no adeudo) para el equipo legal de Tiendas 3B.

El texto viene de OCR y llega por página con marcadores [P1], [P2], ...

Reglas:
1. Extrae solo lo que aparece en el texto. No infieras, no completes, no corrijas.
2. `valor`: el dato como aparece. `cita`: fragmento copiado LITERAL que contiene el dato, de 3 a 20 \
palabras, tal que Ctrl+F lo encontraría. `pagina`: el número del marcador [P#].
3. Si un dato no aparece, devuelve valor, cita y pagina en null. Nunca inventes una cita.
4. Si hay varios recibos del MISMO predio (ej. boleta + comprobante bancario), usa el que tenga más datos \
del predio y el pago más reciente. Si hay predios DISTINTOS, extrae el principal y reporta el otro en `otras_cuentas`.
5. La ubicación del predio no es el domicilio de la tesorería, del banco ni de la notaría."""


# ---------------------------------------------------------------- texto y localización literal

def _plano(t: str) -> str:
    """Mayúsculas sin acentos conservando la longitud, para mapear posiciones al texto original."""
    out = []
    for c in t:
        base = unicodedata.normalize("NFKD", c)[:1] or c
        u = base.upper()
        out.append(u[0] if u else c)
    return "".join(out)


def _tokens(s: Optional[str]) -> list[str]:
    return re.findall(r"[A-Z0-9]+", _plano(s or ""))


def _norm(s: Optional[str]) -> str:
    return " ".join(_tokens(s))


def _localizar(fragmento: Optional[str], paginas: list[Pagina], preferida: Optional[int] = None):
    """Busca el fragmento en las páginas ignorando mayúsculas, acentos y puntuación.

    Devuelve (pagina, inicio, fin) sobre el texto ORIGINAL de esa página, o None.
    """
    toks = _tokens(fragmento)
    if not toks:
        return None
    patron = re.compile(r"(?<![A-Z0-9])" + r"[^A-Z0-9]+".join(map(re.escape, toks)) + r"(?![A-Z0-9])")
    orden = sorted(paginas, key=lambda p: p.numero != preferida)
    for p in orden:
        m = patron.search(_plano(p.texto))
        if m:
            return p.numero, m.start(), m.end()
    return None


def _contexto(texto: str, inicio: int, fin: int, antes: int = 45, despues: int = 25) -> str:
    """Recorta el texto alrededor de [inicio, fin) sin partir palabras ni cruzar saltos de línea."""
    a = max(0, inicio - antes)
    b = min(len(texto), fin + despues)
    salto = texto.rfind("\n", a, inicio)
    a = salto + 1 if salto != -1 else a
    salto = texto.find("\n", fin, b)
    b = salto if salto != -1 else b
    while a > 0 and a < inicio and not texto[a - 1].isspace():
        a += 1
    while b < len(texto) and b > fin and not texto[b].isspace():
        b -= 1
    return re.sub(r"\s+", " ", texto[a:b]).strip(" |,;")


def _evidenciar(dato: _Dato, paginas: list[Pagina], archivo: str) -> tuple[Optional[Evidencia], float]:
    """Evidencia literal del documento para el dato, y la confianza que le corresponde."""
    por_numero = {p.numero: p for p in paginas}
    valor = set(_tokens(dato.valor))
    loc = _localizar(dato.cita, paginas, dato.pagina)
    if loc and valor and valor <= set(_tokens(dato.cita)):
        n, i, f = loc
        return Evidencia(archivo=archivo, pagina=n, cita=por_numero[n].texto[i:f].strip()), CONF_CITA
    loc = _localizar(dato.valor, paginas, dato.pagina)
    if loc:
        n, i, f = loc
        return Evidencia(archivo=archivo, pagina=n, cita=_contexto(por_numero[n].texto, i, f)), CONF_SOLO_VALOR
    return None, 0.0


# ---------------------------------------------------------------- normalización

_SIN_DATO = {"", "S D", "SD", "N A", "NA", "NULL", "NINGUNO", "NO APLICA"}
_MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8,
    "SEP": 9, "SEPT": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}


def _texto(s: Optional[str]) -> Optional[str]:
    t = _norm(s)
    return None if t in _SIN_DATO else t


def _clave(s: Optional[str]) -> Optional[str]:
    """Solo dígitos; None si tiene menos de 8 (una cuenta como 'U-02946' no es clave catastral)."""
    d = re.sub(r"\D", "", s or "")
    return d if len(d) >= 8 else None


def _cuenta(s: Optional[str]) -> Optional[str]:
    t = _texto(s)
    return t.replace(" ", "") if t else None


def _numero(s: Optional[str]) -> Optional[float]:
    """'1,250.50' -> 1250.5; '245,00' -> 245.0; '$ 418,260.00' -> 418260.0"""
    m = re.search(r"\d[\d.,]*", s or "")
    if not m:
        return None
    n = m.group(0).rstrip(".,")
    if "," in n and "." in n:
        n = n.replace(",", "") if n.rfind(".") > n.rfind(",") else n.replace(".", "").replace(",", ".")
    elif "," in n:
        ent, _, dec = n.rpartition(",")
        n = f"{ent.replace(',', '')}.{dec}" if len(dec) != 3 else n.replace(",", "")
    try:
        return float(n)
    except ValueError:
        return None


def _superficie(s: Optional[str]) -> Optional[str]:
    """En m² con 2 decimales. 0 se trata como dato ausente: no sirve para la validación cruzada."""
    x = _numero(s)
    return f"{x:.2f}" if x else None


def _dinero(s: Optional[str]) -> Optional[str]:
    x = _numero(s)
    return f"{x:.2f}" if x is not None else None


def _fecha_iso(s: Optional[str]) -> Optional[str]:
    """ISO; acepta '26/01/2025', '09-01-2024', '2025-01-26', '16 ENE 2025', '28ENE25', '19 de febrero de 2025'."""
    if not s:
        return None

    def ok(y: int, mo: int, d: int) -> Optional[str]:
        try:
            return date(y + 2000 if y < 100 else y, mo, d).isoformat()
        except ValueError:
            return None

    if m := re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
        return ok(int(m[1]), int(m[2]), int(m[3]))
    if m := re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", s):
        return ok(int(m[3]), int(m[2]), int(m[1]))
    t = _plano(s)
    if m := re.search(r"(\d{1,2})\s*(?:DE\s+)?([A-Z]{3,10})\.?\s*(?:DE\s+|DEL\s+)?(\d{4}|\d{2})\b", t):
        if m[2] in _MESES:
            return ok(int(m[3]), _MESES[m[2]], int(m[1]))
    return None


def _anio_ejercicio(s: Optional[str]) -> Optional[str]:
    """Último año que cubre el ejercicio: '2025-2025' -> '2025'; 'ENE-DIC 2024' -> '2024'."""
    anios = [int(a) for a in re.findall(r"\b(19\d{2}|20\d{2})\b", s or "")]
    return str(max(anios)) if anios else None


_ENTIDADES = {
    "ESTADO DE MEXICO": "MEXICO", "EDO DE MEXICO": "MEXICO", "EDO MEX": "MEXICO", "EDOMEX": "MEXICO",
    "CDMX": "CIUDAD DE MEXICO", "DISTRITO FEDERAL": "CIUDAD DE MEXICO", "HGO": "HIDALGO",
}


def _entidad(s: Optional[str]) -> Optional[str]:
    t = _texto(s)
    if not t:
        return None
    t = _ENTIDADES.get(t, t)
    return re.sub(r"^(ESTADO|EDO) (LIBRE Y SOBERANO )?DE ", "", t) if t != "CIUDAD DE MEXICO" else t


def _municipio(s: Optional[str]) -> Optional[str]:
    t = _texto(s)
    return re.sub(r"^(H )?(AYUNTAMIENTO|MUNICIPIO|MPIO)( CONSTITUCIONAL)? DE ", "", t) if t else None


# ---------------------------------------------------------------- llamada al LLM (con caché en disco)

def _formatear(paginas: list[Pagina]) -> str:
    return "\n\n".join(f"[P{p.numero}]\n{p.texto}" for p in paginas)


def _extraer(doc: DocumentoLeido, paginas: list[Pagina]) -> _PredialLLM:
    texto = _formatear(paginas)
    firma = json.dumps([LLM_MODEL, _PROMPT, _PredialLLM.model_json_schema(), texto], ensure_ascii=False)
    ruta = DIR_ANALISIS / f"{doc.archivo}.{hashlib.sha256(firma.encode()).hexdigest()[:12]}.json"
    if ruta.exists():
        return _PredialLLM.model_validate_json(ruta.read_text(encoding="utf-8"))

    llm = get_llm(effort="low", max_tokens=4000).with_structured_output(_PredialLLM, method="json_schema")
    extraido = llm.invoke(
        [SystemMessage(content=_PROMPT), HumanMessage(content=texto)],
        config={"callbacks": get_callbacks()},
    )
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(extraido.model_dump_json(indent=2), encoding="utf-8")
    return extraido


# ---------------------------------------------------------------- reglas PRE-

def _h(id_regla: str, descripcion: str, estado: EstadoRegla, severidad: Severidad,
       explicacion: str, *campos: Campo) -> Hallazgo:
    return Hallazgo(
        id_regla=id_regla, descripcion=descripcion, estado=estado, severidad=severidad,
        explicacion=explicacion, evidencias=[c.evidencia for c in campos if c and c.evidencia],
    )


_SIN_ADEUDO = re.compile(r"\bNO (PRESENTA|TIENE|REGISTRA|CUENTA CON|EXISTE)( NINGUN)? ADEUDO|\bSIN ADEUDO|\bNO ADEUDO")
_CON_ADEUDO = re.compile(r"PENDIENTE|ADEUDO|REZAGO|\bDEBE\b|VENCID|OMIS")


def _reglas(d: DatosInmueble, ctx: Contexto, descartados: list[str]) -> list[Hallazgo]:
    E, S = EstadoRegla, Severidad
    esp = d.especificos
    vacio = Campo()
    h: list[Hallazgo] = []

    if d.propietario.valor:
        h.append(_h("PRE-01", "El predial identifica al contribuyente", E.CUMPLE, S.INFO,
                    f"Contribuyente: {d.propietario.valor}.", d.propietario))
    else:
        h.append(_h("PRE-01", "El predial identifica al contribuyente", E.NO_EVALUABLE, S.REVISION,
                    "No se encontró el nombre del propietario o contribuyente."))

    cuenta = esp.get("numero_cuenta", vacio)
    if d.clave_catastral.valor or cuenta.valor:
        ident = d.clave_catastral.valor or cuenta.valor
        h.append(_h("PRE-02", "El predio está identificado (clave catastral o cuenta predial)", E.CUMPLE, S.INFO,
                    f"Identificación del predio: {ident}.", d.clave_catastral, cuenta))
    else:
        # Dato ausente => NO_EVALUABLE (contrato): no encontrarlo no prueba que el predio no esté identificado.
        h.append(_h("PRE-02", "El predio está identificado (clave catastral o cuenta predial)", E.NO_EVALUABLE,
                    S.REVISION, "No se encontró clave catastral ni cuenta predial en el documento: no se puede "
                    "vincular con certeza al inmueble."))

    # Criterio de los organizadores: el predial NO tiene vigencia; solo se reporta su fecha y el
    # ejercicio que cubre. No se evalúa contra ctx.fecha_referencia.
    ejercicio = esp.get("ejercicio_pagado", vacio)
    fecha = esp.get("fecha_pago", vacio)
    if fecha.normalizado or ejercicio.normalizado:
        partes = [f"fecha de pago {fecha.valor}" if fecha.valor else None,
                  f"ejercicio {ejercicio.normalizado}" if ejercicio.normalizado else None]
        h.append(_h("PRE-03", "Fecha del pago de predial identificada", E.CUMPLE, S.INFO,
                    "Comprobante de predial con " + " y ".join(p for p in partes if p)
                    + ". El predial no tiene vigencia: se reporta su fecha.", fecha, ejercicio))
    else:
        h.append(_h("PRE-03", "Fecha del pago de predial identificada", E.NO_EVALUABLE, S.REVISION,
                    "No se encontró la fecha de pago ni el ejercicio que cubre el comprobante."))

    adeudos = esp.get("adeudos", vacio)
    texto_adeudo = _norm(adeudos.valor)
    if texto_adeudo and _SIN_ADEUDO.search(texto_adeudo):
        h.append(_h("PRE-04", "Sin adeudos de impuesto predial", E.CUMPLE, S.INFO,
                    f"El documento declara: \"{adeudos.valor}\".", adeudos))
    elif texto_adeudo and _CON_ADEUDO.search(texto_adeudo):
        h.append(_h("PRE-04", "Sin adeudos de impuesto predial", E.NO_CUMPLE, SEVERIDAD_ADEUDO,
                    f"El documento registra adeudos: \"{adeudos.valor}\". Deben regularizarse antes de "
                    "formalizar la operación.", adeudos))
    else:
        h.append(_h("PRE-04", "Sin adeudos de impuesto predial", E.NO_EVALUABLE, S.INFO,
                    "El documento no menciona adeudos ni constancia de no adeudo."))

    pago, sello = esp.get("fecha_pago", vacio), esp.get("fecha_sello", vacio)
    if pago.normalizado and sello.normalizado:
        if sello.normalizado < pago.normalizado:
            h.append(_h("PRE-05", "Coherencia entre fecha de pago y sello de caja", E.NO_CUMPLE, S.REVISION,
                        f"El sello de caja ({sello.valor}) es anterior a la fecha de pago ({pago.valor}): "
                        "un recibo no puede sellarse antes de pagarse. Verificar autenticidad.", pago, sello))
        else:
            h.append(_h("PRE-05", "Coherencia entre fecha de pago y sello de caja", E.CUMPLE, S.INFO,
                        f"Pago {pago.valor}, sello {sello.valor}.", pago, sello))

    if d.superficie_terreno_m2.normalizado:
        h.append(_h("PRE-06", "Superficie de terreno registrada", E.CUMPLE, S.INFO,
                    f"Superficie de terreno: {d.superficie_terreno_m2.normalizado} m².", d.superficie_terreno_m2))
    elif d.superficie_terreno_m2.valor:
        h.append(_h("PRE-06", "Superficie de terreno registrada", E.NO_CUMPLE, S.REVISION,
                    f"El predial registra una superficie de terreno de {d.superficie_terreno_m2.valor}: no "
                    "permite validarla contra la escritura. Solicitar actualización catastral.",
                    d.superficie_terreno_m2))
    else:
        h.append(_h("PRE-06", "Superficie de terreno registrada", E.NO_EVALUABLE, S.REVISION,
                    "El documento no muestra la superficie de terreno."))

    otras = esp.get("otras_cuentas", vacio)
    if otras.valor:
        h.append(_h("PRE-07", "El documento ampara un solo predio", E.NO_CUMPLE, S.REVISION,
                    f"El documento también se refiere a otro predio ({otras.valor}). Confirmar cuál corresponde "
                    "al inmueble del expediente.", otras))

    uso = esp.get("uso_del_predio", vacio)
    if uso.valor:
        riesgo = next((msg for patron, msg in _USOS_DE_RIESGO if re.search(patron, _norm(uso.valor))), None)
        if riesgo:
            h.append(_h("PRE-08", "Uso del predio registrado compatible con un local comercial", E.NO_CUMPLE,
                        SEVERIDAD_USO_RIESGO, f"Uso registrado en catastro: {uso.valor}. {riesgo}", uso))
        else:
            h.append(_h("PRE-08", "Uso del predio registrado compatible con un local comercial", E.CUMPLE, S.INFO,
                        f"Uso registrado en catastro: {uso.valor}.", uso))

    # Embargo o PAE: solo cuenta si el documento lo afirma del predio (campo `embargo`) o el texto de
    # adeudos lo menciona. No se busca en todo el texto: hay leyendas genéricas ("...procedimiento
    # administrativo de ejecución") que darían rechazos falsos.
    embargo = esp.get("embargo", vacio)
    if not embargo.valor and _EMBARGO.search(texto_adeudo):
        embargo = adeudos
    if embargo.valor:
        h.append(_h("PRE-10", "Sin embargo ni procedimiento administrativo de ejecución", E.NO_CUMPLE,
                    SEVERIDAD_EMBARGO, f"El predial indica embargo o ejecución fiscal: \"{embargo.valor}\". "
                    "El inmueble está sujeto a un crédito fiscal exigible.", embargo))

    construccion = esp.get("superficie_construccion_m2", vacio)
    if construccion.valor and _numero(construccion.valor) == 0:
        h.append(_h("PRE-11", "Construcción registrada en catastro", E.NO_CUMPLE, SEVERIDAD_SIN_CONSTRUCCION,
                    f"El predial registra {construccion.valor} m² de construcción: catastro lo tiene como terreno "
                    "sin construir. Si existe un local, la construcción no está dada de alta; si no, habría que "
                    "construir. Confirmar contra el inmueble y la licencia de uso de suelo.", construccion))
    elif construccion.normalizado:
        h.append(_h("PRE-11", "Construcción registrada en catastro", E.CUMPLE, S.INFO,
                    f"Construcción registrada: {construccion.normalizado} m².", construccion))

    if descartados:
        h.append(_h("PRE-09", "Datos sin evidencia literal", E.NO_EVALUABLE, S.INFO,
                    "Se descartaron datos que el modelo propuso pero no aparecen en el texto del documento: "
                    + ", ".join(descartados) + "."))
    return h


# ---------------------------------------------------------------- punto de entrada

def _ilegible(doc: DocumentoLeido) -> DocumentoAnalizado:
    return DocumentoAnalizado(
        archivo=doc.archivo, tipo=doc.tipo, confianza_tipo=doc.confianza_tipo, legibilidad=doc.legibilidad,
        datos=DatosInmueble(),
        hallazgos=[_h("PRE-ILEG", "Documento ilegible; no se extrae información", EstadoRegla.NO_EVALUABLE,
                      Severidad.REVISION, "La ingesta marcó el predial como ilegible. No se extrajeron datos para "
                      "no inventarlos; solicitar una copia legible.")],
        confianza=0.0,
    )


_NORMALIZADORES: dict[str, Callable[[Optional[str]], Optional[str]]] = {
    "propietario": _texto, "direccion": _texto, "numero_oficial": _texto,
    "superficie_terreno_m2": _superficie, "superficie_construccion_m2": _superficie,
    "clave_catastral": _clave, "numero_cuenta": _cuenta, "municipio": _municipio,
    "entidad_federativa": _entidad, "autoridad_emisora": _texto, "fecha_pago": _fecha_iso,
    "fecha_sello": _fecha_iso, "ejercicio_pagado": _anio_ejercicio, "total_pagado": _dinero,
    "valor_catastral": _dinero, "uso_del_predio": _texto, "folio": _texto, "adeudos": _texto, "embargo": _texto,
    "otras_cuentas": _texto,
}
_COMUNES = ("propietario", "direccion", "numero_oficial", "superficie_terreno_m2", "clave_catastral",
            "municipio", "entidad_federativa", "autoridad_emisora")
_IDENTIFICADORES = {"numero_cuenta", "otras_cuentas"}
_IDENTIFICADOR = re.compile(r"\b[A-Z]{0,3}[- ]?\d[\d -]{2,}\d\b", re.IGNORECASE)
_ESPECIFICOS = ("numero_cuenta", "folio", "ejercicio_pagado", "fecha_pago", "fecha_sello", "total_pagado",
                "valor_catastral", "uso_del_predio", "superficie_construccion_m2", "adeudos", "embargo",
                "otras_cuentas")


def analizar(doc: DocumentoLeido, ctx: Contexto) -> DocumentoAnalizado:
    paginas = [p for p in doc.paginas if p.texto.strip()][:MAX_PAGINAS_LLM]
    if doc.legibilidad == Legibilidad.ILEGIBLE or not paginas:
        return _ilegible(doc)

    extraido = _extraer(doc, paginas)
    factor = FACTOR_PARCIAL if doc.legibilidad == Legibilidad.PARCIAL else 1.0
    campos: dict[str, Campo] = {}
    descartados: list[str] = []
    for nombre in _COMUNES + _ESPECIFICOS:
        dato: _Dato = getattr(extraido, nombre)
        if nombre in _IDENTIFICADORES and dato.valor:
            # El modelo a veces agrega descripción ("U-02946 (RANGEL...), valor..."): solo el identificador.
            m = _IDENTIFICADOR.search(dato.valor)
            dato = dato.model_copy(update={"valor": m.group(0).strip() if m else dato.valor})
        if _texto(dato.valor) is None:
            campos[nombre] = Campo()
            continue
        evidencia, conf = _evidenciar(dato, paginas, doc.archivo)
        if evidencia is None:
            descartados.append(nombre)
            campos[nombre] = Campo()
            continue
        campos[nombre] = Campo(valor=dato.valor.strip(), normalizado=_NORMALIZADORES[nombre](dato.valor),
                               evidencia=evidencia, confianza=round(conf * factor, 2))

    datos = DatosInmueble(
        **{n: campos[n] for n in _COMUNES},
        fecha_emision=campos["fecha_pago"],
        vigencia_hasta=Campo(),  # el predial no tiene vigencia (criterio de los organizadores)
        especificos={n: campos[n] for n in _ESPECIFICOS if campos[n].valor},
    )
    poblados = [c.confianza for c in campos.values() if c.valor]
    confianza = round(sum(poblados) / len(poblados), 2) if poblados else 0.0
    return DocumentoAnalizado(
        archivo=doc.archivo, tipo=doc.tipo, confianza_tipo=doc.confianza_tipo, legibilidad=doc.legibilidad,
        datos=datos, hallazgos=_reglas(datos, ctx, descartados), confianza=confianza,
    )
