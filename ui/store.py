"""Persistencia de dictámenes en disco.

- `resultados/<id>.json`: análisis reales (en .gitignore: contienen datos de los documentos, regla 06).
- `ejemplos/*.json`: dictámenes inventados que se muestran con la marca "Ejemplo".
Un archivo dañado o que no cumple el contrato no tumba la bandeja: se reporta aparte.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from pydantic import ValidationError

from expedientes.schemas import Dictamen

RAIZ = Path(__file__).resolve().parent.parent
DIR_RESULTADOS = RAIZ / "resultados"
DIR_EJEMPLOS = RAIZ / "ejemplos"

Origen = Literal["resultado", "ejemplo"]


@dataclass
class Entrada:
    clave: str  # estable y apta para URL: "<origen>:<nombre de archivo sin .json>"
    origen: Origen
    ruta: Path
    dictamen: Dictamen

    @property
    def es_ejemplo(self) -> bool:
        return self.origen == "ejemplo"


@dataclass
class ArchivoInvalido:
    ruta: Path
    motivo: str


RESERVADOS_WINDOWS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def nombre_reservado(nombre: str) -> bool:
    """Nombres que Windows no deja crear o que apuntan a otro lugar: vacío, '.', '..', con ':'
    (flujos alternos de NTFS) o separadores de ruta, o con raíz reservada (CON, NUL, COM1...)."""
    nombre = nombre.strip()
    if nombre in ("", ".", "..") or any(c in nombre for c in ':/\\'):
        return True
    return nombre.split(".")[0].strip().upper() in RESERVADOS_WINDOWS


def nombre_archivo(expediente_id: str) -> str:
    """Nombre de archivo seguro en Windows y macOS para un id libre escrito por el usuario."""
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", expediente_id).strip(" .-")[:120]
    if not limpio or nombre_reservado(limpio):
        limpio = "expediente"
    return limpio + ".json"


def _leer(ruta: Path, origen: Origen) -> Entrada | ArchivoInvalido:
    try:
        dictamen = Dictamen.model_validate_json(ruta.read_text(encoding="utf-8"))
    except ValidationError as e:
        return ArchivoInvalido(ruta, f"no cumple el contrato Dictamen ({e.error_count()} errores)")
    except (OSError, UnicodeDecodeError) as e:
        return ArchivoInvalido(ruta, f"no se pudo leer ({type(e).__name__})")
    return Entrada(f"{origen}:{ruta.stem}", origen, ruta, dictamen)


def cargar(
    dir_resultados: Optional[Path] = None, dir_ejemplos: Optional[Path] = None
) -> tuple[list[Entrada], list[ArchivoInvalido]]:
    dir_resultados = dir_resultados or DIR_RESULTADOS
    dir_ejemplos = dir_ejemplos or DIR_EJEMPLOS
    entradas: list[Entrada] = []
    invalidos: list[ArchivoInvalido] = []
    for carpeta, origen in ((dir_resultados, "resultado"), (dir_ejemplos, "ejemplo")):
        if not carpeta.is_dir():
            continue
        for ruta in sorted(carpeta.glob("*.json")):
            leido = _leer(ruta, origen)
            (entradas if isinstance(leido, Entrada) else invalidos).append(leido)
    return entradas, invalidos


def buscar(entradas: list[Entrada], clave: Optional[str]) -> Optional[Entrada]:
    return next((e for e in entradas if e.clave == clave), None)


def guardar(dictamen: Dictamen, dir_resultados: Optional[Path] = None) -> Entrada:
    """Escribe `resultados/<id>.json`. Si ya existe un expediente con ese id, lo reemplaza; si el
    nombre lo ocupa otro expediente, usa `<id>-2.json`, `-3`...

    Se escribe a un temporal y luego se renombra, para que la bandeja nunca lea un archivo a medias.
    """
    dir_resultados = dir_resultados or DIR_RESULTADOS
    dir_resultados.mkdir(parents=True, exist_ok=True)
    destino = _destino_libre(dir_resultados, dictamen.expediente_id)
    fd, tmp = tempfile.mkstemp(dir=dir_resultados, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(dictamen.model_dump_json(indent=2))
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    real = _en_disco(destino)
    return Entrada(f"resultado:{real.stem}", "resultado", real, dictamen)


def _id_guardado(ruta: Path) -> Optional[str]:
    try:
        return json.loads(ruta.read_text(encoding="utf-8")).get("expediente_id")
    except (OSError, ValueError, AttributeError):
        return None


def _en_disco(ruta: Path) -> Path:
    """El nombre tal como quedó en disco (NTFS y APFS no distinguen mayúsculas)."""
    return next((p for p in ruta.parent.iterdir() if p.name.lower() == ruta.name.lower()), ruta)


def _destino_libre(carpeta: Path, expediente_id: str) -> Path:
    """El mismo id reusa su archivo (re-análisis). Si otro id cae en el mismo nombre, por la limpieza
    de caracteres o por mayúsculas, se agrega -2, -3..."""
    base = nombre_archivo(expediente_id)[: -len(".json")]
    n = 1
    while True:
        destino = carpeta / (f"{base}.json" if n == 1 else f"{base}-{n}.json")
        if not destino.exists() or _id_guardado(_en_disco(destino)) == expediente_id:
            return destino
        n += 1
