"""Ingesta: convierte cada PDF/imagen en páginas con texto (si lo trae) e imagen.

59 de los 63 PDFs de prueba son escaneos sin capa de texto, así que cada página
se rasteriza a PNG para mandarla a un modelo con visión.
"""
import base64
from dataclasses import dataclass
from pathlib import Path

import pymupdf

DPI = 150          # suficiente para leer sellos y tablas sin disparar tokens
MAX_PAGINAS = 12   # las escrituras llegan a 50 páginas; los datos clave suelen ir al inicio


@dataclass
class Pagina:
    archivo: str
    numero: int          # 1 = primera
    texto: str           # vacío si es escaneo
    png_b64: str

    @property
    def es_escaneo(self) -> bool:
        return len(self.texto.strip()) < 200


def cargar_documento(ruta: Path, max_paginas: int = MAX_PAGINAS) -> list[Pagina]:
    ruta = Path(ruta)
    doc = pymupdf.open(ruta)  # también abre .jpeg/.png
    paginas = []
    for i, pg in enumerate(doc):
        if i >= max_paginas:
            break
        png = pg.get_pixmap(dpi=DPI).tobytes("png")
        paginas.append(
            Pagina(
                archivo=ruta.name,
                numero=i + 1,
                texto=pg.get_text(),
                png_b64=base64.b64encode(png).decode(),
            )
        )
    return paginas


def listar_expediente(carpeta: Path) -> list[Path]:
    """Archivos de un expediente (una carpeta por inmueble)."""
    exts = {".pdf", ".jpeg", ".jpg", ".png"}
    return sorted(
        p for p in Path(carpeta).rglob("*")
        if p.suffix.lower() in exts and "__MACOSX" not in p.parts
    )
