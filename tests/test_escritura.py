"""Tests del agente escritura.py. No llama al LLM: valida normalizadores,
selección de páginas, verificación de evidencia y aplicación de reglas ESC-.
"""
from __future__ import annotations

import pytest

from expedientes.agentes import escritura
from expedientes.agentes.escritura import (
    _CampoLLM,
    _aplicar_reglas,
    _construir_campo,
    _formatear_paginas,
    _normalizar_clave_catastral,
    _normalizar_direccion,
    _normalizar_fecha,
    _normalizar_nombre,
    _normalizar_numero,
    _normalizar_superficie,
    _resultado_ilegible,
    _seleccionar_paginas,
    _upper_sin_acentos,
    _verificar_cita,
)
from expedientes.schemas import (
    Campo,
    Contexto,
    DatosInmueble,
    DocumentoLeido,
    EstadoRegla,
    Evidencia,
    Legibilidad,
    Pagina,
    Severidad,
    TipoDocumento,
)


# ============================================================ normalizadores

class TestUpperSinAcentos:
    def test_quita_acentos_y_mayusculiza(self):
        assert _upper_sin_acentos("Nogal de los Olmos") == "NOGAL DE LOS OLMOS"
        assert _upper_sin_acentos("Méndez Salazar") == "MENDEZ SALAZAR"

    def test_colapsa_espacios(self):
        assert _upper_sin_acentos("  hola   mundo  ") == "HOLA MUNDO"

    def test_nulos(self):
        assert _upper_sin_acentos(None) is None
        assert _upper_sin_acentos("") is None
        assert _upper_sin_acentos("   ") is None


class TestNormalizarNombre:
    def test_apellidos_primero_con_tres_mas_tokens(self):
        assert _normalizar_nombre("Claudia Alejandra Méndez Salazar") == "MENDEZ SALAZAR CLAUDIA ALEJANDRA"

    def test_quita_prefijos(self):
        assert _normalizar_nombre("C. Juan López") == "LOPEZ JUAN"
        assert _normalizar_nombre("Lic. María Sánchez") == "SANCHEZ MARIA"

    def test_un_solo_apellido_y_un_nombre(self):
        assert _normalizar_nombre("Juan López") == "LOPEZ JUAN"

    def test_un_solo_token(self):
        assert _normalizar_nombre("Pedro") == "PEDRO"

    def test_nulos(self):
        assert _normalizar_nombre(None) is None
        assert _normalizar_nombre("") is None


class TestNormalizarDireccion:
    def test_quita_abreviaturas(self):
        r = _normalizar_direccion("Calle Nogal de los Olmos No. 214, Col. Jardines del Lago")
        assert r == "CALLE NOGAL DE LOS OLMOS 214, JARDINES DEL LAGO"

    def test_quita_numero_completo(self):
        assert "NUMERO" not in _normalizar_direccion("Av. Hidalgo Numero 45")
        assert "NUM" not in _normalizar_direccion("Av. Hidalgo Num. 45")

    def test_sin_acentos(self):
        assert "Á" not in (_normalizar_direccion("San Ángel") or "")

    def test_nulos(self):
        assert _normalizar_direccion(None) is None
        assert _normalizar_direccion("") is None


class TestNormalizarSuperficie:
    @pytest.mark.parametrize("entrada,esperado", [
        ("450.00 metros cuadrados", "450.00"),
        ("432 m²", "432.00"),
        ("432.00", "432.00"),
        ("1,250.50 m2", "1250.50"),
        ("1250,50", "1250.50"),
        ("SUP. 85.5 M2", "85.50"),
    ])
    def test_formatos_validos(self, entrada, esperado):
        assert _normalizar_superficie(entrada) == esperado

    def test_sin_numero(self):
        assert _normalizar_superficie("metros cuadrados") is None

    def test_nulos(self):
        assert _normalizar_superficie(None) is None
        assert _normalizar_superficie("") is None


class TestNormalizarClaveCatastral:
    def test_quita_espacios_y_guiones(self):
        assert _normalizar_clave_catastral("061 18 134 09 00 0000") == "0611813409000000"

    def test_mayusculiza_letras(self):
        assert _normalizar_clave_catastral("a1b2 c3") == "A1B2C3"

    def test_nulos(self):
        assert _normalizar_clave_catastral(None) is None


