"""Caminos, rutas y callejones rurales desde OpenStreetMap para respetar la red vial (A).

Cuando se dividen campos o potreros, los caminos vecinales, callejones y servidumbres de paso
actúan como límites físicos reales. Este módulo consulta OpenStreetMap (Overpass), aplica un
ancho real estimado (buffer de 6 a 12 m) y corta el campo antes o durante la partición para que
las secciones nunca queden montadas sobre una calle ni la absorban en el polígono.
"""

from __future__ import annotations

import math
from typing import Any

import httpx
import shapely
from shapely.geometry import LineString, shape
from shapely.ops import unary_union

from .. import cache

# Anchos estimados de calzada + banquina/zanja por tipo de vía en zonas rurales (en metros)
ANCHOS_METROS: dict[str, float] = {
    "motorway": 18.0,
    "trunk": 16.0,
    "primary": 14.0,
    "secondary": 12.0,
    "tertiary": 9.0,
    "unclassified": 7.5,
    "residential": 7.0,
    "service": 6.0,
    "track": 6.0,
    "path": 4.5,
    "road": 6.5,
}
ANCHO_DEFECTO = 6.0


def consultar_vias_osm(bounds: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """Consulta las vías vehiculares y caminos rurales de OSM en el rectángulo dado."""
    minx, miny, maxx, maxy = bounds
    # margen de ~150 m alrededor
    margen = 0.0015
    south, west = round(miny - margen, 5), round(minx - margen, 5)
    north, east = round(maxy + margen, 5), round(maxx + margen, 5)

    clave = f"{south}_{west}_{north}_{east}"
    guardado = cache.leer("caminos_osm", clave, max_dias=30)
    if guardado is not None:
        return guardado.get("elementos", [])

    consulta = f"""
    [out:json][timeout:4];
    (
      way["highway"]({south},{west},{north},{east});
    );
    out geom;
    """
    try:
        r = httpx.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": consulta},
            timeout=4.5,
            headers={"User-Agent": "FieldShift/1.0 (Hackathon; agricultural parcel delineation)"},
        )
        if r.status_code == 200:
            datos = r.json().get("elements", [])
            cache.guardar("caminos_osm", clave, {"elementos": datos})
            return datos
    except Exception:  # noqa: BLE001
        # Si Overpass está caído, saturado o sin conexión, se continúa sin calles sin romper la app
        pass

    return []


def obtener_geometrias_caminos(campo: shapely.Geometry, m2_por_grado2: float) -> list[tuple[shapely.Geometry, float]]:
    """Devuelve las líneas de caminos que cruzan o tocan el campo con su ancho en metros."""
    elementos = consultar_vias_osm(campo.bounds)
    if not elementos:
        return []

    caminos: list[tuple[shapely.Geometry, float]] = []
    campo_buffer = campo.buffer(0.0001)  # ~10 m de margen

    for el in elementos:
        geom = el.get("geometry")
        if not geom or len(geom) < 2:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in geom]
        try:
            linea = LineString(coords)
            if not linea.is_valid:
                linea = linea.buffer(0)
            if linea.intersects(campo_buffer):
                hw = str(el.get("tags", {}).get("highway", "track")).lower()
                ancho = ANCHOS_METROS.get(hw, ANCHO_DEFECTO)
                caminos.append((linea, ancho))
        except Exception:  # noqa: BLE001
            continue

    return caminos


def cortar_por_calles(
    campo: shapely.Geometry, m2_por_grado2: float
) -> tuple[shapely.Geometry, shapely.Geometry | None, list[dict[str, Any]]]:
    """Corta el campo restándole los corredores viales reales detectados en OSM.

    Devuelve (campo_util, mascara_calles, lista_calles). Si no hay caminos que crucen el lote,
    devuelve (campo, None, []).
    """
    caminos = obtener_geometrias_caminos(campo, m2_por_grado2)
    if not caminos:
        return campo, None, []

    # metros a grados de latitud/longitud aproximados
    lat_c = campo.centroid.y
    m_por_grado_lon = 111320 * math.cos(math.radians(lat_c))
    m_por_grado_lat = 110540
    m_por_grado = (m_por_grado_lon + m_por_grado_lat) / 2

    buffers: list[shapely.Geometry] = []
    info: list[dict[str, Any]] = []

    for linea, ancho_m in caminos:
        radio_grados = (ancho_m / 2.0) / m_por_grado
        buf = linea.buffer(radio_grados, cap_style="flat", join_style="mitre")
        if buf.intersects(campo):
            buffers.append(buf)
            info.append({"ancho_m": ancho_m, "tipo": "camino_osm"})

    if not buffers:
        return campo, None, []

    calles_union = unary_union(buffers)
    campo_cortado = campo.difference(calles_union)
    if campo_cortado.is_empty:
        return campo, None, []

    campo_cortado = shapely.make_valid(campo_cortado)
    return campo_cortado, calles_union, info
