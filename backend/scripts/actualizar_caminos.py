"""Vuelve a bajar de OpenStreetMap (Overpass) los caminos departamentales, vecinales
y huellas rurales de un departamento y los guarda en fieldshift/datos/caminos/<slug>.json..

Uso desde app/backend:
    .venv/Scripts/python scripts/actualizar_caminos.py soriano
    .venv/Scripts/python scripts/actualizar_caminos.py paysandu
    .venv/Scripts/python scripts/actualizar_caminos.py soriano respuesta_overpass.json

Licencia de los datos: ODbL, con atribución "© colaboradores de OpenStreetMap".
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import httpx
from shapely.geometry import LineString, shape

DIR_DATOS = Path(__file__).resolve().parents[1] / "fieldshift" / "datos"
DIR_CAMINOS = DIR_DATOS / "caminos"
ARCHIVO_DEPTOS = DIR_DATOS / "departamentos_uy.json"
TOLERANCIA = 0.00014  # ~15 metros


def slugificar(nombre: str) -> str:
    """Normaliza un nombre de departamento a slug en minúsculas sin acentos: 'PAYSANDÚ' -> 'paysandu'."""
    n = unicodedata.normalize("NFKD", nombre).encode("ASCII", "ignore").decode("utf-8")
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def procesar_elementos(elementos: list[dict[str, Any]], geom_depto) -> dict[str, Any]:
    """Clasifica, recorta al límite del departamento y simplifica los caminos de OSM."""
    vias: dict[str, list[list[tuple[float, float]]]] = {
        "tertiary": [],
        "unclassified": [],
        "track": [],
    }

    for el in elementos:
        hw = el.get("tags", {}).get("highway", "track")
        if hw not in vias:
            continue
        geom = el.get("geometry", [])
        if len(geom) < 2:
            continue

        coords = [(round(p["lon"], 5), round(p["lat"], 5)) for p in geom]
        linea = LineString(coords)

        # Si se pasa la geometría del departamento, verificar intersección
        if geom_depto is not None:
            if not linea.intersects(geom_depto):
                continue
            recortada = linea.intersection(geom_depto)
            if recortada.is_empty:
                continue
            lineas_proc = (
                [recortada]
                if recortada.geom_type == "LineString"
                else list(recortada.geoms)
                if recortada.geom_type == "MultiLineString"
                else []
            )
        else:
            lineas_proc = [linea]

        for lp in lineas_proc:
            ls = lp.simplify(TOLERANCIA)
            if ls.is_empty or len(ls.coords) < 2:
                continue
            coords_simplificadas = [(round(x, 5), round(y, 5)) for x, y in ls.coords]
            vias[hw].append(coords_simplificadas)

    return vias


def descargar_depto(nombre_depto: str, archivo_json_previo: Path | None = None) -> dict[str, Any]:
    """Descarga o procesa desde archivo los caminos de un departamento."""
    DIR_CAMINOS.mkdir(parents=True, exist_ok=True)
    slug = slugificar(nombre_depto)
    salida = DIR_CAMINOS / f"{slug}.json"

    # Buscar polígono del departamento en departamentos_uy.json
    geom_depto = None
    if ARCHIVO_DEPTOS.exists():
        deptos_geojson = json.loads(ARCHIVO_DEPTOS.read_text(encoding="utf-8"))
        for f in deptos_geojson.get("features", []):
            nom = f.get("properties", {}).get("nombre", "")
            if slugificar(nom) == slug:
                geom_depto = shape(f["geometry"])
                break

    if archivo_json_previo and archivo_json_previo.exists():
        print(f"Leyendo respuesta previa desde {archivo_json_previo}...")
        datos_raw = json.loads(archivo_json_previo.read_text(encoding="utf-8"))
        elementos = datos_raw.get("elements", [])
    else:
        print(f"Consultando Overpass API para departamento {nombre_depto}...")
        consulta = f"""
        [out:json][timeout:120];
        area["name"~"^{nombre_depto}$",i]["admin_level"="4"]->.depto;
        (
          way["highway"~"^(tertiary|unclassified|track)$"](area.depto);
        );
        out tags geom;
        """
        headers = {"User-Agent": "FieldShift/1.0 (hackathon agricultural tool; contact@fieldshift.uy)"}
        try:
            r = httpx.post("https://overpass-api.de/api/interpreter", data={"data": consulta}, timeout=120, headers=headers)
            r.raise_for_status()
            elementos = r.json().get("elements", [])
        except Exception as e:
            if geom_depto is not None:
                minx, miny, maxx, maxy = geom_depto.bounds
                print(f"Falla con area.depto ({e}), reintentando por bbox [{miny:.2f}, {minx:.2f}, {maxy:.2f}, {maxx:.2f}]...")
                consulta_bbox = f"""
                [out:json][timeout:120];
                (
                  way["highway"~"^(tertiary|unclassified|track)$"]({miny},{minx},{maxy},{maxx});
                );
                out tags geom;
                """
                r = httpx.post("https://overpass-api.de/api/interpreter", data={"data": consulta_bbox}, timeout=120, headers=headers)
                r.raise_for_status()
                elementos = r.json().get("elements", [])
            else:
                raise

    print(f"Procesando {len(elementos)} elementos de {nombre_depto}...")
    caminos = procesar_elementos(elementos, geom_depto)

    resultado = {
        "departamento": nombre_depto.upper(),
        "slug": slug,
        "fuente": f"OpenStreetMap (© colaboradores de OpenStreetMap, ODbL), consulta del {dt.date.today():%d/%m/%Y}",
        "tertiary": {"type": "MultiLineString", "coordinates": caminos["tertiary"]},
        "unclassified": {"type": "MultiLineString", "coordinates": caminos["unclassified"]},
        "track": {"type": "MultiLineString", "coordinates": caminos["track"]},
    }

    salida.write_text(json.dumps(resultado, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    t_count = len(caminos["tertiary"])
    u_count = len(caminos["unclassified"])
    k_count = len(caminos["track"])
    print(f"Guardado {salida} ({round(salida.stat().st_size / 1024)} KB) | tertiary: {t_count}, unclassified: {u_count}, track: {k_count}")
    return resultado


if __name__ == "__main__":
    args = sys.argv[1:]
    depto = args[0] if args else "soriano"
    archivo_previo = Path(args[1]) if len(args) > 1 else None

    descargar_depto(depto, archivo_previo)
