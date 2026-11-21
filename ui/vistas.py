"""Pantallas de Streamlit: bandeja, nuevo análisis y detalle.

El estado de navegación vive en `st.query_params` (vista, exp, entidad, rec, q, ej) para que los
enlaces del mapa y de las tarjetas, que recargan la página, conserven filtros y destino.
"""
from __future__ import annotations

import logging
import re
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

import streamlit as st

from expedientes.schemas import Dictamen, Recomendacion

from . import componentes as C
from . import logica as L
from . import mapa, store, trabajos

FILTROS = ("entidad", "rec", "q", "ej")
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


def cargar() -> tuple[list[store.Entrada], list[store.ArchivoInvalido]]:
    """Relee del disco solo si cambió algún archivo (nombre, tamaño o fecha)."""
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
    return _cargar_cache(tuple(huella))


# ------------------------------------------------------------------ barra lateral

def barra_lateral(vista: str, abierto: Optional[store.Entrada]) -> None:
    with st.sidebar:
        html(
            f'<div class="lateral-marca">{C.logo_3b(invertido=True)}<div><b>Revisión de expedientes</b>'
            "<small>Tiendas 3B · Expansión</small></div></div>"
        )
        html('<div class="lateral-grupo">Expedientes</div>')
        st.button(
            "Bandeja", key="nav-bandeja", on_click=ir, args=("bandeja",),
            type="primary" if vista == "bandeja" else "secondary", width="stretch",
        )
        st.button(
            "Nuevo análisis", key="nav-nuevo", on_click=ir, args=("nuevo",),
            type="primary" if vista == "nuevo" else "secondary", width="stretch",
        )
        if abierto:
            st.button(
                seguro(abierto.dictamen.expediente_id) or "Expediente abierto", key="nav-detalle", on_click=ir, args=("detalle", abierto.clave),
                type="primary" if vista == "detalle" else "secondary", width="stretch",
                help="Expediente abierto",
            )
        seguimiento()
        avisos_laterales()
        html(
            '<p class="lateral-nota">Revisión inicial automática. La decisión final sobre cada expediente '
            "es del equipo legal.</p>"
        )


# ------------------------------------------------------------------ bandeja

def vista_bandeja(entradas: list[store.Entrada], invalidos: list[store.ArchivoInvalido]) -> None:
    cab, buscador = st.columns([3, 2], vertical_alignment="bottom")
    with cab:
        html(C.encabezado("Bandeja de expedientes", "Primero los que no cumplen, luego los que requieren revisión."))
    with buscador:
        _filtro("q")
        st.text_input(
            "Buscar", key="f_q", on_change=_sincronizar, args=("q",), label_visibility="collapsed",
            placeholder="Buscar por expediente, municipio, propietario o archivo",
        )

    if "f_ej" not in st.session_state:
        st.session_state["f_ej"] = st.query_params.get("ej") != "0"
    con_ejemplos = st.session_state["f_ej"]
    visibles = [e for e in entradas if con_ejemplos or not e.es_ejemplo]

    if invalidos:
        nombres = ", ".join(f"{seguro(i.ruta.name)}: {i.motivo}" for i in invalidos)
        st.warning(f"No se pudieron abrir {len(invalidos)} archivo(s) de resultados y no se muestran: {nombres}.")

    html(C.kpis(L.indicadores([(e.dictamen, e.es_ejemplo) for e in visibles])))

    if not entradas:
        st.info("Todavía no hay expedientes analizados. Sube los archivos de uno en Nuevo análisis.")
        st.button("Ir a Nuevo análisis", on_click=ir, args=("nuevo",), type="primary")
        return

    conteos = L.conteo_por_entidad(e.dictamen for e in visibles)
    sin_entidad = sum(1 for e in visibles if L.consolidar_ubicacion(e.dictamen).entidad is None)

    izq, der = st.columns([1.45, 1], gap="large")
    with izq:
        f1, f2 = st.columns([1, 1.4], vertical_alignment="bottom")
        entidad_actual = _filtro("entidad")
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
            if "f_rec" not in st.session_state:
                rec_url = st.query_params.get("rec")
                st.session_state["f_rec"] = rec_url if rec_url in {r.value for r in Recomendacion} else None
            st.segmented_control(
                "Recomendación", [r.value for r in (Recomendacion.NO_CUMPLE, Recomendacion.REQUIERE_REVISION, Recomendacion.CUMPLE)],
                key="f_rec", on_change=_sincronizar, args=("rec",),
            )
        st.toggle(
            "Incluir expedientes de ejemplo", key="f_ej", on_change=_sincronizar, args=("ej",),
            help="Los ejemplos son dictámenes inventados para probar la pantalla. Ocúltalos cuando haya resultados reales.",
        )

        rec = st.session_state.get("f_rec")
        recomendacion = Recomendacion(rec) if rec else None
        filtrados = [
            e for e in visibles
            if L.coincide(e.dictamen, st.session_state.get("f_entidad") or None, recomendacion, st.session_state.get("f_q") or "")
        ]
        filtrados.sort(key=lambda e: L.orden_bandeja(e.dictamen))

        if not visibles:
            st.info("Solo hay expedientes de ejemplo y están ocultos. Activa “Incluir expedientes de ejemplo” para verlos.")
        elif not filtrados:
            st.info("Ningún expediente coincide con los filtros.")
            st.button("Quitar filtros", on_click=_quitar_filtros)
        else:
            st.caption(f"{len(filtrados)} de {len(visibles)} expedientes")
            html(C.lista_expedientes((e.clave, e.dictamen, e.es_ejemplo) for e in filtrados))

    with der:
        seleccion = st.session_state.get("f_entidad") or None
        base = dict(params_filtros(), vista="bandeja")
        html(C.caja_mapa(mapa.svg_bandeja(conteos, seleccion, base), sin_entidad))


