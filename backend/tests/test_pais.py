"""/api/pais: el país de quien visita sale de la cabecera que pone Vercel."""
from fastapi.testclient import TestClient

from fieldshift.api import app

cliente = TestClient(app)


def test_sin_cabecera_devuelve_null():
    # en la PC no hay cabecera: la pantalla se queda con lo que adivinó por la zona horaria
    assert cliente.get("/api/pais").json() == {"pais": None}


def test_con_cabecera_de_vercel():
    r = cliente.get("/api/pais", headers={"x-vercel-ip-country": "uy"})
    assert r.json() == {"pais": "UY"}
    # depende de quién pide: la CDN no lo puede guardar para otros
    assert "no-store" in r.headers["cache-control"]
