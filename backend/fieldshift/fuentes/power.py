"""NASA POWER: clima agrícola diario desde 1981, sin cuenta.

Docs: https://power.larc.nasa.gov/docs/services/api/
- Grilla ~0,5° (≈50 km): un campo entero cae en la misma celda, así que todas sus secciones
  comparten el clima. Lo que diferencia secciones es el suelo (MGAP) y la cobertura (MODIS).
- Valor faltante: -999. Atraso: ~3 días meteorología, ~5 días radiación.
- Es reanálisis/modelo, no un pluviómetro: por eso se compara con la estación del productor
  cuando la sube.
"""

from __future__ import annotations

import datetime as dt

import httpx

from .. import cache

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETROS = [
    "T2M_MAX",  # °C
    "T2M_MIN",  # °C
    "PRECTOTCORR",  # mm/día
    "ALLSKY_SFC_SW_DWN",  # MJ/m²/día
    "RH2M",  # %
    "WS2M",  # m/s
    "GWETROOT",  # 0-1, humedad zona de raíces (modelo)
]
INICIO = "19910101"


def _celda(valor: float) -> float:
    """Redondea a 0,25° para que puntos vecinos reusen la misma descarga."""
    return round(round(valor * 4) / 4, 2)


def bajar_diario(lat: float, lon: float, fin: dt.date | None = None, con_imerg: bool = True) -> dict:
    """Clima diario de POWER con la lluvia de GPM IMERG desde junio de 2000. En `lluvia` dice de dónde salió; si IMERG no
    contesta queda la de POWER. `con_imerg=False` da POWER solo."""
    pw = _bajar_power(lat, lon, fin)
    if not con_imerg:
        return pw
    from . import imerg

    return imerg.con_lluvia_imerg(pw, lat, lon)


def _bajar_power(lat: float, lon: float, fin: dt.date | None = None) -> dict:
    """Devuelve {"elevacion": m, "fechas": [...], "<PARAM>": [...]} con -999 → None.

    Se cachea 7 días: el dato nuevo llega de a uno por día y la climatología no cambia.
    """
    lat_c, lon_c = _celda(lat), _celda(lon)
    fin = fin or (dt.date.today() - dt.timedelta(days=7))
    clave = f"{lat_c},{lon_c},{INICIO},{fin.isoformat()[:7]}"
    guardado = cache.leer("power", clave, max_dias=7)
    if guardado:
        return guardado

    params = {
        "parameters": ",".join(PARAMETROS),
        "community": "AG",
        "latitude": lat_c,
        "longitude": lon_c,
        "start": INICIO,
        "end": fin.strftime("%Y%m%d"),
        "format": "JSON",
    }
    r = httpx.get(URL, params=params, timeout=45)
    r.raise_for_status()
    js = r.json()
    datos = js["properties"]["parameter"]
    fechas = sorted(datos[PARAMETROS[0]].keys())
    salida: dict = {
        "fuente": "NASA POWER (daily, community AG)",
        "url": str(r.url),
        "lat": lat_c,
        "lon": lon_c,
        "elevacion": js["geometry"]["coordinates"][2],
        "fechas": fechas,
    }
    for p in PARAMETROS:
        serie = datos.get(p, {})
        salida[p] = [None if serie.get(f) in (None, -999, -999.0) else serie.get(f) for f in fechas]
    cache.guardar("power", clave, salida)
    return salida
