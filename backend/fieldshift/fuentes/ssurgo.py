"""Suelo de un punto de EE. UU. con SSURGO (USDA-NRCS), el par de CONEAT/MGAP en Uruguay.

SSURGO es la carta de suelos detallada de EE. UU. (escala 1:12.000 a 1:63.360), la misma que muestra Web Soil Survey.
Se consulta con la API Soil Data Access, sin cuenta: https://sdmdataaccess.sc.egov.usda.gov (SQL por POST).
Probado con un punto de Iowa: Clarion loam, K 0,24, T 5, pendiente 3 %, grupo hidrológico B.

Devuelve las mismas claves que `mgap.suelo_punto` para que el motor no distinga el país:

- `factor_k`: el Kw del primer horizonte con dato del componente dominante. SSURGO lo da en las unidades de la USLE
  de EE. UU. (t·acre·h / (100·acre·pie·tonf·pulgada)); el motor usa las del MGAP (t·ha·h/(ha·MJ·mm) × 10), así que
  se multiplica por 1,317 (0,1317 del paso a SI, Foster et al. 1981, por 10). Comprobación: R_US × K_US × 2,242 da
  t/ha, y R_MGAP × K_MGAP = (1,702 R_US) × (1,317 K_US) = 2,242 R_US K_US.
- `tolerancia_t`: el T de SSURGO está en t cortas/acre/año (1 a 5); × 2,242 pasa a t/ha/año.
- `pendiente_pct`: la pendiente representativa del componente (`slope_r`).
- `agua_util_mm`: la suma de la capacidad de agua disponible (`awc_r`, cm/cm) de los horizontes hasta la
  profundidad de raíces que usa la app, en mm. El MGAP no la da: en Uruguay sale de tablas por textura.

Licencia: dominio público (USDA-NRCS).
"""

from __future__ import annotations

import httpx

from .. import cache

URL = "https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest"
TIMEOUT = 30.0
K_US_A_MGAP = 1.317
T_US_A_HA = 2.242  # t cortas/acre → t/ha
PROFUNDIDAD_CM = 80  # la misma de `analisis/suelo.py` (PROFUNDIDAD_RAICES_M = 0,8)

def _consulta(lat: float, lon: float) -> str:
    return f"""
SELECT mu.mukey, mu.muname, c.cokey, c.compname, c.comppct_r, c.slope_r, c.tfact, c.hydgrp, c.drainagecl,
       c.taxorder, ch.hzdept_r, ch.hzdepb_r, ch.kwfact, ch.om_r, ch.awc_r, ch.claytotal_r, ch.sandtotal_r,
       ch.silttotal_r, ch.ph1to1h2o_r
FROM mapunit mu
INNER JOIN component c ON c.mukey = mu.mukey AND c.majcompflag = 'Yes'
LEFT JOIN chorizon ch ON ch.cokey = c.cokey
WHERE mu.mukey IN (SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('point({lon:.6f} {lat:.6f})'))
ORDER BY c.comppct_r DESC, c.cokey, ch.hzdept_r
"""


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _agua_util_mm(horizontes: list[dict]) -> float | None:
    total, cubierto = 0.0, 0.0
    for h in horizontes:
        arriba, abajo, awc = _num(h["hzdept_r"]), _num(h["hzdepb_r"]), _num(h["awc_r"])
        if arriba is None or abajo is None or awc is None or arriba >= PROFUNDIDAD_CM:
            continue
        espesor = min(abajo, PROFUNDIDAD_CM) - arriba
        total += awc * espesor * 10  # cm de agua por cm de suelo × cm → mm
        cubierto += espesor
    return round(total) if cubierto >= PROFUNDIDAD_CM * 0.5 else None


