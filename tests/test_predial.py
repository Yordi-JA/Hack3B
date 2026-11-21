"""Pruebas del agente Predial. No llaman a la API: el LLM se sustituye por una respuesta fija."""
from datetime import date

import pytest

from expedientes.agentes import predial
from expedientes.agentes.predial import _Dato, _PredialLLM
from expedientes.schemas import Contexto, DocumentoLeido, EstadoRegla, Legibilidad, Pagina, Severidad, TipoDocumento

TEXTO = """MUNICIPIO DE OCOTLÁN DE LAS TORRES, ESTADO DE MÉXICO
TESORERÍA MUNICIPAL · CATASTRO E IMPUESTO PREDIAL
FOLIO: TM-2023-345031
FECHA DE PAGO: 14/01/2023 13:33
CLAVE CATASTRAL | 077 04 310 12 00 0000
PROPIETARIO / POSEEDOR | PEÑALOZA RUIZ SILVIA ADRIANA
UBICACIÓN | AV DE LAS TORRES SN LT 12 MZ 3, COL. EL MIRADOR
SUPERFICIE TERRENO (M²) | 300.00
USO DEL PREDIO | BALDÍO URBANO
2023 | 1 | 6 | 2,170.80 | 160.80 | 0.00 | 0.00 | -321.60 | 2,010.00
OBSERVACIONES: EJERCICIOS 2024 Y 2025 PENDIENTES DE PAGO
PAGADO CAJA 3 · TESORERÍA 10 ENE 2023"""

NULO = _Dato(valor=None, cita=None, pagina=None)


def _d(valor, cita=None, pagina=1):
    return _Dato(valor=valor, cita=cita, pagina=pagina)


def _respuesta(**campos) -> _PredialLLM:
    base = {n: NULO for n in _PredialLLM.model_fields}
    base.update(campos)
    return _PredialLLM(**base)


def _doc(legibilidad=Legibilidad.BUENA, texto=TEXTO) -> DocumentoLeido:
    return DocumentoLeido(archivo="02 Predial!!.pdf", tipo=TipoDocumento.PREDIAL, confianza_tipo=1.0,
                          legibilidad=legibilidad, paginas=[Pagina(numero=1, texto=texto)], paginas_totales=1)


def _hallazgo(analizado, id_regla):
    return next(h for h in analizado.hallazgos if h.id_regla == id_regla)


@pytest.fixture
def llm_falso(monkeypatch):
    def poner(respuesta):
        monkeypatch.setattr(predial, "_extraer", lambda doc, paginas: respuesta)
    return poner


CTX_2025 = Contexto(fecha_referencia=date(2025, 6, 30))


# ---------------------------------------------------------------- normalización

@pytest.mark.parametrize("entrada,esperado", [
    ("26/01/2025 12:21", "2025-01-26"), ("09-01-2024 / 12:56:16", "2024-01-09"), ("2025-03-14", "2025-03-14"),
    ("16 ENE 2025", "2025-01-16"), ("28ENE25", "2025-01-28"), ("19 de febrero de 2025", "2025-02-19"),
    ("DIECINUEVE DE FEBRERO", None),
])
def test_fecha(entrada, esperado):
    assert predial._fecha_iso(entrada) == esperado


def test_superficie_y_claves():
    assert predial._superficie("1,250.50 m2") == "1250.50"
    assert predial._superficie("245,00") == "245.00"
    assert predial._superficie("0.0") is None  # 0 no sirve para el cruce
    assert predial._clave("077 04 310 12 00 0000") == "0770431012000000"
    assert predial._clave("U-02946") is None  # cuenta, no clave catastral
    assert predial._cuenta("U-02946") == "U02946"
    assert predial._anio_ejercicio("ENE-DIC 2024") == "2024"
    assert predial._anio_ejercicio("2025-2025") == "2025"
    assert predial._entidad("Estado de México") == "MEXICO"
    assert predial._entidad("HIDALGO") == "HIDALGO"
    assert predial._municipio("H. Ayuntamiento de Tepotzotlán") == "TEPOTZOTLAN"


def test_localizar_ignora_acentos_y_puntuacion_y_devuelve_texto_original():
    paginas = [Pagina(numero=1, texto=TEXTO)]
    n, i, f = predial._localizar("superficie terreno (m2) 300.00", paginas)
    assert n == 1 and TEXTO[i:f] == "SUPERFICIE TERRENO (M²) | 300.00"
    assert predial._localizar("PENALOZA RUIZ", paginas) is not None
    assert predial._localizar("GARCIA LOPEZ", paginas) is None


# ---------------------------------------------------------------- agente completo

