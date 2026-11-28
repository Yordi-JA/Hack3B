"""Cada valor literal de los ejemplos tiene que estar respaldado por su propia cita.

Es la misma comprobación que hace el auditor (AUD-02); evita que, al cambiar un dato de un
ejemplo, la cita quede con el valor anterior.
"""
import pytest

from expedientes.agentes.auditor import CAMPOS_VALOR_LITERAL, _valor_en
from expedientes.schemas import Dictamen
from tests.test_ui_ejemplos import EJEMPLOS


def _campos_con_cita(ruta):
    dictamen = Dictamen.model_validate_json(ruta.read_text(encoding="utf-8"))
    for doc in dictamen.documentos:
        for nombre in CAMPOS_VALOR_LITERAL:
            campo = getattr(doc.datos, nombre)
            if campo.evidencia:
                yield doc.archivo, nombre, campo


@pytest.mark.parametrize("ruta", EJEMPLOS, ids=lambda p: p.name)
def test_valor_literal_aparece_en_su_cita(ruta):
    huerfanos = [
        f"{archivo}: {nombre}={campo.valor!r} no está en la cita {campo.evidencia.cita!r}"
        for archivo, nombre, campo in _campos_con_cita(ruta)
        if not _valor_en(nombre, campo.valor, campo.evidencia.cita)
    ]
    assert not huerfanos, "\n".join(huerfanos)
