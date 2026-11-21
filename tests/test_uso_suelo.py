"""Pruebas del agente de Uso de Suelo sin llamar a la API: el LLM se sustituye por un stub.

El texto de la licencia es inventado (regla 06: los documentos del reto no van al repo).
"""
from datetime import date

import pytest

from expedientes.agentes import uso_suelo as us
from expedientes.schemas import (
    Contexto,
    DocumentoLeido,
    EstadoRegla,
    Legibilidad,
    Pagina,
    Severidad,
    TipoDocumento,
)

ARCHIVO = "Uso de Suelo PRUEBA.pdf"
P1 = """H. AYUNTAMIENTO DE SAN PRUEBA
GOBIERNO MUNICIPAL 2022-2024
LICENCIA DE USO DEL SUELO EXPEDIENTE No: LUS/045/2023
San Prueba, Estado de México a quince de marzo del dos mil veintitrés.
La Dirección de Desarrollo Urbano del Municipio de San Prueba expide la presente LICENCIA DE USO DEL SUELO,
con vigencia del QUINCE DE MARZO DEL DOS MIL VEINTITRÉS AL QUINCE DE MARZO DEL DOS MIL VEINTICUATRO,
a favor de ANA MARÍA LÓPEZ RUIZ, en relación al predio ubicado en: CALLE ROBLE No. 12, COLONIA CENTRO,
con clave catastral: 001 02 003 04 00 0000 con una superficie total de predio de 350.00 M²
USO DE SUELO: CU-100-B. USOS PERMITIDOS: COMERCIO DE PRODUCTOS Y SERVICIOS BÁSICOS, ABARROTES."""
P2 = """RESTRICCIONES: Esta licencia NO autoriza construcción alguna.
Plaza Juárez No. 1, Colonia Centro, San Prueba, Estado de México"""


def _doc(legibilidad=Legibilidad.BUENA, paginas=None) -> DocumentoLeido:
    paginas = paginas if paginas is not None else [Pagina(numero=1, texto=P1), Pagina(numero=2, texto=P2)]
    return DocumentoLeido(archivo=ARCHIVO, tipo=TipoDocumento.USO_SUELO, confianza_tipo=0.95,
                          legibilidad=legibilidad, paginas=paginas, paginas_totales=len(paginas))


def _c(valor, cita=None, pagina=1, confianza=0.9, **kw):
    cls = us._FechaLLM if "iso" in kw else us._CampoLLM
    return cls(valor=valor, cita=cita or valor, pagina=pagina, confianza=confianza, **kw)


def _extraccion(**cambios) -> us._UsoSueloLLM:
    base = dict(
        propietario=_c("ANA MARÍA LÓPEZ RUIZ"),
        direccion=_c("CALLE ROBLE No. 12, COLONIA CENTRO"),
        entidad_federativa=_c("Estado de México", cita="San Prueba, Estado de México"),
        municipio=_c("San Prueba", cita="Municipio de San Prueba"),
        superficie_terreno_m2=_c("350.00 M²", cita="superficie total de predio de 350.00 M²"),
        clave_catastral=_c("001 02 003 04 00 0000"),
        fecha_emision=_c("quince de marzo del dos mil veintitrés", iso="2023-03-15"),
        vigencia_hasta=_c("QUINCE DE MARZO DEL DOS MIL VEINTICUATRO", iso="2024-03-15"),
        autoridad_emisora=_c("Dirección de Desarrollo Urbano del Municipio de San Prueba"),
        folio=_c("LUS/045/2023"),
        periodo_administracion=_c("2022-2024", cita="GOBIERNO MUNICIPAL 2022-2024"),
        uso_autorizado=_c("COMERCIO DE PRODUCTOS Y SERVICIOS BÁSICOS, ABARROTES"),
        clave_uso=_c("CU-100-B"),
        condicionantes=[_c("NO autoriza construcción", cita="Esta licencia NO autoriza construcción alguna", pagina=2)],
        compatibilidad_comercial=us._Compatibilidad.COMPATIBLE,
        compatibilidad_justificacion="Permite comercio de productos básicos y abarrotes.",
        compatibilidad_cita="USOS PERMITIDOS: COMERCIO DE PRODUCTOS Y SERVICIOS BÁSICOS, ABARROTES",
        compatibilidad_pagina=1,
    )
    base.update(cambios)
    return us._UsoSueloLLM(**base)


