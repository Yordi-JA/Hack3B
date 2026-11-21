"""Recorrido guiado (spotlight) de la bandeja. Dueño: Diego.

En cada paso se inyecta un bloque <style> que ilumina el elemento objetivo (un contenedor con
`key`, que Streamlit expone como clase `.st-key-<key>`) y oscurece el resto. La tarjeta del paso es
un contenedor fijo con botones de Streamlit, así que avanzar no recarga la página.

`GUION` es JavaScript que corre en la página principal (scroll al objetivo, foco y Esc). Es una
constante: nunca interpoles datos en él en tiempo de ejecución.
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
    izquierda: bool = False          # tarjeta abajo a la izquierda (cuando a la derecha taparía lo que explica)


PASOS: list[Paso] = [
    Paso("Bienvenido a la revisión de expedientes",
         "En un minuto te mostramos cómo leer el inicio: indicadores, mapa por estado, filtros y "
         "expedientes. Puedes salir del recorrido cuando quieras."),
    Paso("Menú",
         "Desde aquí vas al inicio o subes un expediente nuevo para analizarlo. Para repetir este recorrido, "
         "usa el botón del gallo abajo a la derecha.",
         "nav-bandeja", lateral=True),
    Paso("Indicadores",
         "Cuántos expedientes hay y cuántos cumplen, requieren revisión o tienen posibles motivos de rechazo, "
         "además de los que la abogada ya rechazó. Haz clic en una tarjeta para filtrar la lista.", "b-kpis"),
    Paso("Mapa por estado",
         "Cada estado toma el color que predomina en sus expedientes: verde si cumplen o la abogada los "
         "aprobó, ámbar si requieren revisión y vino si la abogada los rechazó. Los estados en gris no tienen "
         "expedientes.", "b-mapa", izquierda=True),
    Paso("Ventana del estado",
         "Al hacer clic en un estado, a la derecha del mapa aparece el porcentaje de cada color. Desde ahí "
         "entras a los expedientes de ese estado.", "b-mapa", izquierda=True),
    Paso("Filtros",
         "Busca por expediente, municipio, propietario o archivo, o filtra por entidad, motivo, estatus de la "
         "abogada o recomendación.",
         "b-filtros", ancla="expedientes"),
    Paso("Expedientes",
         "Primero salen los que tienen posibles motivos de rechazo y nadie ha revisado, luego el resto de los "
         "que requieren revisión. Abre uno para ver el dictamen, lo que hay que resolver y la evidencia de cada "
         "hallazgo.", "b-lista", ancla="expedientes"),
    Paso("Subir un expediente",
         "Sube los PDF o imágenes de un inmueble: el sistema clasifica cada documento, extrae los datos, "
         "los cruza y recomienda con su evidencia. La decisión final es de la abogada.", "nav-nuevo", lateral=True),
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
            f".st-key-{paso.objetivo} {{ position: relative; z-index: 999; border-radius: 8px; "
            f"box-shadow: 0 0 0 4px #fff, 0 0 0 9999px {_SOMBRA}; scroll-margin: 80px; }}"
        )
    centrada = paso.objetivo is None
    reglas.append(
        ".st-key-tour-card { position: fixed; z-index: 1001; width: 380px; max-width: calc(100vw - 32px); "
        f"background: #fff; border-radius: 6px; padding: 20px 22px 14px; border: 2px solid {t.TINTA_3B}; "
        "box-shadow: 0 18px 48px rgba(0,0,0,.28); "
        + ("left: 50%; top: 50%; transform: translate(-50%, -50%); }" if centrada
           else "left: 332px; bottom: 32px; }" if paso.izquierda else "right: 32px; bottom: 32px; }")
    )
    return "<style>" + " ".join(reglas) + "</style>"


# Guion fijo (constante literal: no interpolar datos en tiempo de ejecución). Lleva el objetivo del paso
# a la vista (lo lee de data-objetivo en la tarjeta), pasa el foco a "Siguiente" y cierra con Esc.
GUION = """<script>
(() => {
  const preparar = (intentos) => {
    const card = document.querySelector(".st-key-tour-card");
    if (!card) { if (intentos > 0) setTimeout(() => preparar(intentos - 1), 60); return; }
    const marca = card.querySelector("[data-objetivo]");
    const clave = marca ? marca.getAttribute("data-objetivo") : "";
    if (/^[a-z0-9-]+$/.test(clave)) {
      const objetivo = document.querySelector(".st-key-" + clave);
      if (objetivo) objetivo.scrollIntoView({block: "start"});
    }
    if (!card.contains(document.activeElement)) {
      const siguiente = card.querySelector(".st-key-tour-sig button");
      if (siguiente) siguiente.focus({preventScroll: true});
    }
  };
  preparar(10);
  if (!window.tourEsc) {
    window.tourEsc = true;
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      const salir = document.querySelector(".st-key-tour-card .st-key-tour-salir button");
      if (salir) salir.click();
    });
  }
})();
</script>"""


def tarjeta(i: int) -> str:
    p = PASOS[i]
    from html import escape
    objetivo = f' data-objetivo="{escape(p.objetivo)}"' if p.objetivo and not p.lateral else ""
    return (
        f'<div class="tour-paso"{objetivo}>Paso {i + 1} de {len(PASOS)}</div>'
        f'<h3 class="tour-titulo">{escape(p.titulo)}</h3><p class="tour-texto">{escape(p.texto)}</p>'
        + (f'<a class="tour-ir" href="#{escape(p.ancla)}">Ir a esta sección ↓</a>' if p.ancla else "")
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
    # Un contenedor por paso: así el guion se vuelve a montar (y a correr) al cambiar de paso.
    with st.container(key=f"tour-guion-{i}"):
        st.html(GUION, unsafe_allow_javascript=True)
