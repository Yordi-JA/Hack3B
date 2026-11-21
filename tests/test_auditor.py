"""Auditor y grafo LangGraph de punta a punta. Sin API: agentes falsos, cruce y dictamen reales."""
from pathlib import Path

import pytest

from expedientes import orquestador
from expedientes.agentes import auditor, cruce
from expedientes.schemas import (
    Campo, Contexto, DatosInmueble, DocumentoAnalizado, DocumentoLeido, EstadoRegla, Evidencia, Hallazgo,
    Legibilidad, Pagina, Recomendacion, Severidad, TipoDocumento,
)

TXT_ESC = "ESCRITURA 4521. Compraventa a favor de SILVIA PEÑALOZA RUIZ. SUPERFICIE DE 300.00 M2. CLAVE 077 04 310 12"
TXT_PRE = "RECIBO PREDIAL\nPROPIETARIO PEÑALOZA RUIZ SILVIA\nSUPERFICIE TERRENO (M²) | 300.00\nCLAVE 077 04 310 12"


def _leido(archivo, tipo, *textos):
    return DocumentoLeido(archivo=archivo, tipo=tipo, confianza_tipo=1.0, legibilidad=Legibilidad.BUENA,
                          paginas=[Pagina(numero=i, texto=t) for i, t in enumerate(textos, 1)],
                          paginas_totales=len(textos))


def _c(valor, cita, archivo, pagina=1, norm=None):
    return Campo(valor=valor, normalizado=norm or valor, confianza=0.9,
                 evidencia=Evidencia(archivo=archivo, pagina=pagina, cita=cita))


def _analizado(leido, datos, hallazgos=()):
    return DocumentoAnalizado(archivo=leido.archivo, tipo=leido.tipo, confianza_tipo=1.0, legibilidad=leido.legibilidad,
                              datos=datos, hallazgos=list(hallazgos), confianza=0.9)


def _aud(doc):
    return [h for h in doc.hallazgos if h.id_regla == "EXP-AUD"]


# ---------------------------------------------------------------- auditor

def test_todo_verificado_no_cambia_nada():
    l = _leido("p.pdf", TipoDocumento.PREDIAL, TXT_PRE)
    a = _analizado(l, DatosInmueble(superficie_terreno_m2=_c("300.00", "SUPERFICIE TERRENO (M²) | 300.00", "p.pdf", norm="300.00")))
    r = auditor.auditar([l], [a])
    assert not r.intervenciones and not r.reabrir_cruce and r.documentos[0] is a


def test_cita_inexistente_se_descarta_y_reabre_cruce():
    l = _leido("p.pdf", TipoDocumento.PREDIAL, TXT_PRE)
    a = _analizado(l, DatosInmueble(propietario=_c("JUAN LOPEZ", "PROPIETARIO JUAN LOPEZ", "p.pdf")))
    r = auditor.auditar([l], [a])
    d = r.documentos[0]
    assert d.datos.propietario.normalizado is None and d.datos.propietario.evidencia is None
    assert d.datos.propietario.valor == "JUAN LOPEZ"  # se conserva para que el revisor lo vea
    assert r.reabrir_cruce and _aud(d)[0].severidad == Severidad.REVISION and "AUD-01" in _aud(d)[0].explicacion


def test_cita_real_con_valor_inventado():
    l = _leido("p.pdf", TipoDocumento.PREDIAL, TXT_PRE)
    a = _analizado(l, DatosInmueble(superficie_terreno_m2=_c("350.00", "SUPERFICIE TERRENO (M²) | 300.00", "p.pdf")))
    d = auditor.auditar([l], [a]).documentos[0]
    assert d.datos.superficie_terreno_m2.normalizado is None and "AUD-02" in _aud(d)[0].explicacion


def test_pagina_mal_atribuida_se_corrige_sin_intervenir():
    l = _leido("p.pdf", TipoDocumento.PREDIAL, "portada", TXT_PRE)
    a = _analizado(l, DatosInmueble(superficie_terreno_m2=_c("300.00", "SUPERFICIE TERRENO (M²) | 300.00", "p.pdf", pagina=1)))
    r = auditor.auditar([l], [a])
    assert r.documentos[0].datos.superficie_terreno_m2.evidencia.pagina == 2 and not r.intervenciones


