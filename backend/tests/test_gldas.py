"""Pruebas unitarias para GLDAS 2.1 (NASA Noah, 0,25°) sin salir a internet."""

import datetime as dt
from unittest.mock import patch
import pytest

from fieldshift.analisis import humedad
from fieldshift.fuentes import gldas


def test_calcular_anomalias_mensuales():
    # 2 años sintéticos con valores conocidos
    mensual = []
    for anio in (2020, 2021):
        for mes in range(1, 13):
            # En mes 12 del 2020 ponemos un valor muy bajo (sequía)
            val = 150.0 if (anio == 2020 and mes == 12) else 350.0
            mensual.append({
                "anio": anio,
                "mes": mes,
                "root_sm": val,
                "sm_0_10": val * 0.1,
                "sm_10_40": val * 0.3,
                "sm_40_100": val * 0.6,
                "evap_mm_dia": 2.5,
            })

    anomalias = gldas._calcular_anomalias_mensuales(mensual)
    assert len(anomalias) == 24
    assert "2020-12" in anomalias
    assert "2021-12" in anomalias
    # El mes 12 de 2020 (150 mm) debe tener anomalía negativa respecto al promedio
    assert anomalias["2020-12"] < -0.9
    assert anomalias["2021-12"] > 0.9


def test_comparar_con_balance_secas():
    gldas_anom = {
        "2008-10": -1.3, "2008-11": -1.8, "2008-12": -1.9, "2009-01": -1.5,
        "2022-10": -1.4, "2022-11": -1.9, "2022-12": -2.0, "2023-01": -1.7,
    }
    # Rellenar algunos otros meses neutros
    for a in range(2005, 2010):
        for m in range(1, 13):
            k = f"{a}-{m:02d}"
            gldas_anom.setdefault(k, 0.1)

    app_anom = dict(gldas_anom)  # Coincidencia perfecta
    comp = gldas.comparar_con_balance(gldas_anom, app_anom)
    assert comp["correlacion"] == 1.0
    assert comp["coinciden_secas"] is True
    assert "2008/09 y 2022/23" in comp["frase_secas"]


def test_armar_expresion_gldas():
    expr = gldas.armar_expresion_gldas(-33.1, -56.15, "2026-11-15", 36)
    assert isinstance(expr, dict)
    assert "values" in expr
    expr_str = str(expr)
    assert "NASA/GLDAS/V021/NOAH/G025/T3H" in expr_str
    assert "RootMoist_inst" in expr_str
    assert "SoilMoi0_10cm_inst" in expr_str


def test_consultar_gldas_desactivado_por_ee():
    # conftest fija DESACTIVAR_EE=1
    res = gldas.consultar_gldas(-33.1, -56.15)
    assert res["ok"] is False
    assert "DESACTIVAR_EE" in res["motivo"]


def test_consultar_gldas_mock_ee(monkeypatch):
    monkeypatch.delenv("DESACTIVAR_EE", raising=False)
    monkeypatch.setattr(gldas.cache, "leer", lambda k, c, max_dias=None: None)
    monkeypatch.setattr(gldas.cache, "guardar", lambda k, c, v: None)
    monkeypatch.setattr(gldas.modis_historia, "_cargar_sa_info", lambda: {"project_id": "test-proj"})
    monkeypatch.setattr(gldas.modis_historia, "_token_bearer_sa", lambda sa: "token-mock")

    simulados = [
        {"anio": 2023, "mes": 1, "root_sm": 180.0, "sm_0_10": 18.0, "sm_10_40": 54.0, "sm_40_100": 108.0, "evap": 3e-5},
        {"anio": 2023, "mes": 2, "root_sm": 200.0, "sm_0_10": 20.0, "sm_10_40": 60.0, "sm_40_100": 120.0, "evap": 3.2e-5},
        {"anio": 2023, "mes": 3, "root_sm": 220.0, "sm_0_10": 22.0, "sm_10_40": 66.0, "sm_40_100": 132.0, "evap": 2.8e-5},
    ]

    class MockResp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"result": simulados}

    with patch("httpx.post", return_value=MockResp()):
        res = gldas.consultar_gldas(-33.1, -56.15)
        assert res["ok"] is True
        assert len(res["mensual"]) == 3
        assert res["mensual"][0]["root_sm"] == 180.0
        assert "GLDAS" in res["fuente"]


