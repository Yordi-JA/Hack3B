"""Piezas de HTML para `st.markdown(..., unsafe_allow_html=True)`.

Funciones puras que devuelven texto, para poder probarlas sin Streamlit. Todo dato que viene de
los documentos pasa por `escape`. El HTML sale en una sola línea por bloque: una línea en blanco
o una sangría de 4 espacios harían que el Markdown de Streamlit lo convierta en párrafo o código.
"""
from __future__ import annotations

from html import escape
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


def etiqueta(texto: str, tono: t.Tono, borde: bool = False) -> str:
    extra = " etq-borde" if borde else ""
    return f'<span class="etq tono-{clase_tono(tono)}{extra}">{txt(texto)}</span>'


def etq_regla(e: EstadoRegla) -> str:
    return etiqueta(L.NOMBRE_ESTADO_REGLA[e], t.REGLA[e])


def etq_severidad(s: Severidad) -> str:
    return etiqueta(L.NOMBRE_SEVERIDAD[s], t.SEVERIDAD[s], borde=True)


def etq_legibilidad(leg: Legibilidad) -> str:
    return etiqueta(NOMBRE_LEGIBILIDAD[leg], t.LEGIBILIDAD[leg])




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


def saludo(nombre: str, subtitulo: str) -> str:
    return (
        f'<div class="saludo"><h1>Hola, <em class="saludo-nombre">{txt(nombre)}</em></h1>'
        f'<p>{txt(subtitulo)}</p></div>'
    )


def cabecera(titulo: str, subtitulo: str) -> str:
    """Encabezado de las demás vistas con la misma banda y tipografía del saludo del inicio."""
    return f'<div class="saludo"><h1>{txt(titulo)}</h1><p>{txt(subtitulo)}</p></div>'


def _pct_entero(parte: int, total: int) -> str:
    return f"{round(100 * parte / total)} %" if total else "0 %"


def kpis_bandeja(ind: L.Indicadores, params: dict[str, str]) -> str:
    """4 tarjetas: total y una por recomendación. Cada una filtra la bandeja al hacer clic."""
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
            f'<a class="kpi kpi-{tono}" href="{escape(url(**dict(base, rec=r.value)))}" target="_self">'
            f'<span class="kpi-etq"><i class="kpi-punto" style="background:{t.ESTADO[r].mapa}"></i>'
            f'{txt(ETIQUETA_KPI[r])}</span><b class="kpi-num est-{tono}">{n}</b>'
            f'<small class="kpi-sub est-{tono}">{_pct_entero(n, ind.total)} del total</small></a>'
        )
    return '<div class="kpis">' + "".join(tarjetas) + "</div>"


def ventana_entidad(clave: str, conteo: "mapa.ConteoEntidad", params: dict[str, str]) -> str:
    """Ventana emergente sobre el mapa: porcentaje de cada recomendación en el estado y acceso a
    sus expedientes. Se ancla al punto del estado (unidades 1000 x 630 -> porcentaje del lienzo)."""
    punto = mapa.punto_etiqueta(clave)
    if punto is None or not conteo or not conteo.total:
        return ""
    x, y = punto
    lado = "v-izq" if x > 560 else "v-der"  # la ventana se abre hacia el lado con más espacio
    top = min(max(y / 630 * 100, 22), 78)
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
    cerrar = url(**{k: v for k, v in params.items() if k != "entidad"})
    predo = conteo.predominante
    return (
        f'<div class="mx-ventana {lado}" style="left:{x / 10:.1f}%;top:{top:.1f}%" role="dialog" '
        f'aria-label="{escape(mapa.nombre_entidad(clave))}">'
        f'<div class="v-cab"><b>{txt(mapa.nombre_entidad(clave))}</b>'
        f'<a class="v-cerrar" href="{escape(cerrar)}" target="_self" aria-label="Cerrar">×</a></div>'
        f'<p class="v-total">{conteo.total} {plural} · predomina '
        f'<b class="est-{clase_tono(t.ESTADO[predo])}">{txt(predo.value) if predo else "-"}</b></p>'
        + "".join(filas)
        + '<a class="v-ver" href="#expedientes">Ver expedientes del estado ↓</a></div>'
    )


