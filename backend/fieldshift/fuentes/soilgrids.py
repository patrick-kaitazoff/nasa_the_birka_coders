"""Suelo en cualquier lugar del mundo: ISRIC SoilGrids 2.0 (250 m).

Se usa cuando la carta del MGAP no tiene datos: fuera de Uruguay o si el servidor del MGAP no
responde. Trae arena, limo, arcilla y carbono orgánico de los primeros 30 cm y estima con eso el factor K de la
ecuación de erosión con la fórmula de EPIC (Williams, 1995), en las mismas unidades que usa el MGAP.

No hay tolerancia de pérdida de suelo mundial: queda en None y la ecuación usa el valor típico, que se avisa como
hueco de información. La pendiente sale del relieve SRTM del lote, como ya se hacía fuera de Uruguay.
API: https://rest.isric.org/soilgrids/v2.0/docs (libre, sin clave; pide no más de 5 consultas por minuto).
"""

from __future__ import annotations

import math

import httpx

from .. import cache

URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROFUNDIDADES = ("0-5cm", "5-15cm", "15-30cm")
ESPESOR = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}
FUENTE = "ISRIC SoilGrids 2.0 (250 m), 0-30 cm"


def factor_k_epic(arena: float, limo: float, arcilla: float, carbono: float) -> float:
    """K de la USLE con la fórmula de EPIC (Williams, 1995), con % de arena, limo, arcilla y carbono orgánico.

    EPIC da K en unidades de EE. UU. (t·acre·h/(cien·acre·pie-tonf·pulg)); el MGAP usa (t·ha·h/ha·MJ·mm)×10, que es
    el K internacional ×10. Internacional = EE. UU. × 0,1317, así que MGAP = EE. UU. × 1,317.
    """
    f_arena = 0.2 + 0.3 * math.exp(-0.256 * arena * (1 - limo / 100))
    f_limo_arcilla = (limo / max(arcilla + limo, 1e-6)) ** 0.3
    f_carbono = 1 - 0.25 * carbono / (carbono + math.exp(3.72 - 2.95 * carbono))
    sn1 = 1 - arena / 100
    f_arena_alta = 1 - 0.7 * sn1 / (sn1 + math.exp(-5.51 + 22.9 * sn1))
    k_eeuu = f_arena * f_limo_arcilla * f_carbono * f_arena_alta
    return round(k_eeuu * 1.317, 3)


def suelo_punto(lat: float, lon: float) -> dict:
    """Suelo en un punto, con la misma forma que mgap.suelo_punto (sin grupo CONEAT ni tolerancia). Cacheado 180 días."""
    clave = f"{lat:.4f},{lon:.4f}"
    guardado = cache.leer("soilgrids", clave, max_dias=180)
    if guardado:
        return guardado
    salida: dict = {"fuente": FUENTE, "lat": lat, "lon": lon, "ok": False, "mundial": True}
    params = [("lon", lon), ("lat", lat), *[("property", p) for p in ("sand", "silt", "clay", "soc")],
              *[("depth", d) for d in PROFUNDIDADES], ("value", "mean")]
    capas = None
    for intento in range(2):  # el servidor de ISRIC a veces tarda: un reintento
        try:
            r = httpx.get(URL, params=params, timeout=30)
            r.raise_for_status()
            capas = {c["name"]: c for c in r.json()["properties"]["layers"]}
            break
        except (httpx.HTTPError, ValueError, KeyError) as e:
            salida["errores"] = [f"SoilGrids: {e}"]
    if capas is None:
        return salida
    salida.pop("errores", None)

    def promedio(nombre: str) -> float | None:
        c = capas.get(nombre)
        if not c:
            return None
        div = c["unit_measure"]["d_factor"]
        vals = [(ESPESOR.get(d["label"], 0), d["values"].get("mean")) for d in c["depths"]]
        vals = [(e, v) for e, v in vals if v is not None and e]
        if not vals:
            return None
        return sum(e * v for e, v in vals) / sum(e for e, _ in vals) / div

    # SoilGrids da arena, limo y arcilla en g/kg y el carbono en dg/kg (ya divididos por d_factor: g/kg)
    arena, limo, arcilla, carbono = (promedio(p) for p in ("sand", "silt", "clay", "soc"))
    if None in (arena, limo, arcilla):
        salida["errores"] = ["SoilGrids no tiene datos en este punto (agua, ciudad o roca)."]
        return salida
    arena, limo, arcilla = (x / 10 for x in (arena, limo, arcilla))  # g/kg → %
    total = arena + limo + arcilla or 1
    arena, limo, arcilla = (100 * x / total for x in (arena, limo, arcilla))
    carbono_pct = (carbono or 0) / 10  # g/kg → %
    salida.update({
        "ok": True,
        "factor_k": factor_k_epic(arena, limo, arcilla, carbono_pct),
        "tolerancia_t": None,
        "arena": round(arena, 1), "limo": round(limo, 1), "arcilla": round(arcilla, 1),
        "carbono_organico": round(carbono_pct, 2), "materia_organica": round(carbono_pct * 1.724, 1),
    })
    cache.guardar("soilgrids", clave, salida)
    return salida
