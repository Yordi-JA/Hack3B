"""Piezas de HTML para `st.markdown(..., unsafe_allow_html=True)`.

Funciones puras que devuelven texto, para poder probarlas sin Streamlit. Todo dato que viene de
los documentos pasa por `escape`. El HTML sale en una sola línea por bloque: una línea en blanco
o una sangría de 4 espacios harían que el Markdown de Streamlit lo convierta en párrafo o código.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlencode

from expedientes.schemas import (
    Campo,
    Dictamen,
    DocumentoAnalizado,
    EstadoRegla,
    Evidencia,
    Hallazgo,
    Inconsistencia,
    Legibilidad,
    Recomendacion,
    Severidad,
    TipoDocumento,
)

from . import decisiones as Dec
from . import logica as L
from . import mapa
from . import tokens as t
from .estilos import clase_tono

NOMBRE_LEGIBILIDAD = {
    Legibilidad.BUENA: "Legible",
    Legibilidad.PARCIAL: "Legible en parte",
    Legibilidad.ILEGIBLE: "Ilegible",
}


def txt(valor: Optional[object]) -> str:
    """Única salida de texto libre (documentos, LLM, nombres de archivo) hacia el HTML.

    Escapa, quita retornos de carro, colapsa espacios dentro de cada línea y une las líneas con <br>. Así ningún
    fragmento puede tener una línea en blanco: con una, el Markdown de Streamlit cerraría el bloque
    HTML y el resto se interpretaría como Markdown (por ejemplo `![](https://...)`, que haría que el
    navegador pidiera una URL externa con datos del expediente).
    """
    if valor is None:
        return ""
    lineas = (" ".join(linea.split()) for linea in str(valor).replace(chr(13), "").split(chr(10)))
    return "<br>".join(escape(linea) for linea in lineas if linea)


def url(**params: Optional[str]) -> str:
    return "?" + urlencode({k: v for k, v in params.items() if v})


def pct(valor: float) -> str:
    return f"{round(valor * 100)} %"


def fecha(valor) -> str:
    return valor.strftime("%d/%m/%Y %H:%M") if hasattr(valor, "hour") else valor.strftime("%d/%m/%Y")


def logo_3b(invertido: bool = False) -> str:
    """Círculo con B sobre BB, dibujado aquí porque las imágenes de marca no se versionan.

    Normal: círculo rojo, letras blancas. Invertido (sobre la barra lateral roja): círculo blanco,
    letras rojas; un círculo rojo sobre rojo desaparecería.
    """
    fondo, letra = ("#fff", t.ROJO_3B) if invertido else (t.ROJO_3B, "#fff")
    return (
        '<svg viewBox="0 0 100 100" role="img" aria-label="Tiendas 3B" xmlns="http://www.w3.org/2000/svg">'
        f'<circle cx="50" cy="50" r="49" fill="{fondo}"/>'
        f'<text x="50" y="45" text-anchor="middle" fill="{letra}" font-family={t.FUENTE_TITULAR!r} '
        'font-weight="900" font-size="38">B</text>'
        f'<text x="50" y="80" text-anchor="middle" fill="{letra}" font-family={t.FUENTE_TITULAR!r} '
        'font-weight="900" font-size="38" letter-spacing="-1">BB</text></svg>'
    )


def encabezado(titulo: str, subtitulo: str = "") -> str:
    sub = f"<p>{txt(subtitulo)}</p>" if subtitulo else ""
    return f'<div class="encabezado"><div><h1>{txt(titulo)}</h1>{sub}</div></div>'


def seccion(titulo: str, ancla: str, sub: str = "") -> str:
    extra = f'<p class="seccion-sub">{txt(sub)}</p>' if sub else ""
    # Streamlit reescribe el id de los encabezados con el texto; el ancla va en un elemento aparte.
    return f'<div class="ancla" id="{ancla}"></div><h2 class="seccion">{txt(titulo)}</h2>{extra}'


def cita(ev: Evidencia) -> str:
    return (
        f'<q class="cita">{txt(ev.cita)}</q>'
        f'<span class="fuente">{txt(ev.archivo)}, página {ev.pagina}</span>'
    )


def texto_ubicacion(u: L.Ubicacion) -> str:
    """Texto plano: 'Ixmiquilpan, Hidalgo', con aviso si los documentos no coinciden."""
    municipio = u.municipio_valor or (u.municipio.title() if u.municipio else None)
    if not u.valores:
        return ", ".join(filter(None, [municipio, "sin entidad federativa"]))
    if u.confirmada:
        return ", ".join(filter(None, [municipio, mapa.nombre_entidad(u.entidad)]))
    nombres = " o ".join(mapa.nombre_entidad(v) for v in u.valores)
    return ", ".join(filter(None, [municipio, f"{nombres} (sin confirmar)"]))


# ------------------------------------------------------------------ bandeja

def resumen_bandeja(ind: L.Indicadores) -> str:
    """Una línea de texto bajo el subtítulo: total, confianza promedio y cuántos son de ejemplo."""
    if not ind.total:
        return '<p class="resumen-bandeja">Ningún expediente con estos filtros</p>'
    partes = [f"{ind.total} expediente{'s' if ind.total != 1 else ''}"]
    if ind.confianza_promedio is not None:
        partes.append(f"confianza promedio {pct(ind.confianza_promedio)}")
    if ind.ejemplos:
        partes.append(f"{ind.ejemplos} de ejemplo")
    return f'<p class="resumen-bandeja">{" · ".join(partes)}</p>'


def tarjeta_expediente(clave: str, d: Dictamen, es_ejemplo: bool) -> str:
    """Tarjeta de la bandeja: solo la línea del marco sobre el fondo de la página, sin etiquetas
    de color; el estado va en texto, en su color, al final de la ceja."""
    u = L.consolidar_ubicacion(d)
    recibidos = sum(1 for tr in L.documentos_por_tipo(d) if tr.recibido)
    n_inc = len(d.inconsistencias)
    inc = "Sin inconsistencias" if not n_inc else f"{n_inc} inconsistencia{'s' if n_inc > 1 else ''}"
    tono = clase_tono(t.ESTADO[d.recomendacion])
    meta = [f"{recibidos} de 4 tipos de documento", inc, f"Confianza {pct(d.confianza)}"]
    if es_ejemplo:
        meta.append("Ejemplo")
    meta.append(fecha(d.fecha_analisis))
    return (
        f'<a class="exp" href="{escape(url(vista="detalle", exp=clave))}" target="_self">'
        f'<span class="exp-titulo">{txt(d.expediente_id)}</span>'
        f'<div class="exp-lugar">{txt(texto_ubicacion(u))} · '
        f'<b class="exp-estado est-{tono}">{txt(d.recomendacion.value)}</b></div>'
        f'<p class="exp-resumen">{txt(d.resumen)}</p>'
        f'<div class="exp-meta">{" · ".join(meta)}</div></a>'
    )


def lista_expedientes(items: Iterable[tuple[str, Dictamen, bool]]) -> str:
    return '<div class="lista">' + "".join(tarjeta_expediente(*i) for i in items) + "</div>"


# ------------------------------------------------------------------ tabla de expedientes (repositorio)
#
# Una fila por expediente para que la vista aguante miles de registros: encabezado fijo con el
# nombre de cada columna, filas compactas que abren el detalle y paginación.

COLUMNAS_TABLA = ("Expediente", "Ubicación", "Recomendación", "Estatus", "Documentos", "Inconsistencias", "Confianza", "Análisis")


def insignia_estatus(e: "Dec.Estatus") -> str:
    return f'<span class="insignia est-{clase_tono(Dec.TONO[e])}" style="background:{Dec.TONO[e].fondo}">{txt(e.value)}</span>'


def _motivo_fila(d: Dictamen, params: dict[str, str], categoria: Optional["L.Categoria"]) -> str:
    """Debajo de la recomendación: el motivo principal como enlace que filtra por su categoría. Con un
    filtro de motivo activo se muestra el motivo de esa categoría y, si no es el principal, también éste."""
    ms = L.motivos(d) if d.recomendacion != Recomendacion.CUMPLE else []
    principal = ms[0] if ms else None
    mostrado = L.motivo_de_categoria(d, categoria) if categoria else principal
    if mostrado is None:
        return ""
    tono = t.SEVERIDAD[mostrado.severidad]
    href = url(**L.aplicar_filtro(params, "mot", mostrado.categoria.value))
    extra = ""
    if categoria and principal and principal.categoria != categoria:
        extra = f' <span class="t-tambien">(también: {txt(L.MOTIVO[principal.categoria])})</span>'
    return (
        f'<a class="t-motivo est-{clase_tono(tono)}" style="color:{tono.texto}" href="{escape(href)}" target="_self" '
        f'title="Filtrar por {txt(L.MOTIVO[mostrado.categoria])}">{txt(mostrado.etiqueta)}</a>{extra}'
    )


def fila_expediente(clave: str, d: Dictamen, es_ejemplo: bool, estatus: "Dec.Estatus",
                    params: Optional[dict[str, str]] = None, categoria: Optional["L.Categoria"] = None) -> str:
    """Una fila de la tabla. La fila es un div: el enlace del identificador se estira sobre toda la fila
    para abrir el detalle, y el enlace del motivo queda encima para filtrar sin abrir el detalle (un
    enlace dentro de otro no es HTML válido)."""
    u = L.consolidar_ubicacion(d)
    recibidos = sum(1 for tr in L.documentos_por_tipo(d) if tr.recibido)
    tono = t.ESTADO[d.recomendacion]
    ejemplo = ' <small class="t-ej">Ejemplo</small>' if es_ejemplo else ""
    motivo = _motivo_fila(d, params or {}, categoria)
    celdas = (
        f'<a class="t-id t-abrir" href="{escape(url(vista="detalle", exp=clave))}" target="_self">'
        f'{txt(d.expediente_id)}{ejemplo}</a>',
        f'<span class="t-lugar">{txt(texto_ubicacion(u))}</span>',
        f'<span class="t-rec est-{clase_tono(tono)}"><i style="background:{tono.mapa}"></i>{txt(d.recomendacion.value)}</span>'
        + (f'<span class="t-motivo-linea">{motivo}</span>' if motivo else ""),
        insignia_estatus(estatus),
        f"<span>{recibidos} de 4</span>",
        f"<span>{len(d.inconsistencias)}</span>",
        f"<span>{pct(d.confianza)}</span>",
        f'<span class="t-fecha">{fecha(d.fecha_analisis)}</span>',
    )
    cuerpo = "".join(f'<span class="t-celda" role="cell" data-col="{escape(n)}">{c}</span>' for n, c in zip(COLUMNAS_TABLA, celdas))
    return f'<div class="t-fila" role="row">{cuerpo}</div>'


def tabla_expedientes(filas: Iterable[tuple[str, Dictamen, bool, "Dec.Estatus"]],
                      params: Optional[dict[str, str]] = None, categoria: Optional["L.Categoria"] = None) -> str:
    cab = "".join(f'<span class="t-celda" role="columnheader">{n}</span>' for n in COLUMNAS_TABLA)
    return (
        f'<div class="t-tabla" role="table" aria-label="Expedientes"><div class="t-cab" role="row">{cab}</div>'
        + "".join(fila_expediente(*f, params=params, categoria=categoria) for f in filas)
        + "</div>"
    )


def filtro_motivo_activo(categoria: "L.Categoria", params: dict[str, str]) -> str:
    href = url(**L.aplicar_filtro(params, "mot", ""))
    return (
        f'<p class="filtro-activo">Filtrando por motivo: <b>{txt(L.nombre_motivo(categoria))}</b> · '
        f'<a href="{escape(href)}" target="_self">Quitar filtro</a></p>'
    )


def paginador(pagina: int, por_pagina: int, total: int, params: dict[str, str]) -> str:
    """'Mostrando 26-50 de 18 000' y enlaces a la página anterior y siguiente."""
    paginas = max(1, -(-total // por_pagina))
    desde = (pagina - 1) * por_pagina + 1 if total else 0
    hasta = min(pagina * por_pagina, total)

    def enlace(p: int, texto: str) -> str:
        if p < 1 or p > paginas or p == pagina:
            return f'<span class="pag-btn pag-off">{texto}</span>'
        return f'<a class="pag-btn" href="{escape(url(**dict(params, pag=str(p) if p > 1 else "")))}" target="_self">{texto}</a>'

    def miles(n: int) -> str:
        return f"{n:,}".replace(",", " ")

    return (
        f'<div class="paginador"><span>Mostrando {miles(desde)}–{miles(hasta)} de {miles(total)}</span>'
        f'<span class="pag-nav">{enlace(pagina - 1, "‹ Anterior")}'
        f'<span class="pag-num">Página {miles(pagina)} de {miles(paginas)}</span>{enlace(pagina + 1, "Siguiente ›")}</span></div>'
    )


def tarjeta_decision(dec: Optional["Dec.Decision"]) -> str:
    """Tarjeta con el estatus vigente del expediente y el comentario que lo explica."""
    if dec is None:
        return (
            f'<div class="decision-actual">{insignia_estatus(Dec.Estatus.SIN_REVISAR)}'
            '<p class="dec-com">Nadie ha revisado este expediente todavía.</p></div>'
        )
    return (
        f'<div class="decision-actual" style="border-left-color:{Dec.TONO[dec.estatus].texto}">{insignia_estatus(dec.estatus)}'
        f'<p class="dec-com">{txt(dec.comentario)}</p>'
        f'<p class="dec-meta">{txt(dec.usuario)} · {dec.cuando:%d/%m/%Y %H:%M}</p></div>'
    )


def historial_decisiones(hist: list["Dec.Decision"]) -> str:
    filas = "".join(
        f'<li>{insignia_estatus(h.estatus)} <span class="dec-meta">{txt(h.usuario)} · {h.cuando:%d/%m/%Y %H:%M}</span>'
        f'<p class="dec-com">{txt(h.comentario)}</p></li>'
        for h in reversed(hist)
    )
    return f'<ul class="dec-historial">{filas}</ul>'


def caja_mapa(svg: str, sin_entidad: int) -> str:
    leyenda = "".join(
        f'<span><i style="background:{t.ESTADO[r].mapa}"></i>{txt(r.value)}</span>'
        for r in (Recomendacion.NO_CUMPLE, Recomendacion.REQUIERE_REVISION, Recomendacion.CUMPLE)
    ) + f'<span><i style="background:{t.MAPA_VACIO}"></i>Sin expedientes</span>'
    pie = ""
    if sin_entidad:
        pie = (
            f'<div class="sin-entidad">{sin_entidad} expediente{"s" if sin_entidad > 1 else ""} sin entidad '
            "federativa identificada: aparecen en la lista, no en el mapa.</div>"
        )
    return (
        '<div class="mapa-bloque"><h3>Expedientes por entidad</h3>'
        "<p>Color: recomendación más grave. Número: expedientes. Clic para filtrar.</p>"
        f'<div class="leyenda">{leyenda}</div>{svg}{pie}</div>'
    )


# ------------------------------------------------------------------ bandeja tipo tablero (Diego)
#
# Saludo, 4 indicadores en tarjetas, mapa en tarjeta blanca con ventana emergente por estado.

RECS_TABLERO = (Recomendacion.CUMPLE, Recomendacion.REQUIERE_REVISION, Recomendacion.NO_CUMPLE)
ETIQUETA_KPI = {
    Recomendacion.CUMPLE: "Cumplen",
    Recomendacion.REQUIERE_REVISION: "Requieren revisión",
    Recomendacion.NO_CUMPLE: "No cumplen",
}


def _pct_entero(parte: int, total: int) -> str:
    return f"{round(100 * parte / total)} %" if total else "0 %"


def kpis_bandeja(ind: L.Indicadores, params: dict[str, str], activo: Optional[str] = None) -> str:
    """4 tarjetas: total y una por recomendación. Cada una filtra la bandeja al hacer clic.
    `activo`: valor de la recomendación filtrada, para marcar su tarjeta."""
    base = {k: v for k, v in params.items() if k != "rec"}
    sub_total = []
    if ind.confianza_promedio is not None:
        sub_total.append(f"confianza promedio {pct(ind.confianza_promedio)}")
    if ind.ejemplos:
        sub_total.append(f"{ind.ejemplos} de ejemplo")
    tarjetas = [
        f'<a class="kpi kpi-total" href="{escape(url(**base))}" target="_self">'
        f'<span class="kpi-etq">Expedientes analizados</span><b class="kpi-num">{ind.total}</b>'
        f'<small class="kpi-sub">{txt(" · ".join(sub_total) or "en total")}</small></a>'
    ]
    for r in RECS_TABLERO:
        n = ind.por_recomendacion.get(r, 0)
        tono = clase_tono(t.ESTADO[r])
        tarjetas.append(
            f'<a class="kpi kpi-{tono}{" kpi-activo" if activo == r.value else ""}" '
            f'href="{escape(url(**dict(base, rec=r.value)))}" target="_self">'
            f'<span class="kpi-etq"><i class="kpi-punto" style="background:{t.ESTADO[r].mapa}"></i>'
            f'{txt(ETIQUETA_KPI[r])}</span><b class="kpi-num est-{tono}">{n}</b>'
            f'<small class="kpi-sub est-{tono}">{_pct_entero(n, ind.total)} del total</small></a>'
        )
    return '<div class="kpis">' + "".join(tarjetas) + "</div>"


def ventana_entidad(
    clave: str, conteo: "mapa.ConteoEntidad", params: dict[str, str], parametro: str = "entidad",
) -> str:
    """Recuadro del estado en el panel junto al mapa (no encima, para no taparlo): porcentaje de
    cada recomendación y acceso a la vista del estado. `parametro` es el que se quita al cerrar."""
    if not conteo or not conteo.total:
        return ""
    filas = []
    for r in RECS_TABLERO:
        n = conteo.por_recomendacion.get(r, 0)
        p = round(100 * conteo.porcentaje(r))
        tono = clase_tono(t.ESTADO[r])
        filas.append(
            f'<div class="v-fila"><span class="v-etq"><i style="background:{t.ESTADO[r].mapa}"></i>'
            f'{txt(r.value)}</span><b class="est-{tono}">{p} %</b><small>{n}</small></div>'
            f'<div class="v-barra"><i style="width:{p}%;background:{t.ESTADO[r].mapa}"></i></div>'
        )
    plural = "expediente" if conteo.total == 1 else "expedientes"
    cerrar = url(**{k: v for k, v in params.items() if k != parametro})
    ver = url(vista="estado", entidad=clave, ej=params.get("ej"))
    predo = conteo.predominante
    return (
        f'<div class="mx-ventana" role="region" '
        f'aria-label="{escape(mapa.nombre_entidad(clave))}">'
        f'<div class="v-cab"><b>{txt(mapa.nombre_entidad(clave))}</b>'
        f'<a class="v-cerrar" href="{escape(cerrar)}" target="_self" aria-label="Cerrar">×</a></div>'
        f'<p class="v-total">{conteo.total} {plural} · predomina '
        f'<b class="est-{clase_tono(t.ESTADO[predo])}">{txt(predo.value) if predo else "-"}</b></p>'
        + "".join(filas)
        + f'<a class="v-ver" href="{escape(ver)}" target="_self">Ver expedientes del estado →</a></div>'
    )


def resumen_estado(ind: L.Indicadores, params: dict[str, str], svg: str, nombre: str, activo: Optional[str]) -> str:
    """Vista del estado: indicadores del estado (2 x 2) y su ubicación resaltada en el mapa."""
    return (
        '<div class="estado-resumen">'
        f'<div class="estado-kpis">{kpis_bandeja(ind, params, activo)}</div>'
        f'<figure class="estado-mapa"><figcaption>{txt(nombre)}</figcaption>{svg}</figure></div>'
    )


def caja_mapa_tablero(svg: str, ventana: str, sin_entidad: int) -> str:
    """Mapa en tarjeta, con leyenda arriba y el recuadro del estado en un panel a la derecha."""
    leyenda = "".join(
        f'<span><i style="background:{t.ESTADO[r].mapa}"></i>{txt(r.value)}</span>' for r in RECS_TABLERO
    ) + f'<span><i style="background:{t.MAPA_VACIO}"></i>Sin expedientes</span>'
    pie = ""
    if sin_entidad:
        pie = (
            f'<div class="sin-entidad">{sin_entidad} expediente{"s" if sin_entidad > 1 else ""} sin entidad '
            "federativa identificada: aparecen en la lista, no en el mapa.</div>"
        )
    return (
        '<div class="mapa-tarjeta"><div class="mapa-cab"><div><h3>Mapa de expedientes</h3>'
        "<p>Color: la recomendación que predomina en el estado. "
        "Haz clic en un estado para ver su información.</p></div>"
        f'<div class="leyenda">{leyenda}</div></div>'
        '<div class="mapa-cuerpo">'
        f'<div class="mapa-lienzo">{svg}</div><aside class="mapa-panel">{ventana or _panel_vacio()}</aside></div>'
        f"{pie}</div>"
    )


def _panel_vacio() -> str:
    return (
        '<div class="mx-ventana v-vacia"><div class="v-cab"><b>Selecciona un estado</b></div>'
        '<p class="v-total">Haz clic en un estado de color para ver el porcentaje de cada recomendación '
        "y entrar a sus expedientes.</p></div>"
    )


def usuario_lateral(nombre: str, rol: str) -> str:
    iniciales = "".join(p[0] for p in nombre.split()[:2]).upper()
    return (
        f'<div class="lateral-usuario"><span class="lat-avatar">{txt(iniciales)}</span>'
        f'<span><b>{txt(nombre)}</b><small>{txt(rol)}</small></span></div>'
    )


# ------------------------------------------------------------------ detalle
# Sin etiquetas tipo píldora: estado y severidad van como texto en su color, siempre con la palabra.

def _sev(sev: Optional[Severidad]) -> str:
    if sev is None or sev == Severidad.INFO:
        return '<span class="est-gris">Informativo</span>'
    return f'<b class="est-{clase_tono(t.SEVERIDAD[sev])}">{L.NOMBRE_SEVERIDAD[sev]}</b>'


def _estado(e: EstadoRegla) -> str:
    return f'<b class="est-{clase_tono(t.REGLA[e])}">{L.NOMBRE_ESTADO_REGLA[e]}</b>'


def _archivos(archivos: list[str]) -> str:
    return txt(", ".join(archivos)) if archivos else "Expediente completo"


def tarjeta_dictamen(d: Dictamen, es_ejemplo: bool, pend: Optional[tuple] = None) -> str:
    u = L.consolidar_ubicacion(d)
    tono = t.ESTADO[d.recomendacion]
    # Cada parte de la ceja se queda en una pieza: si no cabe, el corte cae entre partes.
    partes_ceja = [d.expediente_id, texto_ubicacion(u)] + (["datos de ejemplo"] if es_ejemplo else [])
    ceja = " · ".join(f'<span class="nobr">{txt(p)}</span>' for p in partes_ceja)
    n = len((pend or L.pendientes(d))[0])
    if n:
        botones = f'<a class="btn-acento" href="#resolver" target="_self">Qué resolver ({n})</a>'
    else:
        botones = '<span class="btn-nada">Sin pendientes</span>'
    botones += '<a class="btn-linea" href="#documentos" target="_self">Ver documentos</a>'
    if u.entidad:
        pie = f"{mapa.nombre_entidad(u.entidad)}" + ("" if u.confirmada else " (los documentos no coinciden)")
    elif u.valores:
        pie = " o ".join(mapa.nombre_entidad(v) for v in u.valores) + " (los documentos no coinciden)"
    else:
        pie = "Ningún documento indica la entidad federativa"
    return (
        '<section class="marco marco-dictamen" aria-labelledby="titulo-dictamen">'
        '<h2 class="marco-titulo" id="titulo-dictamen">Dictamen</h2>'
        '<div class="marco-cuerpo"><div class="marco-texto">'
        f'<p class="marco-ceja">{ceja}</p>'
        f'<p class="marco-titular"><span class="sello sello-{clase_tono(tono)}">{txt(d.recomendacion.value)}</span></p>'
        f'<p class="marco-resumen">{txt(d.resumen)}</p>'
        '<div class="marco-datos">'
        f"<span>Confianza del análisis <b>{pct(d.confianza)}</b></span>"
        f"<span>Analizado <b>{fecha(d.fecha_analisis)}</b></span>"
        f"<span>Vigencias evaluadas al <b>{fecha(d.fecha_referencia)}</b></span></div>"
        f'<div class="marco-botones">{botones}</div></div>'
        f'<figure class="marco-media" style="margin:0">{mapa.svg_detalle(u.entidad, "#FFFFFF")}'
        f"<figcaption>{txt(pie)}</figcaption></figure>"
        "</div></section>"
    )


# ---------------------------------------------------------------- bloque 2: qué hay que resolver

def tabla_inconsistencia(inc: Inconsistencia) -> str:
    """Documento, valor encontrado y cita. El valor que no coincide va en negrita y ámbar."""
    discrepan = L.valores_inconsistencia_discrepantes([v.valor for v in inc.valores])
    filas = []
    for i, v in enumerate(inc.valores):
        valor = txt(v.valor or "Sin dato")
        if i in discrepan:
            valor = f'<b class="est-ambar">{valor}</b><span class="sr"> (no coincide)</span>'
        evid = cita(v.evidencia) if v.evidencia else '<span class="fuente">Sin cita</span>'
        filas.append(
            f"<tr><td>{L.NOMBRE_TIPO_CORTO[v.tipo]}<br><span class='fuente'>{txt(v.archivo)}</span></td>"
            f"<td>{valor}</td><td>{evid}</td></tr>"
        )
    return (
        f'<table class="tabla"><thead><tr><th>Documento</th><th>{txt(L.nombre_campo(inc.campo))}</th>'
        f'<th>Cita</th></tr></thead><tbody>{"".join(filas)}</tbody></table>'
    )


def _evidencia_requisito(r: L.Requisito) -> str:
    partes = [f'<p class="ev-regla">{txt(r.descripcion)} <span class="fuente">({txt(r.id_regla)})</span></p>']
    origen = r.origen or [None] * len(r.hallazgos)
    for archivo, h in zip(origen, r.hallazgos):
        partes.append(
            f'<p><span class="fuente">{txt(archivo or "Expediente")} · {L.NOMBRE_ESTADO_REGLA[h.estado]}</span><br>'
            f"{txt(h.explicacion)}</p>"
        )
        partes.extend(cita(e) for e in h.evidencias)
    return "".join(partes)


def _evidencia(it: L.Pendiente) -> str:
    if it.requisito:
        return _evidencia_requisito(it.requisito)
    if it.inconsistencia:
        return tabla_inconsistencia(it.inconsistencia) + "".join(_evidencia_requisito(r) for r in it.relacionados)
    if it.explicacion:
        return f"<p>{txt(it.explicacion)}</p>"
    return ""


def resumen_motivos(d: Dictamen) -> str:
    """'Descartado por: uso de suelo (2) · adeudos de predial (1)' y 'En revisión por: ...'."""
    from expedientes.motivos import resumen_por_categoria

    filas = resumen_por_categoria(d)
    lineas = []
    for sev, titulo, tono in ((Severidad.BLOQUEANTE, "Descartado por", "vino"), (Severidad.REVISION, "En revisión por", "ambar")):
        partes = [f"{txt(L.MOTIVO[f.categoria])} ({f.total})" for f in filas if f.severidad == sev]
        if partes:
            lineas.append(f'<p class="motivos-resumen"><b class="est-{tono}">{titulo}:</b> {" · ".join(partes)}</p>')
    return "".join(lineas)


def lista_pendientes(d: Dictamen, pend: Optional[tuple] = None) -> str:
    items, sueltas = pend or L.pendientes(d)
    ms = L.motivos(d)
    if items:
        filas = []
        for it in items:
            evid = _evidencia(it)
            detalle = f'<details class="ev"><summary>Evidencia</summary>{evid}</details>' if evid else ""
            m = L.motivo_de_pendiente(it, ms)
            motivo = f' · <span class="est-{clase_tono(t.SEVERIDAD[m.severidad])}">{txt(m.etiqueta)}</span>' if m else ""
            filas.append(
                f'<li><p class="resolver-texto">{txt(it.texto)}</p>'
                f'<p class="resolver-meta">{_sev(it.severidad)}{motivo} · {_archivos(it.archivos)}</p>{detalle}</li>'
            )
        cuerpo = f'<ol class="resolver">{"".join(filas)}</ol>'
    else:
        cuerpo = '<p class="resolver-vacio">No hay pendientes: todos los requisitos evaluados se cumplen.</p>'
    if sueltas:
        notas = "".join(f"<li>{txt(r)}</li>" for r in sueltas)
        cuerpo += f'<div class="resolver-notas"><h3>Otras notas del dictamen</h3><ul>{notas}</ul></div>'
    return cuerpo


# ---------------------------------------------------------------- bloque 3: documentos

def _estado_documento(doc: DocumentoAnalizado) -> str:
    if L.sin_analizar(doc):
        motivo = next((h.explicacion for h in doc.hallazgos if h.id_regla == "EXP-ERROR"), "")
        return f'<p class="doc-estado"><span class="est-ambar"><b>Sin analizar:</b> {txt(motivo)}</span></p>'
    if doc.tipo == TipoDocumento.OTRO:
        return '<p class="doc-estado">No se reconoció el tipo; no se analizó.</p>'
    legible = NOMBRE_LEGIBILIDAD[doc.legibilidad]
    if doc.legibilidad != Legibilidad.BUENA:
        legible = f'<b class="est-{clase_tono(t.LEGIBILIDAD[doc.legibilidad])}">{legible}</b>'
    return (
        f'<p class="doc-estado">{legible} · tipo detectado con {pct(doc.confianza_tipo)} · '
        f"confianza {pct(doc.confianza)}</p>"
    )


def _tarjeta_documento(titulo: str, doc: DocumentoAnalizado, ver: Optional[str] = None) -> str:
    campos = "".join(
        f"<dt>{txt(L.nombre_campo(c))}</dt><dd>{txt(campo.valor or '')}</dd>" for c, campo in L.campos_clave(doc)
    )
    reglas = [h for h in doc.hallazgos if h.id_regla not in L.REGLAS_DE_PROCESO]
    conteo = L.contar_por_estado(reglas)
    pie = ""
    if reglas:
        n_no = conteo[EstadoRegla.NO_CUMPLE]
        pie = (
            f'<p class="doc-reglas">Reglas: {conteo[EstadoRegla.CUMPLE]} cumple{"n" if conteo[EstadoRegla.CUMPLE] != 1 else ""}'
            f' · {n_no} no cumple{"n" if n_no != 1 else ""} · {conteo[EstadoRegla.NO_EVALUABLE]} sin evaluar</p>'
        )
    return (
        f'<div class="doc-tarjeta"><span class="doc-titulo">{txt(titulo)}</span>'
        + (
            f'<a class="doc-archivo doc-ver" href="{escape(ver)}" target="_self">{txt(doc.archivo)}'
            '<span class="doc-ver-txt">Ver documento →</span></a>' if ver
            else f'<p class="doc-archivo">{txt(doc.archivo)}</p>'
        )
        + f"{_estado_documento(doc)}"
        + (f'<dl class="doc-campos">{campos}</dl>' if campos else "")
        + f"{pie}</div>"
    )


def documentos(d: Dictamen, enlaces: Optional[dict[str, str]] = None) -> str:
    """Una tarjeta por archivo de cada tipo requerido; una tarjeta punteada por tipo faltante; al final
    los archivos que no se reconocieron. `enlaces`: archivo -> URL de su vista, si el original existe."""
    enlaces = enlaces or {}
    faltan = set(L.faltantes(d))
    tarjetas = []
    for tr in L.documentos_por_tipo(d):
        nombre = L.NOMBRE_TIPO[tr.tipo]
        if tr.tipo in faltan:
            texto = (
                f"Falta · se recibió {', '.join(tr.archivos)}, pero el dictamen lo considera faltante "
                "(por ejemplo, ilegible)." if tr.recibido else "Falta · no se recibió ningún archivo."
            )
            tarjetas.append(
                f'<div class="doc-tarjeta doc-falta"><span class="doc-titulo">{txt(nombre)}</span>'
                f'<p class="doc-estado"><b class="est-vino">{txt(texto)}</b></p></div>'
            )
        for doc in d.documentos:
            if doc.tipo == tr.tipo:
                tarjetas.append(_tarjeta_documento(nombre, doc, enlaces.get(doc.archivo)))
    for doc in d.documentos:
        if doc.tipo == TipoDocumento.OTRO:
            tarjetas.append(_tarjeta_documento("Otro archivo", doc, enlaces.get(doc.archivo)))
    return f'<div class="docs-grid">{"".join(tarjetas)}</div>'


# ---------------------------------------------------------------- bloque 4: detalle completo

def _celda_campo(campo: Optional[Campo], difiere: bool) -> str:
    if campo is None:
        return '<td class="vacio">No encontrado</td>'
    valor = txt(campo.valor or "")
    if difiere:
        valor = f'<b class="est-ambar">{valor}</b><span class="sr"> (no coincide)</span>'
    evid = ""
    if campo.evidencia:
        evid = (
            f'<details class="ev ev-celda"><summary>p. {campo.evidencia.pagina}</summary>'
            f'<q class="cita">{txt(campo.evidencia.cita)}</q></details>'
        )
    return f"<td>{valor}{evid}</td>"


def tabla_datos(d: Dictamen) -> str:
    """Dato x documento. Se omiten las columnas de archivos sin datos (sin analizar o no reconocidos)
    y se dice arriba cuáles son."""
    con_datos = [doc for doc in d.documentos if L.campos_con_dato(doc)]
    notas = []
    for doc in d.documentos:
        if doc in con_datos:
            continue
        if L.sin_analizar(doc):
            notas.append(f"{doc.archivo} no se pudo analizar.")
        elif doc.tipo == TipoDocumento.OTRO:
            notas.append(f"{doc.archivo} no se reconoció; no tiene datos.")
        else:
            notas.append(f"{doc.archivo} no tiene datos extraídos.")
    nota = "".join(f'<p class="dc-nota">{txt(n)}</p>' for n in notas)
    filas = L.filas_datos(d, con_datos)
    if not filas:
        return nota + '<p class="dc-nota">Ningún documento tiene datos extraídos.</p>'
    cab = "".join(
        f"<th>{L.NOMBRE_TIPO_CORTO[doc.tipo]}<br><span class='fuente'>{txt(doc.archivo)}</span></th>"
        for doc in con_datos
    )
    cuerpo, hay_diferencias = [], False
    for clave, celdas in filas:
        difieren = L.valores_discrepantes(celdas) if clave in L.CAMPOS_COMPARABLES else set()
        hay_diferencias = hay_diferencias or bool(difieren)
        tds = "".join(_celda_campo(c, i in difieren) for i, c in enumerate(celdas))
        cuerpo.append(f'<tr><td class="campo">{txt(L.nombre_campo(clave))}</td>{tds}</tr>')
    leyenda = (
        '<p class="dc-nota">En <b class="est-ambar">negrita y ámbar</b>, el valor que no coincide con el de '
        "los demás documentos.</p>" if hay_diferencias else ""
    )
    return (
        f'{nota}{leyenda}<div class="tabla-scroll"><table class="tabla"><thead><tr><th>Dato</th>{cab}</tr></thead>'
        f'<tbody>{"".join(cuerpo)}</tbody></table></div>'
    )


def tabla_requisitos(reqs: list[L.Requisito]) -> str:
    if not reqs:
        return '<p class="dc-nota">El dictamen no trae reglas evaluadas.</p>'
    filas = []
    for r in reqs:
        filas.append(
            f"<tr><td>{txt(r.descripcion)}"
            f'<details class="ev ev-celda"><summary>Evidencia</summary>{_evidencia_requisito(r)}</details></td>'
            f"<td>{_estado(r.estado)}</td><td>{_sev(r.severidad)}</td><td>{_archivos(r.archivos)}</td></tr>"
        )
    return (
        '<table class="tabla"><thead><tr><th>Requisito</th><th>Estado</th><th>Severidad</th><th>Archivo</th>'
        f'</tr></thead><tbody>{"".join(filas)}</tbody></table>'
    )


def detalle_completo(d: Dictamen) -> str:
    return (
        '<h3 class="dc-titulo">Datos extraídos</h3>' + tabla_datos(d)
        + '<h3 class="dc-titulo">Todos los requisitos</h3>' + tabla_requisitos(L.consolidar_requisitos(d))
    )


# ------------------------------------------------------------------ pie de página

PAISAJE = Path(__file__).resolve().parent / "assets" / "paisaje.webp"


def paisaje() -> str:
    """Ilustración 3B al pie de cada vista. Decorativa: sin texto alternativo y oculta a lectores de pantalla."""
    return _paisaje(PAISAJE.stat().st_mtime_ns)


@lru_cache(maxsize=1)
def _paisaje(_version: int) -> str:
    """Se cachea por fecha del archivo: si cambia paisaje.webp, la app lo toma sin reiniciar."""
    datos = base64.b64encode(PAISAJE.read_bytes()).decode("ascii")
    return (
        '<div class="paisaje" aria-hidden="true">'
        f'<img src="data:image/webp;base64,{datos}" alt="" draggable="false"></div>'
    )
