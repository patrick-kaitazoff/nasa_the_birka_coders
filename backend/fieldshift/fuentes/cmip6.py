"""Cambio de clima proyectado para la celda del campo (NASA NEX-GDDP-CMIP6), ya calculado para todo Uruguay.

Para cada celda de 0,25° (~25 km): cuánto cambian, mes por mes, la temperatura media, máxima y mínima
(°C) y la lluvia (cociente) entre 1991-2020 y 2026-2035 con el escenario medio de emisiones (SSP2-4.5): el promedio de
30 modelos climáticos y su rango (p10 y p90). Lo arma `scripts/cmip6_uruguay_ee.py` con Earth Engine; la app solo lee
el archivo, así que no suma tiempo ni depende de Earth Engine en Vercel.

Se usan la máxima y la mínima (la media, `tas`, de TaiESM1 viene rota: +3,3 °C con máxima y mínima +1 °C). CESM2,
CESM2-WACCM e IITM-ESM no entran: sus archivos de 2026 dan error en Earth Engine.

Fuera de Uruguay (o lejos de toda celda con datos) devuelve None y el motor usa el clima de los años reales tal cual.
"""

from __future__ import annotations

import functools
import gzip
import json
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parents[1] / "datos" / "cmip6_uruguay.json.gz"
DISTANCIA_MAX = 0.4  # grados: más lejos que eso de una celda con datos, no se usa


@functools.lru_cache(maxsize=1)
def _datos() -> dict | None:
    if not ARCHIVO.exists():
        return None
    return json.loads(gzip.decompress(ARCHIVO.read_bytes()).decode("utf-8"))


def cambio(lat: float, lon: float) -> dict | None:
    """{"tas", "tasmax", "tasmin": {"media", "p10", "p90"} en °C por mes; "pr": cocientes; "celda"; "meta"}."""
    d = _datos()
    if not d:
        return None
    celdas = [c for c in d["celdas"] if "tas" in c]
    if not celdas:
        return None
    c = min(celdas, key=lambda c: (c["lat"] - lat) ** 2 + (c["lon"] - lon) ** 2)
    if ((c["lat"] - lat) ** 2 + (c["lon"] - lon) ** 2) ** 0.5 > DISTANCIA_MAX:
        return None
    return {**{k: c[k] for k in ("tas", "tasmax", "tasmin", "pr")}, "anual": c.get("anual"), "celda": [c["lat"], c["lon"]],
            "meta": d["meta"]}
