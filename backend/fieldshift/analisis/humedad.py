"""Humedad del suelo: lo que mide SMAP contra lo que calcula la app con el clima de POWER.

Dos preguntas para el productor:
1. ¿Cómo está el suelo ahora? El percentil de SMAP L4 dice si la zona de raíces está más seca o más
   húmeda que lo normal para esta época ("más seco que 8 de cada 10 años").
2. ¿Le podemos creer al balance de agua de la app? Se compara, mes a mes, el agua del "balde" de la app
   (FAO-56 con la lluvia y la ET0 de POWER, sobre un pasto de referencia) con la humedad de raíces de
   SMAP. Como las unidades son distintas (fracción del agua útil contra m³/m³), se comparan las
   **anomalías**: cuánto se aparta cada mes de su promedio de ese mes. Si suben y bajan juntas, el
   balance capta bien las secas y los excesos de la zona.

Límites: SMAP L4 es un píxel de 9 km y un modelo que asimila el satélite; el balance de la app usa POWER
(~50 km) y un agua útil fija. Ninguno ve un bajo o una loma del campo.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

from .clima import P_AGOTAMIENTO, Serie


def balde_referencia(serie: Serie, agua_util_mm: float) -> np.ndarray:
    """Fracción del agua útil que queda en el suelo cada día, bajo un pasto de referencia (Kc = 1)."""
    taw = max(agua_util_mm, 1.0)
    raw = P_AGOTAMIENTO * taw
    dr = taw * 0.5
    salida = np.empty(len(serie.lluvia))
    for i in range(len(serie.lluvia)):
        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / (taw - raw))
        dr = min(taw, max(0.0, dr - serie.lluvia[i] + ks * serie.et0[i]))
        salida[i] = 1 - dr / taw
    return salida


def _anomalias(valores: dict[str, float]) -> dict[str, float]:
    """Por mes calendario: valor menos el promedio de ese mes, dividido por su desvío."""
    por_mes: dict[int, list[float]] = {}
    for k, v in valores.items():
        por_mes.setdefault(int(k[5:7]), []).append(v)
    stats = {m: (float(np.mean(v)), float(np.std(v)) or 1.0) for m, v in por_mes.items()}
    return {k: (v - stats[int(k[5:7])][0]) / stats[int(k[5:7])][1] for k, v in valores.items()}


def comparar(smap: list[dict], serie: Serie, agua_util_mm: float, gldas: dict | None = None) -> dict:
    if not smap:
        return {"ok": False, "motivo": "SMAP no devolvió datos para este punto."}
    balde = balde_referencia(serie, agua_util_mm)
    sm_mes: dict[str, list[float]] = {}
    app_mes: dict[str, list[float]] = {}
    for i, d in enumerate(serie.fechas):
        app_mes.setdefault(f"{d.year:04d}-{d.month:02d}", []).append(float(balde[i]))
    for f in smap:
        if f.get("sm") is not None:
            k = f["fecha"][:7]
            sm_mes.setdefault(k, []).append(f["sm"])
    # meses con al menos 20 días calculados en el clima
    meses = sorted(k for k in sm_mes if k in app_mes and len(app_mes[k]) >= 20)
    if len(meses) < 12:
        return {"ok": False, "motivo": "Menos de un año en común entre SMAP y el clima de POWER."}
    sm = {k: float(np.mean(sm_mes[k])) for k in meses}
    app = {k: float(np.mean(app_mes[k])) for k in meses}
    a_sm, a_app = _anomalias(sm), _anomalias(app)
    r = float(np.corrcoef([a_sm[k] for k in meses], [a_app[k] for k in meses])[0, 1])
    if r >= 0.7:
        acuerdo = "coinciden bien: el balance de la app capta las secas y los excesos que ve SMAP."
    elif r >= 0.4:
        acuerdo = "coinciden en lo grueso: las secas grandes aparecen en los dos, los detalles no."
    else:
        acuerdo = ("no coinciden: conviene revisar el agua útil del suelo con un análisis, o tomar con más "
                   "cuidado el riesgo de seca.")
    # cómo está ahora (promedio de los últimos 7 días con dato)
    ultimos = [f for f in smap[-7:] if f.get("pctl") is not None]
    ahora = None
    if ultimos:
        pctl = float(np.mean([f["pctl"] for f in ultimos]))
        mas_seco_que = round((100 - pctl) / 10)
        if pctl <= 30:
            texto = f"La zona de raíces está más seca que lo normal: más seca que {mas_seco_que} de cada 10 años en esta época."
        elif pctl >= 70:
            texto = f"La zona de raíces está más húmeda que lo normal: más húmeda que {round(pctl / 10)} de cada 10 años en esta época."
        else:
            texto = "La zona de raíces está dentro de lo normal para esta época."
        ahora = {"hasta": smap[-1]["fecha"], "percentil": round(pctl), "texto": texto}
    ult = meses[-36:]

    # Integración GLDAS (2000-presente)
    gldas_anomalias: dict[str, float] = {}
    gldas_info: dict | None = None
    limites_extra = []
    if gldas and gldas.get("ok"):
        from ..fuentes import gldas as gldas_mod
        gldas_anomalias = gldas.get("anomalias") or {}
        # Anomalías completas de la app desde 1991 para comparar con todo GLDAS
        app_todas = {k: float(np.mean(v)) for k, v in app_mes.items() if len(v) >= 20}
        a_app_todas = _anomalias(app_todas)
        gldas_info = gldas_mod.comparar_con_balance(gldas_anomalias, a_app_todas)
        limites_extra = gldas.get("limites") or []

    mensual_salida = []
    for k in ult:
        fila: dict[str, Any] = {
            "mes": k,
            "smap_m3m3": round(sm[k], 3),
            "app_fraccion": round(app[k], 3),
            "smap_anomalia": round(a_sm[k], 2),
            "app_anomalia": round(a_app[k], 2),
        }
        if k in gldas_anomalias:
            fila["gldas_anomalia"] = gldas_anomalias[k]
        mensual_salida.append(fila)

    return {
        "ok": True,
        "desde": smap[0]["fecha"],
        "hasta": smap[-1]["fecha"],
        "meses_en_comun": len(meses),
        "correlacion": round(r, 2),
        "acuerdo": acuerdo,
        "ahora": ahora,
        "mensual": mensual_salida,
        "gldas": gldas_info,
        "gldas_fuente": gldas.get("fuente") if gldas and gldas.get("ok") else None,
        "limites": [
            "SMAP L4 es un píxel de 9 km que combina el satélite (primeros 5 cm) con un modelo para llegar a 1 m.",
            "El balance de la app usa el clima de POWER (~50 km) y un agua útil fija para todo el campo.",
            "Se comparan anomalías (cuánto se aparta cada mes de lo normal), no los valores, porque miden cosas distintas.",
            *limites_extra,
        ],
    }
