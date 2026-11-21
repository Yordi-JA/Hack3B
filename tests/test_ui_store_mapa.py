import json

from expedientes.orquestador import analizar_expediente
from ui import componentes as C
from ui import mapa, store
from ui import tokens as t
from ui.mapa import ConteoEntidad
from expedientes.schemas import Recomendacion


# ------------------------------------------------------------------ store

def test_guardar_y_cargar_ida_y_vuelta(tmp_path):
    d = analizar_expediente([], usar_ejemplo=True).model_copy(update={"expediente_id": "Expediente 5 / lote: 2"})
    entrada = store.guardar(d, tmp_path / "resultados")
    assert entrada.ruta.name == "Expediente 5 - lote- 2.json"
    entradas, invalidos = store.cargar(tmp_path / "resultados", tmp_path / "no-existe")
    assert invalidos == [] and len(entradas) == 1
    assert entradas[0].dictamen == d and entradas[0].clave == entrada.clave and not entradas[0].es_ejemplo
    assert store.buscar(entradas, entrada.clave) is entradas[0]
    assert list((tmp_path / "resultados").glob("*.tmp")) == []


def test_archivos_danados_no_tumban_la_carga(tmp_path):
    res = tmp_path / "resultados"
    res.mkdir()
    (res / "roto.json").write_text("{no es json", encoding="utf-8")
    (res / "otro_contrato.json").write_text(json.dumps({"expediente_id": "X"}), encoding="utf-8")
    store.guardar(analizar_expediente([], usar_ejemplo=True), res)
    entradas, invalidos = store.cargar(res, tmp_path / "vacio")
    assert len(entradas) == 1
    assert sorted(i.ruta.name for i in invalidos) == ["otro_contrato.json", "roto.json"]


def test_nombre_archivo_nunca_vacio():
    assert store.nombre_archivo("..") == "expediente.json"
    assert store.nombre_archivo('a<b>c') == "a-b-c.json"


# ------------------------------------------------------------------ mapa

def test_normalizar_entidad_acepta_variantes():
    assert mapa.normalizar_entidad("Estado de México") == "MEXICO"
    assert mapa.normalizar_entidad("CDMX") == "CIUDAD DE MEXICO"
    assert mapa.normalizar_entidad("hidalgo") == "HIDALGO"
    assert mapa.normalizar_entidad("Veracruz de Ignacio de la Llave") == "VERACRUZ"
    assert mapa.normalizar_entidad("Atlantida") is None and mapa.normalizar_entidad(None) is None


def test_las_32_entidades_existen_en_el_svg():
    geo = mapa._geometria()["estados"]
    assert len(mapa.ENTIDADES) == 32
    assert {id_ for id_, _ in mapa.ENTIDADES.values()} == set(geo)
    assert all("bbox" in e and "etiqueta" in e for e in geo.values())


def test_relleno_por_peor_recomendacion():
    conteos = {"HIDALGO": ConteoEntidad(2, {Recomendacion.CUMPLE: 1, Recomendacion.REQUIERE_REVISION: 1})}
    rellenos = mapa.relleno_por_entidad(conteos)
    assert rellenos["MXHID"] == t.AMBAR.mapa
    assert rellenos["MXMEX"] == t.MAPA_VACIO


def test_svg_bandeja_enlaza_solo_entidades_con_expedientes_y_sin_recursos_externos():
    conteos = {"HIDALGO": ConteoEntidad(1, {Recomendacion.NO_CUMPLE: 1})}
    svg = mapa.svg_bandeja(conteos, None, {"vista": "bandeja", "rec": "Cumple"})
    assert svg.count("<a ") == 1
    assert "entidad=HIDALGO" in svg and "rec=Cumple" in svg and 'target="_self"' in svg
    assert "http" not in svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    # con la entidad seleccionada, el enlace la quita del filtro
    assert "entidad=" not in mapa.svg_bandeja(conteos, "HIDALGO", {"vista": "bandeja"})


def test_cajas_de_vista():
    assert mapa.caja_de_vista(None) == (0.0, 0.0, 1000.0, 630.0)
    x, y, w, h = mapa.caja_de_vista("HIDALGO")
    x0, y0, x1, y1 = mapa._geometria()["estados"]["MXHID"]["bbox"]
    assert x < x0 and y < y0 and x + w > x1 and y + h > y1
    assert mapa.caja_de_datos([]) == (0.0, 0.0, 1000.0, 630.0)
    x, y, w, h = mapa.caja_de_datos(["HIDALGO", "MEXICO"])
    assert 0 <= x and 0 <= y and x + w <= 1000 and y + h <= 630 and w >= 430


# ------------------------------------------------------------------ html

def test_html_escapa_datos_de_documentos_y_no_deja_lineas_en_blanco():
    d = analizar_expediente([], usar_ejemplo=True)
    doc = d.documentos[0]
    doc.datos.propietario.valor = "<script>alert(1)</script>"
    doc.hallazgos[0].evidencias[0].cita = 'línea 1\n\nlínea "2" <b>'
    piezas = [C.tarjeta_dictamen(d, True), C.tarjetas_documentos(d), C.tabla_datos(d),
              C.lista_hallazgos(doc.hallazgos), C.tipos_recibidos(d), C.tarjeta_expediente("ejemplo:x", d, True)]
    for html in piezas:
        assert "<script>" not in html and "\n\n" not in html
    assert "&lt;script&gt;" in C.tabla_datos(d)


def test_contraste_de_etiquetas_cumple_aa():
    for tono in (t.VERDE, t.AMBAR, t.VINO, t.AZUL, t.GRIS):
        assert t.contraste(tono.texto, tono.fondo) >= 4.5
        assert t.contraste(tono.oscuro, t.TARJETA_OSCURA) >= 4.5
    assert t.contraste("#FFFFFF", t.ROJO_3B_OSCURO) >= 4.5
    assert t.contraste(t.TEXTO_SOBRE_OSCURO_2, t.TARJETA_OSCURA) >= 4.5
