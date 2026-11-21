"""Normalización para comparar datos entre documentos. Dueño: Diego (lo usan alineamiento y cruce).

Cualquier agente puede usar estas funciones para llenar `Campo.normalizado`, pero `cruce`
vuelve a normalizar lo que recibe, así que no es obligatorio.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Optional

MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7,
    "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}


def texto(s: Optional[str]) -> str:
    """Mayúsculas, sin acentos ni signos, espacios simples."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def digitos(s: Optional[str]) -> str:
    return re.sub(r"\D", "", s or "")


# ---------------------------------------------------------------- claves y números

def clave_catastral(s: Optional[str]) -> Optional[str]:
    """Solo dígitos. Devuelve None si no parece una clave catastral (menos de 8 dígitos):
    cuentas prediales como 'U-04817' no se deben comparar contra claves catastrales."""
    d = digitos(s)
    return d if len(d) >= 8 else None


def claves_equivalentes(a: str, b: str) -> bool:
    """Iguales, o iguales salvo ceros de relleno al final (algunos municipios los omiten)."""
    return a == b or (a.rstrip("0") == b.rstrip("0") and min(len(a), len(b)) >= 8)


SIN_NUMERO = "SN"


def numero_oficial(s: Optional[str]) -> Optional[str]:
    """'No. 28' -> '28'; 'S/N', 'sin número' -> 'SN'; '104-A' -> '104A'; 'KM 27.5 No. 1' -> '1'."""
    t = texto(s)
    if not t:
        return None
    if re.search(r"\bS N\b|\bSN\b|SIN NUMERO|SIN NUM\b|^S$", t):
        return SIN_NUMERO
    t = re.sub(r"\b(NUMERO|NUM|NO|N|OFICIAL|EXT|EXTERIOR|INT)\b", " ", t)
    m = re.findall(r"\b(\d+)\s*([A-Z])?\b", t)
    if not m:
        return None
    num, letra = m[-1]
    return f"{int(num)}{letra or ''}"


# ---------------------------------------------------------------- superficies y fechas

def superficie(s: Optional[str]) -> Optional[float]:
    """'1,039.71 m2' -> 1039.71; '245,00 m²' -> 245.0; '536.82 M²' -> 536.82."""
    if not s:
        return None
    m = re.search(r"\d[\d.,\s]*", s.replace(" ", " "))
    if not m:
        return None
    n = m.group(0).strip().replace(" ", "")
    if "," in n and "." in n:          # 1,039.71  o  1.039,71
        n = n.replace(",", "") if n.rfind(".") > n.rfind(",") else n.replace(".", "").replace(",", ".")
    elif "," in n:                      # 245,00 (decimal)  o  1,039 (miles)
        ent, _, dec = n.rpartition(",")
        n = f"{ent.replace(',', '')}.{dec}" if len(dec) != 3 else n.replace(",", "")
    try:
        return float(n.rstrip("."))
    except ValueError:
        return None


def fecha(s: Optional[str]) -> Optional[date]:
    """ISO, dd/mm/aaaa o '17 de febrero de 2025'. Devuelve None si no se puede leer."""
    if not s:
        return None
    s = s.strip()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return _fecha_segura(y, mo, d)
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", s)
    if m:
        d, mo, y = map(int, m.groups())
        return _fecha_segura(y + 2000 if y < 100 else y, mo, d)
    t = texto(s)
    m = re.search(r"(\d{1,2}) (?:DE )?([A-Z]+) (?:DE |DEL )?(?:ANO )?(\d{4})", t)
    if m and m.group(2) in MESES:
        return _fecha_segura(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
    return None


def _fecha_segura(y: int, mo: int, d: int) -> Optional[date]:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def sumar_meses(f: date, meses: int) -> date:
    y, m = divmod(f.month - 1 + meses, 12)
    y, m = f.year + y, m + 1
    for dia in (f.day, 30, 29, 28):
        r = _fecha_segura(y, m, dia)
        if r:
            return r
    raise ValueError(f)


# ---------------------------------------------------------------- nombres y direcciones

_VACIAS_NOMBRE = {
    "C", "CC", "SR", "SRA", "SRES", "LIC", "ING", "ARQ", "DR", "DE", "DEL", "LA", "LAS", "LOS", "Y",
    "SA", "CV", "S", "A", "V", "RL", "SC", "SAPI", "APELLIDOS", "SUCESION", "REPRESENTANTE", "LEGAL",
}
_EQUIV_NOMBRE = {"MA": "MARIA", "MARIA": "MARIA", "J": "JOSE", "FCO": "FRANCISCO", "GPE": "GUADALUPE"}


def tokens_nombre(s: Optional[str]) -> set[str]:
    return {_EQUIV_NOMBRE.get(t, t) for t in texto(s).split() if t not in _VACIAS_NOMBRE and len(t) > 1}


_VACIAS_DIR = {
    "CALLE", "C", "AV", "AVENIDA", "BLVD", "BOULEVARD", "BULEVAR", "CALZ", "CALZADA", "CARRETERA", "CARR",
    "NO", "NUM", "NUMERO", "N", "OFICIAL", "COL", "COLONIA", "FRACC", "FRACCIONAMIENTO", "BARRIO", "BO",
    "MUNICIPIO", "MPIO", "ESTADO", "EDO", "DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "EN", "ESQ",
    "ESQUINA", "CON", "CP", "C P", "MEXICO", "MEX", "HGO", "HIDALGO", "SN", "S", "SIN", "LOTE", "LT",
    "MZA", "MZ", "MANZANA", "UBICADO", "PREDIO", "INMUEBLE", "CENTRO", "CABECERA",
}


def tokens_direccion(s: Optional[str]) -> set[str]:
    return {t for t in texto(s).split() if t not in _VACIAS_DIR and (len(t) > 1 or t.isdigit())}


def solapamiento(a: set[str], b: set[str]) -> float:
    """Proporción del conjunto más chico que aparece en el otro (0 si alguno está vacío)."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def nombres_equivalentes(a: str, b: str) -> bool:
    """Orden indistinto ('CORTES PENA MA TERESA' = 'MARIA TERESA CORTES PENA') y tolera
    que un documento liste a varios copropietarios y otro solo a uno."""
    return solapamiento(tokens_nombre(a), tokens_nombre(b)) >= 0.75
