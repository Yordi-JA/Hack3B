"""Corre el agente escritura sobre TODAS las escrituras del caché.

Lee cada .json de CACHE_DIR cuyo tipo sea `escritura`, ejecuta el agente
contra Claude y produce una tabla resumen con:
- Archivo
- Legibilidad
- Confianza global
- Cuántas de las 7 reglas ESC- cumplen / revisan / no cumplen
- Dato clave extraído (propietario)

Útil para ver de un vistazo cómo se comporta el agente en los 12 PDFs
reales sin pagar un llamado por cada uno interactivamente.

Cuesta aprox. 1-3 centavos de USD por escritura con Haiku.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from expedientes.agentes import escritura
from expedientes.cache import leer_cache
from expedientes.config import CACHE_DIR
from expedientes.schemas import Contexto, EstadoRegla, Severidad, TipoDocumento


def _resumen_hallazgos(hallazgos):
    counts = {"CUMPLE": 0, "NO_CUMPLE": 0, "NO_EVALUABLE": 0}
    bloqueantes = 0
    for h in hallazgos:
        counts[h.estado.name] = counts.get(h.estado.name, 0) + 1
        if h.severidad == Severidad.BLOQUEANTE and h.estado == EstadoRegla.NO_CUMPLE:
            bloqueantes += 1
    return counts, bloqueantes


def main() -> int:
    if not CACHE_DIR.exists():
        print(f"[ERROR] CACHE_DIR no existe: {CACHE_DIR}", file=sys.stderr)
        return 2

    jsons = sorted(CACHE_DIR.glob("*.pdf.json"))
    escrituras: list = []
    for j in jsons:
        try:
            doc = leer_cache(j.stem)  # stem quita .json, deja ".pdf"
        except Exception:
            continue
        if doc and doc.tipo == TipoDocumento.ESCRITURA:
            escrituras.append(doc)

    print(f"Procesando {len(escrituras)} escrituras del caché contra Claude...\n")
    ctx = Contexto()

    print(f"{'archivo':<60} {'leg':<9} {'conf':>5}  reglas          propietario")
    print("-" * 120)

    costo_estimado_usd = 0.0
    inicio = time.time()

    for doc in escrituras:
        t0 = time.time()
        try:
            resultado = escritura.analizar(doc, ctx)
            err = None
        except Exception as e:
            print(f"{doc.archivo[:58]:<60} ERROR: {type(e).__name__}: {e}")
            continue
        dt = time.time() - t0

        counts, bloqueantes = _resumen_hallazgos(resultado.hallazgos)
        reglas = f"C{counts['CUMPLE']} R{counts['NO_CUMPLE']} N{counts['NO_EVALUABLE']}"
        if bloqueantes:
            reglas += f" !{bloqueantes}"
        prop = (resultado.datos.propietario.valor or "—")[:40]
        print(f"{doc.archivo[:58]:<60} {resultado.legibilidad.value:<9} {resultado.confianza:>5.2f}  "
              f"{reglas:<15} {prop}  ({dt:.1f}s)")

        # Estimación muy gruesa: ~5-10k tokens input, ~1k output con Haiku.
        # $0.80/MT input + $4/MT output ≈ $0.01 por escritura.
        costo_estimado_usd += 0.01

    print(f"\nTiempo total: {time.time() - inicio:.1f}s")
    print(f"Costo estimado: ~${costo_estimado_usd:.2f} USD (verificar en console.anthropic.com → Usage)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