def test_dato_no_cruzable_sin_evidencia_es_informativo():
    l = _leido("p.pdf", TipoDocumento.PREDIAL, TXT_PRE)
    a = _analizado(l, DatosInmueble(especificos={"folio": _c("TM-1", "FOLIO TM-1", "p.pdf")}))
    r = auditor.auditar([l], [a])
    assert not r.reabrir_cruce and _aud(r.documentos[0])[0].severidad == Severidad.INFO


def test_rechazo_sin_evidencia_baja_a_revision():
    l = _leido("u.pdf", TipoDocumento.USO_SUELO, "LICENCIA DE USO DE SUELO COMERCIAL")
    falso = Hallazgo(id_regla="USO-02", descripcion="Vigente", estado=EstadoRegla.NO_CUMPLE, severidad=Severidad.BLOQUEANTE,
                     explicacion="Venció.", evidencias=[Evidencia(archivo="u.pdf", pagina=1, cita="VENCE EL 10 DE MARZO DE 2020")])
    real = Hallazgo(id_regla="USO-01", descripcion="Uso", estado=EstadoRegla.NO_CUMPLE, severidad=Severidad.BLOQUEANTE,
                    explicacion="No autoriza.", evidencias=[Evidencia(archivo="u.pdf", pagina=1, cita="USO DE SUELO COMERCIAL")])
    d = auditor.auditar([l], [_analizado(l, DatosInmueble(), [falso, real])]).documentos[0]
    uso02 = next(h for h in d.hallazgos if h.id_regla == "USO-02")
    uso01 = next(h for h in d.hallazgos if h.id_regla == "USO-01")
    assert (uso02.estado, uso02.severidad) == (EstadoRegla.NO_EVALUABLE, Severidad.REVISION)
    assert (uso01.estado, uso01.severidad) == (EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE)  # con evidencia: se respeta


# ---------------------------------------------------------------- grafo completo

@pytest.fixture
def expediente(monkeypatch):
    """Escritura y predial del mismo predio; el agente de predial inventa la superficie (350)."""
    leidos = {"esc.pdf": _leido("esc.pdf", TipoDocumento.ESCRITURA, TXT_ESC),
              "pre.pdf": _leido("pre.pdf", TipoDocumento.PREDIAL, TXT_PRE)}
    monkeypatch.setattr(orquestador.ingesta, "leer_documento", lambda ruta: leidos[Path(ruta).name])
    monkeypatch.setattr(cruce, "USAR_LLM", False)

    def agente_escritura(doc, ctx):
        return _analizado(doc, DatosInmueble(
            propietario=_c("SILVIA PEÑALOZA RUIZ", "a favor de SILVIA PEÑALOZA RUIZ", doc.archivo),
            superficie_terreno_m2=_c("300.00 M2", "SUPERFICIE DE 300.00 M2", doc.archivo, norm="300.00")))

    def agente_predial(doc, ctx):
        return _analizado(doc, DatosInmueble(
            propietario=_c("PEÑALOZA RUIZ SILVIA", "PROPIETARIO PEÑALOZA RUIZ SILVIA", doc.archivo),
            superficie_terreno_m2=_c("350.00", "SUPERFICIE TERRENO (M²) | 300.00", doc.archivo, norm="350.00")))

    monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, TipoDocumento.ESCRITURA, agente_escritura)
    monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, TipoDocumento.PREDIAL, agente_predial)
    return [Path("esc.pdf"), Path("pre.pdf")]


def test_grafo_el_auditor_corrige_y_el_cruce_se_repite(expediente):
    final = orquestador.GRAFO.invoke({"rutas": expediente, "ctx": Contexto(), "expediente_id": "T1",
                                      "resultados": [], "bitacora": []})
    assert [d.archivo for d in final["analizados"]] == ["esc.pdf", "pre.pdf"]  # orden de entrada
    assert final["rondas_auditoria"] == 2                                       # auditor -> cruce -> auditor
    assert not [i for i in final["inconsistencias"] if i.campo == "superficie_terreno_m2"]  # el 350 inventado ya no cuenta
    assert any("se repite el cruce" in b for b in final["bitacora"])
    assert isinstance(final["dictamen"].recomendacion, Recomendacion)


