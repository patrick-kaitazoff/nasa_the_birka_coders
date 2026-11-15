"""Pruebas del análisis histórico («Tu campo, temporada por temporada»)."""

import pytest
from fastapi.testclient import TestClient

from fieldshift.analisis import clima, historia
from fieldshift.analisis.cultivos import CULTIVOS
from fieldshift.api import app
from fieldshift.fuentes import modis_historia


def _serie_falsa() -> clima.Serie:
    """Serie climática sintética con un año de sequía severa en 2022/23 (solo para tests de software)."""
    import datetime as dt
    import numpy as np

    fechas = []
    d = dt.date(2000, 1, 1)
    fin = dt.date(2025, 12, 31)
    while d <= fin:
        fechas.append(d)
        d += dt.timedelta(days=1)

    n = len(fechas)
    anio = np.array([f.year for f in fechas])
    mes = np.array([f.month for f in fechas])
    doy = np.array([f.timetuple().tm_yday for f in fechas])

    tmax = np.full(n, 25.0)
    tmin = np.full(n, 12.0)
    lluvia = np.full(n, 3.5)  # ~1.277 mm anuales normales
    rad = np.full(n, 18.0)
    hr = np.full(n, 70.0)
    viento = np.full(n, 2.5)
    gwet = np.full(n, 0.70)
    et0 = np.full(n, 4.0)

    # Seca extrema en verano 2022/23 (diciembre 2022 a marzo 2023)
    m_seca = ((anio == 2022) & (mes == 12)) | ((anio == 2023) & (mes <= 3))
    lluvia[m_seca] = 0.01  # casi 0 mm
    tmax[m_seca] = 36.0  # calor extremo > 35°C
    gwet[m_seca] = 0.15

    return clima.Serie(
        fechas=fechas,
        anio=anio,
        mes=mes,
        doy=doy,
        tmax=tmax,
        tmin=tmin,
        lluvia=lluvia,
        rad=rad,
        hr=hr,
        viento=viento,
        gwet=gwet,
        et0=et0,
        elevacion=100.0,
        lat=-33.10,
    )


def _serie_modis_prueba() -> list[dict]:
    """Serie fija de NDVI de prueba exclusivamente para tests unitarios (rotulada como prueba de software)."""
    puntos = []
    for y in range(2000, 2026):
        for m in (12, 1, 2, 6, 7, 8):
            # En verano 2022/23 simulamos estrés para probar la lógica de coincidencia del modelo
            ndvi = 0.45 if ((y == 2022 and m == 12) or (y == 2023 and m in (1, 2))) else 0.75
            puntos.append({"fecha": f"{y}-{m:02d}-15", "ndvi": ndvi})
    return puntos


def test_erosividad_temporada():
    s = _serie_falsa()
    inv = clima.erosividad_temporada(s, 2021, "invierno")
    assert inv["lluvia_mm"] > 0
    assert inv["r_temporada"] >= 0

    ver = clima.erosividad_temporada(s, 2021, "verano")
    assert ver["lluvia_mm"] > 0


def test_interpretar_historia():
    puntos = _serie_modis_prueba()
    res = modis_historia.interpretar_historia(puntos)
    assert res["total_temporadas"] > 0
    assert "medianas" in res
    assert res["medianas"]["verano"] > 0.5


def test_analisis_historia_caso_seca_2022_23():
    s = _serie_falsa()
    sec = {
        "id": "s1",
        "nombre": "La Loma",
        "area_ha": 100.0,
        "grupo_coneat": "1.20",
        "historial": [
            {"anio": 2022, "invierno": "barbecho", "verano": "soja"},
            {"anio": 2023, "invierno": "barbecho", "verano": "soja"},
        ],
    }

    # Se inyecta la serie fija de prueba unitaria explícitamente
    res = historia.analizar_historia_seccion(sec, s, agua_util_mm=120.0, serie_modis=_serie_modis_prueba())
    assert res["seccion_id"] == "s1"
    assert res["total_temporadas"] > 20
    assert res["hay_satelite"] is True

    # Buscar la temporada verano 2022/23
    t_22_23 = next((t for t in res["temporadas"] if t["temporada"] == "verano 2022/23"), None)
    assert t_22_23 is not None
    assert t_22_23["es_estrella"] is True
    # En verano 2022/23 no llovió en la serie sintética de prueba
    assert t_22_23["clima"]["lluvia_mm"] < 10.0
    assert t_22_23["clima"]["dias_calor"] > 0
    # Validación biofísica: el modelo detectó la seca
    assert t_22_23["cultivo_real"]["modelo_dijo_seca"] is True
    assert t_22_23["cultivo_real"]["codigo"] == "soja"

    # Verificar que existe validación con coincidencia y kappa
    val = res["validacion"]
    assert val["total_evaluadas"] > 0
    assert "coincidencia_pct" in val
    assert "frase" in val


def test_correccion_usuario_gana():
    s = _serie_falsa()
    sec = {
        "id": "s1",
        "nombre": "Potrero 1",
        "area_ha": 50.0,
    }
    # Usuario corrige que en invierno 2021 sembró colza en vez de barbecho detectado
    res = historia.analizar_historia_seccion(
        sec, s, correcciones_usuario={"invierno 2021": "colza"}, serie_modis=_serie_modis_prueba()
    )
    t_inv_21 = next((t for t in res["temporadas"] if t["temporada"] == "invierno 2021"), None)
    assert t_inv_21 is not None
    assert t_inv_21["cultivo_real"]["codigo"] == "colza"
    assert t_inv_21["cultivo_real"]["origen"] == "corregido"


