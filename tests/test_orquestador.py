"""Tests del orquestador. Focalizados en la paralelización de agentes.

No llama al LLM: mockea cada agente por tipo para controlar tiempos y excepciones.
"""
from __future__ import annotations

import time

from expedientes import orquestador
from expedientes.schemas import (
    Contexto,
    DatosInmueble,
    DocumentoAnalizado,
    DocumentoLeido,
    EstadoRegla,
    Legibilidad,
    Pagina,
    TipoDocumento,
)


def _doc(tipo: TipoDocumento, archivo: str) -> DocumentoLeido:
    return DocumentoLeido(
        archivo=archivo,
        tipo=tipo,
        confianza_tipo=1.0,
        legibilidad=Legibilidad.BUENA,
        paginas=[Pagina(numero=1, texto="texto de prueba")],
        paginas_totales=1,
    )


def _analizado_ok(doc: DocumentoLeido) -> DocumentoAnalizado:
    return DocumentoAnalizado(
        archivo=doc.archivo,
        tipo=doc.tipo,
        confianza_tipo=1.0,
        legibilidad=doc.legibilidad,
        datos=DatosInmueble(),
        hallazgos=[],
        confianza=0.9,
    )


class TestAnalizarEnParalelo:
    def test_preserva_orden_aunque_un_agente_tarde(self, monkeypatch):
        """El agente de escritura tarda 300ms, los otros 50ms: el orden del
        resultado debe seguir siendo el orden de entrada."""

        def escritura_lenta(doc, ctx):
            time.sleep(0.3)
            return _analizado_ok(doc)

        def rapido(doc, ctx):
            time.sleep(0.05)
            return _analizado_ok(doc)

        monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, TipoDocumento.ESCRITURA, escritura_lenta)
        monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, TipoDocumento.PREDIAL, rapido)
        monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, TipoDocumento.ALINEAMIENTO, rapido)
        monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, TipoDocumento.USO_SUELO, rapido)

        leidos = [
            _doc(TipoDocumento.ESCRITURA, "a.pdf"),
            _doc(TipoDocumento.PREDIAL, "b.pdf"),
            _doc(TipoDocumento.ALINEAMIENTO, "c.pdf"),
            _doc(TipoDocumento.USO_SUELO, "d.pdf"),
        ]

        resultados = orquestador._analizar_en_paralelo(leidos, Contexto())

        assert [r.archivo for r in resultados] == ["a.pdf", "b.pdf", "c.pdf", "d.pdf"]

    def test_corre_realmente_en_paralelo(self, monkeypatch):
        """4 agentes de 200ms en paralelo deben tardar < 600ms (serial sería 800ms)."""

        def lento(doc, ctx):
            time.sleep(0.2)
            return _analizado_ok(doc)

        for t in TipoDocumento:
            if t in orquestador.AGENTES_POR_TIPO:
                monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, t, lento)

        leidos = [
            _doc(TipoDocumento.ESCRITURA, "1.pdf"),
            _doc(TipoDocumento.PREDIAL, "2.pdf"),
            _doc(TipoDocumento.ALINEAMIENTO, "3.pdf"),
            _doc(TipoDocumento.USO_SUELO, "4.pdf"),
        ]

        t0 = time.time()
        resultados = orquestador._analizar_en_paralelo(leidos, Contexto())
        dt = time.time() - t0

        assert len(resultados) == 4
        # Serial sería 4*0.2 = 0.8s; con 5 workers debería ser cerca de 0.2s.
        # Margen generoso para CI lento.
        assert dt < 0.6, f"La paralelización no funcionó; tardó {dt:.2f}s"

    def test_agente_que_lanza_excepcion_no_tumba_a_los_otros(self, monkeypatch):
        """Un agente que explota devuelve EXP-ERROR, pero los otros se analizan bien."""

        def explosivo(doc, ctx):
            raise RuntimeError("boom")

        def bueno(doc, ctx):
            return _analizado_ok(doc)

        monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, TipoDocumento.ESCRITURA, explosivo)
        monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, TipoDocumento.PREDIAL, bueno)
        monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, TipoDocumento.ALINEAMIENTO, bueno)
        monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, TipoDocumento.USO_SUELO, bueno)

        leidos = [
            _doc(TipoDocumento.ESCRITURA, "esc.pdf"),
            _doc(TipoDocumento.PREDIAL, "pre.pdf"),
        ]

        resultados = orquestador._analizar_en_paralelo(leidos, Contexto())

        assert len(resultados) == 2
        assert resultados[0].archivo == "esc.pdf"
        assert resultados[0].hallazgos
        assert resultados[0].hallazgos[0].id_regla == "EXP-ERROR"
        assert resultados[0].hallazgos[0].estado == EstadoRegla.NO_EVALUABLE
        # El segundo pasa limpio
        assert resultados[1].archivo == "pre.pdf"
        assert resultados[1].confianza == 0.9

    def test_lista_vacia(self):
        assert orquestador._analizar_en_paralelo([], Contexto()) == []

    def test_un_solo_doc_sin_executor(self, monkeypatch):
        """Con un solo doc no abrimos executor (optimización); el resultado es el mismo."""

        def bueno(doc, ctx):
            return _analizado_ok(doc)

        monkeypatch.setitem(orquestador.AGENTES_POR_TIPO, TipoDocumento.ESCRITURA, bueno)

        resultados = orquestador._analizar_en_paralelo(
            [_doc(TipoDocumento.ESCRITURA, "x.pdf")], Contexto()
        )
        assert len(resultados) == 1
        assert resultados[0].archivo == "x.pdf"

    def test_tipo_otro_devuelve_exp_tipo(self):
        """Un doc con tipo OTRO no tiene agente; sale como EXP-TIPO sin análisis."""
        leidos = [_doc(TipoDocumento.OTRO, "misterio.pdf")]
        resultados = orquestador._analizar_en_paralelo(leidos, Contexto())
        assert len(resultados) == 1
        assert resultados[0].hallazgos[0].id_regla == "EXP-TIPO"

    def test_ingesta_fallida_devuelve_exp_ingesta(self):
        """Si la ingesta marcó el doc con _PREFIJO_INGESTA_ROTA, el hallazgo
        es EXP-INGESTA con la razón del error (no EXP-TIPO engañoso)."""
        doc_roto = DocumentoLeido(
            archivo="roto.pdf",
            tipo=TipoDocumento.OTRO,
            confianza_tipo=0.0,
            legibilidad=Legibilidad.ILEGIBLE,
            paginas=[],
            paginas_totales=0,
            notas=f"{orquestador._PREFIJO_INGESTA_ROTA}TimeoutError: la API tardó demasiado",
        )
        resultados = orquestador._analizar_en_paralelo([doc_roto], Contexto())
        assert len(resultados) == 1
        hallazgo = resultados[0].hallazgos[0]
        assert hallazgo.id_regla == "EXP-INGESTA"
        assert "TimeoutError" in hallazgo.explicacion


