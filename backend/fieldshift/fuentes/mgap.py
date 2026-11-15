"""Servidor de mapas del MGAP (DGRN): suelo por punto y contorno de un padrón.

https://dgrn.mgap.gub.uy/arcgis/rest/services — ArcGIS Server 10.31, sin cuenta, lento
(~20 s por consulta). Probado (ver `09-datos-locales-uruguay.md` §1.1).

- `TEMATICOS/Coneat_K`: grupo CONEAT, suelos dominante y asociados, FACTOR_K (erodabilidad,
  en las unidades de la USLE de EE. UU.) y T (tolerancia de pérdida, t/ha/año).
- `TEMATICOS/a_pendiente`: pendiente en %.
- `CONEAT/IndicesConeat`: índice de productividad CONEAT (100 = media del país).
- `CONEAT/ConsultaConeat`: padrones rurales partidos por grupo de suelo (PADRON, DEPTO, AREAHA).

Licencia: datos públicos del MGAP, con atribución.
"""

from __future__ import annotations

import json

import httpx
import numpy as np
import shapely
from shapely.geometry import LinearRing, Polygon, mapping, shape
from shapely.ops import unary_union

from .. import cache

BASE = "https://dgrn.mgap.gub.uy/arcgis/rest/services"
DEPARTAMENTOS = [
    "ARTIGAS", "CANELONES", "CERRO LARGO", "COLONIA", "DURAZNO", "FLORES", "FLORIDA",
    "LAVALLEJA", "MALDONADO", "MONTEVIDEO", "PAYSANDU", "RIO NEGRO", "RIVERA", "ROCHA",
    "SALTO", "SAN JOSE", "SORIANO", "TACUAREMBO", "TREINTA Y TRES",
]

# Tiempos máximos de espera: el MGAP responde en 2-6 s si está sano; con 15-25 s evitamos
# agotar el límite de Vercel (300 s) y pasamos rápido al respaldo de valores típicos avisando.
TIMEOUT_IDENTIFY = 15.0
TIMEOUT_PADRON = 25.0
TIMEOUT_FACTOR_R = 15.0


