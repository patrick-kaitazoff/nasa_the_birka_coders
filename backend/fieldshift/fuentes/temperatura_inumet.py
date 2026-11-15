"""La temperatura de NASA POWER corregida con las estaciones de INUMET.

POWER exagera el calor del verano en Uruguay (de +0,6 °C en Colonia a +3,5 °C en el Aeropuerto Melilla en la máxima
media de dic-mar 2020-2025) y le faltan heladas. `datos/temperatura_inumet.json` (lo arma
`scripts/armar_temperatura_inumet.py`) tiene, para 7 estaciones y cada mes del año, los percentiles de la máxima y la
mínima diarias de la estación y de POWER en los mismos días. Cada día de POWER pasa al valor de la estación que ocupa
el mismo percentil en ese mes (mapeo de cuantiles); por encima del máximo o por debajo del mínimo aprendidos se suma la
diferencia del extremo. Un campo usa las dos estaciones más cercanas, pesadas por la inversa del cuadrado de la
distancia; a más de 250 km de toda estación (fuera de Uruguay), POWER queda como está.
"""

from __future__ import annotations

import functools
import json
import math
from pathlib import Path

import numpy as np

ARCHIVO = Path(__file__).resolve().parents[1] / "datos" / "temperatura_inumet.json"
DISTANCIA_MAX_KM = 250.0


@functools.lru_cache(maxsize=1)
def _datos() -> dict | None:
    try:
        return json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * 111.32
    dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def estaciones_cercanas(lat: float, lon: float, n: int = 2) -> list[tuple[dict, float]]:
    """Las n estaciones más cercanas a menos de DISTANCIA_MAX_KM, con su peso (suman 1)."""
    d = _datos()
    if not d:
        return []
    cerca = sorted(((e, _km(lat, lon, e["lat"], e["lon"])) for e in d["estaciones"]), key=lambda x: x[1])[:n]
    cerca = [(e, km) for e, km in cerca if km <= DISTANCIA_MAX_KM]
    if not cerca:
        return []
    pesos = [1 / max(km, 1.0) ** 2 for _, km in cerca]
    total = sum(pesos)
    return [(e, p / total) for (e, _), p in zip(cerca, pesos)]


def _mapear(x: np.ndarray, q_power: list[float], q_est: list[float]) -> np.ndarray:
    qp, qe = np.array(q_power, dtype=float), np.array(q_est, dtype=float)
    y = np.interp(x, qp, qe)
    y = np.where(x > qp[-1], x + (qe[-1] - qp[-1]), y)
    return np.where(x < qp[0], x + (qe[0] - qp[0]), y)


def corregir(mes: np.ndarray, tmax: np.ndarray, tmin: np.ndarray, lat: float, lon: float
             ) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Máxima y mínima corregidas, y los nombres de las estaciones usadas (vacío si no se corrigió)."""
    cerca = estaciones_cercanas(lat, lon)
    if not cerca:
        return tmax, tmin, []
    salida = []
    for valores, var in ((tmax, "tmax"), (tmin, "tmin")):
        cambio = np.zeros_like(valores, dtype=float)
        peso = np.zeros_like(valores, dtype=float)
        for est, w in cerca:
            for m in range(1, 13):
                q = est[var].get(str(m))
                if not q:
                    continue
                sel = mes == m
                cambio[sel] += w * (_mapear(valores[sel], q["power"], q["estacion"]) - valores[sel])
                peso[sel] += w
        # si a una estación le falta ese mes, el cambio se reparte entre las que lo tienen
        salida.append(valores + np.divide(cambio, peso, out=np.zeros_like(cambio), where=peso > 0))
    tmax_c, tmin_c = salida
    tmin_c = np.minimum(tmin_c, tmax_c)  # el mapeo por separado no puede dejar la mínima arriba de la máxima
    return tmax_c, tmin_c, [e["nombre"] for e, _ in cerca]
