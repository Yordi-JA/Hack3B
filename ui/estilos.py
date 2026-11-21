"""CSS de la app. Los valores salen de `tokens`; aquí solo hay estructura.

Dirección "Rojo 3B + blanco": la barra lateral y el marco de la app son rojo de marca; todo el
contenido va sobre blanco o gris muy claro. La tinta solo se usa como color de texto y líneas finas.
"""
from __future__ import annotations

from . import tokens as t

TONOS = {"verde": t.VERDE, "ambar": t.AMBAR, "vino": t.VINO, "azul": t.AZUL, "gris": t.GRIS}


def clase_tono(tono: t.Tono) -> str:
    return next(nombre for nombre, valor in TONOS.items() if valor == tono)


def _css_tonos() -> str:
    reglas = []
    for nombre, tono in TONOS.items():
        reglas.append(f".tono-{nombre}{{color:{tono.texto};background:{tono.fondo};}}")
        # Sello del dictamen: blanco sobre el color fuerte del estado (6.7:1 a 8.1:1).
        reglas.append(f".sello-{nombre}{{color:#fff;background:{tono.texto};}}")
        # Estado en texto (tarjetas de la bandeja): el color fuerte del estado sobre el fondo claro.
        reglas.append(f".est-{nombre}{{color:{tono.texto};}}")
        # Sobre la tarjeta roja del dictamen el sello se invierte: bloque blanco, texto del estado.
        reglas.append(f".marco-dictamen .sello-{nombre}{{color:{tono.texto};background:#fff;}}")
    return "".join(reglas)


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

/* ---- etiquetas de estado: fondo suave, texto siempre presente ---- */
.etq {{ display: inline-block; padding: 2px 9px; border-radius: 6px; font-size: 12px; font-weight: 700;
  line-height: 1.6; white-space: nowrap; }}
