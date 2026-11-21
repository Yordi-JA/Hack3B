"""Caché del texto leído: `cache/<archivo>.json` con un DocumentoLeido.

El OCR de las 249 páginas se corre una sola vez (Julián) y el resto del equipo trabaja
contra el caché. La carpeta está en .gitignore: se comparte por USB/Drive dentro del equipo,
nunca por el repo (regla 06).

La llave es el nombre original del archivo normalizado a NFC: varios nombres del zip vienen
en NFD (macOS) y el navegador los manda en NFC. Usar `nombre_archivo()` también al llenar
`DocumentoLeido.archivo`.
"""
import os
import unicodedata
from pathlib import Path
from typing import Optional

from .config import CACHE_DIR
from .schemas import DocumentoLeido


def nombre_archivo(ruta) -> str:
    return unicodedata.normalize("NFC", Path(ruta).name)


def ruta_cache(archivo: str) -> Path:
    return CACHE_DIR / f"{nombre_archivo(archivo)}.json"


def leer_cache(archivo: str) -> Optional[DocumentoLeido]:
    p = ruta_cache(archivo)
    if not p.exists():
        return None
    return DocumentoLeido.model_validate_json(p.read_text(encoding="utf-8"))


def guardar_cache(doc: DocumentoLeido) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = ruta_cache(doc.archivo)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, p)  # atómico: un Ctrl-C no deja JSON truncado
    return p
