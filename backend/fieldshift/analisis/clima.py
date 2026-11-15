"""Análisis climático del campo a partir de NASA POWER (diario 1991 → hoy).

Qué calcula, todo reproducible y con la fórmula a la vista:
1. ET0 diaria por FAO-56 Penman-Monteith (Allen et al. 1998, ec. 6) con temperatura, humedad,
   viento y radiación de POWER.
2. Balance de agua del suelo por cultivo (modelo de "balde" FAO-56 cap. 8): para cada año y cada
   cultivo, cuántos días de su ventana crítica pasa con el agua por debajo del umbral de estrés.
   → probabilidad de seca en el período que define el rendimiento.
3. Riesgo de helada (T2M_MIN) y de calor (T2M_MAX) dentro de la ventana sensible de cada cultivo.
4. Erosividad de la lluvia: en qué meses cae la lluvia que erosiona (días ≥ 12,7 mm, energía
   ∝ P^1,81) y un factor R anual estimado con Renard y Freimund (1994).
5. Corrimiento del clima ("Field Shift"): los mismos riesgos en 1991-2008 contra 2009-hoy.
6. Esta zafra contra lo normal: lluvia de los últimos 90 días y humedad de raíces actual.

Límites que se dicen en la app: POWER es una celda de ~50 km (no ve bajos ni lomas), la helada a
2 m subestima la del pasto en bajos, y las lluvias extremas se suavizan al promediar la celda.
"""

from __future__ import annotations

import calendar
import datetime as dt
import math
from dataclasses import dataclass, replace

import numpy as np

from .cultivos import CULTIVOS, Cultivo

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
UMBRAL_HELADA = 0.0  # °C a 2 m: helada meteorológica
UMBRAL_HELADA_AGRO = 2.0  # °C a 2 m: a nivel de cultivo suele ser 2-4 °C más fría
P_AGOTAMIENTO = 0.5  # fracción del agua disponible que se usa sin estrés (FAO-56, tabla 22)


@dataclass
class Serie:
    fechas: list[dt.date]
    anio: np.ndarray
    mes: np.ndarray
    doy: np.ndarray
    tmax: np.ndarray
    tmin: np.ndarray
    lluvia: np.ndarray
    rad: np.ndarray
    hr: np.ndarray
    viento: np.ndarray
    gwet: np.ndarray
    et0: np.ndarray
    elevacion: float
    lat: float
    # de dónde salió la lluvia: "GPM IMERG" desde 2000 o "NASA POWER" si IMERG no contestó
    fuente_lluvia: str = "NASA POWER"
    # días a los que les faltaba algún dato y se completaron con el promedio de ese día del año
    dias_completados: int = 0
    # primer día con lluvia de IMERG: para contar tormentas solo con IMERG, que no las suaviza como POWER
    lluvia_desde: dt.date | None = None
    # estaciones de INUMET con las que se corrigió la temperatura; vacío si quedó la de POWER
    temp_corregida: tuple[str, ...] = ()
    # el viento de POWER venía roto (promedio < 0,5 m/s) y se usó 2 m/s, como dice FAO-56 cuando falta el dato
    viento_fijo: bool = False


def fuente_lluvia(power: dict) -> str:
    """Nombre corto de la fuente de la lluvia, para los textos: "GPM IMERG" si se mezcló, si no "NASA POWER"."""
    return "GPM IMERG" if (power.get("lluvia") or {}).get("dias_imerg") else "NASA POWER"


def _rellenar(x: list, doy: np.ndarray, nombre: str = "") -> tuple[np.ndarray, np.ndarray]:
    """Huecos (-999) → promedio del mismo día del año; si no hay, interpolación. Devuelve la serie y qué días se
    completaron, para poder decirlo. Si no vino ningún dato, error: no se inventa una serie entera."""
    a = np.array([np.nan if v is None else v for v in x], dtype=float)
    huecos = np.isnan(a)
    if huecos.all():
        raise ValueError(f"La NASA no trajo ningún dato de {nombre or 'una variable del clima'} para este punto.")
    if huecos.any():
        clim = np.full(367, np.nan)
        for d in range(1, 367):
            m = (doy == d) & ~huecos
            if m.any():
                clim[d] = a[m].mean()
        a[huecos] = clim[doy[huecos]]
        if np.isnan(a).any():
            idx = np.arange(len(a))
            ok = ~np.isnan(a)
            a[~ok] = np.interp(idx[~ok], idx[ok], a[ok])
    return a, huecos


def et0_penman_monteith(tmax, tmin, rad, hr, viento, doy, lat_deg, z):
    """FAO-56 ec. 6, paso diario. Unidades: °C, MJ/m²/día, %, m/s, m → mm/día."""
    tmed = (tmax + tmin) / 2
    presion = 101.3 * ((293 - 0.0065 * z) / 293) ** 5.26
    gamma = 0.000665 * presion
    e0 = lambda t: 0.6108 * np.exp(17.27 * t / (t + 237.3))  # noqa: E731
    es = (e0(tmax) + e0(tmin)) / 2
    ea = np.clip(hr, 1, 100) / 100 * es
    delta = 4098 * e0(tmed) / (tmed + 237.3) ** 2
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    decl = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(decl), -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.sin(ws)
    )
    rso = (0.75 + 2e-5 * z) * ra
    rns = 0.77 * rad
    sigma = 4.903e-9
    rel = np.clip(rad / np.maximum(rso, 0.1), 0.3, 1.0)
    rnl = sigma * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 * (0.34 - 0.14 * np.sqrt(ea)) * (
        1.35 * rel - 0.35
    )
    rn = rns - rnl
    et0 = (0.408 * delta * rn + gamma * 900 / (tmed + 273) * viento * (es - ea)) / (
        delta + gamma * (1 + 0.34 * viento)
    )
    return np.clip(et0, 0, None)


