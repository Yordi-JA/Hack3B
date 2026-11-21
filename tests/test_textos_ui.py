"""Textos que ve el equipo legal en la UI. Sin API."""
import pytest

from expedientes.agentes import cruce, dictamen
from expedientes.schemas import (Campo, Contexto, DatosInmueble, DocumentoAnalizado, Evidencia, Legibilidad,
                                 TipoDocumento)


def _doc(archivo, tipo, **campos):
    datos = DatosInmueble(**{k: Campo(valor=v, normalizado=v, confianza=0.9,
                                      evidencia=Evidencia(archivo=archivo, pagina=1, cita=v)) for k, v in campos.items()})
    return DocumentoAnalizado(archivo=archivo, tipo=tipo, confianza_tipo=1.0, legibilidad=Legibilidad.BUENA,
                              datos=datos, hallazgos=[], confianza=0.9)


@pytest.fixture
def inconsistencias(monkeypatch):
    monkeypatch.setattr(cruce, "USAR_LLM", False)
    docs = [_doc("e.pdf", TipoDocumento.ESCRITURA, propietario="CLAUDIA MENDEZ SALAZAR", numero_oficial="15",
                 clave_catastral="0980122309000000"),
            _doc("p.pdf", TipoDocumento.PREDIAL, propietario="JORGE BENITEZ ARROYO", numero_oficial="51",
                 clave_catastral="0980122319000000")]
    return docs, cruce.validar_cruzado(docs, Contexto())


def test_articulo_segun_el_campo(inconsistencias):
    _, incs = inconsistencias
    por_campo = {i.campo: i.descripcion for i in incs}
    assert por_campo["propietario"].startswith("El propietario no coincide")
    assert por_campo["numero_oficial"].startswith("El número oficial no coincide")
    assert por_campo["clave_catastral"].startswith("La clave catastral no coincide")


def test_resumen_del_dictamen_sin_nombres_internos(inconsistencias):
    docs, incs = inconsistencias
    d = dictamen.dictaminar("T", docs, [], incs, Contexto())
    assert "clave catastral" in d.resumen and "número oficial" in d.resumen
    assert "clave_catastral" not in d.resumen and "numero_oficial" not in d.resumen
