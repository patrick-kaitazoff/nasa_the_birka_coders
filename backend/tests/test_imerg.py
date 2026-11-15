"""Lluvia de GPM IMERG en lugar de la de NASA POWER, sin red."""

from fieldshift.fuentes import imerg

CSV = """prod_name,GPM_3IMERGDF.07
unit,mm/day
undef,-9999.9
lat,-33.15
lon,-56.15

Timestamp (UTC),Data
2023-01-01 00:00,4.035
2023-01-02 00:00,0
2023-01-03 00:00,-9999.9
"""


def test_leer_csv_de_giovanni():
    assert imerg.leer_csv(CSV) == {"20230101": 4.035, "20230102": 0.0, "20230103": None}
    assert imerg.leer_csv("sin datos") == {}


def test_celda_de_imerg():
    # Durazno del ejemplo: -33.103, -56.146 → centro -33.15, -56.15 (lo que devolvió Giovanni)
    assert imerg._celda(-33.103) == -33.15
    assert imerg._celda(-56.146) == -56.15
    assert imerg._celda(-34.6) == -34.55


def _power():
    return {"fechas": ["19991231", "20230101", "20230102", "20230103"], "PRECTOTCORR": [5.0, 0.0, 0.0, 1.0], "lat": -33.0}


def test_la_lluvia_sale_de_imerg_y_lo_que_falta_de_power(monkeypatch):
    monkeypatch.setattr(imerg, "serie", lambda lat, lon: {
        "fechas": ["20230101", "20230102", "20230103"], "mm": [4.035, 0.0, None], "lat": -33.15, "lon": -56.15,
        "fuente": imerg.NOMBRE})
    r = imerg.con_lluvia_imerg(_power(), -33.1, -56.1)
    # antes de IMERG (1999) y el día sin dato (None) quedan de POWER
    assert r["PRECTOTCORR"] == [5.0, 4.04, 0.0, 1.0]
    assert r["PRECTOTCORR_POWER"] == [5.0, 0.0, 0.0, 1.0]
    assert r["lluvia"]["dias_imerg"] == 2 and r["lluvia"]["dias_power"] == 2
    assert r["lluvia"]["desde"] == "20230101"
    # no se mezcla dos veces
    assert imerg.con_lluvia_imerg(r, -33.1, -56.1) is r


def test_si_imerg_falla_queda_power_y_lo_dice(monkeypatch):
    def falla(lat, lon):
        raise RuntimeError("sin red")
    monkeypatch.setattr(imerg, "serie", falla)
    r = imerg.con_lluvia_imerg(_power(), -33.1, -56.1)
    assert r["PRECTOTCORR"] == [5.0, 0.0, 0.0, 1.0]
    assert r["lluvia"]["fuente"] == "NASA POWER" and r["lluvia"]["dias_imerg"] == 0
    assert "sin red" in r["lluvia"]["motivo"]


def test_la_lluvia_de_power_de_antes_de_imerg_se_ajusta_a_imerg():
    # POWER achata la lluvia. Si en los años con las dos POWER da la mitad que IMERG, los días de POWER sin
    # IMERG (antes de 2000) pasan a valer el doble; el mes en que POWER falla (0 mm) no entra en el ajuste.
    import datetime as dt

    import numpy as np

    rng = np.random.default_rng(1)
    dias = [dt.date(1991, 1, 1) + dt.timedelta(days=i) for i in range(365 * 30)]
    fechas = [d.strftime("%Y%m%d") for d in dias]
    imerg_mm = {}
    power = []
    for f in fechas:
        lluvia = float(rng.exponential(8)) if rng.random() < 0.3 else 0.0
        if f >= "20000601":
            imerg_mm[f] = lluvia
        power.append(0.0 if f.startswith("201501") else lluvia / 2)  # en enero de 2015 POWER «falla»
    aj, n = imerg.ajustar_power(fechas, power, imerg_mm)
    antes = [i for i, f in enumerate(fechas) if f < "20000601"]
    assert n == len(antes)
    assert abs(sum(aj[i] for i in antes) / sum(power[i] for i in antes) - 2) < 0.1
    # los días con IMERG no se tocan acá (los reemplaza con_lluvia_imerg)
    assert aj[-1] == power[-1]
