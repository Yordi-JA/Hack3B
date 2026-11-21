"""Reglas de Alineamiento sin LLM: la extracción se arma a mano a partir de las constancias sintéticas."""
from datetime import date

from expedientes.agentes import alineamiento as ali
from expedientes.agentes.alineamiento import DatoExtraido, ExtraccionAlineamiento
from expedientes.schemas import Contexto, DocumentoLeido, EstadoRegla, Legibilidad, Pagina, Severidad, TipoDocumento

ARCHIVO = "03 Alineamiento y Numero Oficial!!.pdf"
P1 = (
    "H. AYUNTAMIENTO CONSTITUCIONAL DE OCOTLÁN DE LAS TORRES Estado de México · Administración 2025-2027 "
    "DIRECCIÓN DE DESARROLLO URBANO Y OBRAS PÚBLICAS CONSTANCIA DE ALINEAMIENTO FOLIO: DDU/ALI/1504/2025 "
    "Ocotlán de las Torres, Estado de México, a 09 de junio de 2025. C. SILVIA ADRIANA PEÑALOZA RUIZ: Esta Dirección, "
    "en contestación a su solicitud, ha señalado el alineamiento que se indica en el siguiente croquis con ubicación en "
    "Avenida de las Torres No. S/N, Lote 12, Manzana 3, Col. El Mirador, Municipio de Ocotlán de las Torres, Estado de "
    "México. CLAVE CATASTRAL: 077 04 310 12 00 0000. SUP. 300.00 m² Alineamiento oficial: 15.00 m de frente a Avenida "
    "de las Torres. Restricción de construcción al frente: 0.00 m. OBSERVACIONES: EL PREDIO PRESENTA AFECTACIÓN DE "
    "4.00 M AL FRENTE POR AMPLIACIÓN DE LA AVENIDA DE LAS TORRES. SUPERFICIE AFECTADA: 60.00 M². NO SE PERMITE "
    "CONSTRUIR EN LA FRANJA AFECTADA. Vigencia: un año a partir de su expedición."
)


def _d(valor, cita=None, normalizado=None, pagina=1, confianza=0.9):
    return DatoExtraido(valor=valor, normalizado=normalizado, pagina=pagina, cita=cita or valor, confianza=confianza)


def _doc(legibilidad=Legibilidad.BUENA):
    return DocumentoLeido(archivo=ARCHIVO, tipo=TipoDocumento.ALINEAMIENTO, confianza_tipo=0.97,
                          legibilidad=legibilidad, paginas=[Pagina(numero=1, texto=P1)], paginas_totales=2)


def _ext(**cambios):
    base = dict(
        contiene_alineamiento=True, contiene_numero_oficial=False,
        propietario=_d("C. SILVIA ADRIANA PEÑALOZA RUIZ"),
        direccion=_d("Avenida de las Torres No. S/N, Lote 12, Manzana 3, Col. El Mirador"),
        superficie_terreno_m2=_d("300.00 m²", "SUP. 300.00 m²", "300"),
        clave_catastral=_d("077 04 310 12 00 0000", "CLAVE CATASTRAL: 077 04 310 12 00 0000"),
        fecha_emision=_d("09 de junio de 2025", normalizado="2025-06-09"),
        vigencia_texto=_d("un año a partir de su expedición"),
        autoridad_emisora=_d("DIRECCIÓN DE DESARROLLO URBANO Y OBRAS PÚBLICAS"),
        administracion=_d("Administración 2025-2027", normalizado="2025-2027"),
        alineamiento=_d("15.00 m de frente a Avenida de las Torres", "Alineamiento oficial: 15.00 m de frente a Avenida de las Torres"),
        afectaciones=_d("AFECTACIÓN DE 4.00 M AL FRENTE POR AMPLIACIÓN DE LA AVENIDA DE LAS TORRES"),
        superficie_afectada_m2=_d("60.00 M²", "SUPERFICIE AFECTADA: 60.00 M²", "60"),
    )
    base.update(cambios)
    return ExtraccionAlineamiento(**base)


def _regla(analizado, id_regla):
    return next(h for h in analizado.hallazgos if h.id_regla == id_regla)


