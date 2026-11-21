"""Id fijado por la UI, subidas, colisiones de nombres, límites y ruteo de la bitácora."""
import contextvars
import logging
import threading
from collections import deque
from datetime import datetime

from expedientes.orquestador import analizar_expediente
from ui import store
from ui.trabajos import Bitacora


# ------------------------------------------------------------------ S1: id fijado por la UI

def test_id_expediente_usa_nombre_o_fecha():
    assert store.id_expediente("  TEPEJI-05 ") == "TEPEJI-05"
    assert store.id_expediente(None, datetime(2026, 11, 21, 13, 5, 9)) == "EXP-20261121-130509"
    assert store.id_expediente("   ", datetime(2026, 11, 21, 13, 5, 9)) == "EXP-20261121-130509"


def test_un_id_cambiado_por_el_llm_no_pisa_otro_expediente(tmp_path, monkeypatch):
    import expedientes.orquestador as orq
    from ui import vistas

    original = orq.analizar_expediente
    otro = store.guardar(original([], usar_ejemplo=True).model_copy(update={"expediente_id": "VICTIMA"}), tmp_path)
    contenido_previo = otro.ruta.read_text(encoding="utf-8")

    def inyectado(rutas, ctx=None, expediente_id=None, usar_ejemplo=False):
        return original([], usar_ejemplo=True).model_copy(update={"expediente_id": "VICTIMA"})

    monkeypatch.setattr(orq, "analizar_expediente", inyectado)
    monkeypatch.setattr(store, "DIR_RESULTADOS", tmp_path)
    entrada = vistas._analizar([("a.pdf", b"x")], "MIO")
    assert entrada.dictamen.expediente_id == "MIO" and entrada.ruta.name == "MIO.json"
    assert otro.ruta.read_text(encoding="utf-8") == contenido_previo


def test_fijar_id_no_copia_si_ya_coincide():
    d = analizar_expediente([], usar_ejemplo=True)
    assert store.fijar_id(d, d.expediente_id) is d


# ------------------------------------------------------------------ F8: colisiones en cualquier disco

def test_mismo_id_reusa_su_archivo_y_otro_id_con_otras_mayusculas_no(tmp_path):
    base = analizar_expediente([], usar_ejemplo=True)
    a = store.guardar(base.model_copy(update={"expediente_id": "Lote"}), tmp_path)
    a2 = store.guardar(base.model_copy(update={"expediente_id": "Lote", "confianza": 0.1}), tmp_path)
    b = store.guardar(base.model_copy(update={"expediente_id": "LOTE"}), tmp_path)
    assert a.ruta.name == a2.ruta.name == "Lote.json"
    assert b.ruta.name == "LOTE-2.json"
    assert sorted(p.name for p in tmp_path.glob("*.json")) == ["LOTE-2.json", "Lote.json"]


# ------------------------------------------------------------------ F9, S3, S4: subidas

def test_subidas_deduplican_sin_mayusculas_ni_punto_final_y_limpian_caracteres():
    r = store.preparar_subidas([
        ("Escritura.pdf", b"1"), ("ESCRITURA.PDF", b"2"), ("escritura.pdf. ", b"3"),
        ('predial <2024>?.pdf', b"4"), ("carpeta/uso.pdf", b"5"), ("sub\\alin.pdf", b"6"),
    ])
    assert [n for n, _ in r.validos] == ["Escritura.pdf", "predial -2024-.pdf", "uso.pdf", "alin.pdf"]
    assert r.validos[0][1] == b"1"
    assert r.repetidos == ["ESCRITURA.PDF", "escritura.pdf. "]
    assert not r.omitidos and r.exceso is None


def test_subidas_omiten_nombres_reservados():
    nombres = ["CON.pdf", "nul", "a:b.pdf", "..", "", "CONIN$.pdf", "conout$", "COM¹.pdf", "lpt³.jpg", "COM1.tif"]
    r = store.preparar_subidas([(n, b"x") for n in nombres] + [("bien.pdf", b"x")])
    assert r.omitidos == nombres and [n for n, _ in r.validos] == ["bien.pdf"]


def test_subidas_respetan_limites_de_cantidad_y_tamano():
    muchas = store.preparar_subidas([(f"{i}.pdf", b"x") for i in range(store.LIMITE_ARCHIVOS + 1)])
    assert muchas.exceso and not muchas.validos
    justas = store.preparar_subidas([(f"{i}.pdf", b"x") for i in range(store.LIMITE_ARCHIVOS)])
    assert justas.exceso is None and len(justas.validos) == store.LIMITE_ARCHIVOS
    grandes = store.preparar_subidas([("a.pdf", b"x" * (store.LIMITE_BYTES // 2 + 1)), ("b.pdf", b"x" * (store.LIMITE_BYTES // 2))])
    assert grandes.exceso and "MB" in grandes.exceso and not grandes.validos


def test_reservados_nuevos():
    for n in ["CONIN$", "conout$.txt", "COM²", "LPT¹.pdf"]:
        assert store.nombre_reservado(n), n


# ------------------------------------------------------------------ S2: host permitido

def test_host_permitido():
    from ui.vistas import host_permitido
    assert host_permitido("localhost:8501", 8501) and host_permitido("127.0.0.1:8501", 8501)
    assert host_permitido("LOCALHOST:8501", 8501)
    for malo in ["evil.example:8501", "localhost:8502", "127.0.0.1", None, "", "localhost:8501.evil.example"]:
        assert not host_permitido(malo, 8501), malo


# ------------------------------------------------------------------ F4: bitácora por contexto

def test_bitacora_sigue_al_contexto_y_no_mezcla_trabajos():
    registro: contextvars.ContextVar = contextvars.ContextVar("prueba", default=None)
    log = logging.getLogger("expedientes.prueba_bitacora")
    log.setLevel(logging.INFO)
    handler = Bitacora(registro)
    log.addHandler(handler)
    try:
        mias, ajenas = deque(), deque()

        def trabajo(lineas, texto):
            registro.set(lineas)
            log.info(texto)
            # un hilo hijo que copia el contexto (como LangChain) escribe en la misma bitácora
            ctx = contextvars.copy_context()
            hijo = threading.Thread(target=ctx.run, args=(log.info, texto + " hijo"))
            hijo.start(); hijo.join()

        hilos = [threading.Thread(target=contextvars.copy_context().run, args=(trabajo, mias, "a")),
                 threading.Thread(target=contextvars.copy_context().run, args=(trabajo, ajenas, "b"))]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        log.info("sin trabajo")
        assert list(mias) == ["a", "a hijo"] and list(ajenas) == ["b", "b hijo"]
    finally:
        log.removeHandler(handler)
