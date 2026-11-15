"""El index.html tiene que cambiar de ETag cuando cambia su contenido, aunque fecha y tamaño sean iguales.

En Vercel todos los archivos tienen la misma fecha y el index.html pesa siempre lo mismo (los hashes de Vite tienen
largo fijo). Con el ETag de fecha + tamaño, cada subida nueva respondía 304 y el navegador se quedaba con el
index.html viejo, que pedía JS borrado: página en blanco."""

import os

from fastapi.testclient import TestClient

from fieldshift import api

FECHA_VERCEL = 1540000000  # La fecha que Vercel les pone a todos los archivos


def test_etag_cambia_con_el_contenido_aunque_fecha_y_tamano_coincidan(tmp_path):
    viejo = '<script src="/assets/index-AAAA.js"></script>'
    nuevo = '<script src="/assets/index-BBBB.js"></script>'
    assert len(viejo) == len(nuevo)
    idx = tmp_path / "index.html"

    idx.write_text(viejo)
    os.utime(idx, (FECHA_VERCEL, FECHA_VERCEL))
    r1 = api._archivo_dist(idx, None)

    idx.write_text(nuevo)
    os.utime(idx, (FECHA_VERCEL, FECHA_VERCEL))
    r2 = api._archivo_dist(idx, r1.headers["etag"])

    assert r2.status_code == 200, "con el ETag viejo tiene que mandar el index.html nuevo, no 304"
    assert r2.body.decode() == nuevo
    assert r1.headers["etag"] != r2.headers["etag"]


def test_mismo_contenido_responde_304_y_no_cache(tmp_path):
    idx = tmp_path / "index.html"
    idx.write_text("<html></html>")
    r1 = api._archivo_dist(idx, None)
    r2 = api._archivo_dist(idx, r1.headers["etag"])
    assert r2.status_code == 304
    assert r1.headers["cache-control"] == "no-cache"


def test_assets_con_hash_se_guardan_un_anio():
    if not api.DIST.exists():
        return
    js = next((api.DIST / "assets").glob("*.js")).name
    r = TestClient(api.app).get(f"/assets/{js}")
    assert r.status_code == 200
    assert "immutable" in r.headers["cache-control"]


def test_index_por_la_app_trae_etag_de_contenido():
    if not api.DIST.exists():
        return
    c = TestClient(api.app)
    r = c.get("/")
    assert r.status_code == 200 and "<div id=\"root\">" in r.text
    assert r.headers["cache-control"] == "no-cache"
    assert c.get("/", headers={"If-None-Match": r.headers["etag"]}).status_code == 304
    assert c.get("/", headers={"If-None-Match": '"otro"'}).status_code == 200

def test_api_departamentos_sirve_archivo_estatico_con_cache_publica():
    """/api/departamentos debe servir departamentos_uy.json directamente con Cache-Control público de 24 h."""
    c = TestClient(api.app)
    r = c.get("/api/departamentos")
    assert r.status_code == 200
    assert "public" in r.headers["cache-control"]
    assert "86400" in r.headers["cache-control"]
    data = r.json()
    assert data.get("type") == "FeatureCollection"
    assert len(data.get("features", [])) == 19
    nombres = {f["properties"]["nombre"] for f in data["features"]}
    assert "DURAZNO" in nombres and "MONTEVIDEO" in nombres and "ARTIGAS" in nombres


def test_lo_compilado_y_los_mapas_fijos_piden_guardarse_en_la_red_de_vercel(tmp_path, monkeypatch):
    """Sin esta cabecera cada archivo despierta a la función de Python. Con contraseña no va: la red se lo daría a cualquiera."""
    idx = tmp_path / "index.html"
    idx.write_text("<html></html>")
    assert api._archivo_dist(idx, None).headers["vercel-cdn-cache-control"] == "max-age=86400"
    r = TestClient(api.app).get("/api/departamentos")
    assert r.headers["vercel-cdn-cache-control"] == "max-age=86400"
    assert "86400" in r.headers["cache-control"]

    monkeypatch.setattr(api.acceso, "activa", lambda: True)
    assert "vercel-cdn-cache-control" not in api._archivo_dist(idx, None).headers
    assert "vercel-cdn-cache-control" not in api._un_dia()


def test_la_foto_webp_sale_con_su_tipo(tmp_path):
    foto = tmp_path / "portada.webp"
    foto.write_bytes(b"RIFF")
    assert api._archivo_dist(foto, None).media_type == "image/webp"
