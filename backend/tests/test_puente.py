"""Pruebas del puente remoto (el de Vercel), con la caché en memoria que usa la librería de Vercel fuera de Vercel.
Sin internet. Correr desde app/backend: .venv/Scripts/python -m pytest -q"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from fieldshift import api  # noqa: E402
from fieldshift.agente import puente  # noqa: E402

CLAVE = "clave-de-prueba"


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("FIELDSHIFT_PUENTE", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("FIELDSHIFT_PUENTE_CLAVE", CLAVE)
    monkeypatch.setattr(puente, "_almacen_remoto", None)
    return TestClient(api.app)


def test_sin_clave_configurada_no_existe(monkeypatch):
    monkeypatch.delenv("FIELDSHIFT_PUENTE", raising=False)
    monkeypatch.delenv("FIELDSHIFT_PUENTE_CLAVE", raising=False)
    c = TestClient(api.app)
    assert c.get("/api/puente/pendientes").status_code == 404
    assert c.get("/api/salud?puente=1").json()["modelo"] != "puente de prueba"


def test_solo_con_la_clave(cliente):
    assert cliente.get("/api/puente/pendientes").status_code == 401
    assert cliente.get("/api/puente/pendientes", headers={"X-Puente-Clave": "otra"}).status_code == 401
    assert cliente.get("/api/puente/pendientes", headers={"X-Puente-Clave": CLAVE}).status_code == 200


def test_solo_los_chats_que_lo_piden(cliente):
    assert cliente.get("/api/salud?puente=1").json()["modelo"] == "puente de prueba"
    assert cliente.get("/api/salud").json()["modelo"] != "puente de prueba"


def test_ida_y_vuelta(cliente):
    h = {"X-Puente-Clave": CLAVE}
    recibidos: list[dict] = []
    hilo = threading.Thread(target=lambda: recibidos.extend(puente.conversar({"id": "c1", "secciones": []}, "hola")))
    hilo.start()

    pend = cliente.get("/api/puente/pendientes", params={"esperar": 5}, headers=h).json()
    assert [p["texto"] for p in pend] == ["hola"]
    mid = pend[0]["id"]
    assert cliente.get(f"/api/puente/entrada/{mid}", headers=h).json()["campo"]["id"] == "c1"

    cliente.post(f"/api/puente/salida/{mid}", json=[{"tipo": "texto", "delta": "Buenas"}], headers=h)
    cliente.post(f"/api/puente/salida/{mid}", json=[{"tipo": "fin"}], headers=h)
    hilo.join(timeout=10)
    assert recibidos == [{"tipo": "texto", "delta": "Buenas"}, {"tipo": "fin"}]
    # contestado, deja de figurar como pendiente
    assert cliente.get("/api/puente/pendientes", headers=h).json() == []


def test_corta_antes_del_limite_de_vercel(cliente, monkeypatch):
    monkeypatch.setattr(puente, "ESPERA_MAX_REMOTO", 1.5)
    t = time.time()
    evs = list(puente.conversar({"id": "c2"}, "nadie contesta"))
    assert time.time() - t < 5
    assert evs[0]["tipo"] == "error" and evs[-1] == {"tipo": "fin"}
    assert cliente.get("/api/puente/pendientes", headers={"X-Puente-Clave": CLAVE}).json() == []