def test_detecta_adeudo_ejercicio_atrasado_y_sello_anterior_al_pago(llm_falso):
    llm_falso(_respuesta(
        propietario=_d("PEÑALOZA RUIZ SILVIA ADRIANA", "PROPIETARIO / POSEEDOR | PEÑALOZA RUIZ SILVIA ADRIANA"),
        clave_catastral=_d("077 04 310 12 00 0000", "CLAVE CATASTRAL | 077 04 310 12 00 0000"),
        superficie_terreno_m2=_d("300.00", "SUPERFICIE TERRENO (M²) | 300.00"),
        municipio=_d("OCOTLÁN DE LAS TORRES", "MUNICIPIO DE OCOTLÁN DE LAS TORRES"),
        entidad_federativa=_d("ESTADO DE MÉXICO", "OCOTLÁN DE LAS TORRES, ESTADO DE MÉXICO"),
        ejercicio_pagado=_d("2023", "2023 | 1 | 6 | 2,170.80"),
        fecha_pago=_d("14/01/2023", "FECHA DE PAGO: 14/01/2023 13:33"),
        fecha_sello=_d("10 ENE 2023", "TESORERÍA 10 ENE 2023"),
        adeudos=_d("EJERCICIOS 2024 Y 2025 PENDIENTES DE PAGO", "OBSERVACIONES: EJERCICIOS 2024 Y 2025 PENDIENTES DE PAGO"),
        uso_del_predio=_d("BALDÍO URBANO", "USO DEL PREDIO | BALDÍO URBANO"),
    ))
    r = predial.analizar(_doc(), CTX_2025)

    assert r.datos.entidad_federativa.normalizado == "MEXICO"
    assert r.datos.superficie_terreno_m2.normalizado == "300.00"
    assert r.datos.vigencia_hasta.valor is None  # el predial no tiene vigencia
    pre03 = _hallazgo(r, "PRE-03")  # solo reporta la fecha: un pago de 2023 no es incumplimiento por sí solo
    assert pre03.estado == EstadoRegla.CUMPLE and "14/01/2023" in pre03.explicacion
    assert _hallazgo(r, "PRE-04").estado == EstadoRegla.NO_CUMPLE
    assert _hallazgo(r, "PRE-05").estado == EstadoRegla.NO_CUMPLE
    assert "baldío" in _hallazgo(r, "PRE-08").explicacion
    for h in r.hallazgos:  # toda evidencia es texto literal del documento
        for e in h.evidencias:
            assert e.cita in TEXTO


def test_descarta_datos_inventados(llm_falso):
    llm_falso(_respuesta(
        propietario=_d("JUAN PÉREZ LÓPEZ", "PROPIETARIO JUAN PÉREZ LÓPEZ"),        # no está en el texto
        superficie_terreno_m2=_d("300.00", "superficie de trescientos metros"),  # cita mala, valor real
    ))
    r = predial.analizar(_doc(), CTX_2025)
    assert r.datos.propietario.valor is None
    assert "propietario" in _hallazgo(r, "PRE-09").explicacion
    sup = r.datos.superficie_terreno_m2
    assert sup.normalizado == "300.00" and sup.confianza == predial.CONF_SOLO_VALOR and "300.00" in sup.evidencia.cita


def test_ilegible_no_llama_al_llm(llm_falso, monkeypatch):
    def prohibido(*_):
        raise AssertionError("no debe llamar al LLM")
    monkeypatch.setattr(predial, "_extraer", prohibido)
    r = predial.analizar(_doc(Legibilidad.ILEGIBLE, texto=""), CTX_2025)
    assert [h.id_regla for h in r.hallazgos] == ["PRE-ILEG"]
    assert r.hallazgos[0].estado == EstadoRegla.NO_EVALUABLE and r.datos.propietario.valor is None


def test_ejercicio_vigente_y_sin_adeudo(llm_falso):
    texto = "PAGO DE IMPUESTO PREDIAL 2025\nNO PRESENTA NINGÚN ADEUDO DEL IMPUESTO MENCIONADO"
    llm_falso(_respuesta(
        ejercicio_pagado=_d("2025", "PAGO DE IMPUESTO PREDIAL 2025"),
        adeudos=_d("NO PRESENTA NINGÚN ADEUDO", "NO PRESENTA NINGÚN ADEUDO DEL IMPUESTO MENCIONADO"),
    ))
    r = predial.analizar(_doc(texto=texto), CTX_2025)
    assert _hallazgo(r, "PRE-03").estado == EstadoRegla.CUMPLE
    assert _hallazgo(r, "PRE-04").estado == EstadoRegla.CUMPLE
    pre02 = _hallazgo(r, "PRE-02")  # sin clave ni cuenta: dato ausente, no incumplimiento
    assert pre02.estado == EstadoRegla.NO_EVALUABLE and pre02.severidad == Severidad.REVISION


