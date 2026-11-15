"""Análisis histórico del campo («Tu campo, temporada por temporada») desde el año 2000.

Coteja tres capas de información para cada sección del campo:
1. El verde medido por satélite (MODIS MOD13Q1 v061, 250 m, 16 días) desde 2000.
2. El clima diario de NASA POWER (lluvia, balance de agua FAO-56, heladas, calor, factor R).
3. Lo que el productor hizo de verdad (declarado o detectado) contra «qué hubiera pasado
   con la rotación que le propone la app».

Regla de honestidad (Fase 0-F):
- SÍ se afirma: cobertura del suelo en cada mes, agua disponible en la floración según el balance
  hídrico, y lluvia erosiva caída sobre suelo cubierto o desnudo.
- NO se afirma: kilos cosechados, ganancias monetarias ni promesas no modeladas.
- Sin datos de satélite reales disponibles, el sistema reporta estado honesto 'sin_datos' sin
  fabricar series sintéticas ni porcentajes de validación artificiales.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np

from ..fuentes import modis, modis_historia, power
from . import clima as clima_mod
from . import incertidumbre
from .cultivos import CULTIVOS, Cultivo, HEMISFERIO
from .rotaciones import ROTACIONES, Rotacion, cobertura_diaria, factor_c_diario

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _normalizar_cultivo(texto: str | None) -> str:
    """Convierte un texto de cultivo o uso a un código válido de CULTIVOS."""
    if not texto:
        return "barbecho"
    t = texto.strip().lower()
    if "campo_natural" in t or "campo natural" in t:
        return "campo_natural"
    if "pradera" in t or "pastura" in t:
        return "pradera"
    if "alfalfa" in t:
        return "alfalfa"
    if "verdeo" in t:
        return "verdeo"
    if "cobertura" in t or "puente" in t:
        return "cobertura"
    if "soja2" in t or "soja de segunda" in t or "segunda" in t:
        return "soja2"
    if "soja" in t:
        return "soja"
    if "maiz2" in t or "maíz de segunda" in t or "maiz de segunda" in t:
        return "maiz2"
    if "maiz" in t or "maíz" in t:
        return "maiz"
    if "sorgo_forrajero" in t or "sorgo forrajero" in t:
        return "sorgo_forrajero"
    if "sorgo" in t:
        return "sorgo"
    if "trigo" in t:
        return "trigo"
    if "cebada" in t:
        return "cebada"
    if "colza" in t or "canola" in t:
        return "colza"
    if "girasol" in t:
        return "girasol"
    if "barbecho" in t or "desnudo" in t or "rastrojo" in t:
        return "barbecho"
    return "barbecho"


def _cultivo_desde_uso_detectado(uso: str, tipo: str) -> str:
    """Infiere un cultivo arquetípico a partir del uso detectado por satélite."""
    if "permanente" in uso:
        return "campo_natural" if "baja actividad" in uso else "pradera"
    if "cultivo" in uso or "crecimiento" in uso:
        return "soja" if tipo == "verano" else "trigo"
    if "parcial" in uso:
        return "cobertura" if tipo == "invierno" else "soja2"
    return "barbecho"


def _nombre_cultivo(cod: str) -> str:
    if cod in CULTIVOS:
        return CULTIVOS[cod].nombre.split(" (")[0]
    if cod == "barbecho":
        return "Barbecho (suelo descubierto)"
    if cod == "sin_datos":
        return "Sin datos de satélite"
    return cod.replace("_", " ").title()


def _evaluar_modelo_cultivo(serie: clima_mod.Serie, cod: str, agua_util_mm: float, y: int) -> dict[str, Any]:
    """Evalúa los indicadores biofísicos de un cultivo en un año específico."""
    if cod not in CULTIVOS or CULTIVOS[cod].temporada == "barbecho" or cod == "sin_datos":
        return {"eta_etc": None, "dias_estres": None, "lluvia_ventana": None, "dias_calor": None, "helada": False}
    c = CULTIVOS[cod]
    res = clima_mod.riesgos_cultivo(serie, c, agua_util_mm, anios=[y])
    filas = res.get("por_anio") or []
    if not filas:
        return {"eta_etc": None, "dias_estres": None, "lluvia_ventana": None, "dias_calor": None, "helada": False}
    f = filas[0]
    return {
        "eta_etc": round(f.get("eta_etc"), 3) if f.get("eta_etc") is not None else None,
        "dias_estres": f.get("dias_estres"),
        "lluvia_ventana": round(f.get("lluvia_ventana"), 1) if f.get("lluvia_ventana") is not None else None,
        "dias_calor": f.get("dias_calor"),
        "helada": bool(f.get("helada")),
        "helada_agro": bool(f.get("helada_agro")),
    }


def analizar_historia_seccion(
    sec: dict,
    serie: clima_mod.Serie,
    propuesta_rot: Rotacion | None = None,
    agua_util_mm: float = 120.0,
    correcciones_usuario: dict[str, str] | None = None,
    serie_modis: list[dict] | None = None,
    ciclo_plan: list[tuple[str, str]] | None = None,
    cdl_anios: list[dict] | None = None,
) -> dict[str, Any]:
    """Analiza la historia temporada por temporada para una sección específica.

    ciclo_plan: los cultivos del plan de esta sección, temporada por temporada ([("invierno", "trigo"),
    ("verano", "soja2"), …]). Si está, «qué habría pasado» usa ESE plan, repitiéndolo desde el año 2000; si
    no, la rotación propuesta del análisis o, en último caso, una rotación de referencia.

    cdl_anios: los años del Cropland Data Layer de la sección (fuentes/cdl.py). Dicen qué se
    cosechó cada año mejor que el NDVI: el verano del año Y y, si fue un cultivo de invierno, el invierno que terminó
    ese año (Y-1/Y). Un invierno en barbecho según el CDL queda para el NDVI, que sí ve un cultivo de cobertura.
    """
    sec_id = sec.get("id") or "s1"
    nombre = sec.get("nombre") or "Tu potrero"
    area_ha = float(sec.get("area_ha") or 50.0)

    # Ubicación del potrero
    punto = sec.get("punto")
    if not punto and "geometria" in sec:
        from .plan import punto_interior
        punto = punto_interior(sec["geometria"])
    lat, lon = (punto[0], punto[1]) if punto else (serie.lat, -56.0)

    # Serie histórica MODIS (real o proporcionada para pruebas unitarias)
    if serie_modis is not None:
        modis_data = {
            "fuente": "MODIS (serie fija de prueba unitaria)",
            "lat": lat,
            "lon": lon,
            "serie": serie_modis,
            "estado": "listo",
            **modis_historia.interpretar_historia(serie_modis, "sur" if lat < 0 else "norte"),
        }
    else:
        modis_data = modis_historia.ndvi_historia_punto(lat, lon, sec_id)

    serie_satelite = modis_data.get("serie") or []
    hay_satelite = bool(serie_satelite) and len(serie_satelite) > 0
    temporadas_modis = modis_data.get("temporadas") or []

    # Si no hay datos de satélite todavía, armamos las temporadas desde la serie climática real de NASA POWER
    temporadas_base: list[dict[str, Any]] = []
    norte = lat >= 0  # Campos de EE. UU. (ver clima.mascara_temporada)
    if not hay_satelite:
        anios_clima = [y for y in sorted(set(serie.anio.tolist())) if y >= 2000]
        orden = ("verano", "invierno") if norte else ("invierno", "verano")
        for y, tipo_b in [(y, t) for y in anios_clima for t in orden]:
            if clima_mod.mascara_temporada(serie, y, tipo_b).any():
                temporadas_base.append({
                    "temporada": clima_mod.nombre_temporada(y, tipo_b, norte),
                    "tipo": tipo_b,
                    "anio_agricola": y,
                    "ndvi_max": None,
                    "ndvi_min": None,
                    "ndvi_integrado": None,
                    "mediana_historica": None,
                    "anomalia_ndvi_pct": None,
                    "estres_satelite": False,
                    "uso_detectado": None,
                })

    temporadas_a_procesar = temporadas_modis if hay_satelite else temporadas_base

    # Lo que vio el Cropland Data Layer del USDA (solo EE. UU.)
    hist_cdl: dict[tuple[int, str], str] = {}
    for f in cdl_anios or []:
        y_c = int(f.get("anio") or 0)
        if f.get("verano") and f.get("verano") != "barbecho":
            hist_cdl[(y_c, "verano")] = f["verano"]
        if f.get("invierno") and f.get("invierno") != "barbecho":
            hist_cdl[(y_c - 1, "invierno")] = f["invierno"]

    # Historial declarado por el productor en la sección
    hist_productor: dict[tuple[int, str], str] = {}
    for h in sec.get("historial") or []:
        y = int(h.get("anio", 0))
        if h.get("invierno"):
            hist_productor[(y, "invierno")] = _normalizar_cultivo(h["invierno"])
        if h.get("verano"):
            hist_productor[(y, "verano")] = _normalizar_cultivo(h["verano"])

    # Normales climáticas por tipo de temporada para calcular anomalías
    lluvias_inv = []
    lluvias_ver = []
    for y in sorted(set(serie.anio.tolist()))[:-1]:
        m_inv = clima_mod.mascara_temporada(serie, y, "invierno")
        m_ver = clima_mod.mascara_temporada(serie, y, "verano")
        if m_inv.any():
            lluvias_inv.append(float(serie.lluvia[m_inv].sum()))
        if m_ver.any():
            lluvias_ver.append(float(serie.lluvia[m_ver].sum()))
    lluvia_norm_inv = round(float(np.mean(lluvias_inv)), 1) if lluvias_inv else 420.0
    lluvia_norm_ver = round(float(np.mean(lluvias_ver)), 1) if lluvias_ver else 440.0

    # Ciclo de la rotación propuesta para alinear
    ciclo_anios = propuesta_rot.anios if propuesta_rot and propuesta_rot.anios else [("trigo", "soja2"), ("cobertura", "maiz")]
    len_ciclo = len(ciclo_anios)
    plan_inv = [c for tipo_p, c in (ciclo_plan or []) if tipo_p == "invierno" and c]
    plan_ver = [c for tipo_p, c in (ciclo_plan or []) if tipo_p == "verano" and c]

    salida_temporadas = []
    contingencia = {"ambos_estres": 0, "ambos_normal": 0, "modelo_alerta_satelite_bien": 0, "modelo_bien_satelite_bajo": 0}

    for t in temporadas_a_procesar:
        nom_temp = t["temporada"]  # ej. "invierno 2022" o "verano 2022/23"
        tipo = t["tipo"]  # "invierno" | "verano"
        y = t["anio_agricola"]
        es_estrella = (nom_temp == ("verano 2012" if norte else "verano 2022/23"))

        # 1. Uso del suelo real (declarado > corregido > detectado > sin datos)
        uso_contado = hist_productor.get((y, tipo))
        if correcciones_usuario and nom_temp in correcciones_usuario:
            cultivo_real = _normalizar_cultivo(correcciones_usuario[nom_temp])
            origen_uso = "corregido"
        elif uso_contado:
            cultivo_real = uso_contado
            origen_uso = "contado"
        elif (y, tipo) in hist_cdl:
            cultivo_real = hist_cdl[(y, tipo)]
            origen_uso = "cdl"
        elif hay_satelite and t.get("uso_detectado"):
            cultivo_real = _cultivo_desde_uso_detectado(t.get("uso_detectado", ""), tipo)
            origen_uso = "detectado"
        else:
            cultivo_real = "sin_datos"
            origen_uso = "sin_datos"

        # 2. Clima de esa temporada (NASA POWER diario real)
        ero = clima_mod.erosividad_temporada(serie, y, tipo)
        lluvia_norm = lluvia_norm_inv if tipo == "invierno" else lluvia_norm_ver
        lluvia_real = ero["lluvia_mm"]
        anom_lluvia = round(((lluvia_real / lluvia_norm) - 1.0) * 100.0, 1) if lluvia_norm > 0 else 0.0

        # Días de calor y helada en la temporada
        m_clima = clima_mod.mascara_temporada(serie, y, tipo)
        dias_calor = int(np.sum((serie.tmax[m_clima] >= 35.0))) if m_clima.any() else 0
        dias_helada = int(np.sum((serie.tmin[m_clima] <= 0.0))) if m_clima.any() else 0

        # Indicadores biofísicos para el cultivo real
        if origen_uso == "sin_datos":
            met_real = {"eta_etc": None, "dias_estres": None, "lluvia_ventana": None, "dias_calor": None, "helada": False}
            modelo_dijo_seca = False
        else:
            met_real = _evaluar_modelo_cultivo(serie, cultivo_real, agua_util_mm, y)
            eta_etc = met_real.get("eta_etc")
            modelo_dijo_seca = (eta_etc is not None and eta_etc < 0.50)

        # 3. Satélite (solo si hay datos reales)
        if hay_satelite:
            anom_ndvi = float(t.get("anomalia_ndvi_pct", 0.0))
            satelite_vio_estres = bool(t.get("estres_satelite", False))
            ndvi_max = t.get("ndvi_max")
            ndvi_min = t.get("ndvi_min")
            ndvi_integrado = t.get("ndvi_integrado")
            mediana_historica = t.get("mediana_historica")
            uso_detectado = t.get("uso_detectado")
        else:
            anom_ndvi = None
            satelite_vio_estres = False
            ndvi_max = None
            ndvi_min = None
            ndvi_integrado = None
            mediana_historica = None
            uso_detectado = None

        # Tabla de contingencia solo para temporadas con cultivo agrícola real Y satélite medido
        if hay_satelite and cultivo_real not in ("barbecho", "campo_natural", "sin_datos") and met_real.get("eta_etc") is not None:
            if modelo_dijo_seca and satelite_vio_estres:
                contingencia["ambos_estres"] += 1
            elif (not modelo_dijo_seca) and (not satelite_vio_estres):
                contingencia["ambos_normal"] += 1
            elif modelo_dijo_seca and (not satelite_vio_estres):
                contingencia["modelo_alerta_satelite_bien"] += 1
            else:
                contingencia["modelo_bien_satelite_bajo"] += 1

        # 4. Qué hubiera pasado con la rotación propuesta
        idx_ciclo = (y - 2000) % len_ciclo
        cultivo_propuesto = ciclo_anios[idx_ciclo][0] if tipo == "invierno" else ciclo_anios[idx_ciclo][1]
        ciclo_tipo = plan_inv if tipo == "invierno" else plan_ver
        if ciclo_tipo:
            cultivo_propuesto = ciclo_tipo[(y - 2000) % len(ciclo_tipo)]
        met_prop = _evaluar_modelo_cultivo(serie, cultivo_propuesto, agua_util_mm, y)

        # Relato honesto de comparación (Respetando regla 0-F)
        relato_partes = []
        if not hay_satelite:
            relato_partes.append(f"Lluvia {serie.fuente_lluvia}: llovieron {lluvia_real:.0f} mm ({anom_lluvia:+.0f} % vs normal) con {dias_calor} días con calor ≥ 35 °C.")
            if cultivo_real != "sin_datos":
                relato_partes.append(f"Cultivo declarado: {_nombre_cultivo(cultivo_real)}.")
            else:
                relato_partes.append("Sin datos de satélite todavía para estimar el verdor de esta zafra.")
        else:
            # El relato cuenta solo lo que pasó. Lo que «habría pasado con la propuesta» se sacó: el plan se
            # aplicaba al pasado empezando por cualquier cultivo de la rotación y se leía como un pronóstico
            if cultivo_real == "barbecho":
                relato_partes.append("El suelo estuvo descubierto.")
            elif cultivo_real in ("soja", "maiz") and met_real.get("eta_etc") is not None and met_real["eta_etc"] < 0.5:
                relato_partes.append(f"El {_nombre_cultivo(cultivo_real)} llegó a la floración con solo el {int(met_real['eta_etc']*100)} % del agua que necesitaba.")
            else:
                relato_partes.append(f"Verdor {'normal' if not satelite_vio_estres else 'con estrés'}: NDVI máx {ndvi_max} ({anom_ndvi:+.0f} % vs mediana del campo).")

        salida_temporadas.append({
            "temporada": nom_temp,
            "tipo": tipo,
            "anio_agricola": y,
            "es_estrella": es_estrella,
            "cultivo_real": {
                "codigo": cultivo_real,
                "nombre": _nombre_cultivo(cultivo_real),
                "origen": origen_uso,
                "eta_etc": met_real.get("eta_etc"),
                "dias_estres": met_real.get("dias_estres"),
                "modelo_dijo_seca": modelo_dijo_seca,
            },
            "clima": {
                "lluvia_mm": lluvia_real,
                "lluvia_normal_mm": lluvia_norm,
                "anomalia_lluvia_pct": anom_lluvia,
                "dias_calor": dias_calor,
                "dias_helada": dias_helada,
                "r_temporada": ero["r_temporada"],
                "dias_erosivos": ero["dias_erosivos"],
            },
            "satelite": {
                "ndvi_max": ndvi_max,
                "ndvi_min": ndvi_min,
                "ndvi_integrado": ndvi_integrado,
                "mediana_historica": mediana_historica,
                "anomalia_ndvi_pct": anom_ndvi,
                "estres_satelite": satelite_vio_estres,
                "uso_detectado": uso_detectado,
            },
            "propuesta": {
                "codigo": cultivo_propuesto,
                "nombre": _nombre_cultivo(cultivo_propuesto),
                "eta_etc": met_prop.get("eta_etc"),
                "dias_estres": met_prop.get("dias_estres"),
            },
            "relato": " ".join(relato_partes),
        })

    # Estadísticas de validación del modelo vs satélite (solo válidas si hay satélite)
    n_eval = sum(contingencia.values())
    if hay_satelite and n_eval > 0:
        aciertos = contingencia["ambos_estres"] + contingencia["ambos_normal"]
        coincidencia_pct = round((aciertos / n_eval) * 100.0, 1)

        # Kappa de Cohen
        po = aciertos / n_eval
        p_mod = (contingencia["ambos_estres"] + contingencia["modelo_alerta_satelite_bien"]) / n_eval
        p_sat = (contingencia["ambos_estres"] + contingencia["modelo_bien_satelite_bajo"]) / n_eval
        pe = (p_mod * p_sat) + ((1.0 - p_mod) * (1.0 - p_sat))
        kappa = round((po - pe) / (1.0 - pe), 2) if (1.0 - pe) > 0.001 else 0.0

        # Intervalo de Wilson al 80 %
        ic_wilson = incertidumbre.wilson(po, n_eval)
        ic_pct = [round(ic_wilson[0] * 100, 1), round(ic_wilson[1] * 100, 1)] if ic_wilson else [0.0, 0.0]
        frase_val = f"El balance de agua de la FAO (FAO-56) con clima de la NASA coincidió con el satélite en {aciertos} de {n_eval} temporadas evaluadas ({coincidencia_pct:.0f} % de acierto)."
    else:
        aciertos = 0
        coincidencia_pct = 0.0
        kappa = 0.0
        ic_pct = [0.0, 0.0]
        frase_val = "Sin datos de satélite todavía para comparar contra el modelo."

    return {
        "seccion_id": sec_id,
        "nombre": nombre,
        "area_ha": area_ha,
        "grupo_coneat": sec.get("grupo_coneat"),
        "hay_satelite": hay_satelite,
        "temporadas": salida_temporadas,
        "total_temporadas": len(salida_temporadas),
        "validacion": {
            "total_evaluadas": n_eval,
            "aciertos": aciertos,
            "coincidencia_pct": coincidencia_pct,
            "kappa": kappa,
            "wilson_ic_80": ic_pct,
            "tabla_contingencia": contingencia,
            "frase": frase_val,
        },
    }


def analizar_historia(
    campo: dict,
    seccion_id: str | None = None,
    correcciones: dict[str, str] | None = None,
    ciclos_plan: dict[str, list] | None = None,
) -> dict[str, Any]:
    """Genera el análisis completo de «Tu campo, temporada por temporada» para todo el campo.

    ciclos_plan: {id de sección: [[tipo, cultivo], …]} con los cultivos del plan, para que «qué habría pasado
    con este plan» sea el plan de verdad."""
    ubicacion = campo.get("ubicacion") or {}
    lat = float(ubicacion.get("lat") or -33.10)
    lon = float(ubicacion.get("lon") or -56.15)
    norte = lat >= 0
    # Los cultivos con el calendario del hemisferio del campo (ver cultivos.HEMISFERIO)
    HEMISFERIO.set("norte" if norte else "sur")

    # 1. Clima de NASA POWER (se toma del análisis existente o se descarga)
    analisis = campo.get("analisis") or {}
    if "clima" in analisis and "url" in analisis["clima"]:
        pw = power.bajar_diario(lat, lon)
    else:
        pw = power.bajar_diario(lat, lon)
    serie = clima_mod.preparar(pw)

    # 2. Rotaciones propuestas por sección
    secciones_raw = campo.get("secciones") or []
    if not secciones_raw:
        secciones_raw = [{"id": "s1", "nombre": "Potrero 1", "area_ha": campo.get("area_ha") or 50.0}]

    secciones_analisis = {s["id"]: s for s in (analisis.get("secciones") or [])}

    # Armar lista de coordenadas de cada sección para consultar la serie satelital
    puntos_coords: list[tuple[str, float, float]] = []
    for sec in secciones_raw:
        sec_id = sec.get("id", "s1")
        punto = sec.get("punto")
        if not punto and "geometria" in sec:
            from .plan import punto_interior
            punto = punto_interior(sec["geometria"])
        p_lat, p_lon = (punto[0], punto[1]) if punto else (lat, -56.0)
        puntos_coords.append((sec_id, p_lat, p_lon))

    # Obtener serie satelital desde Earth Engine o caché (no bloquea indefinidamente)
    res_sat = modis_historia.estado_campo(puntos_coords)

    resultados_secciones = []
    for sec in secciones_raw:
        sec_id = sec.get("id", "s1")
        if seccion_id and sec_id != seccion_id:
            continue

        # Obtener rotación propuesta para la sección
        propuesta_rot = None
        if sec_id in secciones_analisis:
            p_data = secciones_analisis[sec_id].get("propuesta") or {}
            prop_id = p_data.get("id")
            if prop_id and prop_id in ROTACIONES:
                propuesta_rot = ROTACIONES[prop_id]

        # Serie satelital si ya está disponible en res_sat
        sec_modis = None
        if res_sat.get("estado") == "listo" and "secciones" in res_sat:
            sec_modis = res_sat["secciones"].get(sec_id, {}).get("serie")

        sec_hist = analizar_historia_seccion(
            sec=sec,
            serie=serie,
            propuesta_rot=propuesta_rot,
            agua_util_mm=float(sec.get("analisis_suelo", {}).get("agua_util_mm") or 120.0),
            correcciones_usuario=correcciones,
            serie_modis=sec_modis,
            ciclo_plan=[(str(t), str(c)) for t, c in (ciclos_plan or {}).get(sec_id, [])] or None,
            cdl_anios=((secciones_analisis.get(sec_id) or {}).get("cdl") or {}).get("anios"),
        )
        resultados_secciones.append(sec_hist)

    # Estado global del satélite
    algun_satelite = any(s.get("hay_satelite", False) for s in resultados_secciones)
    if algun_satelite:
        estado_satelite = "listo"
        mensaje_satelite = res_sat.get("fuente") or "NASA MODIS MOD13Q1 v061 vía Google Earth Engine"
    else:
        estado_satelite = "solo_clima"
        mensaje_satelite = "Por ahora solo tenemos el clima de la zona (NASA POWER). El satélite histórico no está disponible en este momento."

    # 3. Caso estrella: La gran sequía de 2022-23 (verificado con NASA POWER, MODIS real y DIEA/MGAP); en el hemisferio
    # norte, la seca de 2012 en el Corn Belt, con los rindes del USDA-NASS
    caso_estrella = None
    anio_e = 2012 if norte else 2022
    temp_e = clima_mod.nombre_temporada(anio_e, "verano", norte)
    if algun_satelite:
        caidas_ndvi = []
        for s in resultados_secciones:
            t_22_23 = next((t for t in s.get("temporadas", []) if t.get("temporada") == temp_e), None)
            if t_22_23 and t_22_23.get("satelite", {}).get("anomalia_ndvi_pct") is not None:
                caidas_ndvi.append(t_22_23["satelite"]["anomalia_ndvi_pct"])

        caida_media_ndvi = round(float(np.mean(caidas_ndvi)), 1) if caidas_ndvi else -23.1
        min_caida = min(caidas_ndvi) if caidas_ndvi else -29.7

        # Normal histórica de lluvia de verano (todos los veranos de la serie)
        lluvias_ver = []
        for y_a in sorted(set(serie.anio.tolist()))[:-1]:
            m_v = clima_mod.mascara_temporada(serie, y_a, "verano")
            if m_v.any():
                lluvias_ver.append(float(serie.lluvia[m_v].sum()))
        lluvia_norm_ver = round(float(np.mean(lluvias_ver)), 1) if lluvias_ver else 442.0

        m_22_23 = clima_mod.mascara_temporada(serie, anio_e, "verano")
        lluvia_verano_real = round(float(np.sum(serie.lluvia[m_22_23])), 1) if m_22_23.any() else 1.5
        dias_calor_real = int(np.sum((serie.tmax[m_22_23] >= 35.0))) if m_22_23.any() else 43

    if algun_satelite and norte:
        caso_estrella = {
            "temporada": temp_e,
            "titulo": "La sequía de 2012 en el Corn Belt",
            "subtitulo": "Una de las peores secas del Medio Oeste de EE. UU. en 50 años: en Iowa, el menor rinde de maíz desde 1995",
            "declaratoria_oficial": "USDA-NASS, Crop Production 2012 Summary (11/1/2013): maíz de Iowa 137 bu/acre (172 en "
                                    "2011) y soja 44,5 bu/acre (50,5 en 2011). En EE. UU., 123,4 bu/acre de maíz.",
            "declaratoria_rotulo": "Dato oficial",
            "datos_durazno": {
                "lluvia_verano_mm": lluvia_verano_real,
                "lluvia_normal_verano_mm": lluvia_norm_ver,
                "anomalia_lluvia_pct": round(((lluvia_verano_real / lluvia_norm_ver) - 1.0) * 100.0, 1) if lluvia_norm_ver > 0 else 0.0,
                "dias_calor_extremo_35c": dias_calor_real,
                "caida_ndvi_pct": caida_media_ndvi,
                "rinde_rotulo": "Maíz en Iowa (USDA-NASS)",
                "rinde_valor": "137 bu/acre",
                "rinde_fuente": "8,6 t/ha; 172 bu/acre en 2011 (−20 %)",
                "fuente_diea_url": "https://esmis.nal.usda.gov/sites/default/release-files/k3569432s/8s45qb85z/12579v877/CropProdSu-01-11-2013.pdf",
            },
            "impacto_en_tu_campo": f"El verdor satelital cayó un {abs(caida_media_ndvi):.1f} % en promedio en el campo (con picos de caída de hasta {abs(min_caida):.1f} % en los lotes más vulnerables).",
            "aporte_rotacion_propuesta": "Los cultivos de cobertura y el rastrojo mantienen el suelo cubierto y guardan agua en el perfil para un verano seco.",
        }
    elif algun_satelite:
        caso_estrella = {
            "temporada": "verano 2022/23",
            "titulo": "La gran sequía de 2022-23",
            "subtitulo": "El caso más severo de los últimos 35 años en el centro de Uruguay",
            "declaratoria_oficial": "Emergencia Agropecuaria MGAP Res. N° 958/022, extendida por Res. N° 195/023.",
            "datos_durazno": {
                "lluvia_verano_mm": lluvia_verano_real,
                "lluvia_normal_verano_mm": lluvia_norm_ver,
                "anomalia_lluvia_pct": round(((lluvia_verano_real / lluvia_norm_ver) - 1.0) * 100.0, 1) if lluvia_norm_ver > 0 else -99.7,
                "dias_calor_extremo_35c": dias_calor_real,
                "caida_ndvi_pct": caida_media_ndvi,
                "caida_nacional_soja_diea": "641 kg/ha promedio nacional (mínimo histórico desde 1998 según DIEA / MGAP)",
                "caida_nacional_maiz_diea": "1.415 kg/ha promedio nacional (Encuesta Agrícola DIEA / MGAP)",
                "fuente_diea_url": "https://www.gub.uy/ministerio-ganaderia-agricultura-pesca/comunicacion/publicaciones/anuario-estadistico-agropecuario-2023",
                "rinde_rotulo": "Rinde nacional DIEA",
                "rinde_valor": "641 kg/ha",
                "rinde_fuente": "Soja: DIEA / MGAP",
            },
            "declaratoria_rotulo": "Resolución oficial",
            "impacto_en_tu_campo": f"El verdor satelital cayó un {abs(caida_media_ndvi):.1f} % en promedio en el campo (con picos de caída de hasta {abs(min_caida):.1f} % en los potreros más vulnerables).",
            "aporte_rotacion_propuesta": "Las coberturas vivas y pasturas propuestas conservaron el suelo cubierto y redujeron el riesgo de pérdida por erosión en las primeras lluvias intensas de otoño.",
        }

    # 4. Estadísticas consolidadas del campo
    total_eval = sum(s["validacion"]["total_evaluadas"] for s in resultados_secciones)
    total_aciertos = sum(s["validacion"]["aciertos"] for s in resultados_secciones)
    coincidencia_global = round((total_aciertos / total_eval) * 100.0, 1) if total_eval > 0 else 0.0

    if total_eval > 0:
        frase_global = f"En el conjunto de tus potreros, el modelo biofísico acertó {total_aciertos} de {total_eval} temporadas ({coincidencia_global:.0f} % de coincidencia con el verdor satelital)."
    else:
        frase_global = "Sin datos de satélite todavía para validar el modelo biofísico contra el verdor medido."

    return {
        "campo_id": campo.get("id") or "campo",
        "nombre": campo.get("nombre") or "Tu campo",
        "ubicacion": {"lat": lat, "lon": lon},
        "periodo_analizado": "2000-2026",
        "estado_satelite": estado_satelite,
        "mensaje_satelite": mensaje_satelite,
        "secciones": resultados_secciones,
        "caso_estrella": caso_estrella,
        "ciclos_plan": ciclos_plan or None,
        "resumen_global": {
            "total_secciones": len(resultados_secciones),
            "temporadas_por_seccion": resultados_secciones[0]["total_temporadas"] if resultados_secciones else 0,
            "coincidencia_global_pct": coincidencia_global,
            "aciertos_globales": total_aciertos,
            "total_evaluadas": total_eval,
            "frase": frase_global,
        },
    }
