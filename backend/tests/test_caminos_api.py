"""Pruebas para el endpoint de caminos por departamento (/api/caminos/{depto})."""

from fastapi.testclient import TestClient

from fieldshift.api import app

client = TestClient(app)


def test_caminos_soriano_existente():
    r = client.get("/api/caminos/soriano")
    assert r.status_code == 200
    datos = r.json()
    assert datos.get("departamento") == "SORIANO"
    assert "tertiary" in datos
    assert "unclassified" in datos
    assert "track" in datos
    assert len(datos["tertiary"]["coordinates"]) > 0
    assert len(datos["unclassified"]["coordinates"]) > 0
    assert len(datos["track"]["coordinates"]) > 0
    assert "Cache-Control" in r.headers
    assert "max-age=86400" in r.headers["Cache-Control"]


def test_caminos_soriano_mayusculas_con_espacios_o_acentos():
    r = client.get("/api/caminos/SORIANO")
    assert r.status_code == 200
    assert r.json().get("departamento") == "SORIANO"


def test_caminos_departamento_inexistente_responde_404():
    r = client.get("/api/caminos/inexistente_123")
    assert r.status_code == 404