@pytest.fixture
def llm_falso(monkeypatch):
    """Sustituye la llamada al LLM; devuelve la lista donde se registran las llamadas."""
    llamadas = []

    def usar(extraccion):
        def _extraer(doc, ctx):
            llamadas.append(doc.archivo)
            return extraccion
        monkeypatch.setattr(us, "_extraer", _extraer)
        return llamadas
    return usar


def _hallazgo(resultado, id_regla):
    return next(h for h in resultado.hallazgos if h.id_regla == id_regla)


CTX_2023 = Contexto(fecha_referencia=date(2023, 10, 1))
CTX_2026 = Contexto(fecha_referencia=date(2026, 11, 21))


# ---------------------------------------------------------------- normalizadores

@pytest.mark.parametrize("entrada, esperado", [
    ("Estado de México", "MEXICO"),
    ("ESTADO DE MÉXICO", "MEXICO"),
    ("México", "MEXICO"),
    ("Hidalgo", "HIDALGO"),
    ("Estado de Hidalgo", "HIDALGO"),
    ("Ciudad de México", "CIUDAD DE MEXICO"),
    ("CDMX", "CIUDAD DE MEXICO"),
    ("Querétaro", "QUERETARO"),
    ("Estado Libre y Soberano de México", "MEXICO"),
    ("Tultepec", None),
    (None, None),
])
def test_normalizar_entidad(entrada, esperado):
    assert us._normalizar_entidad(entrada) == esperado


@pytest.mark.parametrize("entrada, esperado", [
    ("Municipio de Tepeji del Río", "TEPEJI DEL RIO"),
    ("H. Ayuntamiento de Villa del Carbón", "VILLA DEL CARBON"),
    ("Tultepec", "TULTEPEC"),
])
def test_normalizar_municipio(entrada, esperado):
    assert us._normalizar_municipio(entrada) == esperado


@pytest.mark.parametrize("valor, iso, esperado", [
    ("15/03/2023", None, "2023-03-15"),
    ("15 de marzo de 2023", None, "2023-03-15"),
    ("28 de noviembre del 2023", None, "2023-11-28"),
    ("quince de marzo del dos mil veintitrés", "2023-03-15", "2023-03-15"),
    ("quince de marzo del dos mil veintitrés", "2023-02-30", None),
    ("sin fecha", None, None),
])
def test_fecha_iso(valor, iso, esperado):
    assert us._fecha_iso(valor, iso) == esperado


def test_verificar_cita_corta_y_larga():
    paginas = _doc().paginas
    assert us._verificar_cita("ESTADO DE MEXICO", None, paginas) == 1  # sin acentos también calza
    assert us._verificar_cita("Esta licencia NO autoriza construcción alguna", 1, paginas) == 2
    assert us._verificar_cita("Estado de Jalisco", None, paginas) is None


# ---------------------------------------------------------------- agente completo

def test_licencia_compatible_y_vigente(llm_falso):
    llm_falso(_extraccion())
    r = us.analizar(_doc(), CTX_2023)

    assert r.datos.entidad_federativa.normalizado == "MEXICO"
    assert r.datos.entidad_federativa.evidencia.pagina == 1
    assert r.datos.municipio.normalizado == "SAN PRUEBA"
    assert r.datos.propietario.normalizado == "LOPEZ RUIZ ANA MARIA"
    assert r.datos.superficie_terreno_m2.normalizado == "350.00"
    assert r.datos.vigencia_hasta.normalizado == "2024-03-15"
    assert r.datos.especificos["condicionante_1"].evidencia.pagina == 2
    assert _hallazgo(r, "USO-01").estado == EstadoRegla.CUMPLE
    assert _hallazgo(r, "USO-02").estado == EstadoRegla.CUMPLE
    assert _hallazgo(r, "USO-03").estado == EstadoRegla.CUMPLE
    assert all(h.evidencias for h in r.hallazgos if h.estado == EstadoRegla.CUMPLE
               and h.id_regla != "USO-04")
    assert 0 < r.confianza <= 1


