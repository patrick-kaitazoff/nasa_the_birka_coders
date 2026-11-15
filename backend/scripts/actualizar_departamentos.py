"""Vuelve a bajar del MGAP (BASE/Administrativo, capa 13) los límites de los 19 departamentos de Uruguay,
los simplifica todos juntos con coverage_simplify (para que los bordes compartidos coincidan exactamente)
y los guarda en fieldshift/datos/departamentos_uy.json (lo que usa el mapa para dibujarlos y nombrarlos).

Correr desde app/backend: .venv/Scripts/python scripts/actualizar_departamentos.py (tarda ~15 s)
Si el servidor del MGAP da error o está saturado, se le puede pasar un JSON ya bajado:
    .venv/Scripts/python scripts/actualizar_departamentos.py respuesta_mgap.json
Fuente: MGAP-DGRN, Dirección General de Recursos Naturales, IDEUY.
"""

import json
import sys
from pathlib import Path

import httpx
import numpy as np
import shapely
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union

BASE = "https://dgrn.mgap.gub.uy/arcgis/rest/services"
SALIDA = Path(__file__).resolve().parents[1] / "fieldshift" / "datos" / "departamentos_uy.json"


def esri_a_geojson(js: dict) -> dict:
    """Esri JSON → GeoJSON. En Esri los anillos exteriores van en sentido horario y los huecos
    al revés; un mismo registro puede tener varias partes exteriores."""
    feats = []
    for f in js.get("features", []):
        g = f.get("geometry") or {}
        if "rings" not in g:
            continue
        exteriores: list[Polygon] = []
        huecos: list[Polygon] = []
        for r in g["rings"]:
            if len(r) < 3:
                continue
            p = Polygon(r)
            (exteriores if p.exterior.is_ccw is False else huecos).append(p)
        if not exteriores:
            continue
        poligonos = []
        for ext in exteriores:
            h_dentro = [h.exterior.coords for h in huecos if ext.contains(h)]
            poligonos.append(Polygon(ext.exterior.coords, h_dentro))
        geom = unary_union(poligonos)
        feats.append({"type": "Feature", "properties": f.get("attributes", {}), "geometry": mapping(geom)})
    return {"type": "FeatureCollection", "features": feats}


def procesar(datos_esri: dict) -> dict:
    """Simplifica los polígonos de los departamentos con coverage_simplify a 0,004° y redondea a 4 decimales."""
    fc = esri_a_geojson(datos_esri)
    por_nombre: dict[str, list] = {}
    for f in fc["features"]:
        por_nombre.setdefault(f["properties"].get("NOMBRE", ""), []).append(shape(f["geometry"]))
    nombres = sorted(n for n in por_nombre if n)
    simples = shapely.coverage_simplify([unary_union(por_nombre[n]) for n in nombres], 0.004)  # ~400 m
    # redondear a 4 decimales (~10 m): dos vértices iguales quedan iguales
    simples = [shapely.transform(g, lambda c: np.round(c, 4)) for g in simples]
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"nombre": n}, "geometry": mapping(g)}
            for n, g in zip(nombres, simples)
        ],
    }


def main():
    if len(sys.argv) > 1:
        ruta_archivo = Path(sys.argv[1])
        print(f"Leyendo datos desde {ruta_archivo}...")
        datos_esri = json.loads(ruta_archivo.read_text(encoding="utf-8"))
    else:
        url = f"{BASE}/BASE/Administrativo/MapServer/13/query"
        params = {"where": "1=1", "outFields": "NOMBRE", "returnGeometry": "true", "outSR": 4326, "f": "json"}
        print(f"Descargando departamentos del MGAP desde {url}...")
        r = httpx.get(url, params=params, timeout=120)
        r.raise_for_status()
        datos_esri = r.json()

    resultado = procesar(datos_esri)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    contenido = json.dumps(resultado, ensure_ascii=False, separators=(",", ":"))
    SALIDA.write_text(contenido, encoding="utf-8")
    tamano_kb = round(SALIDA.stat().st_size / 1024, 1)
    print(f"Guardados {len(resultado['features'])} departamentos ({tamano_kb} KB) en {SALIDA}")


if __name__ == "__main__":
    main()