class TestNormalizarNumero:
    def test_extrae_primer_numero(self):
        assert _normalizar_numero("No. 214 Int. A") == "214"
        assert _normalizar_numero("Mz 15 Lt 8") == "15"

    def test_sin_numero(self):
        assert _normalizar_numero("sin numero") is None


class TestNormalizarFecha:
    @pytest.mark.parametrize("entrada,esperado", [
        ("15 de marzo de 2019", "2019-03-15"),
        ("02 de septiembre de 2026", "2026-09-02"),
        ("5 de enero de 2020", "2020-01-05"),
        ("14/01/2026", "2026-01-14"),
        ("05-03-2024", "2024-03-05"),
        ("2026-11-21", "2026-11-21"),
        ("a 02 de Septiembre de 2026", "2026-09-02"),
    ])
    def test_formatos_validos(self, entrada, esperado):
        assert _normalizar_fecha(entrada) == esperado

    def test_formato_no_reconocido(self):
        assert _normalizar_fecha("en algún momento del 2019") is None

    def test_nulos(self):
        assert _normalizar_fecha(None) is None
        assert _normalizar_fecha("") is None


# ============================================================ verificación de cita

class TestVerificarCita:
    def _pagina(self, numero, texto):
        return Pagina(numero=numero, texto=texto)

    def test_cita_literal_devuelve_pagina(self):
        paginas = [
            self._pagina(1, "y de la otra como COMPRADORA CLAUDIA ALEJANDRA MÉNDEZ SALAZAR"),
            self._pagina(2, "con superficie de 450.00 metros cuadrados"),
        ]
        r = _verificar_cita("COMPRADORA CLAUDIA ALEJANDRA MÉNDEZ SALAZAR", paginas)
        assert r is not None
        assert r[0] == 1

    def test_detecta_pagina_correcta_de_varias(self):
        paginas = [
            self._pagina(1, "y de la otra como COMPRADORA CLAUDIA ALEJANDRA MÉNDEZ"),
            self._pagina(2, "con superficie de 450.00 metros cuadrados conforme al plano"),
        ]
        r = _verificar_cita("con superficie de 450.00 metros cuadrados", paginas)
        assert r is not None
        assert r[0] == 2

    def test_cita_inventada_devuelve_none(self):
        paginas = [self._pagina(1, "texto completamente distinto al que busca el llm")]
        assert _verificar_cita("TEXTO QUE NO EXISTE EN EL DOCUMENTO", paginas) is None

    def test_tolerante_a_acentos_y_mayusculas(self):
        paginas = [self._pagina(1, "COMPRADORA claudia alejandra méndez salazar firma")]
        r = _verificar_cita("Compradora Claudia Alejandra Méndez Salazar", paginas)
        assert r is not None

    def test_cita_muy_corta_rechaza(self):
        paginas = [self._pagina(1, "x y z")]
        assert _verificar_cita("hola", paginas) is None

    def test_cita_corta_pero_completa_se_acepta(self):
        """Fix: una cita corta como '300.00 m²' se acepta si aparece literal."""
        paginas = [self._pagina(1, "superficie de 300.00 m² conforme al plano")]
        r = _verificar_cita("300.00 m²", paginas)
        assert r is not None and r[0] == 1

    def test_cita_corta_notaria_aceptada(self):
        paginas = [self._pagina(1, "ante la Notaría 101 del Estado")]
        r = _verificar_cita("Notaría 101", paginas)
        assert r is not None and r[0] == 1

    def test_cita_nula(self):
        paginas = [self._pagina(1, "cualquier cosa")]
        assert _verificar_cita(None, paginas) is None
        assert _verificar_cita("", paginas) is None


# ============================================================ selección de páginas

