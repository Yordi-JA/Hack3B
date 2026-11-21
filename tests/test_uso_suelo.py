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
               and h.id_regla not in ("USO-04", "USO-08"))  # ausencias: no hay cita que mostrar
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
    llm_falso(_extraccion(fecha_emision=_c("15 de marzo de 2021", cita="expedida el 15 de marzo de 2021",
                                           iso="2021-03-15")))
    doc = _doc(paginas=[Pagina(numero=1, texto=P1 + "\nexpedida el 15 de marzo de 2021"), Pagina(numero=2, texto=P2)])
    h = _hallazgo(us.analizar(doc, CTX_2023), "USO-03")
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


def test_no_manda_paginas_de_otro_tipo_ni_vacias():
    paginas = [Pagina(numero=1, texto=P1), Pagina(numero=2, texto=""), Pagina(numero=3, texto="RECIBO PREDIAL"),
               Pagina(numero=4, texto=P2), Pagina(numero=5, texto="PLANO")]
    doc = _doc(paginas=paginas).model_copy(update={
        "notas": "Origen del texto: llm 5 pág. Contiene páginas de tipo predial: p3. "
                 "Contiene páginas de tipo alineamiento_numero_oficial: p5-p5."})
    assert [p.numero for p in us._paginas_con_texto(doc)] == [1, 4]


def test_respuesta_del_llm_se_reutiliza_del_disco(monkeypatch, tmp_path):
    monkeypatch.setattr(us, "DIR_ANALISIS", tmp_path)
    llamadas = []

    class LLMFalso:
        def with_structured_output(self, *a, **kw):
            return self

        def invoke(self, mensajes, config=None):
            llamadas.append(1)
            return _extraccion()

    monkeypatch.setattr(us, "get_llm", lambda **kw: LLMFalso())
    primera = us.analizar(_doc(), CTX_2023)
    segunda = us.analizar(_doc(), CTX_2026)  # otra fecha: cambian las reglas, no el prompt
    assert len(llamadas) == 1
    assert primera.datos == segunda.datos


# ---------------------------------------------------------------- criterios Tiendas 3B (USO-07..11)

P_CRITERIOS = P1 + """
SUPERFICIE MÁXIMA PARA COMERCIO: 120 M2 POR USO.
SUPERFICIE LIBRE DE CONSTRUCCIÓN: 50% LA SUPERFICIE DEL LOTE.
QUEDA PROHIBIDA LA VENTA DE BEBIDAS ALCOHÓLICAS EN ENVASE CERRADO.
Se reconoce el uso por DERECHOS ADQUIRIDOS conforme al plan anterior.
EL PREDIO SE UBICA DENTRO DE LA ZONA DE MONUMENTOS HISTÓRICOS DECLARADA POR EL INAH."""


def _doc_criterios():
    return _doc(paginas=[Pagina(numero=1, texto=P_CRITERIOS), Pagina(numero=2, texto=P2)])


def test_criterios_3b_detectan_banderas(llm_falso):
    llm_falso(_extraccion(
        superficie_maxima_giro_m2=_c("120 M2", cita="SUPERFICIE MÁXIMA PARA COMERCIO: 120 M2"),
        area_libre=_c("50%", cita="SUPERFICIE LIBRE DE CONSTRUCCIÓN: 50% LA SUPERFICIE DEL LOTE"),
        prohibiciones_giro=[_c("venta de bebidas alcohólicas en envase cerrado",
                               cita="QUEDA PROHIBIDA LA VENTA DE BEBIDAS ALCOHÓLICAS EN ENVASE CERRADO")],
        derechos_adquiridos=_c("DERECHOS ADQUIRIDOS", cita="Se reconoce el uso por DERECHOS ADQUIRIDOS"),
        zona_protegida=_c("ZONA DE MONUMENTOS HISTÓRICOS", cita="DENTRO DE LA ZONA DE MONUMENTOS HISTÓRICOS"),
    ))
    r = us.analizar(_doc_criterios(), CTX_2023)
    bloq = (EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE)
    for regla in ("USO-07", "USO-08", "USO-09"):
        h = _hallazgo(r, regla)
        assert (h.estado, h.severidad) == bloq, regla
        assert h.evidencias, regla
    for regla in ("USO-10", "USO-11"):
        h = _hallazgo(r, regla)
        assert (h.estado, h.severidad) == (EstadoRegla.NO_CUMPLE, Severidad.REVISION), regla