def test_afectacion_y_vigencia_vigente():
    r = ali.construir(_ext(), _doc(), Contexto(fecha_referencia=date(2026, 1, 15)))
    assert r.tipo == TipoDocumento.ALINEAMIENTO
    assert _regla(r, "ALI-02").estado == EstadoRegla.CUMPLE           # vence 09/06/2026
    afect = _regla(r, "ALI-03")
    assert afect.estado == EstadoRegla.NO_CUMPLE and afect.severidad == Severidad.BLOQUEANTE
    assert afect.evidencias and afect.evidencias[0].archivo == ARCHIVO
    assert _regla(r, "ALI-07").estado == EstadoRegla.CUMPLE
    assert r.datos.vigencia_hasta.normalizado == "2026-06-09"
    assert r.datos.clave_catastral.normalizado == "0770431012000000"
    assert r.datos.superficie_terreno_m2.normalizado == "300.00"
    assert r.datos.especificos["afectaciones"].valor


def test_vencida_contra_fecha_referencia():
    r = ali.construir(_ext(), _doc(), Contexto(fecha_referencia=date(2026, 11, 21)))
    h = _regla(r, "ALI-02")
    assert h.estado == EstadoRegla.NO_CUMPLE and "09/06/2026" in h.explicacion


def test_vigencia_indefinida_y_sin_numero():
    ext = _ext(vigencia_texto=_d("vigente en tanto no existan modificaciones al plan municipal"),
               numero_oficial=_d("S/N", "Avenida de las Torres No. S/N"), contiene_numero_oficial=True,
               afectaciones=None, superficie_afectada_m2=None)
    r = ali.construir(ext, _doc(), Contexto(fecha_referencia=date(2026, 11, 21)))
    assert _regla(r, "ALI-02").estado == EstadoRegla.CUMPLE
    assert _regla(r, "ALI-01").estado == EstadoRegla.NO_CUMPLE
    assert _regla(r, "ALI-03").estado == EstadoRegla.CUMPLE
    assert r.datos.numero_oficial.normalizado == "SN"


def test_encabezado_no_cuadra_con_fecha():
    ext = _ext(administracion=_d("Administración 2019-2021", normalizado="2019-2021"))
    r = ali.construir(ext, _doc(), Contexto(fecha_referencia=date(2026, 1, 1)))
    assert _regla(r, "ALI-07").estado == EstadoRegla.NO_CUMPLE


def test_cita_inventada_baja_confianza():
    ext = _ext(propietario=_d("JUAN PÉREZ", "a favor de JUAN PÉREZ LÓPEZ"))
    no_ver = ali.verificar_citas(ext, _doc())
    assert no_ver == ["propietario"] and ext.propietario.confianza == 0.45
    r = ali.construir(ext, _doc(), Contexto(), no_ver)
    assert _regla(r, "ALI-EVI").estado == EstadoRegla.NO_EVALUABLE
    assert r.datos.propietario.valor == "JUAN PÉREZ" and r.datos.propietario.normalizado is None
    assert r.datos.direccion.normalizado  # los verificados conservan su normalizado


def test_ilegible_no_llama_al_llm(monkeypatch):
    monkeypatch.setattr(ali, "extraer", lambda doc: (_ for _ in ()).throw(AssertionError("no debe llamar al LLM")))
    r = ali.analizar(_doc(Legibilidad.ILEGIBLE), Contexto())
    assert r.confianza == 0 and r.datos.propietario.valor is None
    assert [h.estado for h in r.hallazgos] == [EstadoRegla.NO_EVALUABLE]


def test_solo_numero_oficial_no_penaliza_alineamiento():
    ext = ExtraccionAlineamiento(contiene_alineamiento=False, contiene_numero_oficial=True,
                                 numero_oficial=_d("15 (QUINCE)", "NÚMERO OFICIAL: 15 (QUINCE)"))
    r = ali.construir(ext, _doc(), Contexto())
    assert _regla(r, "ALI-01").estado == EstadoRegla.CUMPLE
    assert _regla(r, "ALI-04").severidad == Severidad.INFO
    assert r.datos.numero_oficial.normalizado == "15"


def test_evaluador_compara_campos():
    from expedientes.agentes.evaluar_alineamiento import comparar
    r = ali.construir(_ext(), _doc(), Contexto(fecha_referencia=date(2026, 1, 15)))
    verdad = {"propietario": "SILVIA ADRIANA PEÑALOZA RUIZ", "direccion": "Avenida de las Torres S/N, Col. El Mirador",
              "numero_oficial": None, "clave_catastral": "0770431012000000", "superficie_m2": 300.0,
              "fecha_emision": "2025-06-09", "vigencia_hasta": "2026-06-09", "afectaciones": "AFECTACIÓN DE 4.00 M",
              "contiene_alineamiento": True,
              "autoridad_emisora": "Dirección de Desarrollo Urbano y Obras Públicas - Ocotlán de las Torres"}
    res = comparar(verdad, r)
    assert all(x["estado"] == "ok" for x in res.values()), res
    verdad["superficie_m2"] = 450.0
    verdad["numero_oficial"] = "28"
    res = comparar(verdad, r)
    assert res["superficie_m2"]["estado"] == "distinto" and res["numero_oficial"]["estado"] == "faltó"


