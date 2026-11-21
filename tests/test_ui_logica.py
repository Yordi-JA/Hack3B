from datetime import datetime

from expedientes.schemas import (
    Campo,
    DatosInmueble,
    Dictamen,
    DocumentoAnalizado,
    EstadoRegla,
    Hallazgo,
    Legibilidad,
    Recomendacion,
    Severidad,
    TipoDocumento,
)
from ui import componentes as C
from ui import logica as L
from ui.mapa import ConteoEntidad


def doc(archivo, tipo=TipoDocumento.PREDIAL, entidad=None, municipio=None, hallazgos=(), **campos):
    datos = DatosInmueble(
        entidad_federativa=Campo(valor=entidad, normalizado=entidad),
        municipio=Campo(valor=municipio, normalizado=municipio),
        **{k: Campo(valor=v, normalizado=v) for k, v in campos.items()},
    )
    return DocumentoAnalizado(
        archivo=archivo, tipo=tipo, confianza_tipo=0.9, legibilidad=Legibilidad.BUENA,
        datos=datos, hallazgos=list(hallazgos), confianza=0.9,
    )


def h(id_regla, estado, severidad=Severidad.INFO):
    return Hallazgo(id_regla=id_regla, descripcion=id_regla, estado=estado, severidad=severidad, explicacion="x")


def dictamen(docs, recomendacion=Recomendacion.CUMPLE, confianza=0.8, hallazgos_expediente=(), fecha=None, **extra):
    return Dictamen(
        expediente_id=extra.get("expediente_id", "EXP-T"), fecha_analisis=fecha or datetime(2026, 11, 21, 10),
        fecha_referencia="2026-11-21", documentos=docs, documentos_faltantes=[],
        hallazgos_expediente=list(hallazgos_expediente), inconsistencias=[], recomendacion=recomendacion,
        confianza=confianza, resumen="r", razones=[],
    )


# ------------------------------------------------------------------ ubicación

def test_ubicacion_por_mayoria_y_confirmada_cuando_todos_coinciden():
    d = dictamen([doc("a", entidad="HIDALGO", municipio="IXMIQUILPAN"), doc("b", entidad="Hidalgo"), doc("c")])
    u = L.consolidar_ubicacion(d)
    assert (u.entidad, u.municipio, u.confirmada) == ("HIDALGO", "IXMIQUILPAN", True)


def test_ubicacion_con_desacuerdo_queda_sin_confirmar_con_ambos_valores():
    d = dictamen([doc("a", entidad="HIDALGO"), doc("b", entidad="HIDALGO"), doc("c", entidad="Estado de México")])
    u = L.consolidar_ubicacion(d)
    assert u.entidad == "HIDALGO" and not u.confirmada
    assert u.valores == ["HIDALGO", "MEXICO"]
    assert "sin confirmar" in C.texto_ubicacion(u)


def test_ubicacion_empatada_no_elige_entidad():
    u = L.consolidar_ubicacion(dictamen([doc("a", entidad="HIDALGO"), doc("b", entidad="MEXICO")]))
    assert u.entidad is None and not u.confirmada and len(u.valores) == 2


def test_ubicacion_sin_datos():
    u = L.consolidar_ubicacion(dictamen([doc("a"), doc("b")]))
    assert u.entidad is None and u.valores == [] and u.municipio is None
    assert C.texto_ubicacion(u) == "sin entidad federativa"


# ------------------------------------------------------------------ requisitos

def test_requisito_se_cumple_si_algun_archivo_lo_cumple():
    d = dictamen([
        doc("ali1", TipoDocumento.ALINEAMIENTO, hallazgos=[h("ALI-01", EstadoRegla.NO_EVALUABLE, Severidad.REVISION)]),
        doc("ali2", TipoDocumento.ALINEAMIENTO, hallazgos=[h("ALI-01", EstadoRegla.CUMPLE)]),
    ])
    (req,) = L.consolidar_requisitos(d)
    assert req.estado == EstadoRegla.CUMPLE and req.archivos == ["ali1", "ali2"]


def test_requisitos_excluyen_avisos_de_proceso_y_ordenan_por_gravedad():
    d = dictamen(
        [doc("p", hallazgos=[
            h("PRE-01", EstadoRegla.CUMPLE),
            h("EXP-ERROR", EstadoRegla.NO_EVALUABLE, Severidad.REVISION),
            h("PRE-02", EstadoRegla.NO_CUMPLE, Severidad.REVISION),
            h("PRE-03", EstadoRegla.NO_EVALUABLE, Severidad.REVISION),
        ])],
        hallazgos_expediente=[h("EXP-01", EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE)],
    )
    ids = [r.id_regla for r in L.consolidar_requisitos(d)]
    assert ids == ["EXP-01", "PRE-02", "PRE-03", "PRE-01"]


