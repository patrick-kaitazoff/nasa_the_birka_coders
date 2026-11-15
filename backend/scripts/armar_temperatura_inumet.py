"""Corrección de la temperatura de NASA POWER con las estaciones de INUMET.

POWER exagera el calor del verano en Uruguay (veranos 2020-2025 contra INUMET: +3,5 °C en el Aeropuerto Melilla,
+2,2 en Mercedes, +1,4 en Paso de los Toros; días ≥ 35 °C, el doble a cinco veces) y le faltan heladas (Mercedes:
días ≤ 2 °C, 20 % real contra 8 %). Ver claude_brain/15-uruguay-datos-y-apis.

Qué hace: para cada una de las 7 estaciones de INUMET con datos abiertos por hora (catalogodatos.gub.uy), arma la
máxima y la mínima de cada día (hora local, días con 20 horas o más) y, mes por mes, los percentiles de esas
temperaturas y de las de POWER en la celda de la estación, en los mismos días. La app pasa cada día de POWER al valor
de la estación que ocupa el mismo percentil en ese mes (mapeo de cuantiles, el mismo método que la lluvia de POWER
contra IMERG). Se guarda en fieldshift/datos/temperatura_inumet.json.

Límites: 7 estaciones y unos 5 años en común; la máxima sacada de datos por hora pierde el pico (~0,5 °C), así que
la corrección queda un poco fresca en las máximas; INUMET no publica las coordenadas en el dataset (se usan las del
aeropuerto o la ciudad).

Correr desde app/backend (baja ~14 MB de INUMET y 7 series de POWER): .venv/Scripts/python scripts/armar_temperatura_inumet.py
"""

from __future__ import annotations

import datetime as dt
import io
import json
import sys
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from fieldshift.fuentes import power  # noqa: E402

SALIDA = RAIZ / "fieldshift" / "datos" / "temperatura_inumet.json"
CSV = ("https://catalogodatos.gub.uy/dataset/accd0e24-76be-4101-904b-81bb7d41ee88/resource/"
       "f800fc53-556b-4d1c-8bd6-28b41f9cf146/download/inumet_temperatura_del_aire.csv")
# INUMET no publica las coordenadas en el dataset: las de cada aeropuerto o ciudad (Artigas, la de su tabla 1991-2020)
ESTACIONES = {
    "Aeropuerto Melilla G3": ("Aeropuerto Melilla", -34.790, -56.265),
    "Artigas G3": ("Artigas", -30.398, -56.512),
    "Colonia G3": ("Colonia", -34.453, -57.840),
    "Mercedes G3": ("Mercedes", -33.250, -58.067),
    "Paso de los Toros G3": ("Paso de los Toros", -32.817, -56.517),
    "Rocha G3": ("Rocha", -34.493, -54.310),
    "Salto G3": ("Salto", -31.433, -57.983),
}
PERCENTILES = [0, 1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 99, 100]
MIN_HORAS = 20
MIN_DIAS_MES = 60  # días en común en ese mes del año para armar el mapeo (unos 2 años)


def main() -> None:
    r = httpx.get(CSV, timeout=120, follow_redirects=True)
    r.raise_for_status()
    t = pd.read_csv(io.StringIO(r.text), sep=";").dropna()
    t["fecha"] = pd.to_datetime(t["fecha"]) - pd.Timedelta(hours=3)  # viene en UTC
    t["dia"] = t["fecha"].dt.date
    g = t.groupby(["estacion_id", "dia"])["temp_aire"]
    completos = g.size() >= MIN_HORAS
    tx, tn = g.max()[completos], g.min()[completos]

    salida = []
    for clave, (nombre, lat, lon) in ESTACIONES.items():
        pw = power._bajar_power(lat, lon)
        fechas = [dt.date(int(f[:4]), int(f[4:6]), int(f[6:8])) for f in pw["fechas"]]
        fila = {"nombre": nombre, "lat": lat, "lon": lon, "celda_power": [pw["lat"], pw["lon"]], "tmax": {}, "tmin": {}}
        for var, est, col in (("tmax", tx, "T2M_MAX"), ("tmin", tn, "T2M_MIN")):
            p = pd.Series(pw[col], index=fechas, dtype=float).dropna()
            e = est.loc[clave]
            comun = sorted(set(e.index) & set(p.index))
            df = pd.DataFrame({"est": e.loc[comun].values, "power": p.loc[comun].values}, index=pd.to_datetime(comun))
            for m in range(1, 13):
                dm = df[df.index.month == m]
                if len(dm) < MIN_DIAS_MES:
                    continue
                fila[var][str(m)] = {
                    "dias": len(dm),
                    "power": [round(float(v), 2) for v in np.percentile(dm["power"], PERCENTILES)],
                    "estacion": [round(float(v), 2) for v in np.percentile(dm["est"], PERCENTILES)],
                }
            ver = df[df.index.month.isin([12, 1, 2, 3])]
            print(f"  {nombre:18s} {var}: {len(df)} días en común; verano POWER {ver['power'].mean():.1f} °C, "
                  f"estación {ver['est'].mean():.1f} °C ({ver['power'].mean() - ver['est'].mean():+.1f})", flush=True)
        salida.append(fila)

    meta = {
        "fuente": "INUMET, observaciones por hora (catalogodatos.gub.uy, «temperatura del aire en el Uruguay»)",
        "metodo": "mapeo de cuantiles mes a mes de la máxima y la mínima diarias de NASA POWER a las de la estación",
        "percentiles": PERCENTILES, "armado": dt.date.today().isoformat(),
        "limites": "7 estaciones; unos 5 años en común; la máxima por hora pierde el pico (~0,5 °C)",
    }
    SALIDA.write_text(json.dumps({"meta": meta, "estaciones": salida}, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")
    print(SALIDA, round(SALIDA.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
