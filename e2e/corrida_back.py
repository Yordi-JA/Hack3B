"""Corrida end to end del backend por el mismo camino que la UI (`analizar_expediente`).

Copia los PDFs a una carpeta temporal (como una subida real), analiza cada expediente, guarda el
dictamen en resultados/ y cuenta las llamadas a la API. Con el caché del equipo los expedientes ya
analizados no gastan; uno nuevo sí.

    LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY= python e2e/corrida_back.py
"""
import logging
import shutil
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

llamadas: list[str] = []


class _Contador(logging.Handler):
    def emit(self, r):
        if "api.anthropic.com" in r.getMessage():
            llamadas.append(r.getMessage())


logging.basicConfig(level=logging.WARNING)
for nombre in ("httpx", "anthropic._base_client"):
    lg = logging.getLogger(nombre)
    lg.setLevel(logging.DEBUG)
    lg.addHandler(_Contador())
    lg.propagate = False

from expedientes.orquestador import analizar_expediente  # noqa: E402
from expedientes.schemas import EstadoRegla, Severidad  # noqa: E402
from ui import store  # noqa: E402

D = RAIZ / "Documentos"


def sintetico(sufijo: str) -> list[Path]:
    return [D / f"Escritura/01 Escritura{sufijo}.pdf", D / f"Predial/02 Predial{sufijo}.pdf",
            D / f"Alineamiento_y_Numero_Oficial/03 Alineamiento y Numero Oficial{sufijo}.pdf",
            D / f"Uso_de_suelo/04 Licencia de Uso de Suelo{sufijo}.pdf"]


EXPEDIENTES = {
    "SINT-normal": sintetico(""), "SINT-!!": sintetico("!!"), "SINT-borroso": sintetico(".."), "SINT-v": sintetico("v"),
    "REAL-ejemplo-3": [D / "Escritura/Escritura Ejemplo 3.pdf", D / "Predial/Predial Ejemplo 3.pdf",
                      D / "Alineamiento_y_Numero_Oficial/Alineamiento Ejemplo 3.pdf",
                      D / "Uso_de_suelo/Uso de Suelo Ejemplo 3.pdf"],
    "REAL-ejemplo-1": [D / "Escritura/Escritura Ejemplo 1.pdf",
                                  D / "Predial/Predial Ejemplo 1.pdf",
                                  D / "Alineamiento_y_Numero_Oficial/Alineamiento Ejemplo 1.pdf",
                                  D / "Uso_de_suelo/Uso de Suelo Ejemplo 1.pdf"],
    "REAL-ejemplo-2": [D / "Predial/Predial Ejemplo 2.pdf",
                       D / "Alineamiento_y_Numero_Oficial/Constancia de Alineamiento Ejemplo 2.pdf",
                       D / "Alineamiento_y_Numero_Oficial/Numero Oficial Ejemplo 2.pdf",
                       D / "Uso_de_suelo/Uso de Suelo Ejemplo 2.pdf"],
}


def alertas(d) -> str:
    return ", ".join(f"{h.id_regla}{'(bloq)' if h.severidad == Severidad.BLOQUEANTE else ''}"
                     for x in d.documentos for h in x.hallazgos
                     if h.estado != EstadoRegla.CUMPLE and h.severidad != Severidad.INFO) or "-"


def main() -> int:
    fallas = 0
    for eid, rutas in EXPEDIENTES.items():
        faltan = [r for r in rutas if not r.exists()]
        if faltan:
            print(f"{eid}: faltan archivos en Documentos/: {[r.name for r in faltan]}")
            fallas += 1
            continue
        antes, t = len(llamadas), time.time()
        with tempfile.TemporaryDirectory(prefix="expediente-") as tmp:  # igual que ui/vistas._analizar
            copias = []
            for r in rutas:
                destino = Path(tmp) / r.name
                shutil.copyfile(r, destino)
                copias.append(destino)
            d = analizar_expediente(copias, expediente_id=eid)
        store.guardar(d)
        print(f"{eid:26} {d.recomendacion.value:18} conf {d.confianza:.2f} | {time.time() - t:5.1f}s | "
              f"API {len(llamadas) - antes:2} | faltan {[x.value for x in d.documentos_faltantes] or '-'}")
        print(f"{'':26} alertas: {alertas(d)} | cruces: {[i.id_regla for i in d.inconsistencias] or '-'}")

    print("\nCasos límite")
    d = analizar_expediente([], expediente_id="E2E-VACIO")
    print(f"  expediente vacío -> {d.recomendacion.value}, faltan {len(d.documentos_faltantes)} tipos")
    with tempfile.TemporaryDirectory() as tmp:
        raro = Path(tmp) / "foto.png"
        raro.write_bytes(b"no es un pdf")
        d = analizar_expediente([raro], expediente_id="E2E-RARO")
        print(f"  archivo inválido -> {d.recomendacion.value}, {[h.id_regla for x in d.documentos for h in x.hallazgos]}")
    print(f"\nLlamadas a la API: {len(llamadas)}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
