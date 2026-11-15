"""Relieve dentro de cada sección: pendiente y erosión cuadrado por cuadrado (SRTM de la NASA, 30 m).

Hasta ahora la erosión de una sección usaba la pendiente del MGAP en un solo punto. Con el relieve de
SRTM se calcula la pendiente de cada cuadrado del campo y, con la misma ecuación del Plan de Uso
(A = R × K × LS × C × P), la erosión de cada cuadrado: así aparecen las **zonas** que más se lavan dentro
de una sección (la ladera, la cabecera de una cañada), que el promedio esconde. R, K, C y P son los de
la sección (los mismos que usa la comparación de rotaciones); lo único que cambia de un cuadrado a otro
es la pendiente.

Pasos: 1) suavizado de 3 × 3 de la elevación (SRTM tiene ruido de unos metros, que en un llano se
convierte en pendientes falsas); 2) pendiente con el método de Horn (1981); 3) largo de ladera de cada
cuadrado siguiendo el camino del agua (abajo); 4) LS de Wischmeier y Smith (el mismo de
rotaciones.factor_ls); 5) A por cuadrado con la rotación actual y con la del plan.

Largo de ladera. El agua de cada cuadrado baja al vecino más empinado de los ocho (D8,
O'Callaghan y Mark 1984). Recorriendo el campo de lo más alto a lo más bajo, cada cuadrado hereda el camino más
largo que le llega desde arriba y le suma su paso. El camino se corta, como en el programa de RUSLE de
Van Remortel y otros (2001, 2004) sobre el método de Hickey (2000): a) donde la pendiente cae a menos de la mitad
(menos del 70 % si la de arriba pasa el 5 %), porque ahí el agua frena y deja el suelo; b) donde el agua de más de
5 ha ya corre junta (una cañada: deja de ser ladera); c) a los 300 m, el largo más grande para el que se armó
la ecuación. Sirve en cualquier país que cubra SRTM (entre 60° N y 56° S). Si el productor cargó su largo de
pendiente, manda el suyo.

- La pendiente para decidir el corte se mide sobre el relieve suavizado tres veces (~100 m): SRTM viene en metros
  enteros y, cuadrado a cuadrado, la pendiente salta tanto que el camino se cortaba cada 30 m.
- El largo de un lote es el de sus laderas enteras: cada cuadrado toma el largo del camino en el punto donde ese
  camino termina, y el lote, la mediana. En el campo de ejemplo da de 111 a 143 m según el lote.
- En el 3D, cada cuadrado usa su tramo de ladera con la fórmula de Foster y Wischmeier (1974). El promedio de un
  lote queda cerca del de la ecuación con el largo del lote (en el ejemplo, de 10 a 18 % menos, porque no todas
  las laderas de un lote son igual de largas).

Límites: la pendiente de SRTM en llanos es menos confiable que en lomadas; con cuadrados de ~16 m (30 m de dato),
el camino del agua no ve zanjas, caminos ni terrazas que lo cortan antes. En llanos el ruido de metros del radar
puede generar caminos de drenaje o bajos artificiales.

Camino del agua y vías de escurrimiento: el algoritmo D8 acumula la superficie aportante que drena a cada
cuadrado. Con eso se clasifican las zonas del campo: 0 ladera/loma normal, 1 "acá se junta el agua" (bajo: pendiente
baja y al menos 0,5 ha aportantes, o índice topográfico TWI ln(a / tan β) alto), 2 "vía de agua" (cañada o cauce
con más de 5 ha aportantes juntas). Ayuda al productor a ver por dónde baja el agua cuando llueve fuerte y dónde
conviene mantener cobertura permanente o vías empastadas.
"""

from __future__ import annotations

import math

import numpy as np
from shapely import contains_xy
from shapely.geometry import shape

from ..fuentes import relieve as fuente

MAX_LADO_3D = 180  # cuadrados por lado que se mandan al visor 3D


def _suavizar(z: np.ndarray) -> np.ndarray:
    p = np.pad(z, 1, mode="edge")
    return sum(p[i:i + z.shape[0], j:j + z.shape[1]] for i in range(3) for j in range(3)) / 9


def pendiente_pct(z: np.ndarray, px_m: float) -> np.ndarray:
    """Horn (1981), en %."""
    p = np.pad(z, 1, mode="edge")
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * px_m)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * px_m)
    return 100 * np.hypot(dzdx, dzdy)


