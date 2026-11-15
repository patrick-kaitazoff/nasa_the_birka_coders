"""Vuelve a bajar del MTOP los mojones de kilómetro de las rutas nacionales y los guarda en
fieldshift/datos/mojones_uy.json.

Correr desde app/backend: .venv/Scripts/python scripts/actualizar_mojones.py (tarda unos segundos)

Fuente: geoservicio WFS de la IDE del MTOP, capa `rutas_SD:mojones_sd` (puntos de calibración de la segmentación
dinámica de rutas nacionales: postes de kilómetro y puntos calculados, con su progresiva). Es el conjunto «Rutas y
puntos de calibración para segmentación dinámica de rutas nacionales» del Catálogo de Datos Abiertos, Licencia de
Datos Abiertos de Uruguay (citar al MTOP como fuente).

El servicio de direcciones de la IDE (direcciones.ide.uy, /api/v1/geocode/rutakm) reconoce la ruta y el km pero devolvía el punto en 0, 0: por eso se guardan los mojones y se interpola entre los dos más cercanos.
"""

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import httpx

WFS = ("https://geoservicios.mtop.gub.uy/geoserver/ows?service=WFS&version=1.1.0&request=GetFeature"
       "&typeName=rutas_SD:mojones_sd&outputFormat=application/json&srsName=EPSG:4326")
SALIDA = Path(__file__).resolve().parents[1] / "fieldshift" / "datos" / "mojones_uy.json"


def main() -> None:
    r = httpx.get(WFS, timeout=120, headers={"User-Agent": "FieldShift (NASA Space Apps 2026)"})
    r.raise_for_status()
    rutas: dict[str, list[list[float]]] = defaultdict(list)
    for f in r.json()["features"]:
        p = f["properties"]
        ruta = str(p.get("nom_sd") or "").strip().upper()
        km = p.get("progresiva")
        if not ruta or km is None or not f.get("geometry"):
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        rutas[ruta].append([float(km), round(lat, 6), round(lon, 6)])
    for lista in rutas.values():
        lista.sort()
    salida = {
        "fuente": f"MTOP, IDE del MTOP: mojones de la segmentación dinámica de rutas nacionales (WFS rutas_SD:mojones_sd), "
                  f"consulta del {dt.date.today():%d/%m/%Y}",
        "rutas": dict(sorted(rutas.items(), key=lambda kv: (len(kv[0]), kv[0]))),
    }
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{sum(len(v) for v in rutas.values())} mojones en {len(rutas)} rutas -> {SALIDA} ({SALIDA.stat().st_size // 1024} KB)")
    print("rutas:", ", ".join(rutas))


if __name__ == "__main__":
    main()
