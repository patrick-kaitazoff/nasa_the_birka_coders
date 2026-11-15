r"""Regenera app/frontend/public/ejemplos/historia_demo.json usando datos 100 % reales.

Descarga y procesa:
1. Clima diario de NASA POWER (1991-hoy) para el campo de ejemplo de Durazno (-33.1030, -56.1462).
2. Serie histórica satelital de verdor MODIS MOD13Q1.061 (NDVI, 2000-hoy) para las 6 secciones del campo
   de ejemplo.
3. Balance de agua de suelo FAO-56 para evaluar el estrés hídrico de cada zafra histórica.
4. Caso estrella del verano 2022/23 con datos verificados de NASA POWER, NASA MODIS y DIEA/MGAP.
5. «Con este plan»: los cultivos del plan del ejemplo, temporada por temporada (ciclos_plan), igual que los
   manda la app (ciclosDelPlan en store.ts). Si cambia el plan del ejemplo, hay que volver a correr esto.

Correr desde app/backend:
    .\.venv\Scripts\python scripts/armar_historia_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from fieldshift.analisis import historia, plan
from fieldshift.fuentes import modis_historia

CAMPO_DEMO_PATH = RAIZ.parent / "frontend" / "public" / "ejemplos" / "campo_demo.fieldshift.json"
HISTORIA_DEMO_PATH = RAIZ.parent / "frontend" / "public" / "ejemplos" / "historia_demo.json"


def main():
    print(f"Leyendo campo demo desde: {CAMPO_DEMO_PATH}")
    if not CAMPO_DEMO_PATH.is_file():
        raise FileNotFoundError(f"No existe {CAMPO_DEMO_PATH}")

    with open(CAMPO_DEMO_PATH, "r", encoding="utf-8") as f:
        demo_raw = json.load(f)

    campo = demo_raw["campo"]
    if "analisis" in demo_raw:
        campo["analisis"] = demo_raw["analisis"]

    # Extraer centroides de las 6 secciones
    puntos_coords = []
    for sec in campo.get("secciones", []):
        sid = sec["id"]
        p = plan.punto_interior(sec["geometria"])
        puntos_coords.append((sid, p[0], p[1]))

    print(f"Secciones a procesar ({len(puntos_coords)}):")
    for sid, lat, lon in puntos_coords:
        print(f"  - {sid}: lat={lat:.4f}, lon={lon:.4f}")

    # Asegurar que las series reales de MODIS están descargadas y en caché
    print("\nConsultando serie histórica MODIS vía NASA AppEEARS...")
    res_sat = modis_historia.estado_campo(puntos_coords)
    if res_sat.get("estado") != "listo":
        print(f"Estado inicial de satélite: {res_sat.get('estado')}. Esperando finalización...")
        res_sat = modis_historia.esperar_campo(puntos_coords, max_min=30)

    if res_sat.get("estado") != "listo":
        raise RuntimeError(f"No se pudo obtener la serie de MODIS: {res_sat}")

    print(f"Serie satelital lista: {res_sat.get('fuente')}")

    # Correr el análisis histórico completo
    print("\nEjecutando análisis biofísico histórico (FAO-56 + NASA POWER + MODIS)...")
    plan_demo = demo_raw.get("plan") or (demo_raw.get("analisis") or {}).get("plan") or {}
    temporadas_plan = plan_demo.get("temporadas") or []
    ciclos = {
        s["seccion_id"]: [[(temporadas_plan[i] or {}).get("tipo", "verano"), c] for i, c in enumerate(s["cultivos"])]
        for s in plan_demo.get("secciones") or []
    } or None
    resultado = historia.analizar_historia(campo, ciclos_plan=ciclos)

    # Imprimir validación científica con datos reales
    rg = resultado.get("resumen_global", {})
    print("\n" + "=" * 60)
    print("VALIDACIÓN CIENTÍFICA CON DATOS REALES (DURAZNO DEMO)")
    print("=" * 60)
    print(f"Total secciones: {rg.get('total_secciones')}")
    print(f"Temporadas por sección: {rg.get('temporadas_por_seccion')}")
    print(f"Total temporadas evaluadas: {rg.get('total_evaluadas')}")
    print(f"Aciertos del modelo vs satélite: {rg.get('aciertos_globales')}")
    print(f"Coincidencia global: {rg.get('coincidencia_global_pct')} %")
    print(f"Frase resumen: {rg.get('frase')}")

    contingencia_total = {"ambos_estres": 0, "ambos_normal": 0, "modelo_alerta_satelite_bien": 0, "modelo_bien_satelite_bajo": 0}
    for sec in resultado.get("secciones", []):
        v = sec.get("validacion", {})
        tc = v.get("tabla_contingencia", {})
        for k in contingencia_total:
            contingencia_total[k] += tc.get(k, 0)
        print(f"\n  Potrero {sec.get('seccion_id')} ({sec.get('nombre')}):")
        print(f"    Coincidencia: {v.get('aciertos')}/{v.get('total_evaluadas')} ({v.get('coincidencia_pct')} %)")
        print(f"    Kappa: {v.get('kappa')} · Wilson IC 80%: {v.get('wilson_ic_80')}%")

    n_tot = sum(contingencia_total.values())
    if n_tot > 0:
        po = (contingencia_total["ambos_estres"] + contingencia_total["ambos_normal"]) / n_tot
        p_mod = (contingencia_total["ambos_estres"] + contingencia_total["modelo_alerta_satelite_bien"]) / n_tot
        p_sat = (contingencia_total["ambos_estres"] + contingencia_total["modelo_bien_satelite_bajo"]) / n_tot
        pe = (p_mod * p_sat) + ((1.0 - p_mod) * (1.0 - p_sat))
        kappa_global = round((po - pe) / (1.0 - pe), 2) if (1.0 - pe) > 0.001 else 0.0
        from fieldshift.analisis import incertidumbre
        ic_w = incertidumbre.wilson(po, n_tot)
        ic_w_pct = [round(ic_w[0] * 100, 1), round(ic_w[1] * 100, 1)]
        print(f"\nConsolidado global del campo:")
        print(f"  Kappa de Cohen: {kappa_global}")
        print(f"  Wilson IC 80%: {ic_w_pct} %")
        print(f"  Contingencia: {contingencia_total}")

    # Guardar en JSON precalculado para demo
    print(f"\nGuardando archivo generado en: {HISTORIA_DEMO_PATH}")
    with open(HISTORIA_DEMO_PATH, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    tam = HISTORIA_DEMO_PATH.stat().st_size
    print(f"Archivo guardado con éxito ({tam / 1024:.1f} KB).")


if __name__ == "__main__":
    main()
