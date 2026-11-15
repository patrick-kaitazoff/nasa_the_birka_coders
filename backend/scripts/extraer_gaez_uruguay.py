"""
Baja de FAO GAEZ v4 (Theme 4, res05) la aptitud de los cultivos de FieldShift para todo Uruguay, en una grilla
de 5 minutos de arco (~9 km), y la guarda en backend/fieldshift/datos/gaez_uruguay.json.

Qué se baja, por cultivo (secano, nivel de insumo alto), para toda la tierra de cada celda: `sxHr_*` (índice de
aptitud, 0-10000) y `siHr_*` (el mismo índice en clases), con dos climas:
- 2011-2040 con el escenario medio RCP 4.5: es el que usa la app. El índice es el promedio de los índices de los 5 modelos de GAEZ y
  la clase sale de ese índice con los cortes de abajo. GAEZ publica su propio promedio (ENSEMBLE) para 6 de los 8
  cultivos, pero no para maíz ni sorgo; para usar el mismo criterio en todos se promedia acá, y en esos 6 se compara
  con el ENSEMBLE (el script avisa cuánto difieren);
- 1981-2010 (CRU TS 3.2), el histórico, para decir si la clase cambia.

Clases de GAEZ v4:
1 muy alta (índice > 85), 2 alta (70-85), 3 buena (55-70), 4 media (40-55), 5 moderada (25-40),
6 marginal (10-25), 7 muy marginal (0-10), 8 no apta; 9 (agua) y 0 quedan sin dato.

No se usa la variante «tierra de cultivo actual» (`scHr_*` / `suHr_*`): `sc` trae una clase 10 y `su` no sigue esos
cortes, y no se encontró su leyenda.

Cuidado: cada nombre de capa (por ejemplo scHr_soy) existe para 1961-1990, 1971-2000 y 1981-2010; hay que filtrar
por `year`.

Licencia: CC BY-NC-SA 3.0 IGO, con atribución a FAO e IIASA; no permite uso comercial sin acuerdo con la FAO.

Uso (desde la raíz del repo): python scripts/extraer_gaez_uruguay.py
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

SERVICIO = "https://gaez-services.fao.org/server/rest/services/res05/ImageServer"
UA = {"User-Agent": "Mozilla/5.0"}

# Uruguay entero, alineado a la grilla de GAEZ (pasos de 1/12 de grado desde -180, 90)
OESTE, SUR, ESTE, NORTE = -58.5, -35.0, -53.0, -30.0
PASO = 1 / 12
ANCHO = round((ESTE - OESTE) / PASO)  # 66
ALTO = round((NORTE - SUR) / PASO)  # 60

CULTIVOS_GAEZ = {
    "soja": ("soy", "Soybean"),
    "maiz": ("mze", "Maize"),
    "trigo": ("whe", "Wheat"),
    "cebada": ("brl", "Barley"),
    "sorgo": ("srg", "Sorghum"),
    "girasol": ("sfl", "Sunflower"),
    "colza": ("rsd", "Rapeseed"),
    "alfalfa": ("alf", "Alfalfa"),
}

CLASES = {
    1: "muy alta", 2: "alta", 3: "buena", 4: "media", 5: "moderada",
    6: "marginal", 7: "muy marginal", 8: "no apta", 9: "agua",
}


def _get(url: str, params: dict, json_ok: bool = True):
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        datos = r.read()
    return json.loads(datos) if json_ok else datos


MODELOS_GAEZ = ["GFDL-ESM2M", "HadGEM2-ES", "IPSL-CM5A-LR", "MIROC-ESM-CHEM", "NorESM1-M"]
CORTES = [(8500, 1), (7000, 2), (5500, 3), (4000, 4), (2500, 5), (1000, 6), (0, 7)]  # índice > corte → clase


def clase_de_indice(sx: np.ndarray) -> np.ndarray:
    """La clase de GAEZ que corresponde a un índice 0-10000 (8 = no apta, con índice 0)."""
    clase = np.full(sx.shape, 8)
    for corte, c in reversed(CORTES):
        clase = np.where(sx > corte, c, clase)
    return clase


def capas(modelo: str, rcp: str, anios: str, exigir: bool = True) -> dict[str, int]:
    nombres = [f"{v}Hr_{codigo}" for codigo, _ in CULTIVOS_GAEZ.values() for v in ("si", "sx")]
    lista = "', '".join(nombres)
    where = (f"model = '{modelo}' AND rcp = '{rcp}' AND year = '{anios}' AND water_supply = 'Rainfed' "
             f"AND input_level = 'High' AND name IN ('{lista}')")
    feats = _get(f"{SERVICIO}/query", {"where": where, "outFields": "objectid,name", "returnGeometry": "false",
                                       "f": "json"})["features"]
    salida: dict[str, int] = {}
    for f in feats:
        a = f["attributes"]
        if a["name"] in salida:
            raise RuntimeError(f"Capa repetida para {modelo} {rcp} {anios}: {a['name']}")
        salida[a["name"]] = a["objectid"]
    faltan = set(nombres) - set(salida)
    if faltan and exigir:
        raise RuntimeError(f"Faltan capas: {sorted(faltan)}")
    return salida


def grilla(oid: int) -> np.ndarray:
    """Devuelve la capa como matriz ALTO × ANCHO (fila 0 = norte). 0 = sin dato."""
    crudo = _get(f"{SERVICIO}/exportImage", {
        "bbox": f"{OESTE},{SUR},{ESTE},{NORTE}", "bboxSR": "4326", "imageSR": "4326", "size": f"{ANCHO},{ALTO}",
        "format": "bsq", "pixelType": "U16", "interpolation": "RSP_NearestNeighbor", "noData": "0",
        "mosaicRule": json.dumps({"mosaicMethod": "esriMosaicLockRaster", "lockRasterIds": [oid]}), "f": "image",
    }, json_ok=False)
    # Los primeros ANCHO*ALTO*2 bytes son los valores; después viene una máscara de un bit por celda.
    return np.frombuffer(crudo[: ANCHO * ALTO * 2], dtype="<u2").reshape(ALTO, ANCHO).astype(int)


def valor_punto(oid: int, lat: float, lon: float) -> int:
    v = _get(f"{SERVICIO}/identify", {
        "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "sr": "4326",
        "mosaicRule": json.dumps({"mosaicMethod": "esriMosaicLockRaster", "lockRasterIds": [oid]}),
        "returnGeometry": "false", "returnCatalogItems": "false", "f": "json",
    }).get("value")
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


# Puntos para comprobar que la grilla bajada coincide con lo que da `identify` celda por celda
CONTROLES = [(-33.1, -56.15), (-33.3, -58.0), (-31.7, -55.9), (-34.5, -56.0)]


def bajar(modelo: str, rcp: str, anios: str) -> dict:
    oids = capas(modelo, rcp, anios)
    print(f"{len(oids)} capas de {modelo} {rcp} {anios}")
    cultivos = {}
    for id_app, (codigo, nombre_gaez) in CULTIVOS_GAEZ.items():
        si, sx = grilla(oids[f"siHr_{codigo}"]), grilla(oids[f"sxHr_{codigo}"])
        for lat, lon in CONTROLES:
            fila, col = int((NORTE - lat) // PASO), int((lon - OESTE) // PASO)
            esperado = valor_punto(oids[f"sxHr_{codigo}"], lat, lon)
            assert sx[fila, col] == esperado, (id_app, lat, lon, sx[fila, col], esperado)
        clase = np.where((si >= 1) & (si <= 8), si, 0)  # 9 = agua: sin dato
        indice = np.where(clase > 0, np.minimum(sx, 10000), 0)
        cultivos[id_app] = {
            "gaez": nombre_gaez,
            # una cifra por celda, fila por fila desde el norte; "0" = sin dato
            "clase": "".join(str(int(v)) for v in clase.ravel()),
            # índice 0-100 por celda (GAEZ lo da de 0 a 10000)
            "indice": [int(round(v / 100)) for v in indice.ravel()],
        }
        fila, col = int((NORTE - -33.1) // PASO), int((-56.15 - OESTE) // PASO)
        print(f"  {id_app}: en el ejemplo clase {clase[fila, col]}, índice {indice[fila, col] / 100:.0f}")
    return cultivos


def bajar_promedio(rcp: str, anios: str) -> dict:
    """El promedio de los 5 modelos de GAEZ: índice promedio y su clase; agua o sin dato si ningún modelo da tierra."""
    por_modelo = {m: capas(m, rcp, anios) for m in MODELOS_GAEZ}
    ens = capas("ENSEMBLE", rcp, anios, exigir=False)
    print(f"{len(MODELOS_GAEZ)} modelos de {rcp} {anios}")
    cultivos = {}
    for id_app, (codigo, nombre_gaez) in CULTIVOS_GAEZ.items():
        sx = np.array([grilla(por_modelo[m][f"sxHr_{codigo}"]) for m in MODELOS_GAEZ], dtype=float)
        si = np.array([grilla(por_modelo[m][f"siHr_{codigo}"]) for m in MODELOS_GAEZ])
        tierra = ((si >= 1) & (si <= 8)).any(axis=0)
        media = np.minimum(sx, 10000).mean(axis=0)
        clase = np.where(tierra, clase_de_indice(media), 0)
        indice = np.where(tierra, media, 0)
        if f"sxHr_{codigo}" in ens:
            e = np.minimum(grilla(ens[f"sxHr_{codigo}"]), 10000)
            dif = np.abs(e - media)[tierra] / 100
            print(f"  {id_app}: contra el ENSEMBLE de GAEZ, diferencia de índice mediana {np.median(dif):.1f}, "
                  f"máxima {dif.max():.1f} (de 100)")
        cultivos[id_app] = {
            "gaez": nombre_gaez,
            "clase": "".join(str(int(v)) for v in clase.ravel()),
            "indice": [int(round(v / 100)) for v in indice.ravel()],
        }
        fila, col = int((NORTE - -33.1) // PASO), int((-56.15 - OESTE) // PASO)
        print(f"  {id_app}: en el ejemplo clase {clase[fila, col]}, índice {indice[fila, col] / 100:.0f}")
    return cultivos


def main() -> None:
    cultivos = bajar_promedio("RCP4.5", "2011-2040")
    antes = bajar("CRUTS32", "Historical", "1981-2010")
    salida = {
        "fuente": "FAO/IIASA GAEZ v4, Theme 4 (Suitability and Attainable Yield, res05)",
        "variables": "siHr (clase) y sxHr (índice 0-100), toda la tierra de la celda",
        "regimen": "secano, nivel de insumo alto, con fertilización por CO2",
        "periodo": "2011-2040 (promedio de los índices de 5 modelos, RCP 4.5)",
        "periodo_antes": "1981-2010 (CRU TS 3.2)",
        "licencia": "CC BY-NC-SA 3.0 IGO",
        "cita": "FAO & IIASA (2021). Global Agro-Ecological Zones version 4 (GAEZ v4). FAO, Rome, and IIASA, Laxenburg.",
        "grilla": {"oeste": OESTE, "norte": NORTE, "paso_grados": PASO, "ancho": ANCHO, "alto": ALTO},
        "clases": {str(k): v for k, v in CLASES.items()},
        "cultivos": cultivos,
        "cultivos_1981_2010": antes,
    }
    destino = Path(__file__).resolve().parents[1] / "fieldshift" / "datos" / "gaez_uruguay.json"
    destino.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Guardado {destino} ({destino.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