def _identify(servicio: str, lat: float, lon: float, timeout: float = TIMEOUT_IDENTIFY) -> list[dict]:
    d = 0.002
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "sr": 4326,
        "layers": "all",
        "tolerance": 1,
        "mapExtent": f"{lon - d},{lat - d},{lon + d},{lat + d}",
        "imageDisplay": "400,400,96",
        "returnGeometry": "false",
        "f": "json",
    }
    r = httpx.get(f"{BASE}/{servicio}/MapServer/identify", params=params, timeout=timeout)
    r.raise_for_status()
    return r.json().get("results", [])


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def suelo_punto(lat: float, lon: float) -> dict:
    """Suelo oficial en un punto. Cacheado 180 días (la carta no cambia)."""
    clave = f"{lat:.5f},{lon:.5f}"
    guardado = cache.leer("mgap_suelo", clave, max_dias=180)
    if guardado:
        return guardado

    salida: dict = {
        "fuente": "MGAP-DGRN, servicios TEMATICOS/Coneat_K, TEMATICOS/a_pendiente, CONEAT/IndicesConeat",
        "lat": lat,
        "lon": lon,
        "ok": False,
    }
    errores = []
    try:
        filas = _identify("TEMATICOS/Coneat_K", lat, lon)
        suelos = []
        for f in filas:
            a = f.get("attributes", {})
            suelos.append(
                {
                    "grupo_coneat": a.get("CONEAT") or a.get("SC"),
                    "tipo": a.get("TIPO"),
                    "suelo": (a.get("SUELO_R6") or "").strip(),
                    "factor_k": _num(a.get("FACTOR_K")),
                    "tolerancia_t": _num(a.get("T")),
                    "pendiente_tipica": a.get("FGR"),
                }
            )
        if suelos:
            # grupo más repetido en el punto (si cae en un borde vienen dos)
            grupos: dict[str, int] = {}
            for s in suelos:
                grupos[s["grupo_coneat"]] = grupos.get(s["grupo_coneat"], 0) + 1
            grupo = max(grupos, key=grupos.get)
            del_grupo = [s for s in suelos if s["grupo_coneat"] == grupo]
            dominantes = [s for s in del_grupo if (s["tipo"] or "").startswith("dominante")] or del_grupo
            ks = [s["factor_k"] for s in dominantes if s["factor_k"] is not None]
            ts = [s["tolerancia_t"] for s in del_grupo if s["tolerancia_t"] is not None]
            salida.update(
                {
                    "grupo_coneat": grupo,
                    "suelos": del_grupo,
                    "suelo_dominante": dominantes[0]["suelo"],
                    "factor_k": round(sum(ks) / len(ks), 3) if ks else None,
                    # la tolerancia más baja del grupo: criterio conservador
                    "tolerancia_t": min(ts) if ts else None,
                    "ok": True,
                }
            )
    except (httpx.HTTPError, ValueError) as e:
        errores.append(f"Coneat_K: {e}")
        # Si el servidor no responde por timeout o fallo de red, no esperamos otros
        # dos timeouts para pendiente e índice CONEAT: pasamos antes a los valores típicos
        if isinstance(e, (httpx.TimeoutException, httpx.NetworkError)):
            salida["errores"] = errores
            return salida

    try:
        filas = _identify("TEMATICOS/a_pendiente", lat, lon)
        if filas:
            salida["pendiente_pct"] = _num(filas[0]["attributes"].get("Pixel Value"))
    except (httpx.HTTPError, ValueError) as e:
        errores.append(f"pendiente: {e}")

    try:
        filas = _identify("CONEAT/IndicesConeat", lat, lon)
        for f in filas:
            a = f.get("attributes", {})
            for k, v in a.items():
                if "IND" in k.upper() and _num(v) is not None:
                    salida["indice_coneat"] = _num(v)
                    break
    except (httpx.HTTPError, ValueError) as e:
        errores.append(f"índice CONEAT: {e}")

    if errores:
        salida["errores"] = errores
    if salida["ok"]:
        cache.guardar("mgap_suelo", clave, salida)
    return salida


def padron(departamento: str, numero: int) -> dict:
    """Contorno de un padrón rural (unión de sus partes por grupo CONEAT) y sus suelos."""
    depto = departamento.strip().upper()
    for a, b in (("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U")):
        depto = depto.replace(a, b)
    clave = f"{depto}:{numero}"
    guardado = cache.leer("mgap_padron", clave, max_dias=180)
    if guardado:
        return guardado

    params = {
        "where": f"PADRON={int(numero)} AND DEPTO='{depto}'",
        "outFields": "PADRON,DEPTO,AREAHA,SC,IND_CONEAT,IND_PROMEDIO",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "json",  # ArcGIS 10.31 no habla geojson (da 400)
    }
    r = httpx.get(f"{BASE}/CONEAT/ConsultaConeat/MapServer/0/query", params=params, timeout=TIMEOUT_PADRON)
    r.raise_for_status()
    js = _esri_a_geojson(r.json())
    feats = [f for f in js.get("features", []) if f.get("geometry")]
    if not feats:
        return {"ok": False, "error": f"No se encontró el padrón {numero} en {depto}."}

    geoms = [shape(f["geometry"]).buffer(0) for f in feats]
    union = unary_union(geoms)
    partes = []
    for f, g in zip(feats, geoms):
        p = f.get("properties", {})
        partes.append(
            {
                "grupo_coneat": p.get("SC"),
                "indice_coneat": p.get("IND_CONEAT"),
                "geometria": mapping(g),
            }
        )
    # juntar partes del mismo grupo CONEAT: son las secciones naturales por suelo
    por_grupo: dict[str, list] = {}
    for pt, g in zip(partes, geoms):
        por_grupo.setdefault(pt["grupo_coneat"] or "s/d", []).append(g)
    secciones_suelo = [
        {"grupo_coneat": k, "geometria": mapping(unary_union(v))} for k, v in por_grupo.items()
    ]
    salida = {
        "ok": True,
        "fuente": "MGAP-DGRN, CONEAT/ConsultaConeat (parcelario rural por grupo de suelo)",
        "departamento": depto,
        "padron": int(numero),
        "area_ha_catastro": feats[0].get("properties", {}).get("AREAHA"),
        "contorno": mapping(union),
        "secciones_por_suelo": secciones_suelo,
    }
    cache.guardar("mgap_padron", clave, salida)
    return salida