class TestSeleccionarPaginas:
    def _doc(self, textos_por_pagina):
        paginas = [Pagina(numero=i + 1, texto=t) for i, t in enumerate(textos_por_pagina)]
        return DocumentoLeido(
            archivo="test.pdf",
            tipo=TipoDocumento.ESCRITURA,
            confianza_tipo=1.0,
            legibilidad=Legibilidad.BUENA,
            paginas=paginas,
            paginas_totales=len(paginas),
        )

    def test_doc_pequeno_devuelve_todo(self):
        doc = self._doc(["pag1", "pag2", "pag3"])
        assert len(_seleccionar_paginas(doc, maximo=15)) == 3

    def test_doc_grande_toma_primeras_y_relevantes(self):
        textos = ["intro proemio"] * 5 + [
            "relleno sin datos",
            "la superficie del predio es",
            "colindancias al norte",
            "más relleno",
            "clave catastral del inmueble",
        ] + ["relleno adicional"] * 20
        doc = self._doc(textos)
        sel = _seleccionar_paginas(doc, maximo=8)
        # Primeras 5 siempre están
        for i in range(5):
            assert sel[i].numero == i + 1
        # Las relevantes aparecen
        numeros_sel = {p.numero for p in sel}
        assert 7 in numeros_sel   # superficie
        assert 8 in numeros_sel   # colindancias
        assert 10 in numeros_sel  # clave catastral

    def test_tope_de_paginas_se_respeta(self):
        textos = ["superficie" for _ in range(50)]
        doc = self._doc(textos)
        sel = _seleccionar_paginas(doc, maximo=15)
        assert len(sel) <= 15


# ============================================================ construir Campo

class TestConstruirCampo:
    def _paginas(self):
        return [Pagina(numero=1, texto="el inmueble se ubica en Calle Nogal 214 Jardines del Lago")]

    def test_campo_vacio_si_valor_nulo(self):
        vacio = _CampoLLM(valor=None, cita=None, pagina=None, confianza=0.0)
        campo = _construir_campo(vacio, "a.pdf", self._paginas())
        assert campo.valor is None
        assert campo.evidencia is None

    def test_evidencia_valida_conserva_confianza(self):
        extraido = _CampoLLM(
            valor="Calle Nogal 214 Jardines del Lago",
            cita="el inmueble se ubica en Calle Nogal 214 Jardines del Lago",
            pagina=1,
            confianza=0.9,
        )
        campo = _construir_campo(extraido, "a.pdf", self._paginas(), _normalizar_direccion)
        assert campo.valor == "Calle Nogal 214 Jardines del Lago"
        assert campo.evidencia is not None
        assert campo.evidencia.pagina == 1
        assert campo.confianza == 0.9
        # Normalizador aplicado
        assert campo.normalizado and "COL" not in campo.normalizado.split()  # "COL" solo si abreviatura

    def test_cita_inventada_pierde_evidencia_confianza_y_normalizado(self):
        """Regla 4 del equipo: cita no verificada → normalizado=None (no entra al cruce)."""
        extraido = _CampoLLM(
            valor="algo",
            cita="esta cita no está en el documento",
            pagina=1,
            confianza=0.9,
        )
        campo = _construir_campo(extraido, "a.pdf", self._paginas(), _normalizar_direccion)
        assert campo.valor == "algo"
        assert campo.evidencia is None
        assert campo.normalizado is None  # <- clave: no entra al cruce
        assert campo.confianza == pytest.approx(0.5, abs=0.01)


# ============================================================ reglas ESC-

def _datos_completos():
    """DatosInmueble con todos los campos poblados y evidencia válida."""
    ev = Evidencia(archivo="a.pdf", pagina=1, cita="cita literal")
    def campo(valor, normalizado=None, conf=0.9):
        return Campo(valor=valor, normalizado=normalizado or valor.upper(),
                     evidencia=ev, confianza=conf)
    datos = DatosInmueble(
        propietario=campo("Claudia Méndez", "MENDEZ CLAUDIA"),
        direccion=campo("Nogal 214"),
        superficie_terreno_m2=campo("450.00"),
        clave_catastral=campo("061 18 134", "0611813409"),
        numero_oficial=campo("214"),
        fecha_emision=campo("15 de marzo de 2019", "2019-03-15"),
        autoridad_emisora=campo("Notaría 12"),
    )
    datos.especificos = {
        "numero_escritura": campo("52687"),
        "notario": campo("Juan Pérez"),
        "tipo_acto": campo("Compraventa", "COMPRAVENTA"),
        "folio_real": campo("12345"),
        "inscripcion_rpp": campo("Libro 1 Sección Primera Vol. 100"),
        "gravamenes": campo("libre de gravámenes"),
        "regimen_propiedad": campo("Privada", "PRIVADA"),
        # copropiedad, embargo_o_litigio y usufructo quedan ausentes (titular único, limpio).
    }
    return datos


