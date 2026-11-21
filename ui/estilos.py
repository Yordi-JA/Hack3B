"""CSS de la app. Los valores salen de `tokens`; aquí solo hay estructura."""
from __future__ import annotations

from . import tokens as t

TONOS = {"verde": t.VERDE, "ambar": t.AMBAR, "vino": t.VINO, "azul": t.AZUL, "gris": t.GRIS}


def clase_tono(tono: t.Tono) -> str:
    return next(nombre for nombre, valor in TONOS.items() if valor == tono)


def _css_tonos() -> str:
    reglas = []
    for nombre, tono in TONOS.items():
        reglas.append(f".tono-{nombre}{{color:{tono.texto};background:{tono.fondo};}}")
        reglas.append(f".marco .tono-{nombre}{{color:{t.TARJETA_OSCURA};background:{tono.oscuro};}}")
        reglas.append(f".txt-{nombre}{{color:{tono.oscuro};}}")
    return "".join(reglas)


def css() -> str:
    return f"""
<style>
:root {{
  --rojo: {t.ROJO_3B}; --rojo-osc: {t.ROJO_3B_OSCURO}; --verde3b: {t.VERDE_3B}; --tinta: {t.TINTA_3B};
  --panel: {t.PANEL}; --tarjeta: {t.TARJETA}; --oscura: {t.TARJETA_OSCURA}; --oscura2: {t.TARJETA_OSCURA_2};
  --borde: {t.BORDE}; --texto: {t.TEXTO}; --texto2: {t.TEXTO_2};
  --claro: {t.TEXTO_SOBRE_OSCURO}; --claro2: {t.TEXTO_SOBRE_OSCURO_2};
  --f-texto: {t.FUENTE_TEXTO}; --f-titular: {t.FUENTE_TITULAR};
}}

/* ---- armazón: fondo oscuro, barra lateral y panel principal redondeado ---- */
.stApp, [data-testid="stAppViewContainer"] {{ background: var(--tinta); }}
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp button {{ font-family: var(--f-texto); }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"],
[data-testid="stDecoration"], footer {{ display: none !important; }}
[data-testid="stExpandSidebarButton"] {{ color: var(--claro); }}
[data-testid="stMain"] {{
  background: var(--panel); margin: 12px 12px 12px 0; border-radius: 20px;
  max-height: calc(100dvh - 24px); overflow-y: auto;
}}
[data-testid="stMainBlockContainer"] {{ max-width: 1360px; padding: 28px 36px 64px; }}
[data-testid="stSidebar"] {{ background: var(--tinta); border-right: 0; }}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding: 4px 0 24px 16px; }}
[data-testid="stSidebar"] {{ color: var(--claro2); }}

.lateral-marca {{ display: flex; gap: 12px; align-items: center; padding: 4px 16px 20px 4px;
  border-bottom: 1px solid var(--oscura2); margin-bottom: 8px; }}
.lateral-marca svg {{ width: 46px; height: 46px; flex: none; }}
.lateral-marca b {{ display: block; color: var(--claro); font-size: 15px; line-height: 1.2; }}
.lateral-marca small {{ color: var(--claro2); font-size: 12px; }}
.lateral-grupo {{ color: var(--claro2); font-size: 11px; font-weight: 600; letter-spacing: .06em;
  text-transform: uppercase; margin: 18px 0 6px 6px; }}
[data-testid="stSidebar"] p.lateral-nota {{ color: var(--claro2); font-size: 13px; line-height: 1.5; margin: 28px 16px 0 6px; }}

/* navegación: botones de Streamlit con forma de pestaña que se une al panel */
[data-testid="stSidebar"] [class*="st-key-nav-"] {{ width: calc(100% + 32px) !important; }}
[data-testid="stSidebar"] [class*="st-key-nav-"] button {{
  width: 100%; justify-content: flex-start; min-height: 44px; border: 0; border-radius: 22px 0 0 22px;
  background: transparent; color: var(--claro2); padding: 10px 16px; box-shadow: none;
}}
[data-testid="stSidebar"] [class*="st-key-nav-"] button > div {{ justify-content: flex-start; width: 100%; }}
[data-testid="stSidebar"] [class*="st-key-nav-"] button p {{ font-size: 15px; color: inherit; text-align: left; }}
[data-testid="stSidebar"] [class*="st-key-nav-"] button:hover {{ color: var(--claro); background: var(--oscura2); }}
[data-testid="stSidebar"] [class*="st-key-nav-"] [data-testid="stBaseButton-primary"],
[data-testid="stSidebar"] [class*="st-key-nav-"] [data-testid="stBaseButton-primary"]:hover {{
  background: var(--panel); color: var(--rojo-osc); font-weight: 700;
}}
[data-testid="stSidebar"] [class*="st-key-nav-"] [data-testid="stBaseButton-primary"] p {{ font-weight: 700; }}

/* foco visible en todo lo que se puede usar con teclado */
.stApp a:focus-visible, .stApp button:focus-visible, .mx-enlace:focus-visible path {{
  outline: 3px solid var(--verde3b); outline-offset: 2px;
}}

/* acción principal: rojo de marca (versión oscura, contraste AA con texto blanco) */
.stApp [data-testid="stBaseButton-primary"] {{ background: var(--rojo-osc); border-color: var(--rojo-osc); color: #fff; }}
.stApp [data-testid="stBaseButton-primary"]:hover {{ background: #A51118; border-color: #A51118; color: #fff; }}

/* ---- tipografía del panel ---- */
.encabezado {{ display: flex; flex-wrap: wrap; align-items: end; justify-content: space-between; gap: 8px 24px; margin-bottom: 4px; }}
.encabezado h1 {{ font-family: var(--f-titular); font-size: 30px; line-height: 1.1; color: var(--tinta); margin: 0; padding: 0; }}
.encabezado p {{ color: var(--texto2); margin: 6px 0 0; font-size: 14px; }}
.seccion {{ font-family: var(--f-titular); font-size: 19px; color: var(--tinta); margin: 36px 0 4px; scroll-margin-top: 24px; }}
.ancla {{ scroll-margin-top: 16px; height: 0; }}
.seccion-sub {{ color: var(--texto2); font-size: 14px; margin: 0 0 14px; }}

/* ---- etiquetas de estado: fondo suave, texto siempre presente ---- */
.etq {{ display: inline-block; padding: 2px 9px; border-radius: 6px; font-size: 12px; font-weight: 700;
  line-height: 1.6; white-space: nowrap; }}
.etq-borde {{ background: transparent; border: 1px solid currentColor; }}
{_css_tonos()}

/* ---- indicadores ---- */
.kpis {{ display: grid; grid-template-columns: 1.3fr repeat(4, 1fr); gap: 12px; margin: 18px 0 8px; }}
.kpi {{ background: var(--tarjeta); border: 1px solid var(--borde); border-radius: 14px; padding: 14px 16px; min-width: 0; }}
.kpi span {{ color: var(--texto2); font-size: 13px; }}
.kpi b {{ display: block; font-family: var(--f-titular); font-size: 30px; color: var(--tinta); line-height: 1.2; margin-top: 4px; }}
.kpi small {{ color: var(--texto2); font-size: 12px; }}
.kpi-principal {{ background: var(--tinta); border-color: var(--tinta); }}
.kpi-principal span, .kpi-principal small {{ color: var(--claro2); }}
.kpi-principal b {{ color: var(--claro); }}

/* ---- tarjeta de expediente en la bandeja (versión ligera del marco) ---- */
.lista {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(min(290px, 100%), 1fr)); gap: 22px 14px; margin-top: 18px; }}
a.exp {{ position: relative; display: block; text-decoration: none; color: var(--texto); background: var(--tarjeta);
  border-radius: 12px; padding: 26px 20px 16px; border: 1px solid var(--borde); }}
a.exp::before {{ content: ""; position: absolute; inset: 12px 8px 8px; border: 1.5px solid var(--tinta);
  border-radius: 4px; pointer-events: none; }}
a.exp:hover {{ border-color: var(--tinta); }}
a.exp:hover::before {{ border-color: var(--rojo); }}
.exp-titulo {{ position: absolute; top: 12px; left: 18px; transform: translateY(-50%); background: var(--tarjeta);
  padding: 0 8px; font-family: var(--f-titular); font-size: 15px; color: var(--tinta); text-transform: uppercase;
  max-width: calc(100% - 40px); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.exp-lugar {{ font-size: 12px; font-weight: 600; text-transform: uppercase; color: var(--texto2); letter-spacing: .03em; margin: 4px 0 8px; }}
.exp-etiquetas {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }}
.exp-resumen {{ font-size: 14px; line-height: 1.45; color: var(--texto); margin: 0 0 10px;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
.exp-meta {{ font-size: 12px; color: var(--texto2); display: flex; flex-wrap: wrap; gap: 4px 12px; }}

/* ---- mapa ---- */
.mapa-caja {{ background: var(--tarjeta); border: 1px solid var(--borde); border-radius: 14px; padding: 16px 16px 10px; }}
.mapa-caja h3 {{ font-size: 15px; color: var(--tinta); margin: 0; padding: 0; font-weight: 700; }}
.mapa-caja p {{ font-size: 12px; color: var(--texto2); margin: 4px 0 8px; }}
.leyenda {{ display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 12px; color: var(--texto2); margin: 6px 0 4px; }}
.leyenda i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: -1px; margin-right: 5px; border: 1px solid rgba(0,0,0,.15); }}
svg.mx-mapa {{ width: 100%; height: auto; display: block; }}
.mx-estado {{ stroke: #fff; stroke-width: 1; vector-effect: non-scaling-stroke; }}
.mx-enlace {{ cursor: pointer; }}
.mx-enlace:hover .mx-estado {{ stroke: var(--tinta); stroke-width: 2; }}
.mx-borde-sel {{ fill: none; stroke: var(--tinta); stroke-width: 3; vector-effect: non-scaling-stroke; pointer-events: none; }}
.mx-num {{ font: 700 14px var(--f-texto); fill: var(--tinta); stroke: #fff; stroke-width: 3px; paint-order: stroke; pointer-events: none; }}
.sin-entidad {{ font-size: 12px; color: var(--texto2); margin-top: 4px; }}

/* ---- marco: tarjeta oscura con línea blanca y título sobre la línea ---- */
.marco {{ position: relative; background: var(--oscura); color: var(--claro); border-radius: 6px;
  padding: 58px 40px 36px; margin: 34px 0 10px; }}
.marco::before {{ content: ""; position: absolute; inset: 28px 14px 14px; border: 2px solid var(--claro); pointer-events: none; }}
.marco-titulo {{ position: absolute; top: 28px; left: 30px; transform: translateY(-50%); background: var(--oscura);
  padding: 0 14px; margin: 0; font-family: var(--f-titular); font-size: 34px; line-height: 1; color: var(--claro);
  text-transform: uppercase; letter-spacing: -.01em; max-width: calc(100% - 60px);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.marco-cuerpo {{ display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: 28px; align-items: center; }}
.marco-ceja {{ font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--claro2); margin: 0 0 6px; }}
.marco-titular {{ font-family: var(--f-titular); font-size: 44px; line-height: 1.05; margin: 0 0 14px; }}
.marco-texto p.marco-resumen {{ color: var(--claro); font-size: 16px; line-height: 1.55; margin: 0 0 14px; max-width: 62ch; }}
.marco-datos {{ display: flex; flex-wrap: wrap; gap: 6px 22px; font-size: 13px; color: var(--claro2); margin: 0 0 20px; }}
.marco-datos b {{ color: var(--claro); }}
.marco-botones {{ display: flex; flex-wrap: wrap; gap: 10px; }}
.marco-botones a {{ display: inline-flex; align-items: center; min-height: 44px; padding: 0 20px; font-weight: 700;
  font-size: 14px; text-transform: uppercase; text-decoration: none; border-radius: 2px; }}
.btn-acento {{ background: var(--rojo-osc); color: #fff !important; }}
.btn-acento:hover {{ background: #A51118; }}
.btn-oscuro {{ background: var(--oscura2); color: var(--claro) !important; }}
.btn-oscuro:hover {{ background: #21504B; }}
.marco-media {{ align-self: stretch; display: flex; flex-direction: column; justify-content: center; align-items: center;
  background: #06231F; border-radius: 2px; padding: 12px; min-height: 220px; }}
.marco-media svg {{ width: 100%; max-height: 300px; }}
.marco-media figcaption {{ font-size: 12px; color: var(--claro2); margin-top: 8px; text-align: center; }}
.mx-vecino {{ fill: {t.MAPA_VECINO}; stroke: var(--oscura); stroke-width: 1; vector-effect: non-scaling-stroke; }}
.mx-resaltado {{ stroke: var(--claro); stroke-width: 2; vector-effect: non-scaling-stroke; }}

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

/* tarjetas por documento: mismo marco, más chico */
.docs {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(min(400px, 100%), 1fr)); gap: 6px 16px; }}
.docs .marco {{ padding: 46px 26px 26px; margin: 26px 0 4px; }}
.docs .marco::before {{ inset: 22px 10px 10px; }}
.docs .marco-titulo {{ top: 22px; left: 22px; font-size: 21px; padding: 0 10px; }}
.doc-archivo {{ font-size: 12px; color: var(--claro2); margin: 0 0 10px; overflow-wrap: anywhere; }}
.doc-etiquetas {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
.doc-campos {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; font-size: 13px; margin: 0 0 12px; }}
.doc-campos dt {{ color: var(--claro2); }}
.doc-campos dd {{ margin: 0; color: var(--claro); overflow-wrap: anywhere; }}
.doc-conteo {{ font-size: 13px; color: var(--claro2); border-top: 1px solid var(--oscura2); padding-top: 10px; }}
.doc-conteo b {{ color: var(--claro); }}
.doc-aviso {{ font-size: 13px; line-height: 1.5; color: var(--claro); background: var(--oscura2); padding: 10px 12px; border-radius: 4px; margin-bottom: 10px; }}

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
.tabla details summary:focus-visible {{ outline: 3px solid var(--verde3b); }}
q.cita, .cita {{ display: block; quotes: "\\201C" "\\201D"; font-style: italic; color: var(--texto); background: #F3F5F0;
  border-left: 3px solid var(--borde); padding: 6px 10px; margin: 4px 0; font-size: 13px; line-height: 1.45; overflow-wrap: anywhere; }}
.fuente {{ font-size: 12px; color: var(--texto2); }}

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

/* Streamlit da estilo propio a h1-h3 y p dentro de Markdown; estas reglas ganan por especificidad. */
.stApp .marco .marco-titulo, .stApp .encabezado h1, .stApp h2.seccion {{ font-family: var(--f-titular); font-weight: 900; }}
.stApp .marco .marco-titulo {{ font-size: 34px; line-height: 1; padding: 0 14px; margin: 0; }}
.stApp .docs .marco .marco-titulo {{ font-size: 21px; padding: 0 10px; }}
.stApp .marco p.marco-titular {{ font-family: var(--f-titular); font-size: 44px; line-height: 1.05; font-weight: 900; margin: 0 0 14px; }}
.stApp h2.seccion {{ font-size: 21px; padding: 0; margin: 40px 0 4px; letter-spacing: 0; }}
.stApp .doc-campos dt, .stApp .doc-campos dd {{ font-size: 14px; line-height: 1.4; }}
.stApp .inc h3, .stApp .razones h3, .stApp .mapa-caja h3 {{ font-family: var(--f-texto); font-weight: 700; }}

@media (max-width: 900px) {{
  .stApp .marco .marco-titulo {{ font-size: 26px; }}
  .stApp .marco p.marco-titular {{ font-size: 34px; }}
  .kpis {{ grid-template-columns: repeat(2, 1fr); }}
  .kpi-principal {{ grid-column: 1 / -1; }}
  .marco-cuerpo {{ grid-template-columns: 1fr; }}
  .marco {{ padding: 54px 24px 28px; }}
  .marco-titulo {{ font-size: 26px; }}
  .marco-titular {{ font-size: 34px; }}
  [data-testid="stMainBlockContainer"] {{ padding: 56px 16px 48px; }}
  [data-testid="stMain"] {{ margin: 0; border-radius: 0; max-height: none; }}
}}
</style>
"""
