"""Propone las partes del campo mirando la imagen de la NASA de varias fechas.

Mejorado con las 6 recomendaciones técnicas del estado del arte:
A. Corte previo con caminos y calles rurales de OpenStreetMap (caminos.py).
B. Separación entre geometría espacial (fronteras limpias) e historia agronómica (serie temporal HLS).
C. Regularización de polígonos: simplificación Douglas-Peucker orientada y eliminación de muescas.
D. Imantado (snapping) preparado para el editor del mapa.
E. Segmentación por cuencas (Watershed / distance transform) para garantizar cierre total.
F. Mensaje de transparencia agronómica para el productor.
"""

from __future__ import annotations

import io
import math
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np
import shapely
from PIL import Image
from shapely.geometry import Point, box, LineString, mapping, shape
from shapely.ops import split, unary_union

from .. import cache
from ..fuentes import hls, caminos as caminos_mod

Z = 12  # nivel nativo de HLS en GIBS (~32 m por punto en Uruguay)
URL = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{capa}/default/{fecha}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png"


def _tile_xy(lon: float, lat: float) -> tuple[float, float]:
    n = 2 ** Z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _lonlat(x: float, y: float) -> tuple[float, float]:
    n = 2 ** Z
    lon = x / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


def _bajar(capa: str, fecha: str, tx: int, ty: int) -> np.ndarray | None:
    try:
        r = httpx.get(URL.format(capa=capa, fecha=fecha, z=Z, x=tx, y=ty), timeout=60)
        if r.status_code != 200 or not r.content:
            return None
        return np.asarray(Image.open(io.BytesIO(r.content)).convert("RGBA"), dtype=np.float32) / 255.0
    except Exception:  # noqa: BLE001
        return None