class TestReglasESC:
    def _hallazgo_de(self, hallazgos, id_regla):
        return next((h for h in hallazgos if h.id_regla == id_regla), None)

    def test_datos_completos_cumplen_las_aplicables(self):
        """ESC-01..ESC-09 cumplen con _datos_completos(). ESC-11 y ESC-12 son
        NO_EVALUABLE porque el documento no menciona embargo ni usufructo
        (comportamiento alineado al contrato: ausencia != CUMPLE)."""
        h = _aplicar_reglas(_datos_completos())
        for id_regla in ("ESC-01", "ESC-02", "ESC-03", "ESC-04", "ESC-05",
                         "ESC-06", "ESC-07", "ESC-08", "ESC-09"):
            hallazgo = self._hallazgo_de(h, id_regla)
            assert hallazgo is not None, f"Falta {id_regla}"
            assert hallazgo.estado == EstadoRegla.CUMPLE, f"{id_regla} esperaba CUMPLE y fue {hallazgo.estado}"
        for id_regla in ("ESC-11", "ESC-12"):
            hallazgo = self._hallazgo_de(h, id_regla)
            assert hallazgo is not None
            assert hallazgo.estado == EstadoRegla.NO_EVALUABLE

    def test_sin_propietario_ESC01_no_evaluable(self):
        datos = _datos_completos()
        datos.propietario = Campo()
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-01")
        assert h.estado == EstadoRegla.NO_EVALUABLE

    def test_sin_clave_catastral_ESC04_no_evaluable(self):
        """Ausencia de dato va a NO_EVALUABLE según el contrato, no NO_CUMPLE."""
        datos = _datos_completos()
        datos.clave_catastral = Campo()
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-04")
        assert h.estado == EstadoRegla.NO_EVALUABLE

    def test_acto_no_traslativo_ESC05_no_cumple(self):
        """Dato presente pero incompatible SÍ es NO_CUMPLE."""
        datos = _datos_completos()
        datos.especificos["tipo_acto"] = Campo(
            valor="Testamento", normalizado="TESTAMENTO",
            evidencia=Evidencia(archivo="a.pdf", pagina=1, cita="x"),
            confianza=0.9,
        )
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-05")
        assert h.estado == EstadoRegla.NO_CUMPLE

    def test_hipoteca_ESC06_bloqueante(self):
        datos = _datos_completos()
        datos.especificos["gravamenes"] = Campo(
            valor="Hipoteca a favor de BBVA", normalizado="HIPOTECA A FAVOR DE BBVA",
            evidencia=Evidencia(archivo="a.pdf", pagina=1, cita="x"),
            confianza=0.9,
        )
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-06")
        assert h.estado == EstadoRegla.NO_CUMPLE
        assert h.severidad == Severidad.BLOQUEANTE

    def test_libre_de_gravamenes_ESC06_cumple(self):
        h = self._hallazgo_de(_aplicar_reglas(_datos_completos()), "ESC-06")
        assert h.estado == EstadoRegla.CUMPLE

    def test_sin_notario_ni_numero_ESC07_no_evaluable(self):
        """Ausencia de dato va a NO_EVALUABLE según el contrato."""
        datos = _datos_completos()
        datos.especificos["numero_escritura"] = Campo()
        datos.especificos["notario"] = Campo()
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-07")
        assert h.estado == EstadoRegla.NO_EVALUABLE

    def test_sin_folio_ni_inscripcion_ESC08_no_evaluable(self):
        datos = _datos_completos()
        datos.especificos["folio_real"] = Campo()
        datos.especificos["inscripcion_rpp"] = Campo()
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-08")
        assert h.estado == EstadoRegla.NO_EVALUABLE

    def test_solo_catastral_ESC08_no_evaluable(self):
        """ESC-04 cumple con catastral, pero ESC-08 (inscripción RPP) SIGUE sin evaluarse."""
        datos = _datos_completos()
        datos.especificos["folio_real"] = Campo()
        datos.especificos["inscripcion_rpp"] = Campo()
        resultado = _aplicar_reglas(datos)
        esc04 = self._hallazgo_de(resultado, "ESC-04")
        esc08 = self._hallazgo_de(resultado, "ESC-08")
        assert esc04.estado == EstadoRegla.CUMPLE
        assert esc08.estado == EstadoRegla.NO_EVALUABLE

    def test_regimen_ejidal_ESC09_bloqueante(self):
        datos = _datos_completos()
        datos.especificos["regimen_propiedad"] = Campo(
            valor="Ejidal", normalizado="EJIDAL",
            evidencia=Evidencia(archivo="a.pdf", pagina=1, cita="régimen ejidal"),
            confianza=0.9,
        )
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-09")
        assert h.estado == EstadoRegla.NO_CUMPLE
        assert h.severidad == Severidad.BLOQUEANTE

    def test_regimen_ejidal_con_dominio_pleno_ESC09_cumple(self):
        """Caso QUMA: ejido con dominio pleno ya es propiedad desincorporada, no bloqueante."""
        datos = _datos_completos()
        datos.especificos["regimen_propiedad"] = Campo(
            valor="Ejido con dominio pleno (desincorporado)",
            normalizado="EJIDO CON DOMINIO PLENO DESINCORPORADO",
            evidencia=Evidencia(archivo="a.pdf", pagina=1, cita="dominio pleno"),
            confianza=0.9,
        )
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-09")
        assert h.estado == EstadoRegla.CUMPLE

    def test_regimen_con_valor_pero_sin_evidencia_ESC09_no_evaluable(self):
        """Si el modelo cita algo pero no se verificó, no afirmamos ni descartamos."""
        datos = _datos_completos()
        datos.especificos["regimen_propiedad"] = Campo(
            valor="Ejidal", normalizado=None,  # normalizado=None indica cita no verificada
            evidencia=None, confianza=0.5,
        )
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-09")
        assert h.estado == EstadoRegla.NO_EVALUABLE

    def test_sin_regimen_ESC09_no_evaluable(self):
        datos = _datos_completos()
        datos.especificos["regimen_propiedad"] = Campo()
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-09")
        assert h.estado == EstadoRegla.NO_EVALUABLE

    def test_copropiedad_sin_poder_ESC10_revision(self):
        datos = _datos_completos()
        datos.especificos["copropiedad"] = Campo(
            valor="Son copropietarios Juan y María en partes iguales",
            evidencia=Evidencia(archivo="a.pdf", pagina=1, cita="copropietarios"),
            confianza=0.9,
        )
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-10")
        assert h is not None
        assert h.estado == EstadoRegla.NO_CUMPLE
        assert h.severidad == Severidad.REVISION

    def test_copropiedad_con_poder_ESC10_cumple(self):
        datos = _datos_completos()
        datos.especificos["copropiedad"] = Campo(
            valor="Copropietarios Juan y María, representados por poder notarial a Juan",
            evidencia=Evidencia(archivo="a.pdf", pagina=1, cita="poder"),
            confianza=0.9,
        )
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-10")
        assert h is not None
        assert h.estado == EstadoRegla.CUMPLE

    def test_titular_unico_ESC10_no_se_emite(self):
        """Si no hay copropiedad declarada, la regla ESC-10 no aparece (no aplica)."""
        resultado = _aplicar_reglas(_datos_completos())
        assert self._hallazgo_de(resultado, "ESC-10") is None

    def test_embargo_ESC11_bloqueante(self):
        datos = _datos_completos()
        datos.especificos["embargo_o_litigio"] = Campo(
            valor="Anotación preventiva de embargo por el juzgado 5°",
            evidencia=Evidencia(archivo="a.pdf", pagina=1, cita="embargo"),
            confianza=0.9,
        )
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-11")
        assert h.estado == EstadoRegla.NO_CUMPLE
        assert h.severidad == Severidad.BLOQUEANTE

    def test_sin_embargo_ESC11_no_evaluable(self):
        """Contrato: ausencia de mención no afirma 'sin embargo', queda NO_EVALUABLE."""
        h = self._hallazgo_de(_aplicar_reglas(_datos_completos()), "ESC-11")
        assert h.estado == EstadoRegla.NO_EVALUABLE
        assert h.severidad == Severidad.INFO  # ausencia es INFO, no REVISION

    def test_usufructo_ESC12_revision(self):
        datos = _datos_completos()
        datos.especificos["usufructo"] = Campo(
            valor="Usufructo vitalicio a favor de la señora X",
            evidencia=Evidencia(archivo="a.pdf", pagina=1, cita="usufructo"),
            confianza=0.9,
        )
        h = self._hallazgo_de(_aplicar_reglas(datos), "ESC-12")
        assert h.estado == EstadoRegla.NO_CUMPLE
        assert h.severidad == Severidad.REVISION

    def test_sin_usufructo_ESC12_no_evaluable(self):
        """Contrato: ausencia de mención no afirma 'sin usufructo', queda NO_EVALUABLE."""
        h = self._hallazgo_de(_aplicar_reglas(_datos_completos()), "ESC-12")
        assert h.estado == EstadoRegla.NO_EVALUABLE
        assert h.severidad == Severidad.INFO


