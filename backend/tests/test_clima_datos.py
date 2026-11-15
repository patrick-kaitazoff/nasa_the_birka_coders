"""Lo que la app dice de los datos del clima: días completados y lluvia dudosa. Sin red."""

import datetime as dt

import numpy as np
import pytest

from fieldshift.analisis import clima

VARS = ("T2M_MAX", "T2M_MIN", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN", "RH2M", "WS2M", "GWETROOT")


def _power(desde: dt.date, dias: int, lluvia=None) -> dict:
    fechas = [(desde + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(dias)]
    p = {"fechas": fechas, "lat": -33.0, "lon": -56.0, "elevacion": 100}
    valores = {"T2M_MAX": 25.0, "T2M_MIN": 12.0, "PRECTOTCORR": 3.0, "ALLSKY_SFC_SW_DWN": 18.0, "RH2M": 70.0,
               "WS2M": 3.0, "GWETROOT": 0.6}
    for v in VARS:
        p[v] = [valores[v]] * dias
    if lluvia is not None:
        p["PRECTOTCORR"] = list(lluvia)
    return p


def test_cuenta_los_dias_completados():
    p = _power(dt.date(2020, 1, 1), 10)
    p["PRECTOTCORR"][2] = None
    p["T2M_MAX"][2] = None  # mismo día: cuenta una vez
    p["RH2M"][7] = None
    s = clima.preparar(p)
    assert s.dias_completados == 2
    assert not np.isnan(s.lluvia).any()
    assert clima.aviso_completados(s) == ("2 de 10 días no tenían algún dato de la NASA y se completaron con el promedio "
                                          "de ese mismo día en los otros años.")


def test_sin_huecos_lo_dice():
    s = clima.preparar(_power(dt.date(2020, 1, 1), 1500))
    assert s.dias_completados == 0
    assert clima.aviso_completados(s) == "Los 1.500 días tienen todos sus datos de la NASA: no se completó ninguno."


def _lluvia_con_hueco(desde: dt.date, hasta: dt.date, mm_hueco: float = 0.01):
    """Cuatro años con 3 mm por día, salvo entre `desde` y `hasta` (como POWER en 2022/23)."""
    inicio = dt.date(2021, 1, 1)
    dias = (dt.date(2025, 1, 1) - inicio).days
    return inicio, dias, [mm_hueco if desde <= inicio + dt.timedelta(days=i) <= hasta else 3.0 for i in range(dias)]


def test_marca_los_meses_seguidos_casi_sin_lluvia():
    inicio, dias, ll = _lluvia_con_hueco(dt.date(2022, 10, 1), dt.date(2023, 7, 31))
    s = clima.preparar(_power(inicio, dias, ll))
    d = clima.lluvia_dudosa(s)
    assert d == [{"desde": "10/2022", "hasta": "7/2023", "meses": 10, "mm": 3.0}]
    assert clima.aviso_lluvia_dudosa(s, d[0]).startswith(
        "La lluvia de NASA POWER casi no registra agua de 10/2022 a 7/2023 (3 mm en 10 meses seguidos).")


def test_dos_meses_secos_no_alcanzan():
    inicio, dias, ll = _lluvia_con_hueco(dt.date(2022, 12, 1), dt.date(2023, 1, 31))
    assert clima.lluvia_dudosa(clima.preparar(_power(inicio, dias, ll))) == []


def test_un_mes_incompleto_no_cuenta():
    # la serie termina a mitad de un tramo seco: los meses completos son solo dos
    inicio = dt.date(2023, 1, 1)
    ll = [3.0] * 31 + [0.0] * (28 + 31 + 10)
    assert clima.lluvia_dudosa(clima.preparar(_power(inicio, len(ll), ll))) == []


def test_una_variable_sin_ningun_dato_es_error_y_no_ceros():
    p = _power(dt.date(2020, 1, 1), 10)
    p["PRECTOTCORR"] = [None] * 10
    with pytest.raises(ValueError, match="lluvia"):
        clima.preparar(p)


def test_tormentas_cuenta_solo_los_anios_enteros_de_imerg():
    """: lluvias de 50 mm o más por año y por mes, sin mezclar la lluvia de POWER de antes de IMERG."""
    inicio = dt.date(1998, 1, 1)
    dias = (dt.date(2010, 1, 1) - inicio).days
    fechas = [inicio + dt.timedelta(days=i) for i in range(dias)]
    # una de 60 mm cada 15 de abril; en los años de POWER (antes de 2001), además, una de 120 mm cada 15 de enero
    lluvia = [60.0 if (f.month, f.day) == (4, 15) else 120.0 if (f.year < 2001 and (f.month, f.day) == (1, 15)) else 2.0
              for f in fechas]
    p = _power(inicio, dias, lluvia)
    p["lluvia"] = {"fuente": "GPM IMERG", "desde": "20000601", "dias_imerg": 100}
    t = clima.tormentas(clima.preparar(p))
    assert t["periodo"] == "2001-2009" and t["anios"] == 9
    assert t["por_anio"] == 1.0
    assert t["por_mes"][3] == 1.0 and sum(t["por_mes"]) == 1.0
    assert t["grandes"] == 0 and t["cada_anios_grande"] is None
    assert t["meses_pico"][0] == "abr"
    assert t["fuente"] == "GPM IMERG"


def test_tormentas_sin_imerg_usa_power_y_pocos_anios_no_da_nada():
    p = _power(dt.date(2020, 1, 1), 1500)
    assert clima.tormentas(clima.preparar(p)) is None  # cuatro años: muy pocos
    p = _power(dt.date(2010, 1, 1), 8 * 365 + 2, [55.0 if i % 365 == 30 else 1.0 for i in range(8 * 365 + 2)])
    t = clima.tormentas(clima.preparar(p))
    assert t["fuente"] == "NASA POWER" and t["por_anio"] == 1.0 and t["por_mes"][0] == 1.0  # el día 31 de cada año: enero
