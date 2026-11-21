"""UI del revisor de expedientes (Streamlit). Dueño: Yordi.

Correr desde la raíz del repo:
    python -m streamlit run app.py
Solo consume `Dictamen` (expedientes/schemas.py) a través de `analizar_expediente`.
"""
import streamlit as st

from ui import estilos, vistas

st.set_page_config(page_title="Revisión de expedientes · Tiendas 3B", layout="wide", initial_sidebar_state="auto")
st.html(estilos.css())
vistas.main()