def test_analizar_expediente_devuelve_dictamen_con_hallazgo_del_auditor(expediente):
    d = orquestador.analizar_expediente(expediente, expediente_id="T2")
    predial = next(x for x in d.documentos if x.archivo == "pre.pdf")
    assert _aud(predial) and d.recomendacion != Recomendacion.CUMPLE  # dato descartado => no se da por bueno
    assert d.expediente_id == "T2"


# ---------------------------------------------------------------- falso positivo reportado por Juan Pablo

def test_direccion_repartida_en_dos_paginas_no_interviene():
    l = DocumentoLeido(archivo="esc.pdf", tipo=TipoDocumento.ESCRITURA, confianza_tipo=1, legibilidad=Legibilidad.BUENA,
                       paginas_totales=2, paginas=[
                           Pagina(numero=1, texto="EL INMUEBLE UBICADO EN CALLE HIDALGO NUMERO 120 CON SUPERFICIE DE 300.00 M2"),
                           Pagina(numero=2, texto="PERTENECIENTE A LA COLONIA CENTRO, MUNICIPIO DE TULTEPEC, ESTADO DE MEXICO")])
    direccion = Campo(valor="CALLE HIDALGO 120, COL. CENTRO, TULTEPEC, MEX.", normalizado="CALLE HIDALGO 120 CENTRO TULTEPEC",
                      confianza=0.9, evidencia=Evidencia(archivo="esc.pdf", pagina=1, cita="UBICADO EN CALLE HIDALGO NUMERO 120"))
    r = auditor.auditar([l], [_analizado(l, DatosInmueble(direccion=direccion))])
    assert not r.reabrir_cruce and r.intervenciones == []
    assert r.documentos[0].datos.direccion.normalizado == "CALLE HIDALGO 120 CENTRO TULTEPEC"


def test_propietario_abreviado_con_cita_real_no_interviene():
    l = _leido("p.pdf", TipoDocumento.PREDIAL, "CONTRIBUYENTE: MA. GUADALUPE PEREZ SOTO")
    prop = _c("MARIA GUADALUPE PEREZ", "CONTRIBUYENTE: MA. GUADALUPE PEREZ SOTO", "p.pdf")
    r = auditor.auditar([l], [_analizado(l, DatosInmueble(propietario=prop))])
    assert r.intervenciones == [] and r.documentos[0].datos.propietario.normalizado == "MARIA GUADALUPE PEREZ"


def test_superficie_300_contra_350_se_sigue_descartando():
    l = _leido("e.pdf", TipoDocumento.ESCRITURA, "SUPERFICIE TOTAL DE 300.00 M2")
    a = _analizado(l, DatosInmueble(superficie_terreno_m2=_c("350.00", "SUPERFICIE TOTAL DE 300.00 M2", "e.pdf")))
    r = auditor.auditar([l], [a])
    assert r.reabrir_cruce and r.documentos[0].datos.superficie_terreno_m2.normalizado is None
    assert "AUD-02" in _aud(r.documentos[0])[0].explicacion


@pytest.mark.parametrize("valor,texto", [("1250.50", "SUPERFICIE DE 1,250.50 M2"), ("1,250.50 m2", "SUPERFICIE 1250.50"),
                                         ("12500.00", "SUPERFICIE DE 1-25-00 HAS")])
def test_superficie_con_otro_formato_no_interviene(valor, texto):
    l = _leido("e.pdf", TipoDocumento.ESCRITURA, texto)
    r = auditor.auditar([l], [_analizado(l, DatosInmueble(superficie_terreno_m2=_c(valor, texto, "e.pdf")))])
    assert r.intervenciones == [] and not r.reabrir_cruce


@pytest.mark.parametrize("campo,valor,texto", [("clave_catastral", "0770431012000000", "CLAVE 077 04 310 12 00 0000"),
                                               ("numero_oficial", "104-A", "NUMERO OFICIAL 104 A"),
                                               ("numero_oficial", "S/N", "CALLE FRESNO S/N")])
def test_clave_y_numero_con_otro_formato_no_intervienen(campo, valor, texto):
    l = _leido("a.pdf", TipoDocumento.ALINEAMIENTO, texto)
    r = auditor.auditar([l], [_analizado(l, DatosInmueble(**{campo: _c(valor, texto, "a.pdf")}))])
    assert r.intervenciones == []
