"""Pruebas del motor que no usan internet. Correr desde app/backend: .venv/Scripts/python -m pytest -q"""

from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fieldshift import archivos  # noqa: E402
from fieldshift.agente import estado, guiado  # noqa: E402
from fieldshift.analisis import clima, plan, rotaciones, suelo  # noqa: E402
from fieldshift.analisis.cultivos import CULTIVOS  # noqa: E402


def power_sintetico(anios=(2000, 2001, 2002, 2003), lluvia_dia=3.0):
    """Una serie de clima inventada pero coherente (verano cálido, invierno frío)."""
    fechas, cols = [], {k: [] for k in ("T2M_MAX", "T2M_MIN", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN", "RH2M", "WS2M", "GWETROOT")}
    d = dt.date(anios[0], 1, 1)
    while d.year <= anios[-1]:
        doy = d.timetuple().tm_yday
        estacion = math.cos(2 * math.pi * (doy - 15) / 365)  # 1 en enero (verano austral)
        fechas.append(d.strftime("%Y%m%d"))
        cols["T2M_MAX"].append(23 + 8 * estacion)
        cols["T2M_MIN"].append(11 + 7 * estacion)
        cols["PRECTOTCORR"].append(lluvia_dia * (2.5 if doy % 7 == 0 else 0.5))
        cols["ALLSKY_SFC_SW_DWN"].append(16 + 9 * estacion)
        cols["RH2M"].append(72.0)
        cols["WS2M"].append(2.5)
        cols["GWETROOT"].append(0.7)
        d += dt.timedelta(days=1)
    return {"lat": -33.4, "lon": -56.5, "elevacion": 110, "fechas": fechas, **cols}


def test_et0_rango_razonable():
    # verano de Uruguay: 4-7 mm/día; invierno: 0,5-2 mm/día
    et0 = clima.et0_penman_monteith(np.array([31.0, 15.0]), np.array([17.0, 5.0]), np.array([25.0, 9.0]),
                                    np.array([65.0, 80.0]), np.array([2.5, 2.5]), np.array([15, 180]), -33.4, 110)
    assert 4 < et0[0] < 7.5
    assert 0.3 < et0[1] < 2.2


def test_riesgos_cultivo_probabilidades_validas():
    serie = clima.preparar(power_sintetico())
    r = clima.riesgos_cultivo(serie, CULTIVOS["soja"], 120)
    assert r["anios_evaluados"] >= 2
    assert 0 <= r["prob_seca"] <= 1
    assert r["ventana_agua"].startswith("floración")
    # con mucha más lluvia la seca no puede aumentar
    mojado = clima.preparar(power_sintetico(lluvia_dia=12))
    assert clima.riesgos_cultivo(mojado, CULTIVOS["soja"], 120)["prob_seca"] <= r["prob_seca"]

def test_es_cambio_claro():
    from fieldshift.analisis.clima import es_cambio_claro
    # Caso igual: sin cambio
    assert not es_cambio_claro(0.444, 0.444)
    # Caso con diferencia muy chica (ej. 8/18 vs 8/17 en soja: 0.444 vs 0.471 -> dif 0.027)
    assert not es_cambio_claro(0.444, 0.471)
    # Caso chico: diferencia menor a 0.2 (ej. 0.1 o 0.13)
    assert not es_cambio_claro(0.3, 0.4)
    assert not es_cambio_claro(0.222, 0.353)
    # Caso claro: diferencia >= 0.2
    assert es_cambio_claro(0.333, 0.588)  # maiz seca (+0.255)
    assert es_cambio_claro(0.278, 0.588)  # soja calor (+0.310)
    assert es_cambio_claro(0.6, 0.3)      # descenso claro (-0.3)
    # Casos con None
    assert not es_cambio_claro(None, 0.5)
    assert not es_cambio_claro(0.5, None)


def test_tendencia_anios_reales_y_cambio_claro():
    serie = clima.preparar(power_sintetico(anios=list(range(2000, 2015))))
    t = clima.tendencia(serie, 120.0, ["soja"])
    soja_seca = t["cultivos"]["soja"]["prob_seca"]
    assert "k_antes" in soja_seca
    assert "n_antes" in soja_seca
    assert "k_ahora" in soja_seca
    assert "n_ahora" in soja_seca
    assert "cambio_claro" in soja_seca
    assert "antes" in soja_seca
    assert "ahora" in soja_seca
    assert isinstance(soja_seca["cambio_claro"], bool)



def test_erosividad_reparto_suma_uno():
    for lluvia in (3.0, 8.0):  # con 3 mm ningún día pasa de 12,7 mm: no puede dar NaN
        e = clima.erosividad(clima.preparar(power_sintetico(lluvia_dia=lluvia)))
        assert abs(sum(e["reparto_mensual"]) - 1) < 1e-3  # redondeado a 4 decimales
        assert e["r_anual"] > 0


def test_factor_ls_crece_con_pendiente():
    assert rotaciones.factor_ls(1) < rotaciones.factor_ls(4) < rotaciones.factor_ls(8)
    # referencia de Wischmeier: 9 % y 22,13 m da LS = 1
    assert abs(rotaciones.factor_ls(9, 22.13) - 1) < 0.05


def test_cobertura_pradera_mayor_que_soja_continua():
    soja = rotaciones.cobertura_diaria(rotaciones.ROTACIONES["soja_continua"]).mean()
    pradera = rotaciones.cobertura_diaria(rotaciones.ROTACIONES["pradera_permanente"]).mean()
    assert pradera > soja
    c = rotaciones.factor_c_diario(np.array([0.0, 1.0]))
    assert c[0] > c[1] > 0


def ctx_basico():
    reparto = [1 / 12] * 12
    riesgos = {cod: {"prob_seca": 0.3, "deficit_medio": 0.3, "prob_helada_agro": 0.1, "prob_calor": 0.2,
                     "ventana_agua": "floración: x", "ventana_helada": "floración: y", "ventana_calor": "floración: z"}
               for cod in CULTIVOS}
    return {"suelo": {"factor_k": 0.35, "tolerancia_t": 7, "pendiente_pct": 4, "grupo_coneat": "10.3"},
            "r_factor": 500, "reparto_erosivo": reparto, "riesgos": riesgos, "problemas": [], "margenes": {}}


def test_evaluar_y_explicar_tienen_las_cinco_filas():
    ctx = ctx_basico()
    actual = rotaciones.evaluar(rotaciones.ROTACIONES["soja_continua"], ctx)
    alt = rotaciones.evaluar(rotaciones.ROTACIONES["agricola_pastoril"], ctx)
    assert alt["erosion"]["a_t_ha"] < actual["erosion"]["a_t_ha"]
    ex = rotaciones.explicar(alt, ctx, actual)
    for k in ("por_que", "evidencia", "beneficios", "huecos", "riesgos"):
        assert isinstance(ex[k], list)
    assert ex["por_que"] and ex["evidencia"] and ex["huecos"]
    assert "," in ex["evidencia"][0]  # coma decimal


def test_anegamiento_penaliza_cultivos_de_invierno():
    ctx = ctx_basico()
    r = rotaciones.ROTACIONES["trigo_soja_maiz"]
    normal = rotaciones.ponderar(rotaciones.evaluar(r, ctx), {})
    ctx["problemas"] = ["anegamiento"]
    anegado = rotaciones.ponderar(rotaciones.evaluar(r, ctx), {})
    assert anegado < normal


def test_rotacion_desde_historial_recorta_ciclos():
    h = [{"anio": a, "invierno": "barbecho", "verano": "soja"} for a in (2022, 2023, 2024)]
    r = rotaciones.rotacion_desde_historial(h)
    assert r.anios == (("barbecho", "soja"),)
    h2 = [{"anio": 2022, "invierno": "trigo", "verano": "soja2"}, {"anio": 2023, "invierno": "cobertura", "verano": "maiz"},
          {"anio": 2024, "invierno": "trigo", "verano": "soja2"}, {"anio": 2025, "invierno": "cobertura", "verano": "maiz"}]
    assert len(rotaciones.rotacion_desde_historial(h2).anios) == 2


def test_secuencia_temporadas():
    temps = plan.etiquetas_temporadas(2, dt.date(2026, 11, 15))
    assert [t["etiqueta"] for t in temps] == ["Verano 2026/27", "Invierno 2027", "Verano 2027/28", "Invierno 2028"]
    r = rotaciones.ROTACIONES["trigo_soja_maiz"]
    assert plan.secuencia(r, 0, temps) == ["soja2", "cobertura", "maiz", "trigo"]
    temps_inv = plan.etiquetas_temporadas(1, dt.date(2026, 3, 1))
    assert temps_inv[0]["etiqueta"] == "Invierno 2026"


def test_area_de_un_cuadrado_de_un_km():
    lat = -33.0
    dlat = 1 / 110.54
    dlon = 1 / (111.32 * math.cos(math.radians(lat)))
    g = {"type": "Polygon", "coordinates": [[[-56, lat], [-56 + dlon, lat], [-56 + dlon, lat + dlat], [-56, lat + dlat], [-56, lat]]]}
    assert abs(plan.area_ha(g) - 100) < 1.5


def test_textura_y_agua_util():
    assert suelo.clase_textural(20, 30, 50) == "arcilloso"
    assert suelo.clase_textural(20, 40, 40) == "arcillo limoso"  # borde del triángulo USDA
    assert suelo.clase_textural(80, 10, 10) == "arenoso franco"
    mm, origen = suelo.agua_util({"arena": 25, "limo": 45, "arcilla": 30})
    assert 100 < mm < 160 and "textura" in origen
    assert suelo.agua_util(None)[0] == suelo.AGUA_UTIL_POR_DEFECTO


def test_lectura_de_analisis_de_suelo_csv_y_texto():
    csv = "Muestra;pH (H2O);M.O. (%);P Bray I (ppm);K (meq/100g)\nPotrero 1;5,8;3,1;9;0,42\n".encode()
    r = archivos.procesar("a.csv", csv)
    assert r["tipo"] == "analisis_suelo"
    assert r["filas"][0]["ph"] == 5.8 and r["filas"][0]["nombre"] == "Potrero 1"
    t = archivos.suelo_desde_texto("pH (H2O): 6,1\nCarbono orgánico (%): 2,0\nP Bray I (ppm) 12")
    assert t["ph"] == 6.1 and abs(t["materia_organica"] - 3.45) < 0.01


def test_estacion_horaria_se_pasa_a_diaria():
    filas = ["Fecha;Hora;Temp;Lluvia"]
    for dia in (1, 2):
        for h in range(24):
            filas.append(f"0{dia}/03/2026;{h:02d}:00;{15 + h * 0.5};{0.2 if h == 5 else 0}".replace(".", ","))
    df = archivos.leer_tabla("est.csv", "\n".join(filas).encode())
    assert archivos.clasificar(df) == "estacion"
    est = archivos.estacion_desde_tabla(df)
    assert len(est) == 2
    assert abs(est["tmax"].iloc[0] - 26.5) < 1e-6 and abs(est["lluvia"].iloc[0] - 0.2) < 1e-6


def test_historial_con_nombres_comunes():
    csv = "Año,Potrero,Invierno,Verano\n2024,P1,avena,soja de segunda\n".encode()
    r = archivos.procesar("h.csv", csv)
    assert r["tipo"] == "historial"
    assert r["filas"][0]["invierno"] == "cobertura" and r["filas"][0]["verano"] == "soja2"


def test_fusionar_secciones_por_id():
    base = {"nombre": "A", "secciones": [{"id": "s1", "nombre": "P1"}, {"id": "s2", "nombre": "P2"}]}
    nuevo = estado.fusionar(base, {"sistema": {"tipo": "mixto"}, "secciones": [{"id": "s2", "problemas": ["helada"]}]})
    assert nuevo["secciones"][1] == {"id": "s2", "nombre": "P2", "problemas": ["helada"]}
    assert nuevo["sistema"]["tipo"] == "mixto" and base.get("sistema") is None


def test_guiado_pide_lo_que_falta_en_orden():
    assert guiado.siguiente_paso({})[0] == "dibujar_campo"
    c = {"contorno": {"type": "Polygon", "coordinates": []}, "secciones": [{"id": "s1"}]}
    assert guiado.siguiente_paso(c)[0] == "datos_sistema"
    c["sistema"] = {"tipo": "agricola"}
    c["pasos_omitidos"] = ["historial_seccion"]
    assert guiado.siguiente_paso(c)[0] == "problemas"


def test_guiado_conversar_transicion_sin_avance_falso(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    c = {"contorno": {"type": "Polygon", "coordinates": []}, "secciones": [{"id": "s1"}]}
    eventos = list(guiado.conversar(c, "respuesta del productor"))
    progresos = [e for e in eventos if e["tipo"] == "progreso"]
    assert len(progresos) == 1
    assert progresos[0]["avance"] is None
    assert "Analizando la información del campo" in progresos[0]["mensaje"]


def test_comparacion_estacion_detecta_campo_mas_helador():
    pw = power_sintetico((2025, 2026))
    idx = pd.to_datetime([f"{f[:4]}-{f[4:6]}-{f[6:]}" for f in pw["fechas"]])
    est = pd.DataFrame({"lluvia": pw["PRECTOTCORR"], "tmax": pw["T2M_MAX"], "tmin": np.array(pw["T2M_MIN"]) - 6}, index=idx)
    r = archivos.comparar_con_power(est, pw)
    assert r["tmin"]["sesgo_c"] < -5
    assert r.get("campo_mas_helador")


def _sec_falsa(sid, area, actual_pts, alt_pts):
    """Sección mínima para el reparto del plan: actual con pradera (sin cultivos de cosecha) y una alternativa agrícola."""
    actual = {"id": "actual", "tipo": "actual", "anios": [("pradera", "pradera"), ("pradera", "pradera"), ("pradera", "pradera")],
              "puntaje_total": actual_pts, "erosion": {"ratio": 0.5}}
    alt = {"id": "soja_cobertura", "tipo": "agrícola", "anios": [("cobertura", "soja")], "puntaje_total": alt_pts,
           "erosion": {"ratio": 0.2}}
    return {"id": sid, "area_ha": area, "actual": actual, "alternativas": [alt]}


def test_equilibrio_agricola_ganadero_solo_en_campos_mixtos():
    secs = [_sec_falsa("s1", 10, 70, 48), _sec_falsa("s2", 20, 71, 47)]
    agricola = {"sistema": {"tipo": "agricola"}, "objetivos": {"pct_agricola": 100}}
    assert plan._equilibrar(secs, agricola) == {}  # la cambiaba la actual por soja con cobertura
    ganadero = {"sistema": {"tipo": "ganadero"}, "objetivos": {"pct_agricola": 0}}
    assert plan._equilibrar(secs, ganadero) == {}
    mixto = {"sistema": {"tipo": "mixto"}, "objetivos": {"pct_agricola": 50}}
    assert set(plan._equilibrar(secs, mixto)) == {"s1", "s2"}


def test_compactacion_malezas_y_erosion_pesan_sobre_las_rotaciones_que_no_las_atacan():
    ctx = ctx_basico()
    soja = rotaciones.ROTACIONES["soja_continua"]
    pastoril = rotaciones.ROTACIONES["agricola_pastoril"]
    base_soja = rotaciones.ponderar(rotaciones.evaluar(soja, ctx), {})
    base_past = rotaciones.ponderar(rotaciones.evaluar(pastoril, ctx), {})
    for problema in ("compactacion", "malezas", "erosion"):
        ctx["problemas"] = [problema]
        ev = rotaciones.evaluar(soja, ctx)
        assert rotaciones.ponderar(ev, {}) < base_soja, problema
        assert any("productor" in a for a in ev["alertas"]), problema
    ctx["problemas"] = ["compactacion"]
    assert rotaciones.ponderar(rotaciones.evaluar(pastoril, ctx), {}) == base_past  # la pastura sí la ataca


def test_contrato_corto_castiga_pasturas_al_arrendatario():
    rot = rotaciones.ROTACIONES["agricola_pastoril"]
    base = {"puntaje_total": 60.0, "alertas": []}
    propio = dict(base, alertas=[])
    plan.ajuste_tenencia(propio, rot, {"tenencia": "propio"}, False)
    assert propio["puntaje_total"] == 60.0
    corto = dict(base, alertas=[])
    plan.ajuste_tenencia(corto, rot, {"tenencia": "arrendado", "anios_contrato": 3}, False)
    largo = dict(base, alertas=[])
    plan.ajuste_tenencia(largo, rot, {"tenencia": "arrendado", "anios_contrato": 10}, False)
    assert corto["puntaje_total"] < largo["puntaje_total"] < 60.0
    assert "3 años de contrato" in corto["alertas"][0]
    agricola = dict(base, alertas=[])
    plan.ajuste_tenencia(agricola, rotaciones.ROTACIONES["soja_continua"], {"tenencia": "arrendado", "anios_contrato": 3}, False)
    assert agricola["puntaje_total"] == 60.0 and not agricola["alertas"]


def test_renta_en_kilos_margen_despues_de_renta_y_rinde_de_equilibrio():
    ctx = ctx_basico()
    ctx["margenes"] = {"trigo": 60, "soja2": 180}
    ctx["detalle_margenes"] = {"trigo": {"rinde": 3600, "precio": 200, "costo": 660},
                               "soja2": {"rinde": 2400, "precio": 365, "costo": 696}}
    ctx["renta_kg"] = 800
    ev = rotaciones.evaluar(rotaciones.ROTACIONES["trigo_soja2"] if "trigo_soja2" in rotaciones.ROTACIONES
                            else rotaciones.rotacion_desde_historial([{"anio": 2024, "invierno": "trigo", "verano": "soja2"}]), ctx)
    ing = ev["ingreso"]
    assert ing["renta_usd_ha"] == 292  # 800 kg × 365 USD/t
    assert ing["usd_ha_anio_despues_de_renta"] == 240 - 292
    eq = {q["cultivo"]: q["kg_ha"] for q in ing["equilibrios"]}
    assert eq["soja2"] == round((696 + 146) / 365 * 1000)  # la mitad de la renta, comparte el año con el trigo
    ex = rotaciones.explicar(ev, ctx, None)
    assert any("Rinde de equilibrio" in t for t in ex["evidencia"])
    assert any("Después de pagar la renta" in t for t in ex["beneficios"])


def test_margen_faltante_se_estima_en_la_misma_escala():
    ctx = ctx_basico()
    ctx["margenes"] = {"trigo": 60, "soja2": 180, "soja": 330}
    ev = rotaciones.evaluar(rotaciones.ROTACIONES["girasol_trigo_soja"], ctx)
    assert ev["ingreso"]["usa_margenes"] and "girasol" in ev["ingreso"]["margenes_estimados"]
    ex = rotaciones.explicar(ev, ctx, None)
    assert any("Sin tu margen de girasol" in h for h in ex["huecos"])


def test_seguro_y_venta_a_futuro_cambian_como_se_lee_la_seca():
    e = {"riesgo": {"seca": 0.4}, "alertas": []}
    plan.ajuste_riesgo_comercial(e, {"seguro_seca": False, "vende_futuro": True})
    assert any("Sin seguro" in a for a in e["alertas"]) and any("futuro" in a for a in e["alertas"])
    e = {"riesgo": {"seca": 0.4}, "alertas": []}
    plan.ajuste_riesgo_comercial(e, {"seguro_seca": True})
    assert e["beneficios_extra"] and not e["alertas"]
    e = {"riesgo": {"seca": 0.1}, "alertas": []}
    plan.ajuste_riesgo_comercial(e, {"seguro_seca": False})
    assert not e["alertas"]


def test_lo_que_le_fallo_y_le_anduvo_al_productor_pesa():
    rot_forraje = rotaciones.ROTACIONES["agricola_pastoril"]
    rot_granos = rotaciones.ROTACIONES["soja_continua"]
    exp = {"que_funciono": "maiz y soja", "que_fallo": "forraje"}
    e1 = {"puntaje_total": 60.0, "alertas": []}
    plan.ajuste_experiencia(e1, rot_forraje, exp)
    assert e1["puntaje_total"] < 60.0 and "te falló" in e1["alertas"][0]
    e2 = {"puntaje_total": 60.0, "alertas": []}
    plan.ajuste_experiencia(e2, rot_granos, exp)
    assert e2["puntaje_total"] > 60.0 and e2["beneficios_extra"]
    assert archivos.cultivos_en_texto("Maíz de primera") == {"maiz"}


def test_topes_oficiales_de_rastrojo_a_la_siembra():
    assert rotaciones.tope_rastrojo("soja2", "colza", None) == 0.40
    assert rotaciones.tope_rastrojo("soja", "barbecho", "maiz") == 0.50
    assert rotaciones.tope_rastrojo("soja", "barbecho", "soja") == 0.40
    assert rotaciones.tope_rastrojo("soja2", "trigo", "soja") == 0.70
    assert rotaciones.tope_rastrojo("maiz", "cobertura", None) is None
    # soja después de barbecho de maíz: la cobertura a la siembra no pasa de 50 %
    rot = rotaciones.rotacion_desde_historial([{"anio": 2023, "invierno": "barbecho", "verano": "maiz"},
                                               {"anio": 2024, "invierno": "barbecho", "verano": "soja"}])
    cob = rotaciones.cobertura_diaria(rot, ciclos=1)
    siembra_soja = 365 + rotaciones._offset(CULTIVOS["soja"])
    assert cob[siembra_soja] <= 0.5 + 1e-9


def test_resumen_guiado_explica_tolerancia_y_el_reparto_mixto():
    import json as _json
    demo = Path(__file__).resolve().parents[2] / "frontend" / "public" / "ejemplos" / "campo_demo.fieldshift.json"
    d = _json.loads(demo.read_text(encoding="utf-8"))
    txt = guiado.resumen_texto(d["analisis"], d["campo"])
    assert txt.count("lo máximo que ese suelo puede perder") == 1
    assert "% agrícola" in txt


def test_aportes_de_cada_cultivo():
    from fieldshift.analisis.cultivos import APORTES, aportes, catalogo_publico

    assert "fija_n" in aportes(CULTIVOS["soja"]) and "fija_n" in aportes(CULTIVOS["alfalfa"])
    assert "cubre" in aportes(CULTIVOS["cobertura"])
    assert set(aportes(CULTIVOS["girasol"])) >= {"raiz_profunda", "tolera_seca"}
    assert aportes(CULTIVOS["barbecho"]) == []
    for c in catalogo_publico():
        assert all(a in APORTES for a in c["aportes"])


def test_escenario_de_clima():
    pw = power_sintetico(anios=(2000, 2001, 2002, 2003, 2004))
    igual = clima.escenario(pw, 120, 0, 0, ["soja", "trigo"])
    for f in igual["cultivos"]:
        assert f["hoy"] == f["escenario"]
    seco = clima.escenario(pw, 120, -40, 0, ["soja"])
    assert seco["lluvia_anual_mm"]["escenario"] < seco["lluvia_anual_mm"]["hoy"]
    assert seco["et0_anual_mm"]["escenario"] == seco["et0_anual_mm"]["hoy"]
    assert seco["cultivos"][0]["escenario"]["prob_seca"] >= seco["cultivos"][0]["hoy"]["prob_seca"]
    calido = clima.escenario(pw, 120, 0, 3, ["soja", "maiz"])
    assert calido["et0_anual_mm"]["escenario"] > calido["et0_anual_mm"]["hoy"]
    for f in calido["cultivos"]:
        assert (f["escenario"]["prob_calor"] or 0) >= (f["hoy"]["prob_calor"] or 0)
        assert (f["escenario"]["prob_helada_agro"] or 0) <= (f["hoy"]["prob_helada_agro"] or 0)
    # fuera de rango se recorta
    assert clima.escenario(pw, 120, -90, 9, ["soja"])["lluvia_pct"] == clima.ESCENARIO_LLUVIA[0]


def test_smap_lee_csv_de_appeears():
    from fieldshift.fuentes import smap

    texto = (
        "ID,Latitude,Longitude,Date,SPL4SMGP_008_Geophysical_Data_sm_rootzone,SPL4SMGP_008_Geophysical_Data_sm_rootzone_pctl\n"
        "campo,-33,-56,2020-01-01,0.30,40\n"
        "campo,-33,-56,2020-01-01,0.32,44\n"
        "campo,-33,-56,2020-01-02,-9999,-9999\n"
        "campo,-33,-56,2020-01-03,0.25,20\n"
    )
    serie = smap.leer_csv(texto)
    assert [f["fecha"] for f in serie] == ["2020-01-01", "2020-01-03"]
    assert serie[0]["sm"] == 0.31 and serie[0]["pctl"] == 42.0
    try:
        smap.leer_csv("ID,Date,otra\nx,2020-01-01,1\n")
        raise AssertionError("tenía que fallar sin la columna de SMAP")
    except ValueError:
        pass


def test_smap_sin_cuenta_no_rompe(monkeypatch, tmp_path):
    from fieldshift import cache
    from fieldshift.fuentes import smap

    monkeypatch.setattr(cache, "CARPETA", tmp_path)
    monkeypatch.delenv("EARTHDATA_USER", raising=False)
    monkeypatch.delenv("EARTHDATA_PASS", raising=False)
    assert smap.estado(-30.0, -55.0)["estado"] == "sin_cuenta"


def test_humedad_compara_anomalias():
    from fieldshift.analisis import humedad

    pw = power_sintetico(anios=tuple(range(2016, 2020)))
    rng = np.random.default_rng(0)
    pw["PRECTOTCORR"] = [float(rng.gamma(0.7, 16)) if rng.random() < 0.3 else 0.0 for _ in pw["fechas"]]
    serie = clima.preparar(pw)
    balde = humedad.balde_referencia(serie, 120)
    assert 0 <= balde.min() and balde.max() <= 1
    # un SMAP que sigue al balde (más ruido) tiene que coincidir; uno al azar, no
    fechas = [f.isoformat() for f in serie.fechas]
    sigue = [{"fecha": d, "sm": 0.15 + 0.2 * b + rng.normal(0, 0.01), "pctl": 25.0} for d, b in zip(fechas, balde)]
    azar = [{"fecha": d, "sm": float(rng.uniform(0.1, 0.4)), "pctl": 50.0} for d in fechas]
    bien = humedad.comparar(sigue, serie, 120)
    assert bien["ok"] and bien["correlacion"] > 0.8
    assert "más seca" in bien["ahora"]["texto"]
    assert humedad.comparar(azar, serie, 120)["correlacion"] < 0.5


def test_smap_flujo_appeears_simulado(monkeypatch, tmp_path):
    """Pedido → pendiente → terminado → serie, con las respuestas de AppEEARS simuladas."""
    import httpx

    from fieldshift import cache
    from fieldshift.fuentes import smap

    monkeypatch.setattr(cache, "CARPETA", tmp_path)
    monkeypatch.setenv("EARTHDATA_USER", "u")
    monkeypatch.setenv("EARTHDATA_PASS", "p")
    estado_tarea = {"status": "processing"}
    csv_ok = "ID,Date,SPL4SMGP_008_Geophysical_Data_sm_rootzone,SPL4SMGP_008_Geophysical_Data_sm_rootzone_pctl\nc,2020-01-01,0.3,40\n"
    pedidos = []

    def resp(url, data=None, text=None):
        return httpx.Response(200, json=data, text=text, request=httpx.Request("GET", url))

    def post(url, **kw):
        pedidos.append(url)
        if url.endswith("/login"):
            return resp(url, {"token": "t"})
        assert kw["json"]["params"]["layers"][0]["product"] == "SPL4SMGP.008"
        return resp(url, {"task_id": "abc"})

    def get(url, **kw):
        if url.endswith("/task/abc"):
            return resp(url, estado_tarea)
        if url.endswith("/bundle/abc"):
            return resp(url, {"files": [{"file_id": "1", "file_name": "x-request.json"},
                                        {"file_id": "2", "file_name": "x-granule-list.csv"},
                                        {"file_id": "3", "file_name": "x-SPL4SMGP-008-results.csv"}]})
        if url.endswith("/bundle/abc/3"):
            return resp(url, text=csv_ok)
        return resp(url, text="nada,aca\n1,2\n")

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "get", get)
    assert smap.estado(-30.0, -55.0)["estado"] == "pendiente"
    assert smap.estado(-30.0, -55.0)["estado"] == "pendiente"
    estado_tarea["status"] = "done"
    r = smap.estado(-30.0, -55.0)
    assert r["estado"] == "listo" and r["serie"][0]["sm"] == 0.3
    assert smap.estado(-30.0, -55.0)["estado"] == "listo"  # ahora sale de la caché
    assert sum(u.endswith("/task") for u in pedidos) == 1


def test_dos_metodos_de_suelo_descubierto():
    from fieldshift.analisis import descubierto

    def serie(valores_por_mes):
        return [{"anio": y, "mes": m, "ndvi": valores_por_mes[m - 1]} for y in (2022, 2023, 2024) for m in range(1, 13)]

    # agricultura con barbecho bien pelado (0,2) y cultivo (0,75): los dos métodos coinciden
    claro = descubierto.comparar(serie([0.75, 0.7, 0.55, 0.2, 0.2, 0.2, 0.2, 0.2, 0.5, 0.6, 0.75, 0.8]))
    assert claro["ok"] and claro["metodos"][1]["aplica"]
    assert claro["metodos"][0]["meses_por_anio"] == 5 and claro["coincidencia_pct"] >= 90
    # rastrojo que queda en 0,33: el corte fijo no lo ve, el automático sí
    rastrojo = descubierto.comparar(serie([0.75, 0.7, 0.4, 0.33, 0.33, 0.33, 0.33, 0.33, 0.35, 0.6, 0.75, 0.8]))
    assert rastrojo["metodos"][0]["meses_por_anio"] == 0
    assert rastrojo["metodos"][1]["meses_por_anio"] >= 5 and "más alto que el fijo" in rastrojo["lectura"]
    # pastura (0,45 a 0,8): Otsu separaría estaciones, no suelo: no aplica
    pastura = descubierto.comparar(serie([0.5, 0.45, 0.5, 0.6, 0.7, 0.75, 0.8, 0.8, 0.75, 0.7, 0.6, 0.5]))
    assert not pastura["metodos"][1]["aplica"] and "siguen siendo vegetación" in pastura["lectura"]
    # sin datos suficientes
    assert not descubierto.comparar([])["ok"]


def test_rango_de_la_erosion_y_de_las_frecuencias():
    from fieldshift.analisis import incertidumbre

    er = {"a_t_ha": 19.77, "tolerancia_t": 2.0, "r": 563, "k": 0.255, "ls": 1.112, "c": 0.1238, "p": 1.0, "pendiente_pct": 5.59}
    r = incertidumbre.rango_erosion(er, [563, 535])
    assert r["p10"] < er["a_t_ha"] < r["p90"]
    assert r["prob_supera_t"] == 1.0  # 19,8 contra 2: ningún supuesto lo baja de la tolerancia
    assert incertidumbre.rango_erosion(er, [563, 535]) == r  # semilla fija: reproducible
    cerca = incertidumbre.rango_erosion({**er, "tolerancia_t": 19.0}, [563])
    assert 0.2 < cerca["prob_supera_t"] < 0.9  # cerca de la tolerancia, hay duda de verdad
    assert incertidumbre.rango_erosion({"r": 1}) is None
    lo, hi = incertidumbre.wilson(0.3, 35)
    assert lo < 0.3 < hi and 0.15 < lo and hi < 0.45
    assert incertidumbre.wilson(None, 35) is None


def test_relieve_pendiente_y_erosion_por_cuadrado(monkeypatch):
    from fieldshift.analisis import relieve
    from fieldshift.fuentes import relieve as fuente

    # una loma: plano al oeste y una ladera de 8 % al este (px de 30 m)
    cols, filas, px = 60, 40, 30.0
    x = np.arange(cols) * px
    z = np.tile(np.where(x < 900, 100.0, 100 + (x - 900) * 0.08), (filas, 1))

    def mosaico(o, s, e, n, z_=13):
        return {"elev": z, "oeste": -56.6, "este": -56.58, "norte": -33.0, "sur": -33.011, "px_m": px, "fuente": "prueba"}

    monkeypatch.setattr(fuente, "mosaico", mosaico)
    cuadro = {"type": "Polygon", "coordinates": [[[-56.598, -33.001], [-56.582, -33.001], [-56.582, -33.010], [-56.598, -33.010], [-56.598, -33.001]]]}
    oeste = {"type": "Polygon", "coordinates": [[[-56.598, -33.001], [-56.5905, -33.001], [-56.5905, -33.010], [-56.598, -33.010], [-56.598, -33.001]]]}
    este = {"type": "Polygon", "coordinates": [[[-56.5895, -33.001], [-56.582, -33.001], [-56.582, -33.010], [-56.5895, -33.010], [-56.5895, -33.001]]]}
    secs = [{"id": "o", "nombre": "Llano", "geometria": oeste, "k": 0.3, "t": 7, "c_actual": 0.2, "c_plan": 0.02},
            {"id": "e", "nombre": "Ladera", "geometria": este, "k": 0.3, "t": 7, "c_actual": 0.2, "c_plan": 0.02}]
    # con el largo fijo de 100 m (como si lo hubiera cargado el productor): esta ladera pareja mide 870 m, y con su
    # largo real (tope de 300 m) la erosión del plan ya no entra en la tolerancia
    r = relieve.analizar(cuadro, secs, 500, largo_m=100)
    llano, ladera = r["secciones"]
    assert llano["pendiente_media"] < 1 and 6 < ladera["pendiente_media"] < 9
    assert ladera["erosion_actual"]["media"] > llano["erosion_actual"]["media"] * 5
    assert ladera["erosion_actual"]["pct_supera_t"] > 50 and ladera["erosion_plan"]["pct_supera_t"] == 0
    g = r["grilla"]
    assert len(g["elev"]) == g["filas"] and len(g["elev"][0]) == g["cols"]
    # la base (R · K · LS · P) por C da la misma erosión: el navegador calcula la de cualquier rotación
    assert abs(ladera["base_media"] * 0.02 - ladera["erosion_plan"]["media"]) < 0.1
    q = ladera["base_cuantiles"]
    assert len(q) == 101 and q == sorted(q)
    supera = 100 - sum(1 for v in q if v * 0.2 <= 7)
    assert abs(supera - ladera["erosion_actual"]["pct_supera_t"]) <= 2
    for fila_b, fila_p, fila_s in zip(g["erosion_base"], g["erosion_plan"], g["seccion"]):
        for b, ep, sec in zip(fila_b, fila_p, fila_s):
            if sec >= 0:
                assert abs(b * 0.02 - ep) < 0.05
    sin_plan = relieve.analizar(cuadro, [{**x, "c_plan": None} for x in secs], 500, largo_m=100)
    assert "erosion_plan" not in sin_plan["grilla"] and "erosion_plan" not in sin_plan["secciones"][1]



def test_largo_de_ladera_sale_del_relieve(monkeypatch):
    """: el largo de ladera sale del camino del agua en SRTM (antes, 100 m fijos). Una ladera de 8 % y
    240 m entre un llano y una meseta tiene que dar cerca de 240 m; la erosión del lote cambia con eso."""
    from fieldshift.analisis import plan, relieve
    from fieldshift.fuentes import relieve as fuente

    cols, filas, px = 60, 40, 30.0
    x = np.arange(cols) * px
    z = np.tile(100 + np.clip(x - 900, 0, 240) * 0.08, (filas, 1))

    def mosaico(o, s, e, n, z_=13):
        return {"elev": z, "oeste": -56.6, "este": -56.58, "norte": -33.0, "sur": -33.011, "px_m": px, "fuente": "prueba"}

    monkeypatch.setattr(fuente, "mosaico", mosaico)
    cuadro = {"type": "Polygon", "coordinates": [[[-56.598, -33.001], [-56.582, -33.001], [-56.582, -33.010], [-56.598, -33.010], [-56.598, -33.001]]]}
    ladera = {"type": "Polygon", "coordinates": [[[-56.5899, -33.002], [-56.5875, -33.002], [-56.5875, -33.009], [-56.5899, -33.009], [-56.5899, -33.002]]]}
    r = relieve.ladera_por_seccion(cuadro, [{"id": "l", "geometria": ladera}])
    assert 180 <= r["l"]["largo_m"] <= 300, r
    assert 6 < r["l"]["pendiente_media"] < 9
    # el análisis lo usa si el productor no cargó el suyo, y el suyo manda
    assert plan._largo_de({}, {}, r["l"])["largo_origen"] == "srtm"
    assert plan._largo_de({"largo_pendiente_m": 80}, {}, r["l"]) ["largo_pendiente_m"] == 80
    assert plan._largo_de({}, {}, {})["largo_pendiente_m"] == 100
    # en el 3D, el promedio de los tramos queda cerca de la ecuación con el largo del lote
    gr = relieve._grilla(cuadro)
    from shapely import contains_xy
    from shapely.geometry import shape
    msk = contains_xy(shape(ladera), gr["LON"], gr["LAT"])
    seg = relieve.ls_segmentos(gr["s"], gr["largo"], gr["paso"])[msk].mean()
    lote = relieve.ls_grilla(gr["s"][msk], r["l"]["largo_m"]).mean()
    assert abs(seg / lote - 1) < 0.25

def test_analizar_campo_pasos_cronometro_y_progreso_secciones(monkeypatch):
    from fieldshift.fuentes import mgap, modis, power

    monkeypatch.setattr(power, "bajar_diario", lambda lat, lon: power_sintetico(anios=(2005, 2006, 2007, 2008, 2009, 2010, 2011)))
    monkeypatch.setattr(mgap, "factor_r", lambda lat, lon: {"r": 550, "estaciones": [{"nombre": "Florida", "km": 15}]})
    monkeypatch.setattr(mgap, "suelo_punto", lambda lat, lon: {
        "ok": True, "grupo_coneat": "10.8a", "factor_k": 0.24, "tolerancia_t": 7.0,
        "pendiente_pct": 3.0, "capacidad_uso": "IIIe"
    })
    monkeypatch.setattr(modis, "ndvi_punto", lambda lat, lon: {
        "serie": [{"fecha": "2023-01-01", "ndvi": 0.75}],
        "temporadas": [{"temporada": "verano 2023", "ndvi_max": 0.78, "uso_detectado": "agrícola"}],
        "fuente": "MODIS simulado"
    })

    campo = {
        "id": "campo_test",
        "contorno": {
            "type": "Polygon",
            "coordinates": [[[-56.5, -33.4], [-56.4, -33.4], [-56.4, -33.5], [-56.5, -33.5], [-56.5, -33.4]]]
        },
        "secciones": [
            {
                "id": "s1",
                "nombre": "Potrero 1",
                "geometria": {
                    "type": "Polygon",
                    "coordinates": [[[-56.5, -33.4], [-56.45, -33.4], [-56.45, -33.5], [-56.5, -33.5], [-56.5, -33.4]]]
                }
            },
            {
                "id": "s2",
                "nombre": "Potrero 2",
                "geometria": {
                    "type": "Polygon",
                    "coordinates": [[[-56.45, -33.4], [-56.4, -33.4], [-56.4, -33.5], [-56.45, -33.5], [-56.45, -33.4]]]
                }
            }
        ]
    }

    eventos = list(plan.analizar_campo_pasos(campo))
    progresos = [e for e in eventos if e["tipo"] == "progreso"]
    assert len(progresos) >= 5

    avances = [p["avance"] for p in progresos]
    assert avances == sorted(avances)
    assert avances[0] == 0.05
    assert avances[-1] >= 0.9

    mensajes = [p["mensaje"] for p in progresos]
    assert any("Potrero 1" in m and "CONEAT" in m and "NDVI" in m for m in mensajes)
    assert any("Potrero 2" in m and "CONEAT" in m and "NDVI" in m for m in mensajes)

    assert eventos[-1]["tipo"] == "resultado"
    res = eventos[-1]["resultado"]
    assert "cronometro_s" in res
    crono = res["cronometro_s"]
    for k in ("total", "nasa_power", "clima", "mgap_factor_r", "secciones_total", "armado_plan", "detalle_secciones"):
        assert k in crono
    assert "s1" in crono["detalle_secciones"]
    assert "s2" in crono["detalle_secciones"]
    assert "suelo" in crono["detalle_secciones"]["s1"]
    assert "ndvi" in crono["detalle_secciones"]["s1"]
    assert "rotaciones" in crono["detalle_secciones"]["s1"]


def test_analizar_campo_pasos_descargas_paralelas(monkeypatch):
    """Verifica que POWER, factor R y suelos/NDVI de secciones arranquen en paralelo."""
    import time
    from fieldshift.fuentes import hls_ndvi, mgap, modis, power

    tiempos = {}

    def mock_power(lat, lon):
        t0 = time.perf_counter()
        time.sleep(0.08)
        tiempos["power"] = (t0, time.perf_counter())
        return power_sintetico(anios=(2005, 2006, 2007, 2008, 2009, 2010, 2011))

    def mock_factor_r(lat, lon):
        t0 = time.perf_counter()
        time.sleep(0.08)
        tiempos["factor_r"] = (t0, time.perf_counter())
        return {"r": 550, "estaciones": [{"nombre": "Florida", "km": 15}]}

    def mock_suelo(lat, lon):
        t0 = time.perf_counter()
        time.sleep(0.08)
        tiempos[f"suelo_{lat}_{lon}"] = (t0, time.perf_counter())
        return {
            "ok": True, "grupo_coneat": "10.8a", "factor_k": 0.24, "tolerancia_t": 7.0,
            "pendiente_pct": 3.0, "capacidad_uso": "IIIe",
        }

    def mock_ndvi(lat, lon):
        t0 = time.perf_counter()
        time.sleep(0.08)
        tiempos[f"ndvi_{lat}_{lon}"] = (t0, time.perf_counter())
        return {
            "serie": [{"fecha": "2023-01-01", "ndvi": 0.75}],
            "temporadas": [{"temporada": "verano 2023", "ndvi_max": 0.78, "uso_detectado": "agrícola"}],
            "fuente": "MODIS simulado",
        }

    def mock_hls(geom, **k):
        t0 = time.perf_counter()
        time.sleep(0.08)
        tiempos[f"hls_{len(tiempos)}"] = (t0, time.perf_counter())
        return {"ok": True, "mensual": [], "fuente": "HLS simulado"}

    monkeypatch.setattr(power, "bajar_diario", mock_power)
    monkeypatch.setattr(mgap, "factor_r", mock_factor_r)
    monkeypatch.setattr(mgap, "suelo_punto", mock_suelo)
    monkeypatch.setattr(modis, "ndvi_punto", mock_ndvi)
    monkeypatch.setattr(hls_ndvi, "consultar_hls_seccion", mock_hls)

    campo = {
        "id": "campo_paralelo",
        "contorno": {
            "type": "Polygon",
            "coordinates": [[[-56.5, -33.4], [-56.4, -33.4], [-56.4, -33.5], [-56.5, -33.5], [-56.5, -33.4]]],
        },
        "secciones": [
            {
                "id": "s1",
                "nombre": "Potrero 1",
                "geometria": {
                    "type": "Polygon",
                    "coordinates": [[[-56.5, -33.4], [-56.45, -33.4], [-56.45, -33.5], [-56.5, -33.5], [-56.5, -33.4]]],
                },
            },
            {
                "id": "s2",
                "nombre": "Potrero 2",
                "geometria": {
                    "type": "Polygon",
                    "coordinates": [[[-56.45, -33.4], [-56.4, -33.4], [-56.4, -33.5], [-56.45, -33.5], [-56.45, -33.4]]],
                },
            },
        ],
    }

    t0_analisis = time.perf_counter()
    eventos = list(plan.analizar_campo_pasos(campo))
    duracion = time.perf_counter() - t0_analisis

    # En serie tardarían al menos 0.08 * 6 (red) + 0.15 (clima) + 0.12 (rotaciones) ≈ 0.75 - 0.95 s.
    # En paralelo las descargas arrancan juntas: dura ~0.30 - 0.55 s.
    assert duracion < 0.65

    # Comprobar que todas las descargas arrancaron prácticamente juntas (en una ventana de < 0.05 s)
    inicios = [t_ini for t_ini, _ in tiempos.values()]
    assert max(inicios) - min(inicios) < 0.05
    assert eventos[-1]["tipo"] == "resultado"




def test_analizar_campo_pasos_fallback_tipicos_cuando_servicios_externos_fallan(monkeypatch):
    """Verifica que si MGAP o MODIS fallan/no responden, el análisis no se cae y pasa a valores típicos avisando."""
    from fieldshift.fuentes import mgap, modis, power

    monkeypatch.setattr(power, "bajar_diario", lambda lat, lon: power_sintetico(anios=(2005, 2006, 2007, 2008, 2009, 2010, 2011)))
    # Simular que MGAP no responde (timeout en factor R y suelo)
    monkeypatch.setattr(mgap, "factor_r", lambda lat, lon: None)
    monkeypatch.setattr(mgap, "suelo_punto", lambda lat, lon: {"ok": False, "errores": ["Timeout en identify (15 s)"]})
    # y el respaldo mundial de suelos tampoco
    from fieldshift.fuentes import soilgrids
    monkeypatch.setattr(soilgrids, "suelo_punto", lambda lat, lon: {"ok": False, "errores": ["Timeout SoilGrids"]})
    # Simular que MODIS no responde (timeout en ORNL DAAC)
    monkeypatch.setattr(modis, "ndvi_punto", lambda lat, lon: {"serie": [], "error": "Timeout ORNL DAAC (20 s)"})

    campo = {
        "id": "campo_timeout",
        "contorno": {
            "type": "Polygon",
            "coordinates": [[[-56.5, -33.4], [-56.4, -33.4], [-56.4, -33.5], [-56.5, -33.5], [-56.5, -33.4]]],
        },
        "secciones": [
            {
                "id": "s1",
                "nombre": "Potrero 1",
                "geometria": {
                    "type": "Polygon",
                    "coordinates": [[[-56.5, -33.4], [-56.45, -33.4], [-56.45, -33.5], [-56.5, -33.5], [-56.5, -33.4]]],
                },
            }
        ],
    }

    eventos = list(plan.analizar_campo_pasos(campo))
    progresos = [e for e in eventos if e["tipo"] == "progreso"]
    mensajes = [p["mensaje"] for p in progresos]

    # Verifica que en el mensaje de progreso se avisa del uso de suelo típico
    assert any("suelo típico" in m for m in mensajes)

    # Verifica que el análisis culminó exitosamente con el resultado
    assert eventos[-1]["tipo"] == "resultado"
    res = eventos[-1]["resultado"]

    # Factor R debió caer a NASA POWER avisando que MGAP no respondió
    assert res["factor_r"]["mgap"] is None
    assert "el MGAP no respondió" in res["factor_r"]["fuente"]

    # La sección tiene suelo con ok: False y se evaluó con los valores típicos de K, T y pendiente
    sec_res = res["secciones"][0]
    assert sec_res["suelo"]["ok"] is False
    rec_id = sec_res["recomendada_id"]
    assert rec_id is not None
    assert len(res["plan"]["secciones"]) == 1


def test_mgap_suelo_punto_aborta_rapido_tras_timeout_coneat_k(monkeypatch):
    """Verifica que si Coneat_K da timeout, suelo_punto aborta de inmediato sin esperar a los otros dos servicios."""
    import httpx
    from fieldshift import cache
    from fieldshift.fuentes import mgap

    monkeypatch.setattr(cache, "leer", lambda tipo, clave, max_dias: None)

    llamadas = []

    def mock_get(url, params=None, timeout=None):
        llamadas.append((url, timeout))
        raise httpx.ReadTimeout("Timeout simulado en Coneat_K")

    monkeypatch.setattr(httpx, "get", mock_get)

    res = mgap.suelo_punto(-33.4, -56.5)
    assert res["ok"] is False
    assert any("Coneat_K" in e for e in res["errores"])
    # Solo debe haberse hecho 1 llamada (a Coneat_K), no 3
    assert len(llamadas) == 1
    assert llamadas[0][1] == mgap.TIMEOUT_IDENTIFY == 15.0


def test_elegir_variadas_solo_opciones_que_cumplen():
    r_gan1 = {
        "id": "gan1",
        "nombre": "Pradera permanente (renovación cada 4 años)",
        "tipo": "ganadera",
        "puntaje_total": 80,
        "erosion": {"a_t_ha": 1.61, "tolerancia_t": 2.0, "cumple": True},
    }
    r_gan2 = {
        "id": "gan2",
        "nombre": "Campo natural con manejo del pastoreo",
        "tipo": "ganadera",
        "puntaje_total": 75,
        "erosion": {"a_t_ha": 1.58, "tolerancia_t": 2.0, "cumple": True},
    }
    r_agr1 = {
        "id": "agr1",
        "nombre": "Trigo / soja de segunda → maíz",
        "tipo": "agrícola",
        "puntaje_total": 60,
        "erosion": {"a_t_ha": 2.98, "tolerancia_t": 2.0, "cumple": False},
    }
    top, nota = plan.elegir_variadas([r_gan1, r_gan2, r_agr1], 3)
    # Con dos que cumplen ya hay tres estrategias contando lo de hoy: no se completa con la que no cumple
    assert all(e["erosion"]["cumple"] for e in top)
    assert r_agr1 not in top
    assert len(top) == 2
    # Debe haber una nota explicando que solo cultivos no cumple y dando los números reales
    assert nota is not None
    assert "Con solo cultivos, ninguna rotación cumple lo que aguanta el suelo" in nota
    assert "trigo / soja de segunda → maíz" in nota
    assert "perdería 3 t/ha/año y el suelo aguanta 2" in nota


def test_elegir_variadas_ambos_tipos_cumplen():
    r_gan = {
        "id": "gan",
        "nombre": "Pradera permanente",
        "tipo": "ganadera",
        "puntaje_total": 85,
        "erosion": {"a_t_ha": 1.8, "tolerancia_t": 7.0, "cumple": True},
    }
    r_agr = {
        "id": "agr",
        "nombre": "Maíz → soja con cobertura",
        "tipo": "agrícola",
        "puntaje_total": 75,
        "erosion": {"a_t_ha": 3.0, "tolerancia_t": 7.0, "cumple": True},
    }
    r_gan2 = {
        "id": "gan2",
        "nombre": "Verdeo → sorgo forrajero",
        "tipo": "ganadera",
        "puntaje_total": 70,
        "erosion": {"a_t_ha": 4.2, "tolerancia_t": 7.0, "cumple": True},
    }
    top, nota = plan.elegir_variadas([r_gan, r_agr, r_gan2], 3)
    assert len(top) == 3
    assert all(e["erosion"]["cumple"] for e in top)
    assert r_gan in top and r_agr in top
    assert nota is None


def test_elegir_variadas_ninguna_cumple_muestra_menor_erosion():
    r_agr1 = {
        "id": "agr1",
        "nombre": "Soja continua",
        "tipo": "agrícola",
        "puntaje_total": 55,
        "erosion": {"a_t_ha": 14.0, "tolerancia_t": 5.0, "cumple": False},
    }
    r_gan1 = {
        "id": "gan1",
        "nombre": "Pastura degradada",
        "tipo": "ganadera",
        "puntaje_total": 45,
        "erosion": {"a_t_ha": 6.8, "tolerancia_t": 5.0, "cumple": False},
    }
    r_agr2 = {
        "id": "agr2",
        "nombre": "Maíz continuo",
        "tipo": "agrícola",
        "puntaje_total": 40,
        "erosion": {"a_t_ha": 10.5, "tolerancia_t": 5.0, "cumple": False},
    }
    top, nota = plan.elegir_variadas([r_agr1, r_gan1, r_agr2], 3)
    # Si ninguna cumple, primero la que menos erosiona (r_gan1 con 6.8 t/ha) y se completa hasta dos
    # alternativas con la de mejor puntaje de otro grupo
    assert len(top) == 2
    assert top[0]["id"] == "gan1"
    assert top[1]["id"] == "agr1"
    assert nota is not None
    assert "Ninguna opción queda dentro de lo que aguanta el suelo en este lote (5 t/ha/año)" in nota
    assert "pastura degradada" in nota
    assert ": 6,8 t/ha/año" in nota


def test_elegir_variadas_completa_hasta_dos_alternativas():
    """Una sola opción cumple: se suma la mejor que no cumple, del otro grupo, sin repetir la misma rotación en
    curvas de nivel."""
    def ev(i, tipo, pts, a, cumple):
        return {"id": i, "nombre": i, "tipo": tipo, "puntaje_total": pts,
                "erosion": {"a_t_ha": a, "tolerancia_t": 5.0, "cumple": cumple}}
    r_gan = ev("pradera", "ganadera", 70, 3.0, True)
    r_agr_curvas_no = ev("maiz_soja", "agrícola", 65, 9.0, False)
    r_agr2 = ev("trigo_soja", "agrícola", 60, 8.0, False)
    r_gan2 = ev("campo_natural", "ganadera", 68, 6.0, False)
    top, _ = plan.elegir_variadas([r_gan, r_gan2, r_agr_curvas_no, r_agr2], 3)
    assert [e["id"] for e in top] == ["pradera", "maiz_soja"]
    # la versión sin curvas de una rotación que ya está en curvas no se repite
    r_curvas = ev("maiz_soja_curvas", "agrícola", 72, 4.0, True)
    top, _ = plan.elegir_variadas([r_curvas, r_agr_curvas_no, r_gan2], 3)
    assert [e["id"] for e in top] == ["maiz_soja_curvas", "campo_natural"]


def test_perdidas_por_seca_fao33():
    """Pérdida de rinde por año con FAO-33 y la caída de un año seco (1 de cada 5) contra uno normal."""
    from fieldshift.analisis import clima
    # diez años: pérdidas 0, 0,1, 0,1, 0,2, 0,2, 0,2, 0,3, 0,3, 0,5, 0,6 del rinde sin falta de agua
    v = [0, 0.1, 0.1, 0.2, 0.2, 0.2, 0.3, 0.3, 0.5, 0.6]
    r = clima._perdidas([{"perdida_rinde": x} for x in v])
    assert r["perdida_media"] == 0.25
    # mediana 0,2; percentil 80 = 0,34 (entre 0,3 y 0,5): 1 - 0,66 / 0,8 = 0,175
    assert r["perdida_anio_seco"] == 0.34
    assert r["caida_anio_seco"] == 0.175
    assert clima._perdidas([{"anio": 2000}]) == {"perdida_media": None, "perdida_anio_seco": None, "caida_anio_seco": None}


def test_factor_c_oficial_soja_continua_calculo_a_mano():
    """Comprueba el factor C oficial de Erosión 6.0 contra un cálculo analítico hecho a mano.

    Para soja continua en siembra directa con reparto de erosividad uniforme (1/12 por mes):
      - Siembra: 15 de noviembre, cosecha: 30 de marzo (ciclo 135 días).
      - Rastrojo a la siembra: <= 30 % (escalón 30 de la tabla de soja).
      - Rastrojo dejado a la cosecha: 30 % (escalón 30 en período 4).
      - Período 1 (15 nov a 15 dic, 30 días): 15 días nov (15/360) + 15 días dic (15/372) = 0,081989
        RPS = 0,26 -> C1 = 0,26 * 0,081989 = 0,021317
      - Período 2 (15 dic a 14 ene, 30 días): 16 días dic (16/372) + 14 días ene (14/372) = 0,080645
        RPS = 0,24 -> C2 = 0,24 * 0,080645 = 0,019355
      - Período 3 (14 ene a 30 mar, 75 días): 17 días ene (17/372) + 28 días feb (28/336) + 30 días mar (30/372) = 0,209677
        RPS = 0,21 -> C3 = 0,21 * 0,209677 = 0,044032
      - Período 4 (30 mar a 15 nov, 230 días): 1 día mar (1/372) + 7 meses completos (7/12) + 15 días nov (15/360) = 0,627688
        RPS = 0,46 -> C4 = 0,46 * 0,627688 = 0,288737
      - Suma C analítico = C1 + C2 + C3 + C4 = 0,373441
    """
    ctx = ctx_basico()
    ev_soja = rotaciones.evaluar(rotaciones.ROTACIONES["soja_continua"], ctx)
    c_cod = ev_soja["erosion"]["c"]

    e1 = 15 / (12 * 30) + 15 / (12 * 31)
    e2 = 16 / (12 * 31) + 14 / (12 * 31)
    e3 = 17 / (12 * 31) + 28 / (12 * 28) + 30 / (12 * 31)
    e4 = 1 / (12 * 31) + 7 / 12 + 15 / (12 * 30)
    assert abs((e1 + e2 + e3 + e4) - 1.0) < 1e-6
    c_mano = 0.26 * e1 + 0.24 * e2 + 0.21 * e3 + 0.46 * e4
    assert abs(c_cod - c_mano) < 1e-3
    assert abs(c_cod - 0.3734) < 1e-3


def test_factor_c_sentido_comun_orden_de_magnitud():
    """Sentido común: soja continua > rotación con maíz y trigo > pradera permanente."""
    ctx = ctx_basico()
    ev_soja = rotaciones.evaluar(rotaciones.ROTACIONES["soja_continua"], ctx)
    ev_trigo_maiz = rotaciones.evaluar(rotaciones.ROTACIONES["trigo_soja_maiz"], ctx)
    ev_pradera = rotaciones.evaluar(rotaciones.ROTACIONES["pradera_permanente"], ctx)

    c_soja = ev_soja["erosion"]["c"]
    c_trigo_maiz = ev_trigo_maiz["erosion"]["c"]
    c_pradera = ev_pradera["erosion"]["c"]

    assert c_soja > c_trigo_maiz > c_pradera
    assert ev_soja["erosion"]["a_t_ha"] > ev_trigo_maiz["erosion"]["a_t_ha"] > ev_pradera["erosion"]["a_t_ha"]


def test_guiado_no_anuncia_cambio_chico():
    """El chat no debe anunciar un cambio chico (ej. 4 a 5 años de cada 10 en soja), solo cambios claros."""
    import json as _json
    demo = Path(__file__).resolve().parents[2] / "frontend" / "public" / "ejemplos" / "campo_demo.fieldshift.json"
    d = _json.loads(demo.read_text(encoding="utf-8"))

    # Simular un plan donde el cultivo principal es soja (con cambio chico 0.444 -> 0.471)
    res = _json.loads(_json.dumps(d["analisis"]))
    # Los números de la tendencia se fijan acá (antes salían del ejemplo, y al pasar la lluvia a GPM
    # IMERG el maíz dejó de tener un cambio claro y la prueba se rompió sin que cambiara el código)
    res["clima"]["tendencia"]["cultivos"]["soja"]["prob_seca"] = {"antes": 0.444, "ahora": 0.471, "cambio_claro": False}
    res["clima"]["tendencia"]["cultivos"]["maiz"]["prob_seca"] = {"antes": 0.333, "ahora": 0.588, "cambio_claro": True}
    res["plan"]["secciones"] = [
        {"seccion_id": "s1", "rotacion_id": "soja_continua", "area_ha": 100, "cultivos": ["soja"]}
    ]
    txt = guiado.resumen_texto(res, d["campo"])
    # No debe anunciar el cambio chico en soja
    assert "en soja" not in txt.lower() or "la floración llegó con menos" not in txt
    # Debe usar la frase de lluvia o calor
    assert "la lluvia del año pasó de" in txt

    # Ahora simular un plan con maíz (cambio claro 0.333 -> 0.588, dif >= 0.2)
    res["plan"]["secciones"] = [
        {"seccion_id": "s1", "rotacion_id": "trigo_soja_maiz", "area_ha": 100, "cultivos": ["maiz"]}
    ]
    txt_maiz = guiado.resumen_texto(res, d["campo"])
    assert "la floración llegó con menos de la mitad del agua que necesita 3 de cada 10 años" in txt_maiz
    assert "maíz" in txt_maiz.lower()


def test_rotaciones_no_anuncia_cambio_chico():
    """Los riesgos en rotaciones solo anuncian corrimiento de clima si el aumento es un cambio claro (>= 0.2)."""
    ctx = ctx_basico()
    # Modificamos clima_info para probar caso chico vs claro
    clima_info = {
        "tendencia": {
            "periodo_antes": "1991-2008",
            "periodo_ahora": "2009-2025",
            "cultivos": {
                "soja": {"prob_seca": {"antes": 0.444, "ahora": 0.471}},  # dif 0.027
                "soja2": {"prob_seca": {"antes": 0.222, "ahora": 0.353}},  # dif 0.131 (menor a 0.2)
                "maiz": {"prob_seca": {"antes": 0.333, "ahora": 0.588}},  # dif 0.255 (cambio claro)
            },
        }
    }
    ctx_chico = {**ctx, "clima_info": clima_info}

    # Evaluar soja continua (solo tiene soja)
    ev_soja = rotaciones.evaluar(rotaciones.ROTACIONES["soja_continua"], ctx_chico)
    exp_soja = rotaciones.explicar(ev_soja, ctx_chico, None)
    # Ningún riesgo debe decir "El clima se está corriendo: para soja..."
    assert not any("El clima se está corriendo: para soja" in r for r in exp_soja["riesgos"])

    # Evaluar rotación con maíz
    ev_maiz = rotaciones.evaluar(rotaciones.ROTACIONES["trigo_soja_maiz"], ctx_chico)
    exp_maiz = rotaciones.explicar(ev_maiz, ctx_chico, None)
    # Debe tener el riesgo para maíz
    assert any("El clima se está corriendo: para maíz" in r for r in exp_maiz["riesgos"])
    # Pero NO para soja2
    assert not any("para soja de segunda" in r for r in exp_maiz["riesgos"])


def test_equilibrio_cuenta_la_parte_agricola_de_las_rotaciones_mixtas():
    """Alfalfa 3 años → maíz → trigo / soja 2ª es 2 de 5 agrícola: entra en el reparto aunque no sea agrícola pura,
    y si las sugeridas no llegan a la meta, se dice por qué."""
    gan = {"id": "campo_natural", "tipo": "ganadera", "anios": [("campo_natural", "campo_natural")], "puntaje_total": 70,
           "erosion": {"ratio": 0.5}}
    mixta = {"id": "alfalfa_maiz_curvas", "tipo": "agrícola-ganadera", "puntaje_total": 67, "erosion": {"ratio": 0.8},
             "anios": [("alfalfa", "alfalfa")] * 3 + [("cobertura", "maiz"), ("trigo", "soja2")]}
    sec = {"id": "s1", "area_ha": 100, "actual": None, "alternativas": [gan, mixta], "recomendada_id": "campo_natural"}
    reparto, info = plan._equilibrio([sec], {"sistema": {"tipo": "mixto"}, "objetivos": {"pct_agricola": 50}})
    assert reparto == {"s1": "alfalfa_maiz_curvas"}
    assert info["pct_sugerido"] == 40 and info["nota"] is None
    reparto, info = plan._equilibrio([sec], {"sistema": {"tipo": "mixto"}, "objetivos": {"pct_agricola": 80}})
    assert "40 % agrícola" in info["nota"]


def test_experiencia_vale_para_el_lote_que_nombra_y_para_el_cultivo_repetido():
    from fieldshift.analisis import rotaciones as R
    exp = {"que_fallo": "la soja continua en La Loma se lavó", "que_funciono": "el maíz temprano en el Potrero Grande"}
    secs = ["La Loma", "Potrero Grande"]
    def alertas(seccion, anios):
        e = {"puntaje_total": 50, "alertas": []}
        plan.ajuste_experiencia(e, R.Rotacion("x", "x", "x", tuple(anios), "agrícola"), exp, seccion, secs)
        return e
    assert alertas("La Loma", [("barbecho", "soja")])["alertas"]  # la soja continua, donde falló
    assert not alertas("La Loma", [("trigo", "soja2"), ("cobertura", "maiz")])["alertas"]  # soja un año de cada dos
    assert not alertas("Potrero Grande", [("barbecho", "soja")])["alertas"]  # otro lote
    assert alertas("Potrero Grande", [("cobertura", "maiz")]).get("beneficios_extra")


def test_campo_natural_no_se_exige_plan_de_uso():
    """: el Plan de Uso es para cultivos y pasturas sembradas; el campo natural que erosiona algo más de lo
    que aguanta un suelo superficial no sale «no cumple» (La Loma del ejemplo: 3,2 contra 2)."""
    ctx = ctx_basico()
    ctx["suelo"] = {**ctx["suelo"], "tolerancia_t": 0.1, "pendiente_pct": 8}
    cn = rotaciones.evaluar(rotaciones.ROTACIONES["campo_natural"], ctx)
    assert cn["erosion"]["ratio"] > 1
    assert cn["erosion"]["exigible"] is False and cn["erosion"]["cumple"] is True
    assert any("no se exige" in a for a in cn["alertas"])
    soja = rotaciones.evaluar(rotaciones.ROTACIONES["soja_continua"], ctx)
    assert soja["erosion"]["exigible"] is True and soja["erosion"]["cumple"] is False


def test_estacion_de_referencia_no_suma_heladas(monkeypatch):
    """: la estación del productor que registra más heladas suma el riesgo; una de referencia lejana (la de
    INUMET del campo de ejemplo) no."""
    from fieldshift.fuentes import mgap, modis, power

    monkeypatch.setattr(power, "bajar_diario", lambda lat, lon: power_sintetico(anios=(2005, 2006, 2007, 2008, 2009, 2010, 2011)))
    monkeypatch.setattr(mgap, "factor_r", lambda lat, lon: {"r": 550, "estaciones": [{"nombre": "Florida", "km": 15}]})
    monkeypatch.setattr(mgap, "suelo_punto", lambda lat, lon: {
        "ok": True, "grupo_coneat": "10.8a", "factor_k": 0.24, "tolerancia_t": 7.0, "pendiente_pct": 3.0, "capacidad_uso": "IIIe"})
    monkeypatch.setattr(modis, "ndvi_punto", lambda lat, lon: {
        "serie": [{"fecha": "2023-01-01", "ndvi": 0.75}],
        "temporadas": [{"temporada": "verano 2023", "ndvi_max": 0.78, "uso_detectado": "agrícola"}], "fuente": "MODIS simulado"})
    cuadro = {"type": "Polygon", "coordinates": [[[-56.5, -33.4], [-56.45, -33.4], [-56.45, -33.5], [-56.5, -33.5], [-56.5, -33.4]]]}

    def problemas(estacion):
        campo = {"id": "t", "contorno": cuadro, "secciones": [{"id": "s1", "nombre": "Potrero 1", "geometria": cuadro}],
                 "estacion": estacion}
        res = plan.analizar_campo(campo)
        return res["secciones"][0]["problemas"]

    helador = {"comparacion": {"campo_mas_helador": True}}
    assert "helada" in problemas(helador)
    assert "helada" not in problemas({**helador, "referencia": {"nombre": "INUMET Paso de los Toros G3", "distancia_km": 47}})


def test_rango_de_erosion_usa_el_largo_de_ladera_del_lote():
    # La simulación movía la pendiente con 100 m de ladera fijos. Con 300 m y una pendiente que cruza el
    # corte de 5 % (exponente 0,4 → 0,5), el rango tiene que salir igual que recalcular LS con ese largo.
    import numpy as np

    from fieldshift.analisis import incertidumbre
    from fieldshift.analisis.rotaciones import factor_ls

    er = {"r": 600, "k": 0.3, "ls": factor_ls(4.5, 300), "c": 0.1, "p": 1.0, "tolerancia_t": 7, "pendiente_pct": 4.5,
          "largo_m": 300}
    r = incertidumbre.rango_erosion(er, [600])
    rng = np.random.default_rng(incertidumbre.SEMILLA)
    n = incertidumbre.SIMULACIONES
    R = incertidumbre._triangular(rng, 600, 540, 660, n)
    K = incertidumbre._triangular(rng, 0.3, 0.24, 0.36, n)
    s = incertidumbre._triangular(rng, 4.5, 4.5 * 0.7, 4.5 * 1.3, n)
    C = incertidumbre._triangular(rng, 0.1, 0.075, 0.115, n)
    A = R * K * np.array([factor_ls(x, 300) for x in s]) * C
    assert [r["p10"], r["p50"], r["p90"]] == [round(float(np.percentile(A, q)), 1) for q in (10, 50, 90)]
    assert r["p90"] > 30  # con 100 m fijos daba 28,0


def test_factor_r_medido_fuera_de_uruguay_reemplaza_a_la_formula(monkeypatch):
    """: un campo que trae `factor_r_medido` (los terrenos de ejemplo, con el mapa GloREDa) usa ese R
    en vez del estimado con la lluvia anual; en Uruguay sigue mandando el oficial del MGAP."""
    from fieldshift.fuentes import hls_ndvi, mgap, modis, power, soilgrids

    monkeypatch.setattr(power, "bajar_diario", lambda lat, lon: power_sintetico(anios=(2005, 2006, 2007, 2008, 2009, 2010, 2011)))
    monkeypatch.setattr(soilgrids, "suelo_punto", lambda lat, lon: {"ok": False, "errores": ["sin red"]})
    monkeypatch.setattr(mgap, "suelo_punto", lambda lat, lon: {"ok": False, "errores": ["sin red"]})
    monkeypatch.setattr(modis, "ndvi_punto", lambda lat, lon: {"serie": [], "error": "sin red"})
    monkeypatch.setattr(hls_ndvi, "consultar_hls_seccion", lambda g: {"ok": False, "error": "sin red"})

    def campo(lat, lon, medido=None):
        g = {"type": "Polygon", "coordinates": [[[lon, lat], [lon + 0.004, lat], [lon + 0.004, lat - 0.003], [lon, lat - 0.003], [lon, lat]]]}
        c = {"id": "c", "contorno": g, "secciones": [{"id": "s1", "nombre": "Lote", "geometria": g}]}
        if medido:
            c["factor_r_medido"] = medido
        return c

    # Alemania, sin dato medido: la fórmula con la lluvia anual
    monkeypatch.setattr(mgap, "factor_r", lambda lat, lon: None)
    sin = plan.analizar_campo(campo(50.1, 7.12))
    assert sin["factor_r"]["medido"] is None and "estimado" in sin["factor_r"]["fuente"]
    # con dato medido: se usa ese, en la ecuación de cada rotación y en la lista de fuentes
    con = plan.analizar_campo(campo(50.1, 7.12, {"r": 48.0, "fuente": "GloREDa 1.2"}))
    assert con["factor_r"]["usado"] == 48.0 and con["factor_r"]["medido"]["r"] == 48.0
    assert "medido (GloREDa 1.2)" in con["factor_r"]["fuente"]
    assert con["factor_r"]["nasa"] == sin["factor_r"]["nasa"]  # el estimado se sigue informando al lado
    assert all(e["erosion"]["r"] == 48 for e in con["secciones"][0]["todas"])
    assert any("GloREDa" in f["nombre"] for f in con["fuentes"])
    assert not any("GloREDa" in f["nombre"] for f in sin["fuentes"])
    # en Uruguay manda el R oficial del MGAP aunque el campo traiga uno medido
    monkeypatch.setattr(mgap, "factor_r", lambda lat, lon: {"r": 600, "estaciones": [{"nombre": "durazno", "km": 12}]})
    uy = plan.analizar_campo(campo(-33.4, -56.5, {"r": 48.0, "fuente": "GloREDa 1.2"}))
    assert uy["factor_r"]["usado"] == 600 and uy["factor_r"]["medido"] is None


def test_suelo_del_lote_se_mira_en_el_grupo_coneat_mas_grande():
    # El punto del lote cae en un grupo chico; se mira adentro del que ocupa más superficie
    from fieldshift.fuentes import mgap

    grande = {"type": "Polygon", "coordinates": [[[0, 0], [8, 0], [8, 10], [0, 10], [0, 0]]]}
    chico = {"type": "Polygon", "coordinates": [[[8, 0], [10, 0], [10, 10], [8, 10], [8, 0]]]}
    partes = [{"grupo_coneat": "10.8", "fraccion": 0.8, "geometria": grande}, {"grupo_coneat": "03.2", "fraccion": 0.2, "geometria": chico}]
    la, lo = mgap.punto_del_suelo_mayor(partes, 5.0, 9.0)  # (lat, lon) = (5, 9): cae en el chico
    assert 0 < lo < 8 and 0 < la < 10
    assert mgap.punto_del_suelo_mayor(partes, 5.0, 4.0) == (5.0, 4.0)  # ya estaba en el grande: no se mueve
    assert mgap.punto_del_suelo_mayor([], 5.0, 9.0) == (5.0, 9.0)