# ============================================================ entrada completa

class TestAnalizarIlegible:
    def test_doc_ilegible_no_llama_al_llm(self, monkeypatch):
        """Si llegara a llamar a get_llm lanzaríamos — nunca debe ocurrir con ILEGIBLE."""
        def _boom(**_kw):
            raise AssertionError("get_llm no debe llamarse en ILEGIBLE")
        monkeypatch.setattr(escritura, "get_llm", _boom)

        doc = DocumentoLeido(
            archivo="borroso.pdf",
            tipo=TipoDocumento.ESCRITURA,
            confianza_tipo=0.5,
            legibilidad=Legibilidad.ILEGIBLE,
            paginas=[Pagina(numero=1, texto="??? ilegible ???")],
            paginas_totales=1,
        )
        resultado = escritura.analizar(doc, Contexto())
        assert resultado.confianza == 0.0
        assert resultado.hallazgos
        assert resultado.hallazgos[0].id_regla == "ESC-ILEG"

    def test_doc_sin_paginas_tambien_sale_ilegible(self, monkeypatch):
        def _boom(**_kw):
            raise AssertionError("get_llm no debe llamarse sin páginas")
        monkeypatch.setattr(escritura, "get_llm", _boom)

        doc = DocumentoLeido(
            archivo="vacio.pdf",
            tipo=TipoDocumento.ESCRITURA,
            confianza_tipo=0.5,
            legibilidad=Legibilidad.BUENA,
            paginas=[],
            paginas_totales=0,
        )
        resultado = escritura.analizar(doc, Contexto())
        assert resultado.hallazgos[0].id_regla == "ESC-ILEG"


