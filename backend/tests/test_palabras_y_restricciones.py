"""Respuestas con sus palabras en las tarjetas y cultivos que el productor no quiere."""

from fieldshift.agente import estado, guiado, restricciones


def test_detecta_cultivos_que_no_quiere():
    assert restricciones.detectar("No quiero soja de ninguna manera")["excluir"] == ["soja", "soja2"]
    assert restricciones.detectar("sin soja ni maíz")["excluir"] == ["soja", "soja2", "maiz", "maiz2"]
    assert restricciones.detectar("no quiero hacer más soja de segunda")["excluir"] == ["soja2"]
    assert restricciones.detectar("nada de colza") == {"excluir": ["colza"], "incluir": []}
    assert restricciones.detectar("Ahora sí quiero soja") == {"excluir": [], "incluir": ["soja", "soja2"]}


def test_no_confunde_preguntas_ni_elogios():
    for t in ("¿por qué sale soja?", "la soja me anduvo bien", "quiero más ingreso este año", "¿Por qué no otra rotación?"):
        assert restricciones.detectar(t) == {"excluir": [], "incluir": []}, t


def test_aplicar_suma_y_saca():
    c = {"restricciones": {"cultivos_excluidos": ["girasol"]}}
    assert restricciones.aplicar(c, {"excluir": ["soja"], "incluir": []}) == ["girasol", "soja"]
    assert restricciones.aplicar(c, {"excluir": [], "incluir": ["girasol"]}) == []
    assert restricciones.aplicar(c, {"excluir": ["girasol"], "incluir": []}) is None


def _campo():
    return {"id": "t-palabras", "contorno": {"type": "Polygon", "coordinates": []},
            "secciones": [{"id": "s1", "nombre": "El Bajo"}]}


