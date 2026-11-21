"""CSS de la app. Los valores salen de `tokens`; aquí solo hay estructura.

Dirección "Rojo 3B + blanco": la barra lateral y el marco de la app son rojo de marca; todo el
contenido va sobre blanco o gris muy claro. La tinta solo se usa como color de texto y líneas finas.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from . import tokens as t

TONOS = {"verde": t.VERDE, "ambar": t.AMBAR, "vino": t.VINO, "azul": t.AZUL, "gris": t.GRIS}


def clase_tono(tono: t.Tono) -> str:
    return next(nombre for nombre, valor in TONOS.items() if valor == tono)


def _css_tonos() -> str:
    reglas = []
    for nombre, tono in TONOS.items():
        # Sello del dictamen: blanco sobre el color fuerte del estado (6.7:1 a 8.1:1).
        reglas.append(f".sello-{nombre}{{color:#fff;background:{tono.texto};}}")
        # Estado en texto (tarjetas de la bandeja): el color fuerte del estado sobre el fondo claro.
        reglas.append(f".est-{nombre}{{color:{tono.texto};}}")
    return "".join(reglas)


GALLO = Path(__file__).resolve().parent / "assets" / "gallo.webp"


@lru_cache(maxsize=1)
def _gallo(_version: int) -> str:
    return "data:image/webp;base64," + base64.b64encode(GALLO.read_bytes()).decode("ascii")


def gallo_uri() -> str:
    """Cara del gallo 3B (botón del recorrido) como data URI; se cachea por fecha del archivo."""
    return _gallo(GALLO.stat().st_mtime_ns)


def css() -> str:
    return f"""
<style>
:root {{
  --rojo: {t.ROJO_3B}; --rojo-lat: {t.ROJO_3B_SIDEBAR}; --rojo-osc: {t.ROJO_3B_OSCURO}; --tinta: {t.TINTA_3B};
  --verde: {t.VERDE_3B}; --verde-hover: {t.VERDE_3B_HOVER};
  --panel: {t.PANEL}; --tarjeta: {t.TARJETA}; --borde: {t.BORDE}; --texto: {t.TEXTO}; --texto2: {t.TEXTO_2};
  --blanco: {t.TEXTO_SOBRE_ROJO}; --radio: {t.RADIO}px; --mapa-vacio: {t.MAPA_VACIO};
  --f-texto: {t.FUENTE_TEXTO}; --f-titular: {t.FUENTE_TITULAR}; --f-ui: {t.FUENTE_UI};
}}

/* ---- armazón: rojo de marca alrededor, panel principal claro y redondeado ---- */
.stApp, [data-testid="stAppViewContainer"] {{ background: var(--rojo-lat); }}
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp button {{ font-family: var(--f-texto); }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"],
[data-testid="stDecoration"], footer {{ display: none !important; }}
[data-testid="stExpandSidebarButton"] {{ color: var(--blanco); }}
[data-testid="stMain"] {{
  background: var(--panel); margin: 12px 12px 12px 0; border-radius: 20px;
  max-height: calc(100dvh - 24px); overflow-y: auto;
}}
[data-testid="stMainBlockContainer"] {{ max-width: 1360px; padding: 28px 36px 64px; }}
[data-testid="stSidebar"] {{ background: var(--rojo-lat); border-right: 0; color: var(--blanco); }}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding: 4px 0 24px 16px; }}
[data-testid="stSidebarCollapseButton"] button {{ color: var(--blanco); }}
/* La barra no se redimensiona; su asa dibujaba una línea en la unión con el panel. */
[data-testid="stSidebarResizeHandle"] {{ display: none !important; }}

/* margin-top negativo: el centro del logo queda a la altura del centro del título de la página. */
.lateral-marca {{ display: flex; gap: 12px; align-items: center; padding: 4px 16px 20px 4px; margin-top: -48px;
  border-bottom: 1px solid rgba(255,255,255,.35); margin-bottom: 8px; }}
.lateral-marca svg {{ width: 46px; height: 46px; flex: none; }}
.lateral-marca b {{ display: block; color: var(--blanco); font-size: 15px; line-height: 1.2; }}
.lateral-grupo {{ color: var(--blanco); font-size: 11px; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; margin: 18px 0 6px 6px; }}
[data-testid="stSidebar"] p.lateral-nota {{ color: var(--blanco); font-size: 13px; line-height: 1.5; margin: 28px 16px 0 6px;
  padding-top: 14px; border-top: 1px solid rgba(255,255,255,.35); }}

.lateral-estado {{ margin: 14px 16px 6px 6px; padding: 10px 12px; border: 1px solid rgba(255,255,255,.6);
  border-radius: 8px; color: var(--blanco); }}
