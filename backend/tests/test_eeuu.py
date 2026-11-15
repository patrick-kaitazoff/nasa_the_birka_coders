"""Campos de EE. UU.: país, suelo de SSURGO y calendario del hemisferio norte. Sin internet."""

from fieldshift.fuentes import region, ssurgo


def test_pais_por_coordenadas():
    assert region.pais(-33.1, -56.15) == "UY"  # Durazno
    assert region.pais(41.18, -94.45) == "US"  # Iowa
    assert region.pais(36.7, -119.8) == "US"  # Fresno, California
    assert region.pais(-31.4, -64.2) == ""  # Córdoba, Argentina
    assert region.pais(48.9, 2.35) == ""  # París
    assert region.hemisferio(-33.1) == "sur"
    assert region.hemisferio(41.2) == "norte"


def _fila(cokey, comp, pct, arriba, abajo, kw, awc, om=3.5, ph=6.2):
    return {"mukey": "1", "muname": "Clarion loam, 2 to 6 percent slopes", "cokey": cokey, "compname": comp,
            "comppct_r": str(pct), "slope_r": "4", "tfact": "5", "hydgrp": "B", "drainagecl": "Well drained",
            "taxorder": "Mollisols", "hzdept_r": str(arriba), "hzdepb_r": str(abajo), "kwfact": kw, "om_r": str(om),
            "awc_r": str(awc), "claytotal_r": "21", "sandtotal_r": "45", "silttotal_r": "34", "ph1to1h2o_r": str(ph)}


def test_ssurgo_pasa_k_y_t_a_las_unidades_del_mgap():
    filas = [_fila("a", "Clarion", 85, 0, 23, ".24", 0.21), _fila("a", "Clarion", 85, 23, 35, ".28", 0.18),
             _fila("a", "Clarion", 85, 35, 84, ".32", 0.18), _fila("b", "Nicollet", 10, 0, 40, ".20", 0.22)]
    s = ssurgo.interpretar_filas(filas)
    assert s["ok"] and s["suelo_dominante"] == "Clarion"
    assert s["factor_k"] == round(0.24 * 1.317, 3)  # el K del primer horizonte del componente dominante
    assert s["tolerancia_t"] == 11.2  # 5 t/acre → t/ha
    assert s["pendiente_pct"] == 4.0
    # agua útil hasta 80 cm: 23×0,21 + 12×0,18 + 45×0,18 = 15,09 cm = 151 mm
    assert s["agua_util_mm"] == 151
    assert [c["nombre"] for c in s["componentes"]] == ["Clarion", "Nicollet"]


def test_ssurgo_salta_horizontes_sin_k():
    filas = [_fila("a", "Muck", 90, 0, 10, None, 0.3), _fila("a", "Muck", 90, 10, 90, ".37", 0.2)]
    assert ssurgo.interpretar_filas(filas)["factor_k"] == round(0.37 * 1.317, 3)


def test_ssurgo_sin_suelo():
    assert ssurgo.interpretar_filas([])["ok"] is False


def test_calendario_del_norte():
    import datetime as dt

    from fieldshift.analisis import rotaciones as rot_mod
    from fieldshift.analisis.cultivos import CULTIVOS, HEMISFERIO, inicio_anio_agricola
    from fieldshift.analisis.plan import etiquetas_temporadas

    assert CULTIVOS["maiz"].siembra == (10, 1) and inicio_anio_agricola() == 3  # Uruguay, por defecto
    token = HEMISFERIO.set("norte")
    try:
        assert CULTIVOS["maiz"].siembra == (4, 30)
        assert CULTIVOS["trigo"].nombre == "Trigo de invierno" and CULTIVOS["trigo"].ciclo == 270
        assert dict(CULTIVOS.items())["soja"].siembra == (5, 15)
        assert CULTIVOS["pradera"].siembra == (10, 15)  # las perennes corren seis meses
        assert inicio_anio_agricola() == 9
        # el trigo se siembra 30 días después del 1 de septiembre; la cobertura termina antes del maíz
        assert rot_mod._offset(CULTIVOS["trigo"]) == 30
        fin_cobertura = rot_mod._offset(CULTIVOS["cobertura"]) + CULTIVOS["cobertura"].ciclo
        assert fin_cobertura < rot_mod._offset(CULTIVOS["maiz"])
        # maíz → soja con cobertura: casi sin meses descubiertos, igual que en el sur
        ev_c = rot_mod.cobertura_diaria(rot_mod.ROTACIONES["maiz_soja_cobertura"])
        assert ev_c[-730:].min() > 0.3
    finally:
        HEMISFERIO.reset(token)
    assert CULTIVOS["maiz"].siembra == (10, 1)

    noviembre = etiquetas_temporadas(2, dt.date(2026, 11, 14), "norte")
    assert [t["etiqueta"] for t in noviembre] == ["Verano 2027", "Invierno 2027/28", "Verano 2028", "Invierno 2028/29"]
    marzo = etiquetas_temporadas(1, dt.date(2027, 3, 1), "norte")
    assert [t["etiqueta"] for t in marzo] == ["Verano 2027", "Invierno 2027/28"]
    agosto = etiquetas_temporadas(1, dt.date(2027, 8, 1), "norte")
    assert [t["etiqueta"] for t in agosto] == ["Invierno 2027/28", "Verano 2028"]
    # el sur no cambia
    assert etiquetas_temporadas(1, dt.date(2026, 11, 15))[0]["etiqueta"] == "Verano 2026/27"


