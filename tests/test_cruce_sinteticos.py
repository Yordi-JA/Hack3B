"""Validación cruzada sobre los expedientes sintéticos del reto, con los datos tal como vienen
en los documentos (transcritos a mano, sin LLM). Esperado:

- ""  (San Jerónimo Atlaco): los 4 documentos coinciden -> sin inconsistencias.
- "!!" (Ocotlán de las Torres): los 4 coinciden (sus problemas son de cada documento) -> nada.
- "v"  (Huehuetlán del Monte): el predial es de OTRO inmueble (clave ...223 19..., Jorge Armando,
        Laureles 51, 290 m²) -> CRU-CLAVE, CRU-PROP, CRU-SUP, CRU-NUM y CRU-INM señalando el predial.
"""
import pytest

from expedientes.agentes import cruce
from expedientes.schemas import (
    Campo, Contexto, DatosInmueble, DocumentoAnalizado, Evidencia, Legibilidad, TipoDocumento,
)

T = TipoDocumento


@pytest.fixture(autouse=True)
def sin_llm(monkeypatch):
    monkeypatch.setattr(cruce, "USAR_LLM", False)
    cruce._direcciones_llm.cache_clear()


def _doc(archivo, tipo, **campos):
    datos = DatosInmueble()
    for nombre, valor in campos.items():
        setattr(datos, nombre, Campo(valor=valor, normalizado=valor, confianza=0.9,
                                     evidencia=Evidencia(archivo=archivo, pagina=1, cita=valor)))
    return DocumentoAnalizado(archivo=archivo, tipo=tipo, confianza_tipo=0.98,
                              legibilidad=Legibilidad.BUENA, datos=datos, confianza=0.9)


def _base():
    return [
        _doc("01 Escritura.pdf", T.ESCRITURA,
             propietario="ROSA MARÍA QUINTANAR LEDESMA",
             direccion="Calle Fresno No. 28, Lote 14, Manzana 6, Col. La Loma, Municipio de San Jerónimo Atlaco, Estado de México",
             superficie_terreno_m2="245.00 metros cuadrados", clave_catastral="207 15 088 06 00 0000", numero_oficial="28"),
        _doc("02 Predial.pdf", T.PREDIAL,
             propietario="QUINTANAR LEDESMA ROSA MARIA", direccion="FRESNO 28, COL. LA LOMA",
             superficie_terreno_m2="245.00", clave_catastral="207 15 088 06 00 0000", numero_oficial="28"),
        _doc("03 Alineamiento y Numero Oficial.pdf", T.ALINEAMIENTO,
             propietario="C. ROSA MARÍA QUINTANAR LEDESMA",
             direccion="Calle Fresno No. 28, Lote 14, Manzana 6, Col. La Loma, Municipio de San Jerónimo Atlaco",
             superficie_terreno_m2="245.00 m²", clave_catastral="207 15 088 06 00 0000", numero_oficial="28"),
        _doc("04 Licencia de Uso de Suelo.pdf", T.USO_SUELO,
             propietario="ROSA MARÍA QUINTANAR LEDESMA",
             direccion="Calle Fresno No. 28, Lote 14, Manzana 6, Col. La Loma",
             superficie_terreno_m2="245.00 m²", clave_catastral="207 15 088 06 00 0000", numero_oficial="28"),
    ]


def _bang():
    return [
        _doc("01 Escritura!!.pdf", T.ESCRITURA,
             propietario="SILVIA ADRIANA PEÑALOZA RUIZ",
             direccion="Avenida de las Torres No. S/N, Lote 12, Manzana 3, Col. El Mirador, Municipio de Ocotlán de las Torres",
             superficie_terreno_m2="300.00 metros cuadrados", clave_catastral="077 04 310 12 00 0000", numero_oficial="S/N"),
        _doc("02 Predial!!.pdf", T.PREDIAL,
             propietario="PEÑALOZA RUIZ SILVIA ADRIANA", direccion="AV DE LAS TORRES SN LT 12 MZ 3, COL. EL MIRADOR",
             superficie_terreno_m2="300.00", clave_catastral="077 04 310 12 00 0000", numero_oficial="SN"),
        _doc("03 Alineamiento y Numero Oficial!!.pdf", T.ALINEAMIENTO,
             propietario="C. SILVIA ADRIANA PEÑALOZA RUIZ",
             direccion="Avenida de las Torres No. S/N, Lote 12, Manzana 3, Col. El Mirador",
             superficie_terreno_m2="300.00 m²", clave_catastral="077 04 310 12 00 0000", numero_oficial="S/N"),
        _doc("04 Licencia de Uso de Suelo!!.pdf", T.USO_SUELO,
             propietario="SILVIA ADRIANA PEÑALOZA RUIZ",
             direccion="Avenida de las Torres No. S/N, Lote 12, Manzana 3, Col. El Mirador",
             superficie_terreno_m2="300.00 m²", clave_catastral="077 04 310 12 00 0000", numero_oficial="S/N"),
    ]


def _v():
    return [
        _doc("01 Escriturav.pdf", T.ESCRITURA,
             propietario="JUAN CARLOS BENÍTEZ ARROYO",
             direccion="Calle Laureles No. 15, Lote 9, Manzana 4, Col. Villa de los Fresnos, Municipio de Huehuetlán del Monte",
             superficie_terreno_m2="312.50 metros cuadrados", clave_catastral="098 01 223 09 00 0000", numero_oficial="15"),
        _doc("02 Predialv.pdf", T.PREDIAL,
             propietario="BENITEZ ARROYO JORGE ARMANDO", direccion="LAURELES 51, COL. VILLA DE LOS FRESNOS",
             superficie_terreno_m2="290.00", clave_catastral="098 01 223 19 00 0000", numero_oficial="51"),
        _doc("03 Alineamiento y Numero Oficialv.pdf", T.ALINEAMIENTO,
             propietario="C. JUAN CARLOS BENÍTEZ ARROYO",
             direccion="Calle Laureles No. 15, Lote 9, Manzana 4, Col. Villa de los Fresnos",
             superficie_terreno_m2="312.50 m²", clave_catastral="098 01 223 09 00 0000", numero_oficial="15"),
        _doc("04 Licencia de Uso de Suelov.pdf", T.USO_SUELO,
             propietario="JUAN CARLOS BENÍTEZ ARROYO",
             direccion="Calle Laureles No. 15, Lote 9, Manzana 4, Col. Villa de los Fresnos",
             superficie_terreno_m2="312.50 m²", clave_catastral="098 01 223 09 00 0000", numero_oficial="15"),
    ]


@pytest.mark.parametrize("expediente", [_base, _bang], ids=["base", "bang"])
def test_expedientes_consistentes_sin_falsas_alarmas(expediente):
    assert cruce.validar_cruzado(expediente(), Contexto()) == []


def test_v_predial_de_otro_inmueble():
    incs = {i.id_regla: i for i in cruce.validar_cruzado(_v(), Contexto())}
    assert {"CRU-CLAVE", "CRU-PROP", "CRU-SUP", "CRU-NUM", "CRU-INM"} <= set(incs)
    assert "02 Predialv.pdf" in incs["CRU-INM"].descripcion
    for i in incs.values():  # cada inconsistencia trae qué dice cada documento y su evidencia
        assert all(v.evidencia for v in i.valores)
    assert "«15»" in incs["CRU-NUM"].descripcion and "«51»" in incs["CRU-NUM"].descripcion
    assert "7%" in incs["CRU-SUP"].descripcion  # 312.50 vs 290.00
