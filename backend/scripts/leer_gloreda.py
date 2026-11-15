"""Lee el factor R medido (lluvia erosiva) de GloREDa 1.2 en un punto, para los terrenos de ejemplo.

Qué es: GloREDa (Global Rainfall Erosivity Database, JRC de la Comisión Europea; Panagos y otros 2017 y 2023) junta
el factor R calculado con lluvia de pluviógrafo (cada 1 a 60 minutos) en 3939 estaciones de 65 países, y doce mapas
mensuales de ~1 km interpolados con esas estaciones. Es libre (CC BY 4.0) y está en Zenodo sin registro:
https://doi.org/10.5281/zenodo.8036998 (GloREDa.zip, 2,2 GB). Unidades: MJ·mm/(ha·h·año); el motor usa las del MGAP,
que son esas divididas por 10.

Para qué: fuera de Uruguay el motor estima R con la lluvia anual (Renard y Freimund 1994, ajustada con estaciones
de EE. UU.). En climas de lluvia mansa da varias veces más que lo medido. Los terrenos de ejemplo cargan el R de este mapa en `factor_r_medido`.

No es parte de la app: el zip no entra en el repo ni en Vercel. Se corre a mano, una vez por lugar, y el número
se copia a scripts/armar_terrenos.py. Pide tifffile e imagecodecs (no están en requirements.txt: `pip install
tifffile imagecodecs` en un entorno aparte).

Uso: python scripts/leer_gloreda.py <ruta a GloREDa.zip> <lat> <lon> [<lat> <lon> ...]
"""

from __future__ import annotations

import math
import sys
import tempfile
import zipfile
from pathlib import Path

MESES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
         "November", "December"]


def _valor(pagina, fh, fila: int, col: int) -> float | None:
    """El valor de un píxel leyendo solo el bloque (franja o mosaico) que lo contiene."""
    if pagina.is_tiled:
        th, tw = pagina.tilelength, pagina.tilewidth
        por_fila = math.ceil(pagina.imagewidth / tw)
        i = (fila // th) * por_fila + col // tw
        f, c = fila % th, col % tw
    else:
        rps = pagina.rowsperstrip
        i, f, c = fila // rps, fila % rps, col
    fh.seek(pagina.dataoffsets[i])
    bloque = pagina.decode(fh.read(pagina.databytecounts[i]), i)[0]
    v = float(bloque.reshape(bloque.shape[-3], bloque.shape[-2])[f, c]) if bloque.ndim >= 3 else float(bloque[f, c])
    nulo = pagina.nodata
    if v != v or (nulo is not None and v == float(nulo)) or v < 0:
        return None
    return v


def leer(zip_ruta: str, puntos: list[tuple[float, float]]) -> list[dict]:
    import tifffile

    salida = [{"lat": la, "lon": lo, "mensual": []} for la, lo in puntos]
    with zipfile.ZipFile(zip_ruta) as z, tempfile.TemporaryDirectory() as tmp:
        for mes in MESES:
            ruta = Path(z.extract(f"Rfactor_{mes}.tif", tmp))
            with tifffile.TiffFile(ruta) as t:
                p = t.pages[0]
                escala = p.tags["ModelPixelScaleTag"].value
                ancla = p.tags["ModelTiepointTag"].value  # (i, j, k, x, y, z): el píxel (i, j) está en (x, y)
                geo = p.geotiff_tags
                if geo.get("GTModelTypeGeoKey") not in (2, "ModelTypeGeographic") and "Geographic" not in str(geo.get("GTModelTypeGeoKey")):
                    raise SystemExit(f"{mes}: el mapa no está en latitud y longitud ({geo.get('GTModelTypeGeoKey')})")
                for s in salida:
                    col = int((s["lon"] - ancla[3]) / escala[0] + ancla[0])
                    fila = int((ancla[4] - s["lat"]) / escala[1] + ancla[1])
                    # el punto y sus ocho vecinos (~1 km): si el del medio no tiene dato (agua, borde), los de al lado
                    vals = [_valor(p, t.filehandle, fila + df, col + dc) for df in (0, -1, 1) for dc in (0, -1, 1)]
                    con = [v for v in vals if v is not None]
                    s["mensual"].append({"mes": mes, "punto": vals[0], "vecinos_min": min(con) if con else None,
                                         "vecinos_max": max(con) if con else None})
            ruta.unlink()
    for s in salida:
        ms = [m["punto"] if m["punto"] is not None else m["vecinos_min"] for m in s["mensual"]]
        s["r_anual"] = round(sum(ms)) if None not in ms else None
        s["r_anual_vecinos"] = (round(sum(m["vecinos_min"] for m in s["mensual"])), round(sum(m["vecinos_max"] for m in s["mensual"]))) \
            if all(m["vecinos_min"] is not None for m in s["mensual"]) else None
    return salida


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # la consola de Windows (cp1252) no tiene «→»
    if len(sys.argv) < 4 or len(sys.argv) % 2:
        raise SystemExit(__doc__)
    pts = [(float(sys.argv[i]), float(sys.argv[i + 1])) for i in range(2, len(sys.argv), 2)]
    for s in leer(sys.argv[1], pts):
        print(f"{s['lat']}, {s['lon']}: R anual {s['r_anual']} MJ·mm/(ha·h·año) → {s['r_anual'] / 10 if s['r_anual'] else None} en unidades del MGAP"
              f" | entre los 9 píxeles: {s['r_anual_vecinos']}")
        print("   por mes:", [round(m["punto"]) if m["punto"] is not None else None for m in s["mensual"]])
