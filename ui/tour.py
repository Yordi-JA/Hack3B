"""Recorrido guiado (spotlight) de la bandeja. Dueño: Diego.

Sin JavaScript: en cada paso se inyecta un bloque <style> que ilumina el elemento objetivo (un
contenedor con `key`, que Streamlit expone como clase `.st-key-<key>`) y oscurece el resto. La
tarjeta del paso es un contenedor fijo con botones de Streamlit, así que avanzar no recarga la página.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import streamlit as st

from . import tokens as t

CLAVE = "tour"


@dataclass(frozen=True)
class Paso:
    titulo: str
    texto: str
    objetivo: Optional[str] = None   # clave del contenedor (st-key-...) a iluminar; None = bienvenida
    lateral: bool = False            # el objetivo está en la barra lateral
    ancla: Optional[str] = None      # si el objetivo queda bajo el pliegue, enlace para bajar hasta él


PASOS: list[Paso] = [
    Paso("Bienvenido a la revisión de expedientes",
         "En un minuto te mostramos cómo leer la bandeja: indicadores, mapa por estado, filtros y "
         "expedientes. Puedes salir del recorrido cuando quieras."),
    Paso("Menú",
         "Desde aquí vas a la bandeja, subes un expediente nuevo para analizarlo o repites este recorrido.",
         "nav-bandeja", lateral=True),
    Paso("Indicadores",
         "Cuántos expedientes hay y cuántos cumplen, requieren revisión o no cumplen. Haz clic en una "
         "tarjeta para filtrar la lista.", "b-kpis"),
    Paso("Mapa por estado",
         "Cada estado toma el color de la recomendación que predomina en sus expedientes: verde cumple, "
         "ámbar requiere revisión y rojo no cumple. El número es cuántos expedientes tiene.", "b-mapa"),
    Paso("Ventana del estado",
         "Al hacer clic en un estado se abre una ventana sobre el mapa con el porcentaje de cada "
         "recomendación. Desde ahí entras a los expedientes de ese estado.", "b-mapa"),
    Paso("Filtros",
         "Filtra por estado, por recomendación o busca por expediente, municipio, propietario o archivo.",
         "b-filtros", ancla="expedientes"),
    Paso("Expedientes",
         "Primero los que no cumplen, luego los que requieren revisión. Abre uno para ver el dictamen, "
         "las inconsistencias y la evidencia de cada hallazgo.", "b-lista", ancla="expedientes"),
    Paso("Subir un expediente",
         "Sube los PDF o imágenes de un inmueble: el sistema clasifica cada documento, extrae los datos, "
         "los cruza y emite la recomendación con su evidencia.", "nav-nuevo", lateral=True),
]

_SOMBRA = "rgba(4,33,31,.58)"


def activo() -> Optional[int]:
    paso = st.session_state.get(CLAVE)
    return paso if isinstance(paso, int) and 0 <= paso < len(PASOS) else None


def iniciar() -> None:
    st.session_state[CLAVE] = 0


def _mover(delta: int) -> None:
    paso = activo()
    if paso is None:
        return
    nuevo = paso + delta
    st.session_state[CLAVE] = nuevo if 0 <= nuevo < len(PASOS) else None


def salir() -> None:
    st.session_state[CLAVE] = None


def css_paso(paso: Paso) -> str:
    """Bloque <style> del paso. Solo la etiqueta style (st.html la inyecta como hoja de estilos)."""
    reglas = []
    oscurecer_lateral = (
        '[data-testid="stSidebarContent"] { position: relative; } '
        f'[data-testid="stSidebarContent"]::after {{ content: ""; position: absolute; inset: 0; '
        f"background: {_SOMBRA}; z-index: 998; pointer-events: none; }}"
    )
    oscurecer_principal = (
        f'[data-testid="stMain"]::after {{ content: ""; position: fixed; inset: 0; background: {_SOMBRA}; '
        "z-index: 998; pointer-events: none; }"
    )
    if paso.objetivo is None:
        reglas += [oscurecer_lateral, oscurecer_principal]
    elif paso.lateral:
        reglas.append(oscurecer_principal)
        reglas.append(
            f'[data-testid="stSidebar"] .st-key-{paso.objetivo} {{ position: relative; z-index: 999; '
            "border-radius: 22px 0 0 22px; box-shadow: 0 0 0 3px #fff, 0 0 0 9px rgba(255,255,255,.35); }"
        )
    else:
        reglas.append(oscurecer_lateral)
        reglas.append(
            f".st-key-{paso.objetivo} {{ position: relative; z-index: 999; border-radius: 16px; "
            f"box-shadow: 0 0 0 4px #fff, 0 0 0 9999px {_SOMBRA}; scroll-margin: 80px; }}"
        )
    centrada = paso.objetivo is None
    reglas.append(
        ".st-key-tour-card { position: fixed; z-index: 1001; width: 380px; max-width: calc(100vw - 32px); "
        f"background: #fff; border-radius: 16px; padding: 20px 22px 14px; border-top: 5px solid {t.ROJO_3B}; "
        "box-shadow: 0 18px 48px rgba(0,0,0,.28); "
        + ("left: 50%; top: 50%; transform: translate(-50%, -50%); }" if centrada else "right: 32px; bottom: 32px; }")
    )
    return "<style>" + " ".join(reglas) + "</style>"


def tarjeta(i: int) -> str:
    p = PASOS[i]
    from html import escape
    return (
        f'<div class="tour-paso">Paso {i + 1} de {len(PASOS)}</div>'
        f'<h3 class="tour-titulo">{escape(p.titulo)}</h3><p class="tour-texto">{escape(p.texto)}</p>'
        + (f'<a class="tour-ir" href="#{p.ancla}">Ir a esta sección ↓</a>' if p.ancla else "")
    )


def mostrar(html) -> None:
    """Dibuja el paso activo (si hay recorrido). `html` es vistas.html, para no duplicar el saneo."""
    i = activo()
    if i is None:
        return
    st.html(css_paso(PASOS[i]))
    with st.container(key="tour-card"):
        html(tarjeta(i))
        a, b, c = st.columns([1, 1, 1.2])
        a.button("Salir", key="tour-salir", on_click=salir, type="tertiary")
        b.button("Anterior", key="tour-ant", on_click=_mover, args=(-1,), disabled=i == 0)
        ultimo = i == len(PASOS) - 1
        c.button("Terminar" if ultimo else "Siguiente", key="tour-sig", on_click=_mover, args=(1,), type="primary")
