"""Lógica pura de la UI: nada de Streamlit aquí, todo se prueba con pytest."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import mean
from typing import Iterable, Optional

import re

from expedientes.schemas import (
    TIPOS_REQUERIDOS,
    Campo,
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

from .mapa import ConteoEntidad, normalizar_entidad, normalizar_texto

NOMBRE_TIPO = {
    TipoDocumento.ESCRITURA: "Escritura",
    TipoDocumento.PREDIAL: "Predial",
    TipoDocumento.ALINEAMIENTO: "Alineamiento y Número Oficial",
    TipoDocumento.USO_SUELO: "Uso de Suelo",
    TipoDocumento.OTRO: "No reconocido",
}

NOMBRE_TIPO_CORTO = {
    TipoDocumento.ESCRITURA: "Escritura",
    TipoDocumento.PREDIAL: "Predial",
    TipoDocumento.ALINEAMIENTO: "Alineamiento",
    TipoDocumento.USO_SUELO: "Uso de suelo",
    TipoDocumento.OTRO: "Otro",
}

NOMBRE_CAMPO = {
    "propietario": "Propietario",
    "direccion": "Dirección",
    "entidad_federativa": "Entidad federativa",
    "municipio": "Municipio",
    "superficie_terreno_m2": "Superficie del terreno (m²)",
    "clave_catastral": "Clave catastral",
    "numero_oficial": "Número oficial",
    "fecha_emision": "Fecha de emisión",
    "vigencia_hasta": "Vigente hasta",
    "autoridad_emisora": "Autoridad emisora",
    "numero_escritura": "Número de escritura",
    "tipo_acto": "Acto",
    "uso_autorizado": "Uso autorizado",
    "giro_autorizado": "Giro autorizado",
    "ejercicio_pagado": "Ejercicio pagado",
    "uso_del_predio": "Uso del predio",
    "folio_registro_publico": "Folio del Registro Público",
}

CAMPOS_COMUNES = [
    "propietario", "direccion", "entidad_federativa", "municipio", "superficie_terreno_m2", "clave_catastral",
    "numero_oficial", "fecha_emision", "vigencia_hasta", "autoridad_emisora",
]

# Datos que deben coincidir entre documentos del mismo inmueble. Fechas y autoridad cambian por
# documento de forma legítima, así que no se marcan como diferencia.
CAMPOS_COMPARABLES = {"propietario", "direccion", "entidad_federativa", "municipio",
                      "superficie_terreno_m2", "clave_catastral", "numero_oficial"}

NOMBRE_ESTADO_REGLA = {
    EstadoRegla.CUMPLE: "Cumple",
    EstadoRegla.NO_CUMPLE: "No cumple",
    EstadoRegla.NO_EVALUABLE: "No evaluable",
}

NOMBRE_SEVERIDAD = {
    Severidad.BLOQUEANTE: "Bloqueante",
    Severidad.REVISION: "Revisión",
    Severidad.INFO: "Informativo",
}

# Hallazgos que avisan que un archivo no se pudo analizar; no son requisitos del expediente.
REGLAS_DE_PROCESO = {"EXP-ERROR", "EXP-TIPO"}

_RANGO_SEVERIDAD = {Severidad.INFO: 0, Severidad.REVISION: 1, Severidad.BLOQUEANTE: 2}
_RANGO_RECOMENDACION = {
    Recomendacion.CUMPLE: 0,
    Recomendacion.REQUIERE_REVISION: 1,
    Recomendacion.NO_CUMPLE: 2,
}


def nombre_campo(clave: str) -> str:
    return NOMBRE_CAMPO.get(clave) or clave.replace("_", " ").capitalize()


# ------------------------------------------------------------------ ubicación del expediente

@dataclass
class Ubicacion:
    entidad: Optional[str]           # clave canónica de mapa.ENTIDADES, o None
    municipio: Optional[str]         # normalizado mayoritario
    confirmada: bool                 # todos los documentos que la mencionan coinciden
    valores: list[str] = field(default_factory=list)  # entidades distintas encontradas, mayoritaria primero
    municipio_valor: Optional[str] = None  # el municipio como lo escribe el documento (con acentos)


def _mayoritario(valores: list[str]) -> tuple[Optional[str], bool]:
    """(valor con más menciones, hay empate en el primer lugar)."""
    if not valores:
        return None, False
    conteo = Counter(valores).most_common()
    empate = len(conteo) > 1 and conteo[0][1] == conteo[1][1]
    return conteo[0][0], empate


def consolidar_ubicacion(dictamen: Dictamen) -> Ubicacion:
    """Entidad y municipio del expediente a partir de todos sus documentos.

    Gana la entidad con más documentos. Si hay empate no se elige ninguna; si hay desacuerdo sin
    empate se usa la mayoritaria pero queda sin confirmar, con todos los valores a la vista.
    """
    entidades = []
    for doc in dictamen.documentos:
        campo = doc.datos.entidad_federativa
        clave = normalizar_entidad(campo.normalizado) or normalizar_entidad(campo.valor)
        if clave:
            entidades.append(clave)
    entidad, empate = _mayoritario(entidades)
    distintas = [v for v, _ in Counter(entidades).most_common()]

    municipios = [
        normalizar_texto(d.datos.municipio.normalizado or d.datos.municipio.valor or "")
        for d in dictamen.documentos
    ]
    municipio, empate_mun = _mayoritario([m for m in municipios if m])
    municipio_valor = next(
        (d.datos.municipio.valor for d, m in zip(dictamen.documentos, municipios)
         if municipio and m == municipio and d.datos.municipio.valor),
        None,
    )

    return Ubicacion(
        entidad=None if empate else entidad,
        municipio=None if empate_mun else municipio,
        confirmada=len(distintas) == 1,
        valores=distintas,
        municipio_valor=None if empate_mun else municipio_valor,
    )


# ------------------------------------------------------------------ requisitos

@dataclass
class Requisito:
    id_regla: str
    descripcion: str
    estado: EstadoRegla
    severidad: Severidad
    archivos: list[str]
    hallazgos: list[Hallazgo]
    tipo: Optional[TipoDocumento] = None  # None: regla del expediente completo


def consolidar_requisitos(dictamen: Dictamen) -> list[Requisito]:
    """Un requisito por (tipo, id de regla), siguiendo el contrato: se cumple si algún archivo de ese
    tipo lo cumple. Las reglas de `hallazgos_expediente` van con tipo None.

    Si ninguno lo cumple y alguno lo incumple, no cumple; si no, queda no evaluable.
    Los avisos de proceso (EXP-ERROR, EXP-TIPO) se excluyen: se muestran con su documento, y
    `pendientes` los muestra como renglones propios.
    Orden: no cumple, no evaluable, cumple; dentro de cada grupo, más severo primero.
    """
    grupos: dict[tuple[Optional[TipoDocumento], str], list[tuple[Optional[str], Hallazgo]]] = {}
    for h in dictamen.hallazgos_expediente:
        grupos.setdefault((None, h.id_regla), []).append((None, h))
    for doc in dictamen.documentos:
        for h in doc.hallazgos:
            grupos.setdefault((doc.tipo, h.id_regla), []).append((doc.archivo, h))

    requisitos = []
    for (tipo, id_regla), items in grupos.items():
        if id_regla in REGLAS_DE_PROCESO:
            continue
        hallazgos = [h for _, h in items]
        estados = {h.estado for h in hallazgos}
        if EstadoRegla.CUMPLE in estados:
            estado = EstadoRegla.CUMPLE
        elif EstadoRegla.NO_CUMPLE in estados:
            estado = EstadoRegla.NO_CUMPLE
        else:
            estado = EstadoRegla.NO_EVALUABLE
        decisivos = [h for h in hallazgos if h.estado == estado]
        severidad = max((h.severidad for h in decisivos), key=_RANGO_SEVERIDAD.__getitem__)
        archivos = list(dict.fromkeys(a for a, _ in items if a))
        requisitos.append(
            Requisito(id_regla, decisivos[0].descripcion, estado, severidad, archivos, hallazgos, tipo)
        )

    orden_estado = {EstadoRegla.NO_CUMPLE: 0, EstadoRegla.NO_EVALUABLE: 1, EstadoRegla.CUMPLE: 2}
    requisitos.sort(key=lambda r: (orden_estado[r.estado], -_RANGO_SEVERIDAD[r.severidad], r.id_regla))
    return requisitos


def sin_analizar(doc: DocumentoAnalizado) -> bool:
    """El agente de este archivo falló: sus datos vienen vacíos y sus reglas no se evaluaron."""
    return any(h.id_regla == "EXP-ERROR" for h in doc.hallazgos)


def contar_por_estado(hallazgos: Iterable[Hallazgo]) -> dict[EstadoRegla, int]:
    conteo = Counter(h.estado for h in hallazgos)
    return {e: conteo.get(e, 0) for e in EstadoRegla}


# ------------------------------------------------------------------ documentos

@dataclass
class TipoRecibido:
    tipo: TipoDocumento
    archivos: list[str]

    @property
    def recibido(self) -> bool:
        return bool(self.archivos)


def documentos_por_tipo(dictamen: Dictamen) -> list[TipoRecibido]:
    """Los 4 tipos requeridos en orden, con los archivos recibidos de cada uno (puede haber 0, 1 o 2)."""
    return [
        TipoRecibido(t, [d.archivo for d in dictamen.documentos if d.tipo == t]) for t in TIPOS_REQUERIDOS
    ]


def faltantes(dictamen: Dictamen) -> list[TipoDocumento]:
    """Lo que dice el dictamen, más cualquier tipo requerido sin archivo que el dictamen haya omitido."""
    sin_archivo = [t.tipo for t in documentos_por_tipo(dictamen) if not t.recibido]
    return list(dict.fromkeys([*dictamen.documentos_faltantes, *sin_archivo]))


# Lo primero que revisa el equipo legal en cada tipo (claves de especificos según el ejemplo del equipo).
CAMPOS_CLAVE = {
    TipoDocumento.ESCRITURA: ["propietario", "superficie_terreno_m2", "clave_catastral", "numero_escritura", "tipo_acto"],
    TipoDocumento.PREDIAL: ["propietario", "clave_catastral", "vigencia_hasta", "adeudo", "ejercicio_pagado"],
    TipoDocumento.ALINEAMIENTO: ["numero_oficial", "direccion", "vigencia_hasta", "alineamiento", "afectaciones"],
    TipoDocumento.USO_SUELO: ["uso_autorizado", "giro_autorizado", "vigencia_hasta", "superficie_terreno_m2"],
}


def campos_clave(doc: DocumentoAnalizado, n: int = 4) -> list[tuple[str, Campo]]:
    """Hasta `n` datos para la tarjeta del documento: primero los clave de su tipo, luego el resto."""
    disponibles = dict(campos_con_dato(doc))
    orden = [c for c in CAMPOS_CLAVE.get(doc.tipo, []) if c in disponibles]
    orden += [c for c in disponibles if c not in orden]
    return [(c, disponibles[c]) for c in orden[:n]]


def campos_con_dato(doc: DocumentoAnalizado) -> list[tuple[str, Campo]]:
    """(clave, campo) con valor, comunes primero y luego los específicos del tipo."""
    pares = [(c, getattr(doc.datos, c)) for c in CAMPOS_COMUNES]
    pares += list(doc.datos.especificos.items())
    return [(c, campo) for c, campo in pares if campo.valor]


def filas_datos(
    dictamen: Dictamen, documentos: Optional[list[DocumentoAnalizado]] = None
) -> list[tuple[str, list[Optional[Campo]]]]:
    """Tabla campo x documento. Solo filas con al menos un valor; columnas = `documentos`
    (por omisión, todos los del dictamen)."""
    documentos = dictamen.documentos if documentos is None else documentos
    especificos = list(dict.fromkeys(k for d in documentos for k in d.datos.especificos))
    filas = []
    for clave in CAMPOS_COMUNES + especificos:
        celdas: list[Optional[Campo]] = []
        for doc in documentos:
            campo = getattr(doc.datos, clave) if clave in CAMPOS_COMUNES else doc.datos.especificos.get(clave)
            celdas.append(campo if campo and campo.valor else None)
        if any(celdas):
            filas.append((clave, celdas))
    return filas


def _discrepantes(valores: list[Optional[str]]) -> set[int]:
    """Índices cuyo valor difiere del más frecuente. Con empate en el primer lugar no hay mayoría y
    se marcan todos los que tienen valor. Los vacíos no cuentan."""
    presentes = [v for v in valores if v]
    if len(set(presentes)) < 2:
        return set()
    conteo = Counter(presentes).most_common()
    if conteo[0][1] == conteo[1][1]:
        return {i for i, v in enumerate(valores) if v}
    return {i for i, v in enumerate(valores) if v and v != conteo[0][0]}


def valores_discrepantes(celdas: list[Optional[Campo]]) -> set[int]:
    """Para la tabla de datos: compara `normalizado` de cada celda."""
    return _discrepantes([c.normalizado if c else None for c in celdas])


def valores_inconsistencia_discrepantes(valores: list[Optional[str]]) -> set[int]:
    """Para Inconsistencia.valores (texto ya comparable)."""
    return _discrepantes(valores)


# ------------------------------------------------------------------ detalle: qué hay que resolver

@dataclass
class Pendiente:
    """Un renglón de "Qué hay que resolver"."""
    clase: str                       # requisito | inconsistencia | faltante | sin_analizar | no_reconocido | ilegible
    texto: str                       # una línea: qué está mal
    severidad: Optional[Severidad]
    archivos: list[str]
    explicacion: str = ""
    requisito: Optional[Requisito] = None
    inconsistencia: Optional[Inconsistencia] = None
    relacionados: list[Requisito] = field(default_factory=list)  # reglas que dicen lo mismo que la inconsistencia


_PALABRAS_VACIAS = {
    "para", "porque", "entre", "sobre", "desde", "hasta", "como", "este", "esta", "estos", "estas", "pero",
    "cuando", "donde", "todos", "todas", "tiene", "tienen", "bloqueante", "revision", "documento", "documentos",
}


def _palabras(texto: str) -> set[str]:
    """Palabras con significado para comparar textos: sin acentos, de 4 letras o más, y números."""
    norm = normalizar_texto(texto).lower()
    return {w for w in norm.split() if (len(w) >= 4 or w.isdigit()) and w not in _PALABRAS_VACIAS}


def primera_oracion(texto: str) -> str:
    """La primera oración de una explicación: lo que se lee en la lista; el resto va en la evidencia."""
    partes = re.split(r"(?<=\.)\s+(?=[A-ZÁÉÍÓÚÑ¿¡])", " ".join(texto.split()), maxsplit=1)
    return partes[0] if partes else ""


def _menciona_tipo(texto: str, tipo: TipoDocumento) -> bool:
    clave = normalizar_texto(NOMBRE_TIPO_CORTO[tipo]).lower()
    return clave in normalizar_texto(texto).lower()


def pendientes(dictamen: Dictamen) -> tuple[list[Pendiente], list[str]]:
    """Lista única y priorizada de lo que el equipo legal tiene que resolver, sin duplicados.

    Junta: requisitos no cumplidos o sin evaluar que pesan (revisión o bloqueante), inconsistencias
    entre documentos, archivos que no se pudieron analizar, leer o reconocer, y tipos faltantes que
    ninguna regla del expediente ya menciona. Las reglas sin evaluar de un archivo ilegible o sin
    analizar no se repiten: las cubre el renglón de ese archivo.

    Devuelve (pendientes ordenados: bloqueante, revisión, resto; razones del dictamen que ningún
    renglón cubre, para mostrarlas aparte sin perderlas).
    """
    items: list[Pendiente] = []
    tapados: set[str] = set()   # archivos ilegibles o sin analizar: sus reglas sin evaluar no se listan

    for doc in dictamen.documentos:
        for h in doc.hallazgos:
            if h.id_regla == "EXP-ERROR":
                tipo = NOMBRE_TIPO[doc.tipo]
                items.append(Pendiente(
                    "sin_analizar", f"No se pudo analizar {doc.archivo} ({tipo}); revísalo a mano.",
                    h.severidad, [doc.archivo], h.explicacion))
                tapados.add(doc.archivo)
            elif h.id_regla == "EXP-TIPO":
                items.append(Pendiente(
                    "no_reconocido", f"No se reconoció el tipo de {doc.archivo}; no se analizó.",
                    h.severidad, [doc.archivo], h.explicacion))
                tapados.add(doc.archivo)

    reglas_exp = [h for h in dictamen.hallazgos_expediente if h.estado != EstadoRegla.CUMPLE]
    texto_exp = " ".join(f"{h.descripcion} {h.explicacion}" for h in reglas_exp)

    for doc in dictamen.documentos:
        if doc.legibilidad == Legibilidad.ILEGIBLE and doc.archivo not in tapados:
            tapados.add(doc.archivo)
            ya_dicho = _menciona_tipo(texto_exp, doc.tipo) and "ilegib" in normalizar_texto(texto_exp).lower()
            if not ya_dicho:
                items.append(Pendiente(
                    "ilegible", f"{doc.archivo} es ilegible: sus reglas quedaron sin evaluar. Pide una copia legible.",
                    Severidad.REVISION, [doc.archivo]))

    for r in consolidar_requisitos(dictamen):
        if r.estado == EstadoRegla.CUMPLE:
            continue
        if r.estado == EstadoRegla.NO_EVALUABLE:
            if r.severidad == Severidad.INFO:
                continue
            if r.archivos and all(a in tapados for a in r.archivos):
                continue
        decisivo = next(h for h in r.hallazgos if h.estado == r.estado)
        # Las reglas del expediente no tienen archivo propio: se usan los de sus citas.
        archivos = r.archivos or list(dict.fromkeys(e.archivo for h in r.hallazgos for e in h.evidencias))
        items.append(Pendiente(
            "requisito", primera_oracion(decisivo.explicacion) or r.descripcion, r.severidad, archivos,
            decisivo.explicacion, requisito=r))

    for inc in dictamen.inconsistencias:
        archivos = list(dict.fromkeys(v.archivo for v in inc.valores))
        nuevo = Pendiente("inconsistencia", inc.descripcion, inc.severidad, archivos, inconsistencia=inc)
        # Una regla que dice lo mismo que la inconsistencia (ej. número oficial 17 contra 15) se une a ella.
        palabras_inc = _palabras(inc.descripcion)
        for it in [i for i in items if i.clase == "requisito"]:
            propias = _palabras(it.texto)
            if propias and len(propias & palabras_inc) >= len(propias) / 2:
                items.remove(it)
                nuevo.relacionados.append(it.requisito)
                if _RANGO_SEVERIDAD[it.severidad] > _RANGO_SEVERIDAD[nuevo.severidad]:
                    nuevo.severidad = it.severidad
        items.append(nuevo)

    for tr in documentos_por_tipo(dictamen):
        if tr.tipo not in faltantes(dictamen) or _menciona_tipo(texto_exp, tr.tipo):
            continue
        nombre = NOMBRE_TIPO[tr.tipo]
        if tr.recibido:
            texto = f"Falta {nombre}: se recibió {', '.join(tr.archivos)}, pero el dictamen lo considera faltante."
        else:
            texto = f"Falta {nombre}: no se recibió ningún archivo."
        items.append(Pendiente("faltante", texto, Severidad.REVISION, list(tr.archivos)))

    rango = {Severidad.BLOQUEANTE: 0, Severidad.REVISION: 1}
    items = [it for _, it in sorted(enumerate(items), key=lambda p: (rango.get(p[1].severidad, 2), p[0]))]

    cubiertas = [_palabras(_texto_busqueda(it)) for it in items]
    sueltas = []
    for razon in dictamen.razones:
        palabras = _palabras(razon)
        if not palabras or not any(len(palabras & c) >= max(2, len(palabras) / 2) for c in cubiertas):
            sueltas.append(razon)
    return items, sueltas


def _texto_busqueda(it: Pendiente) -> str:
    partes = [it.texto, it.explicacion, *it.archivos]
    if it.requisito:
        partes += [it.requisito.descripcion, *(h.explicacion for h in it.requisito.hallazgos)]
    for r in it.relacionados:
        partes += [r.descripcion, *(h.explicacion for h in r.hallazgos)]
    if it.inconsistencia:
        inc = it.inconsistencia
        partes += [nombre_campo(inc.campo), inc.descripcion, *(v.valor or "" for v in inc.valores),
                   *(NOMBRE_TIPO[v.tipo] for v in inc.valores)]
    return " ".join(partes)


# ------------------------------------------------------------------ bandeja

def rango_recomendacion(r: Recomendacion) -> int:
    return _RANGO_RECOMENDACION[r]


@dataclass
class Indicadores:
    total: int
    por_recomendacion: dict[Recomendacion, int]
    confianza_promedio: Optional[float]
    ejemplos: int


def indicadores(dictamenes: list[tuple[Dictamen, bool]]) -> Indicadores:
    """`dictamenes`: pares (dictamen, es_ejemplo)."""
    conteo = Counter(d.recomendacion for d, _ in dictamenes)
    return Indicadores(
        total=len(dictamenes),
        por_recomendacion={r: conteo.get(r, 0) for r in Recomendacion},
        confianza_promedio=mean(d.confianza for d, _ in dictamenes) if dictamenes else None,
        ejemplos=sum(1 for _, ej in dictamenes if ej),
    )


def conteo_por_entidad(dictamenes: Iterable[Dictamen]) -> dict[str, ConteoEntidad]:
    conteos: dict[str, ConteoEntidad] = {}
    for d in dictamenes:
        entidad = consolidar_ubicacion(d).entidad
        if not entidad:
            continue
        c = conteos.setdefault(entidad, ConteoEntidad())
        c.total += 1
        c.por_recomendacion[d.recomendacion] = c.por_recomendacion.get(d.recomendacion, 0) + 1
    return conteos


SIN_ENTIDAD = "SIN_ENTIDAD"


def coincide(
    dictamen: Dictamen,
    entidad: Optional[str] = None,
    recomendacion: Optional[Recomendacion] = None,
    texto: str = "",
) -> bool:
    """Filtro de la bandeja. `entidad=SIN_ENTIDAD` deja solo los que no tienen entidad."""
    ubicacion = consolidar_ubicacion(dictamen)
    if entidad == SIN_ENTIDAD and ubicacion.entidad is not None:
        return False
    if entidad and entidad != SIN_ENTIDAD and ubicacion.entidad != entidad:
        return False
    if recomendacion and dictamen.recomendacion != recomendacion:
        return False
    if texto:
        buscado = normalizar_texto(texto)
        pajar = normalizar_texto(
            " ".join(
                filter(
                    None,
                    [
                        dictamen.expediente_id,
                        ubicacion.municipio,
                        *ubicacion.valores,
                        *(d.archivo for d in dictamen.documentos),
                        *(d.datos.propietario.valor for d in dictamen.documentos),
                        *(d.datos.direccion.valor for d in dictamen.documentos),
                    ],
                )
            )
        )
        if buscado not in pajar:
            return False
    return True


def orden_bandeja(dictamen: Dictamen) -> tuple:
    """Primero lo que requiere atención (No cumple, luego revisión), y lo más reciente arriba."""
    return (-rango_recomendacion(dictamen.recomendacion), -dictamen.fecha_analisis.timestamp())
