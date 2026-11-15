"""MODIS MOD13Q1 v061 (NDVI, 250 m, cada 16 días) por punto, desde el servicio de ORNL DAAC.

API: https://modis.ornl.gov/rst/api/v1/ — sin cuenta. Máximo 10 fechas por pedido y ~20 s por
pedido, así que se piden en paralelo de a 4 y se cachea 30 días.

Para qué sirve en la app: ver, sección por sección, cuándo el suelo estuvo cubierto y cuándo
descubierto en los últimos años. Eso dice desde el espacio qué rotación se hizo de verdad
(¿hubo cultivo de invierno? ¿quedó en barbecho?) y alimenta el factor C de la erosión.

Límite: un píxel de 250 m (6,25 ha). Secciones de menos de ~10 ha mezclan bordes, caminos o
vecinos; la app lo avisa. HLS (30 m) es el siguiente paso, con cuenta de Earthdata.
"""

from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import httpx

from .. import cache

URL = "https://modis.ornl.gov/rst/api/v1/MOD13Q1"
BANDA = "250m_16_days_NDVI"
UMBRAL_DESCUBIERTO = 0.30  # NDVI por debajo: suelo desnudo o rastrojo seco
UMBRAL_CULTIVO = 0.55  # NDVI máximo de la temporada por encima: hubo cultivo o pastura activa


# Límite corto por petición (era 120 s con 3 intentos = 360 s, excediendo el límite de Vercel)
TIMEOUT_MODIS = 20.0
MAX_INTENTOS_MODIS = 2


def _fechas(lat: float, lon: float) -> list[str]:
    r = httpx.get(f"{URL}/dates", params={"latitude": lat, "longitude": lon}, timeout=TIMEOUT_MODIS,
                  headers={"Accept": "application/json"})
    r.raise_for_status()
    return [d["modis_date"] for d in r.json()["dates"]]


def _tramo(lat: float, lon: float, ini: str, fin: str) -> list[dict]:
    params = {
        "latitude": lat, "longitude": lon, "band": BANDA,
        "startDate": ini, "endDate": fin, "kmAboveBelow": 0, "kmLeftRight": 0,
    }
    for intento in range(MAX_INTENTOS_MODIS):
        try:
            r = httpx.get(f"{URL}/subset", params=params, timeout=TIMEOUT_MODIS,
                          headers={"Accept": "application/json"})
            r.raise_for_status()
            return r.json().get("subset", [])
        except httpx.HTTPError:
            if intento == MAX_INTENTOS_MODIS - 1:
                raise
    return []


def ndvi_punto(lat: float, lon: float, anios: int = 4) -> dict:
    lat, lon = round(lat, 4), round(lon, 4)
    # Las temporadas dependen del hemisferio (v3 en el norte para no leer cachés con las del sur)
    clave = f"{lat},{lon},{anios},v2" if lat < 0 else f"{lat},{lon},{anios},v3"
    guardado = cache.leer("modis_ndvi", clave, max_dias=30)
    if guardado:
        return guardado

    desde = dt.date.today().replace(month=1, day=1).replace(year=dt.date.today().year - anios)
    try:
        todas = _fechas(lat, lon)
        elegidas = [d for d in todas if dt.datetime.strptime(d[1:], "%Y%j").date() >= desde]
        tramos = [elegidas[i : i + 10] for i in range(0, len(elegidas), 10)]
        with ThreadPoolExecutor(max_workers=4) as ex:
            resultados = list(ex.map(lambda t: _tramo(lat, lon, t[0], t[-1]), tramos))

        puntos = []
        for res in resultados:
            for s in res:
                v = s["data"][0] if s.get("data") else None
                if v is None or v < -2000:
                    continue
                puntos.append({"fecha": s["calendar_date"], "ndvi": round(v * 0.0001, 3)})
        puntos.sort(key=lambda p: p["fecha"])
        puntos = _sacar_nubes(puntos)
        salida = {
            "fuente": "NASA MODIS MOD13Q1 v061 (Terra, 250 m, 16 días) vía ORNL DAAC",
            "lat": lat,
            "lon": lon,
            "serie": puntos,
            **interpretar(puntos, "sur" if lat < 0 else "norte"),
        }
        if puntos:
            cache.guardar("modis_ndvi", clave, salida)
        return salida
    except Exception as e:
        # ORNL estuvo caído toda la tarde (503 y timeouts, también en Uruguay); la misma colección está en
        # Earth Engine, que la app ya usa para la Historia
        respaldo = _desde_earth_engine(lat, lon, desde, clave)
        if respaldo:
            return respaldo
        return {
            "fuente": "NASA MODIS MOD13Q1 v061 (Terra, 250 m, 16 días) vía ORNL DAAC",
            "lat": lat,
            "lon": lon,
            "serie": [],
            "temporadas": [],
            "descubierto_por_anio": [],
            "error": str(e),
        }


