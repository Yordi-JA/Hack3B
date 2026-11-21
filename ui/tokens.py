"""Colores y tipografía de la interfaz. Todo color usado en CSS o SVG sale de aquí.

Marca (muestreados con Pillow de las referencias de Tiendas 3B):
- ROJO_3B   #EB1C24: color dominante del círculo de LOGO.jpg.
- VERDE_3B  #4BD811: subrayado verde de "Iconografia, colores.png".
- TINTA_3B  #04211F: titular casi negro con tinte verde de la misma imagen.

Dirección "Rojo 3B + blanco": barra lateral y marco de la app en rojo, contenido en blanco. La
tinta es solo color de texto. El rojo de marca es identidad (logo, navegación, acción principal,
tarjeta del dictamen). Los estados del
dictamen usan otra familia de tonos para no confundir "No cumple" con la marca, y siempre
van con texto; el color nunca es la única señal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from expedientes.schemas import EstadoRegla, Legibilidad, Recomendacion, Severidad

ROJO_3B = "#EB1C24"           # logo y línea del marco del dictamen (no lleva texto encima)
ROJO_3B_SIDEBAR = "#D9161E"   # barra lateral y marco de la app: el rojo de marca apenas más hondo
                              # para que el texto blanco pase AA (5.1:1; sobre #EB1C24 sería 4.45)
ROJO_3B_OSCURO = "#C0141B"    # botón principal, título DICTAMEN, KPI principal, texto rojo sobre blanco
VERDE_3B = "#4BD811"          # color secundario: acción de analizar y filtros activos de la bandeja
VERDE_3B_HOVER = "#3DB30D"    # hover del botón verde; la tinta encima sigue en 6.2:1
TINTA_3B = "#04211F"          # solo texto y líneas finas; nunca como superficie

# Superficies: rojo de marca alrededor, blanco y gris muy claro adentro.
FONDO_APP = ROJO_3B_SIDEBAR   # detrás del panel principal y en la barra lateral
PANEL = "#F4F5F1"             # panel principal redondeado
TARJETA = "#FFFFFF"
BORDE = "#DEE2DC"
RADIO = 6                     # px: radio de toda caja con línea de 2 px (Subir expediente, Detalle)
TEXTO = "#16201F"
TEXTO_2 = "#4D5A57"
TEXTO_SOBRE_ROJO = "#FFFFFF"  # blanco puro: con transparencia baja a ~3:1 sobre el rojo
MAPA_VACIO = "#DCE1DB"


@dataclass(frozen=True)
class Tono:
    texto: str      # texto de la etiqueta sobre `fondo`; también el fondo del sello del dictamen
    fondo: str      # fondo suave de la etiqueta
    mapa: str       # relleno de la entidad en los mapas


VERDE = Tono(texto="#1B6A2C", fondo="#E2F3DC", mapa="#9FD88F")
AMBAR = Tono(texto="#844A00", fondo="#FCEFD2", mapa="#F2C463")
VINO = Tono(texto="#9E1239", fondo="#FBE4EA", mapa="#E494A8")
AZUL = Tono(texto="#2B5275", fondo="#E3ECF4", mapa="#B5CDE3")
GRIS = Tono(texto="#47524F", fondo="#E9ECE7", mapa=MAPA_VACIO)

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
FUENTE_UI = FUENTE_TEXTO  # el inicio usa la misma letra que Subir expediente


def contraste(a: str, b: str) -> float:
    """Razón de contraste WCAG 2.x entre dos colores #RRGGBB."""

    def lum(hex_: str) -> float:
        canales = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)