VIENTO_MIN_CREIBLE = 0.5  # m/s de promedio; en Uruguay el real anda en 2-4
VIENTO_FAO = 2.0  # FAO-56: cuando no hay dato de viento, 2 m/s


def preparar(power: dict, corregir_temperatura: bool = True) -> Serie:
    """La serie diaria lista para el motor. La máxima y la mínima de POWER se corrigen con las estaciones
    de INUMET (`fuentes/temperatura_inumet.py`; POWER exagera el calor del verano y le faltan heladas), y si el viento
    de la celda viene roto (en Cerro Largo / Treinta y Tres da 0,1 m/s) se usa 2 m/s. `corregir_temperatura=False` da
    POWER tal cual (para compararlo con la estación del productor)."""
    fechas = [dt.date(int(f[:4]), int(f[4:6]), int(f[6:8])) for f in power["fechas"]]
    anio = np.array([f.year for f in fechas])
    mes = np.array([f.month for f in fechas])
    doy = np.array([f.timetuple().tm_yday for f in fechas])
    faltaba = np.zeros(len(fechas), dtype=bool)

    def var(clave: str, nombre: str) -> np.ndarray:
        nonlocal faltaba
        a, huecos = _rellenar(power[clave], doy, nombre)
        faltaba |= huecos
        return a

    tmax = var("T2M_MAX", "temperatura máxima")
    tmin = var("T2M_MIN", "temperatura mínima")
    lluvia = np.clip(var("PRECTOTCORR", "lluvia"), 0, None)
    rad = var("ALLSKY_SFC_SW_DWN", "radiación")
    hr = var("RH2M", "humedad del aire")
    viento = var("WS2M", "viento")
    gwet = var("GWETROOT", "humedad del suelo")
    viento_fijo = bool(np.nanmean(viento) < VIENTO_MIN_CREIBLE)
    if viento_fijo:
        viento = np.full_like(viento, VIENTO_FAO)
    estaciones: list[str] = []
    if corregir_temperatura:
        from ..fuentes import temperatura_inumet

        tmax, tmin, estaciones = temperatura_inumet.corregir(mes, tmax, tmin, power["lat"], power["lon"])
    z = float(power.get("elevacion") or 100)
    et0 = et0_penman_monteith(tmax, tmin, rad, hr, viento, doy, power["lat"], z)
    desde = (power.get("lluvia") or {}).get("desde") if fuente_lluvia(power) == "GPM IMERG" else None
    desde_f = dt.date(int(desde[:4]), int(desde[4:6]), int(desde[6:8])) if desde else None
    return Serie(fechas, anio, mes, doy, tmax, tmin, lluvia, rad, hr, viento, gwet, et0, z, power["lat"], fuente_lluvia(power),
                 int(faltaba.sum()), desde_f, tuple(estaciones), viento_fijo)


# --------------------------------------------------------------------------------------------
# Balance de agua por cultivo
# --------------------------------------------------------------------------------------------


def _kc_diario(c: Cultivo) -> np.ndarray:
    ini, des, med, fin = c.etapas
    kc_ini, kc_med, kc_fin = c.kc
    partes = [np.full(ini, kc_ini)]
    if des:
        partes.append(np.linspace(kc_ini, kc_med, des, endpoint=False))
    partes.append(np.full(med, kc_med))
    if fin:
        partes.append(np.linspace(kc_med, kc_fin, fin))
    return np.concatenate(partes)


def _indice(serie: Serie, fecha: dt.date) -> int | None:
    i = (fecha - serie.fechas[0]).days
    return i if 0 <= i < len(serie.fechas) else None