def _quitar_filtros() -> None:
    for nombre in ("entidad", "rec", "q"):
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
        return store.guardar(store.fijar_id(dictamen, expediente_id))


def _trabajo() -> Optional[trabajos.Trabajo]:
    return st.session_state.get("trabajo")


def _trabajo_pendiente() -> bool:
    trabajo = _trabajo()
    return bool(trabajo) and not trabajo.futuro.done()


def _estado_trabajo() -> None:
    """Estado compacto del análisis en la barra lateral. Al terminar: si el usuario sigue en Nuevo
    análisis se abre el dictamen; si está en otra pantalla, se avisa y se ofrece abrirlo."""
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
                st.session_state["aviso"] = "El análisis no terminó. Abre Nuevo análisis para ver el detalle."
        elif en_nuevo:
            ir("detalle", trabajo.futuro.result().clave)
        else:
            entrada = trabajo.futuro.result()
            st.session_state["listo"] = entrada.clave
            st.session_state["aviso"] = f"Análisis terminado: {seguro(entrada.dictamen.expediente_id)}"
        st.rerun(scope="app")
        return
    seg = trabajo.segundos
    texto = "Analizando…" if trabajo.futuro.running() else "En espera…"
    ultima = trabajo.lineas[-1] if trabajo.lineas else ""
    html(
        f'<div class="lateral-estado"><b>{texto} {seg // 60}:{seg % 60:02d}</b>'
        f"<small>{C.txt(ultima)}</small></div>"
    )


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
            "El análisis automático todavía no está disponible en esta versión: falta implementar alguno de "
            "los agentes. Mientras tanto puedes abrir el dictamen de ejemplo."
        )
    else:
        st.error(
            "No se pudo analizar el expediente. Revisa que los archivos sean PDF o imágenes legibles y vuelve "
            "a intentarlo. Si el error se repite, comparte el detalle técnico con quien mantiene los agentes."
        )
    with st.expander("Detalle técnico"):
        st.code("".join(traceback.format_exception(error)), language=None)


def _archivos_validos(archivos) -> list[tuple[str, bytes]]:
    """Prepara las subidas (ver store.preparar_subidas) y avisa lo que se dejó fuera."""
    r = store.preparar_subidas([(a.name, a.getvalue()) for a in archivos])
    if r.exceso:
        st.warning(r.exceso)
        return []
    if r.omitidos:
        st.warning(
            "Se omitieron archivos con un nombre que Windows no acepta (por ejemplo CON, NUL o con dos puntos): "
            + ", ".join(seguro(n) for n in r.omitidos) + ". Cámbiales el nombre y súbelos de nuevo."
        )
    if r.repetidos:
        st.warning(
            "Hay archivos con el mismo nombre (sin contar mayúsculas) y solo se analizará el primero: "
            + ", ".join(seguro(n) for n in r.repetidos) + "."
        )
    return r.validos


