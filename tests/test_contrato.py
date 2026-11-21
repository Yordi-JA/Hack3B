from expedientes.orquestador import analizar_expediente
from expedientes.schemas import Recomendacion


def test_ejemplo_cumple_el_contrato():
    d = analizar_expediente([], usar_ejemplo=True)
    assert d.recomendacion == Recomendacion.REQUIERE_REVISION  # el sistema no rechaza (e94a8d4)
    assert len(d.documentos) == 4
    assert d.todos_los_hallazgos()
