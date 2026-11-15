"""Arma los tres terrenos de ejemplo de la portada (Pucón, Bremm en el Mosela y el Valle del Lunarejo) con la
entrevista respondida y el análisis corrido. Los guarda en frontend/public/ejemplos/terreno_<id>.fieldshift.json.

El contorno es el campo dibujado en los videos de
Blender; el clima (NASA POWER), el relieve (SRTM), el verdor (MODIS) y el suelo (MGAP en Uruguay, SoilGrids afuera)
son reales. El productor y sus respuestas son INVENTADOS para la demostración.

Dos cosas, sin tocar las cuentas del motor:
- Hay que armarlos con las credenciales a mano (.secretos/ de Earthdata y de Earth Engine) y mirando que no quede
  ningún "error" en la salida. Los se armaron sin ellas y con el servicio de MODIS caído: salieron sin
  verdor de satélite (MODIS ni HLS) y con la lluvia de NASA POWER en vez de GPM IMERG. En Pucón POWER da 1060 mm por
  año e IMERG 2083 (lo que llueve ahí).
- Fuera de Uruguay el factor R (lluvia erosiva) va medido: `factor_r` de cada terreno es el del mapa GloREDa 1.2
  (pluviógrafos de 3939 estaciones, ~1 km), leído con scripts/leer_gloreda.py. El motor lo estimaba con la lluvia
  anual (Renard y Freimund 1994, de EE. UU.), que en lluvia mansa se pasa: Bremm 2386 contra 659 del mapa (las
  estaciones alemanas de alrededor miden de 375 a 525) y Pucón 15 852 contra 4537. En el Lunarejo manda el R
  oficial del MGAP, como en cualquier campo de Uruguay.

Correr desde app/backend: .venv/Scripts/python scripts/armar_terrenos.py [pucon|mosela|lunarejo]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from fieldshift.agente.guiado import resumen_texto  # noqa: E402
from fieldshift.analisis import plan  # noqa: E402

SALIDA = RAIZ.parent / "frontend" / "public" / "ejemplos"


def rect(c: tuple[float, float], w: float, h: float, rot: float, x0: float = -0.5, x1: float = 0.5) -> dict:
    """Rectángulo de w × h metros centrado en c y girado rot grados; x0 y x1 recortan una franja (para los lotes)."""
    lat, lon = c
    kl, ko = 111320.0, 111320.0 * math.cos(math.radians(lat))
    a = math.radians(rot)
    pts = []
    for fx, fy in ((x0, -0.5), (x1, -0.5), (x1, 0.5), (x0, 0.5), (x0, -0.5)):
        x, y = fx * w, fy * h
        xr, yr = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
        pts.append([round(lon + xr / ko, 6), round(lat + yr / kl, 6)])
    return {"type": "Polygon", "coordinates": [pts]}


def anios(*pares: tuple[str, str]) -> list[dict]:
    return [{"anio": 2022 + i, "invierno": inv, "verano": ver} for i, (inv, ver) in enumerate(pares)]


# el mismo campo que se ve marcado en los videos (tools/scene_site.py y prep_site.py de los renders)
TERRENOS = {
    "pucon": {
        "c": (-39.31, -71.95), "w": 1300, "h": 950, "rot": 12,
        # GloREDa 1.2 en el centro del campo, MJ·mm/(ha·h·año); los 9 píxeles de alrededor: 4353 a 4744
        "factor_r": 4537,
        "nombre": "Fundo Los Robles (ejemplo)", "lugar": "Pucón, Araucanía · Chile",
        "lotes": [
            ("El Volcán", anios(("pradera", "pradera"), ("pradera", "pradera"), ("pradera", "pradera"), ("pradera", "pradera")), []),
            ("La Vega", anios(("trigo", "barbecho"), ("verdeo", "maiz"), ("trigo", "barbecho"), ("verdeo", "maiz")), ["anegamiento"]),
            ("El Lago", anios(("colza", "barbecho"), ("trigo", "barbecho"), ("colza", "barbecho"), ("trigo", "barbecho")), ["helada"]),
        ],
        "sistema": {"tipo": "mixto", "ganado": True, "cabezas": 140, "tenencia": "propio", "riego": False},
        "experiencia": {"anios": 22, "que_funciono": "la pradera para las vacas de leche",
                        "que_fallo": "el maíz se hiela temprano algunos años",
                        "texto": "lechería con pradera; el maíz a veces se hiela"},
        "objetivos": {"corto_plazo": "asegurar el forraje del invierno", "largo_plazo": "seguir con la lechería sin gastar el suelo",
                      "pct_agricola": 40,
                      "prioridades": {"ingreso": 3, "suelo": 4, "agua": 2, "clima": 3, "forraje": 5, "simplicidad": 2, "diversificacion": 2}},
        # en el sur de Chile no se siembra soja ni girasol (frío): son cultivos que este productor no quiere
        "restricciones": {"cultivos_excluidos": ["soja", "soja2", "girasol", "sorgo"]},
        "intro": ("Este es un campo de ejemplo en Pucón (Chile), entre el volcán Villarrica y el lago. El clima, el relieve, "
                  "el verdor del satélite y el suelo (mapa mundial SoilGrids) son reales; el productor y sus respuestas son "
                  "inventados para mostrar cómo funciona fuera de Uruguay. Tocá un lote para ver las opciones, con su porqué."),
    },
    "mosela": {
        "c": (50.103, 7.125), "w": 380, "h": 230, "rot": -15,
        # GloREDa 1.2 en el centro del campo; los 9 píxeles de alrededor: 581 a 716. Estación más cercana: Hahn, a
        # 20 km y 494 m de altura, 505
        "factor_r": 659,
        "nombre": "Hof am Calmont (ejemplo)", "lugar": "Bremm, río Mosela · Alemania",
        "lotes": [
            ("Am Fluss", anios(("trigo", "barbecho"), ("colza", "barbecho"), ("cebada", "barbecho"), ("trigo", "barbecho")), ["anegamiento"]),
            ("Unterm Hang", anios(("colza", "barbecho"), ("trigo", "barbecho"), ("cebada", "barbecho"), ("colza", "barbecho")), ["erosion"]),
            ("Kirchweg", anios(("trigo", "barbecho"), ("cebada", "barbecho"), ("trigo", "barbecho"), ("cebada", "barbecho")), []),
            ("Am Wald", anios(("cebada", "maiz"), ("trigo", "barbecho"), ("cebada", "maiz"), ("trigo", "barbecho")), ["helada"]),
        ],
        "sistema": {"tipo": "mixto", "ganado": True, "cabezas": 40, "tenencia": "arrendado", "anios_contrato": 6, "riego": False},
        "experiencia": {"anios": 15, "que_funciono": "el trigo de invierno en la vega del río",
                        "que_fallo": "en el lote de la ladera se lava el suelo cuando queda pelado en otoño",
                        "texto": "trigo bien en la vega; la ladera se lava; unas vacas de carne en el pasto"},
        "objetivos": {"corto_plazo": "pagar el arrendamiento", "largo_plazo": "no perder el suelo de la ladera",
                      "pct_agricola": 50,
                      "prioridades": {"ingreso": 5, "suelo": 4, "agua": 2, "clima": 2, "forraje": 2, "simplicidad": 3, "diversificacion": 2}},
        # en el Mosela no se siembra soja, girasol ni cultivos de segunda de verano: el verano es corto
        "restricciones": {"cultivos_excluidos": ["soja", "soja2", "maiz2", "girasol", "sorgo"]},
        "intro": ("Este es un campo de ejemplo en la vega del río Mosela, en Bremm (Alemania), al pie de las laderas de "
                  "viñedos. El clima, el relieve, el verdor del satélite y el suelo (mapa mundial SoilGrids) son reales; el "
                  "productor y sus respuestas son inventados. La app compara rotaciones de cultivos extensivos: los viñedos "
                  "de las laderas no entran en el cálculo. Tocá un lote para ver las opciones, con su porqué."),
    },
    "lunarejo": {
        "c": (-31.1265, -55.916), "w": 560, "h": 420, "rot": 5,
        "nombre": "Estancia Las Quebradas (ejemplo)", "lugar": "Valle del Lunarejo · Rivera, Uruguay",
        "lotes": [
            ("La Meseta", anios(("barbecho", "soja"), ("barbecho", "soja"), ("barbecho", "soja"), ("barbecho", "soja")), ["erosion"]),
            ("El Pajonal", anios(("campo_natural", "campo_natural"), ("campo_natural", "campo_natural"), ("campo_natural", "campo_natural"), ("campo_natural", "campo_natural")), []),
            ("La Aguada", anios(("campo_natural", "campo_natural"), ("campo_natural", "campo_natural"), ("campo_natural", "campo_natural"), ("campo_natural", "campo_natural")), ["anegamiento"]),
            ("El Borde", anios(("verdeo", "sorgo_forrajero"), ("verdeo", "sorgo_forrajero"), ("verdeo", "sorgo_forrajero"), ("verdeo", "sorgo_forrajero")), ["suelo_superficial"]),
        ],
        "sistema": {"tipo": "mixto", "ganado": True, "cabezas": 300, "tenencia": "propio", "riego": False},
        "experiencia": {"anios": 30, "que_funciono": "el campo natural para la cría",
                        "que_fallo": "la soja en la meseta: el suelo es poco profundo y se lava",
                        "texto": "cría en campo natural; la soja en la meseta rinde poco y se lava"},
        "objetivos": {"corto_plazo": "más pasto para el invierno", "largo_plazo": "cuidar el suelo y el paisaje del valle",
                      "pct_agricola": 30,
                      "prioridades": {"ingreso": 3, "suelo": 5, "agua": 3, "clima": 2, "forraje": 4, "simplicidad": 3, "diversificacion": 1}},
        "intro": ("Este es un campo de ejemplo al borde de las quebradas del Valle del Lunarejo (Rivera, Uruguay). El suelo "
                  "(MGAP), el clima, el relieve y el verdor del satélite son reales; el productor y sus respuestas son "
                  "inventados para mostrar cómo funciona. Tocá un lote para ver las opciones, con su porqué."),
    },
}


def armar(clave: str) -> Path:
    t = TERRENOS[clave]
    n = len(t["lotes"])
    secciones = []
    for i, (nombre, historial, problemas) in enumerate(t["lotes"]):
        g = rect(t["c"], t["w"], t["h"], t["rot"], -0.5 + i / n, -0.5 + (i + 1) / n)
        secciones.append({"id": f"s{i + 1}", "nombre": nombre, "geometria": g, "area_ha": round(plan.area_ha(g), 1),
                          "historial": historial, "problemas": problemas})
    contorno = rect(t["c"], t["w"], t["h"], t["rot"])
    lat, lon = plan.punto_interior(contorno)
    campo = {
        "id": f"ejemplo-{clave}",
        "nombre": t["nombre"],
        "ubicacion": {"lat": lat, "lon": lon, "lugar": t["lugar"], "origen": "ejemplo"},
        "contorno": contorno,
        "area_ha": round(plan.area_ha(contorno), 1),
        "secciones": secciones,
        "sistema": t["sistema"],
        "experiencia": t["experiencia"],
        "objetivos": t["objetivos"],
        "pasos_omitidos": ["subir_analisis_suelo", "margenes"],
    }
    if t.get("restricciones"):
        campo["restricciones"] = t["restricciones"]
    if t.get("factor_r"):
        # el motor trabaja con las unidades del MGAP, que son las internacionales divididas por 10
        campo["factor_r_medido"] = {"r": t["factor_r"] / 10, "r_mj_mm_ha_h": t["factor_r"], "fuente": "GloREDa 1.2, JRC"}
    res = plan.analizar_campo(campo)
    mensajes = [{"id": "d1", "rol": "asesor", "texto": t["intro"]},
                {"id": "d2", "rol": "asesor", "texto": resumen_texto(res, campo)}]
    salida = SALIDA / f"terreno_{clave}.fieldshift.json"
    salida.write_text(json.dumps({"version": 1, "campo": campo, "mensajes": mensajes, "historialApi": [],
                                  "analisis": res, "plan": res["plan"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(salida, round(salida.stat().st_size / 1024), "KB")
    texto = salida.read_text(encoding="utf-8")
    for mal in ('"error": "', "Sin credenciales", "IMERG no disponible"):
        if mal in texto:
            print(f"   OJO: quedó «{mal}» en la salida: alguna fuente no respondió y el ejemplo salió incompleto")
    for s in res["secciones"]:
        print("  ", s["nombre"], "→", s["recomendada_id"], "| alternativas:", [a["id"] for a in s["alternativas"]])
    return salida


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # la consola de Windows (cp1252) no tiene «→»
    for c in (sys.argv[1:] or list(TERRENOS)):
        armar(c)
