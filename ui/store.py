"""Persistencia de dictámenes en disco.

- `resultados/<id>.json`: análisis reales (en .gitignore: contienen datos de los documentos, regla 06).
- `ejemplos/*.json`: dictámenes inventados que se muestran con la marca "Ejemplo".
Un archivo dañado o que no cumple el contrato no tumba la bandeja: se reporta aparte.
"""
from __future__ import annotations

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


def nombre_archivo(expediente_id: str) -> str:
    """Nombre de archivo seguro en Windows y macOS para un id libre escrito por el usuario."""
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", expediente_id).strip(" .-")
    return (limpio or "expediente")[:120] + ".json"


def _leer(ruta: Path, origen: Origen) -> Entrada | ArchivoInvalido:
    try:
        dictamen = Dictamen.model_validate_json(ruta.read_text(encoding="utf-8"))
    except ValidationError as e:
        return ArchivoInvalido(ruta, f"no cumple el contrato Dictamen ({e.error_count()} errores)")
    except (OSError, UnicodeDecodeError) as e:
        return ArchivoInvalido(ruta, f"no se pudo leer ({type(e).__name__})")
    return Entrada(f"{origen}:{ruta.stem}", origen, ruta, dictamen)


def cargar(
    dir_resultados: Path = DIR_RESULTADOS, dir_ejemplos: Path = DIR_EJEMPLOS
) -> tuple[list[Entrada], list[ArchivoInvalido]]:
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


def guardar(dictamen: Dictamen, dir_resultados: Path = DIR_RESULTADOS) -> Entrada:
    """Escribe `resultados/<id>.json`. Si ya existe un expediente con ese id, lo reemplaza.

    Se escribe a un temporal y luego se renombra, para que la bandeja nunca lea un archivo a medias.
    """
    dir_resultados.mkdir(parents=True, exist_ok=True)
    destino = dir_resultados / nombre_archivo(dictamen.expediente_id)
    fd, tmp = tempfile.mkstemp(dir=dir_resultados, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(dictamen.model_dump_json(indent=2))
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return Entrada(f"resultado:{destino.stem}", "resultado", destino, dictamen)
