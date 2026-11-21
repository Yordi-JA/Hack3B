"""Agente de ingesta y clasificación. Dueño: Julián.

Qué hace:
- Abre PDF o imagen (pymupdf abre ambos) y rasteriza cada página.
- Le pasa la imagen a un modelo con visión para transcribir el texto y, en la misma
  llamada, decir qué tipo de documento es y qué tan legible está.
- Guarda el resultado en el caché (`cache.guardar_cache`) para que nadie repita el OCR.

Datos del set:
- 57 de 62 PDFs son escaneos sin texto; 5 sí traen capa de texto (usarla y ahorrar la llamada).
- Escrituras de hasta 50 páginas / 20 MB: definir un tope de páginas y anotarlo en `notas`.
- El expediente con sufijo "..." está borroso a propósito: debe salir `Legibilidad.ILEGIBLE`
  y NO inventar texto.
- Hay un predial en .jpeg.
- Saltar todo lo que esté bajo `__MACOSX` o empiece con `._`: son metadatos de macOS, no PDFs.
- Llenar `DocumentoLeido.archivo` con `cache.nombre_archivo(ruta)` (normaliza a NFC).
- Un expediente real trae Alineamiento y Número Oficial en dos archivos distintos: ambos son
  TipoDocumento.ALINEAMIENTO.

Uso (desde la raíz del repo):

    python -m expedientes.agentes.ingesta                      # llena cache/ desde Documentos/
    python -m expedientes.agentes.ingesta --motor tesseract    # OCR local, sin API key
    python -m expedientes.agentes.ingesta --max-paginas 20 --paralelo 8

Se puede interrumpir y volver a correr: cada página leída se guarda en `cache/_paginas/`
y los documentos ya completos en `cache/` no se vuelven a procesar.

Variables del .env (opcionales): OCR_MOTOR (llm | tesseract), MAX_PAGINAS, OCR_PARALELO,
OCR_LANGFUSE (1 = mandar las trazas del OCR a Langfuse; por defecto no).
"""
from __future__ import annotations

import base64
import os
import sys
import unicodedata
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Union

import pymupdf
from pydantic import BaseModel, Field

from ..cache import guardar_cache, leer_cache, migrar_legado, nombre_archivo, ruta_paginas
from ..config import DOCUMENTOS_DIR, get_callbacks, get_llm
from ..schemas import DocumentoLeido, Legibilidad, Pagina, TipoDocumento

MOTOR = os.getenv("OCR_MOTOR", "llm")                # "llm" (visión) o "tesseract" (local)
MAX_PAGINAS = int(os.getenv("MAX_PAGINAS", "15"))    # decisión 6 del README, pendiente
PARALELO = int(os.getenv("OCR_PARALELO", "6"))       # el README pide 5-10 llamadas como máximo

EXTENSIONES = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
MIN_CARACTERES_CAPA = 80   # menos que esto en la capa de texto = página escaneada
LADO_MAX_PX = 1800         # resolución de la imagen que se manda a OCR
# Nitidez medida localmente (intensidad media de bordes). Calibrada con el set: los sintéticos
# borrosos dan 2.3-3.1 y el documento real más bajo 8.3. Por debajo del umbral la página se
# marca ILEGIBLE y se descarta el texto: un modelo con visión "lee" páginas borrosas inventando datos.
UMBRAL_NITIDEZ = float(os.getenv("UMBRAL_NITIDEZ", "5.0"))


# ---------------------------------------------------------------- lectura de una página

class _SalidaOCR(BaseModel):
    """Lo que el modelo con visión devuelve por página."""
    texto: str = Field(
        description="Transcripción literal y completa de la página, en orden de lectura. "
        "Cadena vacía si la página no se puede leer."
    )
    tipo: TipoDocumento = Field(description="Tipo de documento al que pertenece la página")
    legibilidad: Legibilidad = Field(
        description="buena: se lee todo; parcial: hay partes que no se leen; ilegible: no se puede leer"
    )


class _Lectura(_SalidaOCR):
    origen: str = Field(description="capa_texto | llm | tesseract")


