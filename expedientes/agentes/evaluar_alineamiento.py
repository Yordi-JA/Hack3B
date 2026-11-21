"""Mide qué tan bien extrae el agente de Alineamiento contra datos anotados a mano. Dueño: Diego.

    python -m expedientes.agentes.evaluar_alineamiento                    # corre el agente (gasta API)
    python -m expedientes.agentes.evaluar_alineamiento --reusar           # compara la última corrida, sin API
    python -m expedientes.agentes.evaluar_alineamiento --solo "Tepeji"    # solo archivos que contengan el texto

Entradas (ambas en .gitignore, regla 06):
- `cache/verdad_alineamiento.json`: datos correctos por archivo, anotados a mano.
- `cache/<archivo>.json`: texto OCR de la ingesta.
Salidas en `outputs/`: `pred_alineamiento.json` (lo que extrajo el agente) y `eval_alineamiento.json`.

Por campo cuenta: ok, faltó (había dato y no lo sacó), inventado (no había y sacó algo),
distinto (sacó otro valor).
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from datetime import date
from typing import Optional

from ..config import CACHE_DIR, RAIZ
from ..schemas import Contexto, DocumentoAnalizado
from . import normalizar as nz

VERDAD = CACHE_DIR / "verdad_alineamiento.json"
SALIDA = RAIZ / "outputs"
PRED = SALIDA / "pred_alineamiento.json"

CAMPOS = ["propietario", "direccion", "numero_oficial", "clave_catastral", "superficie_m2",
          "fecha_emision", "vigencia_hasta", "afectaciones"]


def _obtenido(d: DocumentoAnalizado, campo: str) -> Optional[str]:
    datos = d.datos
    if campo == "superficie_m2":
        return datos.superficie_terreno_m2.normalizado
    if campo == "afectaciones":
        c = datos.especificos.get("afectaciones")
        return c.valor if c else None
    c = getattr(datos, campo)
    return c.normalizado if c.normalizado is not None else c.valor


def _iguales(campo: str, esperado, obtenido: str) -> bool:
    if campo == "propietario":
        return nz.nombres_equivalentes(str(esperado), obtenido)
    if campo == "direccion":
        return nz.solapamiento(nz.tokens_direccion(str(esperado)), nz.tokens_direccion(obtenido)) >= 0.6
    if campo == "numero_oficial":
        return nz.numero_oficial(str(esperado)) == nz.numero_oficial(obtenido)
    if campo == "clave_catastral":
        a, b = nz.digitos(str(esperado)), nz.digitos(obtenido)
        return bool(a) and (a == b or nz.claves_equivalentes(a, b))
    if campo == "superficie_m2":
        b = nz.superficie(obtenido)
        return b is not None and abs(float(esperado) - b) <= max(0.5, 0.01 * float(esperado))
    if campo in ("fecha_emision", "vigencia_hasta"):
        if str(esperado).upper() == "INDEFINIDA":
            return obtenido.upper() == "INDEFINIDA"
        return nz.fecha(str(esperado)) == nz.fecha(obtenido)
    if campo == "afectaciones":
        return True  # basta con que ambos digan que hay afectación
    return nz.texto(str(esperado)) == nz.texto(obtenido)


def comparar(verdad: dict, d: DocumentoAnalizado) -> dict[str, dict]:
    out = {}
    for campo in CAMPOS:
        esp, obt = verdad.get(campo), _obtenido(d, campo)
        if esp in (None, "") and obt in (None, ""):
            estado = "ok"
        elif esp in (None, ""):
            estado = "inventado"
        elif obt in (None, ""):
            estado = "faltó"
        else:
            estado = "ok" if _iguales(campo, esp, obt) else "distinto"
        out[campo] = {"estado": estado, "esperado": esp, "obtenido": obt}
    return out


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--reusar", action="store_true", help="comparar outputs/pred_alineamiento.json sin llamar al LLM")
    ap.add_argument("--solo", default="", help="filtrar archivos que contengan este texto")
    ap.add_argument("--fecha", default=None, help="fecha de referencia AAAA-MM-DD")
    a = ap.parse_args(argv)

    if not VERDAD.exists():
        print(f"Falta {VERDAD}")
        return 1
    verdades = [v for v in json.loads(VERDAD.read_text(encoding="utf-8")) if a.solo.lower() in v["archivo"].lower()]
    ctx = Contexto(fecha_referencia=date.fromisoformat(a.fecha)) if a.fecha else Contexto()

    previas = {}
    if PRED.exists():
        previas = {_nfc(p["archivo"]): p for p in json.loads(PRED.read_text(encoding="utf-8"))}

    from ..cache import leer_cache
    from .alineamiento import analizar

    preds: dict[str, DocumentoAnalizado] = {}
    for v in verdades:
        nombre = _nfc(v["archivo"])
        if a.reusar:
            if nombre in previas:
                preds[nombre] = DocumentoAnalizado.model_validate(previas[nombre])
            continue
        leido = leer_cache(nombre)
        if leido is None:
            print(f"  sin caché: {nombre}")
            continue
        print(f"  analizando {nombre} ...", flush=True)
        try:
            preds[nombre] = analizar(leido, ctx)
        except Exception as e:  # que un archivo roto no tumbe la evaluación
            print(f"    ERROR {type(e).__name__}: {e}")

    if not a.reusar:
        previas.update({k: p.model_dump(mode="json") for k, p in preds.items()})
        SALIDA.mkdir(exist_ok=True)
        PRED.write_text(json.dumps(list(previas.values()), ensure_ascii=False, indent=2), encoding="utf-8")

    resultados = {n: comparar(next(v for v in verdades if _nfc(v["archivo"]) == n), p) for n, p in preds.items()}
    if not resultados:
        print("Nada que comparar.")
        return 1

    print(f"\n{'campo':<18}{'ok':>5}{'faltó':>7}{'invent.':>9}{'distinto':>10}{'acierto':>9}")
    for campo in CAMPOS:
        cuenta = {e: sum(r[campo]["estado"] == e for r in resultados.values()) for e in ("ok", "faltó", "inventado", "distinto")}
        print(f"{campo:<18}{cuenta['ok']:>5}{cuenta['faltó']:>7}{cuenta['inventado']:>9}{cuenta['distinto']:>10}"
              f"{cuenta['ok'] / len(resultados):>9.0%}")
    total = sum(r[c]["estado"] == "ok" for r in resultados.values() for c in CAMPOS)
    print(f"\nAcierto global: {total / (len(resultados) * len(CAMPOS)):.0%} en {len(resultados)} archivos")

    print("\nErrores:")
    for n, r in resultados.items():
        for campo, x in r.items():
            if x["estado"] != "ok":
                print(f"  [{x['estado']}] {n} · {campo}: esperado={x['esperado']!r} obtenido={x['obtenido']!r}")

    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "eval_alineamiento.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