class TestLeer:
    def test_leer_atrapa_excepcion(self, monkeypatch, tmp_path):
        """_leer convierte una excepción de ingesta.leer_documento en un
        DocumentoLeido tipo OTRO con el prefijo de ingesta rota."""

        def explosivo(ruta):
            raise ConnectionError("API caída")

        monkeypatch.setattr(orquestador.ingesta, "leer_documento", explosivo)
        p = tmp_path / "x.pdf"
        p.write_bytes(b"dummy")

        doc = orquestador._leer(p)

        assert doc.tipo == TipoDocumento.OTRO
        assert doc.legibilidad == Legibilidad.ILEGIBLE
        assert doc.notas.startswith(orquestador._PREFIJO_INGESTA_ROTA)
        assert "ConnectionError" in doc.notas
        assert doc.archivo == "x.pdf"

    def test_leer_exitoso_devuelve_documento_del_ingesta(self, monkeypatch, tmp_path):
        def bueno(ruta):
            return DocumentoLeido(
                archivo=ruta.name, tipo=TipoDocumento.ESCRITURA,
                confianza_tipo=1.0, legibilidad=Legibilidad.BUENA,
                paginas=[Pagina(numero=1, texto="hola")], paginas_totales=1,
            )

        monkeypatch.setattr(orquestador.ingesta, "leer_documento", bueno)
        p = tmp_path / "ok.pdf"
        p.write_bytes(b"dummy")

        doc = orquestador._leer(p)
        assert doc.tipo == TipoDocumento.ESCRITURA
        assert doc.notas is None
