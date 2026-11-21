"""Texto hostil de documentos/LLM, nombres de archivo raros y casos borde del dictamen."""
import re

from expedientes.orquestador import analizar_expediente
from expedientes.schemas import (
    DatosInmueble,
    DocumentoAnalizado,
    EstadoRegla,
    Hallazgo,
    Inconsistencia,
    Legibilidad,
    Severidad,
    TipoDocumento,
    ValorEncontrado,
)
from ui import componentes as C
from ui import logica as L
from ui import store

CARGA = "a\n\n    b\r\n\n![](http://x.example/p)\n<img src=x>"


def _dictamen_hostil():
    d = analizar_expediente([], usar_ejemplo=True)
    d.expediente_id = "EXP" + CARGA
    d.resumen = CARGA
    d.razones = [CARGA, "ok"]
    doc = d.documentos[0]
    doc.archivo = "Escritura" + CARGA + ".pdf"
    doc.datos.propietario.valor = CARGA
    doc.datos.municipio.normalizado = "TLAL" + CARGA
    doc.hallazgos[0].explicacion = CARGA
    doc.hallazgos[0].descripcion = CARGA
    doc.hallazgos[0].evidencias[0].cita = CARGA
    d.hallazgos_expediente[0].explicacion = CARGA
    inc = d.inconsistencias[0]
    inc.descripcion = CARGA
    inc.valores[0].valor = CARGA
    inc.valores[0].archivo = CARGA
    return d


def _piezas(d):
    reqs = L.consolidar_requisitos(d)
    return [
        C.tarjeta_dictamen(d, True), C.razones(d), C.tipos_recibidos(d), C.tarjetas_documentos(d),
        C.tabla_datos(d), C.tabla_requisitos(reqs), C.resumen_requisitos(reqs), C.avisos_sin_analizar(d),
        C.lista_hallazgos(d.documentos[0].hallazgos), C.lista_hallazgos(d.hallazgos_expediente),
        C.inconsistencia(d.inconsistencias[0]), C.lista_expedientes([("resultado:x", d, False)]),
    ]


def test_ningun_fragmento_tiene_lineas_ni_markdown_activo():
    for html in _piezas(_dictamen_hostil()):
        assert "\n" not in html and "\r" not in html
        assert not re.search(r"^\s*$", html, re.M) or html == ""
        assert "<img" not in html  # la etiqueta del documento sale escapada
        # `![` puede aparecer como texto, pero nunca al inicio de una línea (no hay líneas)
        assert not re.search(r"(^|\n)\s*!\[", html)


def test_txt_colapsa_y_escapa():
    assert C.txt("  a \t b \r\n\n\n c <x> ") == "a b<br>c &lt;x&gt;"
    assert C.txt(None) == ""


def test_nombres_reservados_de_windows():
    for malo in ["", ".", "..", "a:b.pdf", "CON", "con.pdf", "Nul.txt", "COM1.pdf", "lpt9", "x/y.pdf", "x\\y.pdf"]:
        assert store.nombre_reservado(malo), malo
    for bueno in ["Escritura Tepeji.pdf", "console.pdf", "COM10.pdf", "predial (1).jpg"]:
        assert not store.nombre_reservado(bueno), bueno
    assert store.nombre_archivo("CON") == "expediente.json"
    assert store.nombre_archivo("nul.txt") == "expediente.json"


def test_ids_distintos_no_se_pisan_y_el_mismo_id_reemplaza(tmp_path):
    base = analizar_expediente([], usar_ejemplo=True)
    a = store.guardar(base.model_copy(update={"expediente_id": "Tepeji/5"}), tmp_path)
    b = store.guardar(base.model_copy(update={"expediente_id": "Tepeji:5"}), tmp_path)  # mismo nombre limpio
    c = store.guardar(base.model_copy(update={"expediente_id": "TEPEJI-5"}), tmp_path)  # solo cambia mayúsculas
    otra_vez = store.guardar(base.model_copy(update={"expediente_id": "Tepeji/5", "confianza": 0.5}), tmp_path)
    assert [a.ruta.name, b.ruta.name, c.ruta.name] == ["Tepeji-5.json", "Tepeji-5-2.json", "TEPEJI-5-3.json"]
    assert otra_vez.ruta.name == "Tepeji-5.json" and otra_vez.clave == "resultado:Tepeji-5"
    entradas, invalidos = store.cargar(tmp_path, tmp_path / "nada")
    assert len(entradas) == 3 and not invalidos


