"""Caché de la ingesta: la llave es nombre + contenido. Sin API."""
import pytest

from expedientes import cache
from expedientes.schemas import DocumentoLeido, Legibilidad, Pagina, TipoDocumento


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    c, d = tmp_path / "cache", tmp_path / "Documentos"
    d.mkdir()
    monkeypatch.setattr(cache, "CACHE_DIR", c)
    monkeypatch.setattr(cache, "DIR_PAGINAS", c / "_paginas")
    monkeypatch.setattr(cache, "DOCUMENTOS_DIR", d)
    return c, d


def _leido(nombre, texto):
    return DocumentoLeido(archivo=nombre, tipo=TipoDocumento.PREDIAL, confianza_tipo=1.0,
                          legibilidad=Legibilidad.BUENA, paginas=[Pagina(numero=1, texto=texto)], paginas_totales=1)


def test_mismo_nombre_distinto_contenido_no_comparten_cache(dirs, tmp_path):
    a = tmp_path / "exp1" / "Predial.pdf"; a.parent.mkdir(); a.write_bytes(b"inmueble A")
    b = tmp_path / "exp2" / "Predial.pdf"; b.parent.mkdir(); b.write_bytes(b"inmueble B")
    cache.guardar_cache(_leido("Predial.pdf", "TEXTO A"), a)
    assert cache.ruta_cache(a) != cache.ruta_cache(b)
    assert cache.leer_cache(a).paginas[0].texto == "TEXTO A"
    assert cache.leer_cache(b) is None  # el bug: antes devolvía el texto de A
    assert cache.ruta_paginas(a) != cache.ruta_paginas(b)


def test_mismo_contenido_en_otra_carpeta_si_reusa(dirs, tmp_path):
    a = tmp_path / "x" / "Predial.pdf"; a.parent.mkdir(); a.write_bytes(b"mismo")
    b = tmp_path / "subida" / "Predial.pdf"; b.parent.mkdir(); b.write_bytes(b"mismo")
    cache.guardar_cache(_leido("Predial.pdf", "T"), a)
    assert cache.leer_cache(b) is not None  # la UI sube el mismo PDF: no repite OCR


def test_ruta_inexistente_no_adivina_por_nombre(dirs, tmp_path):
    a = tmp_path / "Licencia.pdf"; a.write_bytes(b"x")
    cache.guardar_cache(_leido("Licencia.pdf", "T"), a)
    assert cache.leer_cache(tmp_path / "otro_inmueble" / "Licencia.pdf") is None  # reproducción de Juan Pablo


def test_solo_nombre_para_scripts_de_desarrollo(dirs, tmp_path):
    a = tmp_path / "02 Predial...pdf"; a.write_bytes(b"x")
    cache.guardar_cache(_leido("02 Predial...pdf", "T"), a)
    assert cache.leer_cache("02 Predial...pdf").paginas[0].texto == "T"
    assert cache.leer_cache("02 Predial.pdf") is None  # el nombre tiene que coincidir completo


def test_migra_formato_anterior_solo_dentro_de_documentos(dirs, tmp_path):
    c, d = dirs
    dentro = d / "Predial" / "Viejo.pdf"; dentro.parent.mkdir(); dentro.write_bytes(b"x")
    cache.guardar_cache(_leido("Viejo.pdf", "LEGADO"))  # sin ruta = formato anterior
    (c / "_paginas" / "Viejo.pdf").mkdir(parents=True)
    (c / "_paginas" / "Viejo.pdf" / "0001.llm.json").write_text("{}")

    fuera = tmp_path / "subida" / "Viejo.pdf"; fuera.parent.mkdir(); fuera.write_bytes(b"otro contenido")
    assert cache.leer_cache(fuera) is None  # una subida nunca usa una entrada sin huella

    assert cache.leer_cache(dentro).paginas[0].texto == "LEGADO"  # se migra al vuelo
    assert not (c / "Viejo.pdf.json").exists() and cache.ruta_cache(dentro).exists()
    assert (cache.ruta_paginas(dentro) / "0001.llm.json").exists()


def test_migrar_legado_masivo(dirs):
    c, d = dirs
    for n in ("A.pdf", "B.pdf"):
        (d / n).write_bytes(n.encode())
        cache.guardar_cache(_leido(n, n))
    assert cache.migrar_legado() == 2
    assert cache.migrar_legado() == 0
    assert all(cache.leer_cache(d / n) for n in ("A.pdf", "B.pdf"))
