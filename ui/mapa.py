"""Mapa de México por entidad federativa, en SVG local (sin teselas ni CDN).

`assets/mexico.json` se generó una sola vez desde el mapa de un proyecto anterior del equipo:
trazos absolutos simplificados, `bbox` y punto de etiqueta por estado, con ids ISO 3166-2 (MXHID...).
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from expedientes.schemas import Recomendacion

from . import tokens

ASSET = Path(__file__).resolve().parent / "assets" / "mexico.json"

# normalizado (mayúsculas sin acentos, como lo pide el contrato) -> (id del SVG, nombre visible)
ENTIDADES: dict[str, tuple[str, str]] = {
    "AGUASCALIENTES": ("MXAGU", "Aguascalientes"),
    "BAJA CALIFORNIA": ("MXBCN", "Baja California"),
    "BAJA CALIFORNIA SUR": ("MXBCS", "Baja California Sur"),
    "CAMPECHE": ("MXCAM", "Campeche"),
    "CHIAPAS": ("MXCHP", "Chiapas"),
    "CHIHUAHUA": ("MXCHH", "Chihuahua"),
    "CIUDAD DE MEXICO": ("MXCMX", "Ciudad de México"),
    "COAHUILA": ("MXCOA", "Coahuila"),
    "COLIMA": ("MXCOL", "Colima"),
    "DURANGO": ("MXDUR", "Durango"),
    "GUANAJUATO": ("MXGUA", "Guanajuato"),
    "GUERRERO": ("MXGRO", "Guerrero"),
    "HIDALGO": ("MXHID", "Hidalgo"),
    "JALISCO": ("MXJAL", "Jalisco"),
    "MEXICO": ("MXMEX", "Estado de México"),
    "MICHOACAN": ("MXMIC", "Michoacán"),
    "MORELOS": ("MXMOR", "Morelos"),
    "NAYARIT": ("MXNAY", "Nayarit"),
    "NUEVO LEON": ("MXNLE", "Nuevo León"),
    "OAXACA": ("MXOAX", "Oaxaca"),
    "PUEBLA": ("MXPUE", "Puebla"),
    "QUERETARO": ("MXQUE", "Querétaro"),
    "QUINTANA ROO": ("MXROO", "Quintana Roo"),
    "SAN LUIS POTOSI": ("MXSLP", "San Luis Potosí"),
    "SINALOA": ("MXSIN", "Sinaloa"),
    "SONORA": ("MXSON", "Sonora"),
    "TABASCO": ("MXTAB", "Tabasco"),
    "TAMAULIPAS": ("MXTAM", "Tamaulipas"),
    "TLAXCALA": ("MXTLA", "Tlaxcala"),
    "VERACRUZ": ("MXVER", "Veracruz"),
    "YUCATAN": ("MXYUC", "Yucatán"),
    "ZACATECAS": ("MXZAC", "Zacatecas"),
}

# Variantes que un agente o un documento pueden escribir y que no son el nombre corto.
ALIAS: dict[str, str] = {
    "ESTADO DE MEXICO": "MEXICO",
    "EDO DE MEXICO": "MEXICO",
    "EDO MEX": "MEXICO",
    "EDOMEX": "MEXICO",
    "MEX": "MEXICO",
    "CDMX": "CIUDAD DE MEXICO",
    "DISTRITO FEDERAL": "CIUDAD DE MEXICO",
    "COAHUILA DE ZARAGOZA": "COAHUILA",
    "MICHOACAN DE OCAMPO": "MICHOACAN",
    "VERACRUZ DE IGNACIO DE LA LLAVE": "VERACRUZ",
    "ESTADO DE HIDALGO": "HIDALGO",
}


def normalizar_texto(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    limpio = "".join(c if c.isalnum() else " " for c in sin_acentos.upper())
    return " ".join(limpio.split())


def normalizar_entidad(texto: Optional[str]) -> Optional[str]:
    """Devuelve la clave canónica de ENTIDADES, o None si no se reconoce."""
    if not texto:
        return None
    clave = normalizar_texto(texto)
    clave = ALIAS.get(clave, clave)
    return clave if clave in ENTIDADES else None


def nombre_entidad(clave: Optional[str]) -> str:
    if clave in ENTIDADES:
        return ENTIDADES[clave][1]
    return clave.title() if clave else "Sin entidad"


@lru_cache(maxsize=1)
def _geometria() -> dict:
    return json.loads(ASSET.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ colores (lógica pura)

ORDEN_GRAVEDAD = [Recomendacion.CUMPLE, Recomendacion.REQUIERE_REVISION, Recomendacion.NO_CUMPLE]


@dataclass
class ConteoEntidad:
    total: int = 0
    por_recomendacion: dict[Recomendacion, int] = field(default_factory=dict)

    @property
    def peor(self) -> Optional[Recomendacion]:
        presentes = [r for r in ORDEN_GRAVEDAD if self.por_recomendacion.get(r)]
        return presentes[-1] if presentes else None

    @property
    def predominante(self) -> Optional[Recomendacion]:
        """La recomendación con más expedientes en el estado; en empate, la más grave."""
        presentes = [r for r in ORDEN_GRAVEDAD if self.por_recomendacion.get(r)]
        if not presentes:
            return None
        return max(presentes, key=lambda r: (self.por_recomendacion[r], ORDEN_GRAVEDAD.index(r)))

    def porcentaje(self, r: Recomendacion) -> float:
        return self.por_recomendacion.get(r, 0) / self.total if self.total else 0.0


def relleno_por_entidad(conteos: dict[str, ConteoEntidad], criterio: str = "peor") -> dict[str, str]:
    """id SVG -> color de relleno. `criterio="peor"`: la recomendación más grave del estado;
    `"predominante"`: la que más expedientes tiene (el color "promedio" del estado). Sin
    expedientes queda neutro. El número de expedientes se dibuja aparte, nunca solo color."""
    rellenos = {}
    for clave, (id_svg, _) in ENTIDADES.items():
        conteo = conteos.get(clave)
        rec = (conteo.predominante if criterio == "predominante" else conteo.peor) if conteo else None
        rellenos[id_svg] = tokens.ESTADO[rec].mapa if rec else tokens.MAPA_VACIO
    return rellenos


def abreviatura(clave: str) -> str:
    """'HIDALGO' -> 'HID' (ISO 3166-2 sin el prefijo MX)."""
    return ENTIDADES[clave][0][2:] if clave in ENTIDADES else ""


def punto_etiqueta(clave: Optional[str]) -> Optional[tuple[float, float]]:
    """Punto de la entidad en unidades del mapa (1000 x 630), para anclar la ventana emergente."""
    if clave not in ENTIDADES:
        return None
    estado = _geometria()["estados"].get(ENTIDADES[clave][0])
    if not estado:
        return None
    x, y = estado.get("etiqueta", [0, 0])
    return (float(x), float(y))


def _tooltip(clave: str, conteo: Optional[ConteoEntidad]) -> str:
    nombre = nombre_entidad(clave)
    if not conteo or not conteo.total:
        return f"{nombre}: sin expedientes"
    partes = [f"{n} {r.value}" for r in reversed(ORDEN_GRAVEDAD) if (n := conteo.por_recomendacion.get(r))]
    plural = "expediente" if conteo.total == 1 else "expedientes"
    return f"{nombre}: {conteo.total} {plural} ({', '.join(partes)})"


def etiqueta_accesible(clave: str, conteo: ConteoEntidad) -> str:
    """Para lectores de pantalla: 'Hidalgo: 1 expediente, requiere revisión'."""
    plural = "expediente" if conteo.total == 1 else "expedientes"
    partes = [
        f"{n} {r.value.lower()}" if conteo.total > 1 else r.value.lower()
        for r in reversed(ORDEN_GRAVEDAD) if (n := conteo.por_recomendacion.get(r))
    ]
    return f"{nombre_entidad(clave)}: {conteo.total} {plural}, {', '.join(partes)}"


# A escala nacional, los estados del centro miden pocas unidades y sus números se encimarían. Su
# número va en una burbuja fuera del estado, unida con una línea, en un punto libre del mapa.
LLAMADAS = {
    "QUERETARO": (545, 357),
    "HIDALGO": (642, 368),
    "AGUASCALIENTES": (478, 333),
    "MEXICO": (530, 478),
    "CIUDAD DE MEXICO": (560, 535),
    "MORELOS": (624, 550),
    "TLAXCALA": (684, 428),
}


def _bajo_llamada(x: float, y: float, radio: float = 30) -> bool:
    """La abreviatura quedaría debajo de la burbuja de un estado chico (ej. SLP bajo Querétaro)."""
    return any((x - lx) ** 2 + (y - ly) ** 2 < radio ** 2 for lx, ly in LLAMADAS.values())


def svg_bandeja(
    conteos: dict[str, ConteoEntidad], seleccion: Optional[str], params_base: dict[str, str],
    criterio: str = "predominante", abreviaturas: bool = True, numeros: bool = True,
) -> str:
    """Mapa de todo el país. Cada estado con expedientes es un enlace que filtra la bandeja y abre
    su ventana con los porcentajes. Con `abreviaturas`, cada estado grande lleva su clave (BCN, SON...).
    Con `numeros=False` no se dibujan conteos ni burbujas: solo el color (el detalle va en la ventana)."""
    geo = _geometria()
    rellenos = relleno_por_entidad(conteos, criterio)
    partes = [
        '<svg class="mx-mapa" viewBox="0 0 1000 630" role="group" '
        'aria-label="Mapa de expedientes por entidad federativa" xmlns="http://www.w3.org/2000/svg">'
    ]
    etiquetas = []
    for clave, (id_svg, _) in ENTIDADES.items():
        estado = geo["estados"].get(id_svg)
        if not estado:
            continue
        conteo = conteos.get(clave)
        clases = "mx-estado" + (" mx-sel" if clave == seleccion else "")
        trazo = (
            f'<path class="{clases}" d="{estado["d"]}" fill="{rellenos[id_svg]}">'
            f"<title>{escape(_tooltip(clave, conteo))}</title></path>"
        )
        if conteo and conteo.total:
            nuevo = dict(params_base, entidad="" if clave == seleccion else clave)
            href = escape("?" + urlencode({k: v for k, v in nuevo.items() if v}))
            trazo = (
                f'<a href="{href}" target="_self" class="mx-enlace" '
                f'aria-label="{escape(etiqueta_accesible(clave, conteo))}">{trazo}</a>'
            )
            x, y = estado.get("etiqueta", [0, 0])
            if not numeros:
                if abreviaturas and clave not in LLAMADAS:
                    etiquetas.append(
                        f'<text class="mx-abr" x="{x}" y="{y}" text-anchor="middle" '
                        f'dominant-baseline="central">{abreviatura(clave)}</text>'
                    )
            elif clave in LLAMADAS:
                lx, ly = LLAMADAS[clave]
                # Enlace duplicado solo para el mouse; el lector de pantalla ya tiene el del estado.
                etiquetas.append(
                    f'<line class="mx-guia" x1="{x}" y1="{y}" x2="{lx}" y2="{ly}"/>'
                    f'<a href="{href}" target="_self" class="mx-llamada" tabindex="-1" aria-hidden="true">'
                    f'<circle cx="{lx}" cy="{ly}" r="15" fill="{rellenos[id_svg]}"/>'
                    f'<text class="mx-num" x="{lx}" y="{ly}" text-anchor="middle" dominant-baseline="central">'
                    f"{conteo.total}</text></a>"
                )
            else:
                if abreviaturas:
                    etiquetas.append(
                        f'<text class="mx-abr" x="{x}" y="{y - 13}" text-anchor="middle" '
                        f'dominant-baseline="central">{abreviatura(clave)}</text>'
                    )
                    y += 6
                etiquetas.append(
                    f'<text class="mx-num mx-num-halo" x="{x}" y="{y}" text-anchor="middle" '
                    f'dominant-baseline="central">{conteo.total}</text>'
                )
        elif abreviaturas and clave not in LLAMADAS and not (numeros and _bajo_llamada(*estado.get("etiqueta", [0, 0]))):
            x, y = estado.get("etiqueta", [0, 0])
            etiquetas.append(
                f'<text class="mx-abr" x="{x}" y="{y}" text-anchor="middle" '
                f'dominant-baseline="central">{abreviatura(clave)}</text>'
            )
        partes.append(trazo)
    # La selección se dibuja al final para que su borde no quede tapado por los vecinos.
    if seleccion in ENTIDADES and (estado := geo["estados"].get(ENTIDADES[seleccion][0])):
        partes.append(f'<path class="mx-borde-sel" d="{estado["d"]}"/>')
    partes.extend(etiquetas)
    partes.append("</svg>")
    return "".join(partes)


def caja_de_vista(clave: Optional[str], margen: float = 1.6, minimo: float = 140.0) -> tuple[float, float, float, float]:
    """viewBox centrado en una entidad con sus vecinos alrededor. Sin entidad: todo el país."""
    geo = _geometria()
    if clave not in ENTIDADES or ENTIDADES[clave][0] not in geo["estados"]:
        return (0.0, 0.0, 1000.0, 630.0)
    x0, y0, x1, y1 = geo["estados"][ENTIDADES[clave][0]]["bbox"]
    ancho = max((x1 - x0) * (1 + 2 * margen), minimo)
    alto = max((y1 - y0) * (1 + 2 * margen), minimo * 0.75)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return (round(cx - ancho / 2, 1), round(cy - alto / 2, 1), round(ancho, 1), round(alto, 1))


def svg_detalle(clave: Optional[str], color: str) -> str:
    """Mapa recortado a la entidad del expediente, resaltada con el color de su recomendación."""
    geo = _geometria()
    x, y, w, h = caja_de_vista(clave)
    resaltado = ENTIDADES[clave][0] if clave in ENTIDADES else None
    nombre = nombre_entidad(clave) if resaltado else "entidad no identificada"
    partes = [
        f'<svg class="mx-mapa-detalle" viewBox="{x} {y} {w} {h}" preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-label="Ubicación: {escape(nombre)}" xmlns="http://www.w3.org/2000/svg">'
    ]
    for id_svg, estado in geo["estados"].items():
        if id_svg == resaltado:
            continue
        partes.append(f'<path class="mx-vecino" d="{estado["d"]}"/>')
    if resaltado:
        partes.append(f'<path class="mx-resaltado" d="{geo["estados"][resaltado]["d"]}" fill="{color}"/>')
    partes.append("</svg>")
    return "".join(partes)