def test_guiado_toma_el_sistema_dicho_con_palabras(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    evs = list(guiado.conversar(_campo(), "Tengo unas 80 vacas y siembro soja y trigo; el campo es arrendado", "datos_sistema"))
    patch = next(e for e in evs if e["tipo"] == "campo_patch")["cambios"]
    assert patch["sistema"]["tipo"] == "mixto" and patch["sistema"]["tenencia"] == "arrendado"
    assert patch["sistema"]["cabezas"] == 80
    assert patch["notas_productor"][-1]["paso"] == "datos_sistema"
    # la entrevista sigue con el paso siguiente, no vuelve a pedir el sistema
    tarjetas = [e["tarjeta"] for e in evs if e["tipo"] == "tarjeta"]
    assert tarjetas == ["historial_seccion"]


def test_guiado_da_por_respondido_lo_que_no_entiende(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    c = {**_campo(), "sistema": {"tipo": "agricola"}}
    evs = list(guiado.conversar(c, "Hace años que hago trigo y después soja, más o menos siempre igual", "historial_seccion"))
    patch = next(e for e in evs if e["tipo"] == "campo_patch")["cambios"]
    assert "historial_seccion" in patch["pasos_omitidos"]
    assert [e["tarjeta"] for e in evs if e["tipo"] == "tarjeta"] == ["problemas"]


def test_guiado_problemas_en_la_seccion_nombrada(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    c = {**_campo(), "secciones": [{"id": "s1", "nombre": "El Bajo"}, {"id": "s2", "nombre": "La Loma"}]}
    evs = list(guiado.conversar(c, "En El Bajo se anega cuando llueve mucho", "problemas"))
    patch = next(e for e in evs if e["tipo"] == "campo_patch")["cambios"]
    assert patch["secciones"] == [{"id": "s1", "problemas": ["anegamiento"]}]


def _resultado(sugerida):
    return {"secciones": [{"id": "s1", "nombre": "El Bajo", "actual": None, "alternativas": [
                {"id": "soja_trigo", "nombre": "Trigo / Soja de segunda"}, {"id": "maiz_trigo", "nombre": "Maíz / Trigo"}]}],
            "plan": {"secciones": [{"seccion_id": "s1", "rotacion_id": sugerida, "sugerida_id": sugerida, "cultivos": []}]}}


def test_guiado_recalcula_sin_el_cultivo(monkeypatch):
    c = {**_campo(), "pasos_omitidos": [p for p, _, _ in guiado.PASOS], "rotacion_elegida": {"s1": "soja_trigo"}}
    estado.guardar_analisis(c["id"], _resultado("soja_trigo"))
    vistos = {}

    def analizar(campo):
        vistos["campo"] = campo
        yield {"tipo": "resultado", "resultado": _resultado("maiz_trigo")}

    monkeypatch.setattr(guiado.plan_mod, "analizar_campo_pasos", analizar)
    monkeypatch.setattr(guiado, "_cultivos_rot", lambda rid, plan, sid: {"soja2", "trigo"} if rid == "soja_trigo" else {"maiz", "trigo"})
    evs = list(guiado.conversar(c, "No quiero soja de ninguna manera"))
    assert vistos["campo"]["restricciones"]["cultivos_excluidos"] == ["soja", "soja2"]
    assert "s1" not in vistos["campo"]["rotacion_elegida"]  # la elegida con soja se suelta antes de calcular
    patches = [e["cambios"] for e in evs if e["tipo"] == "campo_patch"]
    assert patches[0] == {"restricciones": {"cultivos_excluidos": ["soja", "soja2"]}}
    assert patches[1] == {"rotacion_elegida": {"s1": "maiz_trigo"}}
    texto = "".join(e["delta"] for e in evs if e["tipo"] == "texto")
    assert "Saqué soja de las opciones. Volví a calcular" in texto
    assert "«volvé a poner soja»" in texto
    assert "antes Trigo / Soja de segunda; ahora Maíz / Trigo" in texto
    assert any(e["tipo"] == "analisis" for e in evs)


def test_guiado_antes_del_analisis_solo_lo_anota(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    evs = list(guiado.conversar({**_campo(), "id": "t-sin-analisis"}, "sin girasol"))
    assert evs[0] == {"tipo": "campo_patch", "cambios": {"restricciones": {"cultivos_excluidos": ["girasol"]}}}
    assert "Lo tengo en cuenta cuando analice" in evs[1]["delta"]
    assert [e["tarjeta"] for e in evs if e["tipo"] == "tarjeta"] == ["datos_sistema"]


def test_pista_para_la_ia():
    p = restricciones.pista({}, "no quiero soja", "prioridades")
    assert "prioridades" in p and '["soja", "soja2"]' in p
    assert restricciones.pista({}, "¿por qué sale soja?", None) is None


def test_tambien_en_ingles():
    assert restricciones.detectar("I don't want soybean at all")["excluir"] == ["soja", "soja2"]
    assert restricciones.detectar("put back the wheat")["incluir"] == ["trigo"]
    assert restricciones.detectar("why not soy?") == {"excluir": [], "incluir": []}


def test_con_resultados_recalcula_aunque_falte_un_paso(monkeypatch):
    c = {**_campo(), "id": "t-sin-memoria", "sistema": {"tipo": "agricola"}}  # faltan pasos y el servidor no guarda análisis
    monkeypatch.setattr(guiado.plan_mod, "analizar_campo_pasos", lambda campo: iter([{"tipo": "resultado", "resultado": _resultado("maiz_trigo")}]))
    evs = list(guiado.conversar(c, "no quiero soja", con_analisis=True))
    assert any(e["tipo"] == "analisis" for e in evs)
    assert not any(e["tipo"] == "tarjeta" for e in evs)


def test_nombres_como_los_dice_la_gente():
    assert restricciones.nombres(["soja", "soja2"]) == "soja"
    assert restricciones.nombres(["soja2"]) == "soja de segunda"
    assert restricciones.nombres(["soja", "soja2", "girasol"]) == "soja y girasol"


def test_guiado_saca_el_analisis_de_suelo_del_texto(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    c = {**_campo(), "id": "t-suelo", "sistema": {"tipo": "agricola"}, "pasos_omitidos": ["historial_seccion", "problemas"]}
    evs = list(guiado.conversar(c, "pH 6,1, materia orgánica 3,4 % y fósforo 12 ppm; arcilla 28", "subir_analisis_suelo"))
    a = next(e for e in evs if e["tipo"] == "campo_patch")["cambios"]["analisis_suelo_general"]
    assert a["ph"] == 6.1 and a["materia_organica"] == 3.4 and a["fosforo_bray"] == 12 and a["arcilla"] == 28
    assert [e["tarjeta"] for e in evs if e["tipo"] == "tarjeta"] == ["prioridades"]


def test_guiado_tarjeta_al_final_no_dice_que_no_entiende(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    c = {**_campo(), "id": "t-final", "pasos_omitidos": [p for p, _, _ in guiado.PASOS if p != "margenes"]}
    texto = "".join(e.get("delta", "") for e in guiado.conversar(c, "soja 280, maíz 220", "margenes", con_analisis=True))
    assert "Anoté los márgenes" in texto and "no puedo contestar" not in texto and "analizar de nuevo" in texto


def test_lo_de_hoy_con_un_cultivo_excluido_no_se_recomienda():
    from fieldshift.analisis.plan import elegir_recomendada
    hoy = {"id": "actual", "erosion": {"cumple": True}, "puntaje_total": 90, "tiene_excluidos": True}
    otra = {"id": "maiz_trigo", "erosion": {"cumple": True}, "puntaje_total": 70}
    assert elegir_recomendada(hoy, [otra])["id"] == "maiz_trigo"
    assert elegir_recomendada({**hoy, "tiene_excluidos": False}, [otra])["id"] == "actual"