def ls_grilla(s_pct: np.ndarray, largo_m: float) -> np.ndarray:
    """Wischmeier y Smith (1978), igual que rotaciones.factor_ls pero para toda la grilla."""
    s = np.maximum(s_pct, 0.1)
    m = np.where(s >= 5, 0.5, np.where(s >= 3.5, 0.4, np.where(s >= 1, 0.3, 0.2)))
    th = np.arctan(s / 100)
    return (largo_m / 22.13) ** m * (65.41 * np.sin(th) ** 2 + 4.56 * np.sin(th) + 0.065)


LARGO_TOPE_M = 300.0       # largo más grande para el que se armó la USLE (~1000 pies)
CAUCE_HA = 5.0             # con más agua junta que esto, ya es una cañada y no una ladera
LARGO_LOTE_MIN_M = 20.0    # menos que esto, en un lote, es ruido de SRTM en un llano
_VECINOS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def largo_ladera_grilla(z: np.ndarray, s_pct: np.ndarray, px_m: float) -> dict[str, np.ndarray]:
    """Por cuadrado: "largo", el camino del agua desde arriba hasta su centro; "paso", lo que recorre adentro del
    cuadrado; "ladera", el largo entero de la ladera a la que pertenece (donde termina su camino). `s_pct`: la
    pendiente con la que se decide el corte."""
    f, c = z.shape
    n = f * c
    pz = np.pad(z, 1, constant_values=np.inf)  # afuera de la grilla nunca es «más abajo»
    dist = np.array([px_m * (math.sqrt(2) if a and b else 1.0) for a, b in _VECINOS])
    caida = np.stack([(z - pz[1 + a:1 + a + f, 1 + b:1 + b + c]) / d for (a, b), d in zip(_VECINOS, dist)])
    k = np.argmax(caida, axis=0)
    baja = np.max(caida, axis=0) > 0
    filas, cols = np.indices(z.shape)
    da = np.array([v[0] for v in _VECINOS])[k]
    db = np.array([v[1] for v in _VECINOS])[k]
    destino = np.where(baja, (filas + da) * c + (cols + db), -1).ravel().tolist()
    paso = dist[k].ravel().tolist()
    pend = np.asarray(s_pct, dtype=float).ravel().tolist()
    largo = [0.5 * x for x in paso]  # el que arranca en una loma recorre medio cuadrado
    agua = [1.0] * n
    sigue = [False] * n
    cauce = CAUCE_HA * 10000 / px_m ** 2  # en cuadrados
    orden = np.argsort(-z.ravel(), kind="stable").tolist()
    for i in orden:
        r = destino[i]
        if r < 0:
            continue
        agua[r] += agua[i]
        if agua[i] > cauce:
            continue  # el agua ya corre junta: la ladera terminó acá
        if pend[r] < (0.7 if pend[i] >= 5 else 0.5) * pend[i]:
            continue  # la pendiente cae: el agua frena y deja el suelo
        sigue[i] = True
        nuevo = largo[i] + paso[i]
        if nuevo > largo[r]:
            largo[r] = nuevo
    fin = list(range(n))  # dónde termina el camino de cada cuadrado, de lo más bajo a lo más alto
    for i in reversed(orden):
        if sigue[i]:
            fin[i] = fin[destino[i]]
    largo_a = np.minimum(np.array(largo), LARGO_TOPE_M)
    return {"largo": largo_a.reshape(z.shape), "paso": np.array(paso).reshape(z.shape),
            "ladera": largo_a[np.array(fin)].reshape(z.shape),
            "agua": np.array(agua).reshape(z.shape)}


def ls_segmentos(s_pct: np.ndarray, largo: np.ndarray, paso: np.ndarray) -> np.ndarray:
    """LS de cada cuadrado con su tramo de ladera (Foster y Wischmeier 1974): L = (λ_sal^(m+1) − λ_ent^(m+1)) /
    ((λ_sal − λ_ent) · 22,13^m). El promedio sobre una ladera entera da (λ/22,13)^m, la L de la ecuación del lote."""
    s = np.maximum(s_pct, 0.1)
    m = np.where(s >= 5, 0.5, np.where(s >= 3.5, 0.4, np.where(s >= 1, 0.3, 0.2)))
    ent = np.maximum(largo - paso / 2, 0)
    sal = np.minimum(largo + paso / 2, LARGO_TOPE_M + paso / 2)
    l_fac = (sal ** (m + 1) - ent ** (m + 1)) / (np.maximum(sal - ent, 1e-6) * 22.13 ** m)
    th = np.arctan(s / 100)
    return l_fac * (65.41 * np.sin(th) ** 2 + 4.56 * np.sin(th) + 0.065)


