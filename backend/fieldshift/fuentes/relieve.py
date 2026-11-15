"""Relieve del campo: SRTM de la NASA (30 m) leído de los "Terrain Tiles" públicos de AWS.

Qué es: los Terrain Tiles (Tilezen/Mapzen, en el registro de datos abiertos de AWS) juntan varios
modelos de elevación; en Uruguay, desde el zoom 7, el dato de tierra es **SRTM** (Shuttle Radar
Topography Mission, NASA/USGS, 30 m). Ver https://github.com/tilezen/joerd/blob/master/docs/data-sources.md.
Se usan porque no piden cuenta y vienen recortados en mosaicos: bajar el SRTM original de LP DAAC pide
Earthdata Login y archivos de 1° × 1° (25 MB) por cada campo.

Formato "terrarium": PNG de 256 × 256; elevación (m) = R × 256 + G + B / 256 − 32768.

Se usa el zoom 13 (≈ 16 m por píxel en Uruguay): el dato de fondo es de 30 m, así que más zoom solo
interpola. Los mosaicos se guardan en disco (no cambian).

Límites: SRTM mide la superficie que ve el radar (en montes y cascos, la copa de los árboles y los
techos), tiene ruido de unos metros y es de febrero de 2000. Para pendientes de chacra alcanza; para
diseñar terrazas, no.
"""

from __future__ import annotations

import io
import math
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np
from PIL import Image

from .. import cache

URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
ZOOM = 13
FUENTE = "NASA SRTM (30 m), vía AWS Terrain Tiles (Tilezen)"


def _tile_xy(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _lonlat(x: float, y: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    lon = x / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


def _tile(z: int, x: int, y: int) -> np.ndarray:
    ruta = cache.CARPETA / "relieve" / f"{z}_{x}_{y}.png"
    if ruta.exists():
        datos = ruta.read_bytes()
    else:
        r = httpx.get(URL.format(z=z, x=x, y=y), timeout=60)
        r.raise_for_status()
        datos = r.content
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(datos)
    rgb = np.asarray(Image.open(io.BytesIO(datos)).convert("RGB"), dtype=np.float64)
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


def mosaico(oeste: float, sur: float, este: float, norte: float, z: int = ZOOM) -> dict:
    """Elevación (m) del rectángulo, en la grilla de los mosaicos (Web Mercator), recortada al rectángulo.

    Devuelve {"elev": ndarray (filas = de norte a sur), "oeste", "norte", "este", "sur" (bordes exactos de la
    grilla recortada), "px_m": metros por píxel, "fuente"}.
    """
    x0, y0 = _tile_xy(oeste, norte, z)
    x1, y1 = _tile_xy(este, sur, z)
    tx = range(int(x0), int(x1) + 1)
    ty = range(int(y0), int(y1) + 1)
    if len(tx) * len(ty) > 36:
        raise ValueError("El campo es demasiado grande para el relieve de 30 m (más de 36 mosaicos).")
    pedidos = [(x, y) for y in ty for x in tx]
    with ThreadPoolExecutor(max_workers=6) as ex:
        tiles = dict(zip(pedidos, ex.map(lambda p: _tile(z, *p), pedidos)))
    grande = np.vstack([np.hstack([tiles[(x, y)] for x in tx]) for y in ty])
    # recorte al rectángulo pedido, en píxeles del mosaico
    c0, f0 = int((x0 - tx[0]) * 256), int((y0 - ty[0]) * 256)
    c1, f1 = int(math.ceil((x1 - tx[0]) * 256)), int(math.ceil((y1 - ty[0]) * 256))
    elev = grande[f0:f1, c0:c1]
    o, n = _lonlat(tx[0] + c0 / 256, ty[0] + f0 / 256, z)
    e, s = _lonlat(tx[0] + c1 / 256, ty[0] + f1 / 256, z)
    lat_media = (n + s) / 2
    px_m = 156543.03392 * math.cos(math.radians(lat_media)) / 2 ** z
    return {"elev": elev, "oeste": o, "norte": n, "este": e, "sur": s, "px_m": px_m, "fuente": FUENTE}
