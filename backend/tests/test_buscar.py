"""Buscador del paso 1: «ruta N km K» con los mojones guardados del MTOP (sin internet)."""

from fieldshift.fuentes import buscar as b


def test_ruta_y_km_cae_en_su_departamento():
    r = b.buscar("ruta 5 km 200")
    assert len(r) == 1
    assert r[0]["departamento"] == "Durazno"
    assert r[0]["tipo"] == "ruta"
    assert -33.4 < r[0]["lat"] < -33.1 and -56.6 < r[0]["lon"] < -56.3


def test_formas_de_escribir_la_ruta():
    for q in ("ruta 5 km 200", "R5 km 200", "ruta 5, kilómetro 200", "Ruta 5 200", "ruta nº 5 km 200,0"):
        r = b.buscar(q)
        assert r and r[0]["nombre"] == "Ruta 5, km 200", q


def test_doble_via_cerca_de_montevideo_da_un_solo_punto():
    # la ruta 8 en sus primeros km está guardada por mano (8-PAN, 8-MVD): un solo resultado
    r = b.buscar("ruta 8 km 26")
    assert len(r) == 1
    assert r[0]["departamento"] == "Canelones"


def test_interbalnearia():
    r = b.buscar("interbalnearia km 60")
    assert r and r[0]["departamento"] == "Canelones"


def test_km_que_no_existe():
    assert b.por_ruta("5", 900) == []
