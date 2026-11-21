from expedientes.orquestador import analizar_expediente
from expedientes.schemas import Recomendacion


def test_ejemplo_cumple_el_contrato():
    d = analizar_expediente([], usar_ejemplo=True)
    assert d.recomendacion == Recomendacion.NO_CUMPLE
    assert len(d.documentos) == 4
    assert d.todos_los_hallazgos()
