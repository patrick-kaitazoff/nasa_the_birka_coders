"""Pruebas del camino del agua y clasificación de escurrimiento en el relieve."""
import numpy as np
import pytest
from fieldshift.analisis import relieve
from fieldshift.fuentes import relieve as fuente


def test_camino_del_agua_y_clases_ladera_en_v(monkeypatch):
    """Verifica que una ladera en V concentre el escurrimiento y clasifique correctamente:
    0: ladera normal (poca cuenca aportante)
    1: bajo / acá se junta el agua (pendiente suave y cuenca aportante moderada)
    2: vía de agua (cuenca aportante acumulada >= CAUCE_HA = 5 ha)
    """
    filas, cols, px = 50, 15, 30.0
    x = np.arange(cols)
    # Valle en V: columnas 0 a 6 caen hacia el centro (columna 7) y 8 a 14 caen hacia el centro
    lateral = np.abs(x - 7) * px * 0.06
    # Pendiente suave a lo largo del cauce de norte a sur (1 %)
    longitudinal = np.arange(filas)[::-1, None] * px * 0.01
    z = 100.0 + lateral + longitudinal

    def mosaico_falso(o, s, e, n, z_=13):
        return {
            "elev": z,
            "oeste": -56.6,
            "este": -56.58,
            "norte": -33.0,
            "sur": -33.011,
            "px_m": px,
            "fuente": "prueba_v",
        }

    monkeypatch.setattr(fuente, "mosaico", mosaico_falso)

    cuadro = {
        "type": "Polygon",
        "coordinates": [[
            [-56.598, -33.001],
            [-56.582, -33.001],
            [-56.582, -33.010],
            [-56.598, -33.010],
            [-56.598, -33.001],
        ]],
    }
    secs = [{"id": "valle", "nombre": "Valle en V", "geometria": cuadro, "k": 0.3, "t": 7, "c_actual": 0.2}]

    res = relieve.analizar(cuadro, secs, 500)
    g = res["grilla"]
    agua = np.array(g["agua"])

    # 1. Dimensiones correctas
    assert agua.shape == (g["filas"], g["cols"])

    # 2. Las tres clases deben estar presentes en la grilla del valle
    clases = set(np.unique(agua).tolist())
    assert clases == {0, 1, 2}, f"Se esperaban clases 0, 1 y 2, se encontraron: {clases}"

    # 3. Las laderas laterales (lejos del centro) deben ser clase 0 (nada)
    assert agua[10, 0] == 0
    assert agua[10, 14] == 0
    assert (agua[:, 0] == 0).all()
    assert (agua[:, 14] == 0).all()

    # 4. En el cauce (columna 7):
    # - Hacia la cabecera (donde junta agua pero menos de 5 ha): clase 1
    # - Hacia abajo (donde acumuló más de 5 ha de cuenca): clase 2
    assert 1 in agua[:, 7]
    assert 2 in agua[:, 7]

    # La vía de agua (2) debe estar aguas abajo de los primeros bajos (1)
    filas_clase_1 = np.where(agua[:, 7] == 1)[0]
    filas_clase_2 = np.where(agua[:, 7] == 2)[0]
    assert len(filas_clase_1) > 0 and len(filas_clase_2) > 0
    assert filas_clase_2.max() > filas_clase_1.min()

    # 5. La sección debe reportar hectáreas en vías de agua y en bajos
    sec = res["secciones"][0]
    assert "ha_via_agua" in sec and sec["ha_via_agua"] > 0
    assert "ha_bajos" in sec and sec["ha_bajos"] > 0
