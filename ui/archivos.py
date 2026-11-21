"""Archivos originales de cada expediente, para abrirlos desde el detalle.

Al analizar, las subidas se copian a `resultados/archivos/<expediente>/` (carpeta fuera del repo,
regla 06). Si un archivo no está ahí (expedientes analizados antes de este cambio o desde la línea
de comandos), se busca por nombre en `Documentos/`. Las páginas se muestran como imágenes con
PyMuPDF: no dependen del visor de PDF del navegador ni salen del equipo.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from .store import DIR_RESULTADOS, RAIZ, nombre_archivo

DIR_ARCHIVOS = DIR_RESULTADOS / "archivos"
DIR_DOCUMENTOS = RAIZ / "Documentos"
EXTENSIONES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
LIMITE_PAGINAS = 60


def carpeta(expediente_id: str, base: Optional[Path] = None) -> Path:
    return (base or DIR_ARCHIVOS) / Path(nombre_archivo(expediente_id)).stem


def guardar_originales(expediente_id: str, archivos: list[tuple[str, bytes]], base: Optional[Path] = None) -> None:
    destino = carpeta(expediente_id, base)
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, contenido in archivos:
        (destino / Path(nombre).name).write_bytes(contenido)


@lru_cache(maxsize=1)
def _indice_documentos(raiz: Path) -> dict[str, Path]:
    if not raiz.is_dir():
        return {}
    return {p.name: p for p in sorted(raiz.rglob("*")) if p.is_file() and p.suffix.lower() in EXTENSIONES}


def ubicar(
    expediente_id: str, archivo: str, base: Optional[Path] = None, documentos: Optional[Path] = None,
) -> Optional[Path]:
    """Ruta del original o None. Solo el nombre cuenta: nada de rutas ni `..` que salgan de las carpetas."""
    nombre = Path(archivo or "").name
    if not nombre or Path(nombre).suffix.lower() not in EXTENSIONES:
        return None
    propio = carpeta(expediente_id, base) / nombre
    if propio.is_file():
        return propio
    return _indice_documentos((documentos or DIR_DOCUMENTOS).resolve()).get(nombre)


def paginas_jpg(ruta: Path, zoom: float = 1.6, limite: int = LIMITE_PAGINAS) -> tuple[list[bytes], int]:
    """Cada página como JPG y el total de páginas (se dibujan hasta `limite`)."""
    import pymupdf

    with pymupdf.open(ruta) as doc:
        total = doc.page_count
        imagenes = [
            doc[i].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("jpg", jpg_quality=80)
            for i in range(min(total, limite))
        ]
    return imagenes, total