def _grilla(contorno: dict) -> dict:
    """SRTM del campo con un poco de alrededor, suavizado, con su pendiente y su largo de ladera por cuadrado."""
    campo = shape(contorno)
    x0, y0, x1, y1 = campo.bounds
    mx, my = (x1 - x0) * 0.15, (y1 - y0) * 0.15  # un poco de alrededor (para el 3D y para que el agua llegue de afuera)
    m = fuente.mosaico(x0 - mx, y0 - my, x1 + mx, y1 + my)
    z = m["elev"]
    filas, cols = z.shape
    lon = m["oeste"] + (np.arange(cols) + 0.5) / cols * (m["este"] - m["oeste"])
    lat = m["norte"] - (np.arange(filas) + 0.5) / filas * (m["norte"] - m["sur"])
    LON, LAT = np.meshgrid(lon, lat)
    zs = _suavizar(z)
    s = pendiente_pct(zs, m["px_m"])
    s_corte = pendiente_pct(_suavizar(_suavizar(zs)), m["px_m"])
    return {"m": m, "z": z, "s": s, **largo_ladera_grilla(zs, s_corte, m["px_m"]), "LON": LON, "LAT": LAT,
            "dentro": contains_xy(campo, LON, LAT)}


def largo_lote(laderas: np.ndarray) -> float:
    """El largo de un lote para la ecuación del Plan de Uso: la mediana del largo de la ladera de cada cuadrado."""
    return float(min(LARGO_TOPE_M, max(LARGO_LOTE_MIN_M, np.median(laderas))))


def ladera_por_seccion(contorno: dict, secciones: list[dict]) -> dict[str, dict]:
    """Para el análisis: {id de la sección: {"largo_m", "pendiente_media"}} sacados de SRTM."""
    g = _grilla(contorno)
    salida = {}
    for sec in secciones:
        msk = contains_xy(shape(sec["geometria"]), g["LON"], g["LAT"]) & g["dentro"]
        if msk.sum() < 3:
            continue
        salida[sec.get("id")] = {
            "largo_m": round(largo_lote(g["ladera"][msk])),
            "pendiente_media": round(float(g["s"][msk].mean()), 2),
        }
    return salida


def _reducir(a: np.ndarray, paso: int) -> np.ndarray:
    return a[::paso, ::paso]


