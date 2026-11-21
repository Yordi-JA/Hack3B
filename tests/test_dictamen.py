"""Pruebas del dictaminador. Es determinista: no usa LLM."""
from datetime import date

from expedientes.agentes import dictamen as dt
from expedientes.schemas import (
    Contexto,
    DatosInmueble,
    DocumentoAnalizado,
    EstadoRegla,
    Hallazgo,
    Inconsistencia,
    Legibilidad,
    Recomendacion,
    Severidad,
    TipoDocumento,
    ValorEncontrado,
)

T, E, S = TipoDocumento, EstadoRegla, Severidad
CTX = Contexto(fecha_referencia=date(2026, 11, 21))
TODOS = [T.ESCRITURA, T.PREDIAL, T.ALINEAMIENTO, T.USO_SUELO]


def _h(id_regla, estado=E.CUMPLE, severidad=S.INFO):
    return Hallazgo(id_regla=id_regla, descripcion=f"Regla {id_regla}", estado=estado,
                    severidad=severidad, explicacion=f"Explicación de {id_regla}.")


def _doc(tipo, *hallazgos, archivo=None, legibilidad=Legibilidad.BUENA, confianza=0.9):
    return DocumentoAnalizado(archivo=archivo or f"{tipo.value}.pdf", tipo=tipo, confianza_tipo=0.95,
                              legibilidad=legibilidad, datos=DatosInmueble(), hallazgos=list(hallazgos),
                              confianza=confianza)


def _expediente(*extra):
    return [_doc(t, _h(f"{t.value[:3].upper()}-01")) for t in TODOS] + list(extra)


def _dictaminar(docs, faltantes=(), inconsistencias=()):
    return dt.dictaminar("EXP-T", docs, list(faltantes), list(inconsistencias), CTX)


def test_todo_cumple():
    d = _dictaminar(_expediente())
    assert d.recomendacion == Recomendacion.CUMPLE
    assert d.hallazgos_expediente[0].estado == E.CUMPLE
    assert d.confianza == 0.9


def test_un_bloqueante_pide_revision_y_no_rechaza():
    """Criterio del equipo: solo la abogada rechaza. Un bloqueante queda primero como posible motivo."""
    docs = _expediente(_doc(T.USO_SUELO, _h("USO-02", E.NO_CUMPLE, S.BLOQUEANTE), archivo="uso2.pdf"))
    d = _dictaminar(docs)
    assert d.recomendacion == Recomendacion.REQUIERE_REVISION
    assert "posible motivo de rechazo" in d.razones[0]
    assert "La decisión de rechazar es del equipo legal" in d.resumen


def test_rechazo_automatico_solo_si_se_habilita(monkeypatch):
    monkeypatch.setattr(dt, "PERMITIR_RECHAZO_AUTOMATICO", True)
    docs = _expediente(_doc(T.USO_SUELO, _h("USO-02", E.NO_CUMPLE, S.BLOQUEANTE), archivo="uso2.pdf"))
    d = _dictaminar(docs)
    assert d.recomendacion == Recomendacion.NO_CUMPLE and "bloqueante" in d.razones[0]


def test_el_sistema_nunca_recomienda_no_cumple():
    docs = _expediente(_doc(T.USO_SUELO, _h("USO-01", E.NO_CUMPLE, S.BLOQUEANTE), _h("USO-02", E.NO_CUMPLE, S.BLOQUEANTE),
                            archivo="uso2.pdf"))
    assert _dictaminar(docs, faltantes=[T.PREDIAL]).recomendacion != Recomendacion.NO_CUMPLE


def test_revision_y_faltante_piden_revision():
    docs = [_doc(T.ESCRITURA, _h("ESC-06", E.NO_EVALUABLE, S.REVISION)), _doc(T.PREDIAL)]
    d = _dictaminar(docs, faltantes=[T.ALINEAMIENTO, T.USO_SUELO])
    assert d.recomendacion == Recomendacion.REQUIERE_REVISION
    exp01 = d.hallazgos_expediente[0]
    assert exp01.estado == E.NO_CUMPLE and "Uso de Suelo" in exp01.explicacion
    assert d.confianza == round(0.9 - 2 * dt.PENALIZACION_FALTANTE, 2)


