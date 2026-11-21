"""Contrato compartido entre todos los agentes y la UI.

Si necesitas cambiar algo de este archivo, avisa al equipo antes: todos dependen de él.
Los cambios van a `main` y cada quien los trae a su rama con `git merge main`.

Flujo de datos:

    archivo PDF/imagen
        └─ ingesta.leer_documento()          -> DocumentoLeido        (Julián)
             └─ <tipo>.analizar()            -> DocumentoAnalizado    (dueño de cada tipo)
                  └─ cruce.validar_cruzado() -> list[Inconsistencia]  (Diego)
                       └─ dictamen.dictaminar() -> Dictamen           (Juan Pablo)
    orquestador.analizar_expediente() encadena todo                    (Carlos)
    La UI solo consume `Dictamen`                                      (Yordi)
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- enums

class TipoDocumento(str, Enum):
    ESCRITURA = "escritura"
    PREDIAL = "predial"
    ALINEAMIENTO = "alineamiento_numero_oficial"
    USO_SUELO = "uso_de_suelo"
    OTRO = "otro"


TIPOS_REQUERIDOS: list[TipoDocumento] = [
    TipoDocumento.ESCRITURA,
    TipoDocumento.PREDIAL,
    TipoDocumento.ALINEAMIENTO,
    TipoDocumento.USO_SUELO,
]


class Legibilidad(str, Enum):
    BUENA = "buena"
    PARCIAL = "parcial"      # se leen algunos datos, otros no
    ILEGIBLE = "ilegible"    # no se debe extraer nada; el dictamen pide revisión


class EstadoRegla(str, Enum):
    CUMPLE = "cumple"
    NO_CUMPLE = "no_cumple"
    NO_EVALUABLE = "no_evaluable"  # falta el dato o el documento es ilegible


class Severidad(str, Enum):
    BLOQUEANTE = "bloqueante"  # empuja a "No cumple"
    REVISION = "revision"      # empuja a "Requiere revisión"
    INFO = "info"              # se muestra, no cambia la recomendación


class Recomendacion(str, Enum):
    CUMPLE = "Cumple"
    REQUIERE_REVISION = "Requiere revisión"
    NO_CUMPLE = "No cumple"


# ---------------------------------------------------------------- contexto

class Contexto(BaseModel):
    """Parámetros del análisis. Se pasa a todos los agentes."""
    fecha_referencia: date = Field(
        default_factory=date.today,
        description="Fecha contra la que se evalúan vigencias. No usar date.today() dentro de los agentes.",
    )
    uso_requerido: str = Field(
        default="comercial (tienda de autoservicio / minisúper)",
        description="Uso que Tiendas 3B necesita que autorice el Uso de Suelo.",
    )


# ---------------------------------------------------------------- ingesta (Julián)

class Pagina(BaseModel):
    numero: int = Field(ge=1, description="1 = primera página del archivo")
    texto: str = Field(description="Transcripción de la página (OCR o capa de texto)")


class DocumentoLeido(BaseModel):
    """Salida de la ingesta. Es también el formato del caché en `cache/<archivo>.json`."""
    archivo: str = Field(description="Nombre del archivo original, sin ruta")
    tipo: TipoDocumento
    confianza_tipo: float = Field(ge=0, le=1)
    legibilidad: Legibilidad
    paginas: list[Pagina]
    paginas_totales: int = Field(ge=0, description="Páginas del archivo, aunque no se hayan leído todas")
    notas: Optional[str] = Field(default=None, description="Ej. 'solo se leyeron las primeras 12 páginas'")


# ---------------------------------------------------------------- extracción

class Evidencia(BaseModel):
    archivo: str
    pagina: int = Field(ge=1)
    cita: str = Field(description="Texto literal del documento que sustenta el dato o hallazgo")


class Campo(BaseModel):
    valor: Optional[str] = Field(default=None, description="Tal como aparece en el documento")
    normalizado: Optional[str] = Field(
        default=None,
        description="Forma comparable: mayúsculas sin acentos, superficie en número, fechas ISO, etc.",
    )
    evidencia: Optional[Evidencia] = None
    confianza: float = Field(default=0.0, ge=0, le=1)


class DatosInmueble(BaseModel):
    """Campos comunes. Son los que usa la validación cruzada, así que todos usan los mismos nombres.

    Lo que sea propio de un solo tipo (uso autorizado, alineamiento, giro, adeudos...)
    va en `especificos` con una clave en snake_case documentada en el agente de ese tipo.
    """
    propietario: Campo = Field(default_factory=Campo)
    direccion: Campo = Field(default_factory=Campo)
    superficie_terreno_m2: Campo = Field(default_factory=Campo)
    clave_catastral: Campo = Field(default_factory=Campo)
    numero_oficial: Campo = Field(default_factory=Campo)
    fecha_emision: Campo = Field(default_factory=Campo)
    vigencia_hasta: Campo = Field(default_factory=Campo)
    autoridad_emisora: Campo = Field(default_factory=Campo)
    especificos: dict[str, Campo] = Field(default_factory=dict)


CAMPOS_CRUZABLES = [
    "propietario",
    "direccion",
    "superficie_terreno_m2",
    "clave_catastral",
    "numero_oficial",
]


# ---------------------------------------------------------------- validación

class Hallazgo(BaseModel):
    id_regla: str = Field(description="Ej. 'USO-01'. Prefijos: ESC, PRE, ALI, USO, CRU, EXP")
    descripcion: str = Field(description="Qué se evaluó, en una línea")
    estado: EstadoRegla
    severidad: Severidad
    explicacion: str = Field(description="Por qué, en lenguaje claro para el equipo legal")
    evidencias: list[Evidencia] = Field(default_factory=list)


class DocumentoAnalizado(BaseModel):
    """Salida de cada agente por tipo: lo extraído más las reglas propias de ese documento."""
    archivo: str
    tipo: TipoDocumento
    confianza_tipo: float = Field(ge=0, le=1)
    legibilidad: Legibilidad
    datos: DatosInmueble
    hallazgos: list[Hallazgo] = Field(default_factory=list)
    confianza: float = Field(ge=0, le=1, description="Confianza global del análisis de este documento")


# ---------------------------------------------------------------- validación cruzada (Diego)

class ValorEncontrado(BaseModel):
    archivo: str
    tipo: TipoDocumento
    valor: Optional[str]
    evidencia: Optional[Evidencia] = None


class Inconsistencia(BaseModel):
    id_regla: str = Field(description="Ej. 'CRU-DIR'")
    campo: str = Field(description="Uno de CAMPOS_CRUZABLES u otro dato comparado")
    descripcion: str
    severidad: Severidad
    valores: list[ValorEncontrado] = Field(description="Qué dice cada documento, con su evidencia")


# ---------------------------------------------------------------- dictamen (Juan Pablo) -> UI

class Dictamen(BaseModel):
    expediente_id: str
    fecha_analisis: datetime
    fecha_referencia: date
    documentos: list[DocumentoAnalizado]
    documentos_faltantes: list[TipoDocumento]
    hallazgos_expediente: list[Hallazgo] = Field(
        default_factory=list,
        description="Reglas a nivel expediente (faltantes, ilegibles, etc.). Los de cada documento viven en documentos[].hallazgos",
    )
    inconsistencias: list[Inconsistencia]
    recomendacion: Recomendacion
    confianza: float = Field(ge=0, le=1)
    resumen: str = Field(description="Explicación de la recomendación para el equipo legal")
    razones: list[str] = Field(description="Viñetas cortas que sustentan la recomendación")

    def todos_los_hallazgos(self) -> list[Hallazgo]:
        return self.hallazgos_expediente + [h for d in self.documentos for h in d.hallazgos]
