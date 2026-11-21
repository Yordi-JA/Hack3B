"""Mide qué tan bien extrae el agente de Alineamiento contra datos anotados a mano. Dueño: Diego.

    python -m expedientes.agentes.evaluar_alineamiento                    # dice cuántas llamadas haría
    python -m expedientes.agentes.evaluar_alineamiento --confirmar        # las hace (gasta saldo; avisar antes)
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
import re
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
          "fecha_emision", "vigencia_hasta", "afectaciones", "alineamiento", "autoridad_emisora"]

# Palabras que no identifican a la autoridad (cargos, conectores, "H. Ayuntamiento").
_VACIAS_AUTORIDAD = {"DIRECCION", "DIRECTOR", "DIRECTORA", "A", "DE", "DEL", "Y", "LA", "EL", "SU", "H",
                     "AYUNTAMIENTO", "CONSTITUCIONAL", "MUNICIPAL", "MUNICIPALES", "MUNICIPIO", "ING", "LIC",
                     "ARQ", "MTRA", "C", "COORDINACION", "SECRETARIA", "SECCION", "AREA"}


def _tokens_autoridad(s: str) -> set[str]:
    return {t for t in nz.texto(s).split() if t not in _VACIAS_AUTORIDAD and len(t) > 2}


def _obtenido(d: DocumentoAnalizado, campo: str) -> Optional[str]:
    datos = d.datos
    if campo == "superficie_m2":
        return datos.superficie_terreno_m2.normalizado
    if campo in ("afectaciones", "alineamiento"):
        c = datos.especificos.get(campo)
        return c.valor if c else None
    if campo == "autoridad_emisora":
        return datos.autoridad_emisora.valor
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
    if campo in ("afectaciones", "alineamiento"):
        return True  # basta con que ambos digan que existe
    if campo == "autoridad_emisora":
        # Debe nombrar la dependencia (Desarrollo Urbano, Obras Públicas, Catastro...), no solo el
        # ayuntamiento ni la persona que firma.
        dependencia = re.search(r"DESARROLLO|OBRAS|CATASTRO|LICENCIAS|ORDENAMIENTO|URBANISMO", nz.texto(obtenido))
        return bool(dependencia) and nz.solapamiento(_tokens_autoridad(str(esperado)), _tokens_autoridad(obtenido)) >= 0.5
    return nz.texto(str(esperado)) == nz.texto(obtenido)


def comparar(verdad: dict, d: DocumentoAnalizado) -> dict[str, dict]:
    out = {}
    for campo in CAMPOS:
        esp, obt = verdad.get(campo), _obtenido(d, campo)
        if campo == "alineamiento":  # en la verdad solo está anotado si la constancia lo trae (sí/no)
            esp = "sí" if verdad.get("contiene_alineamiento") else None
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
    ap.add_argument("--confirmar", action="store_true", help="autoriza llamadas nuevas a la API (gasta saldo)")
    a = ap.parse_args(argv)
    from ..cache import leer_cache

    if not VERDAD.exists():
        print(f"Falta {VERDAD}")
        return 1
    verdades = [v for v in json.loads(VERDAD.read_text(encoding="utf-8")) if a.solo.lower() in v["archivo"].lower()]
    ctx = Contexto(fecha_referencia=date.fromisoformat(a.fecha)) if a.fecha else Contexto()

    previas = {}
    if PRED.exists():
        previas = {_nfc(p["archivo"]): p for p in json.loads(PRED.read_text(encoding="utf-8"))}

    from .alineamiento import analizar

    # Reglas de créditos: avisar cuántas llamadas nuevas haría y pedir confirmación explícita.
    if not a.reusar:
        from .alineamiento import _paginas_como_texto, _ruta_respuesta
        nuevas = []
        for v in verdades:
            leido = leer_cache(_nfc(v["archivo"]))
            if leido is None or not any(p.texto.strip() for p in leido.paginas):
                continue
            ruta, huella = _ruta_respuesta(leido, f"Archivo: {leido.archivo}\n\n{_paginas_como_texto(leido)}")
            if not (ruta.exists() and json.loads(ruta.read_text(encoding="utf-8")).get("huella") == huella):
                nuevas.append(leido.archivo)
        if nuevas and not a.confirmar:
            print(f"Haría {len(nuevas)} llamadas nuevas a la API (el resto sale del disco). "
                  f"Avisa en el grupo y vuelve a correr con --confirmar, o usa --reusar.")
            return 2

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
