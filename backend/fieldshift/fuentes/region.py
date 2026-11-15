"""En qué país cae el campo, para elegir los datos de tierra de cada uno.

Los datos de la NASA son globales, pero el suelo, la erosión oficial, el calendario de siembra y el historial de
cultivos vienen de cada país:

- Uruguay ("UY"): suelo y factor R del MGAP (CONEAT), calendario del hemisferio sur.
- Estados Unidos continental ("US"): suelo de SSURGO (USDA-NRCS), historial del Cropland Data Layer (USDA-NASS) y
  calendario del hemisferio norte.
- Cualquier otro lugar (""): solo los datos globales de la NASA y valores típicos, con el calendario de su hemisferio.

Se decide con rectángulos y no con los límites exactos: alcanza para un campo, y en la frontera con Brasil o
Argentina el servicio del MGAP simplemente no devuelve nada y la app sigue con los valores típicos.
"""

from __future__ import annotations

# (lat mín, lat máx, lon mín, lon máx)
_URUGUAY = (-35.1, -30.0, -58.5, -53.0)
# Los 48 estados contiguos. Deja afuera Alaska y Hawái, que SSURGO cubre pero el CDL no del todo.
_EEUU = (24.4, 49.4, -125.0, -66.9)
# El rectángulo de EE. UU. agarra el sur de Canadá entre los Grandes Lagos (Ontario llega a 42° N) y el norte de
# México no entra porque arranca en 24,4° N recién al este del golfo; para un campo alcanza: SSURGO devuelve vacío
# fuera de EE. UU. y la app sigue con los valores típicos.


def _dentro(lat: float, lon: float, caja: tuple[float, float, float, float]) -> bool:
    return caja[0] <= lat <= caja[1] and caja[2] <= lon <= caja[3]


def pais(lat: float, lon: float) -> str:
    """"UY", "US" o "" (otro lugar)."""
    if _dentro(lat, lon, _URUGUAY):
        return "UY"
    if _dentro(lat, lon, _EEUU):
        return "US"
    return ""


def hemisferio(lat: float) -> str:
    """"sur" o "norte": define el calendario de siembra y el año agrícola."""
    return "sur" if lat < 0 else "norte"
