"""Prueba el agente de Uso de Suelo contra un archivo real.

Uso:
    python probar_uso_suelo.py <ruta>          # NO gasta API: muestra el texto y el prompt
    python probar_uso_suelo.py <ruta> --llm    # llama al LLM una vez e imprime el resultado

Toma el texto del caché de la ingesta (`cache/<archivo>.json`) si existe; si no, de la capa de
texto del PDF, que solo traen 2 de los 16 usos de suelo (Tultepec y Paseo de la Pradera).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pymupdf

from expedientes.agentes import uso_suelo
from expedientes.cache import leer_cache, nombre_archivo
from expedientes.schemas import Contexto, DocumentoLeido, Legibilidad, Pagina, TipoDocumento


def cargar(ruta: Path) -> DocumentoLeido:
    doc = leer_cache(nombre_archivo(ruta))
    if doc:
        print(f"(texto del caché de la ingesta)")
        return doc
    with pymupdf.open(ruta) as pdf:
        paginas = [Pagina(numero=i, texto=p.get_text() or "") for i, p in enumerate(pdf, start=1)]
    hay_texto = sum(len(p.texto.strip()) for p in paginas) > 300
    print("(capa de texto del PDF)" if hay_texto else "(sin caché ni capa de texto: sale ILEGIBLE)")
    return DocumentoLeido(
        archivo=nombre_archivo(ruta), tipo=TipoDocumento.USO_SUELO, confianza_tipo=1.0,
        legibilidad=Legibilidad.BUENA if hay_texto else Legibilidad.ILEGIBLE,
        paginas=paginas, paginas_totales=len(paginas),
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("ruta", type=Path)
    ap.add_argument("--llm", action="store_true", help="llamar al LLM (gasta API)")
    ap.add_argument("--fecha", type=date.fromisoformat, help="fecha de referencia AAAA-MM-DD")
    args = ap.parse_args()

    ctx = Contexto(fecha_referencia=args.fecha) if args.fecha else Contexto()
    doc = cargar(args.ruta)

    if not args.llm:
        sistema, humano = uso_suelo.construir_mensajes(doc, ctx)
        print(f"\n{doc.archivo}: {len(doc.paginas)} páginas, {len(humano.content)} caracteres al LLM")
        print(f"\n--- PROMPT DE SISTEMA ---\n{sistema.content}\n--- TEXTO (primeros 1500) ---")
        print(humano.content[:1500])
        print("\nNo se llamó a la API. Agrega --llm para correr la extracción.")
        return

    r = uso_suelo.analizar(doc, ctx)
    print(f"\n{r.archivo} | legibilidad {r.legibilidad.value} | confianza {r.confianza}\n")
    campos = {k: getattr(r.datos, k) for k in type(r.datos).model_fields if k != "especificos"}
    for nombre, c in {**campos, **r.datos.especificos}.items():
        if c.valor:
            ev = f"p.{c.evidencia.pagina} «{c.evidencia.cita}»" if c.evidencia else "SIN EVIDENCIA"
            print(f"  {nombre:26} {c.normalizado or c.valor!r:40.40}  {ev}")
    print()
    for h in r.hallazgos:
        print(f"  [{h.id_regla}] {h.estado.value:12} {h.severidad.value:10} {h.explicacion}")


if __name__ == "__main__":
    main()