def test_entidad_y_municipio():
    assert ali.entidad("Edo. Méx.") == "MEXICO"
    assert ali.entidad("Estado Libre y Soberano de Hidalgo") == "HIDALGO"
    assert ali.entidad("Hgo.") == "HIDALGO"
    ext = _ext(municipio=_d("Ocotlán de las Torres"), entidad_federativa=_d("Estado de México"))
    r = ali.construir(ext, _doc(), Contexto())
    assert r.datos.municipio.normalizado == "OCOTLAN DE LAS TORRES"
    assert r.datos.entidad_federativa.normalizado == "MEXICO"


def test_vigencia_en_dias():
    ext = _ext(vigencia_texto=_d("ESTA LICENCIA TENDRA UNA VIGENCIA DE 365 DIAS A PARTIR DE LA FECHA DE SU EXPEDICION"),
               fecha_emision=_d("5 de noviembre de 2024", normalizado="2024-11-05"))
    assert ali.calcular_vencimiento(ext) == (date(2025, 11, 5), "calculada")


def test_respuesta_guardada_no_llama_a_la_api(tmp_path, monkeypatch):
    monkeypatch.setattr(ali, "CACHE_DIR", tmp_path)
    doc = _doc()
    entrada = f"Archivo: {doc.archivo}\n\n{ali._paginas_como_texto(doc)}"
    ruta, huella = ali._ruta_respuesta(doc, entrada)
    vacio = {"encontrado": False, "valor": "", "normalizado": "", "pagina": 0, "cita": "", "confianza": 0}
    resp = {n: (True if n.startswith("contiene_alineamiento") else False) if f.annotation is bool else dict(vacio)
            for n, f in ali.ExtraccionAlineamiento.model_fields.items()}
    resp["numero_oficial"] = {"encontrado": True, "valor": "210", "normalizado": "210", "pagina": 2,
                              "cita": "NÚMERO OFICIAL: 210", "confianza": 0.9}
    ruta.parent.mkdir(parents=True)
    ruta.write_text(__import__("json").dumps({"huella": huella, "respuesta": resp}), encoding="utf-8")
    monkeypatch.setattr(ali, "get_llm", lambda **k: (_ for _ in ()).throw(AssertionError("no debe llamar a la API")))
    ext = ali.extraer(doc)
    assert ext.numero_oficial.valor == "210" and ext.propietario is None


def test_riesgos_explicitos_cfe_invasion_lotes_y_restriccion():
    ext = _ext(afectaciones=None, superficie_afectada_m2=None,
               infraestructura=_d("LÍNEA DE ALTA TENSIÓN DE CFE CRUZA EL PREDIO"),
               invasion_via_publica=_d("LA BARDA INVADE LA BANQUETA"),
               lotes_sin_fusionar=_d("LOTES 12 Y 13 SIN FUSIONAR"),
               restricciones_construccion=_d("Restricción de construcción al frente: 3.00 m"))
    r = ali.construir(ext, _doc(), Contexto())
    assert _regla(r, "ALI-03").estado == EstadoRegla.CUMPLE
    assert _regla(r, "ALI-08").severidad == Severidad.BLOQUEANTE
    assert _regla(r, "ALI-09").severidad == Severidad.BLOQUEANTE
    assert _regla(r, "ALI-10").severidad == Severidad.REVISION
    assert _regla(r, "ALI-11").severidad == Severidad.INFO   # restricción no es afectación vial
    assert all(_regla(r, i).evidencias for i in ("ALI-08", "ALI-09", "ALI-10"))


def test_restriccion_cero_no_genera_ali11():
    r = ali.construir(_ext(restricciones_construccion=_d("Restricción de construcción al frente: 0.00 m")), _doc(), Contexto())
    assert not [h for h in r.hallazgos if h.id_regla == "ALI-11"]


def test_evaluador_autoridad_debe_nombrar_dependencia():
    from expedientes.agentes.evaluar_alineamiento import _iguales
    esperado = "Dirección de Desarrollo Urbano y Metropolitano - Tepotzotlán"
    assert _iguales("autoridad_emisora", esperado, "DIRECCIÓN DE DESARROLLO URBANO Y METROPOLITANO")
    assert not _iguales("autoridad_emisora", esperado, "H. AYUNTAMIENTO DE TEPOTZOTLÁN")