def test_consolida_por_tipo_alineamiento_en_dos_archivos():
    """Número oficial en un archivo y alineamiento en otro: ninguno solo cumple todo."""
    solo_alin = _doc(T.ALINEAMIENTO, _h("ALI-01", E.NO_EVALUABLE, S.REVISION), _h("ALI-04"), archivo="alin.pdf")
    solo_num = _doc(T.ALINEAMIENTO, _h("ALI-01"), _h("ALI-04", E.NO_EVALUABLE, S.REVISION), archivo="num.pdf")
    docs = [d for d in _expediente() if d.tipo != T.ALINEAMIENTO] + [solo_alin, solo_num]
    assert _dictaminar(docs).recomendacion == Recomendacion.CUMPLE


def test_bloqueante_de_un_archivo_no_lo_tapa_otro_tipo():
    docs = _expediente(_doc(T.PREDIAL, _h("USO-02"), archivo="otro.pdf"),
                       _doc(T.USO_SUELO, _h("USO-02", E.NO_CUMPLE, S.BLOQUEANTE), archivo="uso2.pdf"))
    assert _dictaminar(docs).recomendacion == Recomendacion.REQUIERE_REVISION  # el bloqueante no se pierde


def test_ilegible_genera_exp02():
    docs = _expediente(_doc(T.USO_SUELO, archivo="borroso.pdf", legibilidad=Legibilidad.ILEGIBLE, confianza=0))
    d = _dictaminar(docs)
    assert any(h.id_regla == "EXP-02" and "borroso.pdf" in h.explicacion for h in d.hallazgos_expediente)
    assert d.recomendacion == Recomendacion.REQUIERE_REVISION


def _inc(campo, valores, id_regla="CRU-X"):
    return Inconsistencia(id_regla=id_regla, campo=campo, descripcion=f"{campo} no coincide.",
                          severidad=S.REVISION,
                          valores=[ValorEncontrado(archivo=f"{t.value}.pdf", tipo=t, valor=v) for t, v in valores])


def test_matriz_propietario_escritura_predial():
    inc = _inc("propietario", [(T.ESCRITURA, "ANA LOPEZ"), (T.PREDIAL, "JUAN PEREZ")])
    d = _dictaminar(_expediente(), inconsistencias=[inc])
    assert d.recomendacion == Recomendacion.REQUIERE_REVISION
    assert "Revisión legal requerida" in d.razones[0]


def test_matriz_superficie_escritura_alineamiento():
    mucha = _inc("superficie_terreno_m2", [(T.ESCRITURA, "450.00"), (T.ALINEAMIENTO, "400.00")])
    poca = _inc("superficie_terreno_m2", [(T.ESCRITURA, "450.00"), (T.ALINEAMIENTO, "440.00")])
    assert "levantamiento topográfico" in dt.accion_inconsistencia(mucha)
    assert dt.accion_inconsistencia(poca) is None


def test_matriz_direccion_uso_suelo_alineamiento():
    inc = _inc("direccion", [(T.USO_SUELO, "CALLE ROBLE 12"), (T.ALINEAMIENTO, "CALLE PINO 3")])
    assert "uso de suelo" in dt.accion_inconsistencia(inc)


def test_razones_acotadas():
    docs = _expediente(*[_doc(T.PREDIAL, _h(f"PRE-{i:02d}", E.NO_CUMPLE, S.REVISION), archivo=f"p{i}.pdf")
                         for i in range(12)])
    d = _dictaminar(docs)
    assert len(d.razones) == dt.MAX_RAZONES and d.razones[-1].startswith("Y ")


def test_sin_datos_no_dice_que_coinciden():
    d = _dictaminar(_expediente())  # documentos sin datos extraídos
    assert "No hubo suficientes datos" in d.resumen and "coinciden" not in d.resumen
