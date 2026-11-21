"""Todo archivo en ejemplos/ debe cumplir el contrato: la bandeja los muestra como datos de ejemplo."""
import json
from pathlib import Path

import pytest

from expedientes.schemas import Dictamen, Recomendacion

EJEMPLOS = sorted((Path(__file__).resolve().parent.parent / "ejemplos").glob("*.json"))


@pytest.mark.parametrize("ruta", EJEMPLOS, ids=lambda p: p.name)
def test_ejemplo_valida_contra_dictamen(ruta):
    Dictamen.model_validate_json(ruta.read_text(encoding="utf-8"))


def test_ejemplos_cubren_las_tres_recomendaciones_con_ids_unicos():
    dictamenes = [Dictamen.model_validate_json(p.read_text(encoding="utf-8")) for p in EJEMPLOS]
    assert {d.recomendacion for d in dictamenes} == set(Recomendacion)
    ids = [d.expediente_id for d in dictamenes]
    assert len(ids) == len(set(ids))


def test_ejemplos_son_json_utf8_legible():
    for ruta in EJEMPLOS:
        json.loads(ruta.read_text(encoding="utf-8"))