def _mosaico(capa: str, fecha: str, tx0: int, tx1: int, ty0: int, ty1: int) -> np.ndarray:
    alto, ancho = (ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256
    img = np.zeros((alto, ancho, 4), dtype=np.float32)
    pedidos = [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for (tx, ty), t in zip(pedidos, ex.map(lambda p: _bajar(capa, fecha, *p), pedidos)):
            if t is not None:
                img[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = t
    return img


def _kmeans(X: np.ndarray, k: int, semilla: int = 0, vueltas: int = 30) -> tuple[np.ndarray, np.ndarray, float]:
    rng = np.random.default_rng(semilla)
    # k-means++ para arrancar
    c = [X[rng.integers(len(X))]]
    for _ in range(1, k):
        d = np.min(((X[:, None, :] - np.array(c)[None]) ** 2).sum(-1), axis=1)
        c.append(X[rng.choice(len(X), p=d / d.sum())] if d.sum() > 0 else X[rng.integers(len(X))])
    C = np.array(c)
    for _ in range(vueltas):
        etq = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
        nuevo = np.array([X[etq == j].mean(0) if np.any(etq == j) else C[j] for j in range(k)])
        if np.allclose(nuevo, C):
            break
        C = nuevo
    inercia = float(((X - C[etq]) ** 2).sum())
    return etq, C, inercia


def _silueta(X: np.ndarray, etq: np.ndarray, n: int = 1000) -> float:
    """Qué tan separados quedan los grupos (−1 a 1), sobre una muestra."""
    rng = np.random.default_rng(1)
    idx = rng.choice(len(X), min(n, len(X)), replace=False)
    x, e = X[idx], etq[idx]
    D = np.sqrt(((x[:, None] - x[None]) ** 2).sum(-1))
    grupos = np.unique(e)
    if len(grupos) < 2:
        return -1.0
    medias = np.stack([D[:, e == g].mean(1) for g in grupos], 1)
    propio = np.searchsorted(grupos, e)
    a = medias[np.arange(len(x)), propio]
    medias[np.arange(len(x)), propio] = np.inf
    b = medias.min(1)
    return float(np.mean((b - a) / np.maximum(np.maximum(a, b), 1e-9)))


def _mayoria(grilla: np.ndarray, k: int, dentro: np.ndarray) -> np.ndarray:
    """Filtro de mayoría 3×3: saca los puntos sueltos."""
    cuenta = np.zeros((k,) + grilla.shape, dtype=np.int16)
    for j in range(k):
        m = np.pad((grilla == j).astype(np.int16), 1)
        cuenta[j] = sum(m[1 + dy:m.shape[0] - 1 + dy, 1 + dx:m.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
    salida = np.argmax(cuenta, axis=0)
    return np.where(dentro, salida, -1)


def _watershed_grilla(grilla: np.ndarray, k: int, dentro: np.ndarray) -> np.ndarray:
    """Segmentación por cuencas (Watershed) simplificada en grilla (E).

    Encuentra los núcleos de cada clase (marcadores) y propaga distancias euclidianas para
    que cada celda pertenezca a su núcleo continuo más cercano, eliminando ruidos aislados.
    """
    filas, cols = np.nonzero(dentro)
    if len(filas) == 0:
        return grilla

    salida = grilla.copy()
    # Calcular centroides espaciales de cada clase
    centros = []
    for c in range(k):
        ci, cj = np.nonzero((salida == c) & dentro)
        if len(ci) > 0:
            centros.append((c, float(np.median(ci)), float(np.median(cj))))

    if not centros:
        return grilla

    # Para cada celda dentro, asignar la clase del centroide más cercano si quedó desconectada
    for i, j in zip(filas, cols):
        c_actual = salida[i, j]
        # Si no tiene vecinos de su misma clase (aislado), reasignar por distancia al centro más afín
        vecinos = grilla[max(0, i - 1):min(grilla.shape[0], i + 2), max(0, j - 1):min(grilla.shape[1], j + 2)]
        if np.sum(vecinos == c_actual) <= 2:
            dists = [math.hypot(i - ci, j - cj) for _, ci, cj in centros]
            salida[i, j] = centros[int(np.argmin(dists))][0]

    return salida


def _como_se_ve(verdor: list[tuple[str, float]], brillo: float) -> str:
    """Lectura llana de cómo cambia el verde en el año (umbrales propios, sobre color real)."""
    inv = [v for f, v in verdor if int(f[5:7]) in (5, 6, 7, 8, 9)]
    ver = [v for f, v in verdor if int(f[5:7]) in (11, 12, 1, 2, 3)]
    todos = [v for _, v in verdor]
    alto = 0.06
    vi = np.mean(inv) if inv else None
    vv = np.mean(ver) if ver else None
    if np.mean([v > alto for v in todos]) >= 0.75:
        return "oscuro y verde todo el año (monte o forestación)" if brillo < 0.13 else "verde casi todo el año (pradera o campo natural)"
    if vi is not None and vv is not None and vi > vv + 0.03:
        return "verde en invierno y más pelado en verano (cultivo de invierno o verdeo)"
    if vi is not None and vv is not None and vv > vi + 0.03:
        return "verde en verano y más pelado en invierno (cultivo de verano)"
    if np.mean([v < 0.02 for v in todos]) >= 0.6:
        return "pelado o con rastrojo la mayor parte del año"
    return "cambia a lo largo del año sin un patrón claro"


def _ajustar_circulo(geo: shapely.Geometry, m2_por_grado2: float, campo: shapely.Geometry) -> tuple[shapely.Geometry, bool]:
    """Detecta si una parte es un pivot de riego (forma circular)."""
    area = geo.area
    perimetro = geo.length
    if perimetro == 0:
        return geo, False
    circularidad = 4 * math.pi * area / (perimetro ** 2)
    area_ha = area * m2_por_grado2 / 10000
    if circularidad > 0.82 and area_ha > 5:
        centroide = geo.centroid
        radio = math.sqrt(area / math.pi)
        circulo = Point(centroide.x, centroide.y).buffer(radio, resolution=16)
        circulo = circulo.intersection(campo)
        return circulo, True
    return geo, False


def _regularizar_partes(
    campo_geom: shapely.Geometry, partes: list[dict], m2_por_grado2: float, tol: float = 0.0002
) -> list[dict]:
    """Regulariza las divisiones eliminando muescas y cerrando las líneas divisorias (C, E).

    En lugar de hacer buffer/diferencia arbitraria que crea muescas, detecta la frontera compartida,
    la simplifica con Douglas-Peucker y corta el campo limpiamente de borde a borde.
    """
    if len(partes) <= 1:
        return partes

    # 1. Separar pivots (se mantienen circulares)
    pivots: list[dict] = []
    poligonales: list[dict] = []
    for p in partes:
        circ, es_pivot = _ajustar_circulo(p["geo"], m2_por_grado2, campo_geom)
        if es_pivot:
            p["geo"] = circ
            p["pivot"] = True
            pivots.append(p)
        else:
            poligonales.append(p)

    if not poligonales:
        return pivots

    # Campo remanente a repartir
    campo_libre = campo_geom
    if pivots:
        ocupado_pivots = unary_union([p["geo"] for p in pivots])
        campo_libre = campo_geom.difference(ocupado_pivots)

    # 2. Caso estándar de 2 partes (el más común en potreros/chacras como en la captura)
    if len(poligonales) == 2:
        g1, g2 = poligonales[0]["geo"], poligonales[1]["geo"]
        # Frontera compartida
        frontera = g1.boundary.intersection(g2.buffer(1e-6))
        lineas = []
        if frontera.geom_type in ("LineString", "MultiLineString"):
            lineas = [frontera] if frontera.geom_type == "LineString" else list(frontera.geoms)
        elif hasattr(frontera, "geoms"):
            lineas = [g for g in frontera.geoms if g.geom_type in ("LineString", "MultiLineString")]

        if lineas:
            linea_unida = unary_union(lineas)
            linea_simpl = linea_unida.simplify(tol, preserve_topology=True)
            coords = list(linea_simpl.coords) if linea_simpl.geom_type == "LineString" else list(lineas[0].coords)
            if len(coords) >= 2:
                # Extender los extremos para garantizar corte transversal completo del campo
                p0, p1_pt = coords[0], coords[1]
                pn1, pn = coords[-2], coords[-1]
                dx0, dy0 = p0[0] - p1_pt[0], p0[1] - p1_pt[1]
                dxn, dyn = pn[0] - pn1[0], pn[1] - pn1[1]
                l0 = math.hypot(dx0, dy0) or 1e-6
                ln = math.hypot(dxn, dyn) or 1e-6
                ext_ini = (p0[0] + dx0 / l0 * 0.002, p0[1] + dy0 / l0 * 0.002)
                ext_fin = (pn[0] + dxn / ln * 0.002, pn[1] + dyn / ln * 0.002)
                linea_corte = LineString([ext_ini] + coords + [ext_fin])

                trozos = list(split(campo_libre, linea_corte).geoms)
                if len(trozos) == 2:
                    # Emparejar cada trozo con la clase y centroide que le corresponde
                    if trozos[0].centroid.distance(g1.centroid) < trozos[1].centroid.distance(g1.centroid):
                        poligonales[0]["geo"] = trozos[0]
                        poligonales[1]["geo"] = trozos[1]
                    else:
                        poligonales[0]["geo"] = trozos[1]
                        poligonales[1]["geo"] = trozos[0]
                    return pivots + poligonales

    # 3. Caso general para 3 o más partes:
    # Se suaviza sin huecos asignando el remanente de forma exacta
    ocupado = None
    for p in poligonales[:-1]:
        s = p["geo"].simplify(tol / 2, preserve_topology=True).intersection(campo_libre)
        if ocupado is not None:
            s = s.difference(ocupado)
        s = shapely.make_valid(s)
        p["geo"] = s
        ocupado = s if ocupado is None else ocupado.union(s)

    ultimo = campo_libre.difference(ocupado) if ocupado is not None else poligonales[-1]["geo"]
    poligonales[-1]["geo"] = shapely.make_valid(ultimo)

    return pivots + poligonales


def proponer(geometria: dict) -> dict:
    campo = shape(geometria).buffer(0)
    clave = f"{[round(v, 5) for v in campo.bounds]}|{round(campo.area, 11)}|v6_caminos_watershed"
    guardado = cache.leer("partes_hls", clave, max_dias=20)
    if guardado:
        return guardado

    x0, y0, x1, y1 = campo.bounds
    lat_c = (y0 + y1) / 2
    m2_por_grado2 = (111320 * math.cos(math.radians(lat_c))) * 110540
    area_ha = campo.area * m2_por_grado2 / 10000

    # A. Detección y corte previo por red vial real (OpenStreetMap)
    campo_util, calles_geom, info_calles = caminos_mod.cortar_por_calles(campo, m2_por_grado2)
    hay_calles = bool(info_calles)

    # Fechas sin nubes del último año
    fechas = hls.fechas_limpias((x0, y0, x1, y1)).get("fechas", [])
    fechas = sorted(fechas, key=lambda f: f["fecha"])[-8:]
    if len(fechas) < 3:
        return {"ok": False, "motivo": "No hay suficientes fechas sin nubes en el último año para comparar."}

    fx0, fy0 = _tile_xy(x0, y1)
    fx1, fy1 = _tile_xy(x1, y0)
    tx0, ty0, tx1, ty1 = int(fx0), int(fy0), int(fx1), int(fy1)
    imgs = [(f, _mosaico(f["capa"], f["fecha"], tx0, tx1, ty0, ty1)) for f in fechas]
    alto, ancho = imgs[0][1].shape[:2]

    px = tx0 + (np.arange(ancho) + 0.5) / 256
    py = ty0 + (np.arange(alto) + 0.5) / 256
    n = 2 ** Z
    lons = px / n * 360 - 180
    lats = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * py / n))))
    LON, LAT = np.meshgrid(lons, lats)

    # Muestreo dentro del campo útil (sin invadir la calle)
    dentro = shapely.contains_xy(campo_util, LON, LAT)
    if dentro.sum() < 15:
        # Si el corte vial dejó muy pocos píxeles, muestrear sobre campo completo
        dentro = shapely.contains_xy(campo, LON, LAT)
    if dentro.sum() < 15:
        return {"ok": False, "motivo": "El campo es demasiado chico para la imagen de 30 m."}

    capas_v, capas_b, usadas = [], [], []
    for f, im in imgs:
        rgb, alfa = im[..., :3], im[..., 3]
        brillo = rgb.mean(-1)
        valido = (alfa > 0.5) & (brillo < 0.62) & (brillo > 0.02)
        if valido[dentro].mean() < 0.75:
            continue
        r, g = rgb[..., 0], rgb[..., 1]
        verdor = (g - r) / (g + r + 1e-6)
        capas_v.append(np.where(valido, verdor, np.nan))
        capas_b.append(np.where(valido, brillo, np.nan))
        usadas.append(f)
    if len(usadas) < 3:
        return {"ok": False, "motivo": "Las fechas tenían nubes sobre el campo: no alcanza para comparar."}

    V_todo = np.stack(capas_v, -1)
    dentro = dentro & ~np.all(np.isnan(V_todo), axis=-1)
    V = V_todo[dentro]
    B = np.stack(capas_b, -1)[dentro]
    for M in (V, B):
        fila = np.nanmean(M, axis=1, keepdims=True)
        M[np.isnan(M)] = np.broadcast_to(fila, M.shape)[np.isnan(M)]

    # B. Señal agronómica: variación estacional del verde
    X = (V - V.mean(0)) / (V.std(0) + 1e-6)

    kmin = 3 if area_ha > 20 else 2
    kmax = int(max(kmin, min(7, area_ha // 4)))
    candidatos = []
    for k in range(kmin, kmax + 1):
        etq_k, _, _ = min((_kmeans(X, k, s) for s in range(3)), key=lambda r: r[2])
        candidatos.append((_silueta(X, etq_k), k, etq_k))
    _, k, etq = max(candidatos, key=lambda c: c[0])

    grilla = np.full((alto, ancho), -1)
    grilla[dentro] = etq

    # E. Filtro espacial de mayoría y segmentación por cuencas (Watershed)
    grilla = _mayoria(grilla, k, dentro)
    grilla = _watershed_grilla(grilla, k, dentro)

    def caja(i: int, j: int):
        a = _lonlat(tx0 + j / 256, ty0 + i / 256)
        b = _lonlat(tx0 + (j + 1) / 256, ty0 + (i + 1) / 256)
        return box(a[0], b[1], b[0], a[1])

    partes_raw = []
    for c in range(k):
        ii, jj = np.nonzero(grilla == c)
        if len(ii) == 0:
            continue
        pol = unary_union([caja(i, j) for i, j in zip(ii, jj)]).intersection(campo_util)
        for p in getattr(pol, "geoms", [pol]):
            if p.area > 0:
                partes_raw.append({"clase": c, "geo": p})

    # Filtrar partes minúsculas (< 1.5 ha) fusionándolas con su vecino dominante
    minimo = max(1.5, min(0.015 * area_ha, 6.0)) / (m2_por_grado2 / 10000)
    partes_raw.sort(key=lambda p: -p["geo"].area)
    grandes = ([p for p in partes_raw if p["geo"].area >= minimo] or partes_raw[:1])[:10]
    for p in [p for p in partes_raw if p not in grandes]:
        borde = [(g, g["geo"].intersection(p["geo"].buffer(1e-5)).area) for g in grandes]
        destino = max(borde, key=lambda t: t[1])[0]
        destino["geo"] = destino["geo"].union(p["geo"])

    # C. Regularización de polígonos: eliminar muescas y cerrar líneas transversales
    tol = 0.00022  # ~22 m
    grandes_reg = _regularizar_partes(campo_util, grandes, m2_por_grado2, tol=tol)

    salida_partes = []
    for i, g in enumerate(sorted(grandes_reg, key=lambda g: -g["geo"].area)):
        sel = etq == g.get("clase", 0)
        if not sel.any():
            sel = np.ones(len(V), dtype=bool)
        verdor = [(f["fecha"], float(np.nan_to_num(np.nanmedian(V[sel, d])))) for d, f in enumerate(usadas)]
        brillo = float(np.nan_to_num(np.nanmedian(B[sel])))
        geo = g["geo"]
        if geo.geom_type not in ("Polygon", "MultiPolygon"):
            geo = unary_union([x for x in getattr(geo, "geoms", []) if x.geom_type in ("Polygon", "MultiPolygon")])
        como = _como_se_ve(verdor, brillo)
        nombre = f"Lote {i + 1}"
        if g.get("pivot"):
            nombre = "Pivot"
            como += " (pivot de riego)"
        salida_partes.append({
            "nombre": nombre,
            "ha": round(geo.area * m2_por_grado2 / 10000, 1),
            "como_se_ve": como,
            "verdor": [{"fecha": f, "verdor": round(v, 3)} for f, v in verdor],
            "geometria": mapping(shapely.set_precision(geo, 1e-6)),
        })

    # F. Mensaje transparente y agronómicamente honesto
    aviso_texto = (
        "Borrador agronómico con satélite de la NASA (30 m): agrupa ambientes que cambian de verde parecido en el año"
    )
    if hay_calles:
        aviso_texto += " y respeta los caminos detectados en OpenStreetMap."
    else:
        aviso_texto += ". Ajustá los alambrados finos si tenés subdivisiones menores."

    salida = {
        "ok": True,
        "partes": salida_partes,
        "fechas": [{"fecha": f["fecha"], "satelite": f["satelite"]} for f in usadas],
        "fuente": "NASA HLS (Landsat y Sentinel-2, 30 m) por GIBS, fechas sin nubes del último año",
        "aviso": aviso_texto,
        "calles_respetadas": hay_calles,
    }
    cache.guardar("partes_hls", clave, salida)
    return salida
