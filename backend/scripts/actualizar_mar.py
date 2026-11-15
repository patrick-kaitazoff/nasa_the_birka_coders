"""Arma el polígono del mar frente a Uruguay (Río de la Plata y Atlántico) con la línea de costa de
OpenStreetMap y lo guarda en fieldshift/datos/mar_uy.json.

Para qué: la foto satelital de Esri, de cerca (zoom 12 o más), trae el agua en cuadrados de distinto tono
y manchas marrones pegadas a la costa. El mapa pinta este
polígono con un azul parejo encima de la foto, solo de cerca.

Correr desde app/backend: .venv/Scripts/python scripts/actualizar_mar.py (tarda ~30 s)
Si Overpass da 502 (saturado), se le puede pasar la respuesta ya bajada: actualizar_mar.py costa.json
Licencia de los datos: ODbL, con atribución "© colaboradores de OpenStreetMap".
"""

import datetime as dt
import json
import sys
from pathlib import Path

import httpx
from shapely.geometry import LineString, Point, box, mapping
from shapely.ops import polygonize, unary_union

CAJA = (-58.7, -35.5, -52.9, -33.5)  # oeste, sur, este, norte
CONSULTA = f'[out:json][timeout:240];way["natural"="coastline"]({CAJA[1]},{CAJA[0]},{CAJA[3]},{CAJA[2]});out geom;'
SALIDA = Path(__file__).resolve().parents[1] / "fieldshift" / "datos" / "mar_uy.json"
# puntos que seguro son agua: los pedazos que los contienen son el mar
AGUA = [Point(-55.5, -35.2), Point(-57.2, -34.85), Point(-56.3, -34.95), Point(-53.3, -34.4), Point(-58.2, -34.3)]

if len(sys.argv) > 1:
    elementos = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["elements"]
else:
    r = httpx.post("https://overpass-api.de/api/interpreter", data={"data": CONSULTA}, timeout=300,
                   headers={"User-Agent": "FieldShift/0.1 (prototipo de hackaton)"})
    r.raise_for_status()
    elementos = r.json()["elements"]

lineas = [LineString([(p["lon"], p["lat"]) for p in e["geometry"]]) for e in elementos if len(e.get("geometry", [])) >= 2]
marco = box(*CAJA)
red = unary_union([l.intersection(marco) for l in lineas] + [marco.exterior])
pedazos = list(polygonize(red))
mar = unary_union([p for p in pedazos if any(p.contains(a) for a in AGUA)])
# las islas (Gorriti, Lobos, Flores) quedan como huecos; se simplifica a ~8 m
mar = mar.simplify(0.00007).buffer(0)
g = mapping(mar)
g = json.loads(json.dumps(g), parse_float=lambda x: round(float(x), 5))
SALIDA.write_text(json.dumps({
    "fuente": f"OpenStreetMap (© colaboradores de OpenStreetMap, ODbL), línea de costa, consulta Overpass del {dt.date.today():%d/%m/%Y}",
    "mar": {"type": "Feature", "properties": {}, "geometry": g},
}, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
print(len(lineas), "tramos de costa,", len(pedazos), "pedazos,", round(SALIDA.stat().st_size / 1024), "KB en", SALIDA)
