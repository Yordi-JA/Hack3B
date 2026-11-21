"""UI del revisor de expedientes (Streamlit). Dueño: Yordi.

Correr desde la raíz del repo:
    python -m streamlit run app.py
Solo consume `Dictamen` (expedientes/schemas.py) a través de `analizar_expediente`.
"""
from PIL import Image, ImageDraw, ImageFont
import streamlit as st

from ui import estilos, tokens, vistas


def _icono_3b() -> Image.Image:
    """Ícono de pestaña: círculo rojo con B sobre BB. Se dibuja en memoria porque los .png no se versionan."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(img)
    dibujo.ellipse((0, 0, 63, 63), fill=tokens.ROJO_3B)
    try:
        fuente = ImageFont.truetype("arialbd.ttf", 24)
    except OSError:
        fuente = ImageFont.load_default(size=24)
    dibujo.text((32, 20), "B", font=fuente, fill="white", anchor="mm")
    dibujo.text((32, 42), "BB", font=fuente, fill="white", anchor="mm")
    return img


st.set_page_config(
    page_title="Revisión de expedientes · Tiendas 3B", page_icon=_icono_3b(), layout="wide",
    initial_sidebar_state="expanded",
)
st.html(estilos.css())
vistas.main()
