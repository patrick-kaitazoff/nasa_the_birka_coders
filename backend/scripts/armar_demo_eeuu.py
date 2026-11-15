"""Arma el campo de ejemplo de EE. UU.: 137 ha de maíz-soja en el condado de Madison, Iowa, con la
entrevista ya respondida y el análisis corrido. Lo guarda en frontend/public/ejemplos/campo_demo_eeuu.fieldshift.json
(la app lo abre con ?demo=us o con «Ver un campo en EE. UU.» en el chat).

Lo real: el contorno (píxeles contiguos del Cropland Data Layer con la misma secuencia de 2023 a 2025, en
`ejemplos/campo_iowa_madison.geojson`), las secciones (unidades de suelo de SSURGO), lo que se sembró cada año (CDL),
el clima y el satélite (NASA). Lo inventado: el productor, su experiencia, sus objetivos y sus prioridades.

Correr desde app/backend: .venv/Scripts/python scripts/armar_demo_eeuu.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from shapely.geometry import mapping, shape  # noqa: E402

from fieldshift.analisis import plan  # noqa: E402
from fieldshift.fuentes import ssurgo  # noqa: E402

CONTORNO = RAIZ.parent / "ejemplos" / "campo_iowa_madison.geojson"
SALIDA = RAIZ.parent / "frontend" / "public" / "ejemplos" / "campo_demo_eeuu.fieldshift.json"


def liviana(g: dict) -> dict:
    """Simplifica la geometría (~15 m) para que el archivo pese poco."""
    return mapping(shape(g).simplify(0.00015, preserve_topology=True))


def nombre_de(muname: str, usados: set[str]) -> str:
    """Nombre del lote como lo llamaría un productor de Iowa, según el suelo y la pendiente de la unidad."""
    m = muname.lower()
    if "0 to 2" in m:
        n = "The Flat"
    elif "eroded" in m or "9 to" in m or "5 to 9" in m:
        n = "Hill Ground"
    else:
        n = "North Field"
    while n in usados:
        n += " 2"
    usados.add(n)
    return n


def main():
    contorno = liviana(json.loads(CONTORNO.read_text(encoding="utf-8"))["geometry"])
    usados: set[str] = set()
    secciones = []
    for i, parte in enumerate(ssurgo.secciones_por_suelo(contorno)):
        g = liviana(parte["geometria"])
        secciones.append({"id": f"s{i + 1}", "nombre": nombre_de(parte["muname"], usados), "geometria": g,
                          "suelo_ssurgo": parte["muname"], "area_ha": round(plan.area_ha(g), 1)})
    # sin historial: lo que se sembró cada año lo dice el Cropland Data Layer (fuentes/cdl.py)
    problemas = {"Hill Ground": ["erosion"], "The Flat": ["anegamiento"]}
    for s in secciones:
        s["problemas"] = problemas.get(s["nombre"], [])
    lat, lon = plan.punto_interior(contorno)

    campo = {
        "id": "demo-iowa-madison",
        "nombre": "Granja en Madison County, Iowa (ejemplo)",
        "ubicacion": {"lat": lat, "lon": lon, "pais": "US", "estado": "Iowa", "condado": "Madison", "origen": "mapa"},
        "contorno": contorno,
        "area_ha": round(plan.area_ha(contorno), 1),
        "secciones": secciones,
        "sistema": {"tipo": "agricola", "ganado": False, "tenencia": "propio", "riego": False},
        "experiencia": {"anios": 22, "que_funciono": "el maíz-soja en el North Field, con buenos rindes",
                        "que_fallo": "en la loma (Hill Ground) se ven las cárcavas después de las tormentas de primavera",
                        "texto": "maíz-soja bien en lo plano; la loma se lava"},
        "objetivos": {"corto_plazo": "mantener el ingreso con maíz y soja",
                      "largo_plazo": "frenar la erosión de la loma y bajar el riesgo de otra seca como la de 2012",
                      "prioridades": {"ingreso": 4, "suelo": 4, "agua": 3, "clima": 3, "forraje": 0, "simplicidad": 2,
                                      "diversificacion": 2}},
        "restricciones": {"cultivos_excluidos": []},
        "pasos_omitidos": ["margenes", "estacion"],
    }
    res = plan.analizar_campo(campo)
    mensajes = [
        {"id": "d1", "rol": "asesor", "texto": "Este es un campo de ejemplo en Iowa (condado de Madison): el contorno sale del "
                                              "Cropland Data Layer del USDA, los lotes de la carta de suelos SSURGO, y lo que se "
                                              "sembró cada año, el clima y el satélite son reales (USDA y NASA). El productor y "
                                              "sus respuestas son inventados. Tocá un lote para ver las alternativas, con su "
                                              "porqué, y elegí qué probar."},
    ]
    from fieldshift.agente.guiado import resumen_texto

    mensajes.append({"id": "d2", "rol": "asesor", "texto": resumen_texto(res, campo)})
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps({"version": 1, "campo": campo, "mensajes": mensajes, "historialApi": [],
                                  "analisis": res, "plan": res["plan"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(SALIDA, round(SALIDA.stat().st_size / 1024), "KB")
    for s in res["secciones"]:
        a = s.get("actual") or {}
        print(f"  {s['nombre']}: {s['area_ha']} ha, {s['suelo'].get('unidad_cartografica')}; hoy {a.get('nombre')} "
              f"(A {a.get('erosion', {}).get('a_t_ha')} t/ha) → {s.get('recomendada_id')}")


if __name__ == "__main__":
    main()