def interpretar_filas(filas: list[dict]) -> dict:
    """Arma la salida a partir de las filas de la consulta (una por horizonte). Aparte para probarla sin internet."""
    if not filas:
        return {"ok": False, "errores": ["SSURGO no tiene suelo cartografiado en ese punto."]}
    cokey = filas[0]["cokey"]
    dominante = [f for f in filas if f["cokey"] == cokey]
    d = dominante[0]
    superficie = next((h for h in dominante if _num(h["kwfact"]) is not None), None)
    k_us = _num(superficie["kwfact"]) if superficie else None
    t_us = _num(d["tfact"])
    primer = dominante[0]
    componentes = []
    for f in filas:
        if f["cokey"] not in [c["cokey"] for c in componentes]:
            componentes.append({"cokey": f["cokey"], "nombre": f["compname"], "pct": _num(f["comppct_r"])})
    return {
        "ok": True,
        "pais": "US",
        "suelo_dominante": d["compname"],
        "unidad_cartografica": d["muname"],
        "mukey": d["mukey"],
        "factor_k": round(k_us * K_US_A_MGAP, 3) if k_us is not None else None,
        "factor_k_usda": k_us,
        "tolerancia_t": round(t_us * T_US_A_HA, 1) if t_us is not None else None,
        "tolerancia_t_usda": t_us,
        "pendiente_pct": _num(d["slope_r"]),
        "agua_util_mm": _agua_util_mm(dominante),
        "grupo_hidrologico": d["hydgrp"],
        "drenaje": d["drainagecl"],
        "orden": d["taxorder"],
        "materia_organica_pct": _num(primer["om_r"]),
        "ph": _num(primer["ph1to1h2o_r"]),
        "arcilla_pct": _num(primer["claytotal_r"]),
        "arena_pct": _num(primer["sandtotal_r"]),
        "limo_pct": _num(primer["silttotal_r"]),
        "componentes": [{"nombre": c["nombre"], "pct": c["pct"]} for c in componentes],
    }


def suelo_punto(lat: float, lon: float) -> dict:
    """Suelo de SSURGO en un punto, con las claves de `mgap.suelo_punto`. Cacheado 180 días."""
    clave = f"{lat:.5f},{lon:.5f}"
    guardado = cache.leer("ssurgo_suelo", clave, max_dias=180)
    if guardado:
        return guardado
    base = {"fuente": "USDA-NRCS SSURGO (Soil Data Access)", "lat": lat, "lon": lon}
    try:
        r = httpx.post(URL, json={"query": _consulta(lat, lon), "format": "JSON+COLUMNNAME"}, timeout=TIMEOUT)
        r.raise_for_status()
        tabla = (r.json() or {}).get("Table") or []
    except (httpx.HTTPError, ValueError) as e:
        return {**base, "ok": False, "errores": [f"SSURGO: {e}"]}
    if len(tabla) < 2:
        return {**base, **interpretar_filas([])}
    cols = tabla[0]
    filas = [dict(zip(cols, fila)) for fila in tabla[1:]]
    salida = {**base, **interpretar_filas(filas)}
    if salida["ok"]:
        cache.guardar("ssurgo_suelo", clave, salida)
    return salida


def secciones_por_suelo(geojson: dict, minimo_pct: float = 8.0) -> list[dict]:
    """Parte un campo por las unidades cartográficas de SSURGO que lo cruzan (el par de los grupos CONEAT de un
    padrón en Uruguay). Las unidades que ocupan menos de `minimo_pct` % del campo se suman a la vecina con la que
    comparten más borde. Devuelve [{mukey, muname, geometria}], de la más grande a la más chica."""
    from shapely import wkt
    from shapely.geometry import mapping, shape
    from shapely.ops import unary_union

    campo = shape(geojson).buffer(0)
    q = f"""
SELECT p.mukey, mu.muname, p.mupolygongeo.STAsText() AS wkt
FROM mupolygon p INNER JOIN mapunit mu ON mu.mukey = p.mukey
WHERE p.mupolygonkey IN (SELECT * FROM SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('{campo.wkt}'))
"""
    r = httpx.post(URL, json={"query": q, "format": "JSON+COLUMNNAME"}, timeout=60)
    r.raise_for_status()
    tabla = (r.json() or {}).get("Table") or []
    if len(tabla) < 2:
        return []
    cols = tabla[0]
    por_unidad: dict[str, dict] = {}
    for fila in tabla[1:]:
        f = dict(zip(cols, fila))
        g = wkt.loads(f["wkt"]).buffer(0).intersection(campo)
        if g.is_empty:
            continue
        u = por_unidad.setdefault(f["mukey"], {"mukey": f["mukey"], "muname": f["muname"], "partes": []})
        u["partes"].append(g)
    unidades = [{**u, "g": unary_union(u["partes"])} for u in por_unidad.values()]
    total = campo.area
    unidades.sort(key=lambda u: -u["g"].area)
    grandes = [u for u in unidades if 100 * u["g"].area / total >= minimo_pct] or unidades[:1]
    for chica in [u for u in unidades if u not in grandes]:
        vecina = max(grandes, key=lambda u: u["g"].buffer(1e-5).intersection(chica["g"]).area)
        vecina["g"] = unary_union([vecina["g"], chica["g"]])
    return [{"mukey": u["mukey"], "muname": u["muname"], "geometria": mapping(u["g"])} for u in grandes]


