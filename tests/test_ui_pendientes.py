"""La lista "Qué hay que resolver" del detalle: una sola, priorizada y sin duplicados."""
from pathlib import Path

from expedientes.schemas import (
    DatosInmueble,
    Dictamen,
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
    assert sueltas == d.razones  # ninguna es idéntica a un renglón: se muestran todas como notas


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
    assert sueltas == d.razones


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


def test_primera_oracion_no_corta_en_abreviaturas():
    casos = {
        "Ubicado en Av. Juárez 15, Col. Centro, Mpio. de Tula, Edo. de Hidalgo. Lo demás.":
            "Ubicado en Av. Juárez 15, Col. Centro, Mpio. de Tula, Edo. de Hidalgo.",
        "Escritura No. Cuarenta y dos ante el Lic. Pérez. Otra.": "Escritura No. Cuarenta y dos ante el Lic. Pérez.",
        "Lote en Fracc. Las Flores, Mz. 3, Lt. 12. Sigue.": "Lote en Fracc. Las Flores, Mz. 3, Lt. 12.",
        "A nombre de Inmobiliaria Sur S.A. de C.V. con folio 9. Fin.": "A nombre de Inmobiliaria Sur S.A. de C.V. con folio 9.",
        "Firmó el Ing. Ruiz y la Sra. Gómez con el Dr. Paz y el Arq. Sol. Fin.":
            "Firmó el Ing. Ruiz y la Sra. Gómez con el Dr. Paz y el Arq. Sol.",
    }
    for texto, esperado in casos.items():
        assert L.primera_oracion(texto) == esperado, texto


# ---------------------------------------------------------------- casos que antes ocultaban pendientes

def _h(id_regla, explicacion, estado=EstadoRegla.NO_CUMPLE, severidad=Severidad.REVISION, archivo=None):
    evid = [Evidencia(archivo=archivo, pagina=1, cita="x")] if archivo else []
    return Hallazgo(id_regla=id_regla, descripcion=id_regla, estado=estado, severidad=severidad,
                    explicacion=explicacion, evidencias=evid)


def _doc(archivo, tipo, hallazgos=(), legibilidad=Legibilidad.BUENA):
    return DocumentoAnalizado(archivo=archivo, tipo=tipo, confianza_tipo=0.9, legibilidad=legibilidad,
                              datos=DatosInmueble(), hallazgos=list(hallazgos), confianza=0.9)


def _base(documentos, hallazgos_expediente=(), inconsistencias=(), faltantes=(), razones=()):
    d = _demo("dictamen_demo_02")
    return d.model_copy(update={
        "documentos": list(documentos), "hallazgos_expediente": list(hallazgos_expediente),
        "inconsistencias": list(inconsistencias), "documentos_faltantes": list(faltantes), "razones": list(razones),
    })


def test_faltante_bloqueante_no_se_une_a_una_inconsistencia_que_comparte_palabras():
    inc = Inconsistencia(
        id_regla="CRU-SUP", campo="superficie_terreno_m2", severidad=Severidad.REVISION,
        descripcion="Uso de suelo y escritura reportan superficies distintas.",
        valores=[ValorEncontrado(archivo="e.pdf", tipo=TipoDocumento.ESCRITURA, valor="450"),
                 ValorEncontrado(archivo="u.pdf", tipo=TipoDocumento.USO_SUELO, valor="432")])
    d = _base([_doc("e.pdf", TipoDocumento.ESCRITURA), _doc("u.pdf", TipoDocumento.USO_SUELO)],
              [_h("EXP-01", "Falta el uso de suelo.", severidad=Severidad.BLOQUEANTE)], [inc])
    items, _ = L.pendientes(d)
    fila = [it for it in items if "Falta el uso de suelo." in it.texto]
    assert len(fila) == 1 and fila[0].severidad == Severidad.BLOQUEANTE
    assert items[0] is fila[0]  # el bloqueante va primero


def test_regla_que_solo_comparte_una_palabra_no_se_une():
    inc = Inconsistencia(
        id_regla="CRU-NUM", campo="numero_oficial", severidad=Severidad.REVISION,
        descripcion="El alineamiento asigna el 17; la escritura dice 15.",
        valores=[ValorEncontrado(archivo="e.pdf", tipo=TipoDocumento.ESCRITURA, valor="15"),
                 ValorEncontrado(archivo="a.pdf", tipo=TipoDocumento.ALINEAMIENTO, valor="17")])
    d = _base([_doc("e.pdf", TipoDocumento.ESCRITURA),
               _doc("a.pdf", TipoDocumento.ALINEAMIENTO, [_h("ALI-09", "El alineamiento es ilegible.")])],
              inconsistencias=[inc])
    items, _ = L.pendientes(d)
    assert any(it.requisito and it.requisito.id_regla == "ALI-09" for it in items)


def test_regla_mas_severa_que_la_inconsistencia_no_se_une():
    inc = Inconsistencia(
        id_regla="CRU-NUM", campo="numero_oficial", severidad=Severidad.REVISION, descripcion="17 contra 15.",
        valores=[ValorEncontrado(archivo="e.pdf", tipo=TipoDocumento.ESCRITURA, valor="15"),
                 ValorEncontrado(archivo="a.pdf", tipo=TipoDocumento.ALINEAMIENTO, valor="17")])
    d = _base([_doc("a.pdf", TipoDocumento.ALINEAMIENTO,
                    [_h("ALI-01", "Asigna el 17, no el 15.", severidad=Severidad.BLOQUEANTE)])], inconsistencias=[inc])
    items, _ = L.pendientes(d)
    assert items[0].requisito and items[0].requisito.id_regla == "ALI-01"
    assert items[0].severidad == Severidad.BLOQUEANTE


def test_regla_unida_aporta_sus_archivos():
    inc = Inconsistencia(
        id_regla="CRU-NUM", campo="numero_oficial", severidad=Severidad.REVISION, descripcion="17 contra 15.",
        valores=[ValorEncontrado(archivo="e.pdf", tipo=TipoDocumento.ESCRITURA, valor="15"),
                 ValorEncontrado(archivo="p.pdf", tipo=TipoDocumento.PREDIAL, valor="17")])
    d = _base([_doc("a.pdf", TipoDocumento.ALINEAMIENTO, [_h("ALI-01", "Asigna el 17, no el 15.")])],
              inconsistencias=[inc])
    items = [it for it in L.pendientes(d)[0] if it.clase != "faltante"]  # los demás tipos faltan a propósito
    assert len(items) == 1 and items[0].archivos == ["e.pdf", "p.pdf", "a.pdf"]


def test_regla_informativa_del_expediente_no_suprime_el_faltante():
    d = _base([_doc("e.pdf", TipoDocumento.ESCRITURA)],
              [_h("EXP-07", "Falta el predial.", estado=EstadoRegla.NO_EVALUABLE, severidad=Severidad.INFO)],
              faltantes=[TipoDocumento.PREDIAL])
    items, _ = L.pendientes(d)
    assert any(it.clase == "faltante" and "Predial" in it.texto for it in items)


def test_ilegible_se_decide_por_hallazgo():
    # Un hallazgo nombra el alineamiento y otro dice "ilegible", pero ninguno dice las dos cosas.
    d = _base([_doc("a.pdf", TipoDocumento.ALINEAMIENTO, legibilidad=Legibilidad.ILEGIBLE)],
              [_h("EXP-05", "El alineamiento está vencido."), _h("EXP-06", "La escritura es ilegible en parte.")])
    items, _ = L.pendientes(d)
    assert any(it.clase == "ilegible" and it.archivos == ["a.pdf"] for it in items)


def test_razon_de_propietario_no_se_pierde():
    razon = "El propietario no coincide entre escritura y predial."
    d = _base([_doc("p.pdf", TipoDocumento.PREDIAL, [_h("PRE-03", "El predial sigue a nombre de la vendedora.")])],
              razones=[razon])
    _, sueltas = L.pendientes(d)
    assert sueltas == [razon]


def test_razon_identica_a_un_renglon_no_se_repite():
    d = _base([_doc("p.pdf", TipoDocumento.PREDIAL, [_h("PRE-03", "El predial sigue a nombre de la vendedora.")])],
              razones=["  el predial sigue a nombre de la VENDEDORA. "])
    assert L.pendientes(d)[1] == []


def test_texto_y_severidad_salen_del_hallazgo_mas_severo():
    d = _base([_doc("p1.pdf", TipoDocumento.PREDIAL, [_h("PRE-02", "Detalle menor.", severidad=Severidad.INFO)]),
               _doc("p2.pdf", TipoDocumento.PREDIAL, [_h("PRE-02", "Adeudo de $9,000.", severidad=Severidad.BLOQUEANTE)])])
    (fila,) = [it for it in L.pendientes(d)[0] if it.clase == "requisito"]
    assert fila.severidad == Severidad.BLOQUEANTE and fila.texto == "Adeudo de $9,000."
    assert fila.requisito.descripcion == "PRE-02"


def test_evidencia_dice_archivo_y_estado_de_cada_hallazgo():
    d = _base([_doc("p1.pdf", TipoDocumento.PREDIAL, [_h("PRE-02", "Uno.")]),
               _doc("p2.pdf", TipoDocumento.PREDIAL, [_h("PRE-02", "Dos.", estado=EstadoRegla.NO_EVALUABLE)])])
    html = C.lista_pendientes(d)
    assert "p1.pdf · No cumple" in html and "p2.pdf · No evaluable" in html


def test_tipo_faltante_con_archivo_muestra_ambas_tarjetas():
    d = _demo("dictamen_ejemplo")
    d.documentos_faltantes = [TipoDocumento.ALINEAMIENTO]
    html = C.documentos(d)
    assert "doc-falta" in html and html.count("03 Alineamiento DEMO.pdf") >= 2  # aviso y tarjeta del archivo