def vista_nuevo() -> None:
    html(C.encabezado(
        "Nuevo análisis",
        "Sube los archivos de un expediente: Escritura, Predial, Alineamiento y Número Oficial, y Uso de Suelo.",
    ))
    st.write("")
    pendiente = _trabajo_pendiente()
    with st.form("nuevo", border=False):
        nombre = st.text_input(
            "Nombre del expediente (opcional)", max_chars=80,
            placeholder="Ej. TEPEJI-05. Si lo dejas vacío se usa la fecha y hora.",
            help="Si ya existe un expediente con ese nombre, el nuevo análisis lo reemplaza.",
        )
        archivos = st.file_uploader(
            "Archivos del expediente", type=TIPOS_ARCHIVO, accept_multiple_files=True,
            help="PDF o imagen. No hace falta renombrarlos: el sistema reconoce el tipo de cada archivo.",
        )
        enviar = st.form_submit_button("Analizar expediente", type="primary", disabled=pendiente)

    if pendiente:
        st.info("Hay un análisis en curso; su avance se ve en la barra lateral. Puedes ir a la bandeja "
                "mientras tanto: al terminar se guarda y te avisamos.")
    if enviar and not pendiente:
        if not archivos:
            st.warning("Agrega al menos un archivo del expediente antes de analizar.")
        else:
            datos = _archivos_validos(archivos)
            if datos:
                st.session_state.pop("error_trabajo", None)
                st.session_state.pop("listo", None)
                trabajo = trabajos.lanzar(_analizar, datos, store.id_expediente(nombre), archivos=len(datos))
                if trabajo is None:
                    st.warning("Hay otro análisis en espera; intenta cuando termine.")
                else:
                    st.session_state["trabajo"] = trabajo
                    st.rerun()

    error = st.session_state.pop("error_trabajo", None)
    if error is not None:
        _mostrar_error(error)

    html(C.seccion("Probar con el dictamen de ejemplo", "ejemplo",
                   "Abre un dictamen ya generado para ver la pantalla de resultados sin subir archivos."))
    if st.button("Abrir dictamen de ejemplo"):
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
        st.button("Volver a la bandeja", on_click=ir, args=("bandeja",), type="primary")
        return

    d: Dictamen = entrada.dictamen
    with st.container(horizontal=True, horizontal_alignment="distribute"):
        st.button("Volver a la bandeja", on_click=ir, args=("bandeja",))
        st.download_button(
            "Descargar dictamen (JSON)", d.model_dump_json(indent=2), file_name=store.nombre_archivo(d.expediente_id),
            mime="application/json",
        )

    html(C.tarjeta_dictamen(d, entrada.es_ejemplo))
    html(C.razones(d))

    html(C.seccion("Documentos recibidos y faltantes", "documentos",
                   "Los 4 tipos requeridos y qué se extrajo de cada archivo."))
    html(C.tipos_recibidos(d))
    html(C.tarjetas_documentos(d))

    reqs = L.consolidar_requisitos(d)
    html(C.seccion("Requisitos cumplidos y no cumplidos", "requisitos",
                   "Un requisito se da por cumplido si algún archivo de su tipo lo cumple."))
    html(C.resumen_requisitos(reqs))
    avisos = C.avisos_sin_analizar(d)
    if avisos:
        html(avisos)
    html(C.tabla_requisitos(reqs))

    html(C.seccion("Inconsistencias entre documentos", "inconsistencias",
                   "Qué dice cada documento sobre el mismo dato y dónde está la evidencia."))
    if d.inconsistencias:
        for inc in d.inconsistencias:
            html(C.inconsistencia(inc))
    else:
        html('<p class="vacio-msg">No se encontraron diferencias entre documentos en los datos comparados.</p>')

    html(C.seccion("Datos extraídos", "datos",
                   "Cada dato tal como aparece en el documento. Abre “Evidencia” para ver la cita y la página."))
    html(C.tabla_datos(d))

    html(C.seccion("Criterios y validaciones", "criterios",
                   "Cada regla evaluada, con su explicación y la cita del documento que la sustenta."))
    pestañas = [("Expediente", d.hallazgos_expediente)]
    for doc in d.documentos:
        raiz = seguro(Path(doc.archivo).stem)
        corto = raiz if len(raiz) <= 22 else raiz[:21].rstrip() + "…"
        pestañas.append((f"{L.NOMBRE_TIPO_CORTO[doc.tipo]} · {corto}", doc.hallazgos))
    etiquetas = [f"{n} ({len(h)})" for n, h in pestañas]
    for tab, (_, hallazgos) in zip(st.tabs(etiquetas), pestañas):
        with tab:
            html(C.lista_hallazgos(hallazgos))


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
    if vista not in ("bandeja", "nuevo", "detalle"):
        vista = "bandeja"
    abierto = store.buscar(entradas, st.query_params.get("exp"))
    barra_lateral(vista, abierto)
    if vista == "nuevo":
        vista_nuevo()
    elif vista == "detalle":
        vista_detalle(abierto)
    else:
        vista_bandeja(entradas, invalidos)
