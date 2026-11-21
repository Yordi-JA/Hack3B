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
import time
from dataclasses import dataclass, field
from datetime import datetime
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


RESERVADOS_WINDOWS = {
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
    *(f"COM{i}" for i in [*range(1, 10), "¹", "²", "³"]),
    *(f"LPT{i}" for i in [*range(1, 10), "¹", "²", "³"]),
}
# Mismos caracteres que Windows no acepta en un nombre; ":" y separadores se rechazan aparte.
_CARACTERES_INVALIDOS = re.compile(r'[<>"|?*\x00-\x1f]+')

LIMITE_ARCHIVOS = 20
LIMITE_BYTES = 200 * 1024 * 1024


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


@dataclass
class Subidas:
    """Resultado de preparar los archivos subidos: qué se analiza y qué se avisa."""
    validos: list[tuple[str, bytes]] = field(default_factory=list)
    omitidos: list[str] = field(default_factory=list)   # nombres que Windows no acepta
    repetidos: list[str] = field(default_factory=list)  # mismo nombre salvo mayúsculas o punto final
    exceso: Optional[str] = None                        # motivo si se pasan los límites


def preparar_subidas(archivos: list[tuple[str, bytes]]) -> Subidas:
    """Normaliza los nombres de las subidas sin cambiar el original más de lo necesario.

    Rechaza nombres reservados de Windows, limpia <>"|?* y caracteres de control, y deja un solo
    archivo por nombre comparando sin mayúsculas ni puntos o espacios finales (Windows los ignora).
    Con más de LIMITE_ARCHIVOS archivos o LIMITE_BYTES en total no deja nada para analizar.
    """
    r = Subidas()
    if len(archivos) > LIMITE_ARCHIVOS:
        r.exceso = (f"Subiste {len(archivos)} archivos; el límite es {LIMITE_ARCHIVOS} por expediente. "
                    "Quita algunos y vuelve a analizar.")
        return r
    total = sum(len(contenido) for _, contenido in archivos)
    if total > LIMITE_BYTES:
        r.exceso = (f"Los archivos suman {total / 1024 / 1024:.0f} MB; el límite es "
                    f"{LIMITE_BYTES // 1024 // 1024} MB por expediente. Quita algunos y vuelve a analizar.")
        return r
    vistos: dict[str, int] = {}
    for original, contenido in archivos:
        # Se separa a mano: en Windows, Path("a:b.pdf").name daría "b.pdf" (lee "a:" como unidad).
        base = original.replace("\\", "/").rsplit("/", 1)[-1]
        if nombre_reservado(base) or nombre_reservado(Path(base).stem):
            r.omitidos.append(original)
            continue
        limpio = _CARACTERES_INVALIDOS.sub("-", base).rstrip(" .")
        if not limpio or nombre_reservado(limpio):
            r.omitidos.append(original)
            continue
        clave = limpio.casefold()
        if clave in vistos:
            r.repetidos.append(original)
            continue
        vistos[clave] = len(r.validos)
        r.validos.append((limpio, contenido))
    return r


def id_expediente(nombre: Optional[str], ahora: Optional[datetime] = None) -> str:
    """El id lo fija la UI antes del análisis: el nombre del usuario o la fecha y hora."""
    return (nombre or "").strip() or (ahora or datetime.now()).strftime("EXP-%Y%m%d-%H%M%S")


def fijar_id(dictamen: Dictamen, expediente_id: str) -> Dictamen:
    """Si el dictamen trae otro id (un LLM con texto inyectado podría cambiarlo), se usa el de la UI;
    así un análisis nunca sobrescribe el archivo de otro expediente."""
    if dictamen.expediente_id == expediente_id:
        return dictamen
    return dictamen.model_copy(update={"expediente_id": expediente_id})


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
        _reemplazar(tmp, destino)
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


def _reemplazar(origen: str, destino: Path, intentos: int = 10) -> None:
    """os.replace con reintentos: en Windows falla con PermissionError si otra sesión está leyendo
    el archivo en ese momento."""
    for i in range(intentos):
        try:
            os.replace(origen, destino)
            return
        except PermissionError:
            if i == intentos - 1:
                raise
            time.sleep(0.1)


def _parecidos(ruta: Path) -> list[Path]:
    """Archivos de la carpeta con el mismo nombre sin distinguir mayúsculas, el exacto primero."""
    if not ruta.parent.is_dir():
        return []
    iguales = [p for p in ruta.parent.iterdir() if p.name.casefold() == ruta.name.casefold()]
    return sorted(iguales, key=lambda p: p.name != ruta.name)


def _en_disco(ruta: Path) -> Path:
    """El nombre tal como quedó en disco: el exacto si existe; si no, el que solo cambia en
    mayúsculas (NTFS y APFS no las distinguen)."""
    parecidos = _parecidos(ruta)
    return parecidos[0] if parecidos else ruta


def _destino_libre(carpeta: Path, expediente_id: str) -> Path:
    """El mismo id reusa su archivo (re-análisis). Si otro id ocupa el mismo nombre, aunque sea solo
    con otras mayúsculas, se agrega -2, -3... Así funciona igual en disco con o sin mayúsculas."""
    base = nombre_archivo(expediente_id)[: -len(".json")]
    n = 1
    while True:
        destino = carpeta / (f"{base}.json" if n == 1 else f"{base}-{n}.json")
        parecidos = _parecidos(destino)
        if not parecidos:
            return destino
        if all(_id_guardado(p) == expediente_id for p in parecidos):
            return parecidos[0]
        n += 1
