"""El asesor justifica decisiones con consultar_analisis y cuenta qué cambió al rehacer el análisis."""

import copy
import json
from pathlib import Path

from fieldshift.agente import estado, herramientas

DEMO = Path(__file__).resolve().parents[2] / "frontend" / "public" / "ejemplos" / "campo_demo.fieldshift.json"


def _demo():
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    return d["campo"], d["analisis"]


def _correr(nombre, entrada, campo):
    evs = list(herramientas.ejecutar(nombre, entrada, {"campo": campo}))
    return evs[-1]


def test_consultar_analisis_da_ranking_prioridades_y_detalle():
    campo, analisis = _demo()
    estado.guardar_analisis(campo.get("id", "campo"), analisis)
    sec = analisis["secciones"][0]
    otra = sec["todas"][1]["id"]
    r = _correr("consultar_analisis", {"seccion_id": sec["nombre"], "rotacion_id": otra}, campo)
    assert not r["es_error"]
    d = json.loads(r["contenido"])
    assert d["recomendada_id"] == sec["recomendada_id"]
    assert [x["id"] for x in d["ranking_todas"]] == [e["id"] for e in sec["todas"]]
    assert set(d["prioridades_usadas"]) >= {"suelo", "ingreso"}
    assert d["detalle"]["id"] == otra and "puntajes" in d["detalle"]


def test_consultar_analisis_sin_seccion_lista_las_que_hay():
    campo, analisis = _demo()
    estado.guardar_analisis(campo.get("id", "campo"), analisis)
    r = _correr("consultar_analisis", {"seccion_id": "no-existe"}, campo)
    assert r["es_error"] and analisis["secciones"][0]["nombre"] in r["contenido"]


def test_cambios_entre_detecta_otra_recomendacion():
    _, antes = _demo()
    despues = copy.deepcopy(antes)
    s = despues["secciones"][0]
    s["recomendada_id"] = s["todas"][1]["id"]
    c = herramientas.cambios_entre(antes, despues)
    primera = c["secciones"][0]
    assert primera["cambio_la_recomendacion"] is True
    assert primera["recomendada_antes"] != primera["recomendada_ahora"]
    assert all(not x["cambio_la_recomendacion"] for x in c["secciones"][1:])


# ---------------------------------------------------------------- el bucle del chat con Gemini (sin red)

from google.genai import types  # noqa: E402

from fieldshift.agente import chat  # noqa: E402


class _Modelos:
    def __init__(self, turnos):
        self.turnos = list(turnos)
        self.pedidos = []

    def generate_content_stream(self, model, contents, config):
        self.pedidos.append(contents)
        for trozo in self.turnos.pop(0):
            yield trozo


class _Cliente:
    def __init__(self, turnos):
        self.models = _Modelos(turnos)


def _trozo(*partes, fin=None):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role="model", parts=list(partes)), finish_reason=fin)])


def test_chat_gemini_llama_herramienta_y_guarda_firmas(monkeypatch):
    campo, analisis = _demo()
    estado.guardar_analisis(campo.get("id", "campo"), analisis)
    sec = analisis["secciones"][0]
    llamada = types.Part(function_call=types.FunctionCall(id="c1", name="consultar_analisis",
                                                          args={"seccion_id": sec["id"]}), thought_signature=b"firma")
    cliente = _Cliente([
        [_trozo(llamada, fin="STOP")],
        [_trozo(types.Part(text="Sale mejor ")), _trozo(types.Part(text="por el suelo."), fin="STOP")],
    ])
    monkeypatch.setattr(chat, "_cliente", lambda: cliente)
    evs = list(chat.conversar(campo, [], "¿Por qué recomendás esto?"))
    assert "".join(e["delta"] for e in evs if e["tipo"] == "texto") == "Sale mejor por el suelo."
    assert [e["estado"] for e in evs if e["tipo"] == "herramienta"] == ["inicio", "fin"]
    nuevos = next(e["nuevos"] for e in evs if e["tipo"] == "mensajes")
    assert [m["role"] for m in nuevos] == ["user", "model", "user", "model"]
    # la firma vuelve tal cual en el segundo pedido, y la respuesta de la herramienta lleva el mismo id
    segundo = cliente.models.pedidos[1]
    assert segundo[1].parts[0].thought_signature == b"firma"
    assert segundo[2].parts[0].function_response.id == "c1"
    # el texto en trozos se guarda en una sola parte, y el historial guardado se puede volver a leer
    assert nuevos[3]["parts"] == [{"text": "Sale mejor por el suelo."}]
    assert chat.historial_valido(nuevos) == nuevos
    [types.Content.model_validate(m) for m in nuevos]


def test_historial_con_formato_de_claude_se_descarta():
    viejo = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": [{"type": "text", "text": "hola"}]}]
    assert chat.historial_valido(viejo) == []
