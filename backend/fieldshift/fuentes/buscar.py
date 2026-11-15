"""Buscador del paso 1: un pueblo, un paraje, una calle o «ruta 5 km 200», y la
respuesta con su departamento, para ir con el mapa ahí.

- Ruta y kilómetro: entre los dos mojones del MTOP más cercanos (datos/mojones_uy.json, scripts/actualizar_mojones.py).
  El servicio de la IDE reconoce la ruta y el km pero devuelve el punto en 0, 0.
- Lo demás: el Sistema Único de Direcciones de la IDE (direcciones.ide.uy, /api/v1/geocode/candidates y /find), que
  trae localidades, parajes y puntos de interés con su departamento. Las calles con número se ubican con /find.
- Si la IDE no da nada con coordenadas: Nominatim (OpenStreetMap), una sola consulta, solo en Uruguay.
- Si tampoco: Nominatim en EE. UU., con el
  condado y el estado en lugar del departamento. Es una consulta más solo cuando Uruguay no dio nada.
- Los nombres de pueblos se escriben como en OpenStreetMap (con tildes) si hay uno igual a menos de 15 km.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import httpx
from shapely.geometry import Point, shape
from shapely.prepared import prep

from .. import cache

DATOS = Path(__file__).resolve().parents[1] / "datos"
IDE = "https://direcciones.ide.uy/api/v1/geocode"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
AGENTE = {"User-Agent": "FieldShift/1.0 (asesor de rotaciones, NASA Space Apps Challenge 2026)"}
MAX = 6

# «ruta 5 km 200», «R5 km 200,5», «ruta 26 200», «ruta 8, kilómetro 26»
RE_RUTA = re.compile(r"^\s*(?:ruta|rta\.?|r)\s*n?[º°o.]?\s*(\d{1,3}|ib)\s*[,;-]?\s*(?:(?:km|kil[oó]metro)s?\.?\s*)?(\d{1,3}(?:[.,]\d+)?)\s*$", re.I)
RE_INTERBALNEARIA = re.compile(r"^\s*(?:ruta\s*)?interbalnearia\s*[,;-]?\s*(?:(?:km|kil[oó]metro)s?\.?\s*)?(\d{1,3}(?:[.,]\d+)?)\s*$", re.I)


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").upper().strip()


def _titulo(s: str) -> str:
    chicas = {"de", "del", "la", "las", "los", "y", "el"}
    palabras = s.lower().split()
    return " ".join(p if (i and p in chicas) else p[:1].upper() + p[1:] for i, p in enumerate(palabras))


@lru_cache(maxsize=1)
def _departamentos():
    fc = json.loads((DATOS / "departamentos_uy.json").read_text(encoding="utf-8"))
    return [(f["properties"]["nombre"], prep(shape(f["geometry"]))) for f in fc["features"]]


def departamento_de(lat: float, lon: float) -> str | None:
    p = Point(lon, lat)
    for nombre, geo in _departamentos():
        if geo.contains(p):
            return _titulo(nombre)
    return None


@lru_cache(maxsize=1)
def _mojones() -> dict[str, list[list[float]]]:
    return json.loads((DATOS / "mojones_uy.json").read_text(encoding="utf-8"))["rutas"]


@lru_cache(maxsize=1)
def _lugares() -> dict[str, list[dict]]:
    """Nombres de OpenStreetMap por nombre sin tildes, para escribir bien lo que la IDE da en mayúsculas."""
    d: dict[str, list[dict]] = {}
    for l in json.loads((DATOS / "lugares_uy.json").read_text(encoding="utf-8"))["lugares"]:
        d.setdefault(_sin_tildes(l["n"]), []).append(l)
    return d


def _km_entre(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = (a[0] - b[0]) * 111.0
    dx = (a[1] - b[1]) * 111.0 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)


def _nombre_lindo(nombre_ide: str, lat: float, lon: float) -> str:
    for l in _lugares().get(_sin_tildes(nombre_ide), []):
        if _km_entre((lat, lon), (l["lat"], l["lon"])) < 15:
            return l["n"]
    return _titulo(nombre_ide)


def por_ruta(ruta: str, km: float) -> list[dict]:
    """El punto de la ruta en ese kilómetro, entre los dos mojones que lo rodean. La ruta puede estar en varios
    tramos con su propia numeración («53-S1», «53-S2»): se prueba en cada uno."""
    salida: list[dict] = []
    # el MTOP guarda algunas rutas por tramos («53-S1») o por mano en las dobles vías cerca de Montevideo («8-PAN»,
    # «8-MVD», «1-COL»): entran todos menos los ramales («5-RAM15») y los accesos
    for nombre, lista in _mojones().items():
        if nombre != ruta and not re.fullmatch(rf"{ruta}-(?!RAM)[A-Z]+\d*", nombre):
            continue
        punto = None
        for (k1, la1, lo1), (k2, la2, lo2) in zip(lista, lista[1:]):
            if k1 <= km <= k2 and k2 - k1 <= 15:
                f = 0 if k2 == k1 else (km - k1) / (k2 - k1)
                punto = (la1 + (la2 - la1) * f, lo1 + (lo2 - lo1) * f)
                break
        if punto is None:
            # fuera del tramo: el mojón más cercano, si está a menos de 3 km
            k, la, lo = min(lista, key=lambda x: abs(x[0] - km))
            if abs(k - km) <= 3:
                punto = (la, lo)
        if punto:
            lat, lon = punto
            # las dos manos de una doble vía dan casi el mismo punto: queda uno
            if any(_km_entre((lat, lon), (r["lat"], r["lon"])) < 1.5 for r in salida):
                continue
            depto = departamento_de(lat, lon)
            salida.append({"nombre": f"Ruta {ruta}, km {km:g}".replace(".", ","), "departamento": depto,
                           "lat": round(lat, 6), "lon": round(lon, 6), "tipo": "ruta", "zoom": 14})
    return salida


def _ide(q: str) -> list[dict]:
    # «sarandi 300 durazno» → «sarandi 300, durazno»: con la coma después del número la IDE separa la calle del
    # pueblo y encuentra la dirección; sin ella busca todo junto como nombre de calle
    if "," not in q:
        q = re.sub(r"^(.+\s\d{1,5})\s+([^\d,]+)$", r"\1, \2", q)
    q = re.sub(r"^(calle|c\.)\s+", "", q, flags=re.I)
    with httpx.Client(timeout=12, headers=AGENTE) as cli:
        cand = cli.get(f"{IDE}/candidates", params={"q": q, "limit": 10}).json()
        salida = []
        resueltas = 0
        for c in cand:
            tipo = c.get("type")
            lat, lon = c.get("lat") or 0, c.get("lng") or 0
            if tipo == "RUTAyKM":
                continue  # lo resuelve por_ruta con los mojones
            if tipo in ("CALLEyPORTAL", "CALLE") and not lat and resueltas < 3 and c.get("idCalle"):
                resueltas += 1
                params = {"type": tipo, "idcalle": c["idCalle"], "departamento": c.get("departamento") or "",
                          "localidad": c.get("localidad") or ""}
                if tipo == "CALLEyPORTAL":
                    params["portal"] = c.get("portalNumber") or ""  # con «portal» vacío, la calle sola no aparece
                try:
                    r = cli.get(f"{IDE}/find", params=params).json()
                except (httpx.HTTPError, ValueError):
                    r = []
                r = r if isinstance(r, list) else []  # si no encuentra, devuelve un objeto de error
                if r and r[0].get("lat"):
                    lat, lon = r[0]["lat"], r[0]["lng"]
            if not lat or not lon:
                continue
            # el departamento de nuestros polígonos (con tildes, el mismo del mapa); si cae fuera, el de la IDE
            depto = departamento_de(lat, lon) or (_titulo(c["departamento"]) if c.get("departamento") else None)
            if tipo == "LOCALIDAD":
                nombre, zoom = _nombre_lindo(c.get("localidad") or c["address"].split(",")[0], lat, lon), 13
            elif tipo == "POI":
                nombre, zoom = _titulo(c["address"].split(" - ")[0].split(",")[0]), 16
            else:
                partes = [p.strip() for p in c["address"].split(",")]
                nombre = _titulo(partes[0]) + (f", {_titulo(partes[1])}" if len(partes) > 2 else "")
                zoom = 16
            salida.append({"nombre": nombre, "departamento": depto, "lat": round(lat, 6), "lon": round(lon, 6),
                           "tipo": {"LOCALIDAD": "localidad", "POI": "lugar"}.get(tipo, "calle"), "zoom": zoom})
        # primero los pueblos y ciudades (o las calles, si se escribió un número de puerta); los «puntos de interés»
        # (sucursales del Correo, radios…) solo si no hay otra cosa; sin repetidos (mismo nombre en el mismo lugar)
        con_numero = bool(re.search(r"\d", q))
        orden = {"calle": 0, "localidad": 1} if con_numero else {"localidad": 0, "calle": 1}
        salida.sort(key=lambda r: orden.get(r["tipo"], 3))
        if any(r["tipo"] != "lugar" for r in salida):
            salida = [r for r in salida if r["tipo"] != "lugar"]
        unicos: list[dict] = []
        for r in salida:
            if not any(u["nombre"] == r["nombre"] and _km_entre((u["lat"], u["lon"]), (r["lat"], r["lon"])) < 2 for u in unicos):
                unicos.append(r)
        return unicos


def _nominatim(q: str, pais: str = "uy") -> list[dict]:
    r = httpx.get(NOMINATIM, params={"q": q, "format": "jsonv2", "countrycodes": pais, "limit": 5, "accept-language": "es",
                                     "addressdetails": 1},
                  headers=AGENTE, timeout=12).json()
    salida = []
    for x in r:
        lat, lon = float(x["lat"]), float(x["lon"])
        if pais == "us":
            dire = x.get("address") or {}
            zona = ", ".join(v for v in (dire.get("county"), dire.get("state")) if v) or None
        else:
            zona = departamento_de(lat, lon)
        salida.append({"nombre": x.get("name") or x["display_name"].split(",")[0], "departamento": zona,
                       "lat": round(lat, 6), "lon": round(lon, 6), "tipo": "calle" if x.get("category") == "highway" else "lugar",
                       "zoom": 15})
    return salida


def buscar(q: str) -> list[dict]:
    q = re.sub(r"\s+", " ", q or "").strip()[:120]
    if len(q) < 2:
        return []
    m = RE_RUTA.match(q)
    if m:
        ruta = "200" if m.group(1).upper() == "IB" else str(int(m.group(1)))
        return por_ruta(ruta, float(m.group(2).replace(",", ".")))
    m = RE_INTERBALNEARIA.match(q)
    if m:
        return por_ruta("200", float(m.group(1).replace(",", ".")))
    clave = _sin_tildes(q)
    guardado = cache.leer("buscar_lugar", clave, max_dias=30)
    if guardado is not None:
        return guardado
    try:
        res = _ide(q)
    except (httpx.HTTPError, ValueError):
        res = []
    if not res:
        try:
            res = _nominatim(q)
        except (httpx.HTTPError, ValueError):
            res = []
    if not res:
        try:
            res = _nominatim(q, "us")
        except (httpx.HTTPError, ValueError):
            res = []
    res = res[:MAX]
    if res:
        cache.guardar("buscar_lugar", clave, res)
    return res
