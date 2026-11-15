"""Pruebas unitarias para el módulo de NDVI de HLS (Harmonized Landsat Sentinel-2, 30 m)."""

from unittest.mock import patch
import pytest

from fieldshift.fuentes import hls_ndvi


def test_extraer_anillo_exterior_polygon():
    geom = {
        "type": "Polygon",
        "coordinates": [
            [[-56.123456, -33.654321], [-56.120000, -33.654321], [-56.120000, -33.650000], [-56.123456, -33.654321]]
        ],
    }
    anillo = hls_ndvi._extraer_anillo_exterior(geom)
    assert len(anillo) == 4
    assert anillo[0] == [-56.12346, -33.65432]
    assert anillo[0] == anillo[-1]


def test_extraer_anillo_exterior_multipolygon():
    geom = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[-56.1, -33.1], [-56.2, -33.1], [-56.2, -33.2], [-56.1, -33.1]]],
            [[[-56.1, -33.1], [-56.15, -33.1], [-56.15, -33.15], [-56.1, -33.15], [-56.1, -33.1]]],
        ],
    }
    anillo = hls_ndvi._extraer_anillo_exterior(geom)
    # Debe elegir el polígono con más puntos (el segundo tiene 5)
    assert len(anillo) == 5


def test_calcular_coincidencia_sin_modis():
    hls = [{"anio": 2024, "mes": m, "ndvi": 0.6} for m in range(1, 13)]
    res = hls_ndvi._calcular_coincidencia(hls, None)
    assert res["correlacion"] is None
    assert res["dif_media"] is None
    assert res["coincidencia_pct"] is None
    assert res["meses_comunes"] == 0


def test_calcular_coincidencia_con_datos():
    hls = [{"anio": 2024, "mes": m, "ndvi": 0.4 + m * 0.03} for m in range(1, 13)]
    modis = [{"anio": 2024, "mes": m, "ndvi": 0.42 + m * 0.03} for m in range(1, 13)]
    res = hls_ndvi._calcular_coincidencia(hls, modis)
    assert res["meses_comunes"] == 12
    assert res["correlacion"] == 1.0  # Perfect linear correlation
    assert res["dif_media"] == pytest.approx(0.02, abs=0.005)
    assert res["coincidencia_pct"] is not None and res["coincidencia_pct"] > 90


def test_armar_expresion_hls():
    coords = [[-56.15, -33.1], [-56.14, -33.1], [-56.14, -33.11], [-56.15, -33.11], [-56.15, -33.1]]
    expr = hls_ndvi.armar_expresion_hls(coords, "2026-11-15")
    assert isinstance(expr, dict)
    assert "values" in expr
    expr_str = str(expr)
    assert "NASA/HLS/HLSL30/v002" in expr_str
    assert "NASA/HLS/HLSS30/v002" in expr_str
    assert "Fmask" in expr_str


def test_consultar_hls_seccion_sin_credenciales(monkeypatch):
    monkeypatch.delenv("DESACTIVAR_EE")
    monkeypatch.setattr(hls_ndvi.cache, "leer", lambda k, c, max_dias=None: None)
    monkeypatch.setattr(hls_ndvi.modis_historia, "_cargar_sa_info", lambda: None)
    geom = {
        "type": "Polygon",
        "coordinates": [[[-56.1, -33.1], [-56.2, -33.1], [-56.2, -33.2], [-56.1, -33.1]]],
    }
    res = hls_ndvi.consultar_hls_seccion(geom)
    assert res["ok"] is False
    assert "credenciales" in res["error"].lower()


def test_consultar_hls_seccion_con_mock_ee(monkeypatch):
    monkeypatch.delenv("DESACTIVAR_EE")
    monkeypatch.setattr(hls_ndvi, "_asegurar_ee_inicializado", lambda sa_info=None: False)  # la plantilla, sin red
    monkeypatch.setattr(hls_ndvi.cache, "leer", lambda k, c, max_dias=None: None)
    monkeypatch.setattr(hls_ndvi.cache, "guardar", lambda k, c, v: None)
    monkeypatch.setattr(hls_ndvi.modis_historia, "_cargar_sa_info", lambda: {"project_id": "test-proj"})
    monkeypatch.setattr(hls_ndvi.modis_historia, "_token_bearer_sa", lambda sa: "fake-token")

    simulados = [
        {"anio": 2024, "mes": 1, "ndvi": 0.65},
        {"anio": 2024, "mes": 2, "ndvi": 0.70},
        {"anio": 2024, "mes": 3, "ndvi": 0.68},
    ]

    class MockResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"result": simulados}

    with patch("httpx.post", return_value=MockResponse()):
        geom = {
            "type": "Polygon",
            "coordinates": [[[-56.1, -33.1], [-56.2, -33.1], [-56.2, -33.2], [-56.1, -33.1]]],
        }
        res = hls_ndvi.consultar_hls_seccion(geom)
        assert res["ok"] is True
        assert len(res["mensual"]) == 3
        assert res["mensual"][0] == {"anio": 2024, "mes": 1, "ndvi": 0.65}
        assert "HLS" in res["fuente"]


def test_desactivado_no_sale_a_internet(monkeypatch):
    def prohibido(*a, **k):
        raise AssertionError("no debía pedir nada a Earth Engine")

    monkeypatch.setattr("httpx.post", prohibido)
    geom = {"type": "Polygon", "coordinates": [[[-56.1, -33.1], [-56.2, -33.1], [-56.2, -33.2], [-56.1, -33.1]]]}
    res = hls_ndvi.consultar_hls_seccion(geom)
    assert res["ok"] is False and "desactivado" in res["error"]