def caja_mapa_tablero(svg: str, ventana: str, sin_entidad: int) -> str:
    """Mapa en tarjeta blanca, centrado, con leyenda arriba y la ventana del estado encima."""
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
        f'<div class="mapa-lienzo">{svg}{ventana}</div>{pie}</div>'
    )


def usuario_lateral(nombre: str, rol: str) -> str:
    iniciales = "".join(p[0] for p in nombre.split()[:2]).upper()
    return (
        f'<div class="lateral-usuario"><span class="lat-avatar">{txt(iniciales)}</span>'
        f'<span><b>{txt(nombre)}</b><small>{txt(rol)}</small></span></div>'
    )


# ------------------------------------------------------------------ detalle: tarjeta del dictamen

def tarjeta_dictamen(d: Dictamen, es_ejemplo: bool) -> str:
    u = L.consolidar_ubicacion(d)
    tono = t.ESTADO[d.recomendacion]
    # Cada parte de la ceja se queda en una pieza: si no cabe, el corte cae entre partes.
    partes_ceja = [d.expediente_id, texto_ubicacion(u)] + (["datos de ejemplo"] if es_ejemplo else [])
    ceja = " · ".join(f'<span class="nobr">{txt(p)}</span>' for p in partes_ceja)
    n_inc = len(d.inconsistencias)
    reqs = L.consolidar_requisitos(d)
    no_cumplidos = sum(1 for r in reqs if r.estado == EstadoRegla.NO_CUMPLE)
    cumplidos = sum(1 for r in reqs if r.estado == EstadoRegla.CUMPLE)
    req = f"{no_cumplidos} sin cumplir" if no_cumplidos else f"{cumplidos} cumplidos"
    botones = f'<a class="btn-acento" href="#requisitos" target="_self">Ver requisitos ({req})</a>'
    if n_inc:
        botones += f'<a class="btn-linea" href="#inconsistencias" target="_self">Ver inconsistencias ({n_inc})</a>'
    else:
        botones += '<span class="btn-nada">Sin inconsistencias</span>'
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


def razones(d: Dictamen) -> str:
    if not d.razones:
        return ""
    items = "".join(f"<li>{txt(r)}</li>" for r in d.razones)
    return f'<div class="razones"><h3>Razones de la recomendación</h3><ol>{items}</ol></div>'


# ------------------------------------------------------------------ detalle: documentos

def tipos_recibidos(d: Dictamen) -> str:
    faltan = set(L.faltantes(d))
    celdas = []
    for tr in L.documentos_por_tipo(d):
        archivos = "".join(f"<small>{txt(a)}</small>" for a in tr.archivos)
        nombre = L.NOMBRE_TIPO[tr.tipo]
        if tr.tipo in faltan and tr.recibido:
            celdas.append(
                f'<div class="tipo tipo-falta">{etiqueta("Falta", t.VINO)}<b>{nombre}</b>'
                f"<small>Se recibió {txt(', '.join(tr.archivos))} pero el dictamen lo considera faltante "
                "(por ejemplo, ilegible).</small></div>"
            )
        elif tr.tipo in faltan:
            celdas.append(
                f'<div class="tipo tipo-falta">{etiqueta("Falta", t.VINO)}<b>{nombre}</b>'
                "<small>No se recibió ningún archivo de este tipo.</small></div>"
            )
        elif L.tipo_sin_analizar(d, tr.tipo):
            celdas.append(f'<div class="tipo">{etiqueta("Recibido, sin analizar", t.AMBAR)}<b>{nombre}</b>{archivos}</div>')
        else:
            celdas.append(f'<div class="tipo">{etiqueta("Recibido", t.VERDE)}<b>{nombre}</b>{archivos}</div>')
    otros = [doc for doc in d.documentos if doc.tipo == TipoDocumento.OTRO]
    for doc in otros:
        celdas.append(
            f'<div class="tipo">{etiqueta("No reconocido", t.GRIS)}<b>Otro documento</b>'
            f"<small>{txt(doc.archivo)}</small></div>"
        )
    return f'<div class="tipos">{"".join(celdas)}</div>'


