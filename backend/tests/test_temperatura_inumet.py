"""Temperatura de NASA POWER corregida con INUMET y viento roto. Correr desde app/backend: .venv/Scripts/python -m pytest -q"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fieldshift.analisis import clima  # noqa: E402
from fieldshift.fuentes import temperatura_inumet as ti  # noqa: E402
from test_motor import power_sintetico  # noqa: E402


def test_el_archivo_tiene_las_7_estaciones():
    d = ti._datos()
    assert len(d["estaciones"]) == 7
    for e in d["estaciones"]:
        assert len(e["tmax"]) == 12 and len(e["tmin"]) == 12
        for q in e["tmax"].values():
            assert q["power"] == sorted(q["power"]) and q["estacion"] == sorted(q["estacion"]) and q["dias"] >= 60


def test_en_la_costa_el_verano_baja_y_fuera_de_uruguay_no_cambia():
    mes = np.array([1] * 31 + [7] * 31)
    tmax = np.full(62, 31.0)
    tmin = np.full(62, 18.0)
    tx, tn, est = ti.corregir(mes, tmax, tmin, -34.79, -56.26)  # Aeropuerto Melilla
    assert est and est[0] == "Aeropuerto Melilla"
    assert tx[:31].mean() < 29.5  # POWER pasa ~3 °C de más en el verano de la costa
    assert (tn <= tx).all()
    tx, tn, est = ti.corregir(mes, tmax, tmin, 40.0, -95.0)
    assert est == [] and (tx == tmax).all() and (tn == tmin).all()


def test_los_pesos_de_las_dos_estaciones_mas_cercanas():
    cerca = ti.estaciones_cercanas(-33.1, -56.15)  # Durazno
    assert [e["nombre"] for e, _ in cerca][0] == "Paso de los Toros"
    assert abs(sum(w for _, w in cerca) - 1) < 1e-9
    assert ti.estaciones_cercanas(0.0, 0.0) == []


def test_preparar_corrige_y_arregla_el_viento_roto():
    pw = power_sintetico()
    cruda = clima.preparar(pw, corregir_temperatura=False)
    corr = clima.preparar(pw)
    assert corr.temp_corregida and not cruda.temp_corregida
    enero = corr.mes == 1
    assert corr.tmax[enero].mean() < cruda.tmax[enero].mean()
    assert not corr.viento_fijo
    roto = clima.preparar({**pw, "WS2M": [0.1] * len(pw["WS2M"])})
    assert roto.viento_fijo and np.allclose(roto.viento, 2.0)
