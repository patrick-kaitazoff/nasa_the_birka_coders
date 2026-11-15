"""NDVI de HLS (Harmonized Landsat Sentinel-2, 30 m) vía Google Earth Engine.

Promedia el NDVI sobre TODO el polígono de cada sección a escala 30 m (últimos 3 años, mensual).
Resuelve el problema de MODIS (250 m, un punto): en secciones de menos de ~10 ha MODIS mezcla
bordes y lotes vecinos.

Colecciones: NASA/HLS/HLSL30/v002 y NASA/HLS/HLSS30/v002.
Bandas: L30 (roja B4, NIR B5), S30 (roja B4, NIR B8A).
Máscara de nubes: Fmask (bits 1, 2, 3 libres de nubes y sombras).
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import logging
import math
import os
from typing import Any

import httpx

from .. import cache
from . import modis_historia

logger = logging.getLogger(__name__)

COLECCION_L30 = "NASA/HLS/HLSL30/v002"
COLECCION_S30 = "NASA/HLS/HLSS30/v002"
MESES_HISTORIA = 36  # 3 años
TIMEOUT_EE_S = 35.0

try:
    import ee
    HAY_EE = True
except ImportError:
    ee = None  # type: ignore[assignment]
    HAY_EE = False


def _mes_actual() -> str:
    """Primer día del mes en curso: la serie llega hasta el último mes entero."""
    return dt.date.today().replace(day=1).isoformat()


def _ee_desactivado() -> bool:
    """DESACTIVAR_EE=1 apaga Earth Engine, igual que en modis_historia (las pruebas lo usan para no salir a internet)."""
    return os.environ.get("DESACTIVAR_EE") == "1"


def _extraer_anillo_exterior(geometria: dict) -> list[list[float]]:
    """Extrae las coordenadas del anillo exterior (lon, lat) de un Polygon o MultiPolygon GeoJSON."""
    tipo = geometria.get("type")
    coords = geometria.get("coordinates")
    if not coords:
        raise ValueError("Geometría sin coordenadas")
    if tipo == "Polygon":
        anillo = coords[0]
    elif tipo == "MultiPolygon":
        # Tomar el polígono con más puntos (el más grande)
        anillo = max(coords, key=lambda p: len(p[0]))[0]
    else:
        raise ValueError(f"Tipo de geometría no soportado para HLS: {tipo}")

    # Asegurar que esté cerrado
    if anillo and anillo[0] != anillo[-1]:
        anillo = list(anillo) + [anillo[0]]
    # Redondear a 5 decimales (~1 m)
    return [[round(float(p[0]), 5), round(float(p[1]), 5)] for p in anillo]


def _clave_cache(coords: list[list[float]], hoy_str: str) -> str:
    txt = f"{hoy_str}:" + ",".join(f"{p[0]}:{p[1]}" for p in coords)
    return hashlib.sha1(txt.encode("utf-8")).hexdigest()[:16]


def _armar_con_cliente_ee(coords: list[list[float]], hoy_str: str) -> dict:
    """Genera la expresión serializada de EE usando el cliente Python (ee.serializer.encode)."""
    poly = ee.Geometry.Polygon([coords])
    hoy = ee.Date(hoy_str)
    meses_atras = ee.List.sequence(0, MESES_HISTORIA - 1)

    def calc_mes(n):
        fin = hoy.advance(ee.Number(n).multiply(-1), "month")
        ini = fin.advance(-1, "month")
        l30 = (
            ee.ImageCollection(COLECCION_L30)
            .filterBounds(poly)
            .filterDate(ini, fin)
            .map(
                lambda img: img.normalizedDifference(["B5", "B4"])
                .rename("NDVI")
                .updateMask(img.select("Fmask").bitwiseAnd(14).eq(0))
            )
        )
        s30 = (
            ee.ImageCollection(COLECCION_S30)
            .filterBounds(poly)
            .filterDate(ini, fin)
            .map(
                lambda img: img.normalizedDifference(["B8A", "B4"])
                .rename("NDVI")
                .updateMask(img.select("Fmask").bitwiseAnd(14).eq(0))
            )
        )
        med = l30.merge(s30).median()
        val = med.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=poly, scale=30, maxPixels=1e6
        ).get("NDVI")
        return ee.Dictionary({"anio": ini.get("year"), "mes": ini.get("month"), "ndvi": val})

    resultado = ee.List(meses_atras.map(calc_mes))
    return ee.serializer.encode(resultado, for_cloud_api=True)


# Plantilla base pre-serializada con ee.serializer.encode para entornos sin earthengine-api (Vercel)
# Los nodos variables son: fecha de referencia (nodo 3) y polígono (nodo 5).
_PLANTILLA_EXPRESION_BASE: dict[str, Any] = {'result': '0', 'values': {'4': {'constantValue': 'month'}, '3': {'functionInvocationValue': {'functionName': 'Date.advance', 'arguments': {'date': {'functionInvocationValue': {'functionName': 'Date', 'arguments': {'value': {'constantValue': '2026-11-15'}}}}, 'delta': {'functionInvocationValue': {'functionName': 'Number.multiply', 'arguments': {'left': {'argumentReference': '_MAPPING_VAR_2_0'}, 'right': {'constantValue': -1}}}}, 'unit': {'valueReference': '4'}}}}, '2': {'functionInvocationValue': {'functionName': 'Date.advance', 'arguments': {'date': {'valueReference': '3'}, 'delta': {'constantValue': -1}, 'unit': {'valueReference': '4'}}}}, '6': {'constantValue': [-56.15, -33.1]}, '5': {'functionInvocationValue': {'functionName': 'GeometryConstructors.Polygon', 'arguments': {'coordinates': {'arrayValue': {'values': [{'arrayValue': {'values': []}}]}}, 'evenOdd': {'constantValue': True}}}}, '8': {'constantValue': 'B4'}, '10': {'constantValue': 'NDVI'}, '9': {'arrayValue': {'values': [{'valueReference': '10'}]}}, '11': {'functionInvocationValue': {'functionName': 'Image.eq', 'arguments': {'image1': {'functionInvocationValue': {'functionName': 'Image.bitwiseAnd', 'arguments': {'image1': {'functionInvocationValue': {'functionName': 'Image.select', 'arguments': {'bandSelectors': {'constantValue': ['Fmask']}, 'input': {'argumentReference': '_MAPPING_VAR_0_0'}}}}, 'image2': {'functionInvocationValue': {'functionName': 'Image.constant', 'arguments': {'value': {'constantValue': 14}}}}}}}, 'image2': {'functionInvocationValue': {'functionName': 'Image.constant', 'arguments': {'value': {'constantValue': 0}}}}}}}, '7': {'functionInvocationValue': {'functionName': 'Image.updateMask', 'arguments': {'image': {'functionInvocationValue': {'functionName': 'Image.rename', 'arguments': {'input': {'functionInvocationValue': {'functionName': 'Image.normalizedDifference', 'arguments': {'bandNames': {'arrayValue': {'values': [{'constantValue': 'B5'}, {'valueReference': '8'}]}}, 'input': {'argumentReference': '_MAPPING_VAR_0_0'}}}}, 'names': {'valueReference': '9'}}}}, 'mask': {'valueReference': '11'}}}}, '12': {'functionInvocationValue': {'functionName': 'Filter.intersects', 'arguments': {'leftField': {'constantValue': '.all'}, 'rightValue': {'functionInvocationValue': {'functionName': 'Feature', 'arguments': {'geometry': {'valueReference': '5'}}}}}}}, '13': {'functionInvocationValue': {'functionName': 'Filter.dateRangeContains', 'arguments': {'leftValue': {'functionInvocationValue': {'functionName': 'DateRange', 'arguments': {'end': {'valueReference': '3'}, 'start': {'valueReference': '2'}}}}, 'rightField': {'constantValue': 'system:time_start'}}}}, '14': {'functionInvocationValue': {'functionName': 'Image.updateMask', 'arguments': {'image': {'functionInvocationValue': {'functionName': 'Image.rename', 'arguments': {'input': {'functionInvocationValue': {'functionName': 'Image.normalizedDifference', 'arguments': {'bandNames': {'arrayValue': {'values': [{'constantValue': 'B8A'}, {'valueReference': '8'}]}}, 'input': {'argumentReference': '_MAPPING_VAR_0_0'}}}}, 'names': {'valueReference': '9'}}}}, 'mask': {'valueReference': '11'}}}}, '1': {'dictionaryValue': {'values': {'anio': {'functionInvocationValue': {'functionName': 'Date.get', 'arguments': {'date': {'valueReference': '2'}, 'unit': {'constantValue': 'year'}}}}, 'mes': {'functionInvocationValue': {'functionName': 'Date.get', 'arguments': {'date': {'valueReference': '2'}, 'unit': {'valueReference': '4'}}}}, 'ndvi': {'functionInvocationValue': {'functionName': 'Dictionary.get', 'arguments': {'dictionary': {'functionInvocationValue': {'functionName': 'Image.reduceRegion', 'arguments': {'geometry': {'valueReference': '5'}, 'image': {'functionInvocationValue': {'functionName': 'reduce.median', 'arguments': {'collection': {'functionInvocationValue': {'functionName': 'ImageCollection.merge', 'arguments': {'collection1': {'functionInvocationValue': {'functionName': 'Collection.map', 'arguments': {'baseAlgorithm': {'functionDefinitionValue': {'argumentNames': ['_MAPPING_VAR_0_0'], 'body': '7'}}, 'collection': {'functionInvocationValue': {'functionName': 'Collection.filter', 'arguments': {'collection': {'functionInvocationValue': {'functionName': 'Collection.filter', 'arguments': {'collection': {'functionInvocationValue': {'functionName': 'ImageCollection.load', 'arguments': {'id': {'constantValue': 'NASA/HLS/HLSL30/v002'}}}}, 'filter': {'valueReference': '12'}}}}, 'filter': {'valueReference': '13'}}}}}}}, 'collection2': {'functionInvocationValue': {'functionName': 'Collection.map', 'arguments': {'baseAlgorithm': {'functionDefinitionValue': {'argumentNames': ['_MAPPING_VAR_0_0'], 'body': '14'}}, 'collection': {'functionInvocationValue': {'functionName': 'Collection.filter', 'arguments': {'collection': {'functionInvocationValue': {'functionName': 'Collection.filter', 'arguments': {'collection': {'functionInvocationValue': {'functionName': 'ImageCollection.load', 'arguments': {'id': {'constantValue': 'NASA/HLS/HLSS30/v002'}}}}, 'filter': {'valueReference': '12'}}}}, 'filter': {'valueReference': '13'}}}}}}}}}}}}}, 'maxPixels': {'constantValue': 1000000.0}, 'reducer': {'functionInvocationValue': {'functionName': 'Reducer.mean', 'arguments': {}}}, 'scale': {'constantValue': 30}}}}, 'key': {'valueReference': '10'}}}}}}}, '0': {'functionInvocationValue': {'functionName': 'List.map', 'arguments': {'baseAlgorithm': {'functionDefinitionValue': {'argumentNames': ['_MAPPING_VAR_2_0'], 'body': '1'}}, 'dropNulls': {'constantValue': False}, 'list': {'functionInvocationValue': {'functionName': 'List.sequence', 'arguments': {'end': {'constantValue': 35}, 'start': {'constantValue': 0}}}}}}}}}


def _asegurar_ee_inicializado(sa_info: dict | None = None) -> bool:
    global HAY_EE
    if not HAY_EE or ee is None or _ee_desactivado():
        return False
    try:
        ee.data.get_cloud_projects()
        return True
    except Exception:
        pass
    if not sa_info:
        sa_info = modis_historia._cargar_sa_info()
    if not sa_info:
        return False
    try:
        creds = ee.ServiceAccountCredentials(sa_info["client_email"], key_data=json.dumps(sa_info))
        ee.Initialize(credentials=creds, project=sa_info.get("project_id"))
        return True
    except Exception as e:
        logger.debug(f"No se pudo inicializar ee con SA: {e}")
        return False


def armar_expresion_hls(coords: list[list[float]], hoy_str: str | None = None, sa_info: dict | None = None) -> dict:
    """Construye el grafo serializado de EE para value:compute. Sin `hoy_str`, hasta el mes en curso."""
    hoy_str = hoy_str or _mes_actual()
    if HAY_EE and _asegurar_ee_inicializado(sa_info):
        try:
            return _armar_con_cliente_ee(coords, hoy_str)
        except Exception as e:
            logger.debug(f"No se pudo usar ee client para serializar ({e}); usando plantilla pre-serializada")

    # Inyección en plantilla pre-serializada (sin requerir ee)
    expr = copy.deepcopy(_PLANTILLA_EXPRESION_BASE)
    expr["values"]["3"]["functionInvocationValue"]["arguments"]["date"]["functionInvocationValue"]["arguments"]["value"]["constantValue"] = hoy_str
    coords_values = [{"constantValue": pt} for pt in coords]
    expr["values"]["5"]["functionInvocationValue"]["arguments"]["coordinates"]["arrayValue"]["values"][0]["arrayValue"]["values"] = coords_values
    return expr


def _calcular_coincidencia(hls_mensual: list[dict], modis_mensual: list[dict] | None) -> dict:
    """Calcula la correlación y coincidencia entre HLS (30 m polígono) y MODIS (250 m punto)."""
    if not modis_mensual:
        return {"correlacion": None, "dif_media": None, "coincidencia_pct": None, "meses_comunes": 0}

    mapa_modis = {(m["anio"], m["mes"]): m["ndvi"] for m in modis_mensual if m.get("ndvi") is not None}
    pares = []
    for h in hls_mensual:
        clv = (h["anio"], h["mes"])
        if clv in mapa_modis and h.get("ndvi") is not None:
            pares.append((float(h["ndvi"]), float(mapa_modis[clv])))

    if len(pares) < 6:
        return {"correlacion": None, "dif_media": None, "coincidencia_pct": None, "meses_comunes": len(pares)}

    h_vals = [p[0] for p in pares]
    m_vals = [p[1] for p in pares]
    dif_media = sum(abs(a - b) for a, b in pares) / len(pares)

    # Correlación de Pearson
    h_m = sum(h_vals) / len(h_vals)
    m_m = sum(m_vals) / len(m_vals)
    cov = sum((a - h_m) * (b - m_m) for a, b in pares)
    var_h = sum((a - h_m) ** 2 for a, b in pares)
    var_m = sum((b - m_m) ** 2 for a, b in pares)
    denom = math.sqrt(var_h * var_m)
    r = round(cov / denom, 2) if denom > 1e-6 else None

    # Coincidencia porcentual (100 % menos el error medio relativo)
    prom_nivel = max(0.2, (h_m + m_m) / 2.0)
    coincidencia = max(0, min(100, round((1.0 - (dif_media / prom_nivel)) * 100)))

    return {
        "correlacion": r,
        "dif_media": round(dif_media, 3),
        "coincidencia_pct": coincidencia,
        "meses_comunes": len(pares),
    }


def consultar_hls_seccion(
    geometria: dict,
    modis_mensual: list[dict] | None = None,
    hoy_str: str | None = None,
) -> dict:
    """Consulta el NDVI mensual de HLS (últimos 3 años, mediana) sobre el polígono de la sección.

    Usa la cuenta de servicio de Earth Engine y la API value:compute. Guarda en caché (90 días).
    Si Earth Engine falla, devuelve ok: False con el motivo para que la app siga con MODIS.
    """
    if _ee_desactivado():
        return {"ok": False, "error": "Earth Engine desactivado (DESACTIVAR_EE=1)"}
    hoy_str = hoy_str or _mes_actual()
    try:
        coords = _extraer_anillo_exterior(geometria)
    except Exception as e:
        return {"ok": False, "error": f"Geometría inválida: {e}"}

    clave = _clave_cache(coords, hoy_str)
    guardado = cache.leer("hls_ndvi", clave, max_dias=90)
    if guardado:
        # Calcular/actualizar coincidencia con modis si vino en la llamada
        coinc = _calcular_coincidencia(guardado.get("mensual") or [], modis_mensual)
        return {**guardado, **coinc, "desde_cache": True}

    sa_info = modis_historia._cargar_sa_info()
    if not sa_info:
        return {"ok": False, "error": "Sin credenciales de Google Earth Engine (.secretos/)"}

    try:
        token = modis_historia._token_bearer_sa(sa_info)
        project_id = sa_info.get("project_id") or modis_historia.PROJECT_ID_EE
        expr = armar_expresion_hls(coords, hoy_str, sa_info=sa_info)
        url = f"https://earthengine.googleapis.com/v1/projects/{project_id}/value:compute"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Goog-User-Project": project_id,
            "Content-Type": "application/json",
        }
        resp = httpx.post(url, json={"expression": expr}, headers=headers, timeout=TIMEOUT_EE_S)
        resp.raise_for_status()
        raw_items = resp.json().get("result", [])
    except Exception as e:
        logger.warning(f"Error consultando HLS en Earth Engine: {e}")
        return {"ok": False, "error": f"Falla en Earth Engine: {e}"}

    # Procesar y ordenar cronológicamente
    procesados = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        anio, mes, val = item.get("anio"), item.get("mes"), item.get("ndvi")
        if anio is not None and mes is not None:
            procesados.append({
                "anio": int(anio),
                "mes": int(mes),
                "ndvi": round(float(val), 3) if val is not None else None,
            })

    procesados.sort(key=lambda x: x["anio"] * 12 + x["mes"])

    coinc = _calcular_coincidencia(procesados, modis_mensual)
    salida = {
        "ok": True,
        "mensual": procesados,
        "fuente": "NASA HLS v002 (Landsat 8-9 + Sentinel-2, 30 m) vía Google Earth Engine",
        **coinc,
    }

    cache.guardar("hls_ndvi", clave, salida)
    return salida