def riesgos_cultivo(serie: Serie, c: Cultivo, agua_util_mm: float, anios: list[int] | None = None) -> dict:
    """Probabilidades por año de seca, helada y calor en las ventanas sensibles del cultivo."""
    if c.temporada == "barbecho":
        return {}
    kc = _kc_diario(c)
    if c.temporada == "perenne":
        kc = np.full(365, c.kc[1])
    ciclo = len(kc)
    taw = agua_util_mm
    raw = P_AGOTAMIENTO * taw
    anios_disp = sorted(set(serie.anio.tolist()))
    resultados = []
    for y in anios_disp:
        if anios is not None and y not in anios:
            continue
        try:
            siembra = dt.date(y, c.siembra[0], c.siembra[1])
        except ValueError:
            continue
        i0 = _indice(serie, siembra - dt.timedelta(days=60))
        i_s = _indice(serie, siembra)
        i_f = _indice(serie, siembra + dt.timedelta(days=ciclo - 1))
        if i0 is None or i_s is None or i_f is None:
            continue
        # balance: arranca en barbecho 60 días antes, con medio perfil
        dr = taw * 0.5
        estres = np.zeros(ciclo, dtype=bool)
        eta_sum = np.zeros(ciclo)
        etc_sum = np.zeros(ciclo)
        for i in range(i0, i_f + 1):
            k = i - i_s
            kci = 0.30 if k < 0 else kc[k]
            etc = kci * serie.et0[i]
            ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / (taw - raw))
            eta = ks * etc
            dr = min(taw, max(0.0, dr - serie.lluvia[i] + eta))
            if k >= 0:
                estres[k] = dr > raw
                eta_sum[k] = eta
                etc_sum[k] = etc
        fila: dict = {"anio": y}
        # pérdida de rinde por falta de agua en toda la temporada, FAO-33 (Doorenbos y Kassam 1979):
        # 1 - Yr/Ym = Ky (1 - ETr/ETm). Solo cultivos de cosecha (Ky > 0)
        if c.ky > 0 and etc_sum.sum() > 0:
            fila["eta_etc_ciclo"] = float(eta_sum.sum() / etc_sum.sum())
            fila["perdida_rinde"] = float(min(1.0, max(0.0, c.ky * (1 - fila["eta_etc_ciclo"]))))
        if c.ventana_agua:
            a, b = c.ventana_agua.desde, min(c.ventana_agua.hasta, ciclo - 1)
            fila["dias_estres"] = int(estres[a : b + 1].sum())
            fila["frac_estres"] = float(estres[a : b + 1].mean())
            etc_v = etc_sum[a : b + 1].sum()
            fila["eta_etc"] = float(eta_sum[a : b + 1].sum() / etc_v) if etc_v > 0 else 1.0
            fila["lluvia_ventana"] = float(serie.lluvia[i_s + a : i_s + b + 1].sum())
        if c.ventana_helada:
            a, b = c.ventana_helada.desde, c.ventana_helada.hasta
            tmin = serie.tmin[i_s + a : i_s + b + 1]
            fila["helada"] = bool((tmin <= UMBRAL_HELADA).any())
            fila["helada_agro"] = bool((tmin <= UMBRAL_HELADA_AGRO).any())
        if c.ventana_calor:
            a, b = c.ventana_calor.desde, c.ventana_calor.hasta
            tmax = serie.tmax[i_s + a : i_s + b + 1]
            fila["dias_calor"] = int((tmax >= c.umbral_calor).sum())
            fila["calor"] = fila["dias_calor"] >= 3
        resultados.append(fila)

    cuentas: dict[str, tuple[int, int]] = {}

    def prob(nombre_riesgo, clave, cond=lambda v: bool(v)):
        vals = [cond(r[clave]) for r in resultados if clave in r]
        if not vals:
            return None
        k = int(sum(vals))
        n = len(vals)
        cuentas[nombre_riesgo] = (k, n)
        return round(k / n, 3)

    salida = {
        "cultivo": c.codigo,
        "anios_evaluados": len(resultados),
        # año de seca = el cultivo pasó su ventana crítica con menos de la mitad del agua que pedía
        "prob_seca": prob("prob_seca", "eta_etc", lambda v: v < 0.5),
        "deficit_medio": (
            round(float(np.mean([1 - r["eta_etc"] for r in resultados if "eta_etc" in r])), 3)
            if c.ventana_agua and resultados
            else None
        ),
        **_perdidas(resultados),
        "prob_helada": prob("prob_helada", "helada"),
        "prob_helada_agro": prob("prob_helada_agro", "helada_agro"),
        "prob_calor": prob("prob_calor", "calor"),
        "ventana_agua": _texto_ventana(c, c.ventana_agua),
        "ventana_helada": _texto_ventana(c, c.ventana_helada),
        "ventana_calor": _texto_ventana(c, c.ventana_calor),
        "por_anio": resultados,
        "cuentas": cuentas,
    }
    return salida


def _perdidas(resultados: list[dict]) -> dict:
    """Pérdida de rinde por seca, de 1991 a hoy:
    - `perdida_media` y `perdida_anio_seco` (percentil 80: el año seco que se da 1 de cada 5), en fracción del rinde
      sin ninguna falta de agua, que en secano casi nunca se da;
    - `caida_anio_seco`: cuánto menos rinde ese año seco que un año normal (la mediana). Es la que se muestra, porque
      el productor compara con lo que cosecha normalmente: 1 - (1 - p80) / (1 - mediana)."""
    v = [r["perdida_rinde"] for r in resultados if "perdida_rinde" in r]
    if not v:
        return {"perdida_media": None, "perdida_anio_seco": None, "caida_anio_seco": None}
    mediana, p80 = float(np.median(v)), float(np.percentile(v, 80))
    caida = 1 - (1 - p80) / (1 - mediana) if mediana < 1 else 1.0
    return {"perdida_media": round(float(np.mean(v)), 3), "perdida_anio_seco": round(p80, 3),
            "caida_anio_seco": round(max(0.0, caida), 3)}


def _texto_ventana(c: Cultivo, v) -> str | None:
    if not v:
        return None
    base = dt.date(2001, c.siembra[0], c.siembra[1])
    a = base + dt.timedelta(days=v.desde)
    b = base + dt.timedelta(days=v.hasta)
    return f"{v.que}: {a.day} {MESES[a.month - 1]} a {b.day} {MESES[b.month - 1]}"


# --------------------------------------------------------------------------------------------
# Climatología, erosividad, tendencia, zafra actual
# --------------------------------------------------------------------------------------------


def _anios_completos(serie: Serie) -> list[int]:
    cuenta = {}
    for y in serie.anio:
        cuenta[y] = cuenta.get(y, 0) + 1
    return sorted(y for y, n in cuenta.items() if n >= 360)