.lateral-estado b {{ display: block; font-size: 14px; color: var(--blanco); }}
.lateral-estado small {{ display: block; font-size: 12px; color: var(--blanco); margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
[data-testid="stSidebar"] [class*="st-key-lat-"] {{ padding-right: 16px; }}
[data-testid="stSidebar"] [class*="st-key-lat-"] button {{ background: transparent; color: var(--blanco);
  border: 1.5px solid var(--blanco); border-radius: 8px; min-height: 44px; }}
[data-testid="stSidebar"] [class*="st-key-lat-"] button:hover {{ background: rgba(255,255,255,.14); color: var(--blanco); }}
[data-testid="stSidebar"] [class*="st-key-lat-"] button p {{ color: inherit; font-weight: 700; }}

/* navegación: botones de Streamlit con forma de pestaña blanca que se une al panel */
[data-testid="stSidebar"] [class*="st-key-nav-"] {{ width: calc(100% + 30px) !important; max-width: none !important; }}
[data-testid="stSidebar"] [class*="st-key-nav-"] button {{
  width: 100%; justify-content: flex-start; min-height: 44px; border: 0; border-radius: 22px 0 0 22px;
  background: transparent; color: var(--blanco); padding: 10px 16px; box-shadow: none;
}}
[data-testid="stSidebar"] [class*="st-key-nav-"] button > div {{ justify-content: flex-start; width: 100%; }}
[data-testid="stSidebar"] [class*="st-key-nav-"] button p {{ font-size: 15px; color: inherit; text-align: left; }}
[data-testid="stSidebar"] [class*="st-key-nav-"] button:hover {{ color: var(--blanco); background: rgba(255,255,255,.14); }}
[data-testid="stSidebar"] [class*="st-key-nav-"] [data-testid="stBaseButton-primary"],
[data-testid="stSidebar"] [class*="st-key-nav-"] [data-testid="stBaseButton-primary"]:hover {{
  background: var(--panel); color: var(--rojo-osc); font-weight: 700;
}}
[data-testid="stSidebar"] [class*="st-key-nav-"] [data-testid="stBaseButton-primary"] p {{ font-weight: 700; }}

/* foco visible: tinta sobre superficies claras, blanco sobre el rojo de la barra lateral */
.stApp a:focus-visible, .stApp button:focus-visible, .stApp summary:focus-visible, .mx-enlace:focus-visible path {{
  outline: 3px solid var(--tinta); outline-offset: 2px;
}}
[data-testid="stSidebar"] a:focus-visible, [data-testid="stSidebar"] button:focus-visible {{
  outline: 3px solid var(--blanco); outline-offset: 2px;
}}

/* acción principal: rojo de marca (versión oscura, contraste AA con texto blanco) */
.stApp [data-testid="stMain"] [data-testid="stBaseButton-primary"] {{ background: var(--rojo-osc); border-color: var(--rojo-osc); color: #fff; }}
.stApp [data-testid="stMain"] [data-testid="stBaseButton-primary"]:hover {{ background: #A51118; border-color: #A51118; color: #fff; }}

/* Verde de marca, con menos presencia que el rojo: solo la acción de analizar y los filtros activos
   de la bandeja. Texto en tinta (9:1). El verde contra el fondo da 1.7:1, por eso el segmento activo
   y el interruptor encendido llevan contorno en tinta. */
.stApp [data-testid="stMain"] .st-key-analizar button {{ background: var(--verde); border: 1px solid var(--verde); color: var(--tinta); }}
.stApp [data-testid="stMain"] .st-key-analizar button p {{ color: var(--tinta); font-weight: 700; }}
.stApp [data-testid="stMain"] .st-key-analizar button:hover {{ background: var(--verde-hover); border-color: var(--verde-hover); color: var(--tinta); }}
.stApp [data-testid="stMain"] .st-key-analizar button:disabled {{ background: {t.BORDE}; border-color: {t.BORDE}; color: var(--texto2); }}
.stApp [data-testid="stMain"] .st-key-analizar button:disabled p {{ color: var(--texto2); font-weight: 600; }}
.st-key-f_rec button[aria-checked="true"] {{ background: var(--verde) !important; color: var(--tinta) !important;
  border-color: var(--tinta) !important; }}
.st-key-f_rec button[aria-checked="true"] p {{ color: var(--tinta) !important; font-weight: 700; }}
.st-key-f_ej [data-testid="stCheckbox"][data-selected="true"] label > span + div {{
  background: var(--verde) !important; box-shadow: 0 0 0 1px var(--tinta); }}

/* cargador de archivos en español (Streamlit no deja cambiar estos textos) */
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p {{ font-size: 0; }}
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after {{ content: "Elegir archivos"; font-size: 14px; }}
[data-testid="stFileUploaderDropzoneInstructions"] span {{ font-size: 0; }}
[data-testid="stFileUploaderDropzoneInstructions"] span::after {{
  content: "PDF, PNG, JPG o TIF · hasta 50 MB por archivo"; font-size: 14px; color: var(--texto2);
}}

/* ---- tipografía del panel ---- */
.encabezado {{ display: flex; flex-wrap: wrap; align-items: end; justify-content: space-between; gap: 8px 24px; margin-bottom: 4px; }}
.encabezado h1 {{ font-family: var(--f-titular); font-size: 30px; line-height: 1.25; color: var(--tinta); margin: 0; padding: 0;
  text-decoration: underline 5px var(--rojo); text-underline-offset: 9px; text-decoration-skip-ink: none; }}
.encabezado p {{ color: var(--texto2); margin: 14px 0 0; font-size: 14px; }}
.seccion {{ font-family: var(--f-titular); font-size: 19px; color: var(--tinta); margin: 36px 0 4px; scroll-margin-top: 24px; }}
.ancla {{ scroll-margin-top: 16px; height: 0; }}
.seccion-sub {{ color: var(--texto2); font-size: 14px; margin: 0 0 14px; }}

/* ---- estados en texto de color y sello del dictamen ---- */
{_css_tonos()}

/* ---- resumen de la bandeja: una línea de texto, sin tarjetas ---- */
.resumen-bandeja {{ font-size: 14px; color: var(--texto); margin: 6px 0 0; }}

/* ---- tarjeta de expediente en la bandeja: solo la línea del marco, sobre el fondo de la página ---- */
.lista {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 28px 20px; margin-top: 22px; }}
a.exp {{ position: relative; display: block; text-decoration: none; color: var(--texto); background: transparent;
  border: 1.5px solid var(--tinta); border-radius: 4px; padding: 18px 18px 12px; }}
a.exp:hover, a.exp:focus {{ border-color: var(--rojo-osc); }}
.exp-titulo {{ position: absolute; top: 0; left: 12px; transform: translateY(-55%); background: var(--panel);
  padding: 0 8px; font-family: var(--f-titular); font-size: 15px; color: var(--tinta); text-transform: uppercase;
  max-width: calc(100% - 32px); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.exp-lugar {{ font-size: 12px; font-weight: 600; text-transform: uppercase; color: var(--texto2); letter-spacing: .03em; margin: 2px 0 8px; }}
.exp-estado {{ text-transform: none; letter-spacing: 0; font-size: 13px; font-weight: 700; }}
.exp-resumen {{ font-size: 14px; line-height: 1.45; color: var(--texto); margin: 0 0 10px;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
.exp-meta {{ font-size: 12px; color: var(--texto2); }}

/* ---- mapa: elemento principal de la bandeja, centrado y sin caja ----
   Ancho limitado por la altura de la ventana (64vh por la proporción 1000:630 del mapa). */
.mapa-bloque {{ max-width: calc(64vh * 1000 / 630); margin: 18px auto 6px; }}
.mapa-bloque h3 {{ font-size: 15px; color: var(--tinta); margin: 0; padding: 0; font-weight: 700; }}
.mapa-bloque p {{ font-size: 12px; color: var(--texto2); margin: 4px 0 6px; }}
.leyenda {{ display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 12px; color: var(--texto2); margin: 6px 0 8px; }}
.leyenda i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: -1px; margin-right: 5px; border: 1px solid rgba(0,0,0,.15); }}
svg.mx-mapa {{ width: 100%; height: auto; display: block; }}
/* Borde base fino y del mismo color en todos: los bordes compartidos se pintan dos veces sin notarse. */
.mx-estado {{ stroke: #fff; stroke-width: 1; stroke-linejoin: round; vector-effect: non-scaling-stroke; }}
.mx-enlace, .mx-llamada {{ cursor: pointer; }}
/* Los enlaces del SVG heredan el subrayado de los de Streamlit; los números no lo llevan. */
.mx-mapa a, .mx-mapa a:hover, .mx-mapa a:focus, .mx-mapa a:focus-visible, .mx-mapa text {{ text-decoration: none !important; }}
/* Hover solo oscurece el relleno: un trazo propio quedaría medio tapado por los vecinos que se pintan
   después y se vería más grueso donde el estado tiene menos vecinos. */
.mx-enlace:hover .mx-estado {{ filter: brightness(.88); }}
/* La selección es un solo contorno encima de todo (se dibuja al final), igual en cualquier estado. */
.mx-borde-sel {{ fill: none; stroke: var(--tinta); stroke-width: 2; stroke-linejoin: round; vector-effect: non-scaling-stroke;
  pointer-events: none; }}
/* Números en unidades del mapa (1000 de ancho): con el mapa de 810 a 920 px quedan en 14 a 16 px. */
.mx-num {{ font: 700 17px var(--f-texto); fill: var(--tinta); pointer-events: none; }}
.mx-num-halo {{ stroke: #fff; stroke-width: 4px; paint-order: stroke; stroke-linejoin: round; }}
.mx-llamada circle {{ stroke: var(--tinta); stroke-width: 1.5; vector-effect: non-scaling-stroke; }}
.mx-llamada:hover circle {{ stroke-width: 2.5; }}
.mx-guia {{ stroke: var(--tinta); stroke-width: 1.2; vector-effect: non-scaling-stroke; pointer-events: none; }}
.sin-entidad {{ font-size: 12px; color: var(--texto2); margin-top: 4px; }}

/* ---- marco: tarjeta con línea fina y título que interrumpe la línea ----
   Base (documentos): blanca con línea y título en tinta. Dictamen: sobre el fondo de la página, solo
   el borde y el título en rojo; el texto en tinta. */
.marco {{ position: relative; background: var(--tarjeta); color: var(--texto); border-radius: 6px;
  padding: 58px 40px 36px; margin: 34px 0 10px; border: 1px solid var(--borde); }}
.marco::before {{ content: ""; position: absolute; inset: 28px 14px 14px; border: 1.5px solid var(--tinta); pointer-events: none; }}
.marco-titulo {{ position: absolute; top: 28px; left: 30px; transform: translateY(-50%); background: var(--tarjeta);
  padding: 0 14px; margin: 0; font-family: var(--f-titular); font-size: 34px; line-height: 1; color: var(--tinta);
  text-transform: uppercase; letter-spacing: -.01em; max-width: calc(100% - 60px);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.marco-cuerpo {{ display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: 28px; align-items: center; }}
.marco-ceja {{ font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--texto2); margin: 0 0 10px; }}
.marco-titular {{ font-family: var(--f-titular); font-size: 44px; line-height: 1.05; margin: 0 0 14px; }}
.nobr {{ white-space: nowrap; }}
.sello {{ display: inline-block; padding: .06em .28em .1em; border-radius: 2px; }}
.marco-texto p.marco-resumen {{ color: var(--texto); font-size: 16px; line-height: 1.55; margin: 0 0 14px; max-width: 62ch; }}
.marco-datos {{ display: flex; flex-wrap: wrap; gap: 6px 22px; font-size: 13px; color: var(--texto2); margin: 0 0 20px; }}
.marco-datos b {{ color: var(--tinta); }}
.marco-botones {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
.marco-botones a, .marco-botones span {{ display: inline-flex; align-items: center; min-height: 44px; padding: 0 20px; font-weight: 700;
  font-size: 14px; text-transform: uppercase; text-decoration: none; border-radius: 2px; }}
.btn-acento {{ background: var(--rojo-osc); color: #fff !important; }}
.btn-acento:hover {{ background: #A51118; }}
.btn-linea {{ background: var(--tarjeta); color: var(--tinta) !important; border: 1.5px solid var(--tinta); }}
.btn-linea:hover {{ border-color: var(--rojo-osc); color: var(--rojo-osc) !important; }}
.marco-botones span.btn-nada {{ color: var(--texto2); text-transform: none; font-weight: 600; padding: 0 4px; }}
.marco-media {{ align-self: stretch; display: flex; flex-direction: column; justify-content: center; align-items: center;
  background: var(--panel); border-radius: 2px; padding: 12px; min-height: 220px; }}
.marco-media svg {{ width: 100%; max-height: 300px; }}
.marco-media figcaption {{ font-size: 13px; color: var(--tinta); font-weight: 600; margin-top: 8px; text-align: center; }}
.mx-vecino {{ fill: var(--mapa-vacio); stroke: #fff; stroke-width: 1; vector-effect: non-scaling-stroke; }}
.mx-resaltado {{ stroke: var(--tinta); stroke-width: 2; stroke-linejoin: round; vector-effect: non-scaling-stroke; }}

/* dictamen: como el marco de Subir expediente. Fondo de la página, línea de 2 px en rojo 3B con el
   radio de la app y el título rojo sobre la línea (con un parche del fondo detrás). El sello es el color
   del estado con texto blanco; botón principal rojo, secundario blanco con línea de 2 px en tinta. */
.marco-dictamen {{ background: var(--panel); border: 2px solid var(--rojo-osc); border-radius: var(--radio);
  padding: 44px 36px 32px; }}
.marco-dictamen::before {{ display: none; }}
.marco-dictamen .marco-titulo {{ top: 0; left: 22px; background: var(--panel); color: var(--rojo-osc); }}
.marco-dictamen .btn-linea {{ background: #fff; border-width: 2px; }}
.marco-dictamen .marco-botones a {{ border-radius: var(--radio); }}
.marco-dictamen .marco-media {{ background: transparent; }}

/* ---- Detalle: dictamen, qué resolver, documentos y detalle completo ----
   Sin etiquetas tipo píldora. Las cajas usan la línea de Subir expediente: 2 px tinta y radio de 6 px. */
.sr {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }}
.resolver {{ margin: 8px 0 0; padding-left: 28px; }}
.resolver li {{ padding: 12px 0; border-bottom: 1px solid var(--borde); }}
.resolver li::marker {{ font-weight: 700; color: var(--tinta); }}
.resolver-texto {{ font-size: 15px; line-height: 1.45; color: var(--texto); margin: 0 0 4px; }}
.resolver-meta {{ font-size: 13px; color: var(--texto2); margin: 0; overflow-wrap: anywhere; }}
.resolver-vacio {{ font-size: 15px; color: var(--texto); margin: 8px 0 0; }}
.resolver-notas {{ margin-top: 18px; }}
.stApp .resolver-notas h3 {{ font-family: var(--f-texto); font-size: 14px; font-weight: 700; color: var(--tinta);
  margin: 0 0 4px; padding: 0; }}
.resolver-notas ul {{ margin: 0; padding-left: 20px; }}
.resolver-notas li {{ font-size: 14px; line-height: 1.5; color: var(--texto); }}
details.ev summary {{ cursor: pointer; width: fit-content; margin-top: 6px; font-size: 13px; color: var(--tinta);
  text-decoration: underline; text-underline-offset: 3px; }}
details.ev summary:hover {{ color: var(--rojo-osc); }}
details.ev[open] {{ padding-bottom: 4px; }}
details.ev p {{ font-size: 14px; line-height: 1.5; margin: 6px 0; }}
details.ev-celda summary {{ font-size: 12px; color: var(--texto2); margin-top: 2px; }}
.ev-regla {{ font-weight: 600; color: var(--tinta); }}

.docs-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 30px 20px; margin-top: 24px; }}
.doc-tarjeta {{ position: relative; border: 2px solid var(--tinta); border-radius: var(--radio); padding: 24px 18px 14px; min-width: 0; }}
.doc-falta {{ border-style: dashed; }}
.doc-titulo {{ position: absolute; top: 0; left: 12px; transform: translateY(-55%); background: var(--panel);
  padding: 0 8px; font-family: var(--f-titular); font-weight: 900; font-size: 15px; line-height: 1.1; color: var(--tinta);
  text-transform: uppercase; max-width: calc(100% - 32px); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.doc-archivo {{ font-size: 13px; color: var(--texto2); margin: 0 0 4px; overflow-wrap: anywhere; }}
a.doc-ver {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; color: var(--tinta); font-weight: 600;
  text-decoration: underline; text-underline-offset: 3px; }}
a.doc-ver:hover {{ color: var(--rojo-osc); }}
.doc-ver-txt {{ font-size: 12px; font-weight: 700; color: var(--rojo-osc); text-decoration: none; }}
.st-key-doc-paginas [data-testid="stImage"] {{ max-width: 880px; margin: 0 auto 18px; }}
.st-key-doc-paginas img {{ border: 2px solid var(--tinta); border-radius: 6px; background: #fff; }}
.doc-estado {{ font-size: 14px; color: var(--texto); margin: 0 0 10px; overflow-wrap: anywhere; }}
.doc-campos {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; margin: 0 0 10px; }}
.doc-campos dt {{ color: var(--texto2); }}
.doc-campos dd {{ margin: 0; color: var(--texto); overflow-wrap: anywhere; }}
.doc-reglas {{ font-size: 13px; color: var(--texto2); margin: 0; border-top: 1px solid var(--borde); padding-top: 8px; }}

/* tablas con reglas de 1 px, sin caja alrededor */
.tabla-scroll {{ overflow-x: auto; }}
table.tabla {{ width: 100%; border-collapse: collapse; font-size: 13px; margin: 6px 0 4px; }}
.stApp table.tabla {{ border: 0; }}
.stApp table.tabla th {{ text-align: left; font-size: 12px; color: var(--texto2); font-weight: 600; padding: 8px 10px;
  border: 0; border-bottom: 1px solid var(--tinta); vertical-align: bottom; background: transparent; }}
.stApp table.tabla td {{ padding: 8px 10px; border: 0; border-bottom: 1px solid var(--borde); vertical-align: top; }}
.tabla td.campo {{ font-weight: 600; color: var(--tinta); min-width: 140px; }}
.tabla .vacio {{ color: var(--texto2); }}
q.cita, .cita {{ display: block; quotes: "\\201C" "\\201D"; font-style: italic; color: var(--texto); background: #F3F5F0;
  border-left: 3px solid var(--borde); padding: 6px 10px; margin: 4px 0; font-size: 13px; line-height: 1.45; overflow-wrap: anywhere; }}
.fuente {{ font-size: 12px; color: var(--texto2); }}
.stApp h3.dc-titulo {{ font-family: var(--f-texto); font-size: 15px; font-weight: 700; color: var(--tinta); margin: 20px 0 6px; padding: 0; }}
.stApp h3.dc-titulo:first-child {{ margin-top: 4px; }}
.dc-nota {{ font-size: 13px; color: var(--texto2); margin: 0 0 4px; }}
.st-key-detalle-completo {{ margin-top: 30px; }}
.st-key-detalle-completo [data-testid="stExpander"] > details {{ border: 2px solid var(--tinta); border-radius: var(--radio); }}
.st-key-detalle-completo [data-testid="stExpander"] > details > summary p {{ font-weight: 700; color: var(--tinta); }}
.st-key-detalle-descargar button {{ padding: 0; min-height: 0; margin-top: 18px; }}
.st-key-detalle-descargar button p {{ font-size: 14px; color: var(--tinta); text-decoration: underline; text-underline-offset: 3px; }}
.st-key-detalle-descargar button:hover p {{ color: var(--rojo-osc); }}

/* ---- Subir expediente (vista "nuevo"): todo lo de esta vista va en este bloque ----
   Todas las líneas de la vista son de 2 px en tinta con radio de 6 px (RADIO): marco, campos y botones. */
.st-key-subir {{ max-width: 1100px; }}
.st-key-subir-marco {{ position: relative; border: 2px solid var(--tinta); border-radius: var(--radio);
  padding: 30px 22px 20px; margin-top: 52px; overflow: visible; }}
.st-key-subir-marco::before {{ content: "Expediente"; position: absolute; top: 0; left: 14px; transform: translateY(-55%);
  background: var(--panel); padding: 0 10px; font-family: var(--f-titular); font-weight: 900; font-size: 18px;
  line-height: 1; color: var(--tinta); text-transform: uppercase; }}
.st-key-subir-nombre [data-testid="stWidgetLabel"] p, .st-key-subir-archivos [data-testid="stWidgetLabel"] p {{
  font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; color: var(--tinta); }}
.st-key-subir-nombre [data-testid="stTextInputRootElement"] {{ height: 48px; border: 2px solid var(--tinta);
  border-radius: var(--radio); background: #fff; }}
.st-key-subir-nombre [data-testid="stTextInputRootElement"]:focus-within {{ border-color: var(--rojo-osc);
  box-shadow: 0 0 0 2px var(--rojo-osc); }}
.st-key-subir-nombre input::placeholder {{ color: var(--texto2); opacity: 1; }}
/* Streamlit muestra "Press Enter to submit form" en inglés y encima del texto de ejemplo. */
.st-key-subir-nombre [data-testid="InputInstructions"] {{ display: none; }}
.st-key-subir-archivos [data-testid="stFileUploaderDropzone"] {{ border: 2px dashed var(--tinta); border-radius: var(--radio);
  background: #fff; min-height: 180px; padding: 24px; display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 12px; text-align: center; }}
.st-key-subir-archivos [data-testid="stFileUploaderDropzone"]:focus-within {{ border-color: var(--rojo-osc); }}
.st-key-subir-archivos [data-testid="stFileUploaderDropzone"]::before {{
  content: "Arrastra aquí los archivos del expediente"; font-size: 16px; font-weight: 600; color: var(--tinta); }}
.st-key-subir-archivos [data-testid="stFileUploaderDropzone"] button {{ border-radius: var(--radio); }}
/* Al arrastrar archivos encima, Streamlit agrega un div sin data-testid con un aviso en inglés: borde rojo
   y el aviso en español. La lista de archivos elegidos también es un div sin data-testid, pero contiene
   stFileChips; por eso se excluye. El borde se detecta por el aviso seguido del botón, porque :has() no
   admite otro :has() adentro. */
.st-key-subir-archivos [data-testid="stFileUploaderDropzone"]:has(> div:not([data-testid]) + span):not(:has([data-testid="stFileChips"])) {{
  border-color: var(--rojo-osc); }}
.st-key-subir-archivos [data-testid="stFileUploaderDropzone"] > div:not([data-testid]):not(:has([data-testid="stFileChips"])),
.st-key-subir-archivos [data-testid="stFileUploaderDropzone"] > div:not([data-testid]):not(:has([data-testid="stFileChips"])) * {{ font-size: 0 !important; }}
.st-key-subir-archivos [data-testid="stFileUploaderDropzone"] > div:not([data-testid]):not(:has([data-testid="stFileChips"]))::after {{
  content: "Suelta los archivos para agregarlos"; font-size: 16px; font-weight: 600; color: var(--rojo-osc); }}
.stApp [data-testid="stMain"] .st-key-subir .st-key-analizar button {{ border-radius: var(--radio); }}
/* La columna derecha arranca a la altura de la línea superior del marco. */
.subir-esperados {{ margin-top: 52px; }}
.stApp .subir-esperados h3 {{ font-family: var(--f-texto); font-size: 16px; font-weight: 700; color: var(--tinta);
  margin: 0 0 4px; padding: 0; line-height: 1.2; }}
.subir-esperados dl {{ margin: 0 0 16px; }}
.subir-esperados dt {{ font-size: 14px; font-weight: 700; color: var(--tinta); margin-top: 12px; }}
.subir-esperados dd {{ font-size: 14px; line-height: 1.45; color: var(--texto2); margin: 2px 0 0; }}
.subir-esperados p {{ font-size: 14px; color: var(--texto); border-top: 1px solid var(--borde); padding-top: 12px; margin: 0; }}
.st-key-subir-ejemplo {{ margin-top: 28px; }}
.subir-ejemplo-texto {{ font-size: 14px; color: var(--texto2); }}
.st-key-subir-abrir-ejemplo button {{ padding: 0; min-height: 0; }}
.st-key-subir-abrir-ejemplo button p {{ font-size: 14px; color: var(--tinta); text-decoration: underline;
  text-underline-offset: 3px; }}
.st-key-subir-abrir-ejemplo button:hover p {{ color: var(--rojo-osc); }}

/* ---- Pie: paisaje 3B fundido con el panel ----
   Ocupa todo el ancho del panel y llega a su borde inferior: los márgenes negativos cancelan el relleno
   lateral e inferior del contenedor, y el recorte redondeado del panel le da las esquinas. El cielo del
   archivo ya viene recoloreado al color exacto del panel (ver paisaje.webp), así que no hace falta
   degradado ni mezcla: la imagen se ve completa, sin recorte. */
.paisaje {{ margin: 56px -36px -64px; line-height: 0; pointer-events: none; user-select: none; }}
/* En vistas cortas el contenido no llena el panel: el contenedor ocupa toda la altura y el paisaje se
   va al fondo con margin-top: auto. */
[data-testid="stMainBlockContainer"]:has(.paisaje) {{ min-height: 100%; display: flex; flex-direction: column; }}
[data-testid="stMainBlockContainer"]:has(.paisaje) > [data-testid="stVerticalBlock"] {{ flex: 1 0 auto; }}
[data-testid="stElementContainer"]:has(> .paisaje), [data-testid="stElementContainer"]:has(.paisaje) {{ margin-top: auto; }}
.paisaje img {{ display: block; width: 100%; height: auto; }}

/* ---- Botón flotante del recorrido: cara del gallo 3B y globo "Cómo se usa" ----
   Fijo abajo a la derecha en todas las vistas, por debajo de las tarjetas del recorrido (que lo ocultan
   mientras corre) y de los diálogos de Streamlit. Sin brillo ni animación en bucle. */
.st-key-tour-fab-caja {{ position: fixed; right: 24px; bottom: 24px; z-index: 900; width: auto !important;
  max-width: none !important; }}
.st-key-tour-fab button {{ position: relative; width: 64px; height: 64px; min-height: 64px; padding: 0;
  border-radius: 50%; border: 3px solid var(--rojo-osc);
  background: #fff url("{gallo_uri()}") center / cover no-repeat; box-shadow: none; transition: transform .15s ease; }}
.st-key-tour-fab button p {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0);
  white-space: nowrap; }}
.st-key-tour-fab button::after {{ content: "?"; position: absolute; top: -6px; right: -6px; width: 22px; height: 22px;
  border-radius: 50%; background: var(--rojo-osc); color: #fff; font: 700 14px/22px var(--f-texto); text-align: center; }}
.st-key-tour-fab button:hover {{ border-color: #A51118; transform: translateY(-2px); background-color: #fff; }}
.st-key-tour-fab-etiqueta button {{ position: relative; min-height: 0; padding: 8px 12px; background: #fff;
  border: 2px solid var(--tinta); border-radius: var(--radio); box-shadow: none; transition: transform .15s ease; }}
.st-key-tour-fab-etiqueta button p {{ font-size: 14px; font-weight: 700; color: var(--tinta); white-space: nowrap; }}
.st-key-tour-fab-etiqueta button::after {{ content: ""; position: absolute; right: -7px; top: 50%; width: 10px; height: 10px;
  background: #fff; border-top: 2px solid var(--tinta); border-right: 2px solid var(--tinta);
  transform: translateY(-50%) rotate(45deg); }}
.st-key-tour-fab-etiqueta button:hover {{ transform: translateY(-2px); background: #fff; border-color: var(--rojo-osc); }}
.st-key-tour-fab-etiqueta button:hover p {{ color: var(--rojo-osc); }}
@keyframes globo-fuera {{ to {{ opacity: 0; visibility: hidden; }} }}
.st-key-tour-globo-guion, [class*="st-key-tour-guion-"] {{ display: none; }}
.st-key-tour-fab button:focus-visible, .st-key-tour-fab-etiqueta button:focus-visible {{
  outline: 3px solid var(--tinta); outline-offset: 3px; }}
@media (prefers-reduced-motion: reduce) {{
  .st-key-tour-fab button, .st-key-tour-fab-etiqueta button {{ transition: none; }}
  .st-key-tour-fab button:hover, .st-key-tour-fab-etiqueta button:hover {{ transform: none; }}
}}
/* Los avisos de Streamlit salen abajo a la derecha: se suben para que el botón no los tape. */
[data-testid="stToastContainer"] {{ bottom: 112px !important; }}

/* Streamlit da estilo propio a h1-h3 y p dentro de Markdown; estas reglas ganan por especificidad. */
.stApp .marco .marco-titulo, .stApp .encabezado h1, .stApp h2.seccion {{ font-family: var(--f-titular); font-weight: 900; }}
.stApp .marco .marco-titulo {{ font-size: 34px; line-height: 1; padding: 0 14px; margin: 0; }}
.stApp .docs .marco .marco-titulo {{ font-size: 21px; padding: 0 10px; }}
.stApp .marco p.marco-titular {{ font-family: var(--f-titular); font-size: 44px; line-height: 1.05; font-weight: 900; margin: 0 0 14px; }}
.stApp h2.seccion {{ font-size: 21px; padding: 0; margin: 40px 0 4px; letter-spacing: 0; }}
.stApp .doc-campos dt, .stApp .doc-campos dd {{ font-size: 14px; line-height: 1.4; }}
.stApp .inc h3, .stApp .razones h3, .stApp .mapa-bloque h3 {{ font-family: var(--f-texto); font-weight: 700; }}

/* ==== Inicio (Diego) con el estilo de Subir expediente (Yordi) ====
   Mismo lenguaje que esa vista: líneas de 2 px en tinta con esquinas de 6 px, títulos gruesos en
   mayúsculas que interrumpen la línea del marco, etiquetas en mayúsculas y acción principal verde. */
[data-testid="stSidebar"] [class*="st-key-nav-"] [data-testid="stIconMaterial"] {{ font-size: 20px; }}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] {{ gap: 6px; }}
/* La tarjeta del usuario va siempre hasta abajo del menú lateral. */
[data-testid="stSidebarContent"] {{ display: flex; flex-direction: column; }}
[data-testid="stSidebarUserContent"] {{ flex: 1 0 auto; display: flex; flex-direction: column; }}
[data-testid="stSidebarUserContent"] > div {{ flex: 1 0 auto; display: flex; flex-direction: column; }}
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {{ flex: 1 0 auto; }}
[data-testid="stSidebarUserContent"] [data-testid="stElementContainer"]:has(.lateral-usuario) {{ margin-top: auto; }}
[data-testid="stSidebar"] .lateral-grupo {{ margin: 20px 0 10px 6px; }}
.lateral-marca .lateral-sub {{ display: block; color: var(--blanco); font-size: 12px; margin-top: 2px; }}
.lateral-usuario {{ display: flex; gap: 12px; align-items: center; margin: 22px 16px 0 4px; padding-top: 16px;
  border-top: 1px solid rgba(255,255,255,.35); color: var(--blanco); }}
.lat-avatar {{ flex: none; width: 38px; height: 38px; border-radius: 50%; background: var(--blanco); color: var(--rojo-osc);
  display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; }}
.lateral-usuario b {{ display: block; font-size: 14px; color: var(--blanco); }}
.lateral-usuario small {{ display: block; font-size: 12px; color: var(--blanco); }}

/* El inicio usa todo el ancho del panel. */
[data-testid="stMainBlockContainer"]:has(.st-key-b-kpis) {{ max-width: none; }}
.st-key-b-cabecera {{ margin-bottom: 26px; }}
.st-key-b-cabecera [data-testid="stTextInputRootElement"] {{ height: 46px; border: 2px solid var(--tinta); border-radius: 6px; background: #fff; }}
.st-key-b-cabecera [data-testid="stTextInputRootElement"]:focus-within {{ border-color: var(--rojo-osc); box-shadow: 0 0 0 2px var(--rojo-osc); }}
.st-key-b-cabecera input::placeholder {{ color: var(--texto2); opacity: 1; }}

/* Título que interrumpe la línea del marco, igual que EXPEDIENTE en Subir expediente. */
.st-key-b-filtros::before, .mapa-tarjeta .mapa-cab h3, .stApp .mapa-tarjeta .mapa-cab h3 {{
  position: absolute; top: 0; left: 14px; transform: translateY(-55%); background: var(--panel); padding: 0 10px; margin: 0;
  font-family: var(--f-titular); font-weight: 900; font-size: 18px; line-height: 1; color: var(--tinta); text-transform: uppercase; }}

.kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px; margin: 0 0 34px; }}
.kpis.kpis-5 {{ grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 14px; }}
a.kpi {{ display: block; background: transparent; border: 2px solid var(--tinta); border-radius: 6px; padding: 16px 18px 14px;
  text-decoration: none; color: var(--texto); }}
a.kpi:hover, a.kpi:focus-visible {{ border-color: var(--rojo-osc); }}
a.kpi.kpi-total {{ border-color: var(--rojo-osc); }}
.kpi-etq {{ display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .03em; color: var(--tinta); }}
.kpi-punto {{ display: inline-block; width: 11px; height: 11px; border-radius: 2px; border: 1px solid rgba(0,0,0,.2); }}
.kpi-num {{ display: block; font-family: var(--f-titular); font-weight: 900; font-size: 38px; line-height: 1.1; margin: 10px 0 4px; color: var(--tinta); }}
.kpi-sub {{ display: block; font-size: 13px; color: var(--texto2); }}

.mapa-tarjeta {{ position: relative; background: transparent; border: 2px solid var(--tinta); border-radius: 6px;
  padding: 26px 22px 16px; margin: 0 0 34px; }}
.mapa-cab {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 8px 24px; }}
.mapa-cab p {{ font-size: 13px; color: var(--texto2); margin: 0; max-width: 60ch; }}
.mapa-cab .leyenda {{ margin: 0; }}
.mapa-cuerpo {{ display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 24px; align-items: center; margin-top: 10px; }}
.mapa-lienzo {{ position: relative; max-width: calc(62vh * 1000 / 630); width: 100%; margin: 0 auto; }}
.mapa-panel {{ align-self: center; }}
.mx-abr {{ font: 700 11px var(--f-texto); fill: var(--texto2); letter-spacing: .05em; pointer-events: none; }}

.mx-ventana {{ background: #fff; border: 2px solid var(--tinta); border-radius: 6px; padding: 14px 16px 14px; }}
.mx-ventana.v-vacia {{ background: transparent; border-style: dashed; }}
.v-cab {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
.v-cab b {{ font-family: var(--f-titular); font-weight: 900; font-size: 16px; text-transform: uppercase; color: var(--tinta); }}
.mx-ventana a.v-cerrar {{ text-decoration: none; color: var(--tinta); font-size: 22px; line-height: 1; padding: 0 4px; }}
.mx-ventana a.v-cerrar:hover {{ color: var(--rojo-osc); }}
.mx-ventana p.v-total {{ font-size: 13px; color: var(--texto2); margin: 4px 0 10px; }}
.v-fila {{ display: grid; grid-template-columns: 1fr auto 26px; align-items: center; gap: 8px; font-size: 14px; margin-top: 8px; }}
.v-etq i {{ display: inline-block; width: 11px; height: 11px; border-radius: 2px; margin-right: 7px; vertical-align: -1px; }}
.v-fila b {{ font-size: 14px; }}
.v-fila small {{ color: var(--texto2); text-align: right; font-size: 12px; }}
.v-barra {{ height: 6px; background: var(--panel); border-radius: 2px; overflow: hidden; margin: 5px 0 0; }}
.v-barra i {{ display: block; height: 100%; }}
.mx-ventana a.v-ver {{ display: block; margin-top: 14px; text-align: center; font-size: 14px; font-weight: 700; color: var(--tinta);
  background: var(--verde); border: 1px solid var(--verde); border-radius: 6px; padding: 9px 8px; text-decoration: none; }}
.mx-ventana a.v-ver:hover {{ background: var(--verde-hover); border-color: var(--verde-hover); }}

.st-key-b-filtros {{ position: relative; border: 2px solid var(--tinta); border-radius: 6px; padding: 26px 20px 16px;
  margin-bottom: 10px; overflow: visible; }}
.st-key-b-filtros::before {{ content: "Filtros"; }}
.st-key-b-filtros [data-testid="stWidgetLabel"] p {{ font-size: 12px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .03em; color: var(--tinta); }}
.st-key-b-filtros [data-baseweb="select"] > div {{ border: 2px solid var(--tinta); border-radius: 6px; background: #fff; }}
.st-key-b-filtros [data-testid="stButtonGroup"] button {{ border-color: var(--tinta); }}
.stApp h2.lista-titulo {{ font-family: var(--f-titular); font-weight: 900; font-size: 21px; color: var(--tinta); margin: 30px 0 0; padding: 0; }}
h2.lista-titulo small {{ font-family: var(--f-texto); font-size: 13px; font-weight: 700; color: var(--tinta);
  border: 2px solid var(--tinta); border-radius: 6px; padding: 0 8px; margin-left: 8px; vertical-align: 3px; }}

.tour-paso {{ font-size: 12px; font-weight: 700; color: var(--rojo-osc); text-transform: uppercase; letter-spacing: .06em; }}
.stApp h3.tour-titulo {{ font-family: var(--f-titular); font-weight: 900; font-size: 18px; text-transform: uppercase;
  color: var(--tinta); margin: 6px 0 8px; padding: 0; line-height: 1.2; }}
.tour-texto {{ font-size: 15px; line-height: 1.5; color: var(--texto); margin: 0 0 6px; }}
.tour-ir {{ display: inline-block; font-size: 14px; font-weight: 700; color: var(--rojo-osc); text-decoration: none; margin: 0 0 8px; }}

/* Vista de un estado: indicadores 2 x 2 a la izquierda y su ubicación a la derecha. */
.estado-resumen {{ display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr); gap: 24px; align-items: stretch;
  margin: 26px 0 10px; }}
.estado-kpis .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; height: 100%; }}
a.kpi.kpi-activo {{ border-color: var(--rojo-osc); box-shadow: inset 0 0 0 2px var(--rojo-osc); }}
.estado-mapa {{ position: relative; margin: 0; border: 2px solid var(--tinta); border-radius: 6px; padding: 26px 16px 14px;
  display: flex; align-items: center; justify-content: center; }}
.estado-mapa figcaption {{ position: absolute; top: 0; left: 14px; transform: translateY(-55%); background: var(--panel);
  padding: 0 10px; font-family: var(--f-titular); font-weight: 900; font-size: 18px; line-height: 1; color: var(--tinta);
  text-transform: uppercase; }}
.estado-mapa svg {{ width: 100%; max-height: 300px; }}
.st-key-estado-volver button {{ border: 2px solid var(--tinta); border-radius: 6px; }}

/* Tabla de expedientes (repositorio): encabezado con nombre de columna y una fila por expediente. */
.t-tabla {{ margin-top: 14px; border: 2px solid var(--tinta); border-radius: 6px; overflow: hidden; background: #fff; }}
.t-cab, .t-fila {{ display: grid; align-items: center; gap: 12px; padding: 0 16px;
  grid-template-columns: 1.3fr 1.6fr 1.6fr 1fr .75fr 1.05fr .7fr 1fr; }}
.t-cab {{ background: var(--panel); color: var(--tinta); border-bottom: 2px solid var(--tinta); font-size: 12px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .04em; min-height: 40px; }}
.t-fila {{ min-height: 48px; font-size: 14px; color: var(--texto); text-decoration: none; border-top: 1px solid var(--borde); }}
.t-fila:nth-child(odd) {{ background: #FAFBF8; }}
.t-fila:hover, .t-fila:focus {{ background: #FDECEC; color: var(--texto); text-decoration: none; }}
.t-celda {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 8px 0; }}
/* Fila: el enlace del identificador se estira sobre la fila (abre el detalle); el del motivo va encima. */
.t-fila {{ position: relative; }}
a.t-abrir {{ color: var(--tinta); text-decoration: none; }}
a.t-abrir::after {{ content: ""; position: absolute; inset: 0; }}
.t-fila:has(a.t-abrir:focus-visible) {{ outline: 3px solid var(--tinta); outline-offset: -3px; }}
a.t-abrir:focus-visible {{ outline: none; }}
.t-rec {{ display: block; }}
.t-motivo-linea {{ display: block; font-size: 12px; line-height: 1.35; white-space: normal; margin-top: 2px; }}
a.t-motivo {{ position: relative; z-index: 1; font-weight: 600; text-decoration: none; }}
a.t-motivo:hover, a.t-motivo:focus-visible {{ text-decoration: underline; text-underline-offset: 2px; }}
a.t-motivo:focus-visible {{ outline: 3px solid var(--tinta); outline-offset: 1px; }}
.t-tambien {{ color: var(--texto2); }}
/* Lista desplegable de los selectbox: tan ancha como su opción más larga (las del filtro Motivo llevan
   conteos), sin pasar de 480px; nunca más angosta que el campo. */
[data-testid="stSelectboxVirtualDropdown"] {{ width: max-content !important; min-width: 200px; max-width: 480px; }}
.filtro-activo {{ font-size: 14px; color: var(--texto); margin: 8px 0 0; }}
.filtro-activo a {{ color: var(--tinta); text-decoration: underline; }}
.motivos-resumen {{ font-size: 14px; color: var(--texto); margin: 4px 0; }}
/* Posibles motivos de rechazo: primer bloque de "Qué hay que resolver", con la cita a la vista. */
.posibles-rechazo {{ border-left: 4px solid var(--rojo-osc); padding: 2px 0 2px 16px; margin: 14px 0 22px; }}
.stApp .posibles-rechazo h3, .stApp h3.otros-pendientes {{ font-family: var(--f-texto); font-size: 16px; font-weight: 700;
  color: var(--tinta); margin: 0; padding: 0; }}
.posibles-nota {{ font-size: 13px; color: var(--texto2); margin: 2px 0 4px; }}
.stApp h3.otros-pendientes {{ margin-top: 8px; }}
.resolver-citas {{ list-style: none; padding: 0; margin: 4px 0 6px; font-size: 13px; }}
.resolver-citas li {{ margin: 2px 0; }}
.resolver-citas .fuente {{ margin-left: 6px; }}
.dec-nota {{ font-size: 14px; color: var(--texto); margin: 8px 0 2px; }}
.dec-sugerencia {{ font-size: 13px; color: var(--texto2); margin: 0 0 6px; }}
.t-id {{ font-weight: 700; color: var(--tinta); }}
.t-ej {{ font-size: 11px; font-weight: 600; color: var(--texto2); border: 1px solid var(--borde); border-radius: 4px; padding: 0 4px; margin-left: 4px; }}
.t-rec {{ font-weight: 700; }}
.t-rec i {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 7px; }}
.t-fecha {{ color: var(--texto2); font-size: 13px; }}
.insignia {{ display: inline-block; font-size: 12px; font-weight: 700; border-radius: 999px; padding: 2px 10px; }}
.paginador {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;
  font-size: 13px; color: var(--texto2); margin: 12px 0 0; }}
.pag-nav {{ display: flex; align-items: center; gap: 10px; }}
.pag-btn {{ border: 2px solid var(--tinta); border-radius: 6px; padding: 4px 12px; font-weight: 700; color: var(--tinta);
  text-decoration: none; background: #fff; }}
a.pag-btn:hover {{ background: var(--verde); border-color: var(--verde); color: var(--tinta); text-decoration: none; }}
.pag-btn.pag-off {{ opacity: .35; }}
.st-key-estado-filtros {{ margin-top: 18px; }}

/* Decisión de la abogada en el detalle. */
.decision-actual {{ border: 2px solid var(--tinta); border-left-width: 8px; border-radius: 6px; background: #fff;
  padding: 14px 18px; margin: 10px 0 14px; }}
.decision-actual .insignia {{ font-size: 14px; padding: 3px 14px; }}
.dec-com {{ font-size: 15px; line-height: 1.45; color: var(--texto); margin: 10px 0 4px; white-space: normal; }}
.dec-meta {{ font-size: 12px; color: var(--texto2); margin: 0; }}
.dec-historial {{ list-style: none; padding: 0; margin: 0; }}
.dec-historial li {{ border-top: 1px solid var(--borde); padding: 10px 0; }}
.dec-historial li:first-child {{ border-top: 0; }}

@media (max-width: 1100px) {{
  .estado-resumen {{ grid-template-columns: 1fr; }}
  .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .mapa-cuerpo {{ grid-template-columns: 1fr; }}
  .t-cab, .t-fila {{ grid-template-columns: 1.3fr 1.5fr 1.6fr 1fr .9fr; }}
  .t-cab .t-celda:nth-child(n+6), .t-fila .t-celda:nth-child(n+6) {{ display: none; }}
}}

/* escritorio angosto (1280): más aire para el texto del dictamen */
@media (max-width: 1400px) {{
  .marco-cuerpo {{ grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr); }}
  .marco-botones a {{ padding: 0 16px; }}
}}

@media (max-width: 900px) {{
  .stApp .marco .marco-titulo {{ font-size: 26px; }}
  .stApp .marco p.marco-titular {{ font-size: 34px; }}
  .marco-cuerpo {{ grid-template-columns: 1fr; }}
  .marco {{ padding: 54px 24px 28px; }}
  .marco-titulo {{ font-size: 26px; }}
  .marco-titular {{ font-size: 34px; }}
  [data-testid="stMainBlockContainer"] {{ padding: 56px 16px 48px; }}
  [data-testid="stMain"] {{ margin: 0; border-radius: 0; max-height: none; }}
}}

/* ---- Movimiento: poco, corto y con propósito. Solo opacidad y desplazamiento (translate), ease-out,
   150 a 200 ms, sin repeticiones. La entrada de cada vista va en sus contenedores de arriba, que siguen
   montados entre reruns: escribir en el buscador no la repite. La tabla y los filtros no se animan. */
@keyframes vista-entra {{ from {{ opacity: 0; translate: 0 4px; }} }}
@keyframes tarjeta-entra {{ from {{ opacity: 0; translate: 0 6px; }} }}
@keyframes aparece {{ from {{ opacity: 0; }} }}
.st-key-b-cabecera, .st-key-b-kpis, .st-key-b-mapa, .st-key-subir-marco, .st-key-estado-resumen,
.marco-dictamen, .docs-grid {{ animation: vista-entra .15s ease-out both; }}
.st-key-tour-card {{ animation: tarjeta-entra .18s ease-out both; }}
[data-testid="stToast"], [data-testid="stAlert"] {{ animation: aparece .15s ease-out both; }}
/* Estados de hover y foco: misma duración en botones, filas, tarjetas, marcos y estados del mapa. */
.stApp button, a.kpi, .t-fila, .exp, .doc-tarjeta, a.pag-btn, a.t-motivo, .btn-acento, .btn-linea,
.mx-estado, .mx-llamada circle {{
  transition: background-color .14s ease-out, border-color .14s ease-out, color .14s ease-out,
    filter .14s ease-out, transform .14s ease-out, box-shadow .14s ease-out; }}
@media (prefers-reduced-motion: reduce) {{
  .st-key-b-cabecera, .st-key-b-kpis, .st-key-b-mapa, .st-key-subir-marco, .st-key-estado-resumen,
  .marco-dictamen, .docs-grid, .st-key-tour-card, [data-testid="stToast"], [data-testid="stAlert"] {{ animation: none; }}
  .stApp button, a.kpi, .t-fila, .exp, .doc-tarjeta, a.pag-btn, a.t-motivo, .btn-acento, .btn-linea,
  .mx-estado, .mx-llamada circle {{ transition: none; }}
}}
</style>
"""
