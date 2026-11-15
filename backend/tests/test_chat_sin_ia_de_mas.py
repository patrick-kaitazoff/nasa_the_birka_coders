"""La IA (Gemini) se llama solo para lo que la persona escribe, y si falla antes de mostrar nada contesta el modo
guiado."""

import json

from fastapi.testclient import TestClient

from fieldshift import api as api_mod
from fieldshift.agente import chat as chat_mod

client = TestClient(api_mod.app)
CONTORNO = {"type": "Polygon", "coordinates": [[[-56.2, -32.8], [-56.19, -32.8], [-56.19, -32.81], [-56.2, -32.81], [-56.2, -32.8]]]}


def _eventos(r):
    return [json.loads(l[5:]) for l in r.text.splitlines() if l.startswith("data:")]


def _con_ia(monkeypatch, eventos_ia):
    llamadas = []

    def falsa(*a, **k):
        llamadas.append(a)
        yield from eventos_ia

    monkeypatch.setattr(chat_mod, "ia_disponible", lambda: True)
    monkeypatch.setattr(chat_mod, "conversar", falsa)
    return llamadas


def test_lo_que_arma_la_app_no_llama_a_la_ia(monkeypatch):
    llamadas = _con_ia(monkeypatch, [{"tipo": "texto", "delta": "hola"}, {"tipo": "fin"}])
    campo = {"id": "t1", "contorno": CONTORNO, "secciones": []}
    r = client.post("/api/chat", json={"campo": campo, "texto": "Listo, dibujé el contorno del campo en el mapa (12 ha).", "modo": "ia", "accion": True})
    assert r.status_code == 200
    assert not llamadas
    assert any(e["tipo"] == "tarjeta" and e["tarjeta"] == "secciones" for e in _eventos(r))


def test_inicio_y_analizar_de_nuevo_tampoco(monkeypatch):
    llamadas = _con_ia(monkeypatch, [{"tipo": "fin"}])
    campo = {"id": "t2", "contorno": CONTORNO, "secciones": []}
    client.post("/api/chat", json={"campo": campo, "texto": "__inicio", "modo": "ia"})
    assert not llamadas


def test_lo_que_escribe_la_persona_va_a_la_ia(monkeypatch):
    llamadas = _con_ia(monkeypatch, [{"tipo": "texto", "delta": "Porque llueve poco."}, {"tipo": "fin"}])
    campo = {"id": "t3", "contorno": CONTORNO, "secciones": []}
    r = client.post("/api/chat", json={"campo": campo, "texto": "¿Por qué sale mejor esta opción?", "modo": "ia"})
    assert llamadas
    assert any(e.get("delta") == "Porque llueve poco." for e in _eventos(r))


def test_si_la_ia_falla_contesta_el_guiado(monkeypatch):
    _con_ia(monkeypatch, [{"tipo": "error", "mensaje": "La API de Gemini falló (503). Probá de nuevo en un rato."}, {"tipo": "fin"}])
    campo = {"id": "t4", "contorno": CONTORNO, "secciones": []}
    r = client.post("/api/chat", json={"campo": campo, "texto": "tengo 3 lotes", "modo": "ia"})
    ev = _eventos(r)
    assert not any(e["tipo"] == "error" for e in ev)
    assert any(e["tipo"] == "tarjeta" for e in ev)


def test_si_la_ia_guarda_en_la_ficha_y_despues_falla_sigue_el_guiado_con_lo_guardado(monkeypatch):
    """El caso: «Guardando en la ficha» y después Gemini no contestó. Lo guardado queda y el guiado sigue."""
    _con_ia(monkeypatch, [
        {"tipo": "herramienta", "nombre": "actualizar_campo", "estado": "inicio"},
        {"tipo": "campo_patch", "cambios": {"secciones": [{"id": "s1", "nombre": "Lote 1", "geometria": CONTORNO}]}},
        {"tipo": "herramienta", "nombre": "actualizar_campo", "estado": "fin", "error": False},
        {"tipo": "error", "mensaje": "La IA tardó demasiado en contestar."},
        {"tipo": "fin"},
    ])
    campo = {"id": "t5", "contorno": CONTORNO, "secciones": []}
    r = client.post("/api/chat", json={"campo": campo, "texto": "tengo un solo lote", "modo": "ia"})
    ev = _eventos(r)
    assert any(e["tipo"] == "campo_patch" for e in ev)
    assert not any(e["tipo"] == "error" for e in ev)
    # con el lote ya guardado, el guiado no vuelve a pedir las secciones
    assert not any(e["tipo"] == "tarjeta" and e["tarjeta"] == "secciones" for e in ev)


def test_la_ia_piensa_poco_y_espera_25_segundos():
    from fieldshift.agente import chat
    assert chat.TOPE_GEMINI_MS == 25_000
    assert chat._config("es").thinking_config.thinking_level.name == "LOW"
