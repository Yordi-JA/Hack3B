"""Agente Alineamiento y Número Oficial. Dueño: Diego.

Extraer (CONTEXT.md): dirección oficial, número oficial asignado, identificación del predio,
alineamiento determinado por la autoridad, fecha de emisión y vigencia, autoridad emisora.

Claves sugeridas para `datos.especificos`: alineamiento, afectaciones, superficie_afectada_m2,
restricciones_construccion, folio.

Ojo: algunas constancias traen afectaciones (franja donde no se puede construir) y vigencia
de "un año a partir de su expedición": calcular contra `ctx.fecha_referencia`.
Alineamiento y Número Oficial pueden venir en dos archivos separados.

Prefijo de reglas: ALI-.
"""
from ..schemas import Contexto, DocumentoAnalizado, DocumentoLeido


def analizar(doc: DocumentoLeido, ctx: Contexto) -> DocumentoAnalizado:
    raise NotImplementedError
