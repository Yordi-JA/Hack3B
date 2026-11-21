"""Configuración y fábrica del LLM. Todos los agentes piden el modelo con `get_llm()`.

PENDIENTE (Carlos): confirmar proveedor y modelo. Cambiar de proveedor debe ser solo cambiar el .env.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RAIZ = Path(__file__).resolve().parent.parent
DOCUMENTOS_DIR = Path(os.getenv("DOCUMENTOS_DIR", RAIZ / "Documentos"))
CACHE_DIR = Path(os.getenv("CACHE_DIR", RAIZ / "cache"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5-5")


def get_llm(**kwargs):
    """Devuelve el chat model de LangChain configurado en el .env."""
    if LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=LLM_MODEL, **kwargs)
    if LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=LLM_MODEL, **kwargs)
    if LLM_PROVIDER == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=LLM_MODEL, **kwargs)
    raise ValueError(f"LLM_PROVIDER no soportado: {LLM_PROVIDER}")


def get_callbacks() -> list:
    """Callbacks de Langfuse si hay llaves en el .env; si no, lista vacía.

    PENDIENTE (Juan Pablo): confirmar la versión de Langfuse y su import del CallbackHandler.
    """
    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        return []
    from langfuse.langchain import CallbackHandler
    return [CallbackHandler()]