def test_temporadas_de_modis_en_el_norte():
    from fieldshift.fuentes import modis

    # maíz en verano (jun-sep alto) y suelo pelado el resto del año
    puntos = []
    for y in (2022, 2023):
        for m in range(1, 13):
            puntos.append({"fecha": f"{y}-{m:02d}-15", "ndvi": 0.8 if 6 <= m <= 9 else 0.2})
    t = modis.interpretar(puntos, "norte")["temporadas"]
    nombres = [x["temporada"] for x in t]
    assert "verano 2022" in nombres and "invierno 2022/23" in nombres
    assert next(x for x in t if x["temporada"] == "verano 2022")["ndvi_max"] == 0.8
    assert next(x for x in t if x["temporada"] == "invierno 2022/23")["ndvi_max"] == 0.2


def test_cdl_pasa_las_clases_a_cultivos_de_la_app():
    from fieldshift.analisis import rotaciones as rot_mod
    from fieldshift.fuentes import cdl

    histos = {"2022": {"1": 900, "5": 50}, "2023": {"5": 800, "1": 30}, "2024": {"1.0": 850},
              "2025": {"5": 700, "176": 100}, "2021": {}}
    filas = cdl.interpretar(histos)
    assert [f["anio"] for f in filas] == [2022, 2023, 2024, 2025]
    assert filas[0]["nombre_cdl"] == "Corn" and filas[0]["verano"] == "maiz" and filas[0]["pct"] == 95
    hist = [{"anio": f["anio"], "invierno": f["invierno"], "verano": f["verano"]} for f in filas]
    rot = rot_mod.rotacion_desde_historial(hist)
    assert rot.anios == (("barbecho", "maiz"), ("barbecho", "soja"))
    assert cdl.anio_a_cultivos(26)["invierno"] == "trigo" and cdl.anio_a_cultivos(26)["verano"] == "soja2"
    assert cdl.anio_a_cultivos(2)["verano"] is None  # algodón: no está en el catálogo


def test_estados_y_condados_de_eeuu():
    from fastapi.testclient import TestClient

    from fieldshift.api import app

    c = TestClient(app)
    estados = c.get("/api/estados-us").json()["features"]
    assert len(estados) == 49  # los 48 contiguos y DC
    iowa = next(f for f in estados if f["properties"]["sigla"] == "IA")
    assert iowa["properties"]["fips"] == "19"
    condados = c.get("/api/condados-us/19").json()["features"]
    assert len(condados) == 99
    assert any(f["properties"]["nombre"] == "Madison County" for f in condados)
    assert c.get("/api/condados-us/02").status_code == 404  # Alaska no está
    assert c.get("/api/condados-us/1x").status_code == 404
    assert c.post("/api/lote-cdl", json={"lat": -33.1, "lon": -56.1}).status_code == 400  # Uruguay: no hay CDL


def test_plantillas_del_cdl_cambian_la_geometria():
    import json

    from fieldshift.fuentes import cdl

    poli = {"type": "Polygon", "coordinates": [[[-94.2, 41.3], [-94.1, 41.3], [-94.1, 41.4], [-94.2, 41.3]]]}
    expr = cdl._con_geometria("cdl_por_anio", poli)
    s = json.dumps(expr)
    assert s.count("GeometryConstructors.") == 1 and "-94.2" in s and "-90.1" not in s
    multi = {"type": "MultiPolygon", "coordinates": [poli["coordinates"]]}
    assert "GeometryConstructors.MultiPolygon" in json.dumps(cdl._con_geometria("cdl_por_anio", multi))
    s = json.dumps(cdl._con_geometria("cdl_lote", {"type": "Point", "coordinates": [-94.21, 41.38]}))
    assert "[-94.21, 41.38]" in s and "-90.15" not in s


def test_ssurgo_pendiente_del_lote_pesa_por_superficie():
    # Un lote de Iowa con 80 % llano y 20 % de loma no puede salir con la pendiente de la loma
    unidades = [{"mukey": "1", "fraccion": 0.8}, {"mukey": "2", "fraccion": 0.2}]
    assert ssurgo.pendiente_media(unidades, {"1": 1.0, "2": 8.0}) == 2.4
    # una unidad sin pendiente cargada no cuenta
    assert ssurgo.pendiente_media(unidades, {"1": 1.0}) == 1.0
    assert ssurgo.pendiente_media(unidades, {}) is None