def climatologia_mensual(serie: Serie) -> list[dict]:
    anios = _anios_completos(serie)
    sel = np.isin(serie.anio, anios)
    n = len(anios)
    out = []
    for m in range(1, 13):
        mm = sel & (serie.mes == m)
        out.append(
            {
                "mes": MESES[m - 1],
                "lluvia_mm": round(float(serie.lluvia[mm].sum() / n), 1),
                "et0_mm": round(float(serie.et0[mm].sum() / n), 1),
                "balance_mm": round(float((serie.lluvia[mm] - serie.et0[mm]).sum() / n), 1),
                "tmax": round(float(serie.tmax[mm].mean()), 1),
                "tmin": round(float(serie.tmin[mm].mean()), 1),
                "dias_helada": round(float((serie.tmin[mm] <= UMBRAL_HELADA).sum() / n), 1),
                "dias_lluvia_fuerte": round(float((serie.lluvia[mm] >= 40).sum() / n), 2),
                "humedad_raices": round(float(serie.gwet[mm].mean()), 3),
            }
        )
    return out


def r_desde_lluvia(p_mm: float) -> float:
    """Estimación del factor R (MJ·mm/(ha·h·año)) a partir de precipitación anual (Renard y Freimund 1994)."""
    if p_mm < 850:
        return 0.0483 * (p_mm**1.61)
    return 587.8 - 1.219 * p_mm + 0.004105 * (p_mm**2)


def erosividad(serie: Serie) -> dict:
    """Reparto mensual de la lluvia erosiva y R anual estimado.

    - Reparto: suma de P^1,81 de los días con P ≥ 12,7 mm (forma de Richardson et al. 1983).
    - R anual: Renard y Freimund (1994) con la lluvia anual media (MJ·mm/ha/h/año).
      Fórmula de memoria, a verificar; el MGAP tiene un mapa oficial de R (servicio
      EROSION/FACTOR_R) que no respondió en la prueba.
    """
    anios = _anios_completos(serie)
    sel = np.isin(serie.anio, anios)
    p = np.where(sel & (serie.lluvia >= 12.7), serie.lluvia, 0.0)
    energia = p**1.81
    por_mes = np.array([energia[serie.mes == m].sum() for m in range(1, 13)])
    if por_mes.sum() <= 0:  # ningún día erosivo (serie corta o muy seca): se reparte según la lluvia total
        por_mes = np.array([serie.lluvia[sel & (serie.mes == m)].sum() for m in range(1, 13)]) + 1e-9
    reparto = por_mes / por_mes.sum()
    p_anual = float(serie.lluvia[sel].sum() / len(anios))
    r = r_desde_lluvia(p_anual)
    return {
        "lluvia_anual_mm": round(p_anual),
        "r_anual": round(r),
        "unidad_r": "MJ·mm/(ha·h·año)",
        "reparto_mensual": [round(float(x), 4) for x in reparto],
        "meses_pico": [MESES[i] for i in np.argsort(-reparto)[:3]],
        "metodo": f"Reparto: P^1,81 de días ≥ 12,7 mm ({serie.fuente_lluvia}). R: Renard y Freimund 1994.",
    }


TORMENTA_MM = 50.0  # lluvia de un día que ya arrastra suelo descubierto
TORMENTA_GRANDE_MM = 100.0


def tormentas(serie: Serie) -> dict | None:
    """Cuántas lluvias de 50 mm o más en un día caen por año y en qué meses.

    La lista de recursos del desafío pide IMERG para la frecuencia de tormentas y el riesgo de erosión. Se cuentan solo
    los años enteros con lluvia de IMERG (celda de ~10 km): POWER promedia ~50 km y las achata (en el campo de ejemplo,
    2,8 por año contra 4,2 de IMERG en 2001-2025). Sin IMERG se usa POWER y se avisa.
    """
    anios = _anios_completos(serie)
    if serie.lluvia_desde:
        d = serie.lluvia_desde
        primero = d.year if (d.month, d.day) == (1, 1) else d.year + 1
        anios = [y for y in anios if y >= primero]
    if len(anios) < 5:
        return None
    sel = np.isin(serie.anio, anios)
    n = len(anios)
    grande = sel & (serie.lluvia >= TORMENTA_MM)
    por_mes = [round(float((grande & (serie.mes == k)).sum()) / n, 2) for k in range(1, 13)]
    i = int(np.argmax(np.where(sel, serie.lluvia, -1.0)))
    n_grandes = int((sel & (serie.lluvia >= TORMENTA_GRANDE_MM)).sum())
    por_anio = [int((grande & (serie.anio == y)).sum()) for y in anios]
    return {
        "umbral_mm": TORMENTA_MM,
        "umbral_grande_mm": TORMENTA_GRANDE_MM,
        "por_anio": round(float(grande.sum()) / n, 1),
        "por_mes": por_mes,
        "meses_pico": [MESES[k] for k in np.argsort(-np.array(por_mes), kind="stable")[:3]],
        "anios_sin": sum(1 for x in por_anio if x == 0),
        "anio_mas": {"anio": int(anios[int(np.argmax(por_anio))]), "cuantas": max(por_anio)},
        "grandes": n_grandes,
        "cada_anios_grande": round(n / n_grandes, 1) if n_grandes else None,
        "maxima": {"mm": round(float(serie.lluvia[i])), "fecha": serie.fechas[i].isoformat()},
        "periodo": f"{anios[0]}-{anios[-1]}",
        "anios": n,
        "fuente": serie.fuente_lluvia,
    }