def test_vigencia_vencida_es_bloqueante(llm_falso):
    llm_falso(_extraccion())
    h = _hallazgo(us.analizar(_doc(), CTX_2026), "USO-02")
    assert (h.estado, h.severidad) == (EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE)
    assert "15/03/2024" in h.explicacion


def test_incompatible_es_bloqueante(llm_falso):
    llm_falso(_extraccion(compatibilidad_comercial=us._Compatibilidad.INCOMPATIBLE))
    h = _hallazgo(us.analizar(_doc(), CTX_2023), "USO-01")
    assert (h.estado, h.severidad) == (EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE)


def test_compatible_sin_cita_verificable_no_cumple_a_ciegas(llm_falso):
    llm_falso(_extraccion(compatibilidad_cita="AUTORIZA TIENDA DE AUTOSERVICIO",
                          uso_autorizado=_c("COMERCIAL", cita="USO: COMERCIAL")))
    h = _hallazgo(us.analizar(_doc(), CTX_2023), "USO-01")
    assert h.estado == EstadoRegla.NO_EVALUABLE


def test_cita_inventada_deja_el_dato_sin_normalizado(llm_falso):
    llm_falso(_extraccion(entidad_federativa=_c("Hidalgo", cita="ESTADO DE HIDALGO")))
    r = us.analizar(_doc(), CTX_2023)
    assert r.datos.entidad_federativa.valor == "Hidalgo"
    assert r.datos.entidad_federativa.normalizado is None
    assert r.datos.entidad_federativa.evidencia is None


def test_folio_de_otro_anio_sugiere_alteracion(llm_falso):
    llm_falso(_extraccion(fecha_emision=_c("15 de marzo de 2021", cita="LICENCIA DE USO DEL SUELO",
                                           iso="2021-03-15")))
    h = _hallazgo(us.analizar(_doc(), CTX_2023), "USO-03")
    assert (h.estado, h.severidad) == (EstadoRegla.NO_CUMPLE, Severidad.REVISION)
    assert "periodo de gobierno" in h.explicacion and "folio" in h.explicacion


def test_sin_vigencia_es_no_evaluable(llm_falso):
    llm_falso(_extraccion(vigencia_hasta=us._FechaLLM()))
    h = _hallazgo(us.analizar(_doc(), CTX_2023), "USO-02")
    assert h.estado == EstadoRegla.NO_EVALUABLE


def test_ilegible_no_llama_al_llm(llm_falso):
    llamadas = llm_falso(_extraccion())
    r = us.analizar(_doc(Legibilidad.ILEGIBLE), CTX_2023)
    assert llamadas == []
    assert r.datos.entidad_federativa.valor is None
    assert [h.estado for h in r.hallazgos] == [EstadoRegla.NO_EVALUABLE]


def test_sin_texto_no_llama_al_llm(llm_falso):
    llamadas = llm_falso(_extraccion())
    us.analizar(_doc(paginas=[Pagina(numero=1, texto="  ")]), CTX_2023)
    assert llamadas == []


def test_parcial_topa_la_confianza(llm_falso):
    llm_falso(_extraccion())
    assert us.analizar(_doc(Legibilidad.PARCIAL), CTX_2023).confianza <= us.TOPE_CONFIANZA_PARCIAL


def test_prompt_incluye_uso_requerido_y_marcadores():
    sistema, humano = us.construir_mensajes(_doc(), CTX_2023)
    assert CTX_2023.uso_requerido in sistema.content
    assert "[P1]" in humano.content and "[P2]" in humano.content
