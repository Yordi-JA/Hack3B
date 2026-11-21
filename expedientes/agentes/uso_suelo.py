"""Agente Uso de Suelo. Dueño: Juan Pablo.

Extraer (CONTEXT.md): dirección e identificación, uso de suelo autorizado, compatibilidad con
el uso comercial requerido (`ctx.uso_requerido`), restricciones o condicionantes,
superficie aplicable, fecha de emisión y vigencia, autoridad emisora.

Claves sugeridas para `datos.especificos`: uso_autorizado, giro_autorizado,
superficie_maxima_giro_m2, cos, cus, niveles_maximos, condicionantes, folio.

Es el ejemplo que pone el reto: determinar si autoriza el uso comercial, qué condicionantes
tiene y citar la evidencia. Ojo con vigencias vencidas y con encabezados que no cuadran con
la fecha del folio (posible documento alterado).

Prefijo de reglas: USO-.
"""
from ..schemas import Contexto, DocumentoAnalizado, DocumentoLeido


def analizar(doc: DocumentoLeido, ctx: Contexto) -> DocumentoAnalizado:
    raise NotImplementedError