def test_faltantes_incluye_tipos_sin_archivo_aunque_el_dictamen_los_omita():
    d = dictamen([doc("e", TipoDocumento.ESCRITURA), doc("o", TipoDocumento.OTRO)])
    assert L.faltantes(d) == [TipoDocumento.PREDIAL, TipoDocumento.ALINEAMIENTO, TipoDocumento.USO_SUELO]


# ------------------------------------------------------------------ discrepancias

def test_valores_discrepantes_marca_la_minoria_e_ignora_vacios():
    celdas = [Campo(valor="450", normalizado="450"), None, Campo(valor="432", normalizado="432"),
              Campo(valor="450 m2", normalizado="450")]
    assert L.valores_discrepantes(celdas) == {2}
    assert L.valores_discrepantes([Campo(valor="a", normalizado="A"), None]) == set()


def test_valores_inconsistencia_empate_marca_todos():
    assert L.valores_inconsistencia_discrepantes(["15", "17"]) == {0, 1}
    assert L.valores_inconsistencia_discrepantes(["15", "15", "17", None]) == {2}


def test_tabla_no_marca_fechas_distintas_como_diferencia():
    d = dictamen([doc("a", fecha_emision="2020-01-01", propietario="X"), doc("b", fecha_emision="2026-01-01", propietario="Y"),
                  doc("c", propietario="X")])
    html = C.tabla_datos(d)
    assert html.count("Difiere") == 1  # solo el propietario distinto


# ------------------------------------------------------------------ bandeja

def test_indicadores_y_conteo_por_entidad():
    a = dictamen([doc("a", entidad="HIDALGO")], Recomendacion.CUMPLE, 0.9)
    b = dictamen([doc("b", entidad="HIDALGO")], Recomendacion.NO_CUMPLE, 0.7)
    c = dictamen([doc("c")], Recomendacion.REQUIERE_REVISION, 0.8)
    ind = L.indicadores([(a, True), (b, False), (c, False)])
    assert ind.total == 3 and ind.ejemplos == 1
    assert ind.por_recomendacion[Recomendacion.NO_CUMPLE] == 1
    assert abs(ind.confianza_promedio - 0.8) < 1e-9
    conteos = L.conteo_por_entidad([a, b, c])
    assert list(conteos) == ["HIDALGO"] and conteos["HIDALGO"].total == 2
    assert conteos["HIDALGO"].peor == Recomendacion.NO_CUMPLE
    assert L.indicadores([]).confianza_promedio is None


def test_filtros_de_bandeja():
    hgo = dictamen([doc("Predial Tepeji.pdf", entidad="HIDALGO", propietario="JUAN PÉREZ")], Recomendacion.NO_CUMPLE)
    sin = dictamen([doc("x.pdf")], Recomendacion.CUMPLE)
    assert L.coincide(hgo, entidad="HIDALGO") and not L.coincide(sin, entidad="HIDALGO")
    assert L.coincide(sin, entidad=L.SIN_ENTIDAD) and not L.coincide(hgo, entidad=L.SIN_ENTIDAD)
    assert L.coincide(hgo, recomendacion=Recomendacion.NO_CUMPLE) and not L.coincide(sin, recomendacion=Recomendacion.NO_CUMPLE)
    assert L.coincide(hgo, texto="perez") and L.coincide(hgo, texto="tepeji") and not L.coincide(hgo, texto="tultepec")


def test_orden_bandeja_pone_no_cumple_primero_y_lo_reciente_arriba():
    viejo = dictamen([], Recomendacion.NO_CUMPLE, fecha=datetime(2026, 11, 20))
    nuevo = dictamen([], Recomendacion.NO_CUMPLE, fecha=datetime(2026, 11, 21))
    ok = dictamen([], Recomendacion.CUMPLE, fecha=datetime(2026, 11, 22))
    assert sorted([ok, viejo, nuevo], key=L.orden_bandeja) == [nuevo, viejo, ok]


def test_conteo_entidad_peor_vacio():
    assert ConteoEntidad().peor is None


def test_campos_clave_priorizan_lo_propio_del_tipo():
    uso = doc("u", TipoDocumento.USO_SUELO, entidad="HIDALGO", propietario="X", vigencia_hasta="2027-01-01")
    uso.datos.especificos["uso_autorizado"] = Campo(valor="COMERCIAL", normalizado="COMERCIAL")
    claves = [c for c, _ in L.campos_clave(uso)]
    assert claves[:2] == ["uso_autorizado", "vigencia_hasta"] and len(claves) == 4
