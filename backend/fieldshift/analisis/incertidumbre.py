"""Cuánto puede variar cada número: el rango de la erosión y el de las frecuencias («3 de cada 10 años»).

El desafío pide explicar cómo el modelo trata la incertidumbre. Dos fuentes distintas:

1. **Erosión (A = R × K × LS × C × P)**: cada factor sale de un dato con su duda. En vez de inventar una
   precisión que no hay, se hace una simulación de Monte Carlo: se repite la cuenta 4.000 veces moviendo
   cada factor dentro de un rango declarado (abajo) y se informa entre qué valores cae la erosión 8 de
   cada 10 veces (percentiles 10 y 90) y en qué porcentaje de las veces supera la tolerancia del suelo.
   Los rangos son supuestos de trabajo, a revisar con un agrónomo; están escritos acá para que se vean.

   - R (lluvia que erosiona): entre el valor oficial del MGAP y el estimado con la lluvia diaria de NASA
     POWER, y un 10 % más allá de cada uno.
   - K (cuánto se deja arrastrar el suelo): ±20 %. Es el del suelo dominante del grupo CONEAT; dentro de la
     sección hay suelos más y menos erosionables.
   - LS (pendiente y largo): la pendiente sale de un punto de la sección; se mueve ±30 %.
   - C (cobertura): entre 25 % menos y 15 % más. Sale de las tablas del programa Erosión 6.0 del MGAP, pero el
     rastrojo que hay en cada siembra lo simula la app y se redondea al escalón de abajo de la tabla (lo
     conservador): el valor real tiende a ser algo menor que el que se usa, por eso el rango baja más de lo que
     sube.

   Cada factor se mueve con una distribución triangular centrada en el valor que usa la app. Se usa una
   semilla fija: el mismo campo da siempre el mismo rango.

2. **Frecuencias**: «3 de cada 10 años» sale de contar lo que pasó en unos 35 años. Con tan pocos años, el
   número verdadero podría ser otro; el intervalo de Wilson (80 %) dice entre cuánto y cuánto.
"""

from __future__ import annotations

import math

import numpy as np

from .rotaciones import factor_ls

SIMULACIONES = 4000
SEMILLA = 2026
RANGO_K = 0.20
RANGO_PENDIENTE = 0.30
RANGO_C = (0.75, 1.15)
MARGEN_R = 0.10


def _triangular(rng: np.random.Generator, centro: float, bajo: float, alto: float, n: int) -> np.ndarray:
    if alto <= bajo:
        return np.full(n, centro)
    return rng.triangular(bajo, min(max(centro, bajo), alto), alto, n)


def rango_erosion(er: dict, r_alternativas: list[float] | None = None, n: int = SIMULACIONES) -> dict | None:
    """er: el dict "erosion" de una rotación (a_t_ha, tolerancia_t, r, k, ls, c, p, pendiente_pct)."""
    try:
        r, k, ls, c, p = (float(er[x]) for x in ("r", "k", "ls", "c", "p"))
        t = float(er["tolerancia_t"])
    except (KeyError, TypeError, ValueError):
        return None
    if min(r, k, ls, c, p) <= 0:
        return None
    rng = np.random.default_rng(SEMILLA)
    rs = [r] + [float(x) for x in (r_alternativas or []) if x]
    r_bajo, r_alto = min(rs) * (1 - MARGEN_R), max(rs) * (1 + MARGEN_R)
    R = _triangular(rng, r, r_bajo, r_alto, n)
    K = _triangular(rng, k, k * (1 - RANGO_K), k * (1 + RANGO_K), n)
    pend = float(er.get("pendiente_pct") or 0)
    if pend > 0:
        s = _triangular(rng, pend, pend * (1 - RANGO_PENDIENTE), pend * (1 + RANGO_PENDIENTE), n)
        # Con el largo de ladera del lote (antes 100 m fijos): el exponente del largo cambia con la
        # pendiente, así que con otro largo la proporción entre una pendiente y otra no es la misma
        largo = float(er.get("largo_m") or 100)
        base = factor_ls(pend, largo)
        LS = ls * np.array([factor_ls(x, largo) for x in s]) / base
    else:
        LS = np.full(n, ls)
    C = _triangular(rng, c, c * RANGO_C[0], c * RANGO_C[1], n)
    A = R * K * LS * C * p
    p10, p50, p90 = (float(np.percentile(A, q)) for q in (10, 50, 90))
    return {
        "p10": round(p10, 1),
        "p50": round(p50, 1),
        "p90": round(p90, 1),
        "prob_supera_t": round(float(np.mean(A > t)), 2),
        "simulaciones": n,
    }


SUPUESTOS = [
    "R entre el valor del MGAP y el estimado con la lluvia diaria de la NASA, con 10 % de margen.",
    "K ±20 %: es el del suelo dominante; dentro de la sección hay otros.",
    "Pendiente ±30 %: sale de un punto de la sección.",
    "C entre 25 % menos y 15 % más: sale de las tablas del MGAP, pero el rastrojo de cada siembra se simula y se "
    "redondea al escalón de abajo, así que el real tiende a ser algo menor.",
]


def wilson(p: float | None, n: int | None, z: float = 1.2816) -> tuple[float, float] | None:
    """Intervalo de Wilson para una proporción (z = 1,28 → 80 %). Devuelve (bajo, alto) entre 0 y 1."""
    if p is None or not n:
        return None
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    medio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centro - medio), min(1.0, centro + medio)
