"""Pantallas de Streamlit: bandeja, nuevo análisis y detalle.

El estado de navegación vive en `st.query_params` (vista, exp, entidad, rec, q, ej) para que los
enlaces del mapa y de las tarjetas, que recargan la página, conserven filtros y destino.
"""
from __future__ import annotations

import logging
import re
import time
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

import streamlit as st

from expedientes.schemas import Dictamen, Recomendacion

from . import componentes as C
from . import logica as L
from . import archivos as A
from . import decisiones as Dec
from . import mapa, store, tour, trabajos

FILTROS = ("entidad", "rec", "est", "q", "ej", "mot")
POR_PAGINA = 25
# Usuario de la demo (no hay inicio de sesión): nombre y rol que se muestran en la barra lateral y el saludo.
USUARIO = ("Ana Martínez", "Abogada · Expansión")
TIPOS_ARCHIVO = ["pdf", "png", "jpg", "jpeg", "tif", "tiff"]


def html(fragmento: str) -> None:
    """Único punto donde entra HTML a st.markdown. Los fragmentos van en una sola línea; si alguno
    trajera saltos, se quitan aquí para que nada se interprete como Markdown (ver componentes.txt)."""
    st.markdown(re.sub(r"\s*[\r\n]+\s*", " ", fragmento), unsafe_allow_html=True)


def seguro(texto: str) -> str:
    """Texto de documentos o del usuario para etiquetas que Streamlit interpreta como Markdown
    (botones, pestañas, avisos): sin corchetes, paréntesis, !, <, > ni comillas invertidas."""
    return " ".join(re.sub(r"[\[\]()!<>`]", "", texto).split())


# ------------------------------------------------------------------ navegación y filtros

def _filtro(nombre: str, defecto: str = "") -> str:
    clave = f"f_{nombre}"
    if clave not in st.session_state:
        st.session_state[clave] = st.query_params.get(nombre, defecto)
    return st.session_state[clave] or ""


def _sincronizar(nombre: str) -> None:
    valor = st.session_state.get(f"f_{nombre}")
    if nombre == "ej":
        valor = "" if valor else "0"  # el toggle guarda bool; en la URL solo se anota cuando se ocultan
    if valor:
        st.query_params[nombre] = valor
    elif nombre in st.query_params:
        del st.query_params[nombre]
    st.query_params.pop("pag", None)  # con otro filtro, de vuelta a la primera página


def ir(vista: str, exp: Optional[str] = None) -> None:
    params = {k: st.query_params[k] for k in FILTROS if k in st.query_params}
    params["vista"] = vista
    if exp:
        params["exp"] = exp
    st.query_params.from_dict(params)


def params_filtros() -> dict[str, str]:
    return {k: st.query_params[k] for k in FILTROS if k in st.query_params}


@st.cache_data(show_spinner=False, max_entries=4)
def _cargar_cache(huella: tuple) -> tuple[list[store.Entrada], list[store.ArchivoInvalido]]:
    return store.cargar()


def _huella() -> tuple:
    """Nombre, fecha y tamaño de cada JSON: cambia si cambia algún archivo."""
    huella = []
    for carpeta in (store.DIR_RESULTADOS, store.DIR_EJEMPLOS):
        if not carpeta.is_dir():
            continue
        for ruta in sorted(carpeta.glob("*.json")):
            try:
                info = ruta.stat()
            except FileNotFoundError:  # otra sesión lo reemplazó entre el glob y el stat
                continue
            huella.append((str(ruta), info.st_mtime_ns, info.st_size))
    return tuple(huella)


def cargar() -> tuple[list[store.Entrada], list[store.ArchivoInvalido]]:
    """Relee del disco solo si cambió algún archivo (nombre, tamaño o fecha)."""
    return _cargar_cache(_huella())


@st.cache_data(show_spinner=False, max_entries=4)
def _motivos_cache(huella: tuple) -> dict[str, list[L.Motivo]]:
    return L.motivos_por_clave((e.clave, e.dictamen) for e in _cargar_cache(huella)[0])


@st.cache_data(show_spinner=False, max_entries=4)
def _posibles_cache(huella: tuple) -> dict[str, int]:
    return {e.clave: len(L.posibles_motivos_rechazo(e.dictamen)) for e in _cargar_cache(huella)[0]}


def posibles_por_clave() -> dict[str, int]:
    """Cuántos posibles motivos de rechazo tiene cada expediente, una vez por versión de los archivos."""
    return _posibles_cache(_huella())


def motivos_por_clave() -> dict[str, list[L.Motivo]]:
    """Motivos de cada expediente (L.motivos_ui), calculados una vez por versión de los archivos."""
    return _motivos_cache(_huella())


@st.cache_data(show_spinner=False, max_entries=8)
def _csv_cache(huella: tuple, claves: tuple[str, ...], categoria: str) -> bytes:
    """CSV de seguimiento de esos expedientes, en el orden de la tabla; se rehace solo si cambian los
    archivos, la lista filtrada o el filtro de motivo."""
    por_clave = {e.clave: e.dictamen for e in _cargar_cache(huella)[0]}
    motivos_de = _motivos_cache(huella)
    return L.csv_seguimiento(((por_clave[c], motivos_de[c]) for c in claves if c in por_clave), L.categoria_de(categoria))


# ------------------------------------------------------------------ barra lateral

