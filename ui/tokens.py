"""Colores y tipografía de la interfaz. Todo color usado en CSS o SVG sale de aquí.

Marca (muestreados con Pillow de las referencias de Tiendas 3B):
- ROJO_3B   #EB1C24: color dominante del círculo de LOGO.jpg.
- VERDE_3B  #4BD811: subrayado verde de "Iconografia, colores.png".
- TINTA_3B  #04211F: titular casi negro con tinte verde de la misma imagen.

El rojo de marca es identidad (logo, navegación activa, acción principal). Los estados del
dictamen usan otra familia de tonos para no confundir "No cumple" con la marca, y siempre
van con texto; el color nunca es la única señal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from expedientes.schemas import EstadoRegla, Legibilidad, Recomendacion, Severidad

ROJO_3B = "#EB1C24"
ROJO_3B_OSCURO = "#C0141B"  # hover y texto rojo sobre claro (contraste AA con texto chico)
VERDE_3B = "#4BD811"
TINTA_3B = "#04211F"

# Superficies
FONDO_APP = TINTA_3B          # detrás del panel principal y en la barra lateral
PANEL = "#F4F5F1"             # panel principal redondeado
TARJETA = "#FFFFFF"
TARJETA_OSCURA = "#0A2C29"    # tarjeta enmarcada
TARJETA_OSCURA_2 = "#163D39"  # botón secundario y separadores dentro de la tarjeta oscura
BORDE = "#DEE2DC"
TEXTO = "#16201F"
TEXTO_2 = "#4D5A57"
TEXTO_SOBRE_OSCURO = "#FFFFFF"
TEXTO_SOBRE_OSCURO_2 = "#B9C9C5"
MAPA_VACIO = "#DCE1DB"
MAPA_VECINO = "#1D4641"


@dataclass(frozen=True)
class Tono:
    texto: str      # texto de la etiqueta sobre `fondo`
    fondo: str      # fondo suave de la etiqueta
    oscuro: str     # el mismo estado sobre la tarjeta oscura (titular, mapa del detalle)
    mapa: str       # relleno de la entidad en el mapa de la bandeja


VERDE = Tono(texto="#1B6A2C", fondo="#E2F3DC", oscuro="#7FE36A", mapa="#9FD88F")
AMBAR = Tono(texto="#844A00", fondo="#FCEFD2", oscuro="#FFC857", mapa="#F2C463")
VINO = Tono(texto="#9E1239", fondo="#FBE4EA", oscuro="#FF9DB4", mapa="#E494A8")
AZUL = Tono(texto="#2B5275", fondo="#E3ECF4", oscuro="#A9CBEA", mapa="#B5CDE3")
GRIS = Tono(texto="#47524F", fondo="#E9ECE7", oscuro="#C9D3D0", mapa=MAPA_VACIO)

ESTADO: dict[Optional[Recomendacion], Tono] = {
    Recomendacion.CUMPLE: VERDE,
    Recomendacion.REQUIERE_REVISION: AMBAR,
    Recomendacion.NO_CUMPLE: VINO,
    None: GRIS,
}

REGLA: dict[EstadoRegla, Tono] = {
    EstadoRegla.CUMPLE: VERDE,
    EstadoRegla.NO_CUMPLE: VINO,
    EstadoRegla.NO_EVALUABLE: AZUL,
}

SEVERIDAD: dict[Severidad, Tono] = {
    Severidad.BLOQUEANTE: VINO,
    Severidad.REVISION: AMBAR,
    Severidad.INFO: GRIS,
}

LEGIBILIDAD: dict[Legibilidad, Tono] = {
    Legibilidad.BUENA: GRIS,
    Legibilidad.PARCIAL: AMBAR,
    Legibilidad.ILEGIBLE: VINO,
}

# Tipografía: sin fuentes externas (regla 06, todo local). Texto en Source Sans, que Streamlit
# trae empaquetada y lee bien en párrafos legales largos. El titular pesado imita el rótulo
# de 3B, que usa una grotesca negra; Arial Black / Segoe UI Black están en Windows y macOS.
FUENTE_TEXTO = '"Source Sans", "Source Sans Pro", "Segoe UI", Arial, sans-serif'
FUENTE_TITULAR = '"Arial Black", "Segoe UI Black", "Helvetica Neue", Arial, sans-serif'


def contraste(a: str, b: str) -> float:
    """Razón de contraste WCAG 2.x entre dos colores #RRGGBB."""

    def lum(hex_: str) -> float:
        canales = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)
