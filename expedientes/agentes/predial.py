"""Agente Predial. Dueño: Julián.

Extraer (CONTEXT.md): propietario o contribuyente, dirección, cuenta o clave predial,
superficie registrada, datos que lo relacionan con los demás documentos.

Claves sugeridas para `datos.especificos`: ejercicio_pagado, fecha_pago, uso_del_predio,
adeudos, valor_catastral, folio.

Ejemplos de reglas (prefijo PRE-): pago del ejercicio vigente respecto a
`ctx.fecha_referencia`, adeudos u observaciones de ejercicios pendientes,
uso del predio registrado (ej. "BALDÍO URBANO").

Las reglas definitivas vienen en las guías oficiales del reto (pendiente de recibir).
"""
from ..schemas import Contexto, DocumentoAnalizado, DocumentoLeido


def analizar(doc: DocumentoLeido, ctx: Contexto) -> DocumentoAnalizado:
    raise NotImplementedError