def barra_lateral(vista: str, abierto: Optional[store.Entrada]) -> None:
    with st.sidebar:
        html(
            f'<div class="lateral-marca">{C.logo_3b(invertido=True)}'
            '<span><b>Revisión de expedientes</b><small class="lateral-sub">Tiendas 3B</small></span></div>'
        )
        html('<div class="lateral-grupo">Principal</div>')
        st.button(
            "Inicio", key="nav-bandeja", on_click=ir, args=("bandeja",), icon=":material/home:",
            type="primary" if vista in ("bandeja", "estado") else "secondary", width="stretch",
        )
        st.button(
            "Subir expediente", key="nav-nuevo", on_click=ir, args=("nuevo",), icon=":material/upload_file:",
            type="primary" if vista == "nuevo" else "secondary", width="stretch",
        )
        if abierto:
            st.button(
                seguro(abierto.dictamen.expediente_id) or "Expediente abierto", key="nav-detalle", on_click=ir, args=("detalle", abierto.clave),
                type="primary" if vista in ("detalle", "documento") else "secondary", width="stretch",
                help="Expediente abierto",
            )
        seguimiento()
        avisos_laterales()
        html(C.usuario_lateral(*USUARIO))


def _iniciar_tour() -> None:
    tour.iniciar()
    ir("bandeja")


def boton_recorrido() -> None:
    """Botón flotante con la cara del gallo 3B para abrir el recorrido guiado. Se oculta mientras el
    recorrido está activo, para no tapar sus tarjetas."""
    if tour.activo() is not None or _carga_visible():
        return
    restante = segundos_globo(st.session_state)
    if restante > 0:
        # El globo se desvanece solo al cumplirse el tiempo; con movimiento reducido solo desaparece.
        # El tiempo del servidor es por sesión de Streamlit, y cada enlace de la app recarga la página y abre
        # otra; el guion anota la primera vez en sessionStorage de la pestaña y gana el menor de los dos.
        demora = f"min({restante:.1f}s, var(--globo-restante, {restante:.1f}s))"
        st.html(
            "<style>.st-key-tour-fab-etiqueta { animation: globo-fuera var(--globo-dur, .4s) ease "
            + demora
            + " forwards; } @media (prefers-reduced-motion: reduce) "
            "{ .st-key-tour-fab-etiqueta { animation-duration: 0s; } }</style>"
        )
        with st.container(key="tour-globo-guion"):
            st.html(GUION_GLOBO, unsafe_allow_javascript=True)
    with st.container(key="tour-fab-caja", horizontal=True, vertical_alignment="center", gap="small"):
        if restante > 0:
            st.button("¿Quieres un recorrido?", key="tour-fab-etiqueta", on_click=_iniciar_tour)
        st.button("Ver recorrido guiado", key="tour-fab", on_click=_iniciar_tour)


GLOBO_SEGUNDOS = 40


def segundos_globo(estado, ahora: Optional[float] = None) -> float:
    """Segundos que le quedan al globo "¿Quieres un recorrido?" en esta sesión. La primera vez que se
    pide se anota la hora; en los reruns ya no vuelve a empezar."""
    ahora = time.time() if ahora is None else ahora
    desde = estado.setdefault("tour_globo_desde", ahora)
    return max(0.0, GLOBO_SEGUNDOS - (ahora - desde))


# Guion fijo: primera vez que esta pestaña vio el globo, en sessionStorage. Es una constante literal (sin
# f-string ni .format): no interpolar datos en tiempo de ejecución. 40000 ms = GLOBO_SEGUNDOS (hay prueba).
GUION_GLOBO = """<script>
(() => {
  const clave = "tour-globo-desde", ahora = Date.now();
  let desde = Number(sessionStorage.getItem(clave));
  if (!desde) { desde = ahora; sessionStorage.setItem(clave, String(desde)); }
  const resta = Math.max(0, 40000 - (ahora - desde));
  const raiz = document.documentElement.style;
  raiz.setProperty("--globo-restante", resta + "ms");
  if (resta === 0) raiz.setProperty("--globo-dur", "0s");
})();
</script>"""


# ------------------------------------------------------------------ bandeja