class TestFormatearPaginas:
    def test_incluye_marcadores_de_pagina(self):
        pags = [Pagina(numero=1, texto="hola"), Pagina(numero=3, texto="mundo")]
        salida = _formatear_paginas(pags)
        assert "[P1]" in salida
        assert "[P3]" in salida
        assert "hola" in salida
        assert "mundo" in salida


# ============================================================ correcciones de Julián (sin API)

def _vacio_llm():
    return {n: _CampoLLM(valor=None, cita=None, pagina=None, confianza=0.0) for n in escritura._CAMPOS_ESCRITURA_LLM}


def _doc_con_anexo() -> DocumentoLeido:
    return DocumentoLeido(
        archivo="ESCRITURA ANEXO.pdf", tipo=TipoDocumento.ESCRITURA, confianza_tipo=0.9,
        legibilidad=Legibilidad.BUENA, paginas_totales=3,
        notas="Origen del texto: llm 3 pág. Contiene páginas de tipo predial: p2.",
        paginas=[
            Pagina(numero=1, texto="ESCRITURA NÚMERO 27,418. Inmueble en Nogal S/N, Estado de México."),
            Pagina(numero=2, texto="RECIBO PREDIAL. CLAVE CATASTRAL 207 15 088 06 00 0000. SUPERFICIE 245.00 M2"),
            Pagina(numero=3, texto=""),  # borrosa: la ingesta descartó su texto
        ],
    )