def pendiente_media(unidades: list[dict], pendientes: dict[str, float]) -> float | None:
    """Pendiente del lote: la de cada unidad cartográfica pesada por la superficie que ocupa adentro. `unidades` trae
    {mukey, fraccion}; `pendientes`, la pendiente representativa de cada mukey. Aparte para probarla sin internet."""
    peso = sum(u["fraccion"] for u in unidades if pendientes.get(u["mukey"]) is not None)
    if peso <= 0:
        return None
    return round(sum(u["fraccion"] * pendientes[u["mukey"]] for u in unidades if pendientes.get(u["mukey"]) is not None) / peso, 1)


def _pendientes_de(mukeys: list[str]) -> dict[str, float]:
    """Pendiente representativa de cada unidad: la de sus componentes principales, pesada por su porcentaje."""
    lista = ",".join("'" + "".join(ch for ch in str(m) if ch.isdigit()) + "'" for m in mukeys)
    q = f"SELECT c.mukey, c.comppct_r, c.slope_r FROM component c WHERE c.majcompflag = 'Yes' AND c.mukey IN ({lista})"
    r = httpx.post(URL, json={"query": q, "format": "JSON+COLUMNNAME"}, timeout=TIMEOUT)
    r.raise_for_status()
    tabla = (r.json() or {}).get("Table") or []
    suma: dict[str, list[float]] = {}
    for fila in tabla[1:]:
        f = dict(zip(tabla[0], fila))
        pct, pend = _num(f["comppct_r"]), _num(f["slope_r"])
        if pct and pend is not None:
            a = suma.setdefault(str(f["mukey"]), [0.0, 0.0])
            a[0] += pct * pend
            a[1] += pct
    return {m: v[0] / v[1] for m, v in suma.items() if v[1] > 0}


def suelo_seccion(geojson: dict, lat: float, lon: float) -> dict:
    """Suelo de un lote entero. `suelo_punto` mira un solo punto: en un lote de 50 ha de Iowa cayó en una
    loma de 6 a 10 % que era una parte chica, y la erosión salió con 8 % de pendiente cuando casi todo el lote es de
    0 a 6 %. Acá el suelo es el de la unidad cartográfica que ocupa más superficie adentro del lote, y la pendiente,
    la media de todas las unidades pesada por superficie. Si algo falla, queda el suelo del punto. Cacheado 180 días."""
    import hashlib
    import json

    clave = hashlib.sha1(json.dumps(geojson, sort_keys=True).encode()).hexdigest()[:20]
    guardado = cache.leer("ssurgo_seccion", clave, max_dias=180)
    if guardado:
        return guardado
    try:
        from shapely.geometry import shape

        partes = secciones_por_suelo(geojson, minimo_pct=0)
        if not partes:
            return suelo_punto(lat, lon)
        areas = [shape(x["geometria"]).area for x in partes]
        total = sum(areas) or 1
        unidades = [{"mukey": str(x["mukey"]), "muname": x["muname"], "fraccion": a / total} for x, a in zip(partes, areas)]
        mayor = shape(partes[0]["geometria"]).representative_point()
        suelo = suelo_punto(mayor.y, mayor.x)
        if not suelo.get("ok"):
            return suelo_punto(lat, lon)
        pend = pendiente_media(unidades, _pendientes_de([u["mukey"] for u in unidades]))
        salida = {
            **suelo,
            "pendiente_pct": pend if pend is not None else suelo.get("pendiente_pct"),
            "pendiente_origen": "media del lote por superficie" if pend is not None else "unidad principal",
            "unidades": [{"nombre": u["muname"], "pct": round(100 * u["fraccion"])} for u in unidades[:6]],
        }
        cache.guardar("ssurgo_seccion", clave, salida)
        return salida
    except Exception:  # noqa: BLE001 — Soil Data Access se cae a veces: seguimos con el punto
        return suelo_punto(lat, lon)
