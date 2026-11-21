"""Configura el entorno del proyecto en Windows o macOS con un solo comando.

    python configurar.py                         # entorno + .env + prueba del contrato
    python configurar.py --zips RUTA/A/DATA3B    # además descomprime los 4 zip en Documentos/

(En Windows, si `python` no existe, usar `py configurar.py`.)

Qué hace:
1. Revisa que Python sea 3.10 o más nuevo.
2. Crea `.venv/` e instala `requirements.txt` dentro.
3. Crea `.env` a partir de `.env.example` si no existe (no toca uno existente).
4. Con --zips: descomprime los zip en `Documentos/` corrigiendo los nombres con acentos.
   Algunos nombres vienen en UTF-8 sin marcarlo y el Explorador de Windows los dejaría
   como "Nu╠ümero Oficial...", que no coincide con las llaves del caché OCR.
5. Corre `pytest` para validar el contrato.

Se puede correr las veces que haga falta: lo que ya está hecho se salta.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

RAIZ = Path(__file__).resolve().parent
VENV = RAIZ / ".venv"
ES_WINDOWS = os.name == "nt"
PY_VENV = VENV / ("Scripts/python.exe" if ES_WINDOWS else "bin/python")
DOCUMENTOS = RAIZ / "Documentos"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # consola de Windows


def paso(texto: str) -> None:
    print(f"\n== {texto}")


def correr(*cmd) -> int:
    return subprocess.call([str(c) for c in cmd], cwd=RAIZ)


def revisar_python() -> None:
    paso("Python")
    v = sys.version_info
    print(f"Python {v.major}.{v.minor}.{v.micro} en {sys.executable}")
    if v < (3, 10):
        sys.exit("Se necesita Python 3.10 o más nuevo. Instálalo desde python.org y vuelve a correr esto.")


def crear_venv() -> None:
    paso("Entorno virtual .venv")
    if PY_VENV.exists():
        print("Ya existe.")
    else:
        if correr(sys.executable, "-m", "venv", VENV) != 0:
            sys.exit("No se pudo crear .venv.")
        print("Creado.")
    paso("Dependencias (requirements.txt)")
    correr(PY_VENV, "-m", "pip", "install", "-q", "--upgrade", "pip")
    if correr(PY_VENV, "-m", "pip", "install", "-q", "-r", RAIZ / "requirements.txt") != 0:
        sys.exit("Falló pip install. Revisa el mensaje de arriba.")
    print("Instaladas.")


def crear_env() -> None:
    paso("Archivo .env")
    env = RAIZ / ".env"
    if not env.exists():
        shutil.copyfile(RAIZ / ".env.example", env)
        print("Creado a partir de .env.example.")
    else:
        print("Ya existe (no se modificó).")
    valores = {}
    for linea in env.read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            k, v = linea.split("=", 1)
            valores[k.strip()] = v.split("#", 1)[0].strip().strip('"').strip("'")
    if not valores.get("ANTHROPIC_API_KEY"):
        print("FALTA: abre .env y pega la ANTHROPIC_API_KEY (te la pasa Carlos por privado).")
    else:
        print("ANTHROPIC_API_KEY presente.")


def _nombre_real(info: zipfile.ZipInfo) -> str:
    """Recupera el nombre tal como se escribió: UTF-8 aunque el zip no lo marque."""
    if info.flag_bits & 0x800:
        return info.filename
    crudo = info.filename.encode("cp437")
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        return info.filename


def descomprimir(carpeta_zips: Path) -> None:
    paso(f"Documentos desde {carpeta_zips}")
    zips = sorted(Path(carpeta_zips).glob("*.zip"))
    if not zips:
        sys.exit(f"No hay archivos .zip en {carpeta_zips}")
    destino = DOCUMENTOS.resolve()
    nuevos = existentes = 0
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for info in zf.infolist():
                nombre = _nombre_real(info)
                partes = PurePosixPath(nombre).parts
                if info.is_dir() or "__MACOSX" in partes or partes[-1].startswith("._"):
                    continue
                salida = (destino / Path(*partes)).resolve()
                if destino not in salida.parents:  # ruta sospechosa dentro del zip
                    print(f"  Se ignora: {nombre}")
                    continue
                if salida.exists():
                    existentes += 1
                    continue
                salida.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(salida, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                nuevos += 1
    print(f"{nuevos} archivos nuevos, {existentes} ya estaban.")


def revisar_datos() -> None:
    paso("Documentos y caché OCR")
    docs = [p for p in DOCUMENTOS.rglob("*") if p.is_file() and p.name != "README.md"]
    print(f"Documentos/: {len(docs)} archivos (se esperan 63).")
    if not docs:
        print("  Corre de nuevo con --zips RUTA/A/DATA3B, o copia los PDFs a Documentos/.")
    cache = RAIZ / "cache"
    jsons = list(cache.glob("*.json")) if cache.exists() else []
    print(f"cache/: {len(jsons)} documentos.")
    if not jsons:
        print("  Copia aquí la carpeta cache/ que comparte Julián (Drive/USB). No hace falta correr OCR.")


def probar() -> None:
    paso("Prueba del contrato (pytest)")
    if correr(PY_VENV, "-m", "pytest", "-q", "-p", "no:warnings") != 0:
        sys.exit("pytest falló. Revisa el mensaje de arriba.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zips", type=Path, help="Carpeta con los 4 zip del reto (ej. Desktop/DATA3B)")
    a = ap.parse_args()

    revisar_python()
    crear_venv()
    crear_env()
    if a.zips:
        descomprimir(a.zips.expanduser())
    revisar_datos()
    probar()

    activar = r".\.venv\Scripts\activate" if ES_WINDOWS else "source .venv/bin/activate"
    print(f"\nListo. En cada terminal nueva activa el entorno con:\n    {activar}")
    print("En VS Code: Ctrl/Cmd+Shift+P > 'Python: Select Interpreter' > .venv")


if __name__ == "__main__":
    main()
