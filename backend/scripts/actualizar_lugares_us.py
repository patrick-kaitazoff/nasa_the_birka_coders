"""Baja de GeoNames las ciudades y pueblos de los 48 estados contiguos de EE. UU. (y DC) y los guarda en
fieldshift/datos/lugares_us.json, con el mismo formato que lugares_uy.json: es lo que usa el mapa para poner nombres
al acercarse a un estado o un condado.

Fuente: GeoNames, archivo cities1000 (lugares poblados de más de 1.000 habitantes), licencia CC BY 4.0.
El tipo sale de la población, porque decide desde qué zoom aparece cada nombre (frontend/src/mapa/Lugares.ts):
city 100.000 o más, town 25.000, village 5.000, hamlet el resto. Van ordenados de más a menos habitantes: si dos
nombres se enciman en el mapa, queda el del lugar más grande.

Correr desde app/backend: .venv/Scripts/python scripts/actualizar_lugares_us.py
"""

import datetime as dt
import io
import json
import zipfile
from pathlib import Path

import httpx

URL = "https://download.geonames.org/export/dump/cities1000.zip"
FUERA = {"AK", "HI"}  # el mapa de la app muestra los 48 contiguos y DC
SALIDA = Path(__file__).resolve().parents[1] / "fieldshift" / "datos" / "lugares_us.json"


def tipo(poblacion: int) -> str:
    if poblacion >= 100_000:
        return "city"
    if poblacion >= 25_000:
        return "town"
    if poblacion >= 5_000:
        return "village"
    return "hamlet"


r = httpx.get(URL, timeout=180, follow_redirects=True)
r.raise_for_status()
texto = zipfile.ZipFile(io.BytesIO(r.content)).read("cities1000.txt").decode("utf-8")
lugares = []
for linea in texto.splitlines():
    c = linea.split("\t")
    # 1 nombre, 4 lat, 5 lon, 6 clase, 7 código, 8 país, 10 estado, 14 población
    if c[8] != "US" or c[6] != "P" or c[10] in FUERA or c[7] in ("PPLX", "PPLH", "PPLQ", "PPLW"):
        continue
    pob = int(c[14] or 0)
    if pob < 1000:
        continue
    lugares.append((pob, {"n": c[1], "t": tipo(pob), "lat": round(float(c[4]), 4), "lon": round(float(c[5]), 4)}))
lugares.sort(key=lambda x: -x[0])
SALIDA.write_text(json.dumps({"fuente": f"GeoNames (geonames.org, CC BY 4.0), cities1000 del {dt.date.today():%d/%m/%Y}",
                              "lugares": [x for _, x in lugares]}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(len(lugares), "lugares en", SALIDA, SALIDA.stat().st_size // 1024, "KB")
