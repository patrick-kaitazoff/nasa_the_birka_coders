"""Cómo se juntan los criterios en el puntaje (22-ponderacion.md). Correr desde app/backend: .venv/Scripts/python -m pytest -q"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fieldshift.analisis import rotaciones  # noqa: E402


def test_escalas_van_de_lo_peor_a_lo_mejor_de_uruguay():
    """El 0 y el 100 de cada criterio son lo peor y lo mejor que se ve en el país, no valores a los que no llega nadie."""
    esc = rotaciones._escala
    # seca: 5 años de cada 100 = 100; la mitad de los años = 0; en el medio, lineal
    assert esc(0.05, rotaciones.SECA_PEOR, rotaciones.SECA_MEJOR) == 100
    assert esc(0.50, rotaciones.SECA_PEOR, rotaciones.SECA_MEJOR) == 0
    assert abs(esc(0.275, rotaciones.SECA_PEOR, rotaciones.SECA_MEJOR) - 50) < 1e-9
    # fuera de los extremos queda en 0 o 100
    assert esc(0.70, rotaciones.SECA_PEOR, rotaciones.SECA_MEJOR) == 0
    assert esc(0.01, rotaciones.SECA_PEOR, rotaciones.SECA_MEJOR) == 100
    # ingreso relativo y carbono, en el sentido de «más es mejor»
    assert esc(1.0, rotaciones.INGRESO_REL_PEOR, rotaciones.INGRESO_REL_MEJOR) == 100
    assert esc(0.2, rotaciones.INGRESO_REL_PEOR, rotaciones.INGRESO_REL_MEJOR) == 0
    assert esc(0.85, rotaciones.CARBONO_PEOR, rotaciones.CARBONO_MEJOR) == 100
    assert esc(0.15, rotaciones.CARBONO_PEOR, rotaciones.CARBONO_MEJOR) == 0


def _ev(id_, total, cumple):
    return {"id": id_, "nombre": id_, "tipo": "agrícola", "puntaje_total": total, "puntajes": {},
            "erosion": {"a_t_ha": 1.0 if cumple else 9.0, "tolerancia_t": 5.0, "cumple": cumple}}


def test_la_erosion_cuenta_una_sola_vez():
    """Pasarse de la tolerancia ya no baja el puntaje (la erosión está en el criterio suelo); ordena: las que cumplen
    van primero aunque otra que se pasa puntúe más."""
    from fieldshift.analisis import plan

    pj = {d: 60 for d in rotaciones.DIMENSIONES}
    pri = {d: 3 for d in rotaciones.DIMENSIONES}
    se_pasa = {"puntajes": pj, "erosion": {"cumple": False}}
    cumple = {"puntajes": pj, "erosion": {"cumple": True}}
    assert rotaciones.ponderar(se_pasa, pri) == rotaciones.ponderar(cumple, pri) == 60

    evs = sorted([_ev("alta_se_pasa", 80, False), _ev("baja_cumple", 55, True), _ev("media_cumple", 70, True)],
                 key=plan.orden)
    assert [e["id"] for e in evs] == ["media_cumple", "baja_cumple", "alta_se_pasa"]


def test_lo_de_hoy_que_cumple_gana_a_una_alternativa_que_no():
    """Si ninguna alternativa cumple la tolerancia y lo de hoy sí, se recomienda seguir con lo de hoy aunque la
    alternativa puntúe un poco más (pasó en El Molino al probar el clima futuro: 56,7 contra 56,5)."""
    from fieldshift.analisis import plan

    hoy = _ev("actual", 56.5, True)
    pradera = _ev("pradera", 56.7, False)
    assert plan.elegir_recomendada(hoy, [pradera]) is hoy
    # si la alternativa cumple y puntúa más, gana la alternativa; si empatan, lo de hoy
    otra = _ev("otra", 60, True)
    assert plan.elegir_recomendada(hoy, [otra]) is otra
    assert plan.elegir_recomendada(_ev("actual", 60, True), [otra])["id"] == "actual"
    # lo de hoy que no cumple no frena a nadie; sin alternativas, queda lo de hoy
    assert plan.elegir_recomendada(_ev("actual", 90, False), [pradera]) is pradera
    assert plan.elegir_recomendada(hoy, []) is hoy


def test_escala_por_lote_hace_que_la_prioridad_pese_lo_que_dice():
    """Dos criterios con la misma prioridad: uno cambia poco entre las opciones del lote (agua 54-80) y otro de punta a
    punta (forraje 0-100). Con la escala por lote los dos mueven el total lo mismo; un rango menor que el piso no se
    estira hasta 0-100."""
    base = {d: 50 for d in rotaciones.DIMENSIONES}
    a = {"puntajes": {**base, "agua": 80, "forraje": 0}}
    b = {"puntajes": {**base, "agua": 54, "forraje": 100}}
    c = {"puntajes": {**base, "agua": 54, "forraje": 0}}
    pri = {d: 0 for d in rotaciones.DIMENSIONES} | {"agua": 3, "forraje": 3}
    esc = rotaciones.escala_lote([a, b, c])
    assert esc["agua"] == (54, 26 if 26 >= rotaciones.PISO_LOTE else rotaciones.PISO_LOTE)
    # sin escala por lote, b le gana a a por el forraje; con ella, a y b quedan más cerca
    sin = rotaciones.ponderar(b, pri) - rotaciones.ponderar(a, pri)
    con = rotaciones.ponderar(b, pri, esc) - rotaciones.ponderar(a, pri, esc)
    assert sin == 37 and 0 < con < sin
    # un criterio en que todas las opciones son iguales no suma ni resta
    assert rotaciones.puntajes_en_lote(a, esc)["suelo"] == 0


def test_la_recomendada_es_la_que_gana_mas_seguido_con_pesos_parecidos():
    """La recomendada es «la que gana más seguido». Con los pesos exactos (ingreso 5, suelo 1) gana A por poco,
    pero C es mucho mejor en suelo y apenas peor en ingreso: con pesos parecidos en el mismo orden (ingreso ≥ suelo)
    gana C más seguido."""
    from fieldshift.analisis import plan

    base = {d: 50 for d in rotaciones.DIMENSIONES}
    pri = {d: 0 for d in rotaciones.DIMENSIONES} | {"ingreso": 5, "suelo": 1}

    def op(id_, ingreso, suelo, cumple=True):
        e = {"id": id_, "nombre": id_, "puntajes": {**base, "ingreso": ingreso, "suelo": suelo},
             "erosion": {"cumple": cumple}}
        e["puntaje_total"] = rotaciones.ponderar(e, pri)
        return e

    a, c = op("A", 90, 40), op("C", 80, 80)
    assert a["puntaje_total"] > c["puntaje_total"]
    rec, ac = plan.recomendar(None, [a, c], pri, None, "x")
    assert rec is c and ac["C"] > ac["A"] and ac["A"] + ac["C"] == 100
    # siempre igual para el mismo lote (semilla fija)
    assert plan.recomendar(None, [a, c], pri, None, "x")[1] == ac
    # si ninguna alternativa cumple la tolerancia, mandan las reglas de siempre (lo de hoy que cumple)
    hoy = _ev("actual", 40, True) | {"puntajes": {**base}}
    rec, ac = plan.recomendar(hoy, [op("P", 90, 90, cumple=False)], pri, None, "x")
    assert rec is hoy and ac is None
    # lo de hoy con un cultivo que el productor no quiere no compite
    rec, _ = plan.recomendar(op("actual", 100, 100) | {"tiene_excluidos": True}, [a, c], pri, None, "x")
    assert rec["id"] == "C"
