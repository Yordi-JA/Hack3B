import re
from pathlib import Path

from expedientes import motivos as M
from expedientes.orquestador import analizar_expediente
from expedientes.schemas import (
    DatosInmueble,
    DocumentoAnalizado,
    EstadoRegla,
    Evidencia,
    Hallazgo,
    Inconsistencia,
    Legibilidad,
    Severidad,
    TipoDocumento,
    ValorEncontrado,
)

RAIZ = Path(__file__).resolve().parent.parent
_REGLA = re.compile(r"\"((?:ESC|PRE|ALI|USO|CRU|EXP)-[A-Z0-9]+)\"")


def _doc(archivo, tipo, *hallazgos, legibilidad=Legibilidad.BUENA):
    return DocumentoAnalizado(archivo=archivo, tipo=tipo, confianza_tipo=1, legibilidad=legibilidad,
                              datos=DatosInmueble(), hallazgos=list(hallazgos), confianza=0.9)


def _h(id_regla, estado, severidad):
    return Hallazgo(id_regla=id_regla, descripcion=id_regla, estado=estado, severidad=severidad, explicacion="x")


def _dictamen(documentos, inconsistencias=(), hallazgos_expediente=()):
    base = analizar_expediente([], usar_ejemplo=True)
    return base.model_copy(update={"documentos": documentos, "inconsistencias": list(inconsistencias),
                                   "hallazgos_expediente": list(hallazgos_expediente)})


def test_toda_regla_del_codigo_tiene_categoria():
    codigo = (RAIZ / "expedientes").rglob("*.py")
    reglas = {r for f in codigo if f.name != "motivos.py" for r in _REGLA.findall(f.read_text(encoding="utf-8"))}
    sin_categoria = sorted(reglas - set(M.CATEGORIA_POR_REGLA))
    assert not sin_categoria, f"Agregar a motivos.CATEGORIA_POR_REGLA: {sin_categoria}"


def test_cada_categoria_tiene_texto():
    assert set(M.MOTIVO) == set(M.Categoria)


def test_etiquetas():
    assert M.etiqueta(M.Categoria.USO_SUELO, Severidad.BLOQUEANTE) == "Descartado por uso de suelo"
    assert M.etiqueta(M.Categoria.CLARIDAD, Severidad.REVISION) == "En revisión por falta de claridad del documento"


def test_dictamen_de_ejemplo():
    d = analizar_expediente([], usar_ejemplo=True)
    ms = M.motivos(d)
    assert ms[0].etiqueta == "Descartado por documento vencido" and ms[0].id_regla == "USO-02"
    assert ms[0].archivo == "04 Uso de Suelo DEMO.pdf"
    assert {m.categoria for m in ms} >= {M.Categoria.VIGENCIA, M.Categoria.DATOS_NO_COINCIDEN}


def test_no_se_corta_reporta_todos_los_documentos():
    d = _dictamen([
        _doc("uso.pdf", TipoDocumento.USO_SUELO,
             _h("USO-01", EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE),
             _h("USO-02", EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE)),
        _doc("pre.pdf", TipoDocumento.PREDIAL, _h("PRE-04", EstadoRegla.NO_CUMPLE, Severidad.REVISION)),
        _doc("esc.pdf", TipoDocumento.ESCRITURA, _h("ESC-ILEG", EstadoRegla.NO_EVALUABLE, Severidad.REVISION),
             legibilidad=Legibilidad.ILEGIBLE),
    ])
    ms = M.motivos(d)
    assert [(m.archivo, m.etiqueta) for m in ms] == [
        ("uso.pdf", "Descartado por uso de suelo"),
        ("uso.pdf", "Descartado por documento vencido"),
        ("pre.pdf", "En revisión por adeudos de predial"),
        ("esc.pdf", "En revisión por falta de claridad del documento"),
    ]


def test_cumple_e_info_no_son_motivo():
    d = _dictamen([_doc("esc.pdf", TipoDocumento.ESCRITURA,
                        _h("ESC-01", EstadoRegla.CUMPLE, Severidad.INFO),
                        _h("ESC-09", EstadoRegla.NO_EVALUABLE, Severidad.INFO))])
    assert M.motivos(d) == []


def test_consolida_por_tipo_como_el_dictamen():
    """Dos archivos de alineamiento: si uno cumple ALI-01, el otro no genera motivo."""
    d = _dictamen([
        _doc("ali_a.pdf", TipoDocumento.ALINEAMIENTO, _h("ALI-01", EstadoRegla.NO_EVALUABLE, Severidad.REVISION)),
        _doc("ali_b.pdf", TipoDocumento.ALINEAMIENTO, _h("ALI-01", EstadoRegla.CUMPLE, Severidad.INFO)),
    ])
    assert M.motivos(d) == []


def test_inconsistencia_lista_los_documentos_involucrados():
    ev = Evidencia(archivo="a.pdf", pagina=1, cita="x")
    inc = Inconsistencia(id_regla="CRU-PROP", campo="propietario", descripcion="El titular no coincide",
                         severidad=Severidad.REVISION,
                         valores=[ValorEncontrado(archivo="a.pdf", tipo=TipoDocumento.ESCRITURA, valor="A", evidencia=ev),
                                  ValorEncontrado(archivo="b.pdf", tipo=TipoDocumento.PREDIAL, valor="B")])
    (m,) = M.motivos(_dictamen([], [inc]))
    assert m.etiqueta == "En revisión por datos que no coinciden entre documentos"
    assert m.archivos == ["a.pdf", "b.pdf"] and m.archivo is None and m.evidencias == [ev]


def test_resumen_por_categoria():
    d = _dictamen(
        [_doc("uso.pdf", TipoDocumento.USO_SUELO,
              _h("USO-01", EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE),
              _h("USO-08", EstadoRegla.NO_CUMPLE, Severidad.REVISION))],
        hallazgos_expediente=[_h("EXP-01", EstadoRegla.NO_CUMPLE, Severidad.REVISION)],
    )
    filas = M.resumen_por_categoria(d)
    assert [(f.etiqueta, f.total) for f in filas] == [
        ("Descartado por uso de suelo", 2),
        ("En revisión por expediente incompleto", 1),
    ]
    assert filas[0].archivos == ["uso.pdf"]


def test_regla_nueva_cae_por_prefijo():
    assert M.categoria("CRU-NUEVA") == M.Categoria.DATOS_NO_COINCIDEN
    assert M.categoria("ZZZ-01") == M.Categoria.VERIFICACION_MANUAL
