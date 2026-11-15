"""Vuelve a bajar de OpenStreetMap (Overpass) las rutas nacionales de Uruguay y las guarda en
fieldshift/datos/rutas_uy.json.

Correr desde app/backend: .venv/Scripts/python scripts/actualizar_rutas.py (tarda ~1 min)
Si Overpass da 502 (saturado), se le pueden pasar respuestas ya bajadas: actualizar_rutas.py a.json b.json
Licencia de los datos: ODbL, con atribución "© colaboradores de OpenStreetMap".

Qué entra: los tramos con número de ruta nacional (1 a 109, más la Interbalnearia), de las categorías
troncal, primaria y secundaria de OSM. Cada ruta se une en líneas largas y se simplifica a ~15 m (sobre la
foto se nota a partir del zoom 15; por eso el mapa las muestra hasta el 14). Para el número se guardan
puntos cada ~12 km sobre cada ruta: el mapa muestra los que no se pisan.
"""

import datetime as dt
import json
import re
import sys
from pathlib import Path

import httpx
from shapely.geometry import LineString, MultiLineString, mapping
from shapely.ops import linemerge, unary_union

CONSULTA = ('[out:json][timeout:240];area["ISO3166-1"="UY"][admin_level=2]->.uy;'
            'way["highway"~"^(motorway|trunk|primary|secondary)$"]["ref"](area.uy);out tags geom;')
SALIDA = Path(__file__).resolve().parents[1] / "fieldshift" / "datos" / "rutas_uy.json"
TOLERANCIA = 0.00014  # grados, ~15 m
CADA_KM = 12


def numeros(ref: str) -> list[str]:
    """'7;26' -> ['7', '26']; 'IB' -> ['IB']; descarta lo que no es ruta nacional (BR-116, RN HB...)."""
    salida = []
    for r in re.split(r"[;,]", ref):
        r = r.strip().upper().replace("RUTA ", "")
        if r == "IB" or (r.isdigit() and 1 <= int(r) <= 109):
            salida.append(r)
    return salida


if len(sys.argv) > 1:
    # respuestas de Overpass ya bajadas (si el servidor está saturado y da 502): un .json por argumento
    elementos = [e for f in sys.argv[1:] for e in json.loads(Path(f).read_text(encoding="utf-8"))["elements"]]
else:
    r = httpx.post("https://overpass-api.de/api/interpreter", data={"data": CONSULTA}, timeout=300,
                   headers={"User-Agent": "FieldShift/0.1 (prototipo de hackaton)"})
    r.raise_for_status()
    elementos = r.json()["elements"]

tramos: dict[str, list[LineString]] = {}
principal: dict[str, int] = {}  # cuántos tramos troncales o primarios tiene (para el ancho de la línea)
for e in elementos:
    nums = numeros(e["tags"].get("ref", ""))
    if not nums or len(e.get("geometry", [])) < 2:
        continue
    linea = LineString([(p["lon"], p["lat"]) for p in e["geometry"]])
    # la línea va una sola vez (con la primera ruta); el número se pone para cada ruta del tramo
    tramos.setdefault(nums[0], []).append(linea)
    for n in nums:
        principal[n] = principal.get(n, 0) + (e["tags"]["highway"] in ("motorway", "trunk", "primary"))
        if n != nums[0]:
            tramos.setdefault(n, [])

lineas, numeros_pts = [], []
for n, ls in sorted(tramos.items(), key=lambda t: (t[0] != "IB", int(t[0]) if t[0].isdigit() else 0)):
    if not ls:
        continue
    u = unary_union(ls)
    u = MultiLineString([u]) if isinstance(u, LineString) else u  # linemerge no acepta una línea sola
    unida = linemerge(u)
    partes = list(unida.geoms) if isinstance(unida, MultiLineString) else [unida]
    partes = [p.simplify(TOLERANCIA) for p in partes]
    clase = "principal" if principal.get(n, 0) * 2 >= len(ls) else "secundaria"
    geo = MultiLineString(partes) if len(partes) > 1 else partes[0]
    g = mapping(geo)
    g["coordinates"] = json.loads(json.dumps(g["coordinates"]), parse_float=lambda x: round(float(x), 5))
    lineas.append({"type": "Feature", "properties": {"ruta": n, "clase": clase}, "geometry": g})
    # puntos para el número: cada ~12 km a lo largo de cada línea (la mitad del primer tramo para arrancar)
    for p in partes:
        largo_km = p.length * 100  # aprox. (1 grado ~ 100 km a esta latitud, promedio de lat y lon)
        if largo_km < 3:
            continue
        k = max(1, round(largo_km / CADA_KM))
        for i in range(k):
            q = p.interpolate((i + 0.5) / k, normalized=True)
            numeros_pts.append({"ruta": n, "clase": clase, "lat": round(q.y, 5), "lon": round(q.x, 5)})

SALIDA.write_text(json.dumps({
    "fuente": f"OpenStreetMap (© colaboradores de OpenStreetMap, ODbL), consulta Overpass del {dt.date.today():%d/%m/%Y}",
    "lineas": {"type": "FeatureCollection", "features": lineas},
    "numeros": numeros_pts,
}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(len(lineas), "rutas,", len(numeros_pts), "carteles,", round(SALIDA.stat().st_size / 1024), "KB en", SALIDA)
