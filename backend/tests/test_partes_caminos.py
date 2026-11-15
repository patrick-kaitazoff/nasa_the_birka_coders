"""Pruebas para la detección y corte de caminos (A), regularización sin muescas (C) y cierre total (E)."""

import math
from shapely.geometry import box, Polygon, LineString, Point, mapping
from shapely.ops import unary_union

from fieldshift.fuentes import caminos
from fieldshift.analisis import partes


def test_cortar_por_calles_sin_calles():
    campo = box(-56.0, -34.5, -55.997, -34.497)
    m2 = 10000000000
    util, mascara, info = caminos.cortar_por_calles(campo, m2)
    assert util.equals(campo)
    assert mascara is None
    assert info == []


def test_regularizar_partes_elimina_muescas_y_cierra():
    """Comprueba que dos partes compartan una frontera regularizada sin huecos ni muescas."""
    campo = box(-56.002, -34.502, -56.000, -34.498)
    m2 = 10000000000

    # Simular dos partes con escalón/muesca en el medio
    corte_y = -34.500
    p1 = box(-56.002, -34.502, -56.000, corte_y)
    p2 = box(-56.002, corte_y, -56.000, -34.498)

    partes_in = [{"geo": p1, "clase": 0}, {"geo": p2, "clase": 1}]
    reg = partes._regularizar_partes(campo, partes_in, m2, tol=0.0002)

    assert len(reg) == 2
    # El área total debe ser exactamente el área de campo (cero huecos)
    area_total = sum(p["geo"].area for p in reg)
    assert math.isclose(area_total, campo.area, rel_tol=1e-5)
    # No deben superponerse
    assert reg[0]["geo"].intersection(reg[1]["geo"]).area < 1e-9


def test_ajustar_circulo_pivot():
    campo = box(0, 0, 10, 10)
    m2 = 10000000000
    # Círculo perfecto
    circ = Point(5, 5).buffer(2, resolution=64)
    geo, es_pivot = partes._ajustar_circulo(circ, m2, campo)
    assert es_pivot is True
    assert geo.geom_type == "Polygon"
