"""Prueba end to end de la UI con un navegador real (Playwright).

Recorre la bandeja, abre el detalle de dos expedientes y sube los 4 PDFs de SINT-v por "Subir
expediente". Revisa que no haya errores en el navegador y cuenta las respuestas nuevas del modelo.

Requisitos (solo para esta prueba, no están en requirements.txt):
    pip install playwright && python -m playwright install chromium

Modo caché (no gasta API): con la UI corriendo y los expedientes en resultados/
    LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY= python -m streamlit run app.py --server.port 8501
    python e2e/e2e_ui.py

Modo real (OCR + agentes con la API, ~1 centavo): UI aparte con un caché vacío
    CACHE_DIR=/tmp/cache_vacio LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY= \\
        python -m streamlit run app.py --server.port 8502
    python e2e/e2e_ui.py --url http://localhost:8502 --cache /tmp/cache_vacio --solo-subir

Las capturas quedan en e2e/capturas/ (en .gitignore: muestran datos de los documentos, regla 06).
El dictamen de prueba se borra al terminar.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
NOMBRE = "E2E-UI-SINT-v"
ARCHIVOS = ["Escritura/01 Escriturav.pdf", "Predial/02 Predialv.pdf",
            "Alineamiento_y_Numero_Oficial/03 Alineamiento y Numero Oficialv.pdf",
            "Uso_de_suelo/04 Licencia de Uso de Suelov.pdf"]


def esperar(page, texto: str, timeout: int = 60000) -> None:
    page.wait_for_selector('[data-testid="stApp"]', timeout=timeout)
    page.get_by_text(texto, exact=False).first.wait_for(timeout=timeout)
    page.wait_for_timeout(1500)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8501")
    ap.add_argument("--cache", type=Path, default=RAIZ / "cache", help="carpeta de caché que usa esa UI")
    ap.add_argument("--solo-subir", action="store_true", help="no recorre bandeja ni detalles")
    a = ap.parse_args()
    capturas = RAIZ / "e2e" / "capturas"
    capturas.mkdir(parents=True, exist_ok=True)
    antes = {p.name for p in (a.cache / "analisis").rglob("*.json")} if (a.cache / "analisis").exists() else set()
    errores, r = [], {}

    with sync_playwright() as p:
        nav = p.chromium.launch(args=["--no-sandbox"])
        page = nav.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda m: errores.append(m.text[:200]) if m.type == "error" else None)
        page.on("pageerror", lambda e: errores.append(str(e)[:200]))

        if not a.solo_subir:
            page.goto(a.url)
            esperar(page, "Expedientes analizados")
            page.screenshot(path=capturas / "1_bandeja.png")
            for exp in ["SINT-v", "SINT-!!"]:
                page.goto(f"{a.url}/?vista=detalle&exp={quote('resultado:' + exp)}")
                esperar(page, exp.upper())
                page.screenshot(path=capturas / f"2_detalle_{exp.replace('!', 'X')}.png")
                t = page.inner_text("body").lower()
                r[f"detalle {exp}"] = all(k in t for k in ["no cumple", "confianza", "evidencia"])

        page.goto(f"{a.url}/?vista=nuevo")
        esperar(page, "Analizar expediente")
        page.get_by_placeholder("Ej. TEPEJI-05").fill(NOMBRE)
        page.set_input_files('input[type="file"]', [str(RAIZ / "Documentos" / c) for c in ARCHIVOS])
        page.get_by_text("02 Predialv.pdf").first.wait_for(timeout=30000)  # el cargador muestra 3 por página
        t0 = time.time()
        page.get_by_role("button", name="Analizar expediente").click()
        page.wait_for_url("**vista=detalle**", timeout=420000)
        esperar(page, NOMBRE.upper())
        r["subir: segundos"] = round(time.time() - t0, 1)
        page.screenshot(path=capturas / "3_dictamen_subido.png")
        nav.close()

    dictamen = RAIZ / "resultados" / f"{NOMBRE}.json"
    if dictamen.exists():
        d = json.loads(dictamen.read_text(encoding="utf-8"))
        r["subir: recomendación"] = d["recomendacion"]
        r["subir: otro inmueble detectado"] = any(i["id_regla"] == "CRU-INM" for i in d["inconsistencias"])
        dictamen.unlink()
    nuevas = {p.name for p in (a.cache / "analisis").rglob("*.json")} - antes if (a.cache / "analisis").exists() else set()
    r["respuestas nuevas del modelo"] = len(nuevas)
    r["errores del navegador"] = errores
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 1 if errores or not r.get("subir: otro inmueble detectado") else 0


if __name__ == "__main__":
    sys.exit(main())
