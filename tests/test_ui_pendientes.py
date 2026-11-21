"""La lista "Qué hay que resolver" del detalle: una sola, priorizada y sin duplicados."""
from pathlib import Path

from expedientes.schemas import Dictamen, EstadoRegla, Hallazgo, Severidad, TipoDocumento
from ui import componentes as C
from ui import logica as L

EJEMPLOS = Path(__file__).resolve().parent.parent / "ejemplos"


def _demo(nombre: str) -> Dictamen:
    return Dictamen.model_validate_json((EJEMPLOS / f"{nombre}.json").read_text(encoding="utf-8"))


def test_cumple_no_tiene_pendientes_y_conserva_las_razones():
    d = _demo("dictamen_demo_02")
    items, sueltas = L.pendientes(d)
    assert items == []
    assert sueltas == d.razones  # positivas: no se pierden, van como notas
    html = C.lista_pendientes(d)
    assert "No hay pendientes: todos los requisitos evaluados se cumplen." in html
    assert "Otras notas del dictamen" in html
    assert "Sin pendientes" in C.tarjeta_dictamen(d, True)


def test_orden_bloqueante_luego_revision():
    items, _ = L.pendientes(_demo("dictamen_demo_04"))
    rangos = [{Severidad.BLOQUEANTE: 0, Severidad.REVISION: 1}.get(it.severidad, 2) for it in items]
    assert rangos == sorted(rangos) and rangos[0] == 0


def test_faltante_aparece_una_sola_vez():
    d = _demo("dictamen_demo_04")  # falta Uso de Suelo: lo dicen la razón 1 y EXP-01
    items, sueltas = L.pendientes(d)
    menciones = [it for it in items if "Uso de Suelo" in it.texto]
    assert len(menciones) == 1 and menciones[0].severidad == Severidad.BLOQUEANTE
    assert not [it for it in items if it.clase == "faltante"]
    assert sueltas == []  # todas las razones quedan cubiertas


def test_archivo_sin_analizar_es_un_renglon():
    items, _ = L.pendientes(_demo("dictamen_demo_04"))
    fila = [it for it in items if it.clase == "sin_analizar"]
    assert len(fila) == 1 and fila[0].archivos == ["Predial Tultepec 2024 DEMO.pdf"]


def test_regla_que_repite_una_inconsistencia_se_une_a_ella():
    items, _ = L.pendientes(_demo("dictamen_demo_04"))
    assert not [it for it in items if it.requisito and it.requisito.id_regla == "ALI-01"]
    numero = next(it for it in items if it.inconsistencia and it.inconsistencia.campo == "numero_oficial")
    assert [r.id_regla for r in numero.relacionados] == ["ALI-01"]


def test_archivo_ilegible_no_repite_sus_reglas_sin_evaluar():
    d = _demo("dictamen_demo_03")
    items, sueltas = L.pendientes(d)
    ids = [it.requisito.id_regla for it in items if it.requisito]
    assert not {"ALI-01", "ALI-02", "ALI-03"} & set(ids)  # las cubre EXP-02 (alineamiento ilegible)
    assert "EXP-02" in ids
    assert [it.clase for it in items].count("no_reconocido") == 1  # el croquis
    assert sueltas == []


def test_faltante_sin_regla_del_expediente_agrega_renglon():
    d = _demo("dictamen_ejemplo")
    d.documentos = [doc for doc in d.documentos if doc.tipo != TipoDocumento.PREDIAL]
    d.documentos_faltantes = [TipoDocumento.PREDIAL]
    items, _ = L.pendientes(d)
    faltan = [it for it in items if it.clase == "faltante"]
    assert len(faltan) == 1 and faltan[0].texto == "Falta Predial: no se recibió ningún archivo."


def test_razon_sin_renglon_se_conserva_como_nota():
    d = _demo("dictamen_ejemplo")
    d.razones.append("Texto que no corresponde a ningún hallazgo zzzz qqqq")
    _, sueltas = L.pendientes(d)
    assert "Texto que no corresponde a ningún hallazgo zzzz qqqq" in sueltas


def test_requisito_informativo_sin_evaluar_no_es_pendiente():
    d = _demo("dictamen_demo_02")
    d.documentos[0].hallazgos.append(Hallazgo(
        id_regla="ESC-99", descripcion="Dato opcional", estado=EstadoRegla.NO_EVALUABLE,
        severidad=Severidad.INFO, explicacion="No viene."))
    assert L.pendientes(d)[0] == []


def test_detalle_sin_etiquetas():
    for nombre in ("dictamen_ejemplo", "dictamen_demo_02", "dictamen_demo_03", "dictamen_demo_04"):
        d = _demo(nombre)
        for html in (C.lista_pendientes(d), C.documentos(d), C.detalle_completo(d), C.tarjeta_dictamen(d, True)):
            assert 'class="etq' not in html and "Difiere" not in html


def test_primera_oracion():
    assert L.primera_oracion("La licencia venció el 10/02/2025. Hay que tramitar otra.") == "La licencia venció el 10/02/2025."
    assert L.primera_oracion("Sin punto final") == "Sin punto final"
