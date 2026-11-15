"""Cambio de clima proyectado para Uruguay, celda por celda, con NASA NEX-GDDP-CMIP6 (Earth Engine).

Para cada celda de 0,25° (~25 km) que toca Uruguay y para cada modelo climático: cuánto cambian, mes por mes, la
temperatura media, máxima y mínima (°C) y la lluvia (cociente) entre 1991-2020 y 2026-2035, con el escenario medio de
emisiones (SSP2-4.5). 1991-2014 sale de la corrida «historical» de cada modelo y 2015-2020 de la SSP2-4.5, como se
hace en los informes del IPCC. Se guarda el promedio de los modelos y su rango (p10 y p90) en
fieldshift/datos/cmip6_uruguay.json.gz, para que la app lo lea sin consultar Earth Engine.

Correr desde app/backend (tarda: un pedido por modelo): .venv/Scripts/python scripts/cmip6_uruguay_ee.py [modelos]
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import sys
import time
from pathlib import Path

import numpy as np
from shapely.geometry import Point, shape
from shapely.ops import unary_union

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import ee  # noqa: E402

from fieldshift.fuentes import modis_historia  # noqa: E402

SALIDA = RAIZ / "fieldshift" / "datos" / "cmip6_uruguay.json.gz"
PARCIAL = RAIZ / "cache" / "cmip6_por_modelo.json"
COLECCION = "NASA/GDDP-CMIP6"
ESCENARIO = "ssp245"
BASE = (1991, 2020)
FUTURO = (2026, 2035)
VARIABLES = ["tas", "tasmax", "tasmin", "pr"]
ESCALA_M = 27830  # 0,25° en el ecuador


def celdas_uruguay() -> list[tuple[float, float]]:
    """Centros de la grilla de NEX-GDDP (0,125 + k·0,25) a menos de ~20 km de Uruguay."""
    deps = json.loads((RAIZ / "fieldshift" / "datos" / "departamentos_uy.json").read_text(encoding="utf-8"))
    feats = deps["features"] if isinstance(deps, dict) and "features" in deps else deps
    uy = unary_union([shape(f["geometry"]) for f in feats]).buffer(0.2)
    w, s, e, n = uy.bounds
    lats = np.arange(np.floor(s * 4) / 4 + 0.125, n, 0.25)
    lons = np.arange(np.floor(w * 4) / 4 + 0.125, e, 0.25)
    return [(round(float(la), 3), round(float(lo), 3)) for la in lats for lo in lons if uy.contains(Point(lo, la))]


def promedios(col: ee.ImageCollection, anios: tuple[int, int]) -> ee.Image:
    """Una imagen con 48 bandas: <variable>_<mes> = promedio de ese mes en esos años."""
    c = col.filter(ee.Filter.rangeContains("year", anios[0], anios[1]))
    bandas = []
    for m in range(1, 13):
        img = c.filter(ee.Filter.eq("month", m)).select(VARIABLES).mean()
        bandas.append(img.rename([f"{v}_{m}" for v in VARIABLES]))
    return ee.Image.cat(bandas)


def cambio_modelo(modelo: str, puntos: ee.FeatureCollection) -> list[dict]:
    col = ee.ImageCollection(COLECCION).filter(ee.Filter.eq("model", modelo))
    hist = col.filter(ee.Filter.eq("scenario", "historical"))
    ssp = col.filter(ee.Filter.eq("scenario", ESCENARIO))
    base = promedios(hist.merge(ssp), BASE)
    fut = promedios(ssp, FUTURO)
    temps = [f"{v}_{m}" for m in range(1, 13) for v in ("tas", "tasmax", "tasmin")]
    lluvias = [f"pr_{m}" for m in range(1, 13)]
    delta = fut.select(temps).subtract(base.select(temps)).addBands(fut.select(lluvias).divide(base.select(lluvias)))
    res = delta.reduceRegions(collection=puntos, reducer=ee.Reducer.first(), scale=ESCALA_M).getInfo()
    return [f["properties"] for f in res["features"]]


def main():
    sa = modis_historia._cargar_sa_info()
    ee.Initialize(credentials=ee.ServiceAccountCredentials(sa["client_email"], key_data=json.dumps(sa)),
                  project=sa.get("project_id"))
    celdas = celdas_uruguay()
    puntos = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([lo, la]), {"i": i}) for i, (la, lo) in enumerate(celdas)])
    col = ee.ImageCollection(COLECCION)
    con_ssp = set(col.filter(ee.Filter.eq("scenario", ESCENARIO)).filterDate("2030-01-01", "2030-01-02")
                  .aggregate_array("model").getInfo())
    con_hist = set(col.filter(ee.Filter.eq("scenario", "historical")).filterDate("2000-01-01", "2000-01-02")
                   .aggregate_array("model").getInfo())
    modelos = sorted(con_ssp & con_hist)
    if len(sys.argv) > 1:
        modelos = [m for m in modelos if m in sys.argv[1].split(",")]
    print(len(celdas), "celdas;", len(modelos), "modelos", flush=True)
    hechos = json.loads(PARCIAL.read_text(encoding="utf-8")) if PARCIAL.exists() else {}
    for m in modelos:
        if m in hechos:
            continue
        t = time.time()
        try:
            hechos[m] = cambio_modelo(m, puntos)
        except Exception as e:  # noqa: BLE001
            print(f"  {m}: falló ({str(e)[:160]})", flush=True)
            continue
        PARCIAL.parent.mkdir(parents=True, exist_ok=True)
        PARCIAL.write_text(json.dumps(hechos), encoding="utf-8")
        print(f"  {m}: {round(time.time() - t)} s", flush=True)

    usados = [m for m in modelos if m in hechos]
    claves = [f"{v}_{mes}" for mes in range(1, 13) for v in VARIABLES]
    salida_celdas = []
    for i, (la, lo) in enumerate(celdas):
        fila = {"lat": la, "lon": lo}
        for k in claves:
            vals = [next((p[k] for p in hechos[m] if p["i"] == i and p.get(k) is not None), None) for m in usados]
            vals = np.array([v for v in vals if v is not None], dtype=float)
            if not len(vals):
                continue
            fila.setdefault(k.rsplit("_", 1)[0], {"media": [None] * 12, "p10": [None] * 12, "p90": [None] * 12})
            mes = int(k.rsplit("_", 1)[1]) - 1
            nd = 4 if k.startswith("pr") else 2
            fila[k.rsplit("_", 1)[0]]["media"][mes] = round(float(vals.mean()), nd)
            fila[k.rsplit("_", 1)[0]]["p10"][mes] = round(float(np.percentile(vals, 10)), nd)
            fila[k.rsplit("_", 1)[0]]["p90"][mes] = round(float(np.percentile(vals, 90)), nd)
        # rango entre modelos del cambio en el año: con el cambio anual de cada modelo, no promediando los extremos
        # de cada mes (que no caen en el mismo modelo y agrandaban el rango a ±20 %)
        anual_pr, anual_t = [], []
        for m in usados:
            p = next((p for p in hechos[m] if p["i"] == i), None)
            if p and all(p.get(f"{v}_{mes}") is not None for v in ("pr", "tasmax", "tasmin") for mes in range(1, 13)):
                anual_pr.append(np.mean([p[f"pr_{mes}"] for mes in range(1, 13)]))
                anual_t.append(np.mean([(p[f"tasmax_{mes}"] + p[f"tasmin_{mes}"]) / 2 for mes in range(1, 13)]))
        if anual_pr:
            fila["anual"] = {"pr_p10": round(float(np.percentile(anual_pr, 10)), 4), "pr_p90": round(float(np.percentile(anual_pr, 90)), 4),
                             "t_p10": round(float(np.percentile(anual_t, 10)), 2), "t_p90": round(float(np.percentile(anual_t, 90)), 2)}
        if len(fila) > 2:  # 8 celdas sobre el mar o el Río de la Plata no tienen datos en NEX-GDDP
            salida_celdas.append(fila)
    meta = {
        "fuente": "NASA NEX-GDDP-CMIP6 (Earth Engine, NASA/GDDP-CMIP6), 0,25°",
        "escenario": "SSP2-4.5", "base": f"{BASE[0]}-{BASE[1]}", "futuro": f"{FUTURO[0]}-{FUTURO[1]}",
        "modelos": usados, "armado": dt.date.today().isoformat(),
        "unidades": "tas, tasmax, tasmin: °C de diferencia; pr: cociente futuro / base",
    }
    SALIDA.write_bytes(gzip.compress(json.dumps({"meta": meta, "celdas": salida_celdas}, separators=(",", ":")).encode("utf-8")))
    print(SALIDA, round(SALIDA.stat().st_size / 1024), "KB,", len(usados), "modelos", flush=True)


if __name__ == "__main__":
    main()
