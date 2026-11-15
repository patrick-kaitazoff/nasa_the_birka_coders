"""Humedad del suelo de SMAP L4 (NASA) en un punto del campo, vía AppEEARS o Earth Engine.

Para qué: hasta ahora la humedad del suelo de la app era un cálculo propio (el balance de agua con la
lluvia y la ET0 de POWER). SMAP la mide desde el satélite (banda L, primeros ~5 cm) y el producto L4
la asimila en un modelo para dar, sin huecos, la humedad de la **zona de raíces (0–100 cm)** cada 3 h
a 9 km. Sirve para dos cosas: contrastar el balance de la app con un dato de la NASA independiente, y
decir cómo está el suelo ahora comparado con otros años (el L4 trae el percentil ya calculado).

Producto y capas:
- `Geophysical_Data_sm_rootzone`: humedad de la zona de raíces, m³/m³.
- `Geophysical_Data_sm_rootzone_pctl`: la misma, en percentil (0–100) de su propia climatología.

Fuentes disponibles en orden de prioridad:
1. Caché en disco local (últimos 14 días).
2. Serie guardada del punto puntual en `datos/smap/<clave>.json` (ej. campo de ejemplo bajado de AppEEARS).
3. Grilla nacional de todo Uruguay (`datos/smap_uruguay.json.gz`) generada con Google Earth Engine (~2.100 puntos a 9 km).
4. Pedido a AppEEARS (asincrónico, tarda horas; requiere cuenta de Earthdata).
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
import os
from collections import defaultdict
from pathlib import Path

import httpx
import numpy as np

from .. import cache

API = "https://appeears.earthdatacloud.nasa.gov/api"
PRODUCTO = "SPL4SMGP.008"
CAPAS = ("Geophysical_Data_sm_rootzone", "Geophysical_Data_sm_rootzone_pctl")
INICIO = dt.date(2015, 4, 1)  # SMAP mide
RELLENO = -9999.0


def _clave(lat: float, lon: float) -> str:
    # 9 km de píxel: con 2 decimales (~1 km) puntos del mismo campo reusan el pedido
    return f"{round(lat, 2)},{round(lon, 2)}"


DIR_GUARDADOS = Path(__file__).resolve().parents[1] / "datos" / "smap"
ARCHIVO_GRILLA = Path(__file__).resolve().parents[1] / "datos" / "smap_uruguay.json.gz"
_DATOS_GRILLA: dict | None = None


def guardado(lat: float, lon: float) -> dict | None:
    """Serie bajada de antemano y guardada en el repo (datos/smap/<clave>.json).

    AppEEARS tarda horas con SMAP: para los puntos que ya
    se bajaron no hace falta esperar. Lo arma scripts/guardar_smap.py a partir del CSV de AppEEARS."""
    f = DIR_GUARDADOS / f"{_clave(lat, lon)}.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cargar_grilla() -> dict | None:
    """Carga la grilla de promedios mensuales y días recientes de SMAP para todo Uruguay."""
    global _DATOS_GRILLA
    if _DATOS_GRILLA is not None:
        return _DATOS_GRILLA
    if not ARCHIVO_GRILLA.is_file():
        return None
    try:
        with gzip.open(ARCHIVO_GRILLA, "rt", encoding="utf-8") as f:
            _DATOS_GRILLA = json.load(f)
            return _DATOS_GRILLA
    except (OSError, ValueError):
        return None


def desde_grilla_uruguay(lat: float, lon: float, max_km: float = 8.0) -> dict | None:
    """Busca la celda más cercana en la grilla nacional de SMAP (Google Earth Engine).

    Si el punto está a menos de max_km de un nodo de la grilla de Uruguay, devuelve
    la serie combinada (histórico mensual + últimos 60 días diarios) al instante.
    """
    data = cargar_grilla()
    if not data:
        return None
    puntos = data.get("puntos", [])
    if not puntos:
        return None

    lats = np.array([p[0] for p in puntos])
    lons = np.array([p[1] for p in puntos])
    dlat = (lats - lat) * 111.0
    dlon = (lons - lon) * (111.0 * np.cos(np.radians(lat)))
    dists = np.hypot(dlat, dlon)
    i_min = int(np.argmin(dists))
    if dists[i_min] > max_km:
        return None

    meses = data.get("meses", [])
    sm_m = data["sm_mensual"][i_min]
    pc_m = data["pc_mensual"][i_min]
    dias = data.get("dias", [])
    sm_d = data.get("sm_diario", [])[i_min] if "sm_diario" in data else []
    pc_d = data.get("pc_diario", [])[i_min] if "pc_diario" in data else []

    primer_mes_diario = dias[0][:7] if dias else None

    serie = []
    for m, sm, pc in zip(meses, sm_m, pc_m):
        if sm is not None and (not primer_mes_diario or m < primer_mes_diario):
            serie.append({"fecha": f"{m}-15", "sm": sm, "pctl": pc, "mensual": True})

    for d, sm, pc in zip(dias, sm_d, pc_d):
        if sm is not None:
            serie.append({"fecha": d, "sm": sm, "pctl": pc})

    if not serie:
        return None

    mes_hasta = meses[-1] if meses else "?"
    fuente = f"NASA SMAP L4 ({PRODUCTO}) vía Google Earth Engine (hasta {mes_hasta})"
    return {"estado": "listo", "serie": serie, "fuente": fuente}


def _credenciales() -> tuple[str, str] | None:
    u, p = os.environ.get("EARTHDATA_USER"), os.environ.get("EARTHDATA_PASS")
    return (u, p) if u and p else None


def _token(cred: tuple[str, str]) -> str:
    guardado = cache.leer("appeears", "token", max_dias=1.5)  # dura ~48 h
    if guardado:
        return guardado
    r = httpx.post(f"{API}/login", auth=cred, timeout=60)
    r.raise_for_status()
    token = r.json()["token"]
    cache.guardar("appeears", "token", token)
    return token


def _pedido(lat: float, lon: float, hasta: dt.date) -> dict:
    fmt = "%m-%d-%Y"  # AppEEARS pide MM-DD-AAAA
    return {
        "task_type": "point",
        "task_name": f"fieldshift_smap_{_clave(lat, lon)}",
        "params": {
            "dates": [{"startDate": INICIO.strftime(fmt), "endDate": hasta.strftime(fmt)}],
            "layers": [{"product": PRODUCTO, "layer": c} for c in CAPAS],
            "coordinates": [{"id": "campo", "latitude": lat, "longitude": lon}],
        },
    }


def leer_csv(texto: str) -> list[dict]:
    """CSV de punto de AppEEARS → [{"fecha", "sm", "pctl"}] diario (promedio de las pasadas de 3 h).

    Busca la columna de fecha y las de cada capa por nombre (terminan en el nombre de la capa).
    Descarta el valor de relleno (-9999) y lo que está fuera de rango.
    """
    filas = list(csv.DictReader(io.StringIO(texto)))
    if not filas:
        return []
    cols = list(filas[0].keys())
    c_fecha = next((c for c in cols if c.strip().lower() == "date"), None)
    c_sm = next((c for c in cols if c.endswith("sm_rootzone")), None)
    c_pc = next((c for c in cols if c.endswith("sm_rootzone_pctl")), None)
    if not c_fecha or not c_sm:
        raise ValueError(f"El CSV de AppEEARS no tiene las columnas esperadas: {cols}")
    por_dia: dict[str, list[tuple[float | None, float | None]]] = defaultdict(list)

    def num(v: str | None, lo: float, hi: float) -> float | None:
        try:
            x = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return x if x != RELLENO and lo <= x <= hi else None

    for f in filas:
        dia = (f.get(c_fecha) or "")[:10]
        if len(dia) != 10:
            continue
        por_dia[dia].append((num(f.get(c_sm), 0, 0.9), num(f.get(c_pc), 0, 100) if c_pc else None))
    salida = []
    for dia in sorted(por_dia):
        sm = [a for a, _ in por_dia[dia] if a is not None]
        pc = [b for _, b in por_dia[dia] if b is not None]
        if sm:
            salida.append({"fecha": dia, "sm": round(sum(sm) / len(sm), 4),
                           "pctl": round(sum(pc) / len(pc), 1) if pc else None})
    return salida


def _bajar_resultado(token: str, tarea: str) -> list[dict]:
    h = {"Authorization": f"Bearer {token}"}
    r = httpx.get(f"{API}/bundle/{tarea}", headers=h, timeout=60)
    r.raise_for_status()
    csvs = [a for a in r.json().get("files", []) if a.get("file_name", "").lower().endswith(".csv")]
    # primero el que nombra al producto; los demás (lista de archivos, pedido) no tienen las columnas
    csvs.sort(key=lambda a: "SPL4SMGP" not in a.get("file_name", ""))
    for a in csvs:
        r = httpx.get(f"{API}/bundle/{tarea}/{a['file_id']}", headers=h, timeout=180, follow_redirects=True)
        r.raise_for_status()
        try:
            serie = leer_csv(r.text)
        except ValueError:
            continue
        if serie:
            return serie
    raise ValueError("La tarea de AppEEARS terminó sin un CSV de SMAP que se pueda leer.")


def estado(lat: float, lon: float) -> dict:
    """No espera nunca. Devuelve {"estado": "listo"|"pendiente"|"sin_cuenta"|"error"...}.

    Orden de resolución:
    1. Caché en memoria/disco local (últimos 14 días).
    2. Serie guardada del punto puntual (ej. campo de ejemplo de AppEEARS).
    3. Grilla de todo Uruguay (Earth Engine, punto más cercano si está a <= ~8 km).
    4. Pedido a AppEEARS (requiere cuenta de NASA Earthdata).
    """
    clave = _clave(lat, lon)
    listo = cache.leer("smap", clave, max_dias=14)  # el dato nuevo llega de a uno por día
    if listo:
        return {"estado": "listo", "serie": listo, "fuente": f"NASA SMAP L4 ({PRODUCTO}) vía AppEEARS"}
    previo = guardado(lat, lon)
    if previo and previo.get("serie"):
        return {"estado": "listo", "serie": previo["serie"],
                "fuente": f"NASA SMAP L4 ({PRODUCTO}) vía AppEEARS, bajada el {previo.get('bajado', '?')}"}
    nacional = desde_grilla_uruguay(lat, lon, max_km=8.0)
    if nacional is not None:
        return nacional
    cred = _credenciales()
    if not cred:
        return {"estado": "sin_cuenta", "motivo": "Falta configurar la cuenta de NASA Earthdata en el servidor."}
    try:
        token = _token(cred)
        h = {"Authorization": f"Bearer {token}"}
        tarea = cache.leer("smap_tarea", clave, max_dias=2)
        if not tarea:
            hasta = dt.date.today() - dt.timedelta(days=5)  # el L4 sale con unos días de atraso
            r = httpx.post(f"{API}/task", json=_pedido(lat, lon, hasta), headers=h, timeout=60)
            r.raise_for_status()
            tarea = r.json()["task_id"]
            cache.guardar("smap_tarea", clave, tarea)
            return {"estado": "pendiente", "tarea": tarea}
        r = httpx.get(f"{API}/task/{tarea}", headers=h, timeout=60)
        r.raise_for_status()
        est = r.json().get("status")
        if est == "done":
            serie = _bajar_resultado(token, tarea)
            cache.guardar("smap", clave, serie)
            return {"estado": "listo", "serie": serie, "fuente": f"NASA SMAP L4 ({PRODUCTO}) vía AppEEARS"}
        if est == "error":
            cache.guardar("smap_tarea", clave, None)
            return {"estado": "error", "motivo": "AppEEARS no pudo armar la serie de SMAP."}
        return {"estado": "pendiente", "tarea": tarea, "detalle": est}
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return {"estado": "error", "motivo": f"No pude pedir SMAP a la NASA: {e}"}


def esperar(lat: float, lon: float, cada_s: int = 30, max_min: int = 90) -> dict:
    """Para scripts (armar el campo de ejemplo): pide y espera hasta que esté."""
    import time

    fin = time.time() + max_min * 60
    while True:
        r = estado(lat, lon)
        if r["estado"] != "pendiente" or time.time() > fin:
            return r
        time.sleep(cada_s)