PROMPT_OCR = """Eres un transcriptor de documentos legales mexicanos de inmuebles.

1. Transcribe TODO el texto visible de la imagen, literal, en orden de lectura: encabezados, \
tablas (una fila por línea, columnas separadas por " | "), sellos, firmas con nombre y notas al margen.
   - Copia nombres, direcciones, claves, folios, superficies, montos y fechas EXACTAMENTE como aparecen.
   - No corrijas, no completes, no resumas y no agregues nada que no esté en la imagen.
   - Si una palabra o cifra no se alcanza a leer, escribe [ilegible] en su lugar. Nunca la adivines.
   - Si el texto está borroso o desvanecido, NO lo reconstruyas por contexto: transcribe solo los \
caracteres que ves con certeza y marca el resto como [ilegible].
2. Clasifica la página en un tipo:
   - escritura: documento que acredita la propiedad: escritura pública o instrumento notarial, \
testimonio, título de propiedad (RAN, regularización de la tenencia, CORETT/INSUS), sentencia o \
inmatriculación judicial, con sus planos y apéndices.
   - predial: boleta, recibo, estado de cuenta o constancia de impuesto predial / catastro.
   - alineamiento_numero_oficial: constancia de alineamiento y/o asignación de número oficial.
   - uso_de_suelo: licencia, constancia, dictamen o certificado de uso de suelo / zonificación.
   - otro: cualquier otra cosa.
3. Califica la legibilidad. Si la imagen está tan borrosa que no puedes leer los datos clave, \
marca ilegible y deja el texto vacío o solo con lo que sí se lee con certeza."""


@lru_cache(maxsize=1)
def _extractor():
    llm = get_llm(effort="low", max_tokens=8000, max_retries=6)
    return llm.with_structured_output(_SalidaOCR, method="json_schema")


def _ocr_llm(jpeg: bytes) -> _SalidaOCR:
    from langchain_core.messages import HumanMessage

    b64 = base64.b64encode(jpeg).decode("ascii")
    mensaje = HumanMessage(content=[
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": PROMPT_OCR},
    ])
    # Langfuse apagado por defecto en el OCR: la traza llevaría la imagen completa del documento
    # a la nube de Langfuse (regla 06, decisión 2 del README). Se enciende con OCR_LANGFUSE=1.
    callbacks = get_callbacks() if os.getenv("OCR_LANGFUSE") == "1" else []
    return _extractor().invoke([mensaje], config={"callbacks": callbacks})


def _ocr_tesseract(jpeg: bytes) -> _SalidaOCR:
    """Respaldo local: no manda nada fuera de la máquina. Requiere `brew install tesseract tesseract-lang`
    y `pip install pytesseract`."""
    import io

    import pytesseract
    from PIL import Image

    img = Image.open(io.BytesIO(jpeg))
    datos = pytesseract.image_to_data(img, lang="spa", output_type=pytesseract.Output.DICT)
    confs = [float(c) for c, w in zip(datos["conf"], datos["text"]) if w.strip() and float(c) >= 0]
    media = sum(confs) / len(confs) if confs else 0.0
    if media >= 75:
        legibilidad = Legibilidad.BUENA
    elif media >= 45:
        legibilidad = Legibilidad.PARCIAL
    else:
        legibilidad = Legibilidad.ILEGIBLE
    texto = "" if legibilidad == Legibilidad.ILEGIBLE else pytesseract.image_to_string(img, lang="spa").strip()
    tipo, _ = clasificar_por_texto(texto)
    return _SalidaOCR(texto=texto, tipo=tipo, legibilidad=legibilidad)


def _ocr_y_guardar(ruta: Path, indice: int, jpeg: bytes, motor: str) -> _Lectura:
    salida = _ocr_tesseract(jpeg) if motor == "tesseract" else _ocr_llm(jpeg)
    lectura = _Lectura(**salida.model_dump(), origen=motor)
    _guardar_pagina(ruta, indice, motor, lectura)
    return lectura


# ---------------------------------------------------------------- clasificación por palabras clave