class TestCorreccionesJulian:
    def test_entidad_y_municipio_en_formato_del_contrato(self):
        assert escritura._normalizar_entidad("Estado de México") == "MEXICO"
        assert escritura._normalizar_entidad("Edo. de Méx.") == "MEXICO"
        assert escritura._normalizar_entidad("Hidalgo") == "HIDALGO"
        assert escritura._normalizar_entidad("Hgo.") == "HIDALGO"
        assert escritura._normalizar_entidad("Ciudad de México") == "CIUDAD DE MEXICO"
        assert escritura._normalizar_municipio("Municipio de Tultepec") == "TULTEPEC"

    def test_sin_numero_no_se_pierde(self):
        assert escritura._normalizar_numero_oficial("S/N") == "SN"
        assert escritura._normalizar_numero_oficial("sin número") == "SN"
        assert escritura._normalizar_numero_oficial("No. 120") == "120"

    def test_numero_de_escritura_con_miles(self):
        assert escritura._normalizar_instrumento("27,418") == "27418"
        assert escritura._normalizar_instrumento("Escritura número 41,906") == "41906"
        assert escritura._normalizar_instrumento("4521") == "4521"

    def test_persona_moral_no_se_reordena(self):
        assert _normalizar_nombre("Inmobiliaria XYZ, S.A. de C.V.") == "INMOBILIARIA XYZ S A DE C V"
        assert _normalizar_nombre("Claudia Alejandra Méndez Salazar") == "MENDEZ SALAZAR CLAUDIA ALEJANDRA"

    def test_no_manda_anexos_ni_paginas_vacias_al_modelo(self):
        assert [p.numero for p in _seleccionar_paginas(_doc_con_anexo())] == [1]

    def test_dato_del_predial_anexo_no_cuenta_como_de_la_escritura(self, monkeypatch):
        vistas = {}

        def falso(doc, paginas):
            vistas["paginas"] = [p.numero for p in paginas]
            d = _vacio_llm()
            # El modelo "encuentra" la clave del predial anexo: no debe pasar la verificación.
            d["clave_catastral"] = _CampoLLM(valor="207 15 088 06 00 0000", cita="CLAVE CATASTRAL 207 15 088 06 00 0000",
                                             pagina=2, confianza=0.9)
            d["entidad_federativa"] = _CampoLLM(valor="Estado de México", cita="Estado de México", pagina=1, confianza=0.9)
            d["numero_oficial"] = _CampoLLM(valor="S/N", cita="Nogal S/N", pagina=1, confianza=0.9)
            d["numero_escritura"] = _CampoLLM(valor="27,418", cita="ESCRITURA NÚMERO 27,418", pagina=1, confianza=0.9)
            return escritura._EscrituraLLM(**d)

        monkeypatch.setattr(escritura, "_extraer", falso)
        r = escritura.analizar(_doc_con_anexo(), Contexto())
        assert vistas["paginas"] == [1]
        assert r.datos.clave_catastral.normalizado is None and r.datos.clave_catastral.evidencia is None
        assert r.datos.entidad_federativa.normalizado == "MEXICO"
        assert r.datos.numero_oficial.normalizado == "SN"
        assert r.datos.especificos["numero_escritura"].normalizado == "27418"

    def test_sin_paginas_propias_con_texto_es_ilegible(self, monkeypatch):
        monkeypatch.setattr(escritura, "_extraer", lambda *a: (_ for _ in ()).throw(AssertionError("no debe llamar")))
        doc = _doc_con_anexo().model_copy(update={"paginas": [Pagina(numero=1, texto="  ")]})
        assert escritura.analizar(doc, Contexto()).hallazgos[0].id_regla == "ESC-ILEG"
