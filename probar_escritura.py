"""Script de prueba del agente escritura.py contra un PDF o un caché OCR.

Uso:
    python probar_escritura.py <ruta_al_pdf_o_json>

Si el argumento es un PDF:
    1. Si existe el JSON cacheado por la ingesta de Julián, lo usa (ideal
       porque trae el OCR por visión de todas las páginas).
    2. Si no, cae a pymupdf con la capa de texto nativa (solo sirve para
       los 5 PDFs del set que tienen texto seleccionable).

Si el argumento es un .json: lo carga directo como DocumentoLeido.

Imprime datos extraídos con evidencias, los 7 hallazgos ESC-01..ESC-07
y la confianza global. Flag --json vuelca el objeto completo.

Requiere ANTHROPIC_API_KEY en .env y `pip install -r requirements.txt`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf  # el nombre moderno del antiguo `fitz`

from expedientes.agentes import escritura
from expedientes.cache import leer_cache, nombre_archivo
from expedientes.config import CACHE_DIR
from expedientes.schemas import (
    Contexto,
    DocumentoLeido,
    Legibilidad,
    Pagina,
    TipoDocumento,
)


def cargar_json(ruta: Path) -> DocumentoLeido:
    """Carga un DocumentoLeido desde un JSON (cache o export manual)."""
    return DocumentoLeido.model_validate_json(ruta.read_text(encoding="utf-8"))


def leer_pdf_a_documento(ruta: Path) -> DocumentoLeido:
    """Mini ingesta sin OCR: usa solo la capa de texto del PDF.

    Esto solo sirve para los PDFs que tienen texto seleccionable
    (unos 5 de 62 del set). Para los escaneos habrá que esperar la
    ingesta real de Julián con visión + OCR.
    """
    doc = pymupdf.open(ruta)
    paginas: list[Pagina] = []
    for i, pagina in enumerate(doc, start=1):
        texto = pagina.get_text() or ""
        paginas.append(Pagina(numero=i, texto=texto))
    total = len(paginas)
    doc.close()

    hay_texto = sum(len(p.texto.strip()) for p in paginas) > 500
    legibilidad = Legibilidad.BUENA if hay_texto else Legibilidad.ILEGIBLE

    return DocumentoLeido(
        archivo=nombre_archivo(ruta),
        tipo=TipoDocumento.ESCRITURA,
        confianza_tipo=1.0,
        legibilidad=legibilidad,
        paginas=paginas,
        paginas_totales=total,
        notas=None if hay_texto else "Sin capa de texto; se marcó ILEGIBLE (necesita OCR real)",
    )


def resolver_documento(ruta: Path) -> tuple[DocumentoLeido, str]:
    """Devuelve (doc, origen) donde origen es 'cache', 'cache-json' o 'pdf-local'.

    Prioridad:
      1. Si la ruta es un .json -> cargarlo directo.
      2. Si la ruta es un .pdf y existe su JSON en CACHE_DIR -> usar el caché.
      3. Caer a pymupdf sobre la capa de texto nativa del PDF.
    """
    if ruta.suffix.lower() == ".json":
        return cargar_json(ruta), "cache-json"

    doc = leer_cache(ruta.name)
    if doc is not None:
        return doc, "cache"

    return leer_pdf_a_documento(ruta), "pdf-local"


def imprimir_resultado(resultado) -> None:
    sep = "=" * 72
    print(f"\n{sep}\nARCHIVO: {resultado.archivo}")
    print(f"TIPO: {resultado.tipo.value}  |  LEGIBILIDAD: {resultado.legibilidad.value}")
    print(f"CONFIANZA GLOBAL DEL ANÁLISIS: {resultado.confianza}")
    print(sep)

    print("\n--- DATOS EXTRAÍDOS ---")
    campos_comunes = {
        "propietario": resultado.datos.propietario,
        "direccion": resultado.datos.direccion,
        "superficie_terreno_m2": resultado.datos.superficie_terreno_m2,
        "clave_catastral": resultado.datos.clave_catastral,
        "numero_oficial": resultado.datos.numero_oficial,
        "fecha_emision": resultado.datos.fecha_emision,
        "autoridad_emisora": resultado.datos.autoridad_emisora,
    }
    for nombre, campo in campos_comunes.items():
        _imprimir_campo(nombre, campo)

    print("\n--- ESPECÍFICOS DE ESCRITURA ---")
    for nombre, campo in resultado.datos.especificos.items():
        _imprimir_campo(nombre, campo)

    print(f"\n--- HALLAZGOS ({len(resultado.hallazgos)}) ---")
    for h in resultado.hallazgos:
        print(f"  [{h.id_regla}] {h.estado.value.upper()} / {h.severidad.value}")
        print(f"      {h.descripcion}")
        print(f"      → {h.explicacion}")
        for e in h.evidencias:
            print(f"      ✎ p.{e.pagina}: \"{e.cita[:80]}{'…' if len(e.cita) > 80 else ''}\"")
    print()


def _imprimir_campo(nombre: str, campo) -> None:
    if not campo.valor:
        print(f"  {nombre:<28} —")
        return
    norm = f" [norm: {campo.normalizado}]" if campo.normalizado and campo.normalizado != campo.valor else ""
    conf = f" (conf {campo.confianza})"
    print(f"  {nombre:<28} {campo.valor}{norm}{conf}")
    if campo.evidencia:
        cita = campo.evidencia.cita
        print(f"  {'':<28} ✎ p.{campo.evidencia.pagina}: \"{cita[:70]}{'…' if len(cita) > 70 else ''}\"")
    else:
        print(f"  {'':<28} ⚠ sin evidencia verificada (castigado -0.4 de confianza)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba el agente escritura contra un PDF real.")
    parser.add_argument("pdf", type=Path, help="Ruta al PDF de escritura")
    parser.add_argument("--json", action="store_true", help="Imprime también el DocumentoAnalizado como JSON")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"[ERROR] No existe el archivo: {args.pdf}", file=sys.stderr)
        return 2

    print(f"Leyendo: {args.pdf}")
    print(f"CACHE_DIR configurado: {CACHE_DIR}")
    doc, origen = resolver_documento(args.pdf)
    etiqueta = {
        "cache": "caché OCR del equipo (recomendado)",
        "cache-json": "JSON directo",
        "pdf-local": "pymupdf con capa de texto nativa del PDF",
    }[origen]
    print(f"  fuente: {etiqueta}")
    print(f"  {doc.paginas_totales} páginas, legibilidad {doc.legibilidad.value}")
    if doc.notas:
        print(f"  ⚠ {doc.notas}")

    if doc.legibilidad == Legibilidad.ILEGIBLE:
        print("\n[AVISO] Documento ILEGIBLE. El agente no intentará extraer para no inventar.")
        print("        Se emitirá un único hallazgo ESC-ILEG.")

    print("\nLlamando al agente (requiere ANTHROPIC_API_KEY en .env)...")
    resultado = escritura.analizar(doc, Contexto())
    imprimir_resultado(resultado)

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(resultado.model_dump(mode="json"), ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
