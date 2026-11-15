"""Arma la estación del campo de ejemplo con datos REALES de INUMET.

Reemplaza a `estacion_ejemplo_sintetico.csv` (POWER con ruido), que inventaba 15 heladas y 37 % menos lluvia y con eso
le sumaba riesgo de helada a todo el campo. INUMET publica en datos abiertos la lluvia y la temperatura por hora de 7
estaciones automáticas; la más cercana al padrón 1000 de Durazno es Paso de los Toros G3 (~47 km del centro de la
ciudad; INUMET no publica la ubicación exacta de la estación). Licencia: Datos Abiertos de Uruguay.

Se agrega por día en hora de Uruguay (UTC-3): lluvia sumada, máxima y mínima de las temperaturas horarias. Un día
con menos de 20 horas con dato queda vacío (no se completa).

Correr desde app/backend: .venv/Scripts/python scripts/armar_estacion_inumet.py
Escribe app/ejemplos/estacion_inumet_paso_de_los_toros.csv y la copia de frontend/public/ejemplos/.
"""

from __future__ import annotations

import datetime as dt
import io
import shutil
from pathlib import Path

import httpx
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
NOMBRE = "estacion_inumet_paso_de_los_toros.csv"
SALIDA = RAIZ.parent / "ejemplos" / NOMBRE
COPIA = RAIZ.parent / "frontend" / "public" / "ejemplos" / NOMBRE
ESTACION = "Paso de los Toros G3"
CKAN = "https://catalogodatos.gub.uy/api/3/action/package_show?id="
DATASETS = {
    "lluvia": "inumet-observaciones-meteorologicas-precipitacion-puntual-en-el-uruguay",
    "temp": "inumet-observaciones-meteorologicas-temperatura-del-aire-en-el-uruguay",
}
DESDE, HASTA = dt.date(2025, 10, 1), dt.date(2026, 11, 15)
HORAS_MIN = 20


def bajar(dataset: str) -> pd.Series:
    meta = httpx.get(CKAN + dataset, timeout=60).json()["result"]
    url = next(r["url"] for r in meta["resources"] if r["url"].endswith(".csv"))
    df = pd.read_csv(io.StringIO(httpx.get(url, timeout=300, follow_redirects=True).text), sep=";")
    df = df[df["estacion_id"] == ESTACION].copy()
    # UTC → hora de Uruguay, para que el día sea el día local
    df.index = pd.to_datetime(df["fecha"]) - pd.Timedelta(hours=3)
    return pd.to_numeric(df[df.columns[2]], errors="coerce")


def main():
    lluvia, temp = bajar(DATASETS["lluvia"]), bajar(DATASETS["temp"])
    ll = lluvia.resample("D").agg(["sum", "count"])
    tt = temp.resample("D").agg(["max", "min", "count"])
    dias = pd.DataFrame({
        "Lluvia (mm)": ll["sum"].where(ll["count"] >= HORAS_MIN),
        "Temp Max (°C)": tt["max"].where(tt["count"] >= HORAS_MIN),
        "Temp Min (°C)": tt["min"].where(tt["count"] >= HORAS_MIN),
    }).loc[DESDE.isoformat():HASTA.isoformat()]
    dias = dias.dropna(how="all")
    texto = dias.to_csv(sep=";", decimal=",", float_format="%.1f", date_format="%d/%m/%Y", index_label="Fecha")
    cab = (f"# Datos REALES de INUMET (datos abiertos de Uruguay): estación automática {ESTACION}, a ~47 km del campo de "
           f"ejemplo. Por hora, agregados por día en hora de Uruguay. Bajados el {dt.date.today():%d/%m/%Y} de "
           "catalogodatos.gub.uy.\n")
    SALIDA.write_text(cab + texto, encoding="utf-8")
    shutil.copyfile(SALIDA, COPIA)
    print(f"{len(dias)} días ({dias.index.min():%d/%m/%Y} a {dias.index.max():%d/%m/%Y}); "
          f"lluvia {dias['Lluvia (mm)'].sum():.0f} mm; días sin lluvia completa: {dias['Lluvia (mm)'].isna().sum()}; "
          f"heladas (mín <= 0 °C): {(dias['Temp Min (°C)'] <= 0).sum()}")


if __name__ == "__main__":
    main()