def test_con_este_plan_usa_los_cultivos_del_plan():
    """«Con este plan» repite los cultivos del plan de la sección, no la rotación de referencia."""
    s = _serie_falsa()
    sec = {"id": "s1", "nombre": "Potrero 1", "area_ha": 50.0}
    ciclo = [("verano", "pradera"), ("invierno", "pradera")]
    res = historia.analizar_historia_seccion(sec, s, serie_modis=_serie_modis_prueba(), ciclo_plan=ciclo)
    assert res["temporadas"]
    assert {t["propuesta"]["codigo"] for t in res["temporadas"]} == {"pradera"}

    ciclo2 = [("invierno", "trigo"), ("verano", "soja2"), ("invierno", "cobertura"), ("verano", "maiz")]
    res2 = historia.analizar_historia_seccion(sec, s, serie_modis=_serie_modis_prueba(), ciclo_plan=ciclo2)
    por_temp = {t["temporada"]: t["propuesta"]["codigo"] for t in res2["temporadas"]}
    # 2000 y 2001 alternan los dos cultivos de cada estación del plan
    assert por_temp.get("invierno 2000") == "trigo" and por_temp.get("invierno 2001") == "cobertura"
    assert por_temp.get("verano 2000/01") == "soja2" and por_temp.get("verano 2001/02") == "maiz"


def test_endpoint_api_historia_sin_credenciales_earth_engine(monkeypatch):
    """Sin credenciales de Earth Engine, debe contestar enseguida con solo_clima y sin llamar a AppEEARS."""
    from fieldshift import cache
    monkeypatch.setenv("DESACTIVAR_EE", "1")
    monkeypatch.setattr(modis_historia, "_cargar_sa_info", lambda: None)
    monkeypatch.setattr(modis_historia, "_consultar_punto_ee", lambda *args, **kwargs: [])
    # Forzar que la caché no devuelva datos previos para esta prueba
    orig_cache_leer = cache.leer
    monkeypatch.setattr(cache, "leer", lambda tipo, clave, max_dias=90: None if tipo == "modis_historia" else orig_cache_leer(tipo, clave, max_dias))

    client = TestClient(app)
    payload = {
        "campo": {
            "id": "campo-sin-ee",
            "nombre": "Campo sin satélite",
            "ubicacion": {"lat": -33.10, "lon": -56.15},
            "area_ha": 150.0,
            "secciones": [
                {
                    "id": "s1",
                    "nombre": "Potrero A",
                    "area_ha": 150.0,
                    "grupo_coneat": "10.8a",
                }
            ],
        }
    }
    r = client.post("/api/historia", json=payload)
    assert r.status_code == 200
    js = r.json()
    assert js["estado_satelite"] == "solo_clima"
    assert "clima" in js["mensaje_satelite"]
    assert js["caso_estrella"] is None
    assert js["resumen_global"]["total_evaluadas"] == 0
    assert len(js["secciones"]) == 1
    sec = js["secciones"][0]
    assert sec["hay_satelite"] is False
    assert sec["validacion"]["total_evaluadas"] == 0
    # Clima real de NASA POWER sí está presente
    assert len(sec["temporadas"]) > 20
    assert sec["temporadas"][0]["clima"]["lluvia_mm"] is not None
    assert sec["temporadas"][0]["satelite"]["ndvi_max"] is None


def test_historia_earth_engine_simulado(monkeypatch):
    """Con Earth Engine simulado devuelve la serie completa, calcula la fenología y arma el caso estrella."""
    monkeypatch.delenv("DESACTIVAR_EE", raising=False)
    serie_mock = _serie_modis_prueba()
    monkeypatch.setattr(modis_historia, "_consultar_punto_ee", lambda lon, lat, hasta=None: serie_mock)

    client = TestClient(app)
    payload = {
        "campo": {
            "id": "campo-ee-mock",
            "nombre": "Campo con EE",
            "ubicacion": {"lat": -33.10, "lon": -56.15},
            "area_ha": 120.0,
            "secciones": [
                {
                    "id": "s1",
                    "nombre": "Potrero EE",
                    "area_ha": 120.0,
                    "grupo_coneat": "10.8a",
                }
            ],
        }
    }
    r = client.post("/api/historia", json=payload)
    assert r.status_code == 200
    js = r.json()
    assert js["estado_satelite"] == "listo"
    assert "Google Earth Engine" in js["mensaje_satelite"]
    sec = js["secciones"][0]
    assert sec["hay_satelite"] is True
    # Verdor satelital presente
    assert sec["temporadas"][0]["satelite"]["ndvi_max"] is not None
    # Caso estrella 2022/23 detectado
    assert js["caso_estrella"] is not None
    assert js["caso_estrella"]["temporada"] == "verano 2022/23"


def test_historia_cache_evita_volver_a_pedir_ee(monkeypatch):
    """Si los datos ya están en caché (90 días), no vuelve a consultar Earth Engine."""
    from fieldshift import cache

    lat, lon = -33.2222, -56.3333
    clave = modis_historia._clave(lat, lon)
    datos_mock = {
        "fuente": "NASA MODIS MOD13Q1 v061 vía Google Earth Engine",
        "lat": lat,
        "lon": lon,
        "serie": _serie_modis_prueba(),
        "estado": "listo",
        **modis_historia.interpretar_historia(_serie_modis_prueba()),
    }
    cache.guardar("modis_historia", clave, datos_mock)

    llamadas_ee = []
    def _mock_consulta(*args, **kwargs):
        llamadas_ee.append(args)
        return []

    monkeypatch.setattr(modis_historia, "_consultar_punto_ee", _mock_consulta)

    res = modis_historia.estado_campo([("sec_cache", lat, lon)])
    assert res["estado"] == "listo"
    assert "caché" in res["fuente"]
    assert len(llamadas_ee) == 0  # No debió consultar a Earth Engine
