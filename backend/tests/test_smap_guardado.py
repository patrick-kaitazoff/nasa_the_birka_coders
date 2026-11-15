"""SMAP guardado en el repo: el campo de ejemplo y cualquier punto de Uruguay no esperan a AppEEARS."""

from fastapi.testclient import TestClient

from fieldshift import api
from fieldshift.fuentes import smap

LAT, LON = -33.103, -56.146  # campo de ejemplo (Durazno)
LAT_OTRO, LON_OTRO = -31.71, -55.98  # Tacuarembó (sin archivo individual de AppEEARS)
LAT_FUERA, LON_FUERA = -40.0, -50.0  # Fuera de Uruguay y de la grilla


def test_el_campo_de_ejemplo_tiene_smap_guardado(monkeypatch):
    monkeypatch.delenv("EARTHDATA_USER", raising=False)
    monkeypatch.delenv("EARTHDATA_PASS", raising=False)
    monkeypatch.setattr(smap.cache, "leer", lambda *a, **k: None)
    r = smap.estado(LAT, LON)
    assert r["estado"] == "listo"  # sin cuenta de Earthdata y sin caché: sale del archivo
    assert len(r["serie"]) > 4000
    assert "bajada el" in r["fuente"]


def test_la_seca_2022_23_se_ve_en_smap():
    serie = smap.guardado(LAT, LON)["serie"]
    verano = [x["pctl"] for x in serie if "2022-12-01" <= x["fecha"] <= "2023-03-31" and x["pctl"] is not None]
    assert sum(verano) / len(verano) < 20  # percentil medio ~10: muy seco


def test_punto_cualquiera_de_uruguay_tiene_smap_de_earth_engine(monkeypatch):
    """Cualquier campo dentro de Uruguay tiene SMAP al instante vía la grilla de Earth Engine."""
    monkeypatch.delenv("EARTHDATA_USER", raising=False)
    monkeypatch.delenv("EARTHDATA_PASS", raising=False)
    monkeypatch.setattr(smap.cache, "leer", lambda *a, **k: None)
    assert smap.guardado(LAT_OTRO, LON_OTRO) is None  # no tiene archivo individual
    r = smap.estado(LAT_OTRO, LON_OTRO)
    assert r["estado"] == "listo"
    assert "Google Earth Engine" in r["fuente"]
    assert len(r["serie"]) >= 139  # histórico mensual + días recientes


def test_un_punto_fuera_de_uruguay_sigue_pidiendo(monkeypatch):
    """Fuera de Uruguay y sin caché, recurre a AppEEARS (y devuelve sin_cuenta si no hay credenciales)."""
    monkeypatch.delenv("EARTHDATA_USER", raising=False)
    monkeypatch.delenv("EARTHDATA_PASS", raising=False)
    monkeypatch.setattr(smap.cache, "leer", lambda *a, **k: None)
    assert smap.guardado(LAT_FUERA, LON_FUERA) is None
    assert smap.estado(LAT_FUERA, LON_FUERA)["estado"] == "sin_cuenta"


def test_api_smap_del_campo_de_ejemplo(monkeypatch):
    monkeypatch.delenv("FIELDSHIFT_CLAVE", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    r = TestClient(api.app).get("/api/smap", params={"lat": LAT, "lon": LON})
    assert r.status_code == 200
    assert r.json()["estado"] in ("listo", "error")  # "error" solo si no hay salida a POWER desde las pruebas


def test_api_smap_de_otro_campo_de_uruguay(monkeypatch):
    monkeypatch.delenv("FIELDSHIFT_CLAVE", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    r = TestClient(api.app).get("/api/smap", params={"lat": LAT_OTRO, "lon": LON_OTRO})
    assert r.status_code == 200
    assert r.json()["estado"] in ("listo", "error")
