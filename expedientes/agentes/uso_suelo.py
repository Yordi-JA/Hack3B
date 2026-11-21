"""Agente Uso de Suelo. Dueño: Juan Pablo.

Extraer (CONTEXT.md): dirección e identificación, uso de suelo autorizado, compatibilidad con
el uso comercial requerido (`ctx.uso_requerido`), restricciones o condicionantes,
superficie aplicable, fecha de emisión y vigencia, autoridad emisora.

Claves de `datos.especificos`: uso_autorizado, clave_uso (ej. CU-100-B), giro_autorizado,
compatibilidad_comercial, superficie_maxima_giro_m2, cos, cus, niveles_maximos,
condicionantes, folio, periodo_administracion, vigencia_texto, area_libre, prohibicion_N,
derechos_adquiridos, zona_protegida.

Reglas: USO-01 compatibilidad, 02 vigencia, 03 coherencia de fechas, 04 condicionantes,
05 identificación del predio, 06 autoridad; y los criterios de Tiendas 3B: 07 superficie comercial
máxima (< 250 m² rechaza), 08 prohibición expresa de giro, 09 área libre > 40 %, 10 derechos
adquiridos y 11 zona de conservación o patrimonio (estas dos solo aparecen si aplican).

Llenar también `datos.entidad_federativa` y `datos.municipio` (la UI los usa para el mapa).
El estado muchas veces no viene en la dirección: buscarlo en todo el documento (encabezado de
la dependencia, sello, texto legal). `normalizado` en mayúsculas sin acentos: 'HIDALGO',
'MEXICO' (Estado de México), 'CIUDAD DE MEXICO'. No son campos cruzables (decide Diego).

Es el ejemplo que pone el reto: determinar si autoriza el uso comercial, qué condicionantes
tiene y citar la evidencia. Ojo con vigencias vencidas y con encabezados que no cuadran con
la fecha del folio (posible documento alterado).

Una sola llamada al LLM por documento (salida estructurada). Las reglas USO- se evalúan en
código sobre lo extraído, y toda cita del LLM se verifica contra el texto: si no aparece,
el dato se queda sin evidencia ni `normalizado` y no sustenta ningún CUMPLE.

La respuesta del modelo se guarda en `cache/analisis/uso_suelo/` (regla 5 de uso de la API):
la llave es un hash de modelo + prompt + esquema + texto, así que repetir una corrida o cambiar
las reglas no cuesta llamadas.

Prefijo de reglas: USO-.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

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

# Las licencias del set tienen 1-8 páginas; el tope solo protege contra un archivo mal clasificado.
MAX_PAGINAS_LLM = 12
# Una legibilidad PARCIAL no deja que la confianza del documento pase de aquí.
TOPE_CONFIANZA_PARCIAL = 0.6

# Criterios de Tiendas 3B (criterios_de_evaluacion_inmobiliaria, sección 1).
SUPERFICIE_MINIMA_TIENDA_M2 = 250.0  # debajo: rechazo directo
SUPERFICIE_HOLGADA_TIENDA_M2 = 300.0  # entre ambas: revisión
AREA_LIBRE_MAXIMA = 40.0             # % de área libre que todavía deja la huella de sala y bodega
DIR_ANALISIS = CACHE_DIR / "analisis" / "uso_suelo"

ENTIDADES = {
    "AGUASCALIENTES", "BAJA CALIFORNIA", "BAJA CALIFORNIA SUR", "CAMPECHE", "CHIAPAS",
    "CHIHUAHUA", "CIUDAD DE MEXICO", "COAHUILA", "COLIMA", "DURANGO", "GUANAJUATO",
    "GUERRERO", "HIDALGO", "JALISCO", "MEXICO", "MICHOACAN", "MORELOS", "NAYARIT",
    "NUEVO LEON", "OAXACA", "PUEBLA", "QUERETARO", "QUINTANA ROO", "SAN LUIS POTOSI",
    "SINALOA", "SONORA", "TABASCO", "TAMAULIPAS", "TLAXCALA", "VERACRUZ", "YUCATAN",
    "ZACATECAS",
}
ALIAS_ENTIDAD = {
    "ESTADO DE MEXICO": "MEXICO",
    "EDO DE MEXICO": "MEXICO",
    "EDOMEX": "MEXICO",
    "ESTADO LIBRE Y SOBERANO DE MEXICO": "MEXICO",
    "CDMX": "CIUDAD DE MEXICO",
    "DISTRITO FEDERAL": "CIUDAD DE MEXICO",
    "COAHUILA DE ZARAGOZA": "COAHUILA",
    "MICHOACAN DE OCAMPO": "MICHOACAN",
    "VERACRUZ DE IGNACIO DE LA LLAVE": "VERACRUZ",
}

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}


# ---------------------------------------------------------------- modelo interno LLM

def _todo_requerido(schema: dict) -> None:
    schema["required"] = list(schema.get("properties", {}))


class _SalidaLLM(BaseModel):
    """Base de lo que devuelve el modelo. En el esquema que ve la API todos los campos son
    obligatorios (los nulos se piden como null): la API acepta máximo 24 opcionales. Los valores
    por defecto solo sirven para construir objetos en código y en pruebas."""
    model_config = ConfigDict(json_schema_extra=_todo_requerido)


class _CampoLLM(_SalidaLLM):
    valor: Optional[str] = Field(default=None, description="Dato tal como aparece en el documento")
    cita: Optional[str] = Field(default=None, description="Texto literal del documento que contiene el dato")
    pagina: Optional[int] = Field(default=None, description="Página [Pn] donde está la cita")
    # Sin ge/le: el json_schema estricto no acepta límites numéricos; se acota en _campo.
    confianza: float = Field(default=0.0, description="0 a 1")


class _FechaLLM(_CampoLLM):
    iso: Optional[str] = Field(
        default=None,
        description="La misma fecha en formato AAAA-MM-DD, aunque el documento la escriba con letra",
    )


class _Compatibilidad(str, Enum):
    COMPATIBLE = "compatible"          # autoriza expresamente comercio/abarrotes/minisúper
    CONDICIONADO = "condicionado"      # lo permite sujeto a condiciones o a otro trámite
    INCOMPATIBLE = "incompatible"      # autoriza otro uso o prohíbe el comercio requerido
    NO_DETERMINABLE = "no_determinable"


class _UsoSueloLLM(_SalidaLLM):
    """Extracción cruda de la licencia antes de normalizar y verificar citas."""

    propietario: _CampoLLM = Field(default_factory=_CampoLLM)
    direccion: _CampoLLM = Field(default_factory=_CampoLLM)
    entidad_federativa: _CampoLLM = Field(default_factory=_CampoLLM)
    municipio: _CampoLLM = Field(default_factory=_CampoLLM)
    superficie_terreno_m2: _CampoLLM = Field(default_factory=_CampoLLM)
    clave_catastral: _CampoLLM = Field(default_factory=_CampoLLM)
    numero_oficial: _CampoLLM = Field(default_factory=_CampoLLM)
    fecha_emision: _FechaLLM = Field(default_factory=_FechaLLM)
    vigencia_hasta: _FechaLLM = Field(default_factory=_FechaLLM)
    vigencia_texto: _CampoLLM = Field(default_factory=_CampoLLM)
    autoridad_emisora: _CampoLLM = Field(default_factory=_CampoLLM)
    folio: _CampoLLM = Field(default_factory=_CampoLLM)
    periodo_administracion: _CampoLLM = Field(default_factory=_CampoLLM)
    uso_autorizado: _CampoLLM = Field(default_factory=_CampoLLM)
    clave_uso: _CampoLLM = Field(default_factory=_CampoLLM)
    giro_autorizado: _CampoLLM = Field(default_factory=_CampoLLM)
    superficie_maxima_giro_m2: _CampoLLM = Field(default_factory=_CampoLLM)
    cos: _CampoLLM = Field(default_factory=_CampoLLM)
    cus: _CampoLLM = Field(default_factory=_CampoLLM)
    niveles_maximos: _CampoLLM = Field(default_factory=_CampoLLM)
    condicionantes: list[_CampoLLM] = Field(default_factory=list)
    area_libre: _CampoLLM = Field(default_factory=_CampoLLM)
    prohibiciones_giro: list[_CampoLLM] = Field(default_factory=list)
    derechos_adquiridos: _CampoLLM = Field(default_factory=_CampoLLM)
    zona_protegida: _CampoLLM = Field(default_factory=_CampoLLM)
    compatibilidad_comercial: _Compatibilidad = _Compatibilidad.NO_DETERMINABLE
    compatibilidad_justificacion: Optional[str] = Field(
        default=None, description="Por qué, en una o dos frases para el equipo legal")
    compatibilidad_cita: Optional[str] = Field(
        default=None, description="Texto literal que sustenta la compatibilidad")
    compatibilidad_pagina: Optional[int] = None


# ---------------------------------------------------------------- normalizadores
# Los de nombre, dirección, superficie, clave y número replican los de escritura.py para que
# `cruce` compare formas idénticas. PENDIENTE: moverlos a un módulo común en main.

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
    tokens = re.sub(r"\s+", " ", base).strip().split()
    if not tokens:
        return None
    if len(tokens) == 1:
        return tokens[0]
    if len(tokens) == 2:
        return f"{tokens[1]} {tokens[0]}"
    return " ".join(tokens[-2:] + tokens[:-2])


def _normalizar_direccion(s: Optional[str]) -> Optional[str]:
    base = _upper_sin_acentos(s)
    if not base:
        return None
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
    limpio = s.replace(" ", "")
    if re.match(r"^\d{1,3}(,\d{3})+(\.\d+)?", limpio):
        limpio = limpio.replace(",", "")
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
    return re.sub(r"[^0-9A-Z]", "", s.upper()) or None


def _normalizar_numero(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    m = re.search(r"\d+", s)
    return m.group(0) if m else None


def _normalizar_entidad(s: Optional[str]) -> Optional[str]:
    """'Estado de México' -> 'MEXICO', 'Hgo.' no se adivina: solo nombres y alias conocidos."""
    base = _upper_sin_acentos(s)
    if not base:
        return None
    base = re.sub(r"[^A-Z ]", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    if base in ALIAS_ENTIDAD:
        return ALIAS_ENTIDAD[base]
    if base in ENTIDADES:
        return base
    base = re.sub(r"^(ESTADO LIBRE Y SOBERANO DE|ESTADO DE|EDO DE)\s+", "", base)
    if base in ALIAS_ENTIDAD:
        return ALIAS_ENTIDAD[base]
    return base if base in ENTIDADES else None


def _normalizar_municipio(s: Optional[str]) -> Optional[str]:
    base = _upper_sin_acentos(s)
    if not base:
        return None
    base = re.sub(r"^(H\.?\s*AYUNTAMIENTO( CONSTITUCIONAL)? DE|MUNICIPIO DE|ALCALDIA)\s+", "", base)
    base = re.sub(r"[.,]", "", base).strip()
    return base or None


def _fecha_iso(valor: Optional[str], iso_llm: Optional[str]) -> Optional[str]:
    """ISO AAAA-MM-DD. Primero se parsea el valor; si viene con letra, se usa el iso del LLM."""
    if valor:
        low = valor.lower().strip()
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", low)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            return _iso_valida(y, mo, d)
        m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", low)
        if m:
            d, mo, y = (int(x) for x in m.groups())
            return _iso_valida(y, mo, d)
        m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de|del)\s+(\d{4})", low)
        if m:
            mo = MESES_ES.get((_upper_sin_acentos(m.group(2)) or "").lower())
            if mo:
                return _iso_valida(int(m.group(3)), mo, int(m.group(1)))
    if iso_llm:
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso_llm.strip())
        if m:
            return _iso_valida(*(int(x) for x in m.groups()))
    return None


def _iso_valida(y: int, mo: int, d: int) -> Optional[str]:
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


# ---------------------------------------------------------------- verificación de cita

def _limpia(s: str) -> str:
    base = _upper_sin_acentos(s) or ""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]", " ", base)).strip()


# Respaldo por valor: solo para valores que no aparecen por casualidad (no '12' ni '2025').
MIN_CARACTERES_VALOR_DISTINTIVO = 6
CONF_SOLO_VALOR = 0.6
VENTANA_VALOR = 40  # caracteres después de la cita donde puede caer el valor (el OCR corta el final)


def _buscar(fragmento: str, texto: str) -> int:
    """Posición de `fragmento` en `texto` (ambos ya limpios) respetando palabras completas, o -1.
    'NOTARIA 10' no calza dentro de 'NOTARIA 101'."""
    # Los dos espacios agregados se compensan: el índice sale sobre `texto`.
    return f" {texto} ".find(f" {fragmento} ")


def _verificar_cita(cita: Optional[str], pagina_llm: Optional[int], paginas: list[Pagina],
                    valor: Optional[str] = None) -> Optional[int]:
    """Página donde aparece la cita, o None. Se prueba primero la página que dijo el LLM.

    Cita corta (encabezados como 'ESTADO DE MÉXICO'): tiene que aparecer completa.
    Cita larga: basta con las primeras 6 palabras, porque el OCR suele romper el final.
    Con `valor`, además cada palabra del valor tiene que estar en la cita y en el texto junto a
    ella: una cita real con un valor inventado al final ('...SUPERFICIE TOTAL DE 999.00 M2') no
    pasa. No se exige que vayan seguidas: el modelo resume ('Notaría 101' de 'NOTARÍA PÚBLICA
    NÚMERO 101').
    """
    if not cita:
        return None
    limpia = _limpia(cita)
    palabras = limpia.split()
    if not palabras or len(limpia) < 3:
        return None
    firma = limpia if len(palabras) <= 6 else " ".join(palabras[:6])
    v = set(_limpia(valor).split()) if valor else set()
    if not v <= set(palabras):
        return None
    for p in sorted(paginas, key=lambda p: p.numero != pagina_llm):
        tx = _limpia(p.texto)
        i = _buscar(firma, tx)
        if i < 0:
            continue
        ventana = tx[i:i + len(limpia) + VENTANA_VALOR].split()[:len(palabras) + 3]
        if v <= set(ventana):
            return p.numero
    return None


def _plano(t: str) -> str:
    """Mayúsculas sin acentos con la MISMA longitud que `t`, para recortar el texto original."""
    return "".join((unicodedata.normalize("NFKD", c)[:1] or c).upper()[:1] or c for c in t)


def _localizar_valor(valor: str, pagina_llm: Optional[int], paginas: list[Pagina]) -> Optional[tuple[int, str]]:
    """Respaldo cuando la cita no calza (tablas que el modelo junta o corta): busca el valor solo,
    si es distintivo. Devuelve (página, fragmento literal alrededor del valor) como evidencia."""
    v = _limpia(valor)
    if len(v) < MIN_CARACTERES_VALOR_DISTINTIVO or len(v.split()) < 2 and not re.search(r"[A-Z]", v):
        return None  # corto, o un solo número: aparecería en fechas, folios o importes
    patron = re.compile(r"(?<![A-Z0-9])" + r"[^A-Z0-9]+".join(map(re.escape, v.split())) + r"(?![A-Z0-9])")
    for p in sorted(paginas, key=lambda p: p.numero != pagina_llm):
        m = patron.search(_plano(p.texto))
        if m:
            return p.numero, _recorte(p.texto, m.start(), m.end())
    return None


def _recorte(texto: str, inicio: int, fin: int, antes: int = 60, despues: int = 30) -> str:
    """Fragmento alrededor de [inicio, fin) sin salirse de la línea ni partir palabras."""
    linea_ini = texto.rfind("\n", 0, inicio) + 1
    linea_fin = texto.find("\n", fin)
    linea_fin = len(texto) if linea_fin < 0 else linea_fin
    a, b = max(linea_ini, inicio - antes), min(linea_fin, fin + despues)
    while linea_ini < a < inicio and not texto[a - 1].isspace():
        a += 1
    while fin < b < linea_fin and not texto[b].isspace():
        b -= 1
    return re.sub(r"\s+", " ", texto[a:b]).strip(" |")


def _campo(extraido: _CampoLLM, archivo: str, paginas: list[Pagina],
           normalizador: Callable[[Optional[str]], Optional[str]] = _upper_sin_acentos,
           normalizado: Optional[str] = None, exigir_valor: bool = True) -> Campo:
    """_CampoLLM -> Campo del contrato. Sin evidencia verificable no hay evidencia ni `normalizado`.

    `exigir_valor=False` para texto libre (condicionantes) que el modelo resume con sus palabras:
    ahí basta con que la cita exista.
    """
    if not extraido.valor or not extraido.valor.strip():
        return Campo()
    confianza = min(max(extraido.confianza, 0.0), 1.0)
    valor = extraido.valor if exigir_valor else None
    pagina = _verificar_cita(extraido.cita, extraido.pagina, paginas, valor)
    cita = extraido.cita.strip() if pagina else None
    if pagina is None:  # también en texto libre: el valor completo es una frase del documento
        encontrado = _localizar_valor(extraido.valor, extraido.pagina, paginas)
        if encontrado:
            pagina, cita = encontrado
            confianza = min(confianza, CONF_SOLO_VALOR)
    if pagina is None:
        return Campo(valor=extraido.valor, confianza=round(min(confianza, 0.3), 2))
    return Campo(
        valor=extraido.valor,
        normalizado=normalizado if normalizado is not None else normalizador(extraido.valor),
        evidencia=Evidencia(archivo=archivo, pagina=pagina, cita=cita),
        confianza=round(confianza, 2),
    )


def _campo_fecha(extraido: _FechaLLM, archivo: str, paginas: list[Pagina]) -> Campo:
    campo = _campo(extraido, archivo, paginas, normalizado=_fecha_iso(extraido.valor, extraido.iso))
    if campo.evidencia and campo.normalizado is None:
        campo.confianza = round(campo.confianza * 0.5, 2)
    return campo


# ---------------------------------------------------------------- prompt

_PROMPT_SISTEMA = """Eres un extractor de datos de LICENCIAS / CONSTANCIAS DE USO DE SUELO mexicanas para el equipo legal de Tiendas 3B.

Recibes el texto transcrito (OCR, puede traer errores) de un documento. Cada página empieza con un marcador [P1], [P2], ...

USO QUE TIENDAS 3B NECESITA: {uso_requerido}

REGLAS DURAS:
1. Solo extraes lo que aparece en el texto. No infieres ni completas datos.
2. Para cada dato: `valor` (como aparece), `cita` (texto COPIADO tal cual del documento que contiene el dato, de 2 a 25 palabras), `pagina` (número del marcador [Pn]) y `confianza` (0 a 1).
3. Si un dato no aparece, deja valor=null, cita=null, confianza=0. NUNCA inventes una cita: se verifica con búsqueda literal y una cita que no exista invalida el dato.
4. Los datos son del PREDIO objeto de la licencia, no del domicilio de la dependencia que aparece en el pie de página.

CAMPOS:
- propietario: titular o solicitante a favor de quien se expide.
- direccion: ubicación del predio (calle, número, colonia).
- entidad_federativa: el estado de la República. Casi nunca viene en la dirección: búscalo en TODO el documento (encabezado del gobierno o la dependencia, sellos, fundamento legal, lugar y fecha). Ej. "Tultepec, Estado de México" -> valor "Estado de México". Ojo: "Plaza Hidalgo", "Calle Morelos" o "Av. Juárez" son calles, no estados.
- municipio: municipio o alcaldía donde está el predio.
- superficie_terreno_m2: superficie total del predio, con unidad.
- clave_catastral, numero_oficial.
- fecha_emision: fecha de expedición. vigencia_hasta: fecha en que deja de valer. Si la fecha viene con letra ("veintiocho de noviembre del dos mil veintitrés") pon ese texto en `valor` y la fecha en `iso` como AAAA-MM-DD. Si la vigencia es un plazo ("un año", "12 meses") y no una fecha, calcula `iso` a partir de la fecha de expedición.
- vigencia_texto: la frase completa de vigencia (incluye cláusulas como "o hasta en tanto no se modifique el Plan").
- autoridad_emisora: dependencia que expide (ej. "Dirección de Desarrollo Urbano del Municipio de ...").
- folio: número de licencia, expediente o folio.
- periodo_administracion: periodo de gobierno del encabezado o sello (ej. "2022-2024").
- uso_autorizado: uso de suelo que se autoriza o uso general del predio.
- clave_uso: clave de zonificación (ej. "CU-100-B", "H-200-A").
- giro_autorizado: giro o actividad específica autorizada, si la hay.
- superficie_maxima_giro_m2: superficie máxima permitida para el giro, si la indica.
- cos, cus, niveles_maximos: coeficientes de ocupación y utilización, altura o niveles.
- condicionantes: una entrada por cada restricción u obligación relevante (no autoriza construcción, requiere otro dictamen, cajones de estacionamiento, horario, etc.). Máximo 8.
- area_libre: porcentaje de área o superficie libre de construcción que exige (ej. "20% LA SUPERFICIE DEL LOTE").
- prohibiciones_giro: SOLO prohibiciones o limitantes expresas que afecten a una tienda: autoservicio, minisúper, venta de bebidas alcohólicas en envase cerrado, almacenamiento, carga o descarga de mercancías. Una entrada por prohibición; [] si no hay.
- derechos_adquiridos: si la licencia se otorga o se reconoce con base en "derechos adquiridos", la frase que lo dice; null si no.
- zona_protegida: si el PREDIO está en zona de conservación, centro histórico, zona de monumentos o patrimonio (INAH, INBAL) o área natural protegida, la frase que lo dice. Las normas generales de imagen urbana para "zonas patrimoniales" que no digan que el predio está en una de ellas NO cuentan: null.

COMPATIBILIDAD con el uso requerido:
- compatible: el documento autoriza o permite expresamente comercio de productos básicos, abarrotes, tienda de autoservicio o minisúper (o un uso comercial general que los incluya).
- condicionado: lo permite pero sujeto a otro trámite, dictamen o condición expresa.
- incompatible: autoriza otro uso (ej. zonificación habitacional pura H como "H 2/20" sin comercio en planta baja) o prohíbe el comercio.
- no_determinable: el texto no permite decidirlo.
Llena compatibilidad_justificacion, compatibilidad_cita y compatibilidad_pagina con el texto literal que lo sustenta.
"""


def _formatear_paginas(paginas: list[Pagina]) -> str:
    return "\n\n".join(f"[P{p.numero}]\n{p.texto}" for p in paginas)


def _paginas_de_otro_tipo(notas: Optional[str]) -> set[int]:
    """Lee 'Contiene páginas de tipo predial: p4, p6-p7.' de las notas de la ingesta."""
    paginas: set[int] = set()
    for rangos in re.findall(r"Contiene páginas de tipo \w+: ([p\d, -]+)", notas or ""):
        for a, b in re.findall(r"p(\d+)(?:-p(\d+))?", rangos):
            paginas.update(range(int(a), int(b or a) + 1))
    return paginas


def _paginas_con_texto(doc: DocumentoLeido) -> list[Pagina]:
    """Páginas que van al modelo: sin las vacías (borrosas o ilegibles, la ingesta descarta su
    texto) ni las de otro tipo anexas (ej. el predial dentro de una licencia)."""
    otras = _paginas_de_otro_tipo(doc.notas)
    return [p for p in doc.paginas if p.texto.strip() and p.numero not in otras][:MAX_PAGINAS_LLM]


def construir_mensajes(doc: DocumentoLeido, ctx: Contexto) -> list:
    """Mensajes que se mandan al LLM. Público para revisar el prompt sin gastar API."""
    paginas = _paginas_con_texto(doc)
    return [
        SystemMessage(content=_PROMPT_SISTEMA.format(uso_requerido=ctx.uso_requerido)),
        HumanMessage(content=_formatear_paginas(paginas)),
    ]


def _ruta_analisis(doc: DocumentoLeido, mensajes: list) -> Path:
    firma = json.dumps([LLM_MODEL, [m.content for m in mensajes], _UsoSueloLLM.model_json_schema()],
                       ensure_ascii=False)
    return DIR_ANALISIS / f"{doc.archivo}.{hashlib.sha256(firma.encode()).hexdigest()[:12]}.json"


def _extraer(doc: DocumentoLeido, ctx: Contexto) -> _UsoSueloLLM:
    mensajes = construir_mensajes(doc, ctx)
    ruta = _ruta_analisis(doc, mensajes)
    if ruta.exists():
        return _UsoSueloLLM.model_validate_json(ruta.read_text(encoding="utf-8"))

    llm = get_llm(effort="low", max_tokens=4000).with_structured_output(_UsoSueloLLM, method="json_schema")
    extraido = llm.invoke(mensajes, config={"callbacks": get_callbacks()})
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(extraido.model_dump_json(indent=2), encoding="utf-8")
    return extraido


# ---------------------------------------------------------------- reglas USO-

def _h(id_regla: str, descripcion: str, estado: EstadoRegla, severidad: Severidad,
       explicacion: str, *evidencias: Optional[Evidencia]) -> Hallazgo:
    return Hallazgo(id_regla=id_regla, descripcion=descripcion, estado=estado,
                    severidad=severidad, explicacion=explicacion,
                    evidencias=[e for e in evidencias if e is not None])


def _fmt(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def _anios(texto: Optional[str]) -> list[int]:
    return [int(a) for a in re.findall(r"\b(19[5-9]\d|20\d\d)\b", texto or "")]


def _regla_compatibilidad(ex: _UsoSueloLLM, datos: DatosInmueble, ctx: Contexto,
                          archivo: str, paginas: list[Pagina]) -> Hallazgo:
    desc = "Autoriza el uso comercial requerido"
    pagina = _verificar_cita(ex.compatibilidad_cita, ex.compatibilidad_pagina, paginas)
    ev = Evidencia(archivo=archivo, pagina=pagina, cita=ex.compatibilidad_cita.strip()) if pagina else None
    if ev is None:
        uso = datos.especificos.get("uso_autorizado")
        ev = uso.evidencia if uso else None
    motivo = ex.compatibilidad_justificacion or ""

    if ex.compatibilidad_comercial == _Compatibilidad.NO_DETERMINABLE or ev is None:
        return _h("USO-01", desc, EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                  f"No se pudo determinar con evidencia si autoriza {ctx.uso_requerido}. {motivo}".strip(), ev)
    if ex.compatibilidad_comercial == _Compatibilidad.COMPATIBLE:
        return _h("USO-01", desc, EstadoRegla.CUMPLE, Severidad.INFO,
                  f"Compatible con {ctx.uso_requerido}. {motivo}".strip(), ev)
    if ex.compatibilidad_comercial == _Compatibilidad.CONDICIONADO:
        return _h("USO-01", desc, EstadoRegla.CUMPLE, Severidad.REVISION,
                  f"Lo permite con condiciones que el equipo legal debe confirmar. {motivo}".strip(), ev)
    return _h("USO-01", desc, EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE,
              f"No autoriza {ctx.uso_requerido}. {motivo}".strip(), ev)


def _regla_vigencia(datos: DatosInmueble, ctx: Contexto) -> Hallazgo:
    desc = "Licencia vigente a la fecha de referencia"
    vig = datos.vigencia_hasta
    texto = datos.especificos.get("vigencia_texto")
    ev_texto = texto.evidencia if texto else None
    if not vig.normalizado:
        detalle = f" El documento dice: «{texto.valor}»." if texto and texto.valor else ""
        return _h("USO-02", desc, EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                  f"No se encontró una fecha de vencimiento verificable.{detalle}", ev_texto)
    hasta = date.fromisoformat(vig.normalizado)
    if hasta < ctx.fecha_referencia:
        return _h("USO-02", desc, EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE,
                  f"La licencia venció el {_fmt(vig.normalizado)}, antes de la fecha de referencia "
                  f"({ctx.fecha_referencia:%d/%m/%Y}). Hay que tramitar una nueva o su refrendo.",
                  vig.evidencia)
    return _h("USO-02", desc, EstadoRegla.CUMPLE, Severidad.INFO,
              f"Vigente hasta el {_fmt(vig.normalizado)}.", vig.evidencia)


def _regla_coherencia_fechas(datos: DatosInmueble, ctx: Contexto) -> Hallazgo:
    """Fechas que no cuadran entre sí: posible documento alterado o mal capturado."""
    desc = "Fechas coherentes (expedición, vigencia, folio y periodo de gobierno)"
    emi = datos.fecha_emision
    if not emi.normalizado:
        return _h("USO-03", desc, EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                  "No se encontró una fecha de expedición verificable.")
    f_emi = date.fromisoformat(emi.normalizado)
    problemas: list[str] = []
    evs: list[Optional[Evidencia]] = [emi.evidencia]

    if f_emi > ctx.fecha_referencia:
        problemas.append(f"la fecha de expedición ({_fmt(emi.normalizado)}) es posterior a la fecha de referencia")
    vig = datos.vigencia_hasta
    if vig.normalizado and date.fromisoformat(vig.normalizado) < f_emi:
        problemas.append("la vigencia termina antes de la fecha de expedición")
        evs.append(vig.evidencia)
    periodo = datos.especificos.get("periodo_administracion")
    anios_periodo = _anios(periodo.normalizado if periodo else None)
    if len(anios_periodo) >= 2 and not (min(anios_periodo) <= f_emi.year <= max(anios_periodo)):
        problemas.append(f"se expidió en {f_emi.year}, fuera del periodo de gobierno «{periodo.valor}» del encabezado")
        evs.append(periodo.evidencia)
    folio = datos.especificos.get("folio")
    anios_folio = _anios(folio.normalizado if folio else None)
    if anios_folio and f_emi.year not in anios_folio:
        problemas.append(f"el folio «{folio.valor}» corresponde a otro año que la expedición ({f_emi.year})")
        evs.append(folio.evidencia)

    if problemas:
        return _h("USO-03", desc, EstadoRegla.NO_CUMPLE, Severidad.REVISION,
                  "Posible documento alterado o mal capturado: " + "; ".join(problemas) + ".", *evs)
    return _h("USO-03", desc, EstadoRegla.CUMPLE, Severidad.INFO,
              f"Expedida el {_fmt(emi.normalizado)}; no hay contradicciones entre fechas.", *evs)


def _regla_condicionantes(datos: DatosInmueble) -> Hallazgo:
    desc = "Restricciones y condicionantes de la licencia"
    conds = [c for k, c in datos.especificos.items() if k.startswith("condicionante_") and c.evidencia]
    if not conds:
        return _h("USO-04", desc, EstadoRegla.CUMPLE, Severidad.INFO,
                  "No se identificaron condicionantes con evidencia en el documento.")
    lista = "; ".join(c.valor for c in conds)
    return _h("USO-04", desc, EstadoRegla.CUMPLE, Severidad.INFO,
              f"Condicionantes a considerar en la operación: {lista}.", *(c.evidencia for c in conds))


def _regla_identificacion(datos: DatosInmueble) -> Hallazgo:
    desc = "Identifica el predio (dirección o clave catastral)"
    if datos.direccion.evidencia or datos.clave_catastral.evidencia:
        partes = [x for x in (datos.direccion.valor if datos.direccion.evidencia else None,
                              f"clave catastral {datos.clave_catastral.valor}" if datos.clave_catastral.evidencia else None) if x]
        return _h("USO-05", desc, EstadoRegla.CUMPLE, Severidad.INFO,
                  "Predio identificado: " + ", ".join(partes) + ".",
                  datos.direccion.evidencia, datos.clave_catastral.evidencia)
    return _h("USO-05", desc, EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
              "No se encontró con evidencia la dirección ni la clave catastral del predio; "
              "no se puede ligar la licencia al resto del expediente.")


def _regla_autoridad(datos: DatosInmueble) -> Hallazgo:
    desc = "Identifica la autoridad emisora"
    a = datos.autoridad_emisora
    if a.evidencia:
        lugar = ", ".join(x for x in (datos.municipio.valor, datos.entidad_federativa.valor) if x)
        return _h("USO-06", desc, EstadoRegla.CUMPLE, Severidad.INFO,
                  f"Expedida por {a.valor}" + (f" ({lugar})." if lugar else "."), a.evidencia)
    return _h("USO-06", desc, EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
              "No se identificó con evidencia la autoridad que expide la licencia.")


def _porcentaje(s: Optional[str]) -> Optional[float]:
    """'20%' -> 20.0, '70 %' -> 70.0, '0.7' -> 70.0 (coeficiente). None si no hay número."""
    if not s:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", s)
    if not m:
        return None
    n = float(m.group(0).replace(",", "."))
    return n * 100 if "%" not in s and n <= 1 else n


def _regla_superficie_comercial(datos: DatosInmueble) -> Hallazgo:
    desc = f"La superficie comercial permitida alcanza para una tienda ({SUPERFICIE_MINIMA_TIENDA_M2:.0f} m² o más)"
    tope = datos.especificos.get("superficie_maxima_giro_m2")
    if not tope or not tope.normalizado:
        return _h("USO-07", desc, EstadoRegla.NO_EVALUABLE, Severidad.INFO,
                  "La licencia no fija una superficie máxima para el giro comercial.")
    m2 = float(tope.normalizado)
    if m2 < SUPERFICIE_MINIMA_TIENDA_M2:
        return _h("USO-07", desc, EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE,
                  f"Limita el uso comercial a {m2:,.0f} m², menos de los {SUPERFICIE_MINIMA_TIENDA_M2:.0f} m² "
                  "mínimos de una tienda.", tope.evidencia)
    if m2 < SUPERFICIE_HOLGADA_TIENDA_M2:
        return _h("USO-07", desc, EstadoRegla.CUMPLE, Severidad.REVISION,
                  f"Permite hasta {m2:,.0f} m² comerciales: alcanza al mínimo pero queda por debajo de "
                  f"{SUPERFICIE_HOLGADA_TIENDA_M2:.0f} m²; confirmar con el formato de tienda.", tope.evidencia)
    return _h("USO-07", desc, EstadoRegla.CUMPLE, Severidad.INFO,
              f"Permite hasta {m2:,.0f} m² comerciales.", tope.evidencia)


def _regla_prohibiciones(datos: DatosInmueble) -> Hallazgo:
    desc = "Sin prohibición expresa de autoservicio, alcohol en envase cerrado o carga y descarga"
    prohib = [c for k, c in datos.especificos.items() if k.startswith("prohibicion_") and c.evidencia]
    if prohib:
        return _h("USO-08", desc, EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE,
                  "La licencia prohíbe expresamente: " + "; ".join(c.valor for c in prohib) + ".",
                  *(c.evidencia for c in prohib))
    return _h("USO-08", desc, EstadoRegla.CUMPLE, Severidad.INFO,
              "No se encontraron prohibiciones expresas para el giro de la tienda.")


def _regla_area_libre(datos: DatosInmueble) -> Hallazgo:
    desc = f"Área libre exigida de {AREA_LIBRE_MAXIMA:.0f} % o menos"
    libre, cos = datos.especificos.get("area_libre"), datos.especificos.get("cos")
    pct, campo, origen = None, None, ""
    if libre and libre.normalizado:
        pct, campo = _porcentaje(libre.valor), libre
    elif cos and cos.normalizado and (ocupacion := _porcentaje(cos.valor)) is not None and ocupacion <= 100:
        pct, campo, origen = 100 - ocupacion, cos, f" (calculada del COS {cos.valor})"
    if pct is None:
        return _h("USO-09", desc, EstadoRegla.NO_EVALUABLE, Severidad.INFO,
                  "La licencia no indica área libre ni COS.")
    if pct > AREA_LIBRE_MAXIMA:
        return _h("USO-09", desc, EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE,
                  f"Exige {pct:.0f} % de área libre{origen}, más del {AREA_LIBRE_MAXIMA:.0f} % que permite la "
                  "huella de sala de ventas y bodega.", campo.evidencia)
    return _h("USO-09", desc, EstadoRegla.CUMPLE, Severidad.INFO,
              f"Área libre exigida: {pct:.0f} %{origen}.", campo.evidencia)


def _regla_derechos_adquiridos(datos: DatosInmueble) -> Optional[Hallazgo]:
    da = datos.especificos.get("derechos_adquiridos")
    if not da or not da.evidencia:
        return None
    return _h("USO-10", "Uso basado en derechos adquiridos", EstadoRegla.NO_CUMPLE, Severidad.REVISION,
              "La licencia se sustenta en derechos adquiridos: hay que acreditar la documentación legal que "
              "los respalda.", da.evidencia)


def _regla_zona_protegida(datos: DatosInmueble) -> Optional[Hallazgo]:
    zp = datos.especificos.get("zona_protegida")
    if not zp or not zp.evidencia:
        return None
    return _h("USO-11", "Predio fuera de zona de conservación o patrimonio", EstadoRegla.NO_CUMPLE,
              Severidad.REVISION,
              f"El predio está en zona protegida («{zp.valor}»): puede limitar fachada, anuncios luminosos "
              "y maniobras de carga. Revisar las restricciones de la autoridad (INAH, INBAL o ambiental).",
              zp.evidencia)


def aplicar_reglas(ex: _UsoSueloLLM, datos: DatosInmueble, ctx: Contexto,
                   archivo: str, paginas: list[Pagina]) -> list[Hallazgo]:
    hallazgos = [
        _regla_compatibilidad(ex, datos, ctx, archivo, paginas),
        _regla_vigencia(datos, ctx),
        _regla_coherencia_fechas(datos, ctx),
        _regla_condicionantes(datos),
        _regla_identificacion(datos),
        _regla_autoridad(datos),
        _regla_superficie_comercial(datos),
        _regla_prohibiciones(datos),
        _regla_area_libre(datos),
        _regla_derechos_adquiridos(datos),
        _regla_zona_protegida(datos),
    ]
    return [h for h in hallazgos if h is not None]  # USO-10 y USO-11 solo aparecen si aplican


# ---------------------------------------------------------------- armado

def _construir_datos(ex: _UsoSueloLLM, archivo: str, paginas: list[Pagina]) -> DatosInmueble:
    c = lambda campo, norm=_upper_sin_acentos: _campo(campo, archivo, paginas, norm)  # noqa: E731
    datos = DatosInmueble(
        propietario=c(ex.propietario, _normalizar_nombre),
        direccion=c(ex.direccion, _normalizar_direccion),
        entidad_federativa=c(ex.entidad_federativa, _normalizar_entidad),
        municipio=c(ex.municipio, _normalizar_municipio),
        superficie_terreno_m2=c(ex.superficie_terreno_m2, _normalizar_superficie),
        clave_catastral=c(ex.clave_catastral, _normalizar_clave_catastral),
        numero_oficial=c(ex.numero_oficial, _normalizar_numero),
        fecha_emision=_campo_fecha(ex.fecha_emision, archivo, paginas),
        vigencia_hasta=_campo_fecha(ex.vigencia_hasta, archivo, paginas),
        autoridad_emisora=c(ex.autoridad_emisora),
    )
    especificos = {
        "uso_autorizado": c(ex.uso_autorizado),
        "clave_uso": c(ex.clave_uso, _normalizar_clave_catastral),
        "giro_autorizado": c(ex.giro_autorizado),
        "superficie_maxima_giro_m2": c(ex.superficie_maxima_giro_m2, _normalizar_superficie),
        "cos": c(ex.cos),
        "cus": c(ex.cus),
        "niveles_maximos": c(ex.niveles_maximos),
        "folio": c(ex.folio),
        "periodo_administracion": c(ex.periodo_administracion),
        "vigencia_texto": c(ex.vigencia_texto),
    }
    especificos["area_libre"] = c(ex.area_libre)
    libre = lambda campo: _campo(campo, archivo, paginas, exigir_valor=False)  # noqa: E731
    especificos["derechos_adquiridos"] = libre(ex.derechos_adquiridos)
    especificos["zona_protegida"] = libre(ex.zona_protegida)
    for i, prohibicion in enumerate(ex.prohibiciones_giro[:5], start=1):
        especificos[f"prohibicion_{i}"] = libre(prohibicion)
    for i, cond in enumerate(ex.condicionantes[:8], start=1):
        especificos[f"condicionante_{i}"] = libre(cond)
    datos.especificos = {k: v for k, v in especificos.items() if v.valor}
    if ex.compatibilidad_comercial != _Compatibilidad.NO_DETERMINABLE:
        datos.especificos["compatibilidad_comercial"] = Campo(
            valor=ex.compatibilidad_comercial.value,
            normalizado=ex.compatibilidad_comercial.value.upper(),
            evidencia=None,  # la evidencia vive en el hallazgo USO-01
            confianza=1.0,
        )
    return datos


def _confianza(datos: DatosInmueble, legibilidad: Legibilidad) -> float:
    campos = [datos.propietario, datos.direccion, datos.superficie_terreno_m2,
              datos.clave_catastral, datos.fecha_emision, datos.vigencia_hasta,
              datos.autoridad_emisora, datos.especificos.get("uso_autorizado", Campo())]
    confs = [c.confianza for c in campos if c.valor]
    conf = sum(confs) / len(confs) if confs else 0.0
    if legibilidad == Legibilidad.PARCIAL:
        conf = min(conf, TOPE_CONFIANZA_PARCIAL)
    return round(conf, 2)


def _resultado_ilegible(doc: DocumentoLeido) -> DocumentoAnalizado:
    return DocumentoAnalizado(
        archivo=doc.archivo, tipo=doc.tipo, confianza_tipo=doc.confianza_tipo,
        legibilidad=doc.legibilidad, datos=DatosInmueble(), confianza=0.0,
        hallazgos=[_h("USO-00", "Documento legible", EstadoRegla.NO_EVALUABLE, Severidad.REVISION,
                      "La ingesta marcó el documento como ilegible o sin texto; no se extrajo nada "
                      "para no inventar datos. Hay que pedir una copia legible.")],
    )


def analizar(doc: DocumentoLeido, ctx: Contexto) -> DocumentoAnalizado:
    if doc.legibilidad == Legibilidad.ILEGIBLE or not _paginas_con_texto(doc):
        return _resultado_ilegible(doc)
    extraido = _extraer(doc, ctx)
    datos = _construir_datos(extraido, doc.archivo, doc.paginas)
    return DocumentoAnalizado(
        archivo=doc.archivo,
        tipo=doc.tipo,
        confianza_tipo=doc.confianza_tipo,
        legibilidad=doc.legibilidad,
        datos=datos,
        hallazgos=aplicar_reglas(extraido, datos, ctx, doc.archivo, doc.paginas),
        confianza=_confianza(datos, doc.legibilidad),
    )
