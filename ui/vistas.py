"""Pantallas de Streamlit: bandeja, nuevo análisis y detalle.

El estado de navegación vive en `st.query_params` (vista, exp, entidad, rec, q, ej) para que los
enlaces del mapa y de las tarjetas, que recargan la página, conserven filtros y destino.
"""
from __future__ import annotations

import logging
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

import streamlit as st

from expedientes.schemas import Dictamen, Recomendacion

from . import componentes as C
from . import logica as L
from . import mapa, store

FILTROS = ("entidad", "rec", "q", "ej")
TIPOS_ARCHIVO = ["pdf", "png", "jpg", "jpeg", "tif", "tiff"]


def html(fragmento: str) -> None:
    st.markdown(fragmento, unsafe_allow_html=True)


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


@st.cache_data(show_spinner=False)
def _cargar_cache(huella: tuple) -> tuple[list[store.Entrada], list[store.ArchivoInvalido]]:
    return store.cargar()


def cargar() -> tuple[list[store.Entrada], list[store.ArchivoInvalido]]:
    """Relee del disco solo si cambió algún archivo (nombre, tamaño o fecha)."""
    huella = tuple(
        (str(p), p.stat().st_mtime_ns, p.stat().st_size)
        for carpeta in (store.DIR_RESULTADOS, store.DIR_EJEMPLOS)
        if carpeta.is_dir()
        for p in sorted(carpeta.glob("*.json"))
    )
    return _cargar_cache(huella)


# ------------------------------------------------------------------ barra lateral

def barra_lateral(vista: str, abierto: Optional[store.Entrada]) -> None:
    with st.sidebar:
        html(
            f'<div class="lateral-marca">{C.logo_3b()}<div><b>Revisión de expedientes</b>'
            "<small>Tiendas 3B · Expansión</small></div></div>"
        )
        html('<div class="lateral-grupo">Expedientes</div>')
        st.button(
            "Bandeja", key="nav-bandeja", on_click=ir, args=("bandeja",),
            type="primary" if vista == "bandeja" else "secondary", use_container_width=True,
        )
        st.button(
            "Nuevo análisis", key="nav-nuevo", on_click=ir, args=("nuevo",),
            type="primary" if vista == "nuevo" else "secondary", use_container_width=True,
        )
        if abierto:
            st.button(
                abierto.dictamen.expediente_id, key="nav-detalle", on_click=ir, args=("detalle", abierto.clave),
                type="primary" if vista == "detalle" else "secondary", use_container_width=True,
                help="Expediente abierto",
            )
        html(
            '<p class="lateral-nota">Revisión inicial automática. La decisión final sobre cada expediente '
            "es del equipo legal.</p>"
        )


# ------------------------------------------------------------------ bandeja

def vista_bandeja(entradas: list[store.Entrada], invalidos: list[store.ArchivoInvalido]) -> None:
    cab, buscador = st.columns([3, 2], vertical_alignment="bottom")
    with cab:
        html(C.encabezado("Bandeja de expedientes", "Lo que requiere atención aparece primero."))
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
        nombres = ", ".join(f"{i.ruta.name} ({i.motivo})" for i in invalidos)
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

