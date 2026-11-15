"""Caché en disco para respuestas de APIs externas (NASA POWER, MODIS, MGAP).

Las APIs públicas son lentas (MODIS ~20 s cada 10 fechas, MGAP ~20 s por consulta) y no hay
que castigarlas con pedidos repetidos. Cada respuesta se guarda como JSON bajo `cache/`,
con una clave que sale del pedido.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

# En local, app/backend/cache. En Vercel el disco del proyecto es de solo lectura y lo único escribible es
# /tmp (se borra cuando se recicla la instancia: ahí la caché es solo un ahorro, no un archivo).
# FIELDSHIFT_CACHE permite elegir otra carpeta.
if os.environ.get("FIELDSHIFT_CACHE"):
    CARPETA = Path(os.environ["FIELDSHIFT_CACHE"])
elif os.environ.get("VERCEL"):
    CARPETA = Path("/tmp/fieldshift-cache")
else:
    CARPETA = Path(__file__).resolve().parent.parent / "cache"


# Lo que tiene que verse igual desde todas las instancias de Vercel (Runtime Cache compartida en la región):
# 1. Clima de NASA POWER: 35 años diarios (~720 KB, entra holgado en el límite de 2 MB de Vercel).
# Evita que el pedido anticipado caiga en una instancia y el análisis en otra repitiendo la descarga.
# 2. Suelos y catastro del MGAP: padrones, contornos, suelos CONEAT y factor R.
# 3. Verdor satelital: series quincenales MODIS (2 años y 26 años de historia) y agrupamientos HLS.
# 4. Humedad del suelo (SMAP L4) y tokens/tareas de AppEEARS.
# 5. Análisis agronómico guardado y caminos de OpenStreetMap.
COMPARTIDOS = {
    # Clima (NASA POWER) y lluvia
    "power",
    "imerg",
    # Suelos y catastro (MGAP)
    "mgap_padron",
    "mgap_suelo",
    "mgap_suelos_area",
    "mgap_r",
    "mgap_departamentos",
    # Verdor satelital (MODIS y HLS)
    "modis_ndvi",
    "modis_historia",
    "modis_historia_tarea",
    "hls_ndvi",
    "hls_fechas",
    "partes_hls",
    # Humedad y tareas AppEEARS
    "smap",
    "smap_tarea",
    "gldas",
    "appeears",
    # Estado de análisis y caminos
    "analisis",
    "caminos_osm",
}
_TTL_COMPARTIDO = 14 * 86400


def _compartida():
    if not os.environ.get("VERCEL"):
        return None
    try:
        from vercel.functions import RuntimeCache

        return RuntimeCache(namespace="fieldshift-cache")
    except Exception:  # noqa: BLE001
        return None


def _ruta(espacio: str, clave: str) -> Path:
    h = hashlib.sha1(clave.encode("utf-8")).hexdigest()[:20]
    return CARPETA / espacio / f"{h}.json"


def leer(espacio: str, clave: str, max_dias: float | None = None) -> Any | None:
    ruta = _ruta(espacio, clave)
    rc = _compartida() if espacio in COMPARTIDOS else None
    if rc is not None:
        try:
            g = rc.get(f"{espacio}:{ruta.stem}")
        except Exception:  # noqa: BLE001
            g = None
        if g is not None:
            if max_dias is not None and time.time() - g.get("t", 0) > max_dias * 86400:
                return None
            val = g.get("v")
            # Populamos también el /tmp local de esta instancia para acelerar lecturas posteriores
            if not ruta.exists() and val is not None:
                try:
                    ruta.parent.mkdir(parents=True, exist_ok=True)
                    tmp = ruta.with_suffix(".tmp")
                    tmp.write_text(json.dumps(val, ensure_ascii=False), encoding="utf-8")
                    tmp.replace(ruta)
                except Exception:
                    pass
            return val

    if not ruta.exists():
        return None
    if max_dias is not None and (time.time() - ruta.stat().st_mtime) > max_dias * 86400:
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def guardar(espacio: str, clave: str, valor: Any) -> None:
    ruta = _ruta(espacio, clave)
    rc = _compartida() if espacio in COMPARTIDOS else None
    if rc is not None:
        try:
            rc.set(f"{espacio}:{ruta.stem}", {"t": time.time(), "v": valor}, {"ttl": _TTL_COMPARTIDO})
        except Exception:  # noqa: BLE001
            pass  # queda al menos en /tmp o disco local
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(valor, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ruta)
