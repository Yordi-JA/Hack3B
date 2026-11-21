"""Caché del texto leído: `cache/<archivo>.<huella>.json` con un DocumentoLeido.

El OCR de las 249 páginas se corre una sola vez (Julián) y el resto del equipo trabaja
contra el caché. La carpeta está en .gitignore: se comparte por USB/Drive dentro del equipo,
nunca por el repo (regla 06).

Llave = nombre del archivo (NFC) + huella del CONTENIDO (sha256, 12 caracteres). Solo el nombre
no basta: en producción dos expedientes distintos suben "Predial.pdf" y el segundo recibiría el
texto del primero sin ningún error. Varios nombres del zip vienen en NFD (macOS) y el navegador
los manda en NFC: usar `nombre_archivo()` también al llenar `DocumentoLeido.archivo`.

Formas de buscar:
- Con una ruta que existe (orquestador, UI): llave exacta por contenido.
- Solo con el nombre (scripts de desarrollo: probar_*.py, evaluar_alineamiento.py): la entrada
  más reciente con ese nombre. Solo para desarrollo contra el set del reto.

Caché del formato anterior (`cache/<archivo>.json`, sin huella): se migra solo, pero únicamente
para archivos dentro de Documentos/, donde los 63 nombres son únicos. Un archivo subido desde
la UI nunca usa una entrada sin huella.
"""
from __future__ import annotations

import glob
import hashlib
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .config import CACHE_DIR, DOCUMENTOS_DIR
from .schemas import DocumentoLeido

DIR_PAGINAS = CACHE_DIR / "_paginas"
_LARGO_HUELLA = 12


def nombre_archivo(ruta) -> str:
    return unicodedata.normalize("NFC", Path(ruta).name)


@lru_cache(maxsize=512)
def _huella_cacheada(ruta: str, mtime_ns: int, tamano: int) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()[:_LARGO_HUELLA]


def huella(ruta) -> str:
    """sha256 del contenido (12 caracteres). Se recalcula solo si el archivo cambia."""
    st = os.stat(ruta)
    return _huella_cacheada(str(Path(ruta).resolve()), st.st_mtime_ns, st.st_size)


def llave(ruta) -> str:
    """'<nombre>.<huella>': identifica un documento por nombre Y contenido. `ruta` debe existir."""
    return f"{nombre_archivo(ruta)}.{huella(ruta)}"


def ruta_paginas(ruta) -> Path:
    """Carpeta de checkpoints por página de un documento (ingesta)."""
    return DIR_PAGINAS / llave(ruta)


def _por_nombre(nombre: str) -> Optional[Path]:
    """Entrada más reciente con huella para ese nombre (búsqueda de desarrollo)."""
    patron = re.compile(re.escape(nombre) + r"\.[0-9a-f]{%d}\.json" % _LARGO_HUELLA)
    candidatos = [p for p in Path(CACHE_DIR).glob(glob.escape(nombre) + ".*.json") if patron.fullmatch(p.name)]
    return max(candidatos, key=lambda p: p.stat().st_mtime) if candidatos else None


def ruta_cache(archivo) -> Path:
    """Ruta del JSON en caché. Con una ruta existente usa la huella; con solo un nombre, ver arriba."""
    if Path(archivo).is_file():
        return Path(CACHE_DIR) / f"{llave(archivo)}.json"
    nombre = nombre_archivo(archivo)
    return _por_nombre(nombre) or Path(CACHE_DIR) / f"{nombre}.json"


def _en_documentos(ruta: Path) -> bool:
    try:
        Path(ruta).resolve().relative_to(Path(DOCUMENTOS_DIR).resolve())
        return True
    except ValueError:
        return False


def _migrar_uno(ruta: Path) -> bool:
    """Pasa la entrada sin huella de un documento de Documentos/ al formato nuevo."""
    nombre = nombre_archivo(ruta)
    viejo = Path(CACHE_DIR) / f"{nombre}.json"
    nuevo = Path(CACHE_DIR) / f"{llave(ruta)}.json"
    if not viejo.exists() or nuevo.exists():
        return False
    os.replace(viejo, nuevo)
    paginas_viejas, paginas_nuevas = Path(DIR_PAGINAS) / nombre, ruta_paginas(ruta)
    if paginas_viejas.is_dir() and not paginas_nuevas.exists():
        os.replace(paginas_viejas, paginas_nuevas)
    return True


def migrar_legado() -> int:
    """Migra todas las entradas sin huella de los documentos de Documentos/. Devuelve cuántas."""
    if not Path(DOCUMENTOS_DIR).is_dir():
        return 0
    return sum(_migrar_uno(p) for p in Path(DOCUMENTOS_DIR).rglob("*")
               if p.is_file() and "__MACOSX" not in p.parts and not p.name.startswith("."))


def _es_solo_nombre(archivo) -> bool:
    return Path(str(archivo)).name == str(archivo)


def leer_cache(archivo) -> Optional[DocumentoLeido]:
    if not Path(archivo).is_file() and not _es_solo_nombre(archivo):
        return None  # ruta que no existe: no se adivina por nombre (podría ser otro inmueble)
    p = ruta_cache(archivo)
    if not p.exists() and Path(archivo).is_file() and _en_documentos(Path(archivo)) and _migrar_uno(Path(archivo)):
        p = ruta_cache(archivo)
    if not p.exists():
        return None
    return DocumentoLeido.model_validate_json(p.read_text(encoding="utf-8"))


def guardar_cache(doc: DocumentoLeido, ruta=None) -> Path:
    """Guarda el DocumentoLeido. Pasar siempre `ruta` (el archivo original) para usar la huella;
    sin ella se guarda con el formato anterior, solo por nombre."""
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
    p = Path(CACHE_DIR) / f"{llave(ruta)}.json" if ruta is not None else Path(CACHE_DIR) / f"{nombre_archivo(doc.archivo)}.json"
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, p)  # atómico: un Ctrl-C no deja JSON truncado
    return p
