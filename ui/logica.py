"""Lógica pura de la UI: nada de Streamlit aquí, todo se prueba con pytest."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import mean
from typing import Iterable, Optional

from expedientes.schemas import (
    TIPOS_REQUERIDOS,
    Campo,
    Dictamen,
    DocumentoAnalizado,
    EstadoRegla,
    Hallazgo,
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

    return Ubicacion(
        entidad=None if empate else entidad,
        municipio=None if empate_mun else municipio,
        confirmada=len(distintas) == 1,
        valores=distintas,
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
    `archivos_sin_analizar` dice qué tipos pueden tener requisitos incompletos por eso.
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


def archivos_sin_analizar(dictamen: Dictamen) -> list[DocumentoAnalizado]:
    return [d for d in dictamen.documentos if sin_analizar(d)]


def contar_por_estado(hallazgos: Iterable[Hallazgo]) -> dict[EstadoRegla, int]:
    conteo = Counter(h.estado for h in hallazgos)
    return {e: conteo.get(e, 0) for e in EstadoRegla}


def avisos_de_proceso(doc: DocumentoAnalizado) -> list[Hallazgo]:
    return [h for h in doc.hallazgos if h.id_regla in REGLAS_DE_PROCESO]


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


def tipo_sin_analizar(dictamen: Dictamen, tipo: TipoDocumento) -> bool:
    """Se recibió al menos un archivo del tipo y ninguno se pudo analizar."""
    docs = [d for d in dictamen.documentos if d.tipo == tipo]
    return bool(docs) and all(sin_analizar(d) for d in docs)


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


def filas_datos(dictamen: Dictamen) -> list[tuple[str, list[Optional[Campo]]]]:
    """Tabla campo x documento. Solo filas con al menos un valor; columnas = dictamen.documentos."""
    especificos = list(dict.fromkeys(k for d in dictamen.documentos for k in d.datos.especificos))
    filas = []
    for clave in CAMPOS_COMUNES + especificos:
        celdas: list[Optional[Campo]] = []
        for doc in dictamen.documentos:
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