def vista_bandeja(entradas: list[store.Entrada], invalidos: list[store.ArchivoInvalido]) -> None:
    # Los filtros se leen antes de dibujar: la línea de resumen y los conteos de cada recomendación
    # aplican entidad, búsqueda y ejemplos, pero no el filtro de recomendación.
    _filtro("q")
    entidad_actual = _filtro("entidad")
    if "f_ej" not in st.session_state:
        st.session_state["f_ej"] = st.query_params.get("ej") != "0"
    if st.query_params.get("rec") and st.query_params.get("rec") not in {r.value for r in C.RECS_TABLERO}:
        st.query_params.pop("rec", None)  # p. ej. ?rec=No cumple de antes de e94a8d4: se ignora y se quita
    if "f_rec" not in st.session_state:
        rec_url = st.query_params.get("rec")
        # El sistema ya no recomienda "No cumple": un ?rec=No cumple viejo se ignora.
        st.session_state["f_rec"] = rec_url if rec_url in {r.value for r in C.RECS_TABLERO} else None
    if st.query_params.get("mot") and not L.categoria_de(st.query_params.get("mot")):
        st.query_params.pop("mot", None)  # ?mot=xyz no es una categoría: se quita en vez de arrastrarlo
    if "f_mot" not in st.session_state:
        cat_url = L.categoria_de(st.query_params.get("mot"))
        st.session_state["f_mot"] = cat_url.value if cat_url else ""
    categoria = L.categoria_de(st.session_state.get("f_mot"))
    mots = motivos_por_clave()
    visibles = [e for e in entradas if st.session_state["f_ej"] or not e.es_ejemplo]
    texto = st.session_state.get("f_q") or ""
    base = [e for e in visibles if L.coincide(e.dictamen, entidad_actual or None, None, texto)]
    ind = L.indicadores([(e.dictamen, e.es_ejemplo) for e in base])

    # Tablero: saludo y buscador, 4 indicadores, mapa en tarjeta con ventana por estado, filtros y lista.
    with st.container(key="b-cabecera"):
        html(C.encabezado(f"Hola, {USUARIO[0].split()[0]}", "Revisión inicial de expedientes de inmuebles para Tiendas 3B."))

    if invalidos:
        nombres = ", ".join(f"{seguro(i.ruta.name)}: {i.motivo}" for i in invalidos)
        st.warning(f"No se pudieron abrir {len(invalidos)} archivo(s) de resultados y no se muestran: {nombres}.")

    if not entradas:
        st.info("Todavía no hay expedientes analizados. Sube los archivos de uno en Subir expediente.")
        st.button("Ir a Subir expediente", on_click=ir, args=("nuevo",), type="primary")
        tour.mostrar(html)
        return

    historial = Dec.cargar()
    # Mapa: color por la decisión de la abogada si ya la hay; si no, por la recomendación (L.color_mapa).
    conteos = L.conteo_por_entidad(
        (e.dictamen, L.color_mapa(e.dictamen.recomendacion, Dec.estatus(historial, e.clave).value)) for e in visibles
    )
    posibles = posibles_por_clave()
    sin_entidad = sum(1 for e in visibles if L.consolidar_ubicacion(e.dictamen).entidad is None)
    enlace = dict(params_filtros(), vista="bandeja")

    with st.container(key="b-kpis"):
        html(C.kpis_bandeja(
            ind, enlace,
            posibles=sum(1 for e in base if e.dictamen.recomendacion != Recomendacion.CUMPLE and posibles.get(e.clave)),
            rechazados=sum(1 for e in base if Dec.estatus(historial, e.clave) == Dec.Estatus.RECHAZADO),
        ))

    # Elegir un estado en el mapa solo abre su recuadro (parámetro `mapa`); no filtra la lista de abajo.
    # Sus expedientes se ven en la vista del estado ("Ver expedientes del estado").
    seleccion = st.query_params.get("mapa") or None
    ventana = C.ventana_entidad(seleccion, conteos[seleccion], dict(enlace, mapa=seleccion), "mapa") if seleccion in conteos else ""
    with st.container(key="b-mapa"):
        svg = mapa.svg_bandeja(conteos, seleccion, enlace, numeros=False, parametro="mapa")
        html(C.caja_mapa_tablero(svg, ventana, sin_entidad))

    # Repositorio: buscador y filtros justo arriba de la tabla.
    est = _filtro("est")
    rec = st.session_state.get("f_rec")
    # Todos los filtros menos el de motivo: de aquí salen las opciones de "Motivo" (regla en L.opciones_motivo).
    sin_motivo = [
        e for e in base
        if (not rec or L.misma_recomendacion(e.dictamen, Recomendacion(rec)))
        and (not est or Dec.estatus(historial, e.clave).value == est)
    ]
    opciones_motivo, textos_motivo = L.opciones_motivo(((mots.get(e.clave, []), e.es_ejemplo) for e in sin_motivo), categoria)
    filtros = st.container(key="b-filtros")
    b1, f1, fm, b3 = filtros.columns([1.7, 1, 1.2, 1], vertical_alignment="bottom")
    with b1:
        st.text_input(
            "Buscar", key="f_q", on_change=_sincronizar, args=("q",),
            placeholder="Identificador, municipio, propietario o archivo", icon=":material/search:",
        )
    with fm:
        st.selectbox(
            "Motivo", opciones_motivo, key="f_mot", on_change=_sincronizar, args=("mot",),
            format_func=lambda v: textos_motivo.get(v, v),
        )
    with b3:
        st.selectbox(
            "Estatus", [""] + [e.value for e in Dec.Estatus], key="f_est", on_change=_sincronizar, args=("est",),
            format_func=lambda v: v or "Todos",
        )
    f2, f3 = filtros.columns([2, 1], vertical_alignment="bottom")
    opciones = [""] + sorted(conteos, key=mapa.nombre_entidad)
    if sin_entidad:
        opciones.append(L.SIN_ENTIDAD)
    if entidad_actual and entidad_actual not in opciones:
        opciones.append(entidad_actual)
    with f1:
        st.selectbox(
            "Entidad federativa", opciones, key="f_entidad", on_change=_sincronizar, args=("entidad",),
            format_func=lambda v: "Todas" if not v else ("Sin entidad" if v == L.SIN_ENTIDAD else mapa.nombre_entidad(v)),
        )
    with f2:
        st.segmented_control(
            "Recomendación", [r.value for r in (Recomendacion.REQUIERE_REVISION, Recomendacion.CUMPLE)],
            key="f_rec", on_change=_sincronizar, args=("rec",),
            format_func=lambda v: f"{v} {sum(1 for e in base if L.misma_recomendacion(e.dictamen, Recomendacion(v)))}",
        )
    with f3:
        st.toggle(
            "Incluir ejemplos", key="f_ej", on_change=_sincronizar, args=("ej",),
            help="Los ejemplos son dictámenes inventados para probar la pantalla. Ocúltalos cuando haya resultados reales.",
        )

    filtrados = [e for e in sin_motivo if not categoria or L.coincide(e.dictamen, categoria=categoria, ms=mots.get(e.clave))]
    filtrados.sort(key=lambda e: L.orden_bandeja(
        e.dictamen, Dec.estatus(historial, e.clave) == Dec.Estatus.SIN_REVISAR, bool(posibles.get(e.clave))))

    html('<div id="expedientes" class="ancla"></div>')
    with st.container(key="b-lista"):
        donde = f"en {mapa.nombre_entidad(entidad_actual)}" if entidad_actual and entidad_actual != L.SIN_ENTIDAD else ""
        titulo = f"Expedientes {C.txt(donde)}" if donde else "Expedientes"
        html(f'<h2 class="lista-titulo">{titulo} <small>{len(filtrados)}</small></h2>')
        if categoria:
            html(C.filtro_motivo_activo(categoria, enlace))
        if filtrados:
            st.download_button(
                "Descargar seguimiento (CSV)",
                _csv_cache(_huella(), tuple(e.clave for e in filtrados), categoria.value if categoria else ""),
                file_name="seguimiento_expedientes.csv", mime="text/csv", type="tertiary", key="b-csv",
            )
        if not visibles:
            st.info("Solo hay expedientes de ejemplo y están ocultos. Activa “Incluir ejemplos” para verlos.")
        elif not filtrados:
            st.info("Ningún expediente coincide con los filtros.")
            st.button("Quitar filtros", on_click=_quitar_filtros)
        else:
            _tabla(filtrados, historial, enlace, categoria, mots)

    tour.mostrar(html)