def _desde_earth_engine(lat: float, lon: float, desde: dt.date, clave: str) -> dict | None:
    """La misma serie (MOD13Q1 v061) desde Google Earth Engine, si ORNL no responde. None si tampoco hay EE."""
    from . import modis_historia  # acá adentro: modis_historia importa este módulo

    try:
        puntos = [p for p in modis_historia._consultar_punto_ee(lon, lat) if p["fecha"] >= desde.isoformat()]
    except Exception:  # noqa: BLE001
        return None
    if not puntos:
        return None
    puntos = _sacar_nubes(puntos)
    salida = {
        "fuente": "NASA MODIS MOD13Q1 v061 (Terra, 250 m, 16 días) vía Google Earth Engine (ORNL no respondió)",
        "lat": lat,
        "lon": lon,
        "serie": puntos,
        **interpretar(puntos, "sur" if lat < 0 else "norte"),
    }
    cache.guardar("modis_ndvi", clave, salida)
    return salida


def _sacar_nubes(p: list[dict]) -> list[dict]:
    """Una caída brusca aislada (más de 0,2 bajo ambos vecinos) suele ser nube: se interpola."""
    for i in range(1, len(p) - 1):
        a, b, c = p[i - 1]["ndvi"], p[i]["ndvi"], p[i + 1]["ndvi"]
        if b < a - 0.2 and b < c - 0.2:
            p[i] = {**p[i], "ndvi": round((a + c) / 2, 3), "corregido": True}
    return p


def interpretar(puntos: list[dict], hemisferio: str = "sur") -> dict:
    """Uso detectado por temporada y meses de suelo descubierto por año.

    Sur: invierno de junio a octubre y verano de diciembre a marzo. Norte: el cultivo de invierno se ve
    en noviembre y a principios de la primavera (marzo y abril): en pleno invierno está en reposo o bajo la nieve, en
    octubre todavía se cosecha el verano y en mayo ya nacen el maíz y la soja; el verano va de junio a septiembre."""
    if not puntos:
        return {"temporadas": [], "descubierto_por_anio": []}
    por_mes: dict[tuple[int, int], list[float]] = {}
    for p in puntos:
        y, m = int(p["fecha"][:4]), int(p["fecha"][5:7])
        por_mes.setdefault((y, m), []).append(p["ndvi"])
    mensual = {k: sum(v) / len(v) for k, v in por_mes.items()}

    anios = sorted({k[0] for k in mensual})
    descubierto = []
    for y in anios:
        meses = [m for m in range(1, 13) if (y, m) in mensual]
        if len(meses) < 10:
            continue
        bajos = [m for m in meses if mensual[(y, m)] < UMBRAL_DESCUBIERTO]
        descubierto.append({"anio": y, "meses_descubierto": len(bajos), "meses": bajos})

    temporadas = []
    for y in anios:
        if hemisferio == "norte":
            inv = [mensual[k] for k in ((y, 11), (y + 1, 3), (y + 1, 4)) if k in mensual]
            ver = [mensual[(y, m)] for m in (6, 7, 8, 9) if (y, m) in mensual]
            if len(ver) >= 3:
                temporadas.append(_temporada(f"verano {y}", ver))
            if len(inv) >= 3:
                temporadas.append(_temporada(f"invierno {y}/{str(y + 1)[2:]}", inv))
            continue
        inv = [mensual[(y, m)] for m in (6, 7, 8, 9, 10) if (y, m) in mensual]
        ver = [mensual[k] for k in ((y, 12), (y + 1, 1), (y + 1, 2), (y + 1, 3)) if k in mensual]
        if len(inv) >= 3:
            temporadas.append(_temporada(f"invierno {y}", inv))
        if len(ver) >= 3:
            temporadas.append(_temporada(f"verano {y}/{str(y + 1)[2:]}", ver))
    return {
        "mensual": [{"anio": k[0], "mes": k[1], "ndvi": round(v, 3)} for k, v in sorted(mensual.items())],
        "temporadas": temporadas,
        "descubierto_por_anio": descubierto,
        "umbrales": {"descubierto": UMBRAL_DESCUBIERTO, "cultivo": UMBRAL_CULTIVO},
    }


def _temporada(nombre: str, valores: list[float]) -> dict:
    maximo, minimo = max(valores), min(valores)
    amplitud = maximo - minimo
    if minimo >= 0.5:
        uso = "cobertura permanente (pastura o campo natural)"
    elif maximo >= UMBRAL_CULTIVO:
        uso = "cultivo o pastura en crecimiento"
    elif minimo >= UMBRAL_DESCUBIERTO and amplitud < 0.15:
        uso = "cobertura permanente de baja actividad (campo natural, pastura degradada o seca)"
    elif maximo >= 0.42:
        uso = "cobertura parcial (cultivo pobre, rastrojo verde o maleza)"
    else:
        uso = "suelo descubierto o rastrojo (barbecho)"
    return {"temporada": nombre, "ndvi_max": round(maximo, 3), "ndvi_min": round(minimo, 3), "uso_detectado": uso}
