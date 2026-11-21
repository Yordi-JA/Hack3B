"""Agente Escrituras. Dueño: Carlos.

Extraer (CONTEXT.md): propietario o titular, dirección e identificación del inmueble,
superficie del terreno, datos relevantes, información que lo relaciona con el expediente.

Claves sugeridas para `datos.especificos`: numero_escritura, volumen, notario, fecha_escritura,
tipo_acto (compraventa, fusión, lotificación...), folio_real, medidas_colindancias, gravamenes.

Ojo: son las más largas (hasta 50 páginas). Los datos clave suelen estar en el proemio,
antecedentes y cláusulas; no mandar las 50 páginas al modelo.

Prefijo de reglas: ESC-.
"""
from ..schemas import Contexto, DocumentoAnalizado, DocumentoLeido


def analizar(doc: DocumentoLeido, ctx: Contexto) -> DocumentoAnalizado:
    raise NotImplementedError
