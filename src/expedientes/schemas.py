"""Modelos de datos compartidos por todos los agentes.

Cada dato extraído y cada hallazgo lleva su evidencia (documento, página, fragmento),
porque la rúbrica pide trazabilidad: 20 % del puntaje.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TipoDocumento(str, Enum):
    ESCRITURA = "escritura"
    PREDIAL = "predial"
    ALINEAMIENTO = "alineamiento_numero_oficial"
    USO_SUELO = "uso_de_suelo"
    DESCONOCIDO = "desconocido"


TIPOS_REQUERIDOS = [
    TipoDocumento.ESCRITURA,
    TipoDocumento.PREDIAL,
    TipoDocumento.ALINEAMIENTO,
    TipoDocumento.USO_SUELO,
]


class Evidencia(BaseModel):
    documento: str = Field(description="Nombre del archivo")
    pagina: int = Field(description="Página (1 = primera)")
    fragmento: str = Field(description="Texto literal del documento que sustenta el dato")


class Campo(BaseModel):
    valor: Optional[str] = None
    evidencia: Optional[Evidencia] = None
    confianza: float = Field(default=0.0, ge=0, le=1)


class DocumentoExtraido(BaseModel):
    archivo: str
    tipo: TipoDocumento
    confianza_tipo: float = Field(ge=0, le=1)
    # Campos comunes para validación cruzada
    propietario: Campo = Campo()
    direccion: Campo = Campo()
    superficie_m2: Campo = Campo()
    clave_catastral: Campo = Campo()
    numero_oficial: Campo = Campo()
    fecha_emision: Campo = Campo()
    vigencia: Campo = Campo()
    autoridad_emisora: Campo = Campo()
    # Específicos por tipo (uso autorizado, restricciones, alineamiento, etc.)
    otros: dict[str, Campo] = {}


class Severidad(str, Enum):
    BLOQUEANTE = "bloqueante"  # lleva a "No cumple"
    REVISION = "revision"      # lleva a "Requiere revisión"
    INFO = "info"


class Hallazgo(BaseModel):
    regla: str = Field(description="Id o descripción de la regla evaluada")
    cumple: bool
    severidad: Severidad
    explicacion: str = Field(description="Razón en lenguaje claro para el equipo legal")
    evidencias: list[Evidencia] = []


class Recomendacion(str, Enum):
    CUMPLE = "Cumple"
    REVISION = "Requiere revisión"
    NO_CUMPLE = "No cumple"


class Dictamen(BaseModel):
    inmueble: str
    documentos_recibidos: list[str]
    documentos_faltantes: list[TipoDocumento]
    extracciones: list[DocumentoExtraido]
    hallazgos: list[Hallazgo]
    recomendacion: Recomendacion
    confianza: float = Field(ge=0, le=1)
    resumen: str