def analizar(contorno: dict, secciones: list[dict], r: float, p: float = 1.0, largo_m: float | None = None) -> dict:
    """secciones: [{"id", "nombre", "geometria", "k", "t", "c_actual", "c_plan"}]. `c_plan` es opcional.

    La erosión de cada cuadrado es proporcional al factor C del lote (A = R · K · LS · C · P). Se manda
    también la parte que no depende de la rotación (R · K · LS · P, «base») por cuadrado y sus percentiles por
    sección: el navegador calcula la erosión de lo que elija el productor sin volver a pedir el relieve, que antes
    se bajaba entero (~480 KB y el cálculo de SRTM) con cada elección."""
    gr = _grilla(contorno)
    m, z, s, LON, LAT, dentro = gr["m"], gr["z"], gr["s"], gr["LON"], gr["LAT"], gr["dentro"]
    filas, cols = z.shape
    # Sin un largo cargado por el productor, cada cuadrado usa su tramo de ladera (el camino del agua en SRTM)
    ls = ls_grilla(s, float(largo_m)) if largo_m else ls_segmentos(s, gr["largo"], gr["paso"])

    seccion = np.full(z.shape, -1, dtype=int)
    ero_actual = np.full(z.shape, np.nan)
    ero_plan = np.full(z.shape, np.nan)
    ero_base = np.full(z.shape, np.nan)
    tol = np.full(z.shape, np.nan)
    hay_plan = any(sec.get("c_plan") is not None for sec in secciones)
    por_seccion = []
    area_px_ha = m["px_m"] ** 2 / 10000.0

    # Por dónde corre el agua (D8 acumulado e índice topográfico de humedad)
    drenaje_ha = gr["agua"] * area_px_ha
    a_especifica = gr["agua"] * m["px_m"]
    tan_beta = np.maximum(s / 100.0, 0.005)
    twi = np.log(a_especifica / tan_beta)
    BAJO_MIN_HA = 0.5
    BAJO_PEND_MAX = 3.0
    es_cauce = drenaje_ha >= CAUCE_HA
    es_bajo = (~es_cauce) & (drenaje_ha >= BAJO_MIN_HA) & ((s <= BAJO_PEND_MAX) | (twi >= 8.0))
    clase_agua = np.zeros(z.shape, dtype=int)
    clase_agua[es_bajo] = 1
    clase_agua[es_cauce] = 2

    for i, sec in enumerate(secciones):
        g = shape(sec["geometria"])
        msk = contains_xy(g, LON, LAT) & dentro
        if not msk.any():
            continue
        seccion[msk] = i
        k, t = float(sec.get("k") or 0.3), float(sec.get("t") or 7)
        ca, cp = sec.get("c_actual"), sec.get("c_plan")
        tol[msk] = t
        base = r * k * ls[msk] * p
        ero_base[msk] = base
        fila: dict = {
            "id": sec.get("id"), "nombre": sec.get("nombre"), "ha": round(float(msk.sum()) * area_px_ha, 1),
            "pendiente_media": round(float(s[msk].mean()), 1),
            "pendiente_p90": round(float(np.percentile(s[msk], 90)), 1),
            "pct_mas_de_4": round(100 * float((s[msk] > 4).mean())),
            "largo_ladera_m": round(float(largo_m)) if largo_m else round(largo_lote(gr["ladera"][msk])),
            "elev_min": round(float(z[msk].min())), "elev_max": round(float(z[msk].max())),
            "ha_via_agua": round(float((msk & es_cauce).sum()) * area_px_ha, 1),
            "ha_bajos": round(float((msk & es_bajo).sum()) * area_px_ha, 1),
            "indice": i, "t": t,
            "base_media": round(float(base.mean()), 3),
            "base_cuantiles": [round(float(v), 3) for v in np.percentile(base, np.arange(101))],
        }
        for nombre, c, destino in (("actual", ca, ero_actual), ("plan", cp, ero_plan)):
            if c is None:
                continue
            a = r * k * ls[msk] * float(c) * p
            destino[msk] = a
            fila[f"erosion_{nombre}"] = {
                "media": round(float(a.mean()), 1),
                "pct_supera_t": round(100 * float((a > t).mean())),
                "ha_supera_t": round(float((a > t).sum()) * area_px_ha, 1),
            }
        por_seccion.append(fila)

    paso = max(1, int(np.ceil(max(filas, cols) / MAX_LADO_3D)))
    r2 = lambda a, d=1: np.round(_reducir(a, paso), d)  # noqa: E731

    def lista(a: np.ndarray) -> list:
        return [[None if (isinstance(v, float) and np.isnan(v)) else v for v in fila] for fila in a.tolist()]

    zz = _reducir(z, paso)
    return {
        "fuente": m["fuente"],
        "bordes": {"oeste": m["oeste"], "este": m["este"], "norte": m["norte"], "sur": m["sur"]},
        "px_m": round(m["px_m"] * paso, 1),
        "px_m_original": round(m["px_m"], 1),
        "elev_min": round(float(np.nanmin(z))), "elev_max": round(float(np.nanmax(z))),
        "secciones": por_seccion,
        "grilla": {
            "filas": zz.shape[0], "cols": zz.shape[1],
            "elev": lista(np.round(zz, 1)),
            "pendiente": lista(r2(s)),
            "agua": _reducir(clase_agua, paso).tolist(),
            "drenaje_ha": lista(r2(drenaje_ha, 2)),
            "dentro": _reducir(dentro, paso).astype(int).tolist(),
            "seccion": _reducir(seccion, paso).tolist(),
            "erosion_actual": lista(r2(ero_actual)),
            **({"erosion_plan": lista(r2(ero_plan))} if hay_plan else {}),
            "erosion_base": lista(r2(ero_base, 2)),
            "tolerancia": lista(r2(tol)),
        },
        "metodo": "Pendiente de Horn sobre SRTM suavizado (3 × 3); camino del agua y acumulación de cuenca D8 "
                  "con índice topográfico TWI ln(a / tan β) para identificar bajos y cañadas (≥ 5 ha); "
                  "largo de ladera con cortes de Van Remortel y Hickey (hasta 300 m); erosión por cuadrado con "
                  "A = R · K · LS · C · P, con R, K, C y P de cada sección y LS de Wischmeier y Smith.",
        "limites": [
            "SRTM es de 2000 y mide lo que ve el radar: en montes y cascos, la copa de los árboles o los techos.",
            "En los llanos la pendiente de SRTM es menos confiable (ruido de unos metros que puede falsear los caminos del agua).",
            ("El largo de pendiente es el que cargaste, igual para todo el campo." if largo_m else
             "El camino del agua y el largo de ladera salen de SRTM (30 m): no ven zanjas, caminos ni terrazas que cortan el agua antes."),
        ],
    }
