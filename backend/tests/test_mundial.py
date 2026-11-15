"""Campos fuera de Uruguay: suelo de SoilGrids, factor R con la lluvia y rotaciones sin soja."""

from fieldshift.analisis import plan, rotaciones
from fieldshift.fuentes import mgap, soilgrids


def test_factor_k_epic_en_unidades_del_mgap():
    # franco limoso con 1,5 % de carbono: K de EE. UU. ~0,15 → ×1,317 en las unidades del MGAP
    k = soilgrids.factor_k_epic(30, 50, 20, 1.5)
    assert 0.15 <= k <= 0.30
    # más arena, menos erodable
    assert soilgrids.factor_k_epic(80, 10, 10, 1.0) < k


def test_factor_r_lejos_de_las_estaciones(monkeypatch):
    monkeypatch.setattr(mgap, "estaciones_r", lambda: [{"nombre": "DURAZNO", "lat": -33.38, "lon": -56.52, "r": 491}])
    assert mgap.factor_r(-33.3, -56.5)["r"] == 491
    assert mgap.factor_r(50.1, 7.1) is None  # Alemania: el R de Durazno no sirve


def test_dentro_de_uruguay():
    assert plan.dentro_de_uruguay(-31.13, -55.92)  # Lunarejo
    assert not plan.dentro_de_uruguay(-39.31, -71.95)  # Pucón
    assert not plan.dentro_de_uruguay(50.10, 7.12)  # Bremm


def test_rotaciones_sin_soja_solo_fuera_de_uruguay():
    for rid in rotaciones.SOLO_FUERA_DE_URUGUAY:
        r = rotaciones.ROTACIONES[rid]
        assert not {"soja", "soja2"} & set(r.cultivos)