def test_identificador_sin_descripcion(llm_falso):
    texto = "PREDIO: U-05261 VALOR CATASTRAL: $ 184,320.55\nPREDIO: U-02946 | VALOR CATASTRAL: $ 63,915.20"
    llm_falso(_respuesta(
        numero_cuenta=_d("U-05261", "PREDIO: U-05261 VALOR CATASTRAL"),
        otras_cuentas=_d("U-02946 (RANGEL SOTO LUIS), valor catastral $ 63,915.20",
                         "PREDIO: U-02946 | VALOR CATASTRAL: $ 63,915.20"),
    ))
    r = predial.analizar(_doc(texto=texto), CTX_2025)
    assert r.datos.especificos["otras_cuentas"].valor == "U-02946"
    assert _hallazgo(r, "PRE-07").estado == EstadoRegla.NO_CUMPLE


def test_embargo_es_rechazo_directo(llm_falso):
    texto = "OBSERVACIONES: PREDIO CON EMBARGO DERIVADO DEL PROCEDIMIENTO ADMINISTRATIVO DE EJECUCIÓN"
    llm_falso(_respuesta(embargo=_d("PREDIO CON EMBARGO", "PREDIO CON EMBARGO DERIVADO DEL PROCEDIMIENTO")))
    h = _hallazgo(predial.analizar(_doc(texto=texto), CTX_2025), "PRE-10")
    assert h.estado == EstadoRegla.NO_CUMPLE and h.severidad == Severidad.BLOQUEANTE
    assert h.evidencias[0].cita in texto


def test_embargo_dentro_del_texto_de_adeudos(llm_falso):
    texto = "ADEUDO 2023-2024 EN PROCEDIMIENTO ADMINISTRATIVO DE EJECUCIÓN"
    llm_falso(_respuesta(adeudos=_d(texto, texto)))
    assert _hallazgo(predial.analizar(_doc(texto=texto), CTX_2025), "PRE-10").severidad == Severidad.BLOQUEANTE


def test_leyenda_generica_no_es_embargo(llm_falso):
    texto = "EL PAGO EXTEMPORÁNEO DARÁ LUGAR AL PROCEDIMIENTO ADMINISTRATIVO DE EJECUCIÓN\nEN CASO DE QUE SU PREDIO NO SEA BALDÍO ACUDA A CATASTRO"
    llm_falso(_respuesta())  # el modelo no reporta embargo ni uso: la letra chica no debe disparar reglas
    r = predial.analizar(_doc(texto=texto), CTX_2025)
    assert not [h for h in r.hallazgos if h.id_regla in ("PRE-08", "PRE-10")]


@pytest.mark.parametrize("uso,clave", [("BALDÍO URBANO", "baldío"), ("AGROPECUARIO", "no urbano"),
                                       ("EJIDAL", "dominio pleno"), ("RÚSTICO", "no urbano")])
def test_usos_de_riesgo_piden_revision(llm_falso, uso, clave):
    texto = f"USO DEL PREDIO | {uso}"
    llm_falso(_respuesta(uso_del_predio=_d(uso, texto)))
    h = _hallazgo(predial.analizar(_doc(texto=texto), CTX_2025), "PRE-08")
    assert h.estado == EstadoRegla.NO_CUMPLE and h.severidad == Severidad.REVISION and clave in h.explicacion


def test_uso_habitacional_o_comercial_cumple(llm_falso):
    texto = "USO DEL PREDIO | COMERCIAL"
    llm_falso(_respuesta(uso_del_predio=_d("COMERCIAL", texto)))
    assert _hallazgo(predial.analizar(_doc(texto=texto), CTX_2025), "PRE-08").estado == EstadoRegla.CUMPLE


def test_construccion_cero_pide_revision(llm_falso):
    texto = "SUPERFICIE CONSTRUCCIÓN (M²) | 0.00"
    llm_falso(_respuesta(superficie_construccion_m2=_d("0.00", texto)))
    h = _hallazgo(predial.analizar(_doc(texto=texto), CTX_2025), "PRE-11")
    assert h.estado == EstadoRegla.NO_CUMPLE and h.severidad == Severidad.REVISION


def test_construccion_registrada_cumple(llm_falso):
    texto = "Superficie construcción propia:98.00"
    llm_falso(_respuesta(superficie_construccion_m2=_d("98.00", texto)))
    assert _hallazgo(predial.analizar(_doc(texto=texto), CTX_2025), "PRE-11").estado == EstadoRegla.CUMPLE
