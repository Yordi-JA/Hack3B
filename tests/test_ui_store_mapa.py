from pathlib import Path
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
    assert svg.count('class="mx-enlace"') == 1  # un solo enlace enfocable por estado
    # Hidalgo es chico: su número va en una llamada, con enlace solo para el mouse
    assert 'class="mx-llamada" tabindex="-1" aria-hidden="true"' in svg
    assert 'viewBox="0 0 1000 630"' in svg  # todo el país, sin acercamiento
    assert "entidad=HIDALGO" in svg and "rec=Cumple" in svg and 'target="_self"' in svg
    assert "http" not in svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    # con la entidad seleccionada, el enlace la quita del filtro
    assert "entidad=" not in mapa.svg_bandeja(conteos, "HIDALGO", {"vista": "bandeja"})


def test_cajas_de_vista():
    assert mapa.caja_de_vista(None) == (0.0, 0.0, 1000.0, 630.0)
    x, y, w, h = mapa.caja_de_vista("HIDALGO")
    x0, y0, x1, y1 = mapa._geometria()["estados"]["MXHID"]["bbox"]
    assert x < x0 and y < y0 and x + w > x1 and y + h > y1


# ------------------------------------------------------------------ html

def test_html_escapa_datos_de_documentos_y_no_deja_lineas_en_blanco():
    d = analizar_expediente([], usar_ejemplo=True)
    doc = d.documentos[0]
    doc.datos.propietario.valor = "<script>alert(1)</script>"
    doc.hallazgos[0].evidencias[0].cita = 'línea 1\n\nlínea "2" <b>'
    piezas = [C.tarjeta_dictamen(d, True), C.documentos(d), C.tabla_datos(d), C.lista_pendientes(d),
              C.detalle_completo(d), C.tarjeta_expediente("ejemplo:x", d, True)]
    for html in piezas:
        assert "<script>" not in html and "\n\n" not in html
    assert "&lt;script&gt;" in C.tabla_datos(d)


def test_contraste_de_etiquetas_cumple_aa():
    estados = (t.VERDE, t.AMBAR, t.VINO, t.AZUL, t.GRIS)
    for tono in estados:
        assert t.contraste(tono.texto, tono.fondo) >= 4.5            # etiqueta suave
        assert t.contraste("#FFFFFF", tono.texto) >= 4.5              # sello: texto blanco sobre el color del estado
    pares = [
        ("#FFFFFF", t.ROJO_3B_SIDEBAR),   # texto de la barra lateral y foco blanco
        ("#FFFFFF", t.ROJO_3B_OSCURO),    # botón principal del dictamen, KPI principal
        (t.ROJO_3B_OSCURO, t.PANEL),      # título DICTAMEN sobre la línea, pestaña activa de la navegación
        (t.TINTA_3B, "#FFFFFF"), (t.TINTA_3B, t.PANEL),  # texto y botón secundario "Ver documentos"
        (t.TEXTO, t.PANEL), (t.TEXTO_2, t.PANEL), (t.TEXTO_2, "#FFFFFF"),
    ]
    for texto, fondo in pares:
        assert t.contraste(texto, fondo) >= 4.5, (texto, fondo)
    assert t.contraste("#FFFFFF", t.ROJO_3B) < 4.5  # por eso la barra usa ROJO_3B_SIDEBAR
    # Verde de marca: texto en tinta sobre el botón (normal y hover) y sobre el segmento activo.
    assert t.contraste(t.TINTA_3B, t.VERDE_3B) >= 4.5
    assert t.contraste(t.TINTA_3B, t.VERDE_3B_HOVER) >= 4.5
    # El verde solo contra el fondo no llega a 3:1; el contorno en tinta del segmento activo y del
    # interruptor encendido es lo que lo separa del fondo.
    assert t.contraste(t.VERDE_3B, t.PANEL) < 3
    assert t.contraste(t.TINTA_3B, t.PANEL) >= 3


def test_no_quedan_superficies_oscuras():
    raiz = Path(__file__).resolve().parent.parent
    fuentes = "".join((raiz / "ui" / f).read_text(encoding="utf-8")
                      for f in ("tokens.py", "estilos.py", "componentes.py", "mapa.py"))
    for viejo in ("#0A2C29", "#163D39", "#06231F", "#1D4641", "#21504B", "TARJETA_OSCURA", "oscuro="):
        assert viejo not in fuentes, viejo
    assert "background: var(--tinta)" not in fuentes


# ------------------------------------------------------------------ flujo de análisis (sin Streamlit en pantalla)

def test_analizar_guarda_subidas_con_nombre_original_y_persiste(tmp_path, monkeypatch):
    import expedientes.orquestador as orq
    from ui import vistas

    vistos = {}
    original = orq.analizar_expediente

    def falso(rutas, ctx=None, expediente_id=None, usar_ejemplo=False):
        vistos["nombres"] = [r.name for r in rutas]
        vistos["contenido"] = [r.read_bytes() for r in rutas]
        return original([], usar_ejemplo=True).model_copy(update={"expediente_id": expediente_id})

    monkeypatch.setattr(orq, "analizar_expediente", falso)
    monkeypatch.setattr(store, "DIR_RESULTADOS", tmp_path / "resultados")
    entrada = vistas._analizar([("01 Escritura Tepeji ñ.pdf", b"%PDF"), ("../predial.jpg", b"img")], "TEPEJI-05")
    assert vistos["nombres"] == ["01 Escritura Tepeji ñ.pdf", "predial.jpg"]
    assert vistos["contenido"] == [b"%PDF", b"img"]
    assert entrada.ruta == tmp_path / "resultados" / "TEPEJI-05.json"
    assert entrada.clave == "resultado:TEPEJI-05" and entrada.dictamen.expediente_id == "TEPEJI-05"


# ------------------------------------------------------------------ bandeja sin tarjetas de indicadores

def test_resumen_bandeja_en_una_linea():
    from ui import logica as L
    d = analizar_expediente([], usar_ejemplo=True)
    assert C.resumen_bandeja(L.indicadores([(d, True), (d, False)])) == (
        '<p class="resumen-bandeja">2 expedientes · confianza promedio 86 % · 1 de ejemplo</p>')
    assert "de ejemplo" not in C.resumen_bandeja(L.indicadores([(d, False)]))
    assert "1 expediente ·" in C.resumen_bandeja(L.indicadores([(d, False)]))
    assert "Ningún expediente" in C.resumen_bandeja(L.indicadores([]))


def test_tarjeta_de_bandeja_sin_etiquetas_y_estado_en_texto():
    d = analizar_expediente([], usar_ejemplo=True)
    html = C.tarjeta_expediente("ejemplo:x", d, True)
    assert 'class="etq' not in html
    assert '· <b class="exp-estado est-vino">No cumple</b>' in html
    assert "Confianza 86 % · Ejemplo · 21/11/2026 10:00" in html
    assert "Ejemplo" not in C.tarjeta_expediente("resultado:x", d, False)


def test_estado_en_texto_contrasta_con_el_fondo_de_la_pagina():
    for tono in (t.VERDE, t.AMBAR, t.VINO):
        assert t.contraste(tono.texto, t.PANEL) >= 4.5


def test_css_solo_lleva_la_etiqueta_style():
    # st.html solo inyecta el bloque como hoja de estilos si no trae otras etiquetas; un "<a>" en un
    # comentario bastó para que la app se quedara sin estilos.
    import re
    from ui import estilos
    assert re.findall(r"<[^>]+>", estilos.css()) == ["<style>", "</style>"]
