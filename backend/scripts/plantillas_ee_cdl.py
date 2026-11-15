"""Arma las expresiones de Earth Engine del Cropland Data Layer ya serializadas, para mandarlas por la API
REST sin la librería `earthengine-api`, que en Vercel no está (suma 107 MB; ver 10-ideas-y-decisiones.md, «Camino
(a)»). Mismo método que GLDAS y HLS: la expresión se arma una vez acá con la librería y la app solo cambia la
geometría (`fuentes/cdl.py`, `_con_geometria`).

- `cdl_por_anio.json`: histograma de clases del CDL por año dentro de una geometría (polígono del lote).
- `cdl_lote.json`: en un punto, los píxeles contiguos con la misma secuencia de los últimos tres años en 1,5 km
  alrededor, como polígonos; la secuencia y el último año van en las propiedades de la colección.

Correr desde app/backend (con la PC autorizada en Earth Engine): .venv/Scripts/python scripts/plantillas_ee_cdl.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import ee  # noqa: E402
from ee import serializer  # noqa: E402

from fieldshift.fuentes import gldas  # noqa: E402

SALIDA = RAIZ / "fieldshift" / "datos" / "plantillas_ee"
# geometrías de relleno: la app reemplaza el nodo GeometryConstructors.* entero
POLIGONO = [[[-90.1, 40.1], [-90.2, 40.1], [-90.2, 40.2], [-90.1, 40.2], [-90.1, 40.1]]]
PUNTO = [-90.15, 40.15]


def por_anio():
    geom = ee.Geometry.Polygon(POLIGONO)
    col = ee.ImageCollection("USDA/NASS/CDL").filterDate("2008-01-01", "2100-01-01").select("cropland")

    def hist(img):
        h = img.reduceRegion(ee.Reducer.frequencyHistogram(), geom, 30, maxPixels=1e8).get("cropland")
        return ee.Feature(None, {"anio": img.get("system:index"), "h": h})

    return ee.FeatureCollection(col.map(hist))


def lote(radio_m: int = 1500):
    col = ee.ImageCollection("USDA/NASS/CDL").select("cropland")
    ultimo = ee.Number.parse(col.aggregate_max("system:index"))

    def del_anio(n):
        return col.filter(ee.Filter.eq("system:index", ultimo.subtract(n).format("%d"))).first()

    par = del_anio(0).multiply(1000000).add(del_anio(1).multiply(1000)).add(del_anio(2)).toInt64()
    pt = ee.Geometry.Point(PUNTO)
    valor = par.reduceRegion(ee.Reducer.first(), pt, 30).values().get(0)
    vec = par.eq(ee.Number(valor)).selfMask().reduceToVectors(
        geometry=pt.buffer(radio_m).bounds(), scale=30, geometryType="polygon", eightConnected=False, maxPixels=1e8)
    # la colección va directa, con el año y la secuencia como propiedades: metida en un Dictionary, Earth Engine la
    # devuelve sin sus features
    return vec.filterBounds(pt).set({"ultimo": ultimo, "valor": valor})


def main():
    if not gldas._asegurar_ee_inicializado():
        ee.Initialize(project="field-shift-514100")
    SALIDA.mkdir(exist_ok=True)
    for nombre, obj in (("cdl_por_anio", por_anio()), ("cdl_lote", lote())):
        expr = serializer.encode(obj, for_cloud_api=True)
        (SALIDA / f"{nombre}.json").write_text(json.dumps(expr, separators=(",", ":")), encoding="utf-8")
        print(nombre, len(json.dumps(expr)), "bytes")


if __name__ == "__main__":
    main()
