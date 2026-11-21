"""Decisión de la abogada sobre cada expediente: Aprobado, En revisión o Rechazado, siempre con
un comentario que explica el porqué.

Es independiente de la recomendación del sistema (Cumple / Requiere revisión / No cumple): el
sistema sugiere, la persona decide. Se guarda en `resultados/decisiones.json` (carpeta fuera del
repo, regla 06) con el historial completo; la última decisión es el estatus vigente.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from . import tokens as t
from .store import ARCHIVO_DECISIONES, DIR_RESULTADOS

ARCHIVO = ARCHIVO_DECISIONES
LIMITE_COMENTARIO = 2000


class Estatus(str, Enum):
    SIN_REVISAR = "Sin revisar"
    APROBADO = "Aprobado"
    EN_REVISION = "En revisión"
    RECHAZADO = "Rechazado"


# Lo que puede elegir la persona (Sin revisar es solo el estado inicial).
ELEGIBLES = (Estatus.APROBADO, Estatus.EN_REVISION, Estatus.RECHAZADO)

TONO: dict[Estatus, t.Tono] = {
    Estatus.SIN_REVISAR: t.GRIS,
    Estatus.APROBADO: t.VERDE,
    Estatus.EN_REVISION: t.AMBAR,
    Estatus.RECHAZADO: t.VINO,
}


@dataclass(frozen=True)
class Decision:
    estatus: Estatus
    comentario: str
    usuario: str
    fecha: str  # ISO, hora local

    @property
    def cuando(self) -> datetime:
        return datetime.fromisoformat(self.fecha)


def _ruta(carpeta: Optional[Path]) -> Path:
    return (carpeta or DIR_RESULTADOS) / ARCHIVO


def cargar(carpeta: Optional[Path] = None) -> dict[str, list[Decision]]:
    """Historial por clave de expediente. Un archivo dañado o ausente equivale a "sin decisiones"."""
    try:
        crudo = json.loads(_ruta(carpeta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    salida: dict[str, list[Decision]] = {}
    if not isinstance(crudo, dict):
        return {}
    for clave, lista in crudo.items():
        hist = []
        for x in lista if isinstance(lista, list) else []:
            try:
                hist.append(Decision(Estatus(x["estatus"]), str(x["comentario"]), str(x["usuario"]), str(x["fecha"])))
            except (KeyError, TypeError, ValueError):
                continue
        if hist:
            salida[str(clave)] = hist
    return salida


def vigente(historial: dict[str, list[Decision]], clave: str) -> Optional[Decision]:
    hist = historial.get(clave)
    return hist[-1] if hist else None


def estatus(historial: dict[str, list[Decision]], clave: str) -> Estatus:
    d = vigente(historial, clave)
    return d.estatus if d else Estatus.SIN_REVISAR


def registrar(
    clave: str, estatus_nuevo: Estatus, comentario: str, usuario: str,
    carpeta: Optional[Path] = None, ahora: Optional[datetime] = None,
) -> Decision:
    """Agrega una decisión al historial. El comentario es obligatorio: explica el porqué."""
    if estatus_nuevo not in ELEGIBLES:
        raise ValueError("Elige Aprobado, En revisión o Rechazado.")
    comentario = (comentario or "").strip()
    if not comentario:
        raise ValueError("Escribe un comentario que explique la decisión.")
    if len(comentario) > LIMITE_COMENTARIO:
        raise ValueError(f"El comentario no puede pasar de {LIMITE_COMENTARIO} caracteres.")
    nueva = Decision(estatus_nuevo, comentario, usuario, (ahora or datetime.now()).isoformat(timespec="seconds"))
    historial = cargar(carpeta)
    historial.setdefault(clave, []).append(nueva)
    ruta = _ruta(carpeta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = {k: [dict(asdict(d), estatus=d.estatus.value) for d in v] for k, v in historial.items()}
    # Escritura atómica: si algo falla a medias, el archivo anterior queda intacto.
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".decisiones-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=1)
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return nueva