def mascara_temporada(serie: Serie, anio: int, tipo: str) -> np.ndarray:
    """Días de una temporada agrícola. Sur: invierno de junio a octubre del año, verano de diciembre a marzo
    siguiente. Norte: verano de mayo a septiembre del año, invierno de octubre a abril siguiente."""
    norte = serie.lat >= 0
    if tipo == "invierno" and norte:
        return ((serie.anio == anio) & (serie.mes >= 10)) | ((serie.anio == anio + 1) & (serie.mes <= 4))
    if tipo == "verano" and norte:
        return (serie.anio == anio) & np.isin(serie.mes, (5, 6, 7, 8, 9))
    if tipo == "invierno":
        return (serie.anio == anio) & np.isin(serie.mes, (6, 7, 8, 9, 10))
    if tipo == "verano":
        return ((serie.anio == anio) & (serie.mes == 12)) | ((serie.anio == anio + 1) & np.isin(serie.mes, (1, 2, 3)))
    raise ValueError(f"tipo desconocido: {tipo}")


def nombre_temporada(anio: int, tipo: str, norte: bool) -> str:
    """«invierno 2022» y «verano 2022/23» en el sur; «verano 2012» e «invierno 2012/13» en el norte."""
    cruza = (tipo == "verano") != norte
    return f"{tipo} {anio}/{str(anio + 1)[2:]}" if cruza else f"{tipo} {anio}"


def erosividad_temporada(serie: Serie, anio: int, tipo: str) -> dict:
    """Lluvia, energía erosiva y factor R estimado para una temporada agrícola específica."""
    norte = serie.lat >= 0
    m = mascara_temporada(serie, anio, tipo)

    lluvia_temp = float(serie.lluvia[m].sum()) if m.any() else 0.0
    p = np.where(m & (serie.lluvia >= 12.7), serie.lluvia, 0.0)
    energia_temp = float(np.sum(p**1.81))
    dias_erosivos = int(np.sum(m & (serie.lluvia >= 12.7)))

    ref_anio = anio if (tipo == "invierno") != norte else anio + 1
    m_anual = serie.anio == ref_anio
    lluvia_anual = float(serie.lluvia[m_anual].sum()) if m_anual.any() else lluvia_temp
    r_anual_anio = r_desde_lluvia(lluvia_anual)

    p_anual_erosiva = np.where(m_anual & (serie.lluvia >= 12.7), serie.lluvia, 0.0)
    energia_anual = float(np.sum(p_anual_erosiva**1.81))

    if energia_anual > 0:
        r_temp = r_anual_anio * (energia_temp / energia_anual)
    elif lluvia_anual > 0:
        r_temp = r_anual_anio * (lluvia_temp / lluvia_anual)
    else:
        r_temp = 0.0

    return {
        "lluvia_mm": round(lluvia_temp, 1),
        "dias_erosivos": dias_erosivos,
        "energia_erosiva": round(energia_temp, 1),
        "r_temporada": round(r_temp, 1),
    }


def _ultima_helada(serie: Serie, y: int) -> int | None:
    """Día del año de la última helada del invierno: la de primavera (jul-dic en el sur, ene-jun en el norte)."""
    primavera = serie.mes <= 6 if serie.lat >= 0 else serie.mes >= 7
    m = (serie.anio == y) & primavera & (serie.tmin <= UMBRAL_HELADA)
    return int(serie.doy[m].max()) if m.any() else None


def _primera_helada(serie: Serie, y: int) -> int | None:
    """Día del año de la primera helada del otoño (ene-jun en el sur, jul-dic en el norte)."""
    otonio = serie.mes >= 7 if serie.lat >= 0 else serie.mes <= 6
    m = (serie.anio == y) & otonio & (serie.tmin <= UMBRAL_HELADA)
    return int(serie.doy[m].min()) if m.any() else None


def _doy_a_texto(d: float | None) -> str | None:
    if d is None:
        return None
    f = dt.date(2001, 1, 1) + dt.timedelta(days=int(round(d)) - 1)
    return f"{f.day} {MESES[f.month - 1]}"


def es_cambio_claro(antes: float | None, ahora: float | None, umbral: float = 0.2) -> bool:
    """Determina si la diferencia entre dos períodos es un cambio claro (≥ 2 años de cada 10).

    Con períodos de ~17-18 años, diferencias menores a 0,2 suelen ser puro azar (p > 0,20).
    """
    if antes is None or ahora is None:
        return False
    return round(abs(ahora - antes), 4) >= (umbral - 1e-9)


