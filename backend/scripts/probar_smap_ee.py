"""Prueba chica: comparar promedios mensuales de SMAP L4 entre Earth Engine y la serie guardada de AppEEARS.

Punto: campo de ejemplo (-33.103, -56.146).
Compara sm_rootzone (m³/m³) y sm_rootzone_pctl (percentil 0-100) mes a mes desde abril 2015.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import ee
import numpy as np

DIR_DATOS = Path(__file__).resolve().parents[1] / "fieldshift" / "datos" / "smap"
ARCHIVO_EJEMPLO = DIR_DATOS / "-33.1,-56.15.json"
LAT, LON = -33.103046, -56.14625


def comparar():
    data_app = json.loads(ARCHIVO_EJEMPLO.read_text(encoding="utf-8"))
    serie_app = data_app["serie"]

    app_por_mes: dict[str, dict[str, list[float]]] = {}
    for item in serie_app:
        m = item["fecha"][:7]
        app_por_mes.setdefault(m, {"sm": [], "pctl": []})
        if item.get("sm") is not None:
            app_por_mes[m]["sm"].append(item["sm"])
        if item.get("pctl") is not None:
            app_por_mes[m]["pctl"].append(item["pctl"])

    app_promedios = {}
    for m, vals in app_por_mes.items():
        if len(vals["sm"]) >= 15:
            app_promedios[m] = {
                "sm": float(np.mean(vals["sm"])),
                "pctl": float(np.mean(vals["pctl"])) if vals["pctl"] else None,
            }

    ee.Initialize(project="field-shift-514100")
    punto = ee.Geometry.Point([LON, LAT])
    col = ee.ImageCollection("NASA/SMAP/SPL4SMGP/008").select(["sm_rootzone", "sm_rootzone_pctl"])

    meses_lista = sorted(app_promedios.keys())
    features = []
    for m in meses_lista:
        y, mo = int(m[:4]), int(m[5:7])
        d_ini = dt.date(y, mo, 1)
        d_fin = dt.date(y + 1, 1, 1) if mo == 12 else dt.date(y, mo + 1, 1)

        img = col.filterDate(d_ini.isoformat(), d_fin.isoformat()).mean()
        val = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=punto, scale=11000)
        features.append(ee.Feature(None, {
            "mes": m,
            "sm": val.get("sm_rootzone"),
            "pctl": val.get("sm_rootzone_pctl"),
        }))

    fc = ee.FeatureCollection(features)
    res = fc.getInfo()

    ee_promedios = {}
    for f in res["features"]:
        props = f["properties"]
        m = props["mes"]
        if props.get("sm") is not None:
            ee_promedios[m] = {
                "sm": props["sm"],
                "pctl": props.get("pctl"),
            }

    comunes = sorted(set(app_promedios.keys()) & set(ee_promedios.keys()))
    sm_app = [app_promedios[m]["sm"] for m in comunes]
    sm_ee = [ee_promedios[m]["sm"] for m in comunes]

    pctl_app = [app_promedios[m]["pctl"] for m in comunes if app_promedios[m]["pctl"] is not None and ee_promedios[m]["pctl"] is not None]
    pctl_ee = [ee_promedios[m]["pctl"] for m in comunes if app_promedios[m]["pctl"] is not None and ee_promedios[m]["pctl"] is not None]

    diff_sm = np.array(sm_ee) - np.array(sm_app)
    mae_sm = float(np.mean(np.abs(diff_sm)))
    rmse_sm = float(np.sqrt(np.mean(diff_sm**2)))
    bias_sm = float(np.mean(diff_sm))
    r_sm = float(np.corrcoef(sm_app, sm_ee)[0, 1])

    diff_pctl = np.array(pctl_ee) - np.array(pctl_app)
    mae_pctl = float(np.mean(np.abs(diff_pctl)))
    rmse_pctl = float(np.sqrt(np.mean(diff_pctl**2)))
    bias_pctl = float(np.mean(diff_pctl))
    r_pctl = float(np.corrcoef(pctl_app, pctl_ee)[0, 1])

    print(f"Meses comparados: {len(comunes)} ({comunes[0]} a {comunes[-1]})")
    print(f"Humedad sm_rootzone (m³/m³): r={r_sm:.4f}, bias={bias_sm:.4f}, MAE={mae_sm:.4f}, RMSE={rmse_sm:.4f}")
    print(f"Percentil sm_rootzone_pctl (0-100): r={r_pctl:.4f}, bias={bias_pctl:.2f}, MAE={mae_pctl:.2f}, RMSE={rmse_pctl:.2f}")


if __name__ == "__main__":
    comparar()
