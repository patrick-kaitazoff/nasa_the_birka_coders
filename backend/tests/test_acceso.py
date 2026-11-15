"""Contraseña de la app publicada (acceso.py)."""

import importlib

import pytest
from fastapi.testclient import TestClient

from fieldshift import api


@pytest.fixture
def cliente(monkeypatch):
    def hacer(clave: str | None, vercel: bool = False):
        monkeypatch.delenv("FIELDSHIFT_CLAVE", raising=False)
        monkeypatch.delenv("VERCEL", raising=False)
        if clave is not None:
            monkeypatch.setenv("FIELDSHIFT_CLAVE", clave)
        if vercel:
            monkeypatch.setenv("VERCEL", "1")
        return TestClient(api.app, base_url="https://testserver")
    return hacer


def test_en_la_pc_no_pide_nada(cliente):
    c = cliente(None)
    assert c.get("/api/catalogo").status_code == 200


def test_sin_clave_pide_contrasenia(cliente):
    c = cliente("secreta")
    r = c.get("/api/catalogo")
    assert r.status_code == 401
    assert r.headers["cache-control"] == "no-store"
    r = c.get("/")
    assert r.status_code == 401 and "contraseña" in r.text and "noindex" in r.text


def test_clave_mala_avisa(cliente):
    c = cliente("secreta")
    r = c.get("/?clave=otra", follow_redirects=False)
    assert r.status_code == 401 and "Esa no es la contraseña" in r.text
    assert "fs_acceso" not in r.cookies


def test_clave_buena_guarda_cookie_y_limpia_la_direccion(cliente):
    c = cliente("secreta")
    r = c.get("/app?demo=1&clave=secreta", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app?demo=1"
    assert "secreta" not in r.headers["set-cookie"]
    assert "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/api/catalogo").status_code == 200  # la cookie quedó en el cliente


def test_salud_y_puente_quedan_libres(cliente):
    c = cliente("secreta")
    assert c.get("/api/salud").status_code == 200
    assert c.get("/api/puente/pendientes").status_code != 401 or "contraseña" not in c.get("/api/puente/pendientes").text


def test_en_vercel_sin_clave_queda_abierta(cliente):
    # La app se publica sin contraseña; antes, en Vercel sin la variable no entraba nadie
    from fieldshift import acceso
    c = cliente(None, vercel=True)
    assert c.get("/api/catalogo").status_code == 200
    assert "contraseña" not in c.get("/").text
    assert acceso.cache_publico() == "public"


def test_con_clave_el_cdn_no_guarda_copias(cliente):
    from fieldshift import acceso
    cliente("secreta")
    assert acceso.cache_publico() == "private"
    cliente(None)
    assert acceso.cache_publico() == "public"