.etq-borde {{ background: transparent; border: 1px solid currentColor; }}
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
.mx-estado {{ stroke: #fff; stroke-width: 1; vector-effect: non-scaling-stroke; }}
.mx-enlace, .mx-llamada {{ cursor: pointer; }}
/* Los enlaces del SVG heredan el subrayado de los de Streamlit; los números no lo llevan. */
.mx-mapa a, .mx-mapa a:hover, .mx-mapa a:focus, .mx-mapa a:focus-visible, .mx-mapa text {{ text-decoration: none !important; }}
.mx-enlace:hover .mx-estado {{ stroke: var(--tinta); stroke-width: 2; }}
.mx-borde-sel {{ fill: none; stroke: var(--tinta); stroke-width: 3; vector-effect: non-scaling-stroke; pointer-events: none; }}
/* Números en unidades del mapa (1000 de ancho): con el mapa de 810 a 920 px quedan en 14 a 16 px. */
.mx-num {{ font: 700 17px var(--f-texto); fill: var(--tinta); pointer-events: none; }}
.mx-num-halo {{ stroke: #fff; stroke-width: 4px; paint-order: stroke; stroke-linejoin: round; }}
.mx-llamada circle {{ stroke: var(--tinta); stroke-width: 1.5; vector-effect: non-scaling-stroke; }}
.mx-llamada:hover circle {{ stroke-width: 2.5; }}
.mx-guia {{ stroke: var(--tinta); stroke-width: 1.2; vector-effect: non-scaling-stroke; pointer-events: none; }}
.sin-entidad {{ font-size: 12px; color: var(--texto2); margin-top: 4px; }}

/* ---- marco: tarjeta con línea fina y título que interrumpe la línea ----
   Base (documentos): blanca con línea y título en tinta. Dictamen: bloque rojo sólido con línea y
   título blancos; es el único bloque rojo del contenido. */
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
.mx-resaltado {{ stroke: var(--tinta); stroke-width: 2; vector-effect: non-scaling-stroke; }}

/* dictamen: bloque rojo, todo el texto en blanco puro (6.26:1) */
.marco-dictamen {{ background: var(--rojo-osc); border-color: var(--rojo-osc); color: #fff; }}
.marco-dictamen::before {{ border: 2px solid #fff; }}
.marco-dictamen .marco-titulo {{ background: var(--rojo-osc); color: #fff; }}
.marco-dictamen .marco-ceja, .marco-dictamen .marco-texto p.marco-resumen, .marco-dictamen .marco-datos,
.marco-dictamen .marco-datos b, .marco-dictamen .marco-media figcaption {{ color: #fff; }}
.marco-dictamen .btn-acento {{ background: #fff; color: var(--rojo-osc) !important; }}
.marco-dictamen .btn-acento:hover {{ background: {t.PANEL}; }}
.marco-dictamen .btn-linea {{ background: transparent; color: #fff !important; border: 1.5px solid #fff; }}
.marco-dictamen .btn-linea:hover {{ background: rgba(255,255,255,.14); color: #fff !important; border-color: #fff; }}
.marco-dictamen .marco-botones span.btn-nada {{ color: #fff; }}
.stApp .marco-dictamen a:focus-visible {{ outline: 3px solid #fff; outline-offset: 2px; }}
.marco-dictamen .marco-media {{ background: transparent; }}
.marco-dictamen .mx-vecino {{ fill: rgba(255,255,255,.14); stroke: rgba(255,255,255,.5); }}
.marco-dictamen .mx-resaltado {{ fill: #fff; stroke: #fff; }}

.razones {{ background: var(--tarjeta); border: 1px solid var(--borde); border-radius: 12px; padding: 16px 20px; margin-top: 12px; }}
.razones h3 {{ font-size: 14px; margin: 0 0 8px; padding: 0; color: var(--tinta); }}
.razones ol {{ margin: 0; padding-left: 20px; }}
.razones li {{ font-size: 15px; line-height: 1.5; margin: 3px 0; }}

/* ---- tipos de documento: recibidos y faltantes ---- */
.tipos {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }}
.tipo {{ background: var(--tarjeta); border: 1px solid var(--borde); border-radius: 10px; padding: 12px 14px; min-width: 0; }}
.tipo b {{ display: block; font-size: 14px; margin: 6px 0 2px; color: var(--tinta); }}
.tipo small {{ display: block; font-size: 12px; color: var(--texto2); overflow-wrap: anywhere; }}
.tipo-falta {{ border: 1.5px dashed {t.VINO.texto}; }}

/* tarjetas por documento: marco claro, línea y título en tinta */
.docs {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(min(400px, 100%), 1fr)); gap: 6px 16px; }}
.docs .marco {{ padding: 46px 26px 26px; margin: 26px 0 4px; }}
.docs .marco::before {{ inset: 22px 10px 10px; }}
.docs .marco-titulo {{ top: 22px; left: 22px; font-size: 21px; padding: 0 10px; }}
.doc-archivo {{ font-size: 12px; color: var(--texto2); margin: 0 0 10px; overflow-wrap: anywhere; }}
.doc-etiquetas {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
.doc-campos {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; font-size: 13px; margin: 0 0 12px; }}
.doc-campos dt {{ color: var(--texto2); }}
.doc-campos dd {{ margin: 0; color: var(--texto); overflow-wrap: anywhere; }}
.doc-conteo {{ font-size: 13px; color: var(--texto2); border-top: 1px solid var(--borde); padding-top: 10px; }}
.doc-conteo b {{ color: var(--tinta); }}
.doc-aviso {{ font-size: 13px; line-height: 1.5; color: var(--texto); background: {t.AMBAR.fondo}; padding: 10px 12px; border-radius: 4px; margin-bottom: 10px; }}

/* ---- tablas: datos extraídos, requisitos, inconsistencias ---- */
.tabla-caja {{ overflow-x: auto; background: var(--tarjeta); border: 1px solid var(--borde); border-radius: 12px; }}
table.tabla {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.tabla th {{ text-align: left; font-size: 12px; color: var(--texto2); font-weight: 600; background: #F8F9F6;
  padding: 10px 12px; border-bottom: 1px solid var(--borde); vertical-align: bottom; }}
.tabla td {{ padding: 10px 12px; border-bottom: 1px solid var(--borde); vertical-align: top; min-width: 140px; }}
.tabla tr:last-child td {{ border-bottom: 0; }}
.tabla td.campo {{ font-weight: 600; color: var(--tinta); min-width: 150px; }}
.tabla td.difiere {{ background: {t.AMBAR.fondo}; }}
.tabla .vacio {{ color: var(--texto2); }}
.tabla details summary {{ cursor: pointer; color: var(--texto2); font-size: 12px; margin-top: 4px; }}
q.cita, .cita {{ display: block; quotes: "\\201C" "\\201D"; font-style: italic; color: var(--texto); background: #F3F5F0;
  border-left: 3px solid var(--borde); padding: 6px 10px; margin: 4px 0; font-size: 13px; line-height: 1.45; overflow-wrap: anywhere; }}
.fuente {{ font-size: 12px; color: var(--texto2); }}

.aviso-req {{ background: {t.AMBAR.fondo}; color: var(--texto); border-radius: 8px; padding: 8px 12px; margin: 0 0 8px; font-size: 14px; }}
.resumen-req {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}

.inc {{ background: var(--tarjeta); border: 1px solid var(--borde); border-radius: 12px; padding: 16px 18px; margin-bottom: 12px; }}
.inc h3 {{ font-size: 15px; color: var(--tinta); margin: 0 0 4px; padding: 0; }}
.inc p {{ font-size: 14px; margin: 0 0 10px; }}

.hallazgo {{ background: var(--tarjeta); border: 1px solid var(--borde); border-radius: 10px; padding: 14px 16px; margin-bottom: 10px; }}
.hallazgo-cab {{ display: flex; flex-wrap: wrap; gap: 6px 8px; align-items: center; margin-bottom: 6px; }}
.hallazgo-cab b {{ font-size: 14px; color: var(--tinta); }}
.hallazgo-id {{ font-size: 12px; color: var(--texto2); font-weight: 600; }}
.hallazgo p {{ font-size: 14px; line-height: 1.5; margin: 0 0 6px; }}
.vacio-msg {{ color: var(--texto2); font-size: 14px; }}

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
.mapa-lienzo {{ position: relative; max-width: calc(62vh * 1000 / 630); margin: 10px auto 0; }}
.mx-abr {{ font: 700 11px var(--f-texto); fill: var(--texto2); letter-spacing: .05em; pointer-events: none; }}

.mx-ventana {{ position: absolute; z-index: 5; width: 262px; background: #fff; border: 2px solid var(--tinta); border-radius: 6px;
  box-shadow: 0 10px 28px rgba(4,33,31,.18); padding: 14px 16px 14px; }}
.mx-ventana.v-der {{ transform: translate(22px, -50%); }}
.mx-ventana.v-izq {{ transform: translate(calc(-100% - 22px), -50%); }}
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

@media (max-width: 1100px) {{
  .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .mx-ventana {{ width: 220px; }}
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
</style>
"""
