"""Clima de los próximos años (NASA NEX-GDDP-CMIP6). Correr desde app/backend: .venv/Scripts/python -m pytest -q"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fieldshift.analisis import clima  # noqa: E402
from fieldshift.fuentes import cmip6  # noqa: E402
from test_motor import power_sintetico  # noqa: E402


def _cambio(dt=1.0, lluvia=1.1):
    doce = lambda v: {"media": [v] * 12, "p10": [v - 0.5] * 12, "p90": [v + 0.5] * 12}  # noqa: E731
    return {"tas": doce(dt), "tasmax": doce(dt), "tasmin": doce(dt), "pr": doce(lluvia),
            "celda": [-33.125, -56.125], "meta": {"modelos": ["a", "b"], "futuro": "2026-2035"}}


def test_el_archivo_cubre_uruguay_y_nada_mas():
    d = cmip6.cambio(-33.1, -56.15)  # Durazno
    assert d and d["celda"] == [-33.125, -56.125]
    assert all(len(d[v]["media"]) == 12 for v in ("tasmax", "tasmin", "pr"))
    # 30 modelos, escenario medio, y un cambio chico y razonable para la próxima década
    assert len(d["meta"]["modelos"]) >= 25 and d["meta"]["escenario"] == "SSP2-4.5"
    assert 0 < np.mean(d["tasmax"]["media"]) < 1.5 and 0.85 < np.mean(d["pr"]["media"]) < 1.15
    assert cmip6.cambio(-31.0, -55.5)  # Rivera
    assert cmip6.cambio(0.0, 0.0) is None  # lejos de Uruguay: años reales tal cual


def test_los_anos_reales_corridos_mes_a_mes():
    serie = clima.preparar(power_sintetico())
    fut = clima.con_cambio_mensual(serie, _cambio(1.0, 1.1))
    assert np.allclose(fut.tmax, serie.tmax + 1) and np.allclose(fut.tmin, serie.tmin + 1)
    assert np.allclose(fut.lluvia, serie.lluvia * 1.1)
    assert (fut.et0 >= serie.et0).all() and fut.et0.sum() > serie.et0.sum()  # más calor, el aire pide más agua
    # un cambio en un solo mes toca solo ese mes
    c = _cambio(0.0, 1.0)
    c["tasmax"]["media"] = [0.0] * 6 + [2.0] + [0.0] * 5
    fut = clima.con_cambio_mensual(serie, c)
    assert np.allclose((fut.tmax - serie.tmax)[serie.mes == 7], 2) and np.allclose((fut.tmax - serie.tmax)[serie.mes != 7], 0)


def test_resumen_para_el_productor():
    serie = clima.preparar(power_sintetico())
    r = clima.resumen_cambio(serie, _cambio(0.6, 1.02))
    assert r["temp_c"] == 0.6 and r["lluvia_pct"] == 2.0 and r["lluvia_pct_rango"][0] < 2 < r["lluvia_pct_rango"][1]
    assert r["modelos"] == 2 and r["futuro"] == "2026-2035"