def tarjeta_documento(doc: DocumentoAnalizado) -> str:
    titulo = L.NOMBRE_TIPO_CORTO[doc.tipo] if doc.tipo != TipoDocumento.OTRO else "Otro"
    if L.sin_analizar(doc):
        etiquetas = etq_legibilidad(doc.legibilidad) + etiqueta("Sin analizar", t.AMBAR)
    else:
        etiquetas = (
            etq_legibilidad(doc.legibilidad)
            + etiqueta(f"Tipo detectado con {pct(doc.confianza_tipo)}", t.GRIS)
            + etiqueta(f"Confianza {pct(doc.confianza)}", t.GRIS)
        )
    avisos = "".join(f'<div class="doc-aviso">{txt(h.explicacion)}</div>' for h in L.avisos_de_proceso(doc))
    if doc.legibilidad == Legibilidad.ILEGIBLE and not avisos:
        avisos = '<div class="doc-aviso">El archivo es ilegible: sus reglas quedan sin evaluar. Pide una copia legible.</div>'
    campos = L.campos_clave(doc)
    lista = "".join(f"<dt>{txt(L.nombre_campo(c))}</dt><dd>{txt(campo.valor or '')}</dd>" for c, campo in campos)
    datos = f'<dl class="doc-campos">{lista}</dl>' if lista else ""
    reglas = [h for h in doc.hallazgos if h.id_regla not in L.REGLAS_DE_PROCESO]
    conteo = L.contar_por_estado(reglas)
    if reglas:
        partes = [f"<b>{conteo[e]}</b> {L.NOMBRE_ESTADO_REGLA[e].lower()}" for e in EstadoRegla]
        pie = f'<div class="doc-conteo">Reglas revisadas: {" · ".join(partes)}</div>'
    else:
        pie = '<div class="doc-conteo">Sin reglas evaluadas en este archivo.</div>'
    return (
        f'<section class="marco"><h3 class="marco-titulo">{txt(titulo)}</h3>'
        f'<p class="doc-archivo">{txt(doc.archivo)}</p>'
        f'<div class="doc-etiquetas">{etiquetas}</div>{avisos}{datos}{pie}</section>'
    )


def tarjetas_documentos(d: Dictamen) -> str:
    if not d.documentos:
        return '<p class="vacio-msg">El dictamen no trae documentos.</p>'
    return f'<div class="docs">{"".join(tarjeta_documento(doc) for doc in d.documentos)}</div>'


# ------------------------------------------------------------------ detalle: tablas

def _celda_campo(campo: Optional[Campo], difiere: bool, sin_analizar: bool = False) -> str:
    if campo is None:
        return f'<td class="vacio">{"Sin analizar" if sin_analizar else "No encontrado"}</td>'
    marca = " " + etiqueta("Difiere", t.AMBAR) if difiere else ""
    evid = ""
    if campo.evidencia:
        evid = (
            f"<details><summary>Evidencia, página {campo.evidencia.pagina}</summary>"
            f'<q class="cita">{txt(campo.evidencia.cita)}</q></details>'
        )
    clase = ' class="difiere"' if difiere else ""
    return f"<td{clase}>{txt(campo.valor or '')}{marca}{evid}</td>"


def tabla_datos(d: Dictamen) -> str:
    filas = L.filas_datos(d)
    if not filas:
        return '<p class="vacio-msg">Ningún documento tiene datos extraídos.</p>'
    cab = "".join(
        f"<th>{L.NOMBRE_TIPO_CORTO[doc.tipo]}<br><span style='font-weight:400'>{txt(doc.archivo)}</span></th>"
        for doc in d.documentos
    )
    sin = [L.sin_analizar(doc) for doc in d.documentos]
    cuerpo = []
    for clave, celdas in filas:
        difieren = L.valores_discrepantes(celdas) if clave in L.CAMPOS_COMPARABLES else set()
        tds = "".join(_celda_campo(c, i in difieren, sin[i]) for i, c in enumerate(celdas))
        cuerpo.append(f'<tr><td class="campo">{txt(L.nombre_campo(clave))}</td>{tds}</tr>')
    return (
        f'<div class="tabla-caja"><table class="tabla"><thead><tr><th>Dato</th>{cab}</tr></thead>'
        f'<tbody>{"".join(cuerpo)}</tbody></table></div>'
    )