def test_criterios_3b_sin_banderas(llm_falso):
    llm_falso(_extraccion(cos=_c("70 %", cita="COS: 70 %")))
    r = us.analizar(_doc(paginas=[Pagina(numero=1, texto=P1 + "\nCOS: 70 %"), Pagina(numero=2, texto=P2)]), CTX_2023)
    assert _hallazgo(r, "USO-07").estado == EstadoRegla.NO_EVALUABLE
    assert _hallazgo(r, "USO-08").estado == EstadoRegla.CUMPLE
    h = _hallazgo(r, "USO-09")
    assert h.estado == EstadoRegla.CUMPLE and "30 %" in h.explicacion  # 100 - COS 70 %
    assert not [h for h in r.hallazgos if h.id_regla in ("USO-10", "USO-11")]


@pytest.mark.parametrize("m2, estado, severidad", [
    ("249 m2", EstadoRegla.NO_CUMPLE, Severidad.BLOQUEANTE),
    ("280 m2", EstadoRegla.CUMPLE, Severidad.REVISION),
    ("500 m2", EstadoRegla.CUMPLE, Severidad.INFO),
])
def test_superficie_comercial_umbral(llm_falso, m2, estado, severidad):
    cita = f"SUPERFICIE MAXIMA COMERCIAL {m2}"
    llm_falso(_extraccion(superficie_maxima_giro_m2=_c(m2, cita=cita)))
    doc = _doc(paginas=[Pagina(numero=1, texto=P1 + "\n" + cita), Pagina(numero=2, texto=P2)])
    h = _hallazgo(us.analizar(doc, CTX_2023), "USO-07")
    assert (h.estado, h.severidad) == (estado, severidad)


@pytest.mark.parametrize("s, esperado", [("20%", 20.0), ("70 %", 70.0), ("0.7", 70.0), ("1.4 VECES", 1.4), (None, None)])
def test_porcentaje(s, esperado):
    assert us._porcentaje(s) == esperado



# ---------------------------------------------------------------- verificación de valor en la cita

PAG_NOTARIA = [Pagina(numero=1, texto="TITULAR DE LA NOTARIA PUBLICA NUMERO 101 DEL ESTADO DE HIDALGO.\n"
                                      "EL INMUEBLE CUENTA CON UNA SUPERFICIE TOTAL DE TERRENO DE 450.00 M2 Y COLINDANCIAS.\n"
                                      "Fecha: 12 de marzo de 2025\n"
                                      "ESTACIONAMIENTO | 1 CAJÓN / 40 M²")]


@pytest.mark.parametrize("valor, cita, acepta", [
    ("450.00 m2", "DE 450.00 M2", True),
    ("Notaría 10", "NOTARIA PUBLICA NUMERO 10", False),                                     # 10 no es 101
    ("999.00 m2", "EL INMUEBLE CUENTA CON UNA SUPERFICIE TOTAL DE TERRENO DE 999.00 M2", False),  # valor inventado al final
    ("JUAN PEREZ", "TITULAR DE LA NOTARIA PUBLICA", False),                                 # cita real, valor ajeno
    ("450.00 M2", "EL INMUEBLE CUENTA CON UNA SUPERFICIE TOTAL DE TERRENO DE 450.00 M2", True),
    ("Notaría 101", "NOTARIA PUBLICA NUMERO 101", True),                                   # el modelo resume
])
def test_cita_debe_contener_el_valor(valor, cita, acepta):
    assert (us._verificar_cita(cita, 1, PAG_NOTARIA, valor) is not None) is acepta


def test_respaldo_por_valor_solo_si_es_distintivo():
    # Cita que el modelo juntó de una tabla: no calza, pero el valor largo sí está en el documento.
    campo = us._campo(_c("1 CAJÓN / 40 M²", cita="ESTACIONAMIENTO 1 CAJÓN / 40 M² POR LOCAL"), ARCHIVO, PAG_NOTARIA)
    assert campo.evidencia and campo.evidencia.cita == "ESTACIONAMIENTO | 1 CAJÓN / 40 M²"
    assert campo.confianza <= us.CONF_SOLO_VALOR
    # Número corto inventado: el único 12 es de una fecha. No debe pasar como verificado.
    corto = us._campo(_c("12", cita="NUMERO OFICIAL 12"), ARCHIVO, PAG_NOTARIA)
    assert corto.evidencia is None and corto.normalizado is None
