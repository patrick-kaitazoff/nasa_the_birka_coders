"""Baja los límites de los estados y condados de EE. UU. y los guarda simplificados en el repo, como los
departamentos de Uruguay: `datos/estados_us.json` y `datos/condados_us/<FIPS del estado>.json`.

Fuente: U.S. Census Bureau, TIGERweb `Generalized_ACS2023/State_County` (ArcGIS REST, sin cuenta): estados 1:20M
(capa 9) y condados 1:5M (capa 12). Solo los 48 estados contiguos y el Distrito de Columbia, que es lo que cubren el
Cropland Data Layer y el resto de la app en EE. UU. Dominio público.

Correr desde app/backend: .venv/Scripts/python scripts/actualizar_estados_us.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from shapely.geometry import mapping, shape

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "fieldshift" / "datos"
BASE = "https://tigerweb.geo.census.gov/arcgis/rest/services/Generalized_ACS2023/State_County/MapServer"
FUERA = {"02", "15", "60", "66", "69", "72", "78"}  # Alaska, Hawái y los territorios


def _redondear(g: dict, dec: int) -> dict:
    def r(c):
        return [round(c[0], dec), round(c[1], dec)] if isinstance(c[0], (int, float)) else [r(x) for x in c]
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def _bajar(capa: int, donde: str, campos: str) -> list[dict]:
    r = httpx.get(f"{BASE}/{capa}/query", params={"where": donde, "outFields": campos, "outSR": 4326, "f": "geojson",
                                                  "returnGeometry": "true"}, timeout=120)
    r.raise_for_status()
    return r.json()["features"]


def main():
    estados = []
    for f in _bajar(9, "1=1", "NAME,STATE,STUSAB,INTPTLAT,INTPTLON"):
        p = f["properties"]
        if p["STATE"] in FUERA:
            continue
        g = shape(f["geometry"]).simplify(0.01, preserve_topology=True)
        estados.append({"type": "Feature", "properties": {"fips": p["STATE"], "nombre": p["NAME"], "sigla": p["STUSAB"],
                                                          "lat": float(p["INTPTLAT"]), "lon": float(p["INTPTLON"])},
                        "geometry": _redondear(mapping(g), 3)})
    estados.sort(key=lambda f: f["properties"]["nombre"])
    (DATOS / "estados_us.json").write_text(json.dumps({"type": "FeatureCollection", "features": estados},
                                                      ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("estados:", len(estados), round((DATOS / "estados_us.json").stat().st_size / 1024), "KB")

    carpeta = DATOS / "condados_us"
    carpeta.mkdir(exist_ok=True)
    total = 0
    for e in estados:
        fips = e["properties"]["fips"]
        cond = []
        for f in _bajar(12, f"STATE='{fips}'", "NAME,BASENAME,COUNTY,GEOID,INTPTLAT,INTPTLON"):
            p = f["properties"]
            g = shape(f["geometry"]).simplify(0.002, preserve_topology=True)
            cond.append({"type": "Feature", "properties": {"fips": p["GEOID"], "nombre": p["NAME"], "base": p["BASENAME"],
                                                           "lat": float(p["INTPTLAT"]), "lon": float(p["INTPTLON"])},
                         "geometry": _redondear(mapping(g), 4)})
        cond.sort(key=lambda f: f["properties"]["nombre"])
        ruta = carpeta / f"{fips}.json"
        ruta.write_text(json.dumps({"type": "FeatureCollection", "features": cond}, ensure_ascii=False,
                                   separators=(",", ":")), encoding="utf-8")
        total += ruta.stat().st_size
        print(f"  {e['properties']['sigla']}: {len(cond)} condados", file=sys.stderr)
    print("condados:", round(total / 1024), "KB en", len(estados), "archivos")


if __name__ == "__main__":
    main()