def avisos_sin_analizar(d: Dictamen) -> str:
    avisos = []
    for doc in L.archivos_sin_analizar(d):
        if doc.tipo == TipoDocumento.OTRO:  # no es un tipo requerido: no deja requisitos incompletos
            continue
        tipo = L.NOMBRE_TIPO[doc.tipo]
        avisos.append(
            f'<div class="aviso-req">{etiqueta("Sin analizar", t.AMBAR)} {txt(doc.archivo)} ({tipo}) no se pudo '
            f"analizar; los requisitos de {tipo} pueden estar incompletos.</div>"
        )
    return "".join(avisos)


def tabla_requisitos(reqs: list[L.Requisito]) -> str:
    if not reqs:
        return '<p class="vacio-msg">El dictamen no trae reglas evaluadas.</p>'
    filas = []
    for r in reqs:
        archivos = ", ".join(r.archivos) if r.archivos else "Expediente completo"
        filas.append(
            f"<tr><td>{etq_regla(r.estado)}</td><td><b>{txt(r.descripcion)}</b><br>"
            f'<span class="fuente">{txt(r.id_regla)}</span></td>'
            f"<td>{etq_severidad(r.severidad)}</td><td>{txt(archivos)}</td></tr>"
        )
    return (
        '<div class="tabla-caja"><table class="tabla"><thead><tr><th>Estado</th><th>Requisito</th>'
        f'<th>Severidad</th><th>Dónde se evaluó</th></tr></thead><tbody>{"".join(filas)}</tbody></table></div>'
    )


def resumen_requisitos(reqs: list[L.Requisito]) -> str:
    por_estado = {e: sum(1 for r in reqs if r.estado == e) for e in EstadoRegla}
    partes = [
        etiqueta(f"{por_estado[EstadoRegla.CUMPLE]} cumplidos", t.VERDE),
        etiqueta(f"{por_estado[EstadoRegla.NO_CUMPLE]} no cumplidos", t.VINO),
        etiqueta(f"{por_estado[EstadoRegla.NO_EVALUABLE]} sin evaluar", t.AZUL),
    ]
    return f'<div class="resumen-req">{"".join(partes)}</div>'


def hallazgo(h: Hallazgo) -> str:
    evid = "".join(cita(e) for e in h.evidencias)
    if not evid:
        evid = '<span class="fuente">Sin cita en el documento.</span>'
    return (
        f'<div class="hallazgo"><div class="hallazgo-cab">{etq_regla(h.estado)}{etq_severidad(h.severidad)}'
        f'<b>{txt(h.descripcion)}</b><span class="hallazgo-id">{txt(h.id_regla)}</span></div>'
        f"<p>{txt(h.explicacion)}</p>{evid}</div>"
    )


def lista_hallazgos(hallazgos: list[Hallazgo]) -> str:
    if not hallazgos:
        return '<p class="vacio-msg">Sin hallazgos para este archivo.</p>'
    return "".join(hallazgo(h) for h in hallazgos)


def inconsistencia(inc: Inconsistencia) -> str:
    discrepan = L.valores_inconsistencia_discrepantes([v.valor for v in inc.valores])
    filas = []
    for i, v in enumerate(inc.valores):
        marca = " " + etiqueta("Difiere", t.AMBAR) if i in discrepan else ""
        evid = cita(v.evidencia) if v.evidencia else '<span class="fuente">Sin evidencia</span>'
        clase = ' class="difiere"' if i in discrepan else ""
        filas.append(
            f"<tr><td><b>{L.NOMBRE_TIPO_CORTO[v.tipo]}</b><br><span class='fuente'>{txt(v.archivo)}</span></td>"
            f"<td{clase}>{txt(v.valor or 'Sin dato')}{marca}</td><td>{evid}</td></tr>"
        )
    return (
        f'<div class="inc"><div class="hallazgo-cab">{etq_severidad(inc.severidad)}'
        f'<b>{txt(L.nombre_campo(inc.campo))}</b><span class="hallazgo-id">{txt(inc.id_regla)}</span></div>'
        f"<p>{txt(inc.descripcion)}</p>"
        '<div class="tabla-caja"><table class="tabla"><thead><tr><th>Documento</th><th>Valor encontrado</th>'
        f'<th>Evidencia</th></tr></thead><tbody>{"".join(filas)}</tbody></table></div></div>'
    )