def tendencia(serie: Serie, agua_util_mm: float, cultivos_clave: list[str]) -> dict:
    anios = _anios_completos(serie)
    corte = 2008
    a = [y for y in anios if y <= corte]
    b = [y for y in anios if y > corte]

    def lluvia_anual(ys):
        return float(np.mean([serie.lluvia[serie.anio == y].sum() for y in ys]))

    def dias_calor_verano(ys):
        vals = []
        for y in ys:
            if serie.lat >= 0:  # Hemisferio norte, junio a agosto
                m = (serie.anio == y) & np.isin(serie.mes, (6, 7, 8))
            else:
                m = ((serie.anio == y) & (serie.mes <= 2)) | ((serie.anio == y - 1) & (serie.mes == 12))
            vals.append(int((serie.tmax[m] >= 35).sum()))
        return float(np.mean(vals))

    def media_doy(fn, ys):
        v = [fn(serie, y) for y in ys]
        v = [x for x in v if x is not None]
        return float(np.mean(v)) if v else None

    def dias_helada(ys):
        return float(np.mean([int(((serie.anio == y) & (serie.tmin <= UMBRAL_HELADA)).sum()) for y in ys]))

    cultivos = {}
    for cod in cultivos_clave:
        c = CULTIVOS[cod]
        ra = riesgos_cultivo(serie, c, agua_util_mm, a)
        rb = riesgos_cultivo(serie, c, agua_util_mm, b)
        cultivos[cod] = {}
        for k in ("prob_seca", "prob_helada_agro", "prob_calor"):
            if ra.get(k) is None:
                continue
            pa = ra.get(k)
            pb = rb.get(k)
            ka, na = ra.get("cuentas", {}).get(k, (None, None))
            kb, nb = rb.get("cuentas", {}).get(k, (None, None))
            cultivos[cod][k] = {
                "antes": pa,
                "ahora": pb,
                "k_antes": ka,
                "n_antes": na,
                "k_ahora": kb,
                "n_ahora": nb,
                "cambio_claro": es_cambio_claro(pa, pb),
            }

    ult_a, ult_b = media_doy(_ultima_helada, a), media_doy(_ultima_helada, b)
    pri_a, pri_b = media_doy(_primera_helada, a), media_doy(_primera_helada, b)
    return {
        "periodo_antes": f"{a[0]}-{a[-1]}" if a else None,
        "periodo_ahora": f"{b[0]}-{b[-1]}" if b else None,
        "lluvia_anual": {"antes": round(lluvia_anual(a)) if a else None, "ahora": round(lluvia_anual(b)) if b else None},
        "dias_calor_verano": {"antes": round(dias_calor_verano(a), 1) if a else None, "ahora": round(dias_calor_verano(b), 1) if b else None},
        "ultima_helada": {"antes": _doy_a_texto(ult_a), "ahora": _doy_a_texto(ult_b),
                          "corrimiento_dias": round(ult_b - ult_a) if ult_a and ult_b else None},
        "primera_helada": {"antes": _doy_a_texto(pri_a), "ahora": _doy_a_texto(pri_b),
                           "corrimiento_dias": round(pri_b - pri_a) if pri_a and pri_b else None},
        "dias_helada_anio": {"antes": round(dias_helada(a), 1) if a else None, "ahora": round(dias_helada(b), 1) if b else None},
        "cultivos": cultivos,
    }


def zafra_actual(serie: Serie) -> dict:
    """Últimos 90 días contra el promedio de los mismos días en todos los años."""
    fin = serie.fechas[-1]
    ini = fin - dt.timedelta(days=89)
    i_ini = _indice(serie, ini)
    lluvia_90 = float(serie.lluvia[i_ini:].sum())
    normales = []
    for y in sorted(set(serie.anio.tolist()))[:-1]:
        try:
            a, b = dt.date(y, ini.month, ini.day), dt.date(y, fin.month, fin.day)
        except ValueError:
            continue
        if b < a:
            b = dt.date(y + 1, fin.month, fin.day)
        ia, ib = _indice(serie, a), _indice(serie, b)
        if ia is not None and ib is not None:
            normales.append(float(serie.lluvia[ia : ib + 1].sum()))
    normal = float(np.mean(normales)) if normales else None
    gw_ahora = float(serie.gwet[-15:].mean())
    m = serie.mes == fin.month
    gw_normal = float(serie.gwet[m].mean())
    return {
        "hasta": fin.isoformat(),
        "lluvia_90d_mm": round(lluvia_90),
        "lluvia_90d_normal_mm": round(normal) if normal else None,
        "anomalia_pct": round((lluvia_90 / normal - 1) * 100) if normal else None,
        "humedad_raices_ahora": round(gw_ahora, 3),
        "humedad_raices_normal": round(gw_normal, 3),
    }


def analizar(power: dict, agua_util_mm: float = 120.0, conservar_por_anio: bool = False,
             cambio: dict | None = None) -> dict:
    """Todo el análisis climático de un punto, listo para el motor de rotaciones y la app.

    Con `cambio`, los riesgos de cada cultivo (seca, helada, calor, pérdida de rinde)
    se calculan con los años reales ajustados al clima que proyectan los modelos para los próximos años. Lo que
    describe el pasado (climatología, tendencia, zafra actual, tormentas, erosividad) queda con los años reales."""
    serie = preparar(power)
    serie_riesgo = con_cambio_mensual(serie, cambio) if cambio else serie
    riesgos = {}
    for cod, c in CULTIVOS.items():
        if c.temporada == "barbecho":
            continue
        r = riesgos_cultivo(serie_riesgo, c, agua_util_mm)
        if not conservar_por_anio:
            r.pop("por_anio", None)
        riesgos[cod] = r
    anios = _anios_completos(serie)
    dudosa = lluvia_dudosa(serie)
    avisos_lluvia = [aviso_lluvia_dudosa(serie, d) for d in dudosa]
    return {
        "dias": len(serie.fechas),
        "dias_completados": serie.dias_completados,
        "aviso_completados": aviso_completados(serie),
        "lluvia_dudosa": dudosa,
        "avisos_lluvia": avisos_lluvia,
        "fuente": power.get("fuente"),
        "url": power.get("url"),
        "celda": {"lat": power["lat"], "lon": power["lon"], "resolucion": "≈0,5° (~50 km)"},
        "periodo": f"{anios[0]}-{anios[-1]}",
        "fuente_lluvia": serie.fuente_lluvia,
        "lluvia": power.get("lluvia"),
        "agua_util_mm": agua_util_mm,
        "elevacion_m": serie.elevacion,
        "mensual": climatologia_mensual(serie),
        "erosividad": erosividad(serie),
        "tormentas": tormentas(serie),
        "riesgos_cultivo": riesgos,
        "clima_futuro": resumen_cambio(serie, cambio) if cambio else None,
        "tendencia": tendencia(serie, agua_util_mm, ["soja", "maiz", "trigo", "soja2"]),
        "zafra_actual": zafra_actual(serie),
        "limites": [
            "NASA POWER da el clima promedio de una zona de unos 50 km: no distingue bajos, lomas ni microclimas.",
            "La helada se mide en el aire a 2 m; en bajos y a nivel del pasto suele ser 2-4 °C más fría.",
            *([f"Temperatura de NASA POWER corregida con las estaciones de INUMET más cercanas ({', '.join(serie.temp_corregida)}): "
               "POWER exagera el calor del verano en Uruguay y le faltan heladas."] if serie.temp_corregida else []),
            *(["El viento de NASA POWER en esta zona viene roto (casi cero): se usó 2 m/s, como indica la FAO."]
              if serie.viento_fijo else []),
            "Las lluvias extremas se suavizan al promediar toda esa zona: la erosividad real puede ser mayor.",
            "El balance de agua usa un perfil de suelo con agua útil fija; con el análisis de suelo se ajusta.",
            aviso_completados(serie),
            *avisos_lluvia,
        ],
    }


