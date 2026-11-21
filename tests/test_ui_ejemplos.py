"""Todo archivo en ejemplos/ debe cumplir el contrato: la bandeja los muestra como datos de ejemplo."""
import json
from pathlib import Path

import pytest

from expedientes.schemas import Dictamen, Recomendacion

EJEMPLOS = sorted((Path(__file__).resolve().parent.parent / "ejemplos").glob("*.json"))


@pytest.mark.parametrize("ruta", EJEMPLOS, ids=lambda p: p.name)
def test_ejemplo_valida_contra_dictamen(ruta):
    Dictamen.model_validate_json(ruta.read_text(encoding="utf-8"))


def test_ejemplos_cubren_cumple_y_revision_con_y_sin_posible_rechazo_con_ids_unicos():
    from ui import logica as L

    dictamenes = [Dictamen.model_validate_json(p.read_text(encoding="utf-8")) for p in EJEMPLOS]
    # el sistema no rechaza (e94a8d4): ningún ejemplo nuevo dice "No cumple"
    assert {d.recomendacion for d in dictamenes} == {Recomendacion.CUMPLE, Recomendacion.REQUIERE_REVISION}
    revision = [d for d in dictamenes if d.recomendacion == Recomendacion.REQUIERE_REVISION]
    assert {bool(L.posibles_motivos_rechazo(d)) for d in revision} == {True, False}
    ids = [d.expediente_id for d in dictamenes]
    assert len(ids) == len(set(ids))


def test_ejemplos_son_json_utf8_legible():
    for ruta in EJEMPLOS:
        json.loads(ruta.read_text(encoding="utf-8"))