def _tabla(filas: list[store.Entrada], historial: dict, params: dict[str, str],
           categoria: Optional[L.Categoria] = None, motivos_de: Optional[dict[str, list[L.Motivo]]] = None) -> None:
    """Tabla paginada: aguanta miles de expedientes sin volverse una pared de tarjetas."""
    try:
        pagina = max(1, int(st.query_params.get("pag", "1")))
    except ValueError:
        pagina = 1
    paginas = max(1, -(-len(filas) // POR_PAGINA))
    pagina = min(pagina, paginas)
    tramo = filas[(pagina - 1) * POR_PAGINA: pagina * POR_PAGINA]
    html(C.tabla_expedientes(((e.clave, e.dictamen, e.es_ejemplo, Dec.estatus(historial, e.clave)) for e in tramo),
                             params, categoria, motivos_de))
    html(C.paginador(pagina, POR_PAGINA, len(filas), params))


# ------------------------------------------------------------------ vista de un estado
#
# Se llega desde "Ver expedientes del estado" en la ventana del mapa: todo lo del estado en una
# sola pantalla (indicadores, ubicación y expedientes), sin bajar por el inicio.

def vista_estado(entradas: list[store.Entrada], clave: Optional[str]) -> None:
    ej = st.query_params.get("ej") != "0"
    del_estado = [e for e in entradas if (ej or not e.es_ejemplo) and L.coincide(e.dictamen, clave or None, None, "")]
    nombre = mapa.nombre_entidad(clave) if clave else "Sin estado"

    st.button("Volver al inicio", key="estado-volver", on_click=_volver_inicio, args=(clave,), icon=":material/arrow_back:")
    html(C.encabezado(f"Expedientes en {nombre}", "Todo lo del estado en una sola vista: indicadores, ubicación y expedientes."))
    if not del_estado:
        st.info("Este estado no tiene expedientes.")
        return

    ind = L.indicadores([(e.dictamen, e.es_ejemplo) for e in del_estado])
    rec = st.query_params.get("rec")
    rec = rec if rec in {r.value for r in C.RECS_TABLERO} else None
    params = {"vista": "estado", "entidad": clave or "", "ej": st.query_params.get("ej", "")}
    conteo = L.conteo_por_entidad(e.dictamen for e in del_estado).get(clave)
    color = t_estado(conteo.predominante if conteo else None)

    with st.container(key="estado-resumen"):
        html(C.resumen_estado(ind, params, mapa.svg_detalle(clave, color), nombre, rec))

    historial = Dec.cargar()
    with st.container(key="estado-filtros"):
        b1, b2 = st.columns([2, 1], vertical_alignment="bottom")
        texto = b1.text_input(
            "Buscar en este estado", key="estado-q", placeholder="Identificador, municipio, propietario o archivo",
            icon=":material/search:",
        )
        est = b2.selectbox("Estatus", [""] + [e.value for e in Dec.Estatus], key="estado-est", format_func=lambda v: v or "Todos")
    filtrados = [
        e for e in del_estado
        if (not rec or L.misma_recomendacion(e.dictamen, Recomendacion(rec)))
        and (not est or Dec.estatus(historial, e.clave).value == est)
        and L.coincide(e.dictamen, None, None, texto or "")
    ]
    posibles = posibles_por_clave()
    filtrados.sort(key=lambda e: L.orden_bandeja(
        e.dictamen, Dec.estatus(historial, e.clave) == Dec.Estatus.SIN_REVISAR, bool(posibles.get(e.clave))))
    filtro = f" · {rec}" if rec else ""
    html(f'<h2 class="lista-titulo">Expedientes{C.txt(filtro)} <small>{len(filtrados)}</small></h2>')
    if filtrados:
        _tabla(filtrados, historial, dict(params, rec=rec or ""), motivos_de=motivos_por_clave())
    else:
        st.info("Ningún expediente de este estado coincide con la búsqueda y los filtros.")


def t_estado(rec: Optional[Recomendacion]) -> str:
    from . import tokens
    return tokens.ESTADO[rec].mapa if rec else tokens.MAPA_VACIO


def _volver_inicio(clave: Optional[str]) -> None:
    """Regresa al inicio con el estado elegido en el mapa, para que su recuadro siga abierto."""
    params = {k: st.query_params[k] for k in ("ej",) if k in st.query_params}
    params["vista"] = "bandeja"
    if clave:
        params["mapa"] = clave
    st.query_params.from_dict(params)


def _quitar_filtros() -> None:
    st.query_params.pop("pag", None)
    for nombre in ("entidad", "rec", "est", "q", "mot"):
        st.session_state[f"f_{nombre}"] = None if nombre == "rec" else ""
        st.query_params.pop(nombre, None)


# ------------------------------------------------------------------ nuevo análisis
#
# El análisis real tarda minutos. Corre en el ejecutor compartido de `trabajos` y la barra lateral
# lo consulta cada segundo con un fragmento, en cualquier pantalla. Así el usuario puede moverse
# por la app y el resultado no se pierde: el hilo guarda el dictamen aunque nadie esté mirando.

_log = logging.getLogger("expedientes.ui")


def _analizar(archivos: list[tuple[str, bytes]], expediente_id: str) -> store.Entrada:
    """Guarda las subidas con su nombre, analiza y persiste. Corre en el hilo del ejecutor."""
    from expedientes.orquestador import analizar_expediente  # tarde: un agente roto no tumba la app

    # Se guarda dentro del `with`: si Windows no puede borrar el temporal (un PDF aún abierto), el
    # dictamen ya quedó en disco.
    with TemporaryDirectory(prefix="expediente-", ignore_cleanup_errors=True) as tmp:
        rutas = []
        for nombre_archivo, contenido in archivos:
            destino = Path(tmp) / Path(nombre_archivo).name
            destino.write_bytes(contenido)
            rutas.append(destino)
        dictamen = analizar_expediente(rutas, expediente_id=expediente_id)
        entrada = store.guardar(store.fijar_id(dictamen, expediente_id))
    try:  # los originales se guardan para abrirlos desde el detalle; si falla, el dictamen ya quedó
        A.guardar_originales(entrada.dictamen.expediente_id, archivos)
    except OSError:
        _log.exception("No se pudieron guardar los archivos originales de %s", expediente_id)
    return entrada


def _trabajo() -> Optional[trabajos.Trabajo]:
    return st.session_state.get("trabajo")


def _trabajo_pendiente() -> bool:
    trabajo = _trabajo()
    return bool(trabajo) and not trabajo.futuro.done()


def _estado_trabajo() -> None:
    """Estado compacto del análisis en la barra lateral. Al terminar: si el usuario sigue en Subir
    expediente se abre el dictamen; si está en otra pantalla, se avisa y se ofrece abrirlo."""
    trabajo = _trabajo()
    if not trabajo:
        return
    if trabajo.futuro.done():
        del st.session_state["trabajo"]
        error = trabajo.futuro.exception()
        en_nuevo = st.query_params.get("vista") == "nuevo"
        if error is not None:
            st.session_state["error_trabajo"] = error
            if not en_nuevo:
                st.session_state["aviso"] = "El análisis falló. Abre Subir expediente para ver el error."
        elif en_nuevo:
            ir("detalle", trabajo.futuro.result().clave)
        else:
            entrada = trabajo.futuro.result()
            st.session_state["listo"] = entrada.clave
            st.session_state["aviso"] = f"Dictamen listo: {seguro(entrada.dictamen.expediente_id)}"
        st.rerun(scope="app")
        return
    if _carga_visible():
        return
    seg = trabajo.segundos
    corriendo = trabajo.futuro.running()
    ultima = trabajo.lineas[-1] if trabajo.lineas else ""
    html('<div class="lateral-estado">' + C.loader_3b(
        "Analizando…" if corriendo else "En espera…", f"{seg // 60}:{seg % 60:02d}", ultima,
        chico=True, en_espera=not corriendo, invertido=True) + "</div>")


CARGA_SEGUNDOS_FONDO = 90  # a partir de aquí la pantalla de carga ofrece "Seguir en segundo plano"

# Guion fijo (constante literal: no interpolar datos en tiempo de ejecución): pasa el foco a la pantalla
# de carga y, cuando aparece, al botón "Seguir en segundo plano".
GUION_CARGA = """<script>
(() => {
  const preparar = (intentos) => {
    const caja = document.querySelector(".st-key-carga");
    if (!caja) { if (intentos > 0) setTimeout(() => preparar(intentos - 1), 60); return; }
    const boton = caja.querySelector(".st-key-carga-fondo button");
    if (boton) { if (document.activeElement !== boton) boton.focus({preventScroll: true}); return; }
    const texto = caja.querySelector(".loader3b");
    if (texto && !caja.contains(document.activeElement)) texto.focus({preventScroll: true});
  };
  preparar(10);
})();
</script>"""


def _carga_visible() -> bool:
    """Hay un análisis de esta sesión en curso y no se mandó a segundo plano. Va ligado al trabajo: una
    sesión nueva (recargar la página) no tiene trabajo y no muestra una pantalla vieja."""
    trabajo = _trabajo()
    return bool(trabajo) and not trabajo.futuro.done() and st.session_state.get("carga_oculta") != id(trabajo.futuro)


def _a_segundo_plano() -> None:
    trabajo = _trabajo()
    if trabajo:
        st.session_state["carga_oculta"] = id(trabajo.futuro)


def _pantalla_carga() -> None:
    """Pantalla completa mientras corre el análisis. Al terminar no dibuja nada: el fragmento de la barra
    lateral abre el dictamen o deja el error para Subir expediente."""
    if not _carga_visible():
        return
    trabajo = _trabajo()
    seg = trabajo.segundos
    corriendo = trabajo.futuro.running()
    with st.container(key="carga"):
        html(C.loader_3b(
            "Analizando el expediente…" if corriendo else "En espera: hay otro análisis en curso",
            f"{seg // 60}:{seg % 60:02d}", trabajo.lineas[-1] if trabajo.lineas else "",
            en_espera=not corriendo, pantalla=True,
        ))
        boton = seg >= CARGA_SEGUNDOS_FONDO
        if boton:
            st.button("Seguir en segundo plano", key="carga-fondo", type="tertiary", on_click=_a_segundo_plano)
        with st.container(key=f"carga-guion-{'boton' if boton else 'caja'}"):
            st.html(GUION_CARGA, unsafe_allow_javascript=True)


def _progreso_subir() -> None:
    """Avance del análisis en Subir expediente (se refresca cada segundo mientras dura). Al terminar no
    dibuja nada: el fragmento de la barra lateral abre el dictamen o muestra el error."""
    trabajo = _trabajo()
    if not trabajo or trabajo.futuro.done() or _carga_visible():
        return
    seg = trabajo.segundos
    corriendo = trabajo.futuro.running()
    with st.container(key="subir-progreso"):
        html(C.loader_3b(
            "Analizando el expediente…" if corriendo else "En espera…", f"{seg // 60}:{seg % 60:02d}",
            trabajo.lineas[-1] if trabajo.lineas else "", en_espera=not corriendo,
        ) + '<p class="subir-progreso-nota">Puedes ir al inicio mientras tanto: el dictamen se guarda al '
            "terminar y te avisamos.</p>")


def seguimiento() -> None:
    """Solo se consulta cada segundo mientras hay un trabajo; sin trabajo no hay recargas."""
    st.fragment(_estado_trabajo, run_every=1 if _trabajo_pendiente() else None)()


def avisos_laterales() -> None:
    aviso = st.session_state.pop("aviso", None)
    if aviso:
        st.toast(aviso)
    listo = st.session_state.get("listo")
    if listo:
        st.button("Abrir dictamen", key="lat-listo", type="secondary", width="stretch",
                  on_click=_abrir_listo, args=(listo,))
    if st.session_state.get("error_trabajo") is not None and st.query_params.get("vista") != "nuevo":
        st.button("Ver el error del análisis", key="lat-error", type="secondary", width="stretch",
                  on_click=ir, args=("nuevo",))


def _abrir_listo(clave: str) -> None:
    st.session_state.pop("listo", None)
    ir("detalle", clave)


def _mostrar_error(error: BaseException) -> None:
    if isinstance(error, NotImplementedError):
        st.error(
            "El análisis automático aún no está disponible: falta conectar alguno de los agentes. "
            "Mientras tanto puedes abrir el dictamen de ejemplo."
        )
    else:
        st.error(
            "No se pudo analizar el expediente. Revisa que los archivos sean PDF o imágenes legibles e intenta "
            "de nuevo. Si vuelve a fallar, manda el detalle técnico a quien mantiene los agentes."
        )
    with st.expander("Detalle técnico"):
        st.code("".join(traceback.format_exception(error)), language=None)


def _archivos_validos(archivos) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Prepara las subidas (ver store.preparar_subidas). Devuelve (archivos válidos, avisos de lo que
    se dejó fuera); vista_nuevo decide cuándo mostrar los avisos."""
    r = store.preparar_subidas([(a.name, a.getvalue()) for a in archivos])
    avisos: list[str] = []
    if r.exceso:
        return [], [r.exceso]
    if r.omitidos:
        avisos.append(
            "Estos archivos no se analizarán porque Windows no acepta su nombre (por ejemplo CON, NUL o con "
            "dos puntos): " + ", ".join(seguro(n) for n in r.omitidos) + ". Cámbiales el nombre y vuelve a subirlos."
        )
    if r.repetidos:
        avisos.append(
            "Estos archivos repiten el nombre de otro (sin distinguir mayúsculas) y no se analizarán: "
            + ", ".join(seguro(n) for n in r.repetidos) + "."
        )
    return r.validos, avisos


# Qué revisa el sistema en cada tipo, según la sección 02 del reto (CONTEXT.md).
DOCUMENTOS_ESPERADOS = [
    ("Escritura", "Titular, dirección, superficie del terreno y datos del inmueble."),
    ("Predial", "Propietario o contribuyente, dirección, clave catastral y superficie registrada."),
    ("Alineamiento y Número Oficial", "Dirección oficial, número asignado, alineamiento, vigencia y autoridad emisora."),
    ("Uso de Suelo", "Uso autorizado, compatibilidad con uso comercial, restricciones, vigencia y autoridad emisora."),
]


def _documentos_esperados() -> str:
    filas = "".join(f"<dt>{C.txt(tipo)}</dt><dd>{C.txt(revisa)}</dd>" for tipo, revisa in DOCUMENTOS_ESPERADOS)
    return (
        '<div class="subir-esperados"><h3>Se esperan 4 documentos</h3>'
        f"<dl>{filas}</dl>"
        "<p>No hace falta renombrar los archivos: el tipo de cada documento se detecta al analizarlo.</p></div>"
    )


def vista_nuevo() -> None:
    html(C.encabezado("Subir expediente"))
    pendiente = _trabajo_pendiente()
    with st.container(key="subir"):
        izq, der = st.columns([1.5, 1], gap="large")
        with izq, st.container(key="subir-marco"):  # el título EXPEDIENTE lo pone el CSS sobre la línea
            with st.form("nuevo", border=False):
                nombre = st.text_input(
                    "Nombre del expediente (opcional)", max_chars=80, key="subir-nombre",
                    placeholder="Ej. TEPEJI-05",
                    help="Máximo 80 caracteres. Si lo dejas vacío, se usa la fecha y hora. Si ya existe un "
                         "expediente con ese nombre, se reemplaza.",
                )
                archivos = st.file_uploader(
                    "Archivos del expediente", type=TIPOS_ARCHIVO, accept_multiple_files=True,
                    key="subir-archivos",
                )
                enviar = st.form_submit_button(
                    "Analizar expediente", type="primary", disabled=pendiente, key="analizar"
                )
        with der:
            html(_documentos_esperados())

        if pendiente:
            st.fragment(_progreso_subir, run_every=1)()
        if enviar and not pendiente:
            if not archivos:
                st.warning("Agrega al menos un archivo antes de analizar.")
            else:
                datos, avisos = _archivos_validos(archivos)
                trabajo = None
                if datos:
                    st.session_state.pop("error_trabajo", None)
                    st.session_state.pop("listo", None)
                    trabajo = trabajos.lanzar(_analizar, datos, store.id_expediente(nombre), archivos=len(datos))
                    if trabajo is None:
                        st.warning("Ya hay otros análisis en curso. Intenta de nuevo cuando termine alguno.")
                if trabajo is None:
                    for aviso in avisos:
                        st.warning(aviso)
                else:
                    # Lanzar recarga la página: los avisos se guardan ligados a este análisis y se
                    # muestran mientras siga en curso; al terminar o cambiar de análisis se descartan.
                    st.session_state["trabajo"] = trabajo
                    st.session_state["avisos_subida"] = (id(trabajo.futuro), avisos)
                    st.rerun()

        guardados = st.session_state.get("avisos_subida")
        actual = _trabajo()
        if guardados and actual is not None and guardados[0] == id(actual.futuro):
            for aviso in guardados[1]:
                st.warning(aviso)
        else:
            st.session_state.pop("avisos_subida", None)
        error = st.session_state.pop("error_trabajo", None)
        if error is not None:
            _mostrar_error(error)

        with st.container(horizontal=True, vertical_alignment="center", gap="small", key="subir-ejemplo"):
            html('<span class="subir-ejemplo-texto">¿Sin archivos a mano?</span>')
            abrir = st.button("Abrir dictamen de ejemplo", type="tertiary", key="subir-abrir-ejemplo")
        if abrir:
            try:
                clave = _ejemplo()
            except Exception as e:  # el orquestador es de otro equipo: si falla, se muestra y se registra
                _log.error("No se pudo abrir el dictamen de ejemplo", exc_info=e)
                _mostrar_error(e)
            else:
                ir("detalle", clave)
                st.rerun()


def _ejemplo() -> str:
    from expedientes.orquestador import EJEMPLO, analizar_expediente

    analizar_expediente([], usar_ejemplo=True)  # valida que el orquestador lo entrega
    return f"ejemplo:{Path(EJEMPLO).stem}"


# ------------------------------------------------------------------ detalle

def vista_detalle(entrada: Optional[store.Entrada]) -> None:
    if entrada is None:
        html(C.encabezado("Expediente no encontrado"))
        st.info("No existe un expediente con esa clave. Pudo haberse borrado o renombrado el archivo de resultados.")
        st.button("Volver al inicio", on_click=ir, args=("bandeja",), type="primary")
        return

    d: Dictamen = entrada.dictamen
    st.button("Volver al inicio", on_click=ir, args=("bandeja",))

    pend = L.pendientes(d)

    # 1. El dictamen
    html(C.tarjeta_dictamen(d, entrada.es_ejemplo, pend))

    # 1b. Decisión de la abogada: estatus vigente en tarjeta y cambio con comentario obligatorio.
    seccion_decision(entrada)

    # 2. Qué hay que resolver: una sola lista, priorizada
    html(C.seccion(f"Qué hay que resolver ({len(pend[0])})", "resolver"))
    html(C.resumen_motivos(d))
    html(C.lista_pendientes(d, pend))

    # 3. Documentos recibidos y faltantes
    html(C.seccion("Documentos", "documentos"))
    enlaces = {
        doc.archivo: C.url(vista="documento", exp=entrada.clave, doc=doc.archivo)
        for doc in d.documentos if A.ubicar(d.expediente_id, doc.archivo)
    }
    html(C.documentos(d, enlaces))

    # 4. Todo lo demás, plegado
    with st.expander("Ver detalle completo", key="detalle-completo"):
        html(C.detalle_completo(d))

    st.download_button(
        "Descargar dictamen (JSON)", d.model_dump_json(indent=2), file_name=store.nombre_archivo(d.expediente_id),
        mime="application/json", type="tertiary", key="detalle-descargar",
    )


@st.cache_data(max_entries=8, show_spinner="Abriendo el documento…")
def _paginas(ruta: str, modificado: float) -> tuple[list[bytes], int]:
    return A.paginas_jpg(Path(ruta))


def vista_documento(entrada: Optional[store.Entrada], archivo: Optional[str]) -> None:
    """El archivo original, página por página, con botón para descargarlo."""
    if entrada is None:
        st.button("Volver al inicio", on_click=ir, args=("bandeja",), icon=":material/arrow_back:")
        st.info("No existe ese expediente.")
        return
    st.button(
        f"Volver a {seguro(entrada.dictamen.expediente_id)}", key="doc-volver", on_click=ir, args=("detalle", entrada.clave),
        icon=":material/arrow_back:",
    )
    ruta = A.ubicar(entrada.dictamen.expediente_id, archivo or "")
    html(C.encabezado(archivo or "Documento", f"Expediente {entrada.dictamen.expediente_id}"))
    if ruta is None:
        st.info("El archivo original no está en este equipo: solo se conservan los que se suben desde Subir expediente.")
        return
    st.download_button(
        "Descargar archivo original", ruta.read_bytes(), file_name=ruta.name, key="doc-descargar",
        icon=":material/download:",
    )
    try:
        paginas, total = _paginas(str(ruta), ruta.stat().st_mtime)
    except Exception:  # archivo dañado o formato que PyMuPDF no abre
        _log.exception("No se pudo abrir %s", ruta)
        st.error("No se pudo mostrar este archivo. Descárgalo para abrirlo en tu equipo.")
        return
    if total > len(paginas):
        st.caption(f"Se muestran las primeras {len(paginas)} de {total} páginas. Descarga el archivo para verlo completo.")
    with st.container(key="doc-paginas"):
        for i, img in enumerate(paginas, start=1):
            st.image(img, caption=f"Página {i} de {total}", width="stretch")


def seccion_decision(entrada: store.Entrada) -> None:
    historial = Dec.cargar()
    hist = historial.get(entrada.clave, [])
    html(C.seccion("Decisión", "decision", "El sistema recomienda; la decisión final la marca la abogada."))
    with st.container(key="decision"):
        html(C.tarjeta_decision(hist[-1] if hist else None))
        html(C.aviso_decision(entrada.dictamen))
        n = st.session_state.get("dec-version", 0)  # cambia tras guardar: el formulario vuelve vacío
        with st.form("form-decision", border=False):
            nuevo = st.segmented_control("Marcar como", [e.value for e in Dec.ELEGIBLES], key=f"dec-estatus-{n}")
            comentario = st.text_area(
                "Comentario (obligatorio)", key=f"dec-comentario-{n}", max_chars=Dec.LIMITE_COMENTARIO,
                placeholder="Explica el porqué: qué falta, por qué se rechaza o qué se debe revisar.",
            )
            enviado = st.form_submit_button("Guardar decisión", type="primary")
        if enviado:
            if not nuevo:
                st.error("Elige Aprobado, En revisión o Rechazado.")
            else:
                try:
                    Dec.registrar(entrada.clave, Dec.Estatus(nuevo), comentario, USUARIO[0])
                except ValueError as err:
                    st.error(str(err))
                else:
                    st.session_state["dec-version"] = n + 1
                    st.rerun()
        if len(hist) > 1:
            with st.expander(f"Historial de decisiones ({len(hist)})", key="dec-historial"):
                html(C.historial_decisiones(hist))


def host_permitido(host: Optional[str], puerto: int) -> bool:
    """Solo se atiende a quien abrió la app como localhost o 127.0.0.1 en el puerto configurado.
    Frena el DNS rebinding: una página externa que resuelve su dominio a 127.0.0.1 manda otro Host."""
    return (host or "").lower() in {f"localhost:{puerto}", f"127.0.0.1:{puerto}"}


def main() -> None:
    if not host_permitido(st.context.headers.get("Host"), int(st.get_option("server.port"))):
        st.error("Abre la app desde http://localhost o http://127.0.0.1 en este mismo equipo.")
        st.stop()
    trabajos.motor()  # deja listos el ejecutor y el log a consola desde la primera visita
    entradas, invalidos = cargar()
    vista = st.query_params.get("vista", "bandeja")
    if vista not in ("bandeja", "nuevo", "detalle", "estado", "documento"):
        vista = "bandeja"
    if vista != "bandeja" and tour.activo() is not None:
        tour.salir()  # el recorrido es del inicio: al irse a otra vista termina y vuelve el botón del gallo
    abierto = store.buscar(entradas, st.query_params.get("exp"))
    barra_lateral(vista, abierto)
    if vista == "nuevo":
        vista_nuevo()
    elif vista == "detalle":
        vista_detalle(abierto)
    elif vista == "documento":
        vista_documento(abierto, st.query_params.get("doc"))
    elif vista == "estado":
        vista_estado(entradas, st.query_params.get("entidad"))
    else:
        vista_bandeja(entradas, invalidos)
    if _trabajo_pendiente():
        st.fragment(_pantalla_carga, run_every=1)()
    boton_recorrido()  # antes del paisaje: el paisaje tiene que ser lo último para llegar al borde del panel
    st.html(C.paisaje())  # pie de todas las vistas, también los estados vacíos y "no encontrado"