# Lluvia dudosa. En Uruguay no hay tres meses seguidos con menos de 5 mm cada uno: ni en la seca de
# 2022/23 (IMERG da 240 mm ese verano en Durazno). NASA POWER sí los da de 10/2022 a 7/2023 en el centro del país
# (probado con 17 puntos guardados: lo marca en los 7 del centro y en ningún otro, ni en las series de IMERG).
# Si IMERG no contesta y la lluvia queda de POWER, ese hueco inflaría la seca sin que nadie lo note.
MES_CASI_SIN_LLUVIA_MM = 5.0
MESES_SEGUIDOS_DUDOSOS = 3


def lluvia_dudosa(serie: Serie) -> list[dict]:
    """Tramos de meses completos seguidos con casi nada de lluvia, que más probablemente son una falla del dato."""
    meses: list[tuple[int, int, float, int]] = []  # (año, mes, mm, días)
    for f, mm in zip(serie.fechas, serie.lluvia):
        if meses and meses[-1][:2] == (f.year, f.month):
            a, m, t, n = meses[-1]
            meses[-1] = (a, m, t + float(mm), n + 1)
        else:
            meses.append((f.year, f.month, float(mm), 1))
    completos = [x for x in meses if x[3] == calendar.monthrange(x[0], x[1])[1]]
    tramos, tramo = [], []
    for x in completos + [None]:
        seguido = x is not None and tramo and (x[0] * 12 + x[1]) == (tramo[-1][0] * 12 + tramo[-1][1] + 1)
        if x is not None and x[2] < MES_CASI_SIN_LLUVIA_MM and (not tramo or seguido):
            tramo.append(x)
            continue
        if len(tramo) >= MESES_SEGUIDOS_DUDOSOS:
            tramos.append({"desde": f"{tramo[0][1]}/{tramo[0][0]}", "hasta": f"{tramo[-1][1]}/{tramo[-1][0]}",
                           "meses": len(tramo), "mm": round(sum(t[2] for t in tramo), 1)})
        tramo = [x] if x is not None and x[2] < MES_CASI_SIN_LLUVIA_MM else []
    return tramos


def aviso_lluvia_dudosa(serie: Serie, d: dict) -> str:
    mm = f"{d['mm']:.0f}" if d["mm"] >= 1 else "menos de 1"
    return (f"La lluvia de {serie.fuente_lluvia} casi no registra agua de {d['desde']} a {d['hasta']} ({mm} mm en "
            f"{d['meses']} meses seguidos). Es muy probable que sea una falla del dato y no una seca real: los "
            "resultados de seca que incluyen esos meses no son confiables.")


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def aviso_completados(serie: Serie) -> str:
    """Cuántos días no tenían algún dato y se completaron, dicho en una frase."""
    n, k = len(serie.fechas), serie.dias_completados
    if not k:
        return f"Los {_miles(n)} días tienen todos sus datos de la NASA: no se completó ninguno."
    return (f"{_miles(k)} de {_miles(n)} días no tenían algún dato de la NASA y se completaron con el promedio de ese "
            "mismo día en los otros años.")


# --------------------------------------------------------------------------------------------
# Escenarios: "¿y si llueve menos o hace más calor?"
# --------------------------------------------------------------------------------------------

ESCENARIO_LLUVIA = (-40.0, 30.0)  # % de cambio de la lluvia que acepta la app
ESCENARIO_TEMP = (-1.0, 4.0)  # °C de cambio de la temperatura


def con_escenario(serie: Serie, lluvia_pct: float = 0.0, temp_c: float = 0.0) -> Serie:
    """La misma serie de 35 años con la lluvia multiplicada y la temperatura corrida (método delta).

    Es la forma más simple y transparente de armar un escenario: cada día llueve un X % más o menos y
    hace Y °C más o menos que lo que pasó de verdad. La humedad relativa queda igual, así que con más
    calor el aire pide más agua, y la ET0 se recalcula con FAO-56. No cambia cuántos días llueve ni la
    duración de las secas: eso lo dice la app como límite.
    """
    f = 1 + lluvia_pct / 100
    tmax = serie.tmax + temp_c
    tmin = serie.tmin + temp_c
    et0 = et0_penman_monteith(tmax, tmin, serie.rad, serie.hr, serie.viento, serie.doy, serie.lat, serie.elevacion)
    return replace(serie, tmax=tmax, tmin=tmin, lluvia=np.clip(serie.lluvia * f, 0, None), et0=et0)


