"""GPM IMERG (NASA): lluvia diaria de satélite en celdas de 0,1° (~10 km), desde junio de 2000.

Se pide la serie entera de un punto a la API de series de tiempo de Giovanni (GES DISC): 25 años en ~5 s, en CSV.
- Final (`GPM_3IMERGDF_07`, con pluviómetros) cuando termina la V07; Late (`GPM_3IMERGDL_07`,
  ~14 h de atraso). Es lo que recomienda GPM para tener lo reciente.
- Pide el token de Earthdata (`EARTHDATA_TOKEN`, o `.secretos/earthdata_token.txt` en la PC); si no hay, se pide uno
  con `EARTHDATA_USER`/`EARTHDATA_PASS`.

Por qué: la lluvia de NASA POWER (`PRECTOTCORR`) da 0 mm de octubre de 2022 a julio de 2023 en el centro
de Uruguay, y eso inflaba la seca de 2022/23. Fuera de ese hueco coinciden (correlación mensual 0,94). La app usa
IMERG para la lluvia desde 2000 y deja POWER para antes, para la temperatura, la radiación y el viento, y como
respaldo si Giovanni no contesta. Detalle: `nasa/04-datos-y-apis.md` §8.

La lluvia de POWER que queda (1991 a mayo de 2000) se ajusta a la de IMERG mes a mes por cuantiles
(`ajustar_power`). POWER promedia una celda de ~50 km y achata las tormentas (en el campo de ejemplo, 2,8 días de 50 mm
o más por año contra 5,1 de IMERG en los mismos años), y la seca de la soja daba 0,38 con una y 0,19 con la otra en
2001-2021. Sin el ajuste, la comparación 1991-2008 contra 2009-hoy mezclaba dos fuentes en el primer período.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

from .. import cache

logger = logging.getLogger(__name__)

URL = "https://api.giovanni.earthdata.nasa.gov/timeseries"
FINAL = "GPM_3IMERGDF_07_precipitation"
LATE = "GPM_3IMERGDL_07_precipitation"
INICIO_FINAL = dt.date(2000, 6, 1)
FIN_FINAL = dt.date(2025, 9, 30)
NOMBRE = "NASA GPM IMERG (diario, V07: Final hasta 9/2025, Late después)"


def _celda(valor: float) -> float:
    """Centro de la celda de 0,1° de IMERG que contiene el valor (los centros terminan en ,x5)."""
    return round(math.floor(valor * 10) / 10 + 0.05, 2)


def _secretos() -> list[Path]:
    aqui = Path(__file__).resolve()
    return [aqui.parents[4] / ".secretos", aqui.parents[3] / ".secretos", Path.cwd() / ".secretos", Path.home() / "nasa" / ".secretos"]


def token() -> str | None:
    """Token de Earthdata: variable de entorno, archivo local o, con usuario y contraseña, uno pedido a Earthdata."""
    t = os.environ.get("EARTHDATA_TOKEN", "").strip()
    if t:
        return t
    for d in _secretos():
        f = d / "earthdata_token.txt"
        if f.is_file():
            t = f.read_text(encoding="utf-8").strip()
            if t:
                return t
    from .modis_historia import _credenciales

    cred = _credenciales()
    if not cred:
        return None
    guardado = cache.leer("earthdata", "token", max_dias=20)
    if guardado:
        return guardado
    try:
        r = httpx.post("https://urs.earthdata.nasa.gov/api/users/find_or_create_token", auth=cred, timeout=30)
        r.raise_for_status()
        t = r.json().get("access_token")
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo pedir el token de Earthdata: %s", e)
        return None
    if t:
        cache.guardar("earthdata", "token", t)
    return t


def leer_csv(texto: str) -> dict[str, float | None]:
    """CSV de Giovanni → {"AAAAMMDD": mm}. Arriba vienen metadatos; los datos, después de «Timestamp (UTC),Data».
    El valor faltante (`undef`, -9999.9) queda en None."""
    datos: dict[str, float | None] = {}
    en_datos = False
    for linea in texto.splitlines():
        if not en_datos:
            en_datos = linea.startswith("Timestamp")
            continue
        partes = linea.strip().split(",")
        if len(partes) != 2 or len(partes[0]) < 10:
            continue
        try:
            v = float(partes[1])
        except ValueError:
            continue
        datos[partes[0][:10].replace("-", "")] = None if v < -9000 else v
    return datos


def _pedir(producto: str, lat: float, lon: float, desde: dt.date, hasta: dt.date, tok: str) -> dict[str, float | None]:
    params = {"data": producto, "location": f"[{lat},{lon}]",
              "time": f"{desde.isoformat()}T00:00:00/{hasta.isoformat()}T23:59:59"}
    r = httpx.get(URL, params=params, headers={"Authorization": f"Bearer {tok}"}, timeout=90, follow_redirects=True)
    r.raise_for_status()
    datos = leer_csv(r.text)
    if not datos:
        raise ValueError(f"Giovanni no devolvió datos de {producto}")
    return datos


def serie(lat: float, lon: float) -> dict:
    """{"fechas": [AAAAMMDD…], "mm": […], "lat", "lon", "fuente"} desde junio de 2000 hasta ayer.

    La Final no cambia más: se guarda sin vencimiento. La Late se vuelve a pedir una vez por día."""
    lat_c, lon_c = _celda(lat), _celda(lon)
    hoy = dt.date.today()
    final = cache.leer("imerg", f"final,{lat_c},{lon_c}")
    late = cache.leer("imerg", f"late,{lat_c},{lon_c},{hoy.isoformat()}", max_dias=1)
    if final is None or late is None:
        tok = token()
        if not tok:
            raise RuntimeError("Falta el token de Earthdata (EARTHDATA_TOKEN)")
        # las dos a la vez: cada pedido a Giovanni tarda de 3 a 20 s
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_final = ex.submit(_pedir, FINAL, lat_c, lon_c, INICIO_FINAL, FIN_FINAL, tok) if final is None else None
            f_late = (ex.submit(_pedir, LATE, lat_c, lon_c, FIN_FINAL + dt.timedelta(days=1), hoy - dt.timedelta(days=1), tok)
                      if late is None else None)
            if f_final is not None:
                final = f_final.result()
                cache.guardar("imerg", f"final,{lat_c},{lon_c}", final)
            if f_late is not None:
                late = f_late.result()
                cache.guardar("imerg", f"late,{lat_c},{lon_c},{hoy.isoformat()}", late)
    todo = {**final, **late}
    fechas = sorted(todo)
    return {"fechas": fechas, "mm": [todo[f] for f in fechas], "lat": lat_c, "lon": lon_c, "fuente": NOMBRE}


def con_lluvia_imerg(pw: dict, lat: float, lon: float) -> dict:
    """El clima de POWER con la lluvia de IMERG en los días que la tiene. Guarda la de POWER en `PRECTOTCORR_POWER` y
    en `lluvia` de dónde salió cada parte. Si IMERG falla, devuelve POWER tal cual y lo dice en `lluvia`."""
    if not pw or "PRECTOTCORR" not in pw or pw.get("lluvia", {}).get("dias_imerg"):
        return pw
    try:
        im = serie(lat, lon)
    except Exception as e:  # noqa: BLE001
        logger.warning("IMERG no disponible, queda la lluvia de NASA POWER: %s", e)
        return {**pw, "lluvia": {"fuente": "NASA POWER", "dias_imerg": 0, "motivo": f"IMERG no disponible: {e}"[:200]}}
    mm = dict(zip(im["fechas"], im["mm"]))
    power_aj, n_ajustados = ajustar_power(pw["fechas"], pw["PRECTOTCORR"], mm)
    nueva, n_imerg = [], 0
    for f, v in zip(pw["fechas"], power_aj):
        w = mm.get(f)
        if w is not None:
            nueva.append(round(w, 2))
            n_imerg += 1
        else:
            nueva.append(v)
    desde = next((f for f in pw["fechas"] if mm.get(f) is not None), None)
    lluvia = {"fuente": im["fuente"], "celda": [im["lat"], im["lon"]], "desde": desde, "dias_imerg": n_imerg,
              "dias_power": len(nueva) - n_imerg}
    if n_ajustados:
        lluvia["power_ajustada"] = {"dias": n_ajustados, "metodo": METODO_AJUSTE}
    return {**pw, "PRECTOTCORR": nueva, "PRECTOTCORR_POWER": pw["PRECTOTCORR"], "lluvia": lluvia}


# Ajuste de la lluvia de POWER a la de IMERG
MIN_DIAS_AJUSTE = 300  # días con las dos lluvias en ese mes del año (unos 10 años) para armar el ajuste
METODO_AJUSTE = ("cuantiles mes a mes: cada día de POWER sin IMERG toma el valor de IMERG que ocupa el mismo lugar en "
                 "la distribución de ese mes, aprendida en los años que tienen las dos (método de mapeo de cuantiles)")


def ajustar_power(fechas: list[str], power: list, imerg_mm: dict[str, float | None]) -> tuple[list, int]:
    """La lluvia de POWER pasada a la distribución de IMERG, mes del año por mes del año (mapeo empírico de cuantiles,
    Gudmundsson et al. 2012). Se aprende con los días que tienen las dos, sin los meses en que POWER falla (menos de
    5 mm en el mes y 20 o más en IMERG, como el hueco de 2022-23). Un día de POWER toma el valor de IMERG del mismo
    percentil; por encima del máximo aprendido se suma la diferencia, para no achatar una tormenta más grande.
    Los días sin dato de POWER quedan sin dato. Un mes del año con menos de `MIN_DIAS_AJUSTE` días para aprender
    queda sin ajustar. Devuelve la serie y cuántos días sin IMERG se ajustaron."""
    meses_por_dia = [f[:6] for f in fechas]
    tot_p: dict[str, float] = {}
    tot_i: dict[str, float] = {}
    for f, ym, v in zip(fechas, meses_por_dia, power):
        w = imerg_mm.get(f)
        if v is not None and w is not None:
            tot_p[ym] = tot_p.get(ym, 0.0) + float(v)
            tot_i[ym] = tot_i.get(ym, 0.0) + float(w)
    falla = {ym for ym in tot_p if tot_p[ym] < 5 and tot_i[ym] >= 20}

    salida = list(power)
    n = 0
    for mes in range(1, 13):
        par_p, par_i = [], []
        for f, ym, v in zip(fechas, meses_por_dia, power):
            w = imerg_mm.get(f)
            if int(ym[4:]) == mes and v is not None and w is not None and ym not in falla:
                par_p.append(float(v))
                par_i.append(float(w))
        if len(par_p) < MIN_DIAS_AJUSTE:
            continue
        ord_p = np.sort(np.array(par_p))
        ord_i = np.sort(np.array(par_i))
        idx = [i for i, (f, v) in enumerate(zip(fechas, power))
               if int(f[4:6]) == mes and v is not None and imerg_mm.get(f) is None]
        if not idx:
            continue
        x = np.array([float(power[i]) for i in idx])
        # percentil de cada valor en POWER (con empates, el del medio) → el mismo percentil en IMERG
        izq = np.searchsorted(ord_p, x, side="left")
        der = np.searchsorted(ord_p, x, side="right")
        q = np.clip((izq + der) / (2 * len(ord_p)), 0, 1)
        y = np.quantile(ord_i, q)
        arriba = x > ord_p[-1]
        y[arriba] = ord_i[-1] + (x[arriba] - ord_p[-1])
        for i, val in zip(idx, y):
            salida[i] = round(float(max(val, 0.0)), 2)
        n += len(idx)
    return salida, n
