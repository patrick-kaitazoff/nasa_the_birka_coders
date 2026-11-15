"""Fechas con imagen limpia de HLS (Landsat + Sentinel-2 armonizados, 30 m) sobre un campo.

Para qué: el fondo "NASA" del mapa. El color real diario de MODIS (250 m) no sirve a escala de
chacra: un campo de 50 ha son unos 8 píxeles, y la imagen del día casi siempre tiene nubes o
franjas negras entre pasadas. HLS tiene 30 m y GIBS lo sirve
como mosaico por día (capas `HLS_L30_...` y `HLS_S30_...`, hasta el nivel 12), sin cuenta.

El problema es elegir el día: GIBS muestra lo que haya ese día, nubes incluidas. Acá se busca en
CMR (catálogo de la NASA, sin cuenta) cada pasada que toca el campo, con el % de nubes de la
escena, y se devuelve la más limpia de cada mes del último año.

Límite: el % de nubes es de toda la escena (110 × 110 km), no del campo. Una escena con 15 % puede
tener justo la nube encima. Para mirarlo a nivel de campo hace falta bajar la máscara Fmask
(con Earthdata Login); no se hace.
"""

from __future__ import annotations

import datetime as dt

import httpx

from .. import cache

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
COLECCIONES = {"L30": ("HLSL30", "Landsat"), "S30": ("HLSS30", "Sentinel-2")}
CAPA_GIBS = {"L30": "HLS_L30_Nadir_BRDF_Adjusted_Reflectance", "S30": "HLS_S30_Nadir_BRDF_Adjusted_Reflectance"}
MAX_NUBES = 25  # % de la escena; por encima casi nunca se ve el campo


def _pasadas(coleccion: str, bbox: tuple[float, float, float, float], desde: dt.date) -> list[dict]:
    corto, _ = COLECCIONES[coleccion]
    salida: list[dict] = []
    pagina = 1
    while pagina <= 5:
        r = httpx.get(CMR, params={
            "short_name": corto, "version": "2.0",
            "bounding_box": ",".join(f"{v:.5f}" for v in bbox),
            "temporal": f"{desde.isoformat()}T00:00:00Z,",
            "page_size": 200, "page_num": pagina, "sort_key": "-start_date",
        }, timeout=60)
        r.raise_for_status()
        entradas = r.json().get("feed", {}).get("entry", [])
        for e in entradas:
            try:
                nubes = float(e.get("cloud_cover"))
            except (TypeError, ValueError):
                continue
            salida.append({"fecha": e["time_start"][:10], "nubes": nubes, "sensor": coleccion})
        if len(entradas) < 200:
            break
        pagina += 1
    return salida


def fechas_limpias(bbox: tuple[float, float, float, float], meses: int = 12) -> dict:
    """bbox = (oeste, sur, este, norte). Devuelve la pasada más limpia de cada mes, la más nueva primero."""
    x0, y0, x1, y1 = (round(v, 3) for v in bbox)
    hoy = dt.date.today()
    clave = f"{x0},{y0},{x1},{y1},{meses},{hoy.isoformat()}"
    guardado = cache.leer("hls_fechas", clave, max_dias=1)
    if guardado:
        return guardado

    desde = hoy - dt.timedelta(days=31 * meses)
    todas: list[dict] = []
    for c in COLECCIONES:
        todas += _pasadas(c, (x0, y0, x1, y1), desde)

    # una escena puede venir en dos cuadrículas (el campo cae en el borde): por día y sensor, la peor
    por_dia: dict[tuple[str, str], float] = {}
    for p in todas:
        k = (p["fecha"], p["sensor"])
        por_dia[k] = max(por_dia.get(k, 0.0), p["nubes"])

    mejor_mes: dict[str, dict] = {}
    for (fecha, sensor), nubes in por_dia.items():
        if nubes > MAX_NUBES:
            continue
        mes = fecha[:7]
        actual = mejor_mes.get(mes)
        # menos nubes gana; con empate (±3 %), la más nueva
        if actual is None or nubes < actual["nubes"] - 3 or (abs(nubes - actual["nubes"]) <= 3 and fecha > actual["fecha"]):
            mejor_mes[mes] = {"fecha": fecha, "nubes": round(nubes), "sensor": sensor,
                              "satelite": COLECCIONES[sensor][1], "capa": CAPA_GIBS[sensor]}

    fechas = sorted(mejor_mes.values(), key=lambda p: p["fecha"], reverse=True)
    resultado = {"fechas": fechas, "pasadas_vistas": len(por_dia), "max_nubes": MAX_NUBES}
    cache.guardar("hls_fechas", clave, resultado)
    return resultado