def con_cambio_mensual(serie: Serie, cambio: dict, cual: str = "media") -> Serie:
    """Los mismos 35 años reales con el cambio de clima que proyectan los modelos para cada mes (NEX-GDDP-CMIP6, ver
    `fuentes/cmip6.py`): la máxima y la mínima corridas lo que cambian en ese mes, la lluvia multiplicada por su
    cociente, y la ET0 recalculada (FAO-56). Es el método delta de `con_escenario`, pero con los números de los modelos
    mes por mes en vez de un cambio parejo inventado. """
    i = serie.mes - 1
    tmax = serie.tmax + np.array(cambio["tasmax"][cual], dtype=float)[i]
    tmin = serie.tmin + np.array(cambio["tasmin"][cual], dtype=float)[i]
    lluvia = np.clip(serie.lluvia * np.array(cambio["pr"][cual], dtype=float)[i], 0, None)
    et0 = et0_penman_monteith(tmax, tmin, serie.rad, serie.hr, serie.viento, serie.doy, serie.lat, serie.elevacion)
    return replace(serie, tmax=tmax, tmin=tmin, lluvia=lluvia, et0=et0)


def resumen_cambio(serie: Serie, cambio: dict) -> dict:
    """Lo que se le dice al productor: cuánto más calor y cuánta más o menos lluvia en el año (la lluvia, pesada por
    lo que llueve de verdad en cada mes), y el rango entre modelos."""
    anios = _anios_completos(serie)
    sel = np.isin(serie.anio, anios)
    por_mes = np.array([serie.lluvia[sel & (serie.mes == m)].sum() for m in range(1, 13)])
    peso = por_mes / por_mes.sum() if por_mes.sum() > 0 else np.full(12, 1 / 12)

    def lluvia_pct(cual):
        return round(100 * (float(np.dot(peso, np.array(cambio["pr"][cual], dtype=float))) - 1), 1)

    meta = cambio.get("meta") or {}
    an = cambio.get("anual")
    return {
        "fuente": meta.get("fuente"), "escenario": meta.get("escenario"), "base": meta.get("base"),
        "futuro": meta.get("futuro"), "modelos": len(meta.get("modelos") or []), "celda": cambio.get("celda"),
        # con la máxima y la mínima, que son las que usa el balance: la media (tas) de TaiESM1 viene rota en NEX-GDDP
        # (+3,3 °C en Durazno, con la máxima y la mínima +1)
        "temp_c": round(float(np.mean((np.array(cambio["tasmax"]["media"]) + np.array(cambio["tasmin"]["media"])) / 2)), 1),
        "lluvia_pct": lluvia_pct("media"),
        # entre modelos, con el cambio anual de cada uno (fuentes/cmip6.py)
        "lluvia_pct_rango": ([round(100 * (an["pr_p10"] - 1), 1), round(100 * (an["pr_p90"] - 1), 1)] if an
                             else [lluvia_pct("p10"), lluvia_pct("p90")]),
        "temp_c_rango": [an["t_p10"], an["t_p90"]] if an else None,
        "periodo_real": f"{anios[0]}-{anios[-1]}" if anios else None,
    }


def escenario(power: dict, agua_util_mm: float, lluvia_pct: float, temp_c: float,
              cultivos: list[str] | None = None) -> dict:
    """Riesgos de cada cultivo con el clima real y con el escenario, sobre los mismos años."""
    lluvia_pct = float(np.clip(lluvia_pct, *ESCENARIO_LLUVIA))
    temp_c = float(np.clip(temp_c, *ESCENARIO_TEMP))
    base = preparar(power)
    esc = con_escenario(base, lluvia_pct, temp_c)
    anios = _anios_completos(base)
    codigos = [c for c in (cultivos or CULTIVOS) if c in CULTIVOS and CULTIVOS[c].temporada != "barbecho"]
    claves = ("prob_seca", "prob_helada_agro", "prob_calor")
    filas = []
    for cod in codigos:
        c = CULTIVOS[cod]
        hoy = riesgos_cultivo(base, c, agua_util_mm, anios)
        con = riesgos_cultivo(esc, c, agua_util_mm, anios)
        filas.append({"cultivo": cod, "nombre": c.nombre,
                      "hoy": {k: hoy.get(k) for k in claves}, "escenario": {k: con.get(k) for k in claves}})
    sel = np.isin(base.anio, anios)
    n = max(len(anios), 1)
    return {
        "lluvia_pct": lluvia_pct,
        "temp_c": temp_c,
        "periodo": f"{anios[0]}-{anios[-1]}" if anios else None,
        "lluvia_anual_mm": {"hoy": round(float(base.lluvia[sel].sum()) / n), "escenario": round(float(esc.lluvia[sel].sum()) / n)},
        "et0_anual_mm": {"hoy": round(float(base.et0[sel].sum()) / n), "escenario": round(float(esc.et0[sel].sum()) / n)},
        "cultivos": filas,
        "metodo": f"Método delta: la lluvia diaria de {base.fuente_lluvia} multiplicada y la temperatura corrida, con la ET0 "
                  "recalculada (FAO-56) y el mismo balance de agua de cada cultivo.",
        "limites": [
            "Cambia cuánto llueve, no cuántos días llueve ni cuánto duran las secas.",
            "La humedad relativa, el viento y la radiación quedan como fueron.",
            "No es un pronóstico: es lo que habría pasado en estos mismos años con ese cambio.",
        ],
    }


def serie_diaria(power: dict) -> Serie:
    return preparar(power)