_PALABRAS_CLAVE = {
    TipoDocumento.PREDIAL: ["PREDIAL", "CONTRIBUYENTE", "CATASTRAL"],
    TipoDocumento.ALINEAMIENTO: ["ALINEAMIENTO", "NUMERO OFICIAL"],
    TipoDocumento.USO_SUELO: ["USO DE SUELO", "USO DEL SUELO", "ZONIFICACION"],
    TipoDocumento.ESCRITURA: ["ESCRITURA", "NOTARIO", "NOTARIA", "PROTOCOLO", "COMPRAVENTA", "DOY FE"],
}


def _normalizar(texto: str) -> str:
    sin_acentos = "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))
    return sin_acentos.upper()


def clasificar_por_texto(texto: str) -> tuple[TipoDocumento, float]:
    """Clasificación barata para páginas con capa de texto o leídas con Tesseract."""
    t = _normalizar(texto)
    puntos = {tipo: sum(t.count(p) for p in palabras) for tipo, palabras in _PALABRAS_CLAVE.items()}
    total = sum(puntos.values())
    if total == 0:
        return TipoDocumento.OTRO, 0.0
    mejor = max(puntos, key=puntos.get)
    return mejor, puntos[mejor] / total


# ---------------------------------------------------------------- checkpoints por página

def _ruta_pagina(ruta: Path, indice: int, motor: str) -> Path:
    # Por contenido (cache.ruta_paginas): un PDF distinto con el mismo nombre no reusa páginas ajenas.
    return ruta_paginas(ruta) / f"{indice + 1:04d}.{motor}.json"


