"""Estado compartido entre el chat, el análisis y la app: el campo y su último análisis.

El campo vive en el navegador (fuente de verdad) y viaja en cada pedido. El último análisis se
guarda acá por id de campo, para que el chat y el plan lo reusen sin recalcular.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from .. import cache

_ANALISIS: dict[str, dict] = {}


def guardar_analisis(campo_id: str, resultado: dict) -> None:
    _ANALISIS[campo_id] = resultado
    cache.guardar("analisis", campo_id, resultado)


def analisis_de(campo_id: str) -> dict | None:
    if campo_id in _ANALISIS:
        return _ANALISIS[campo_id]
    r = cache.leer("analisis", campo_id)
    if r:
        _ANALISIS[campo_id] = r
    return r


def fusionar(base: Any, cambios: Any) -> Any:
    """Mezcla profunda de diccionarios; las listas se reemplazan, salvo `secciones`, que se
    mezclan por id."""
    if isinstance(base, dict) and isinstance(cambios, dict):
        out = copy.deepcopy(base)
        for k, v in cambios.items():
            if k == "secciones" and isinstance(v, list) and isinstance(out.get(k), list):
                out[k] = fusionar_secciones(out[k], v)
            else:
                out[k] = fusionar(out.get(k), v)
        return out
    return copy.deepcopy(cambios)


def fusionar_secciones(actuales: list[dict], cambios: list[dict]) -> list[dict]:
    por_id = {s.get("id"): s for s in actuales}
    orden = [s.get("id") for s in actuales]
    for c in cambios:
        sid = c.get("id")
        if sid in por_id:
            por_id[sid] = fusionar(por_id[sid], c)
        else:
            por_id[sid] = c
            orden.append(sid)
    return [por_id[i] for i in orden]


def resumen_campo(campo: dict) -> str:
    """Lo que el modelo necesita saber del campo, sin las geometrías."""
    secs = []
    for s in campo.get("secciones") or []:
        secs.append({
            "id": s.get("id"), "nombre": s.get("nombre"), "area_ha": s.get("area_ha"),
            "historial": s.get("historial"), "problemas": s.get("problemas"), "notas": s.get("notas"),
            "tiene_analisis_suelo": bool(s.get("analisis_suelo")),
        })
    r = {
        "nombre": campo.get("nombre"),
        "ubicacion": campo.get("ubicacion"),
        "area_ha": campo.get("area_ha"),
        "tiene_contorno": bool(campo.get("contorno")),
        "secciones": secs,
        "sistema": campo.get("sistema"),
        "experiencia": campo.get("experiencia"),
        "objetivos": campo.get("objetivos"),
        "restricciones": campo.get("restricciones"),
        "margenes": campo.get("margenes"),
        "analisis_suelo_general": campo.get("analisis_suelo_general"),
        "estacion": (campo.get("estacion") or {}).get("comparacion", {}).get("conclusion") if campo.get("estacion") else None,
        "pasos_omitidos": campo.get("pasos_omitidos"),
    }
    return json.dumps({k: v for k, v in r.items() if v not in (None, [], {}, "")}, ensure_ascii=False)


def resumen_analisis(res: dict) -> dict:
    """Versión compacta del análisis para el modelo: números clave y las 5 filas."""
    cl = res["clima"]
    out = {
        "clima": {
            "periodo": cl["periodo"],
            "lluvia_anual_mm": cl["erosividad"]["lluvia_anual_mm"],
            "meses_lluvia_erosiva": cl["erosividad"]["meses_pico"],
            "tendencia": {k: cl["tendencia"][k] for k in ("periodo_antes", "periodo_ahora", "lluvia_anual", "dias_calor_verano", "ultima_helada", "primera_helada", "cultivos")},
            "zafra_actual": cl["zafra_actual"],
        },
        "factor_r": res["factor_r"]["fuente"],
        "secciones": [],
        "plan": {
            "erosion_media_actual": res["plan"]["erosion_media_actual"],
            "erosion_media_plan": res["plan"]["erosion_media_plan"],
            "asignacion": [{"seccion": a["seccion"], "rotacion": a["rotacion"], "primeras_temporadas": a["cultivos"][:4]} for a in res["plan"]["secciones"]],
            "temporadas": [t["etiqueta"] for t in res["plan"]["temporadas"][:4]],
        },
    }
    for s in res["secciones"]:
        sec = {
            "id": s["id"], "nombre": s["nombre"], "area_ha": s["area_ha"],
            "suelo": {k: s["suelo"].get(k) for k in ("grupo_coneat", "suelo_dominante", "factor_k", "tolerancia_t", "pendiente_pct", "indice_coneat")},
            "agua_util_mm": s["agua_util_mm"],
            "analisis_suelo": s["analisis_suelo"].get("alertas"),
            "opciones": [],
        }
        for e in ([s["actual"]] if s["actual"] else []) + s["alternativas"]:
            sec["opciones"].append({
                "id": e["id"], "nombre": e["nombre"], "es_actual": bool(e.get("es_actual")),
                "puntaje": e["puntaje_total"], "puntajes": e["puntajes"],
                "erosion_t_ha": e["erosion"]["a_t_ha"], "tolerancia": e["erosion"]["tolerancia_t"],
                "cumple": e["erosion"]["cumple"], "meses_descubierto": e["meses_descubierto"],
                "riesgo_seca": e["riesgo"]["seca"], "carbono": e["carbono"]["tendencia"],
                "explicacion": e.get("explicacion"),
            })
        out["secciones"].append(sec)
    return out
