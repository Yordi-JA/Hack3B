"""Bandeja tipo tablero: indicadores, mapa con ventana por estado y recorrido guiado (sin Streamlit en pantalla)."""
import re
from pathlib import Path

from expedientes.orquestador import analizar_expediente
from expedientes.schemas import Recomendacion
from ui import componentes as C
from ui import logica as L
from ui import mapa, tour
from ui.mapa import ConteoEntidad

R = Recomendacion


def _ind():
    d = analizar_expediente([], usar_ejemplo=True)
    otro = d.model_copy(update={"recomendacion": R.CUMPLE})
    return L.indicadores([(d, True), (d, False), (otro, False), (otro, False)])


def test_kpis_cuatro_tarjetas_con_porcentaje_y_filtro():
    html = C.kpis_bandeja(_ind(), {"vista": "bandeja", "entidad": "HIDALGO", "rec": "Cumple"})
    assert html.count('class="kpi ') == 4 and "\n" not in html
    assert "Expedientes analizados" in html and "<b class=\"kpi-num\">4</b>" in html
    assert "50 % del total" in html  # 2 de 4 cumplen y 2 de 4 no cumplen
    # cada tarjeta de recomendación filtra conservando la entidad; la del total quita el filtro
    assert "rec=No+cumple" in html and "entidad=HIDALGO" in html
    assert html.split("</a>")[0].count("rec=") == 0


def test_predominante_y_empate_toma_la_mas_grave():
    c = ConteoEntidad(3, {R.CUMPLE: 2, R.NO_CUMPLE: 1})
    assert c.predominante == R.CUMPLE and c.peor == R.NO_CUMPLE
    assert ConteoEntidad(2, {R.CUMPLE: 1, R.REQUIERE_REVISION: 1}).predominante == R.REQUIERE_REVISION
    assert round(c.porcentaje(R.CUMPLE), 2) == 0.67
    rell = mapa.relleno_por_entidad({"HIDALGO": c}, "predominante")
    assert rell["MXHID"] == C.t.ESTADO[R.CUMPLE].mapa


def test_ventana_del_estado_con_porcentajes_y_cerrar():
    c = ConteoEntidad(4, {R.CUMPLE: 1, R.REQUIERE_REVISION: 1, R.NO_CUMPLE: 2})
    html = C.ventana_entidad("SONORA", c, {"vista": "bandeja", "entidad": "SONORA", "q": "x"})
    assert "Sonora" in html and "4 expedientes" in html and "\n" not in html
    assert re.findall(r">(\d+) %<", html) == ["25", "25", "50"]
    cerrar = re.search(r'class="v-cerrar" href="([^"]+)"', html).group(1)
    assert "entidad" not in cerrar and "q=x" in cerrar
    assert 'href="#expedientes"' in html
    assert C.ventana_entidad("SONORA", ConteoEntidad(), {}) == ""


def test_mapa_con_abreviaturas_sin_tapar_burbujas():
    svg = mapa.svg_bandeja({"QUERETARO": ConteoEntidad(1, {R.CUMPLE: 1})}, None, {"vista": "bandeja"})
    assert ">BCN<" in svg and ">SON<" in svg
    assert ">SLP<" not in svg  # quedaría bajo la burbuja de Querétaro
    # en la bandeja: solo color, sin números ni burbujas; la ventana se ancla al estado
    sin = mapa.svg_bandeja({"QUERETARO": ConteoEntidad(1, {R.CUMPLE: 1})}, None, {"vista": "bandeja"}, numeros=False)
    assert "mx-llamada" not in sin and "mx-num" not in sin and ">SLP<" in sin
    assert 'class="mx-enlace"' in sin
    assert mapa.punto_etiqueta("QUERETARO") != mapa.LLAMADAS["QUERETARO"]


def test_recorrido_css_solo_style_y_objetivos_existen():
    fuente = (Path(__file__).resolve().parent.parent / "ui" / "vistas.py").read_text(encoding="utf-8")
    for paso in tour.PASOS:
        css = tour.css_paso(paso)
        assert re.findall(r"<[^>]+>", css) == ["<style>", "</style>"]
        if paso.objetivo:
            assert f'"{paso.objetivo}"' in fuente, paso.objetivo  # el contenedor con esa key existe
        assert "\n" not in tour.tarjeta(tour.PASOS.index(paso))