def _guardar_pagina(ruta: Path, indice: int, motor: str, lectura: _Lectura) -> None:
    p = _ruta_pagina(ruta, indice, motor)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(lectura.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _leer_pagina_guardada(ruta: Path, indice: int, motor: str) -> _Lectura | None:
    p = _ruta_pagina(ruta, indice, motor)
    return _Lectura.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None


# ---------------------------------------------------------------- documento completo

_Pendiente = Union[_Lectura, Future]


def _nitidez(pagina) -> float:
    """Intensidad media de bordes en escala de grises a 1000 px. Baja = borrosa o desvanecida."""
    from PIL import Image, ImageFilter, ImageStat

    zoom = 1000 / max(pagina.rect.width, pagina.rect.height)
    pix = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    return ImageStat.Stat(img.filter(ImageFilter.FIND_EDGES)).mean[0]


def _preparar(
    ruta: Path, pool: ThreadPoolExecutor, motor: str, max_paginas: int
) -> tuple[int, list[_Pendiente], list[float | None]]:
    """Rasteriza en el hilo principal (pymupdf no es thread-safe) y manda el OCR al pool.

    Devuelve también la nitidez de cada página (None si vino de la capa de texto).
    """
    pendientes: list[_Pendiente] = []
    nitideces: list[float | None] = []
    with pymupdf.open(ruta) as doc:
        total = doc.page_count
        for i in range(min(total, max_paginas)):
            pagina = doc[i]
            guardada = _leer_pagina_guardada(ruta, i, motor)
            if guardada:
                pendientes.append(guardada)
                nitideces.append(None if guardada.origen == "capa_texto" else _nitidez(pagina))
                continue
            capa = pagina.get_text().strip()
            if len(capa) >= MIN_CARACTERES_CAPA:
                tipo, _ = clasificar_por_texto(capa)
                lectura = _Lectura(texto=capa, tipo=tipo, legibilidad=Legibilidad.BUENA, origen="capa_texto")
                _guardar_pagina(ruta, i, motor, lectura)
                pendientes.append(lectura)
                nitideces.append(None)
                continue
            nitideces.append(_nitidez(pagina))
            zoom = LADO_MAX_PX / max(pagina.rect.width, pagina.rect.height)
            jpeg = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("jpeg", jpg_quality=80)
            pendientes.append(pool.submit(_ocr_y_guardar, ruta, i, jpeg, motor))
    return total, pendientes, nitideces


def _rangos(paginas: list[int]) -> str:
    """[2, 3, 4, 7] -> 'p2-p4, p7'"""
    partes, inicio = [], None
    for k, p in enumerate(paginas):
        if inicio is None:
            inicio = p
        if k + 1 == len(paginas) or paginas[k + 1] != p + 1:
            partes.append(f"p{inicio}" if inicio == p else f"p{inicio}-p{p}")
            inicio = None
    return ", ".join(partes)


def _ensamblar(
    ruta: Path, total: int, lecturas: list[_Lectura], max_paginas: int, nitideces: list[float | None]
) -> DocumentoLeido:
    borrosas = []
    for i, n in enumerate(nitideces):
        if n is not None and n < UMBRAL_NITIDEZ:
            borrosas.append(i + 1)
            lecturas[i] = lecturas[i].model_copy(update={"texto": "", "legibilidad": Legibilidad.ILEGIBLE})

    legibles = [l for l in lecturas if l.legibilidad != Legibilidad.ILEGIBLE]
    base = legibles or lecturas
    # El tipo lo define la primera página legible (la carátula del documento); si es OTRO,
    # el voto mayoritario. Así un predial con la escritura anexa sigue siendo predial.
    primera = next((l.tipo for l in base if l.tipo != TipoDocumento.OTRO), None)
    if primera is None:
        tipo = TipoDocumento.OTRO
    elif base[0].tipo == primera:
        tipo = primera
    else:
        tipo = Counter(l.tipo for l in base if l.tipo != TipoDocumento.OTRO).most_common(1)[0][0]
    # Las páginas OTRO (planos, anexos, hojas en blanco) no cuentan ni a favor ni en contra.
    clasificadas = [l for l in base if l.tipo != TipoDocumento.OTRO] or base
    n = sum(1 for l in clasificadas if l.tipo == tipo)
    confianza = round(n / len(clasificadas), 2) if clasificadas else 0.0
    if not legibles:
        confianza = min(confianza, 0.3)  # tipo adivinado sobre páginas ilegibles

    estados = {l.legibilidad for l in lecturas}
    if estados == {Legibilidad.BUENA}:
        legibilidad = Legibilidad.BUENA
    elif estados <= {Legibilidad.ILEGIBLE}:
        legibilidad = Legibilidad.ILEGIBLE
    else:
        legibilidad = Legibilidad.PARCIAL

    notas = []
    if total > len(lecturas):
        notas.append(f"Solo se leyeron las primeras {len(lecturas)} de {total} páginas (tope MAX_PAGINAS={max_paginas}).")
    origenes = Counter(l.origen for l in lecturas)
    notas.append("Origen del texto: " + ", ".join(f"{k} {v} pág." for k, v in sorted(origenes.items())))
    if borrosas:
        notas.append(f"Páginas borrosas (nitidez < {UMBRAL_NITIDEZ}): {_rangos(borrosas)}; "
                     "se descartó su texto para no usar datos adivinados.")
    ilegibles = [i + 1 for i, l in enumerate(lecturas) if l.legibilidad == Legibilidad.ILEGIBLE]
    if ilegibles:
        notas.append(f"Páginas ilegibles: {_rangos(ilegibles)}.")
    otros_tipos: dict[TipoDocumento, list[int]] = {}
    for i, l in enumerate(lecturas):
        if l.legibilidad != Legibilidad.ILEGIBLE and l.tipo not in (tipo, TipoDocumento.OTRO):
            otros_tipos.setdefault(l.tipo, []).append(i + 1)
    for t, pags in otros_tipos.items():
        notas.append(f"Contiene páginas de tipo {t.value}: {_rangos(pags)}.")

    return DocumentoLeido(
        archivo=nombre_archivo(ruta),
        tipo=tipo,
        confianza_tipo=confianza,
        legibilidad=legibilidad,
        paginas=[Pagina(numero=i + 1, texto=l.texto) for i, l in enumerate(lecturas)],
        paginas_totales=total,
        notas=" ".join(notas),
    )


def _resolver(pendientes: list[_Pendiente]) -> list[_Lectura]:
    return [p.result() if isinstance(p, Future) else p for p in pendientes]


def leer_documento(ruta: Path) -> DocumentoLeido:
    """Lee un archivo y devuelve su texto por página, tipo y legibilidad. Usa el caché si existe."""
    ruta = Path(ruta)
    cacheado = leer_cache(ruta)
    if cacheado:
        return cacheado
    with ThreadPoolExecutor(max_workers=PARALELO) as pool:
        total, pendientes, nitideces = _preparar(ruta, pool, MOTOR, MAX_PAGINAS)
        doc = _ensamblar(ruta, total, _resolver(pendientes), MAX_PAGINAS, nitideces)
    guardar_cache(doc, ruta)
    return doc


# ---------------------------------------------------------------- caché masivo

def es_documento(ruta: Path) -> bool:
    return (
        ruta.is_file()
        and ruta.suffix.lower() in EXTENSIONES
        and "__MACOSX" not in ruta.parts
        and not ruta.name.startswith(".")
    )


def listar_documentos(carpeta: Path) -> list[Path]:
    return sorted(p for p in Path(carpeta).rglob("*") if es_documento(p))


def construir_cache(
    carpeta: Path = DOCUMENTOS_DIR,
    motor: str = MOTOR,
    max_paginas: int = MAX_PAGINAS,
    paralelo: int = PARALELO,
) -> list[str]:
    """Corre la lectura sobre todos los archivos de la carpeta y guarda el caché.

    Devuelve los archivos que fallaron (vacío si todo salió bien). Volver a correrla
    reintenta solo lo que falta.
    """
    rutas = listar_documentos(carpeta)
    migradas = migrar_legado()
    if migradas:
        print(f"{migradas} entradas del caché anterior (solo por nombre) pasaron al formato con huella.")

    por_hacer = [r for r in rutas if leer_cache(r) is None]
    print(f"{len(rutas)} documentos en {carpeta}; {len(rutas) - len(por_hacer)} ya en caché; "
          f"procesando {len(por_hacer)} con motor={motor}, tope={max_paginas} págs, paralelo={paralelo}.")

    fallidos: list[str] = []
    with ThreadPoolExecutor(max_workers=paralelo) as pool:
        trabajos = []
        for ruta in por_hacer:
            try:
                trabajos.append((ruta, *_preparar(ruta, pool, motor, max_paginas)))
            except Exception as e:  # PDF corrupto o que pymupdf no abre
                print(f"  ERROR al abrir {ruta.name}: {e}", file=sys.stderr)
                fallidos.append(nombre_archivo(ruta))

        for k, (ruta, total, pendientes, nitideces) in enumerate(trabajos, 1):
            try:
                doc = _ensamblar(ruta, total, _resolver(pendientes), max_paginas, nitideces)
            except Exception as e:
                print(f"  [{k}/{len(trabajos)}] ERROR {ruta.name}: {type(e).__name__}: {e}", file=sys.stderr)
                fallidos.append(nombre_archivo(ruta))
                continue
            guardar_cache(doc, ruta)
            print(f"  [{k}/{len(trabajos)}] {doc.archivo}: {doc.tipo.value} ({doc.confianza_tipo:.2f}), "
                  f"{doc.legibilidad.value}, {len(doc.paginas)}/{doc.paginas_totales} págs")

    if fallidos:
        print(f"\n{len(fallidos)} con error; vuelve a correr el comando para reintentarlos: {fallidos}", file=sys.stderr)
    else:
        print("\nCaché completo.")
    return fallidos


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Llena cache/ con el texto de todos los documentos.")
    ap.add_argument("carpeta", nargs="?", type=Path, default=DOCUMENTOS_DIR)
    ap.add_argument("--motor", choices=["llm", "tesseract"], default=MOTOR)
    ap.add_argument("--max-paginas", type=int, default=MAX_PAGINAS)
    ap.add_argument("--paralelo", type=int, default=PARALELO)
    a = ap.parse_args()
    sys.exit(1 if construir_cache(a.carpeta, a.motor, a.max_paginas, a.paralelo) else 0)
