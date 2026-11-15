"""Descarga de SMAP L4 para todo Uruguay con Google Earth Engine.

Genera una grilla de ~9 km dentro del contorno de Uruguay y extrae:
1. Promedios mensuales de sm_rootzone y sm_rootzone_pctl desde abril de 2015.
2. Serie diaria de los últimos 60 días para la consulta de humedad actual («ahora»).

Uso:
  python smap_uruguay_ee.py --probar
  python smap_uruguay_ee.py --completo
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import gzip
import json
import time
from pathlib import Path

import ee
import numpy as np
from shapely.geometry import Point, shape
from shapely.ops import unary_union

DIR_DATOS = Path(__file__).resolve().parents[1] / "fieldshift" / "datos"
ARCHIVO_DEPTOS = DIR_DATOS / "departamentos_uy.json"
ARCHIVO_SALIDA = DIR_DATOS / "smap_uruguay.json.gz"
ARCHIVO_TEMP = DIR_DATOS / "smap_uruguay_mensual_temp.json"

PROYECTO_EE = "field-shift-514100"
COLECCION = "NASA/SMAP/SPL4SMGP/008"
BANDAS = ["sm_rootzone", "sm_rootzone_pctl"]
INICIO_HISTORICO = dt.date(2015, 4, 1)


def generar_grilla_uruguay(paso_km: float = 9.0) -> list[tuple[float, float]]:
    """Genera puntos (lat, lon) espaciados ~paso_km dentro de los límites de Uruguay."""
    if not ARCHIVO_DEPTOS.is_file():
        raise FileNotFoundError(f"No encontré el archivo de contorno: {ARCHIVO_DEPTOS}")

    data = json.loads(ARCHIVO_DEPTOS.read_text(encoding="utf-8"))
    pais = unary_union([shape(f["geometry"]) for f in data["features"]])
    minx, miny, maxx, maxy = pais.bounds

    step_lat = paso_km / 111.0
    step_lon = paso_km / (111.0 * np.cos(np.radians(-32.5)))

    lats = np.arange(miny + step_lat / 2, maxy, step_lat)
    lons = np.arange(minx + step_lon / 2, maxx, step_lon)

    puntos = []
    for la in lats:
        for lo in lons:
            if pais.contains(Point(lo, la)):
                puntos.append((round(float(la), 4), round(float(lo), 4)))

    return puntos


def crear_feature_collection(puntos: list[tuple[float, float]]) -> ee.FeatureCollection:
    feats = [
        ee.Feature(ee.Geometry.Point([lo, la]), {"i": idx})
        for idx, (la, lo) in enumerate(puntos)
    ]
    return ee.FeatureCollection(feats)


def lista_meses(desde: dt.date, hasta: dt.date) -> list[str]:
    """Lista de meses YYYY-MM entre dos fechas."""
    meses = []
    curr = dt.date(desde.year, desde.month, 1)
    while curr < hasta:
        meses.append(curr.strftime("%Y-%m"))
        y = curr.year + (1 if curr.month == 12 else 0)
        m = 1 if curr.month == 12 else curr.month + 1
        curr = dt.date(y, m, 1)
    return meses


def muestrear_rango(col: ee.ImageCollection, fc: ee.FeatureCollection, t_ini: str, t_fin: str) -> dict[int, tuple[float | None, float | None]]:
    """Calcula el promedio temporal en [t_ini, t_fin) y muestrea los puntos de fc."""
    try:
        img = col.filterDate(t_ini, t_fin).mean()
        muestras = img.sampleRegions(collection=fc, scale=11000, geometries=False)
        info = muestras.getInfo()
    except ee.EEException as e:
        if "Invalid numInputs: 0" in str(e):
            return {}
        raise

    res: dict[int, tuple[float | None, float | None]] = {}
    for f in info.get("features", []):
        props = f.get("properties", {})
        idx = props.get("i")
        if idx is not None:
            sm = props.get("sm_rootzone")
            pc = props.get("sm_rootzone_pctl")
            res[idx] = (
                round(float(sm), 4) if sm is not None else None,
                round(float(pc), 1) if pc is not None else None,
            )
    return res


def probar(n_meses: int = 3):
    print("Iniciando Earth Engine...")
    ee.Initialize(project=PROYECTO_EE)
    col = ee.ImageCollection(COLECCION).select(BANDAS)

    print("Generando grilla de Uruguay a ~9 km...")
    puntos = generar_grilla_uruguay(9.0)
    print(f"Puntos dentro del país: {len(puntos)}")

    fc = crear_feature_collection(puntos)

    meses_test = ["2023-01", "2023-02", "2023-03"][:n_meses]
    tiempos = []
    for m in meses_test:
        t0 = time.time()
        y, mo = int(m[:4]), int(m[5:7])
        d1 = dt.date(y, mo, 1)
        d2 = dt.date(y + 1, 1, 1) if mo == 12 else dt.date(y, mo + 1, 1)
        vals = muestrear_rango(col, fc, d1.isoformat(), d2.isoformat())
        dur = time.time() - t0
        tiempos.append(dur)
        print(f"  Mes {m}: {len(vals)} puntos con dato en {dur:.2f} s")

    t_prom = float(np.mean(tiempos))
    hoy = dt.date.today()
    total_meses = len(lista_meses(INICIO_HISTORICO, dt.date(hoy.year, hoy.month, 1)))
    est_total_min = (total_meses * t_prom) / 60
    est_paralelo_min = est_total_min / 3.5

    print(f"\nTiempo promedio por mes: {t_prom:.2f} s")
    print(f"Total meses históricos (2015-04 a hoy): {total_meses}")
    print(f"Estimación secuencial: {est_total_min:.1f} minutos (~{est_total_min*60:.0f} s)")
    print(f"Estimación con 4 conexiones simultáneas: {est_paralelo_min:.1f} minutos (~{est_paralelo_min*60:.0f} s)")


def descargar_todo(max_workers: int = 4):
    print("Iniciando Earth Engine...")
    ee.Initialize(project=PROYECTO_EE)
    col = ee.ImageCollection(COLECCION).select(BANDAS)

    print("Generando grilla de Uruguay a ~9 km...")
    puntos = generar_grilla_uruguay(9.0)
    N = len(puntos)
    print(f"Puntos dentro del país: {N}")
    fc = crear_feature_collection(puntos)

    hoy = dt.date.today()
    primer_dia_mes_actual = dt.date(hoy.year, hoy.month, 1)
    meses = lista_meses(INICIO_HISTORICO, primer_dia_mes_actual)
    M = len(meses)

    t0_global = time.time()

    # Verificar si ya tenemos el checkpoint mensual
    cargar_temp = False
    if ARCHIVO_TEMP.is_file():
        try:
            cached = json.loads(ARCHIVO_TEMP.read_text(encoding="utf-8"))
            if cached.get("meses") == meses and len(cached.get("sm_mensual", [])) == N:
                print(f"Cargando {M} meses históricos desde archivo temporal ({ARCHIVO_TEMP.name})...")
                sm_mensual = cached["sm_mensual"]
                pc_mensual = cached["pc_mensual"]
                cargar_temp = True
        except Exception:
            cargar_temp = False

    if not cargar_temp:
        print(f"Descargando histórico mensual ({M} meses, {meses[0]} a {meses[-1]})...")
        sm_mensual = [[None] * M for _ in range(N)]
        pc_mensual = [[None] * M for _ in range(N)]

        def procesar_un_mes(m_idx: int, m_str: str):
            y, mo = int(m_str[:4]), int(m_str[5:7])
            d1 = dt.date(y, mo, 1)
            d2 = dt.date(y + 1, 1, 1) if mo == 12 else dt.date(y, mo + 1, 1)
            t_ini, t_fin = d1.isoformat(), d2.isoformat()
            res = muestrear_rango(col, fc, t_ini, t_fin)
            return m_idx, m_str, res

        completados = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futuros = [
                executor.submit(procesar_un_mes, i, m)
                for i, m in enumerate(meses)
            ]
            for fut in concurrent.futures.as_completed(futuros):
                m_idx, m_str, res = fut.result()
                for p_idx, (sm, pc) in res.items():
                    sm_mensual[p_idx][m_idx] = sm
                    pc_mensual[p_idx][m_idx] = pc
                completados += 1
                if completados % 10 == 0 or completados == M:
                    transcurrido = time.time() - t0_global
                    ritmo = transcurrido / completados
                    restante = ritmo * (M - completados)
                    print(f"  Histórico: {completados}/{M} meses ({completados*100//M}%) - "
                          f"Restante est: {restante/60:.1f} min")

        # Guardar checkpoint mensual
        try:
            ARCHIVO_TEMP.write_text(json.dumps({
                "meses": meses,
                "sm_mensual": sm_mensual,
                "pc_mensual": pc_mensual,
            }), encoding="utf-8")
            print(f"Guardado temporal mensual en {ARCHIVO_TEMP.name}.")
        except Exception as e:
            print(f"Aviso: no pude guardar temporal: {e}")

    # Consultar última fecha disponible en Earth Engine
    ult_img = col.sort("system:time_start", False).first()
    ts_ult = ult_img.get("system:time_start").getInfo()
    dt_ult = dt.datetime.fromtimestamp(ts_ult / 1000, tz=dt.timezone.utc).date()
    print(f"\nÚltima fecha con datos SMAP en Earth Engine: {dt_ult.isoformat()}")

    # Generar últimos 60 días hasta dt_ult
    dias_lista = [(dt_ult - dt.timedelta(days=59 - i)).isoformat() for i in range(60)]
    D = len(dias_lista)
    print(f"Descargando últimos {D} días para el 'ahora' ({dias_lista[0]} a {dias_lista[-1]})...")

    sm_diario = [[None] * D for _ in range(N)]
    pc_diario = [[None] * D for _ in range(N)]

    def procesar_un_dia(d_idx: int, d_str: str):
        d1 = dt.date.fromisoformat(d_str)
        d2 = d1 + dt.timedelta(days=1)
        res = muestrear_rango(col, fc, d1.isoformat(), d2.isoformat())
        return d_idx, d_str, res

    completados_d = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futuros_d = [
            executor.submit(procesar_un_dia, i, d)
            for i, d in enumerate(dias_lista)
        ]
        for fut in concurrent.futures.as_completed(futuros_d):
            d_idx, d_str, res = fut.result()
            for p_idx, (sm, pc) in res.items():
                sm_diario[p_idx][d_idx] = sm
                pc_diario[p_idx][d_idx] = pc
            completados_d += 1
            if completados_d % 15 == 0 or completados_d == D:
                print(f"  Diario: {completados_d}/{D} días ({completados_d*100//D}%)")

    # Armar estructura final
    paquete = {
        "fuente": "NASA SMAP L4 (SPL4SMGP.008) vía Google Earth Engine",
        "generado": hoy.isoformat(),
        "paso_km": 9.0,
        "puntos": puntos,  # [[lat, lon]...]
        "meses": meses,    # ["2015-04"..., "2026-10"]
        "sm_mensual": sm_mensual,  # [punto_idx][mes_idx]
        "pc_mensual": pc_mensual,
        "dias": dias_lista,  # ["YYYY-MM-DD"...]
        "sm_diario": sm_diario,
        "pc_diario": pc_diario,
    }

    print(f"\nGuardando en {ARCHIVO_SALIDA} con compresión gzip...")
    raw = json.dumps(paquete, separators=(",", ":")).encode("utf-8")
    with gzip.open(ARCHIVO_SALIDA, "wb", compresslevel=6) as f_gz:
        f_gz.write(raw)

    tam_mb = ARCHIVO_SALIDA.stat().st_size / (1024 * 1024)
    tiempo_total = time.time() - t0_global
    print(f"¡Listo! Archivo guardado: {tam_mb:.2f} MB en {tiempo_total/60:.1f} minutos.")

    # Si todo salió bien, limpiar el temporal mensual
    if ARCHIVO_TEMP.is_file():
        try:
            ARCHIVO_TEMP.unlink()
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description="SMAP L4 para todo Uruguay con Earth Engine")
    parser.add_argument("--probar", action="store_true", help="Probar 3 meses y medir tiempos")
    parser.add_argument("--completo", action="store_true", help="Descargar todo el histórico y días recientes")
    parser.add_argument("--workers", type=int, default=4, help="Número de conexiones simultáneas")
    args = parser.parse_args()

    if args.completo:
        descargar_todo(max_workers=args.workers)
    else:
        probar(n_meses=3)


if __name__ == "__main__":
    main()