class _Bitacora(logging.Handler):
    """Junta los mensajes de log del análisis para mostrarlos mientras corre."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.lineas: deque[str] = deque(maxlen=6)

    def emit(self, record: logging.LogRecord) -> None:
        self.lineas.append(record.getMessage()[:200])


def _analizar(archivos: list[tuple[str, bytes]], nombre: Optional[str]) -> store.Entrada:
    """Corre en un hilo aparte: guarda las subidas con su nombre original, analiza y persiste."""
    from expedientes.orquestador import analizar_expediente  # tarde: un agente roto no tumba la app

    with TemporaryDirectory(prefix="expediente-") as tmp:
        rutas = []
        for nombre_archivo, contenido in archivos:
            destino = Path(tmp) / Path(nombre_archivo).name
            destino.write_bytes(contenido)
            rutas.append(destino)
        dictamen = analizar_expediente(rutas, expediente_id=nombre or None)
    return store.guardar(dictamen)


def _correr_con_estado(etiqueta: str, funcion, *args):
    """Ejecuta `funcion` en un hilo y muestra tiempo transcurrido y bitácora. Devuelve (resultado, error)."""
    bitacora = _Bitacora()
    logger = logging.getLogger("expedientes")
    nivel_previo = logger.level
    logger.addHandler(bitacora)
    if logger.getEffectiveLevel() > logging.INFO:
        logger.setLevel(logging.INFO)
    inicio = time.monotonic()
    try:
        with st.status(etiqueta, expanded=True) as estado:
            reloj = st.empty()
            registro = st.empty()
            with ThreadPoolExecutor(max_workers=1) as hilo:
                futuro = hilo.submit(funcion, *args)
                while not futuro.done():
                    seg = int(time.monotonic() - inicio)
                    reloj.markdown(f"Tiempo transcurrido: **{seg // 60}:{seg % 60:02d}**")
                    lineas = list(bitacora.lineas)
                    registro.caption(
                        "\n\n".join(lineas) if lineas else
                        "Leyendo y clasificando los archivos. Una escritura larga puede tardar varios minutos."
                    )
                    time.sleep(0.5)
                error = futuro.exception()
            if error:
                estado.update(label="El análisis no terminó", state="error", expanded=False)
                return None, error
            estado.update(label="Análisis terminado", state="complete", expanded=False)
            return futuro.result(), None
    finally:
        logger.removeHandler(bitacora)
        logger.setLevel(nivel_previo)


def _mostrar_error(error: BaseException) -> None:
    logging.getLogger(__name__).error("Falló el análisis desde la UI", exc_info=error)
    if isinstance(error, NotImplementedError):
        st.error(
            "El análisis automático todavía no está disponible en esta versión: falta implementar alguno de "
            "los agentes. Mientras tanto puedes abrir el dictamen de ejemplo."
        )
    else:
        detalle = f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
        st.error(
            f"No se pudo analizar el expediente ({detalle}).\n\n"
            "Revisa que los archivos sean PDF o imágenes legibles y vuelve a intentarlo. Si el error se repite, "
            "comparte el detalle técnico con quien mantiene los agentes."
        )
    with st.expander("Detalle técnico"):
        st.code("".join(traceback.format_exception(error)), language=None)


def vista_nuevo() -> None:
    html(C.encabezado(
        "Nuevo análisis",
        "Sube los archivos de un expediente: Escritura, Predial, Alineamiento y Número Oficial, y Uso de Suelo.",
    ))
    st.write("")
    with st.form("nuevo", border=False):
        nombre = st.text_input(
            "Nombre del expediente (opcional)", max_chars=80,
            placeholder="Ej. TEPEJI-05. Si lo dejas vacío se usa la fecha y hora.",
            help="Si ya existe un expediente con ese nombre, el nuevo análisis lo reemplaza.",
        )
        archivos = st.file_uploader(
            "Archivos del expediente", type=TIPOS_ARCHIVO, accept_multiple_files=True,
            help="PDF o imagen. El sistema identifica el tipo de cada archivo; conserva el nombre original.",
        )
        enviar = st.form_submit_button("Analizar expediente", type="primary")

    if enviar:
        if not archivos:
            st.warning("Agrega al menos un archivo del expediente antes de analizar.")
        else:
            nombres = [a.name for a in archivos]
            repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
            if repetidos:
                st.warning(f"Hay archivos con el mismo nombre y solo se analizará uno de cada uno: {', '.join(repetidos)}.")
            datos = list({a.name: (a.name, a.getvalue()) for a in archivos}.values())
            plural = "archivo" if len(datos) == 1 else "archivos"
            entrada, error = _correr_con_estado(
                f"Analizando {len(datos)} {plural}", _analizar, datos, nombre.strip() or None
            )
            if error:
                _mostrar_error(error)
            else:
                ir("detalle", entrada.clave)
                st.rerun()

    html(C.seccion("Probar con el dictamen de ejemplo", "ejemplo",
                   "Corre el flujo con el dictamen de ejemplo del equipo, sin subir archivos ni llamar a los agentes."))
    if st.button("Abrir dictamen de ejemplo"):
        resultado, error = _correr_con_estado("Cargando dictamen de ejemplo", _ejemplo)
        if error:
            _mostrar_error(error)
        else:
            ir("detalle", resultado)
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
    volver, descargar = st.columns([1, 1])
    with volver:
        st.button("Volver a la bandeja", on_click=ir, args=("bandeja",))
    with descargar:
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
    tipos = [doc.tipo for doc in d.documentos]
    for doc in d.documentos:
        nombre = L.NOMBRE_TIPO_CORTO[doc.tipo]
        if tipos.count(doc.tipo) > 1:
            nombre = f"{nombre}: {doc.archivo[:28]}"
        pestañas.append((nombre, doc.hallazgos))
    etiquetas = [f"{n} ({len(h)})" for n, h in pestañas]
    for tab, (_, hallazgos) in zip(st.tabs(etiquetas), pestañas):
        with tab:
            html(C.lista_hallazgos(hallazgos))


def main() -> None:
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