def suelos_en_area(geometria: dict) -> dict:
    """Grupos CONEAT que hay dentro de un contorno dibujado (no hace falta el padrón): el parcelario por
    grupo de suelo (CONEAT/ConsultaConeat) consultado por polígono y recortado al contorno. Responde en
    menos de 1 s. Sirve para avisar cuando una sección mezcla suelos distintos."""
    g = shape(geometria).buffer(0)
    clave = json.dumps([round(v, 5) for v in g.bounds]) + f"{round(g.area, 10)}"
    guardado = cache.leer("mgap_suelos_area", clave, max_dias=180)
    if guardado:
        return guardado
    anillos = []
    for pol in getattr(g, "geoms", [g]):
        anillos.append([list(c) for c in pol.exterior.coords])
    params = {
        "geometry": json.dumps({"rings": anillos, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPolygon", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
        "outFields": "SC,IND_CONEAT", "returnGeometry": "true", "outSR": 4326, "f": "json",
    }
    r = httpx.post(f"{BASE}/CONEAT/ConsultaConeat/MapServer/0/query", data=params, timeout=TIMEOUT_PADRON)
    r.raise_for_status()
    por_grupo: dict[str, list] = {}
    for f in _esri_a_geojson(r.json()).get("features", []):
        if not f.get("geometry"):
            continue
        parte = shape(f["geometry"]).buffer(0).intersection(g)
        if not parte.is_empty and parte.area > 0:
            por_grupo.setdefault(f["properties"].get("SC") or "s/d", []).append(parte)
    total = sum(unary_union(v).area for v in por_grupo.values()) or 1
    partes = sorted(({"grupo_coneat": k, "fraccion": round(unary_union(v).area / total, 3),
                      "geometria": mapping(unary_union(v))} for k, v in por_grupo.items()),
                    key=lambda p: -p["fraccion"])
    salida = {"ok": True, "fuente": "MGAP-DGRN, CONEAT/ConsultaConeat (grupos de suelo)", "partes": partes}
    cache.guardar("mgap_suelos_area", clave, salida)
    return salida


def punto_del_suelo_mayor(partes: list[dict], lat: float, lon: float) -> tuple[float, float]:
    """El punto donde mirar el suelo de un lote: adentro del grupo CONEAT que ocupa más superficie. Si el punto que ya
    se tenía cae en ese grupo, queda ese (no cambia nada en los lotes de un solo suelo). `partes` viene de
    `suelos_en_area`, de mayor a menor. Aparte para probarla sin internet."""
    if not partes:
        return lat, lon
    from shapely.geometry import Point

    mayor = shape(partes[0]["geometria"]).buffer(0)
    if mayor.is_empty or mayor.contains(Point(lon, lat)):
        return lat, lon
    p = mayor.representative_point()
    return p.y, p.x


def suelo_seccion(geometria: dict, lat: float, lon: float) -> dict:
    """Suelo de un lote entero. `suelo_punto` mira un
    solo punto, que en un lote con varios grupos CONEAT puede caer en uno chico; acá se mira adentro del grupo que
    ocupa más superficie. Si la consulta por área falla, queda el punto de siempre."""
    try:
        partes = (suelos_en_area(geometria) or {}).get("partes") or []
        la, lo = punto_del_suelo_mayor(partes, lat, lon)
    except Exception:  # noqa: BLE001 — el MGAP se cae seguido
        partes, la, lo = [], lat, lon
    s = suelo_punto(la, lo)
    if not s.get("ok") and (la, lo) != (lat, lon):
        s = suelo_punto(lat, lon)
    if s.get("ok") and len(partes) > 1:
        s = {**s, "grupos_en_el_lote": [{"grupo_coneat": p["grupo_coneat"], "pct": round(100 * p["fraccion"])} for p in partes[:5]]}
    return s


def estaciones_r() -> list[dict]:
    """Las 19 estaciones con factor R oficial (EROSION/FACTOR_R). Cacheado un año."""
    guardado = cache.leer("mgap_r", "todas", max_dias=365)
    if guardado:
        return guardado
    params = {"where": "1=1", "outFields": "POB,r", "returnGeometry": "true", "outSR": 4326, "f": "json"}
    r = httpx.get(f"{BASE}/EROSION/FACTOR_R/MapServer/0/query", params=params, timeout=TIMEOUT_FACTOR_R)
    r.raise_for_status()
    est = [
        {"nombre": f["attributes"]["POB"], "r": _num(f["attributes"]["r"]),
         "lat": f["geometry"]["y"], "lon": f["geometry"]["x"]}
        for f in r.json().get("features", [])
        if _num(f["attributes"].get("r")) is not None
    ]
    cache.guardar("mgap_r", "todas", est)
    return est


LEJOS_DE_ESTACION_KM = 150  # Uruguay mide unos 500 km de punta a punta y hay 19 estaciones


def factor_r(lat: float, lon: float) -> dict | None:
    """R oficial interpolado (inverso de la distancia al cuadrado, 3 estaciones más cercanas).

    Unidades del MGAP: R en (MJ·mm/ha·h·año)/10 y K en (t·ha·h/ha·MJ·mm)×10, de modo que
    A = R × K × LS × C × P sale en t/ha/año. Comprobado al comparar: la estación Durazno da 491 y
    la estimación propia con lluvia diaria de NASA POWER da 4.895 MJ·mm/ha·h·año (= 489,5).
    """
    try:
        est = estaciones_r()
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    if not est:
        return None
    import math

    def dist(e):
        dx = (e["lon"] - lon) * math.cos(math.radians(lat)) * 111.3
        dy = (e["lat"] - lat) * 111.3
        return math.hypot(dx, dy)

    cerca = sorted(est, key=dist)[:3]
    ds = [max(dist(e), 1.0) for e in cerca]
    # Fuera de Uruguay (o lejos de toda estación) el R de otro clima no sirve: se estima con la lluvia
    if ds[0] > LEJOS_DE_ESTACION_KM:
        return None
    pesos = [1 / d**2 for d in ds]
    r = sum(e["r"] * w for e, w in zip(cerca, pesos)) / sum(pesos)
    return {
        "r": round(r),
        "estaciones": [{"nombre": e["nombre"], "r": e["r"], "km": round(d)} for e, d in zip(cerca, ds)],
        "fuente": "MGAP-DGRN, EROSION/FACTOR_R (19 estaciones), interpolado",
    }


def departamentos() -> dict:
    """Límites de los 19 departamentos (BASE/Administrativo, capa 13) para dibujarlos en el
    mapa. Lee la copia guardada en fieldshift/datos/departamentos_uy.json (scripts/actualizar_departamentos.py la renueva)."""
    ruta = Path(__file__).resolve().parent.parent / "datos" / "departamentos_uy.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def _esri_a_geojson(js: dict) -> dict:
    """Esri JSON → GeoJSON. En Esri los anillos exteriores van en sentido horario y los huecos
    al revés; un mismo registro puede tener varias partes exteriores."""
    feats = []
    for f in js.get("features", []):
        g = f.get("geometry") or {}
        if "rings" not in g:
            continue
        exteriores: list[Polygon] = []
        huecos: list[Polygon] = []
        for anillo in g["rings"]:
            if len(anillo) < 4:
                continue
            lr = LinearRing(anillo)
            (huecos if lr.is_ccw else exteriores).append(Polygon(anillo))
        partes = []
        for ext in exteriores:
            adentro = [h.exterior.coords for h in huecos if ext.contains(h.representative_point())]
            partes.append(Polygon(ext.exterior.coords, adentro).buffer(0))
        if not partes:
            continue
        geom = unary_union(partes)
        feats.append({"type": "Feature", "properties": f.get("attributes", {}), "geometry": mapping(geom)})
    return {"type": "FeatureCollection", "features": feats}


if __name__ == "__main__":
    print(json.dumps(suelo_punto(-33.38, -56.52), ensure_ascii=False, indent=1))
