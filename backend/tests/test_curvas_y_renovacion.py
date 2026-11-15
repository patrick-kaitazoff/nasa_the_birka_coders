"""Curvas de nivel como opción y cuándo se siembra o renueva la pastura en el plan."""

from fieldshift.analisis import plan
from fieldshift.analisis import rotaciones as rot_mod
from fieldshift.analisis.plan import etiquetas_temporadas, siembras_pastura


def test_factor_p_de_curvas_segun_pendiente():
    assert rot_mod.p_curvas(1.5) == 0.6
    assert rot_mod.p_curvas(4.3) == 0.5
    assert rot_mod.p_curvas(10) == 0.6
    assert rot_mod.p_curvas(30) == 1.0
    assert rot_mod.p_curvas(None) == 0.5  # sin dato se toma 3 %


def test_pradera_permanente_muestra_su_renovacion():
    rot = rot_mod.ROTACIONES["pradera_permanente"]
    temporadas = etiquetas_temporadas(plan.HORIZONTE_ANIOS)
    marcas, texto = siembras_pastura(rot, 0, temporadas)
    assert marcas.count("renovación") >= 1
    assert texto and texto.startswith("se renueva en el otoño de ")
    # en un invierno, nunca en un verano
    assert all(temporadas[i]["tipo"] == "invierno" for i, m in enumerate(marcas) if m)


def test_rotacion_sin_pasturas_no_marca_nada():
    rot = rot_mod.ROTACIONES["maiz_soja_cobertura"]
    marcas, texto = siembras_pastura(rot, 0, etiquetas_temporadas(plan.HORIZONTE_ANIOS))
    assert not any(marcas) and texto is None


def test_agricola_pastoril_marca_la_siembra_de_la_pradera():
    rot = rot_mod.ROTACIONES["agricola_pastoril"]
    marcas, texto = siembras_pastura(rot, 0, etiquetas_temporadas(plan.HORIZONTE_ANIOS))
    assert "siembra" in marcas and texto.startswith("se siembra en el otoño de ")


def test_ningun_dia_queda_sin_erosion_despues_de_una_pastura():
    # Al romper o renovar una pastura quedaban 31 a 45 días con C = 0 (sin erosión)
    for rot in rot_mod.ROTACIONES.values():
        n = len(rot.anios)
        c_diario, _ = rot_mod.c_diario_oficial(rot)
        estabilizado = c_diario[365 * n : 365 * n * 2]
        assert (estabilizado > 0).all(), rot.id


def test_rastrojo_del_girasol_va_por_el_residuo_a_la_siembra():
    # En Erosión 6.0 la fila del período 4 del girasol (y de los cereales de invierno) va por el residuo
    # que había al sembrar, no por el rastrojo que deja el cultivo (antes el girasol caía siempre en 0,36)
    tabla = rot_mod._tablas_erosion6()["rps"]["girasol"]
    rot = rot_mod.ROTACIONES["girasol_trigo_soja"]
    n = len(rot.anios)
    c_diario, _ = rot_mod.c_diario_oficial(rot)
    girasol = rot_mod.CULTIVOS["girasol"]
    s = 365 * n + rot_mod._offset(girasol)  # segundo ciclo, primer año (cobertura / girasol)
    h = s + girasol.ciclo
    paso = next(k for k, v in tabla["p1"].items() if abs(v - c_diario[s + 1]) < 1e-9)
    assert abs(c_diario[h + 1] - tabla["p4"][paso]) < 1e-9
