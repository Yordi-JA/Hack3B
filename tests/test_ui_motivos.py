"""Seguimiento por motivo de descarte en la UI (bandeja y detalle), sobre expedientes/motivos.py."""
import csv
import io
import re
from pathlib import Path

from expedientes.motivos import Categoria
from expedientes.schemas import (
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

EJEMPLOS = Path(__file__).resolve().parent.parent / "ejemplos"


def _demo(nombre: str) -> Dictamen:
    return Dictamen.model_validate_json((EJEMPLOS / f"{nombre}.json").read_text(encoding="utf-8"))


def _h(id_regla, severidad=Severidad.REVISION, estado=EstadoRegla.NO_CUMPLE, explicacion="x"):
    return Hallazgo(id_regla=id_regla, descripcion=id_regla, estado=estado, severidad=severidad, explicacion=explicacion)


def _exp(hallazgos_por_doc, recomendacion=Recomendacion.REQUIERE_REVISION, expediente_id="EXP-T"):
    docs = [DocumentoAnalizado(archivo=a, tipo=t, confianza_tipo=0.9, legibilidad=Legibilidad.BUENA,
                               datos=DatosInmueble(), hallazgos=hs, confianza=0.9) for a, t, hs in hallazgos_por_doc]
    return _demo("dictamen_demo_02").model_copy(update={
        "expediente_id": expediente_id, "documentos": docs, "hallazgos_expediente": [], "inconsistencias": [],
        "recomendacion": recomendacion})


def test_motivo_principal():
    assert L.motivo_principal(_demo("dictamen_demo_02")) is None  # cumple
    assert L.motivo_principal(_demo("dictamen_demo_04")) == "Descartado por adeudos de predial"
    d = _exp([("u.pdf", TipoDocumento.USO_SUELO, [_h("USO-01"), _h("USO-02", Severidad.BLOQUEANTE)])],
             Recomendacion.NO_CUMPLE)
    assert L.motivo_principal(d) == "Descartado por documento vencido"  # el bloqueante va primero


def test_coincide_por_categoria_con_cualquier_motivo():
    d = _demo("dictamen_demo_04")  # adeudo (principal) + expediente incompleto + datos que no coinciden...
    assert L.coincide(d, categoria=Categoria.ADEUDO_FISCAL)
    assert L.coincide(d, categoria=Categoria.DATOS_NO_COINCIDEN)
    assert not L.coincide(d, categoria=Categoria.USO_SUELO)
    assert not L.coincide(_demo("dictamen_demo_02"), categoria=Categoria.VIGENCIA)


def test_conteo_por_motivo_cuenta_expedientes_y_no_ejemplos():
    dos_uso = _exp([("u.pdf", TipoDocumento.USO_SUELO, [_h("USO-01"), _h("USO-07")])], expediente_id="A")
    uso_bloq = _exp([("u.pdf", TipoDocumento.USO_SUELO, [_h("USO-01"), _h("USO-08", Severidad.BLOQUEANTE)])],
                    Recomendacion.NO_CUMPLE, expediente_id="B")
    ejemplo = _exp([("u.pdf", TipoDocumento.USO_SUELO, [_h("USO-01", Severidad.BLOQUEANTE)])], expediente_id="C")
    conteo = L.conteo_por_motivo([(dos_uso, False), (uso_bloq, False), (ejemplo, True)])
    assert conteo[Categoria.USO_SUELO] == {"descartados": 1, "en_revision": 1}
    assert L.conteo_por_motivo([(ejemplo, True)]) == {}


def _filas_csv(datos: bytes):
    assert datos.startswith(b"\xef\xbb\xbf")  # BOM para Excel
    return list(csv.reader(io.StringIO(datos.decode("utf-8-sig"))))


def test_csv_columnas_cumple_e_inyeccion():
    malo = _exp([("=HYPERLINK(1).pdf", TipoDocumento.PREDIAL, [_h("PRE-04", Severidad.BLOQUEANTE, explicacion="+SUMA(A1)")])],
                Recomendacion.NO_CUMPLE, expediente_id="-EXP-1")
    filas = _filas_csv(L.csv_seguimiento([_demo("dictamen_demo_02"), malo]))
    assert filas[0] == ["expediente_id", "fecha_analisis", "entidad", "municipio", "recomendacion", "categoria",
                        "etiqueta", "severidad", "id_regla", "archivos", "explicacion"]
    cumple = filas[1]
    assert cumple[0] == "EXP-DEMO-002" and cumple[4] == "Cumple" and cumple[5:] == [""] * 6
    assert cumple[2] == "Querétaro" and cumple[3] == "San Juan del Río"
    fila = filas[2]
    assert fila[0] == "'-EXP-1" and fila[9] == "'=HYPERLINK(1).pdf" and fila[10] == "'+SUMA(A1)"
    assert fila[5] == "adeudo_fiscal" and fila[6] == "Descartado por adeudos de predial" and fila[7] == "bloqueante"


def test_csv_respeta_la_categoria_y_une_archivos():
    filas = _filas_csv(L.csv_seguimiento([_demo("dictamen_demo_04")], Categoria.DATOS_NO_COINCIDEN))
    assert {f[5] for f in filas[1:]} == {"datos_no_coinciden"}
    assert " | " in filas[1][9]


def test_aplicar_filtro_vuelve_a_la_primera_pagina():
    params = {"vista": "bandeja", "pag": "3", "entidad": "HIDALGO"}
    assert L.aplicar_filtro(params, "mot", "uso_suelo") == {"vista": "bandeja", "entidad": "HIDALGO", "mot": "uso_suelo"}
    assert L.aplicar_filtro({"mot": "uso_suelo", "pag": "2"}, "mot", "") == {}
    assert L.categoria_de("uso_suelo") is Categoria.USO_SUELO and L.categoria_de("otra") is None


def test_fila_de_tabla_enlace_del_motivo_aparte_del_detalle():
    d = _demo("dictamen_demo_04")
    html = C.fila_expediente("ejemplo:x", d, True, _estatus(), params={"vista": "bandeja", "pag": "2"})
    assert not re.search(r"<a [^>]*>[^<]*<a ", html)  # sin enlaces anidados
    assert 'class="t-motivo' in html and "mot=adeudo_fiscal" in html and "pag=" not in html.split("t-motivo")[1].split(">")[0]
    con_filtro = C.fila_expediente("ejemplo:x", d, True, _estatus(), params={}, categoria=Categoria.DATOS_NO_COINCIDEN)
    assert "En revisión por datos que no coinciden entre documentos" in con_filtro
    assert "(también: adeudos de predial)" in con_filtro


def _estatus():
    from ui import decisiones as Dec
    return Dec.Estatus.SIN_REVISAR


def test_detalle_resumen_y_etiqueta_por_renglon():
    d = _demo("dictamen_demo_04")
    resumen = C.resumen_motivos(d)
    assert "Descartado por:</b> adeudos de predial (1) · expediente incompleto (1)" in resumen
    assert "En revisión por:" in resumen
    html = C.lista_pendientes(d)
    assert "Bloqueante</b> · <span class=\"est-vino\">Descartado por expediente incompleto</span>" in html
    assert "Descartado por adeudos de predial" in html


def test_renglon_sin_motivo_no_inventa():
    d = _demo("dictamen_demo_03")
    items, _ = L.pendientes(d)
    ilegible = next(it for it in items if it.clase == "ilegible")
    assert L.motivo_de_pendiente(ilegible, L.motivos(d)) is None


def test_opcion_del_filtro_lleva_los_conteos():
    assert L.opcion_motivo(Categoria.VIGENCIA, {"descartados": 6, "en_revision": 0}) == "Documento vencido · 6 descartados"
    assert L.opcion_motivo(Categoria.USO_SUELO, {"descartados": 2, "en_revision": 1}) == "Uso de suelo · 2 descartados · 1 en revisión"
    assert L.opcion_motivo(Categoria.ADEUDO_FISCAL, {"descartados": 1, "en_revision": 0}) == "Adeudos de predial · 1 descartado"
    assert L.opcion_motivo(Categoria.IDENTIFICACION) == "Datos de identificación incompletos"


def test_conteo_ordenado_por_total():
    a = _exp([("u.pdf", TipoDocumento.USO_SUELO, [_h("USO-01"), _h("USO-02", Severidad.BLOQUEANTE)])], expediente_id="A")
    b = _exp([("u.pdf", TipoDocumento.USO_SUELO, [_h("USO-01")])], expediente_id="B")
    assert list(L.conteo_por_motivo([(a, False), (b, False)]))[0] == Categoria.USO_SUELO


def test_globo_del_recorrido_dura_40_segundos_por_sesion():
    from ui.vistas import GUION_GLOBO, segundos_globo

    sesion: dict = {}
    assert segundos_globo(sesion, ahora=100.0) == 40
    assert segundos_globo(sesion, ahora=125.0) == 15
    assert segundos_globo(sesion, ahora=150.0) == 0  # ya no vuelve en esta sesión
    assert "sessionStorage" in GUION_GLOBO and "40000" in GUION_GLOBO
