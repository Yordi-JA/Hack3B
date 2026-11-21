"""Agente de ingesta y clasificación. Dueño: Julián.

Qué hace:
- Abre PDF o imagen (pymupdf abre ambos) y rasteriza cada página.
- Le pasa la imagen a un modelo con visión para transcribir el texto y, en la misma
  llamada, decir qué tipo de documento es y qué tan legible está.
- Guarda el resultado en el caché (`cache.guardar_cache`) para que nadie repita el OCR.

Datos del set:
- 57 de 62 PDFs son escaneos sin texto; 5 sí traen capa de texto (usarla y ahorrar la llamada).
- Escrituras de hasta 50 páginas / 20 MB: definir un tope de páginas y anotarlo en `notas`.
- El expediente con sufijo "..." está borroso a propósito: debe salir `Legibilidad.ILEGIBLE`
  y NO inventar texto.
- Hay un predial en .jpeg.
- Saltar todo lo que esté bajo `__MACOSX` o empiece con `._`: son metadatos de macOS, no PDFs.
- Llenar `DocumentoLeido.archivo` con `cache.nombre_archivo(ruta)` (normaliza a NFC).
- Un expediente real trae Alineamiento y Número Oficial en dos archivos distintos: ambos son
  TipoDocumento.ALINEAMIENTO.

Primer entregable (10:30): script que llena `cache/` con todos los documentos,
con 5-10 llamadas en paralelo como máximo para no topar el rate limit.
"""
from pathlib import Path

from ..schemas import DocumentoLeido


def leer_documento(ruta: Path) -> DocumentoLeido:
    """Lee un archivo y devuelve su texto por página, tipo y legibilidad. Usa el caché si existe."""
    raise NotImplementedError


def construir_cache(carpeta: Path) -> None:
    """Corre `leer_documento` sobre todos los archivos de la carpeta y guarda el caché."""
    raise NotImplementedError