def test_humedad_comparar_integra_gldas():
    from test_motor import power_sintetico
    from fieldshift.analisis import clima as clima_mod

    pw = power_sintetico(anios=(2020, 2021, 2022))
    serie = clima_mod.preparar(pw)

    smap = [{"fecha": f"{d.year:04d}-{d.month:02d}-15", "sm": 0.25, "pctl": 45} for d in serie.fechas[::30]]
    gldas_data = {
        "ok": True,
        "fuente": "NASA GLDAS 2.1",
        "anomalias": {f"{d.year:04d}-{d.month:02d}": -0.5 for d in serie.fechas[::30]},
        "limites": ["Límite GLDAS"],
    }

    res = humedad.comparar(smap, serie, 120.0, gldas=gldas_data)
    assert res["ok"] is True
    assert "gldas" in res
    assert res["gldas_fuente"] == "NASA GLDAS 2.1"
    assert any("Límite GLDAS" in l for l in res["limites"])
    assert "gldas_anomalia" in res["mensual"][0]


def test_meses_pedidos_empiezan_en_enero_2000(monkeypatch):
    """Pedir un mes de más llegaba a diciembre de 1999, sin imágenes, y Earth Engine rechazaba todo con un 400."""
    monkeypatch.delenv("DESACTIVAR_EE", raising=False)
    monkeypatch.setattr(gldas.cache, "leer", lambda k, c, max_dias=None: None)
    monkeypatch.setattr(gldas.cache, "guardar", lambda k, c, v: None)
    monkeypatch.setattr(gldas.modis_historia, "_cargar_sa_info", lambda: {"project_id": "p"})
    monkeypatch.setattr(gldas.modis_historia, "_token_bearer_sa", lambda sa: "t")
    pedidos = []
    monkeypatch.setattr(gldas, "armar_expresion_gldas", lambda lat, lon, hoy, n, sa_info=None: pedidos.append(n) or {})

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"result": [{"anio": 2000, "mes": 1, "root_sm": gldas.SIN_DATO, "sm_0_10": None,
                                "sm_10_40": 1.0, "sm_40_100": 2.0, "evap": gldas.SIN_DATO}]}

    with patch("httpx.post", return_value=Resp()):
        res = gldas.consultar_gldas(-33.1, -56.15, fecha_hasta=dt.date(2026, 11, 15))
    assert pedidos == [(2026 - 2000) * 12 + 10]  # enero de 2000 a octubre de 2026
    assert res["mensual"][0]["root_sm"] is None and res["mensual"][0]["evap_mm_dia"] is None


def test_plantilla_pide_valor_por_defecto_en_meses_vacios():
    expr = gldas.armar_expresion_gldas(-33.1, -56.15, "2026-11-15", 12)
    gets = [v["functionInvocationValue"] for v in expr["values"]["1"]["dictionaryValue"]["values"].values()
            if v["functionInvocationValue"]["functionName"] == "Dictionary.get"]
    assert len(gets) == 5
    assert all(g["arguments"]["defaultValue"] == {"constantValue": gldas.SIN_DATO} for g in gets)


def test_frase_secas_usa_los_valores():
    g = {f"{a}-{m:02d}": 0.1 for a in range(2005, 2010) for m in range(1, 13)}
    g.update({"2008-12": -1.9, "2022-12": -2.0})
    a = dict(g, **{"2008-12": -1.6, "2022-12": -1.4})
    comp = gldas.comparar_con_balance(g, a)
    assert comp["coinciden_secas"] is True
    assert "app 1,6, GLDAS 1,9" in comp["frase_secas"] and "app 1,4, GLDAS 2,0" in comp["frase_secas"]
