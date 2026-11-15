"""Qué se sembró cada año en un lote de EE. UU.: Cropland Data Layer del USDA-NASS.

El CDL clasifica cada píxel de 30 m de los 48 estados contiguos por cultivo, año por año (en Earth Engine,
`USDA/NASS/CDL`, de 2008 a 2025 para todo el país). Es el par del historial que cuenta el productor en Uruguay: con
esto la app sabe qué rotación hace hoy cada lote sin preguntarle. Probado en el suroeste de Iowa: se ve
el maíz-soja alternado de 2008 a 2025 y los lotes que pasaron de pastura a agricultura.

Por cada año da la clase que cubre más superficie de la sección y su porcentaje, y la pasa a los cultivos de la app
(invierno, verano). El CDL no ve los cultivos de cobertura (no se cosechan): el invierno queda en barbecho salvo que
la clase sea un trigo o una doble cosecha. Lo que no está en el catálogo de la app (algodón, por ejemplo) vuelve con
`verano = None` y su nombre del USDA.

Cómo se consulta: por la API REST de Earth Engine con expresiones ya serializadas (`datos/plantillas_ee/`, las arma
`scripts/plantillas_ee_cdl.py`), igual que GLDAS y HLS: en Vercel no está la librería `earthengine-api`. Solo se
cambia el nodo de la geometría.

Licencia: dominio público (USDA-NASS).
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import logging
from pathlib import Path

import httpx

from .. import cache
from . import modis_historia

logger = logging.getLogger(__name__)

COLECCION = "USDA/NASS/CDL"
DESDE = 2008  # desde 2008 cubre los 48 estados

# código del CDL → (nombre del USDA, invierno, verano) en códigos de la app
CLASES: dict[int, tuple[str, str | None, str | None]] = {
    1: ("Corn", "barbecho", "maiz"),
    4: ("Sorghum", "barbecho", "sorgo"),
    5: ("Soybeans", "barbecho", "soja"),
    6: ("Sunflower", "barbecho", "girasol"),
    21: ("Barley", "cebada", "barbecho"),
    23: ("Spring Wheat", "barbecho", None),
    24: ("Winter Wheat", "trigo", "barbecho"),
    26: ("Dbl Crop WinWht/Soybeans", "trigo", "soja2"),
    27: ("Rye", "cobertura", "barbecho"),
    28: ("Oats", "cebada", "barbecho"),
    31: ("Canola", "colza", "barbecho"),
    36: ("Alfalfa", "alfalfa", "alfalfa"),
    37: ("Other Hay/Non Alfalfa", "pradera", "pradera"),
    61: ("Fallow/Idle Cropland", "barbecho", "barbecho"),
    176: ("Grassland/Pasture", "campo_natural", "campo_natural"),
    225: ("Dbl Crop WinWht/Corn", "trigo", "maiz2"),
    236: ("Dbl Crop WinWht/Sorghum", "trigo", "sorgo"),
    237: ("Dbl Crop Barley/Corn", "cebada", "maiz2"),
    254: ("Dbl Crop Barley/Soybeans", "cebada", "soja2"),
    2: ("Cotton", "barbecho", None),
    3: ("Rice", "barbecho", None),
    12: ("Sweet Corn", "barbecho", "maiz"),
    121: ("Developed/Open Space", None, None),
    122: ("Developed/Low Intensity", None, None),
    141: ("Deciduous Forest", None, None),
    111: ("Open Water", None, None),
}


def _clave(geojson: dict) -> str:
    return hashlib.sha1(json.dumps(geojson, sort_keys=True).encode()).hexdigest()[:20]


def anio_a_cultivos(codigo: int | None) -> dict:
    nombre, inv, ver = CLASES.get(codigo or -1, (f"clase {codigo} del CDL", None, None))
    return {"codigo_cdl": codigo, "nombre_cdl": nombre, "invierno": inv, "verano": ver}


def interpretar(histogramas: dict[str, dict]) -> list[dict]:
    """{"2008": {"1": 812, "5": 40}...} (píxeles por clase) → un renglón por año, del más viejo al más nuevo."""
    filas = []
    for anio in sorted(histogramas, key=int):
        h = {int(float(k)): v for k, v in (histogramas[anio] or {}).items()}
        total = sum(h.values())
        if not total:
            continue
        codigo = max(h, key=h.get)
        filas.append({"anio": int(anio), **anio_a_cultivos(codigo), "pct": round(100 * h[codigo] / total)})
    return filas


def historial(geojson: dict, anios: int = 4) -> list[dict]:
    """Los últimos `anios` años en el formato de historial del productor ([{anio, invierno, verano}]), solo con los
    años en que la clase dominante es un cultivo del catálogo."""
    filas = por_anio(geojson).get("anios") or []
    utiles = [f for f in filas if f.get("verano") and f.get("invierno")]
    return [{"anio": f["anio"], "invierno": f["invierno"], "verano": f["verano"]} for f in utiles[-anios:]]


_PLANTILLAS = Path(__file__).resolve().parents[1] / "datos" / "plantillas_ee"


@functools.lru_cache(maxsize=4)
def _plantilla(nombre: str) -> dict:
    return json.loads((_PLANTILLAS / f"{nombre}.json").read_text(encoding="utf-8"))


def _nodo_geometria(geojson: dict) -> dict:
    tipo = geojson["type"]
    if tipo not in ("Point", "Polygon", "MultiPolygon"):
        raise ValueError(f"geometría {tipo} no soportada")
    args = {"coordinates": {"constantValue": geojson["coordinates"]}}
    if tipo != "Point":
        args["evenOdd"] = {"constantValue": True}
    return {"functionInvocationValue": {"functionName": f"GeometryConstructors.{tipo}", "arguments": args}}


def _con_geometria(nombre: str, geojson: dict) -> dict:
    """La plantilla con su geometría de relleno (el nodo GeometryConstructors.*) cambiada por la del pedido."""
    nodo = _nodo_geometria(geojson)

    def recorrer(x):
        if isinstance(x, dict):
            f = x.get("functionInvocationValue")
            if isinstance(f, dict) and str(f.get("functionName", "")).startswith("GeometryConstructors."):
                return nodo
            return {k: recorrer(v) for k, v in x.items()}
        if isinstance(x, list):
            return [recorrer(v) for v in x]
        return x

    expr = recorrer(copy.deepcopy(_plantilla(nombre)))
    # las coordenadas repetidas del relleno quedaban como valores sueltos: se dejan solo los que se usan
    def refs(x):
        if isinstance(x, dict):
            if "valueReference" in x:
                yield x["valueReference"]
            if isinstance(x.get("functionDefinitionValue"), dict):  # el cuerpo de una función (los map)
                yield x["functionDefinitionValue"]["body"]
            for v in x.values():
                yield from refs(v)
        elif isinstance(x, list):
            for v in x:
                yield from refs(v)

    usados, pila = set(), [expr["result"]]
    while pila:
        k = pila.pop()
        if k not in usados:
            usados.add(k)
            pila.extend(refs(expr["values"][k]))
    expr["values"] = {k: v for k, v in expr["values"].items() if k in usados}
    return expr


def _calcular(expr: dict, timeout: float = 60) -> object:
    """value:compute de Earth Engine con el token de la cuenta de servicio (sin la librería `earthengine-api`)."""
    sa = modis_historia._cargar_sa_info()
    if not sa:
        raise RuntimeError("Earth Engine no está disponible (falta la cuenta de servicio).")
    proyecto = sa.get("project_id") or modis_historia.PROJECT_ID_EE
    r = httpx.post(f"https://earthengine.googleapis.com/v1/projects/{proyecto}/value:compute",
                   json={"expression": expr}, timeout=timeout,
                   headers={"Authorization": f"Bearer {modis_historia._token_bearer_sa(sa)}",
                            "X-Goog-User-Project": proyecto})
    if r.status_code >= 400:
        raise RuntimeError(f"Earth Engine respondió {r.status_code}: {r.text[:300]}")
    return r.json().get("result")


def por_anio(geojson: dict) -> dict:
    """Clase dominante del CDL en la sección, de 2008 al último año publicado. Cacheado 90 días."""
    clave = _clave(geojson)
    guardado = cache.leer("cdl", clave, max_dias=90)
    if guardado:
        return guardado
    try:
        feats = (_calcular(_con_geometria("cdl_por_anio", geojson)) or {}).get("features") or []
        histos = {f["properties"]["anio"]: f["properties"].get("h") or {} for f in feats}
    except Exception as e:  # noqa: BLE001 — Earth Engine puede tardar o fallar; la app sigue con el NDVI
        logger.warning("CDL: %s", e)
        return {"ok": False, "error": f"CDL: {e}", "anios": []}
    salida = {"ok": True, "fuente": "USDA-NASS Cropland Data Layer (30 m) vía Google Earth Engine",
              "anios": interpretar(histos)}
    cache.guardar("cdl", clave, salida)
    return salida


# lo que no es un lote agrícola, con su nombre para el aviso
NO_CULTIVO = {111: "agua", 121: "zona urbana", 122: "zona urbana", 123: "zona urbana", 124: "zona urbana",
              131: "suelo desnudo", 141: "monte", 142: "monte", 143: "monte", 152: "matorral", 190: "humedal",
              195: "humedal"}


def lote_en_punto(lat: float, lon: float, radio_m: int = 1500) -> dict:
    """El lote que contiene el punto, según el Cropland Data Layer: los píxeles contiguos que tuvieron la
    misma secuencia de cultivos los últimos tres años publicados, suavizados. En EE. UU. no hay un catastro público de
    lotes (el CLU del USDA es reservado): es el par del padrón del MGAP. Dos lotes vecinos con la misma secuencia
    salen juntos; el productor lo corrige en el mapa."""
    from shapely.geometry import Point, mapping, shape

    from ..analisis.plan import area_ha

    clave = f"{lat:.4f},{lon:.4f}"
    guardado = cache.leer("cdl_lote", clave, max_dias=90)
    if guardado:
        return guardado
    try:
        res = _calcular(_con_geometria("cdl_lote", {"type": "Point", "coordinates": [lon, lat]})) or {}
    except Exception as e:  # noqa: BLE001
        logger.warning("CDL lote: %s", e)
        if "may not be null" in str(e):  # sin píxel del CDL en el punto (mar, Canadá, México)
            return {"ok": False, "error": "El Cropland Data Layer no tiene datos en ese punto (¿fuera de EE. UU.?)."}
        return {"ok": False, "error": f"No pude leer el Cropland Data Layer: {e}"}
    props = res.get("properties") or {}
    valor, ultimo = props.get("valor"), int(props.get("ultimo") or 0)
    if valor is None:
        return {"ok": False, "error": "El Cropland Data Layer no tiene datos en ese punto (¿fuera de EE. UU.?)."}
    anios = [ultimo - 2, ultimo - 1, ultimo]
    codigos = [int(valor) // 1000000, (int(valor) // 1000) % 1000, int(valor) % 1000]
    if codigos[0] in NO_CULTIVO and codigos[1] in NO_CULTIVO:
        return {"ok": False, "error": f"Ahí no hay un lote agrícola según el CDL ({NO_CULTIVO[codigos[0]]}). "
                                      "Tocá dentro de la chacra."}
    feats = res.get("features") or []
    if not feats:
        return {"ok": False, "error": "No encontré un lote en ese punto."}
    g = shape(feats[0]["geometry"])
    # suavizado: saca los dientes de 30 m y los píxeles sueltos; si se rompe en partes, queda la que tiene el punto
    g = g.buffer(0.0003).buffer(-0.0006).buffer(0.0003).simplify(0.0002)
    if g.geom_type == "MultiPolygon":
        g = next((p for p in g.geoms if p.contains(Point(lon, lat))), max(g.geoms, key=lambda p: p.area))
    if g.is_empty:
        return {"ok": False, "error": "El lote es demasiado chico para el CDL (píxeles de 30 m)."}
    contorno = mapping(g)
    salida = {
        "ok": True,
        "fuente": "USDA-NASS Cropland Data Layer (30 m) vía Google Earth Engine",
        "contorno": contorno,
        "area_ha": round(area_ha(contorno), 1),
        "anios": [{"anio": a, **anio_a_cultivos(c)} for a, c in zip(anios, reversed(codigos))],
    }
    cache.guardar("cdl_lote", clave, salida)
    return salida