def _doc_con_error(archivo, tipo):
    return DocumentoAnalizado(
        archivo=archivo, tipo=tipo, confianza_tipo=0.9, legibilidad=Legibilidad.BUENA, datos=DatosInmueble(),
        hallazgos=[Hallazgo(id_regla="EXP-ERROR", descripcion="Documento recibido sin análisis",
                            estado=EstadoRegla.NO_EVALUABLE, severidad=Severidad.REVISION,
                            explicacion="Falló el análisis automático: TimeoutError")],
        confianza=0.0,
    )


def test_archivo_sin_analizar_se_ve_en_recibidos_tarjeta_tabla_y_requisitos():
    d = analizar_expediente([], usar_ejemplo=True)
    d.documentos = [doc for doc in d.documentos if doc.tipo != TipoDocumento.PREDIAL]
    d.documentos.append(_doc_con_error("Predial roto.pdf", TipoDocumento.PREDIAL))
    assert [doc.archivo for doc in L.archivos_sin_analizar(d)] == ["Predial roto.pdf"]
    assert L.tipo_sin_analizar(d, TipoDocumento.PREDIAL)
    assert "Recibido, sin analizar" in C.tipos_recibidos(d)
    assert "Sin analizar" in C.tarjeta_documento(d.documentos[-1])
    assert "Confianza 0" not in C.tarjeta_documento(d.documentos[-1])
    assert "Sin analizar" in C.tabla_datos(d)
    aviso = C.avisos_sin_analizar(d)
    assert "Predial roto.pdf (Predial) no se pudo analizar" in aviso and "requisitos de Predial" in aviso


def test_faltante_recibido_explica_por_que():
    d = analizar_expediente([], usar_ejemplo=True)
    d.documentos_faltantes = [TipoDocumento.ALINEAMIENTO]
    html = C.tipos_recibidos(d)
    assert "Se recibió 03 Alineamiento DEMO.pdf pero el dictamen lo considera faltante" in html


def test_requisitos_agrupan_por_tipo_y_regla():
    d = analizar_expediente([], usar_ejemplo=True)
    regla = Hallazgo(id_regla="GEN-01", descripcion="x", estado=EstadoRegla.CUMPLE, severidad=Severidad.INFO, explicacion="x")
    d.documentos[0].hallazgos.append(regla)
    d.documentos[1].hallazgos.append(regla.model_copy(update={"estado": EstadoRegla.NO_CUMPLE}))
    gen = [r for r in L.consolidar_requisitos(d) if r.id_regla == "GEN-01"]
    assert {(r.tipo, r.estado) for r in gen} == {
        (TipoDocumento.ESCRITURA, EstadoRegla.CUMPLE), (TipoDocumento.PREDIAL, EstadoRegla.NO_CUMPLE)}
    assert next(r for r in L.consolidar_requisitos(d) if r.id_regla == "EXP-01").tipo is None


def test_difiere_con_empate_marca_todos():
    from expedientes.schemas import Campo
    celdas = [Campo(valor="15", normalizado="15"), None, Campo(valor="17", normalizado="17")]
    assert L.valores_discrepantes(celdas) == {0, 2}


def test_pie_del_mapa_con_entidades_empatadas():
    d = analizar_expediente([], usar_ejemplo=True)
    for i, doc in enumerate(d.documentos):
        doc.datos.entidad_federativa.normalizado = "HIDALGO" if i % 2 else "MEXICO"
    html = C.tarjeta_dictamen(d, False)
    assert "Estado de México o Hidalgo (los documentos no coinciden)" in html or \
        "Hidalgo o Estado de México (los documentos no coinciden)" in html


def test_valor_inconsistencia_vacio():
    inc = Inconsistencia(id_regla="CRU-X", campo="propietario", descripcion="d", severidad=Severidad.INFO,
                         valores=[ValorEncontrado(archivo="a", tipo=TipoDocumento.PREDIAL, valor=None)])
    assert "Sin dato" in C.inconsistencia(inc)
