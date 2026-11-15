"""Vuelve a bajar de OpenStreetMap (Overpass) las ciudades, villas, pueblos, caseríos y parajes de Uruguay
y los guarda en fieldshift/datos/lugares_uy.json (lo que usa el mapa para poner nombres al acercarse).

Correr desde app/backend: .venv/Scripts/python scripts/actualizar_lugares.py (tarda ~45 s)
Licencia de los datos: ODbL, con atribución "© colaboradores de OpenStreetMap".
"""

import datetime as dt
import json
from pathlib import Path

import httpx

CONSULTA = ('[out:json][timeout:120];area["ISO3166-1"="UY"][admin_level=2]->.uy;'
            'node(area.uy)["place"~"^(city|town|village|hamlet|locality)$"]["name"];out body;')
ORDEN = {"city": 0, "town": 1, "village": 2, "hamlet": 3, "locality": 4}
SALIDA = Path(__file__).resolve().parents[1] / "fieldshift" / "datos" / "lugares_uy.json"

r = httpx.post("https://overpass-api.de/api/interpreter", data={"data": CONSULTA}, timeout=180,
               headers={"User-Agent": "FieldShift/0.1 (prototipo de hackatón)"})
r.raise_for_status()
lugares = sorted(({"n": e["tags"]["name"], "t": e["tags"]["place"], "lat": round(e["lat"], 4), "lon": round(e["lon"], 4)}
                  for e in r.json()["elements"]), key=lambda x: (ORDEN[x["t"]], x["n"]))
SALIDA.write_text(json.dumps({"fuente": f"OpenStreetMap (© colaboradores de OpenStreetMap, ODbL), consulta Overpass del {dt.date.today():%d/%m/%Y}",
                              "lugares": lugares}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(len(lugares), "lugares en", SALIDA)
