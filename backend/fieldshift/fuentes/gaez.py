"""Aptitud de cada cultivo en la zona del campo según FAO/IIASA GAEZ v4 (Global Agro-Ecological Zones).

Qué es: la evaluación agroecológica de la FAO y el IIASA (versión 4, 2021), que combina clima, suelo y pendiente
para decir qué tan apta es la tierra para cada cultivo. Acá se usa como segunda opinión, independiente del motor de la
app, sobre los cultivos de cada rotación.

De dónde sale: `datos/gaez_uruguay.json`, una grilla de todo Uruguay bajada con `scripts/extraer_gaez_uruguay.py`
(5 minutos de arco, ~9 km; secano, nivel de insumo alto). En cada celda, la clase y el índice (0-100) de aptitud de
toda la tierra de la celda, con el clima de 2011-2040 y también con el de 1981-2010, para decir si la clase cambia. GAEZ incluye el efecto
del CO2 sobre los cultivos, que explica parte de las subas.

Clases: 1 muy alta, 2 alta, 3 buena, 4 media, 5 moderada, 6 marginal, 7 muy marginal, 8 no apta.

Licencia: CC BY-NC-SA 3.0 IGO (atribución a FAO e IIASA, sin uso comercial sin acuerdo con la FAO).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_ARCHIVO = Path(__file__).resolve().parent.parent / "datos" / "gaez_uruguay.json"

CLASES = {1: "muy alta", 2: "alta", 3: "buena", 4: "media", 5: "moderada", 6: "marginal", 7: "muy marginal",
          8: "no apta"}

# Cultivo de la app → cultivo de GAEZ. Pradera, verdeos, coberturas y campo natural no tienen equivalente.
DE_LA_APP = {
    "soja": "soja", "soja2": "soja", "maiz": "maiz", "maiz2": "maiz", "trigo": "trigo", "cebada": "cebada",
    "sorgo": "sorgo", "sorgo_forrajero": "sorgo", "girasol": "girasol", "colza": "colza", "alfalfa": "alfalfa",
}
NOMBRES = {"soja": "Soja", "maiz": "Maíz", "trigo": "Trigo", "cebada": "Cebada", "sorgo": "Sorgo",
           "girasol": "Girasol", "colza": "Colza", "alfalfa": "Alfalfa"}


@lru_cache(maxsize=1)
def cargar_datos_gaez() -> dict[str, Any]:
    try:
        return json.loads(_ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def aptitud_punto(lat: float, lon: float) -> dict[str, dict]:
    """Clase e índice de GAEZ de cada cultivo en la celda del punto. Vacío fuera de Uruguay o sin datos."""
    datos = cargar_datos_gaez()
    g = datos.get("grilla")
    if not g:
        return {}
    fila = int((g["norte"] - lat) // g["paso_grados"])
    col = int((lon - g["oeste"]) // g["paso_grados"])
    if not (0 <= fila < g["alto"] and 0 <= col < g["ancho"]):
        return {}
    i = fila * g["ancho"] + col
    salida = {}
    antes = datos.get("cultivos_1981_2010") or {}
    for cultivo, capa in (datos.get("cultivos") or {}).items():
        clase = int(capa["clase"][i])
        if clase in CLASES:
            salida[cultivo] = {"clase": clase, "aptitud": CLASES[clase], "indice": capa["indice"][i]}
            a = antes.get(cultivo)
            if a and int(a["clase"][i]) in CLASES:
                salida[cultivo] |= {"clase_antes": int(a["clase"][i]), "aptitud_antes": CLASES[int(a["clase"][i])],
                                    "indice_antes": a["indice"][i]}
    return salida


def aptitud_rotacion(cultivos_app: list[str], lat: float, lon: float) -> list[dict]:
    """Aptitud de los cultivos de una rotación (sin repetir y en el orden en que aparecen)."""
    en_punto = aptitud_punto(lat, lon)
    vistos: list[str] = []
    for c in cultivos_app:
        g = DE_LA_APP.get(c)
        if g and g in en_punto and g not in vistos:
            vistos.append(g)
    return [{"cultivo": g, "nombre": NOMBRES[g], **en_punto[g]} for g in vistos]


def frases_rotacion(cultivos_app: list[str], lat: float, lon: float) -> list[str]:
    """Renglones de evidencia para la tarjeta de la rotación: uno por clase de aptitud, de la mejor a la peor.

    Ej.: «FAO GAEZ v4 en la zona (secano, clima 2011-2040 según 5 modelos, celda de ~9 km): aptitud alta (índice 70-76
    de 100) para Trigo y Soja.» y, si alguna clase cambió, «Con el clima de 1981-2010, GAEZ daba aptitud buena para Trigo y
    Soja.» Los cultivos van en una lista simple para que el traductor al inglés los reconozca."""
    por_clase: dict[int, list[dict]] = {}
    for f in aptitud_rotacion(cultivos_app, lat, lon):
        por_clase.setdefault(f["clase"], []).append(f)
    salida = []
    for clase in sorted(por_clase):
        filas = por_clase[clase]
        nombres = [f["nombre"] for f in filas]
        lista = nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]
        ind = sorted({f["indice"] for f in filas})
        rango = f"{ind[0]}" if len(ind) == 1 else f"{ind[0]}-{ind[-1]}"
        salida.append(f"FAO GAEZ v4 en la zona (secano, clima 2011-2040 según 5 modelos, celda de ~9 km): aptitud "
                      f"{CLASES[clase]} (índice {rango} de 100) para {lista}.")
    antes: dict[int, list[str]] = {}
    for f in aptitud_rotacion(cultivos_app, lat, lon):
        if f.get("clase_antes") and f["clase_antes"] != f["clase"]:
            antes.setdefault(f["clase_antes"], []).append(f["nombre"])
    for clase in sorted(antes):
        nombres = antes[clase]
        lista = nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]
        salida.append(f"Con el clima de 1981-2010, GAEZ daba aptitud {CLASES[clase]} para {lista}.")
    return salida
