"""Validación cruzada sobre el dictamen de ejemplo, sin LLM."""
import pytest

from expedientes.agentes import cruce
from expedientes.agentes import normalizar as nz
from expedientes.orquestador import analizar_expediente
from expedientes.schemas import Campo, Contexto, TipoDocumento


@pytest.fixture(autouse=True)
def sin_llm(monkeypatch):
    monkeypatch.setattr(cruce, "USAR_LLM", False)
    cruce._direcciones_llm.cache_clear()


def _docs():
    return [d.model_copy(deep=True) for d in analizar_expediente([], usar_ejemplo=True).documentos]


def _ids(incs):
    return sorted(i.id_regla for i in incs)


def test_ejemplo_solo_superficie():
    incs = cruce.validar_cruzado(_docs(), Contexto())
    assert _ids(incs) == ["CRU-SUP"]
    sup = incs[0]
    assert len(sup.valores) == 4 and all(v.evidencia for v in sup.valores)
    assert "432" in sup.descripcion and "450" in sup.descripcion


def test_superficie_dentro_de_tolerancia():
    docs = _docs()
    docs[1].datos.superficie_terreno_m2.normalizado = "446.5"  # < 2 %
    assert cruce.validar_cruzado(docs, Contexto()) == []


def test_numero_sin_numero_vs_quince():
    docs = _docs()
    docs[2].datos.numero_oficial = Campo(valor="S/N", normalizado="SN")
    incs = cruce.validar_cruzado(docs, Contexto())
    num = next(i for i in incs if i.id_regla == "CRU-NUM")
    assert "sin número" in num.descripcion


def test_documento_de_otro_inmueble():
    docs = _docs()
    otro = docs[3].datos
    otro.clave_catastral = Campo(valor="058 09 203 14 00 0000", normalizado="0580920314000000")
    otro.direccion = Campo(valor="Av. Ignacio Zaragoza 52, Villa del Carbón", normalizado="AV IGNACIO ZARAGOZA 52 VILLA DEL CARBON")
    incs = cruce.validar_cruzado(docs, Contexto())
    assert {"CRU-CLAVE", "CRU-DIR", "CRU-INM"} <= set(_ids(incs))
    inm = next(i for i in incs if i.id_regla == "CRU-INM")
    assert docs[3].archivo in inm.descripcion


def test_ignora_otro_y_vacios():
    docs = _docs()
    docs[0].tipo = TipoDocumento.OTRO
    docs[0].datos.superficie_terreno_m2.normalizado = "999"
    docs[2].datos.superficie_terreno_m2 = Campo()
    incs = cruce.validar_cruzado(docs, Contexto())
    sup = next(i for i in incs if i.id_regla == "CRU-SUP")
    assert {v.archivo for v in sup.valores} == {docs[1].archivo, docs[3].archivo}


def test_normalizacion():
    assert nz.nombres_equivalentes("CORTES PENA MA. TERESA ELENA", "C. María Teresa Elena Cortés Peña")
    assert nz.nombres_equivalentes("ROSA ELENA PAREDES LIMON, HECTOR PAREDES LIMON Y OSCAR PAREDES LIMON",
                                   "HECTOR PAREDES LIMON")
    assert not nz.nombres_equivalentes("RAUL ESTRADA VEGA", "MARCOS TELLEZ OROPEZA")
    assert nz.numero_oficial("Número oficial: 15 (QUINCE)") == "15"
    assert nz.numero_oficial("S/N") == "SN"
    assert nz.superficie("1,039.71 m2") == 1039.71
    assert nz.superficie("245,00 m²") == 245.0
    assert nz.claves_equivalentes(nz.clave_catastral("073 02 218 05 00 0000"), nz.clave_catastral("0730221805"))
    assert nz.clave_catastral("U-04817") is None
    assert str(nz.fecha("Tepeji del Rio, a 21 de ABRIL de 2025")) == "2025-04-21"
    assert cruce._dir_equiv("JOSEFA ORTIZ DE DOMINGUEZ, NUMERO 24, COL. LAZARO CARDENAS",
                            "JOSEFA ORTIZ DE DOMINGEZ, SIN NUMERO, LOTE 7, COLONIA LÁZARO CÁRDENAS")


def test_llm_de_direcciones_tiene_tope_y_usa_disco(tmp_path, monkeypatch):
    """Zona gris: como mucho MAX_LLM_POR_EXPEDIENTE llamadas; lo guardado en disco no cuesta."""
    monkeypatch.setattr(cruce, "USAR_LLM", True)
    monkeypatch.setattr(cruce, "_ruta_veredictos", lambda: tmp_path / "v.json")
    llamadas = []

    class FalsoLLM:
        def with_structured_output(self, *a, **k):
            return self

        def invoke(self, *a, **k):
            llamadas.append(1)
            return cruce._Veredicto(misma_direccion=True, razon="x")

    import expedientes.config as config
    monkeypatch.setattr(config, "get_llm", lambda **k: FalsoLLM())
    cruce._llamadas_restantes = 1
    assert cruce._direcciones_llm("A 1", "B 2") is True
    assert cruce._direcciones_llm("C 3", "D 4") is None       # tope agotado: sin llamada
    cruce._direcciones_llm.cache_clear()
    assert cruce._direcciones_llm("A 1", "B 2") is True       # sale del disco
    assert len(llamadas) == 1
