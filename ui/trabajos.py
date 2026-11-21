"""Análisis en segundo plano: un ejecutor para toda la app, bitácora por trabajo y log a consola.

Todo vive en un singleton de `st.cache_resource`, así una recarga de los módulos de la UI (Streamlit
los recarga al editar) reutiliza el mismo ejecutor, contador y handlers en vez de duplicarlos.
"""
from __future__ import annotations

import contextvars
import logging
import sys
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional

import streamlit as st

MAX_PENDIENTES = 2  # trabajos en curso o en cola en toda la app


class Bitacora(logging.Handler):
    """Copia los mensajes del logger `expedientes` a la bitácora del trabajo que los emite.

    El trabajo se identifica con una ContextVar puesta en el hilo del ejecutor. LangChain y LangGraph
    copian el contexto a sus propios hilos, así sus mensajes también llegan a la bitácora correcta.
    """

    def __init__(self, registro: contextvars.ContextVar) -> None:
        super().__init__(level=logging.INFO)
        self.registro = registro

    def emit(self, record: logging.LogRecord) -> None:
        try:
            lineas = self.registro.get()
            if lineas is not None:
                lineas.append(record.getMessage()[:200])
        except Exception:
            self.handleError(record)


@dataclass
class Motor:
    ejecutor: ThreadPoolExecutor
    registro: contextvars.ContextVar
    candado: threading.Lock = field(default_factory=threading.Lock)
    pendientes: int = 0


@st.cache_resource
def motor() -> Motor:
    registro: contextvars.ContextVar[Optional[deque]] = contextvars.ContextVar("bitacora_analisis", default=None)
    m = Motor(ThreadPoolExecutor(max_workers=1, thread_name_prefix="analisis"), registro)

    logger = logging.getLogger("expedientes")
    if logger.getEffectiveLevel() > logging.INFO:
        logger.setLevel(logging.INFO)
    # Con cualquier handler en la cadena, Python ya no usa su salida de último recurso a stderr y los
    # log.exception de los agentes se perderían; este handler los manda a la consola de Streamlit.
    consola = logging.StreamHandler(sys.stderr)
    consola.setLevel(logging.WARNING)
    consola.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    consola.set_name("ui-consola")
    bitacora = Bitacora(registro)
    bitacora.set_name("ui-bitacora")
    for h in list(logger.handlers):
        if h.get_name() in ("ui-consola", "ui-bitacora"):
            logger.removeHandler(h)
    logger.addHandler(consola)
    logger.addHandler(bitacora)
    return m


@dataclass
class Trabajo:
    futuro: Future
    inicio: float
    lineas: deque
    archivos: int

    @property
    def segundos(self) -> int:
        return int(time.monotonic() - self.inicio)


def lanzar(funcion: Callable, *args, archivos: int = 0) -> Optional[Trabajo]:
    """Encola `funcion(*args)`. Devuelve None si ya hay MAX_PENDIENTES trabajos en la app."""
    m = motor()
    with m.candado:
        if m.pendientes >= MAX_PENDIENTES:
            return None
        m.pendientes += 1
    lineas: deque = deque(maxlen=6)

    def en_hilo():
        token = m.registro.set(lineas)
        try:
            return funcion(*args)
        finally:
            m.registro.reset(token)

    try:
        futuro = m.ejecutor.submit(en_hilo)
    except BaseException:
        with m.candado:
            m.pendientes -= 1
        raise
    futuro.add_done_callback(lambda f: _terminar(m, f))
    return Trabajo(futuro, time.monotonic(), lineas, archivos)


def _terminar(m: Motor, futuro: Future) -> None:
    with m.candado:
        m.pendientes -= 1
    error = futuro.exception()
    if error is not None:
        logging.getLogger("expedientes.ui").error("Falló el análisis lanzado desde la UI", exc_info=error)
