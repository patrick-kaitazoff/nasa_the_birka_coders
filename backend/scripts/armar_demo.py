"""Arma el campo de ejemplo de la app (padrón 1000 de Durazno) con la entrevista ya respondida
y el análisis corrido. Lo guarda en frontend/public/ejemplos/campo_demo.fieldshift.json.

Los datos del productor (qué cultivo hizo en cada lote, problemas, sistema, experiencia, objetivos y prioridades)
son INVENTADOS para la demo; el contorno, los suelos, el clima y el NDVI son reales (MGAP, NASA). La agricultura o el pastizal de cada lote siguen a MapBiomas, la estación es la real de INUMET en Paso de los Toros y
no hay análisis de suelo inventado.

Correr desde app/backend: .venv/Scripts/python scripts/armar_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from shapely.geometry import mapping, shape  # noqa: E402

from fieldshift import archivos  # noqa: E402
from fieldshift.analisis import plan  # noqa: E402
from fieldshift.fuentes import mgap, power  # noqa: E402

SALIDA = RAIZ.parent / "frontend" / "public" / "ejemplos" / "campo_demo.fieldshift.json"


def liviana(g: dict) -> dict:
    """Simplifica la geometría (~15 m) para que el archivo pese poco."""
    return mapping(shape(g).simplify(0.00015, preserve_topology=True))


def main():
    p = mgap.padron("DURAZNO", 1000)
    contorno = liviana(p["contorno"])
    nombres = ["La Loma", "El Bajo", "Del Monte", "La Cañada", "El Molino", "Potrero Grande"]
    secciones = []
    for i, parte in enumerate(p["secciones_por_suelo"]):
        g = liviana(parte["geometria"])
        secciones.append({"id": f"s{i + 1}", "nombre": nombres[i] if i < len(nombres) else f"Potrero {i + 1}",
                          "geometria": g, "grupo_coneat": parte["grupo_coneat"],
                          "area_ha": round(plan.area_ha(g), 1)})
    # datos inventados del productor
    sojero = [{"anio": a, "invierno": "barbecho", "verano": "soja"} for a in (2022, 2023, 2024, 2025)]
    rotado = [{"anio": 2022, "invierno": "trigo", "verano": "soja2"}, {"anio": 2023, "invierno": "cobertura", "verano": "maiz"},
              {"anio": 2024, "invierno": "trigo", "verano": "soja2"}, {"anio": 2025, "invierno": "cobertura", "verano": "maiz"}]
    pradera = [{"anio": a, "invierno": "pradera", "verano": "pradera"} for a in (2022, 2023, 2024, 2025)]
    natural = [{"anio": a, "invierno": "campo_natural", "verano": "campo_natural"} for a in (2022, 2023, 2024, 2025)]
    # Agricultura o pastizal en cada lote según MapBiomas Uruguay col. 3 (2024): La Loma 53 % agricultura,
    # El Bajo 69 %, Del Monte 84 %, Potrero Grande 82 %; La Cañada 72 % pastizal y El Molino 64 %. Antes El Bajo era
    # campo natural y El Molino soja continua, al revés de lo que se ve. Qué cultivo exacto sigue inventado.
    historiales = [sojero, rotado, sojero, pradera, natural, rotado]
    problemas = [["erosion"], ["anegamiento"], [], ["anegamiento"], [], []]
    for s, h, pr in zip(secciones, historiales, problemas):
        s["historial"] = h
        s["problemas"] = pr
    # sin análisis de suelo: no hay datos públicos por padrón y los que había eran inventados
    lat, lon = plan.punto_interior(contorno)
    # estación REAL de INUMET a ~47 km (scripts/armar_estacion_inumet.py), en vez de la sintética. Está lejos para decir
    # si el campo es más helador: sirve para ver si los datos de la NASA andan bien en la zona y no cambia los riesgos.
    est_nombre = "estacion_inumet_paso_de_los_toros.csv"
    est_csv = (RAIZ.parent / "ejemplos" / est_nombre).read_bytes()
    est = archivos.procesar(est_nombre, est_csv, power.bajar_diario(lat, lon), "estacion")
    comp = dict(est.get("comparacion") or {})
    comp.pop("campo_mas_helador", None)
    ll = comp.get("lluvia") or {}
    comp["conclusion"] = (
        f"La estación de INUMET en Paso de los Toros, a unos 47 km, midió {ll.get('estacion_mm')} mm de lluvia en "
        f"{comp.get('dias_en_comun')} días y la NASA {ll.get('nasa_mm')} mm en la celda del campo (correlación mensual "
        f"{str(ll.get('correlacion_mensual')).replace('.', ',')}). Sirve para ver si los datos de la NASA andan bien en la "
        "zona; está lejos para decir si este campo es más helador, así que no cambia los riesgos.")

    campo = {
        "id": "demo-durazno-1000",
        "nombre": "Estancia La Esperanza (ejemplo)",
        "ubicacion": {"lat": lat, "lon": lon, "departamento": "DURAZNO", "padron": 1000, "origen": "padron"},
        "contorno": contorno,
        "area_ha": round(plan.area_ha(contorno), 1),
        "secciones": secciones,
        "sistema": {"tipo": "mixto", "ganado": True, "cabezas": 450, "tenencia": "propio", "riego": False},
        "experiencia": {"anios": 18, "que_funciono": "el maíz temprano en el Potrero Grande",
                        "que_fallo": "la soja continua en La Loma se lavó y rinde cada vez menos",
                        "texto": "maíz temprano bien; soja continua en la loma mal"},
        "objetivos": {"corto_plazo": "necesito caja este año", "largo_plazo": "recuperar el suelo de La Loma y dejarle el campo a mis hijos",
                      "pct_agricola": 50,
                      "prioridades": {"ingreso": 4, "suelo": 4, "agua": 3, "clima": 2, "forraje": 3, "simplicidad": 1, "diversificacion": 2}},
        "restricciones": {"cultivos_excluidos": ["girasol"]},
        "estacion": {"archivo": est_nombre, "comparacion": comp, "mensual": est.get("mensual"),
                     "referencia": {"nombre": "INUMET Paso de los Toros G3", "distancia_km": 47}},
        "pasos_omitidos": ["margenes"],
    }
    res = plan.analizar_campo(campo)
    mensajes = [
        {"id": "d1", "rol": "asesor", "texto": "Este es un campo de ejemplo: el padrón 1000 de Durazno, con su contorno, suelos, clima y "
                                              "cobertura reales (MGAP y NASA). El productor y sus respuestas son inventados para mostrar cómo "
                                              "funciona. Tocá un lote para ver las alternativas, con su porqué, y elegí qué probar."},
    ]
    from fieldshift.agente.guiado import resumen_texto

    mensajes.append({"id": "d2", "rol": "asesor", "texto": resumen_texto(res, campo)})
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps({"version": 1, "campo": campo, "mensajes": mensajes, "historialApi": [],
                                  "analisis": res, "plan": res["plan"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(SALIDA, round(SALIDA.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
