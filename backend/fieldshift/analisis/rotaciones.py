"""Motor de rotaciones: evalúa cada rotación candidata en una sección del campo.

Para cada rotación calcula, con números que salen de herramientas (no de la IA):
- Erosión con la ecuación que exige el MGAP en los Planes de Uso: A = R × K × LS × C × P,
  contra la tolerancia T del suelo. R: oficial del MGAP (o estimado con NASA POWER); K, T y
  pendiente: MGAP; C: cobertura simulada día a día y ponderada por el reparto mensual de la
  lluvia erosiva de NASA POWER.
- Agua, helada y calor: probabilidades de NASA POWER en la ventana crítica de cada cultivo.
- Ingreso: márgenes del productor si los dio; si no, un índice relativo (se dice).
- Forraje, carbono del suelo (índice cualitativo), simplicidad y diversificación.
Después pondera con las prioridades del productor y escribe las 5 filas que pide el desafío:
por qué, evidencia, beneficios, huecos de información y riesgos.
"""

from __future__ import annotations

import functools
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .clima import es_cambio_claro
from .cultivos import CULTIVOS, Cultivo, inicio_anio_agricola

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
# El año de la rotación arranca con la siembra de otoño: marzo en Uruguay, septiembre en el hemisferio norte. Es `cultivos.inicio_anio_agricola`; esta constante queda como el valor de Uruguay.
INICIO_ANIO_AGRICOLA = 3


@dataclass(frozen=True)
class Rotacion:
    id: str
    nombre: str
    descripcion: str
    anios: tuple[tuple[str, str], ...]  # (invierno, verano) por año
    tipo: str  # "agrícola" | "agrícola-ganadera" | "ganadera"

    @property
    def cultivos(self) -> list[str]:
        return [c for par in self.anios for c in par]


R = Rotacion
ROTACIONES: dict[str, Rotacion] = {
    r.id: r
    for r in [
        R("soja_continua", "Soja continua con barbecho de invierno",
          "La rotación más común en la agricultura uruguaya reciente: soja todos los veranos y el "
          "suelo sin cultivo en otoño-invierno.", (("barbecho", "soja"),), "agrícola"),
        R("soja_cobertura", "Soja con cultivo de cobertura",
          "Igual que la soja continua, pero con avena negra o raigrás en invierno para cubrir el suelo.",
          (("cobertura", "soja"),), "agrícola"),
        R("trigo_soja_maiz", "Trigo / soja de segunda → maíz",
          "Dos cultivos en el primer año y maíz con cobertura previa en el segundo: más rastrojo y "
          "dos fuentes de ingreso.", (("trigo", "soja2"), ("cobertura", "maiz")), "agrícola"),
        R("colza_trigo_maiz", "Colza / soja 2ª → trigo / soja 2ª → maíz",
          "Rotación intensiva y diversa de tres años: tres cultivos de invierno distintos para cortar "
          "malezas y enfermedades.", (("colza", "soja2"), ("trigo", "soja2"), ("cobertura", "maiz")), "agrícola"),
        R("maiz_soja_cobertura", "Maíz → soja, siempre con cobertura",
          "Alterna gramínea y leguminosa de verano y nunca deja el suelo desnudo en invierno.",
          (("cobertura", "maiz"), ("cobertura", "soja")), "agrícola"),
        R("girasol_trigo_soja", "Girasol → trigo / soja 2ª",
          "Suma un cultivo de raíz profunda y fecha temprana, que libera el campo en febrero.",
          (("cobertura", "girasol"), ("trigo", "soja2")), "agrícola"),
        R("agricola_pastoril", "Agrícola-pastoril: 2 años de cultivos + 3 de pradera",
          "El sistema clásico de Uruguay (La Estanzuela): cultivos de grano y luego una pradera de "
          "festuca, trébol y lotus que recupera el suelo.",
          (("cobertura", "soja"), ("trigo", "soja2"), ("pradera", "pradera"), ("pradera", "pradera"),
           ("pradera", "pradera")), "agrícola-ganadera"),
        R("verdeo_sorgo", "Verdeo de invierno → sorgo forrajero",
          "Para campos con ganado: forraje en invierno y en verano, con poco suelo descubierto.",
          (("verdeo", "sorgo_forrajero"),), "ganadera"),
        R("pradera_permanente", "Pradera permanente (renovación cada 4 años)",
          "Para suelos frágiles, con pendiente o muy erosionados: cobertura todo el año y ganadería.",
          (("pradera", "pradera"), ("pradera", "pradera"), ("pradera", "pradera"), ("pradera", "pradera")),
          "ganadera"),
        R("alfalfa_maiz", "Alfalfa 3 años → maíz → trigo / soja 2ª",
          "Forraje de alta calidad y nitrógeno para el maíz que sigue. Pide pH 6 o más y buen drenaje.",
          (("alfalfa", "alfalfa"), ("alfalfa", "alfalfa"), ("alfalfa", "alfalfa"), ("cobertura", "maiz"),
           ("trigo", "soja2")), "agrícola-ganadera"),
        R("campo_natural", "Campo natural con manejo del pastoreo",
          "Mantener o recuperar el campo natural, ajustando la carga.", (("campo_natural", "campo_natural"),),
          "ganadera"),
        # Rotaciones de clima templado-frío sin soja (Europa, sur de Chile), para campos fuera de Uruguay
        R("trigo_colza_cebada", "Trigo → colza → cebada",
          "Tres cultivos de invierno distintos, un año cada uno, para cortar malezas y enfermedades; el suelo queda "
          "con rastrojo en verano. Es la rotación típica de los climas de verano corto.",
          (("trigo", "barbecho"), ("colza", "barbecho"), ("cebada", "barbecho")), "agrícola"),
        R("maiz_trigo_cobertura", "Maíz → trigo, con cobertura",
          "Alterna un cultivo de verano y uno de invierno, con cobertura antes del maíz: más rastrojo y menos "
          "suelo desnudo, sin soja.",
          (("cobertura", "maiz"), ("trigo", "barbecho")), "agrícola"),
    ]
}

# las que se ofrecen solo fuera de Uruguay: en Uruguay quedan las de siempre, para no mover sus resultados
SOLO_FUERA_DE_URUGUAY = {"trigo_colza_cebada", "maiz_trigo_cobertura"}


# --------------------------------------------------------------------------------------------
# Cobertura del suelo día a día → factor C
# --------------------------------------------------------------------------------------------


def _offset(c: Cultivo) -> int:
    """Días desde el inicio del año agrícola (1 de marzo en el sur, 1 de septiembre en el norte) hasta la siembra."""
    mes, dia = c.siembra
    dias_mes = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    d, m = 0, inicio_anio_agricola()
    while m != mes:
        d += dias_mes[m - 1]
        m = m % 12 + 1
    return d + dia - 1


def _canopia(c: Cultivo, k: int) -> float:
    ini, des, med, fin = c.etapas
    if c.temporada == "perenne":
        return 0.3 + 0.65 * min(1.0, k / 60)
    if k < ini:
        return 0.05 + 0.2 * k / max(ini, 1)
    k -= ini
    if k < des:
        return 0.25 + 0.65 * k / max(des, 1)
    k -= des
    if k < med:
        return 0.9
    k -= med
    return 0.9 - 0.3 * k / max(fin, 1)


def tope_rastrojo(cultivo: str, previo: str | None, antes: str | None) -> float | None:
    """Máximo de suelo cubierto por rastrojo a la siembra que acepta el modelo oficial del MGAP según lo
    que había antes (Cuadro 1 de "Actualización técnica del Modelo de Estimación de Pérdida de Suelo por
    Erosión Hídrica...", García Préchac et al., MGAP-DGRN). "barbecho" = barbecho químico."""
    soja, maiz = {"soja", "soja2"}, {"maiz", "maiz2", "sorgo"}
    if cultivo in soja:
        if previo in ("trigo", "cebada", "cobertura"):
            return 0.70
        if previo == "colza":
            return 0.40
        if previo == "barbecho":
            return 0.50 if antes in maiz else 0.40 if antes in soja else None
    if cultivo in ("colza", "trigo", "cebada", "cobertura") and previo in soja:
        return 0.80
    if cultivo in maiz and previo == "barbecho" and antes in soja:
        return 0.80
    return None


def simular_cobertura_y_rastrojo(rot: Rotacion, ciclos: int = 2) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Simula canopia, rastrojo en descomposición y cobertura total día a día sobre la rotación.

    Devuelve (cobertura_total, canopia, rastrojo) para `ciclos` repeticiones completas de la rotación.
    """
    n = len(rot.anios)
    largo = 365 * n * ciclos
    canopia = np.zeros(largo + 400)
    cosechas: list[tuple[int, float]] = []
    # topes oficiales de rastrojo a la siembra, según los dos componentes anteriores de la secuencia
    secuencia = [c for _ in range(ciclos) for par in rot.anios for c in (par[:1] if par[0] == par[1] else par)]
    topes: dict[int, float] = {}
    pos = 0
    for v in range(ciclos):
        for i, (inv, ver) in enumerate(rot.anios):
            base = 365 * (v * n + i)
            if inv == ver and CULTIVOS[inv].temporada == "perenne":
                c = CULTIVOS[inv]
                previo = rot.anios[i - 1][0] if i > 0 or v > 0 else None
                ya_establecida = previo == inv and (i > 0 or v > 0)
                for k in range(365):
                    val = 0.95 if ya_establecida else _canopia(c, k)
                    canopia[base + k] = max(canopia[base + k], val)
                pos += 1
                continue
            for cod in (inv, ver):
                c = CULTIVOS[cod]
                previo = secuencia[pos - 1] if pos >= 1 else None
                antes = secuencia[pos - 2] if pos >= 2 else None
                pos += 1
                if c.temporada == "barbecho":
                    continue
                s = base + _offset(c)
                tope = tope_rastrojo(cod, previo, antes)
                if tope is not None and s < largo:
                    topes[s] = tope
                for k in range(c.ciclo):
                    canopia[s + k] = max(canopia[s + k], _canopia(c, k))
                cosechas.append((s + c.ciclo, c.rastrojo))
    canopia = canopia[:largo]
    rastrojo = np.zeros(largo)
    cos = dict()
    for d, r in cosechas:
        if d < largo:
            cos[d] = max(cos.get(d, 0), r)
    actual = 0.3
    for d in range(largo):
        if d in cos:
            actual = max(actual, cos[d])
        if d in topes:
            actual = min(actual, topes[d])
        actual *= 0.9975  # el rastrojo se degrada ~7 % por mes
        rastrojo[d] = actual
    cobertura = np.clip(canopia + rastrojo * (1 - canopia), 0, 1)
    return cobertura, canopia, rastrojo


def cobertura_diaria(rot: Rotacion, ciclos: int = 2) -> np.ndarray:
    return simular_cobertura_y_rastrojo(rot, ciclos)[0]


def factor_c_diario(cobertura: np.ndarray) -> np.ndarray:
    """Subfactor de cobertura de RUSLE, forma exponencial: C = 0,45·e^(−4·cobertura).

    Curva de respaldo histórica de Field Shift para siembra directa. El cálculo principal de la app
    ahora usa el método y las tablas oficiales del programa Erosión 6.0 del MGAP (Facultad de
    Agronomía, UdelaR), con relaciones de pérdida de suelo por período y efecto residual de pasturas
    (`factor_c_oficial`).
    """
    return 0.45 * np.exp(-4.0 * cobertura)


def _escalon_hacia_abajo(valor: float, escalones: list[int | float]) -> int | float:
    """Redondea hacia el escalón más cercano de la tabla hacia abajo (lo conservador)."""
    menores = [e for e in escalones if e <= valor]
    if menores:
        return max(menores)
    return min(escalones)


@functools.lru_cache(maxsize=1)
def _tablas_erosion6() -> dict:
    ruta = Path(__file__).resolve().parent.parent / "datos" / "rps_erosion6.json"
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def factor_c_oficial(rot: Rotacion, ctx: dict) -> tuple[float, np.ndarray, list[str]]:
    """Calcula el factor C con el método y las tablas oficiales de Erosión 6.0 (MGAP - UdelaR).

    Divide cada cultivo en períodos:
      1: siembra a 30 días
      2: establecimiento (día 30 a 60)
      3: crecimiento hasta cosecha
      4: rastrojo desde cosecha hasta la próxima siembra
    Busca la RPS (relación de pérdida de suelo) por cultivo y nivel de residuo a la siembra. En el período 4,
    soja, maíz y sorgo tienen su propia escala (el rastrojo que deja el cultivo); cereales de invierno, girasol,
    cobertura y verdeo no: en Erosión 6.0 su fila del período 4 va por el mismo residuo a la siembra. Multiplica por el ERP (efecto residual de pasturas) si viene de pastura, y pondera
    por el reparto de erosividad diario de NASA POWER a lo largo del año agrícola (marzo a febrero).

    Devuelve:
      - c_anual: factor C promedio anual ponderado del ciclo estabilizado (segundo ciclo).
      - c_m: promedio mensual del factor C por mes calendario (enero..diciembre, shape (12,)).
      - aproximaciones: lista de códigos de cultivos evaluados con aproximación propia.
    """
    n = len(rot.anios)

    # Erosividad diaria a lo largo del año agrícola (marzo a febrero; en el hemisferio norte, septiembre a agosto)
    # ctx["reparto_erosivo"] viene en meses calendario (enero..diciembre)
    reparto = np.array(ctx["reparto_erosivo"])
    inicio = inicio_anio_agricola()
    meses_agr = [(inicio - 1 + i) % 12 + 1 for i in range(12)]
    dias_mes_agr = [[31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1] for m in meses_agr]
    e_diario = np.zeros(365)
    idx = 0
    for mc, dm in zip(meses_agr, dias_mes_agr):
        e_diario[idx : idx + dm] = reparto[mc - 1] / dm
        idx += dm

    c_diario, aproximaciones = c_diario_oficial(rot)
    inicio_c2 = 365 * n
    fin_c2 = 365 * n * 2
    c_c2 = c_diario[inicio_c2:fin_c2]

    c_anual = sum(c_c2[d] * e_diario[d % 365] for d in range(365 * n)) / n
    c_m = _mensual(c_c2, n)
    return float(c_anual), c_m, aproximaciones


def c_diario_oficial(rot: Rotacion) -> tuple[np.ndarray, list[str]]:
    """Factor C de cada día, sobre dos ciclos de la rotación (el segundo es el estabilizado), con las tablas de
    Erosión 6.0, y los cultivos que se evaluaron con una aproximación propia. Ver `factor_c_oficial`."""
    tablas = _tablas_erosion6()
    rps_data = tablas["rps"]
    erp_data = tablas.get("erp", {})

    n = len(rot.anios)
    ciclos = 2
    largo = 365 * n * ciclos

    _, _, rastrojo = simular_cobertura_y_rastrojo(rot, ciclos=ciclos)

    # Armamos la lista cronológica de eventos de siembra/cultivo sobre los 2 ciclos
    eventos: list[tuple[int, int, str, int, bool, bool]] = []
    # cada evento: (s_dia, h_dia, cod, pos_pastura, es_perenne, es_siembra_pastura)
    ultimo_fue_pastura = False
    contador_post_pastura = 999

    for v in range(ciclos):
        for i, (inv, ver) in enumerate(rot.anios):
            base = 365 * (v * n + i)
            if inv == ver and CULTIVOS[inv].temporada == "perenne":
                if inv == "campo_natural":
                    eventos.append((base, base + 365, inv, 0, True, False))
                else:
                    prev_par = rot.anios[(i - 1) % n]
                    prev_es_pastura = (prev_par[0] == prev_par[1] and CULTIVOS[prev_par[0]].temporada == "perenne")
                    es_siembra = not prev_es_pastura or (rot.id == "pradera_permanente" and i == 0)
                    s_past = (base + _offset(CULTIVOS[inv])) if es_siembra else base
                    eventos.append((s_past, base + 365, inv, 0, True, es_siembra))
                ultimo_fue_pastura = True
                contador_post_pastura = 0
                continue

            # Invierno
            if inv != "barbecho":
                if ultimo_fue_pastura:
                    contador_post_pastura = 1
                elif contador_post_pastura < 999:
                    contador_post_pastura += 1
                ultimo_fue_pastura = False
                c_inv = CULTIVOS[inv]
                s_inv = base + _offset(c_inv)
                h_inv = s_inv + c_inv.ciclo
                eventos.append((s_inv, h_inv, inv, contador_post_pastura, False, False))

            # Verano
            if ver != "barbecho":
                if ultimo_fue_pastura:
                    contador_post_pastura = 1
                elif contador_post_pastura < 999:
                    contador_post_pastura += 1
                ultimo_fue_pastura = False
                c_ver = CULTIVOS[ver]
                s_ver = base + _offset(c_ver)
                h_ver = s_ver + c_ver.ciclo
                eventos.append((s_ver, h_ver, ver, contador_post_pastura, False, False))

    c_diario = np.zeros(largo)
    aproximaciones: set[str] = set()

    for idx_ev, ev in enumerate(eventos):
        s, h, cod, pos_past, es_perenne, es_siembra_past = ev
        s_next = eventos[idx_ev + 1][0] if idx_ev + 1 < len(eventos) else largo
        c_obj = CULTIVOS[cod]

        if es_perenne:
            if cod == "campo_natural":
                val_cn = float(tablas.get("precalculados", {}).get("campo_natural", 0.02))
                c_diario[s : min(h, largo)] = val_cn
            else:
                if es_siembra_past:
                    past_data = rps_data["pastura_no_consociada"]
                    pasos = past_data["pasos_residuo"]
                    res_pct = rastrojo[s] * 100 if s < largo else 85
                    step = str(_escalon_hacia_abajo(res_pct, pasos))
                    p1_end = min(s + 30, h)
                    p2_end = min(s + 60, h)
                    c_diario[s:p1_end] = float(past_data["p1"].get(step, 0.06))
                    if p2_end > p1_end:
                        c_diario[p1_end:p2_end] = float(past_data["p2"].get(step, 0.06))
                    if h > p2_end:
                        c_diario[p2_end:h] = float(past_data["p3"].get(step, 0.06))
                else:
                    c_diario[s : min(h, largo)] = float(rps_data["pastura_establecida"])
            # Entre el fin de la pastura y la siembra siguiente (un mes al romperla, mes y medio al
            # renovarla) esos días quedaban con C = 0, o sea sin erosión. En siembra directa la pastura se quema y se
            # siembra encima, y Erosión 6.0 no tiene un período aparte para eso: la pastura vieja sigue cubriendo.
            if s_next > h and h > s:
                c_diario[h : min(s_next, largo)] = c_diario[min(h, largo) - 1]
            continue

        res_siembra = rastrojo[s] * 100 if s < largo else 30
        rastrojo_p4 = c_obj.rastrojo * 100

        if cod in ("soja", "soja2"):
            t_crop = rps_data["soja"]
            s_s = str(_escalon_hacia_abajo(res_siembra, t_crop["pasos_residuo_siembra"]))
            s_4 = str(_escalon_hacia_abajo(rastrojo_p4, t_crop["pasos_rastrojo_p4"]))
            rps = {
                1: float(t_crop["p1"][s_s]),
                2: float(t_crop["p2"][s_s]),
                3: float(t_crop["p3"][s_s]),
                4: float(t_crop["p4"][s_4]),
            }
        elif cod in ("maiz", "maiz2", "sorgo", "sorgo_forrajero"):
            t_crop = rps_data["sorgo_o_maiz"]
            s_s = str(_escalon_hacia_abajo(res_siembra, t_crop["pasos_residuo_siembra"]))
            s_4 = str(_escalon_hacia_abajo(rastrojo_p4, t_crop["pasos_rastrojo_p4"]))
            rps = {
                1: float(t_crop["p1"][s_s]),
                2: float(t_crop["p2"][s_s]),
                3: float(t_crop["p3"][s_s]),
                4: float(t_crop["p4"][s_4]),
            }
        elif cod in ("trigo", "cebada"):
            t_crop = rps_data["cereales_invierno"]
            s_s = str(_escalon_hacia_abajo(res_siembra, t_crop["pasos_residuo"]))
            s_4 = s_s  # la tabla de este cultivo va por el rastrojo a la siembra también en el período 4
            rps = {
                1: float(t_crop["p1"][s_s]),
                2: float(t_crop["p2"][s_s]),
                3: float(t_crop["p3"][s_s]),
                4: float(t_crop["p4"][s_4]),
            }
        elif cod == "girasol":
            t_crop = rps_data["girasol"]
            s_s = str(_escalon_hacia_abajo(res_siembra, t_crop["pasos_residuo"]))
            s_4 = s_s  # la tabla de este cultivo va por el rastrojo a la siembra también en el período 4
            rps = {
                1: float(t_crop["p1"][s_s]),
                2: float(t_crop["p2"][s_s]),
                3: float(t_crop["p3"][s_s]),
                4: float(t_crop["p4"][s_4]),
            }
        elif cod == "colza":
            c_colza = rps_data["colza"]["periodos"]
            rps = {
                1: float(c_colza["p1"]),
                2: float(c_colza["p2"]),
                3: float(c_colza["p3"]),
                4: float(c_colza["p4"]),
            }
        elif cod in ("cobertura", "verdeo"):
            aproximaciones.add(cod)
            t_crop = rps_data["cereales_invierno"]
            s_s = str(_escalon_hacia_abajo(res_siembra, t_crop["pasos_residuo"]))
            s_4 = s_s  # la tabla de este cultivo va por el rastrojo a la siembra también en el período 4
            rps = {
                1: float(t_crop["p1"][s_s]),
                2: float(t_crop["p2"][s_s]),
                3: float(t_crop["p3"][s_s]),
                4: float(t_crop["p4"][s_4]),
            }
        else:
            aproximaciones.add(cod)
            rps = {1: 0.15, 2: 0.15, 3: 0.15, 4: 0.20}

        def _get_erp(p: int) -> float:
            if pos_past in (1, 2):
                return float(erp_data.get(str(pos_past), {}).get(str(p), 1.0))
            return 1.0

        p1_end = min(s + 30, h)
        p2_end = min(s + 60, h)
        c_diario[s:p1_end] = rps[1] * _get_erp(1)
        if p2_end > p1_end:
            c_diario[p1_end:p2_end] = rps[2] * _get_erp(2)
        if h > p2_end:
            c_diario[p2_end:h] = rps[3] * _get_erp(3)
        if s_next > h:
            c_diario[h : min(s_next, largo)] = rps[4] * _get_erp(4)

    return c_diario, sorted(aproximaciones)


def _mensual(diario: np.ndarray, n_anios: int) -> np.ndarray:
    """Promedio por mes calendario (ene..dic) del último ciclo."""
    ultimo = diario[-365 * n_anios :]
    inicio = inicio_anio_agricola()  # el día 0 de la simulación es el inicio del año agrícola
    meses_cal = [(inicio - 1 + i) % 12 + 1 for i in range(12)]
    dias_mes = [[31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1] for m in meses_cal]
    suma = np.zeros(12)
    cuenta = np.zeros(12)
    for a in range(n_anios):
        d = 365 * a
        for mc, dm in zip(meses_cal, dias_mes):
            suma[mc - 1] += ultimo[d : d + dm].sum()
            cuenta[mc - 1] += dm
            d += dm
    return suma / cuenta


def p_curvas(pendiente_pct: float | None) -> float:
    """Factor P de la USLE por sembrar en curvas de nivel, según la pendiente (Wischmeier y Smith, 1978, tabla de
    cultivo en contorno): rinde más entre 3 y 8 %, y casi nada en pendientes fuertes. Antes se usaba 0,6 fijo."""
    p = 3.0 if pendiente_pct is None else float(pendiente_pct)
    for hasta, fac in ((2, 0.6), (8, 0.5), (12, 0.6), (16, 0.7), (20, 0.8), (25, 0.9)):
        if p <= hasta:
            return fac
    return 1.0


def factor_ls(pendiente_pct: float, largo_m: float = 100.0) -> float:
    """Wischmeier y Smith (1978)."""
    s = max(pendiente_pct, 0.1)
    m = 0.5 if s >= 5 else 0.4 if s >= 3.5 else 0.3 if s >= 1 else 0.2
    th = math.atan(s / 100)
    return (largo_m / 22.13) ** m * (65.41 * math.sin(th) ** 2 + 4.56 * math.sin(th) + 0.065)


# --------------------------------------------------------------------------------------------
# Evaluación
# --------------------------------------------------------------------------------------------

# precio de la soja si el productor no lo da: proyección de INIA para la zafra 2025/26 (USD 350-380/t,
# Revista INIA n.º 83, dic-2025); solo se usa para pasar la renta en kilos a dólares
PRECIO_SOJA_REFERENCIA = 365.0

DIMENSIONES = ["suelo", "agua", "clima", "ingreso", "forraje", "simplicidad", "diversificacion"]
NOMBRE_DIM = {
    "suelo": "Suelo (erosión y carbono)",
    "agua": "Agua (seca en floración)",
    "clima": "Helada y calor",
    "ingreso": "Ingreso",
    "forraje": "Forraje",
    "simplicidad": "Simplicidad",
    "diversificacion": "Diversificación",
}


def _clip(x: float, a: float = 0, b: float = 100) -> float:
    return max(a, min(b, x))


# Escalas de 0 a 100. En una suma ponderada el peso vale lo que vale pasar del 0
# al 100 de cada criterio, así que el 0 y el 100 tienen que ser lo peor y lo mejor que se ve de verdad en Uruguay; si
# el 0 queda donde no llega nadie, el criterio pesa menos que lo que pidió el productor. Extremos medidos con las 22
# rotaciones en 14 puntos del país (de Rivera a la costa, Colonia a Cerro Largo; agua útil 84 y 120 mm):
# - seca en floración: de 3 a 66 años de cada 100 (9 de cada 10 casos entre 11 y 53) → 5 = 100, 50 = 0;
# - helada + calor en floración: 0 a 109 de cada 100 → ahora 100·(1 − h − c); antes 0,6·(h + c), con el 0 en 167;
# - ingreso relativo con riesgo: 0,30 a 1,05 → 0,2 = 0, 1,0 = 100 (antes 0 = no ganar nada, que no da ninguna);
# - índice de carbono: 0,18 a 1,0 → 0,15 = 0, 0,85 = 100.
# Con márgenes del productor el ingreso sigue en dólares (0 = no ganar nada), que sí puede pasar.
SECA_MEJOR, SECA_PEOR = 0.05, 0.50
INGRESO_REL_PEOR, INGRESO_REL_MEJOR = 0.2, 1.0
CARBONO_PEOR, CARBONO_MEJOR = 0.15, 0.85


def _escala(x: float, peor: float, mejor: float) -> float:
    """x pasado a 0-100 entre lo peor (0) y lo mejor (100) que se ve en Uruguay; sirve en los dos sentidos."""
    return _clip(100 * (x - peor) / (mejor - peor))


def evaluar(rot: Rotacion, ctx: dict) -> dict:
    """ctx: suelo, r_factor, erosividad (reparto), riesgos (por cultivo), problemas, margenes,
    largo_pendiente_m, practica_p, ndvi, analisis_suelo, ganado."""
    n = len(rot.anios)
    suelo = ctx.get("suelo") or {}
    k = suelo.get("factor_k") or 0.33
    t = suelo.get("tolerancia_t") or 7.0
    pend = suelo.get("pendiente_pct")
    if pend is None:
        pend = ctx.get("pendiente_srtm")  # fuera de Uruguay no hay pendiente del MGAP: la de SRTM del lote
    pend = 3.0 if pend is None else pend
    # El largo de ladera sale del relieve (SRTM) de cada lote; antes, 100 m fijos (ver analisis/relieve.py)
    largo = ctx.get("largo_pendiente_m") or 100
    ls = factor_ls(pend, largo)
    p_fac = ctx.get("practica_p") or 1.0
    r = ctx["r_factor"]
    reparto = np.array(ctx["reparto_erosivo"])

    cob_d = cobertura_diaria(rot)
    cob_m = _mensual(cob_d, n)
    c_anual, c_m, aprox_c = factor_c_oficial(rot, ctx)
    a = r * k * ls * c_anual * p_fac
    meses_descubierto = [MESES[i] for i in range(12) if cob_m[i] < 0.5]
    peligro = [MESES[i] for i in range(12) if cob_m[i] < 0.5 and reparto[i] >= 1 / 12]

    riesgos = ctx["riesgos"]
    problemas = set(ctx.get("problemas") or [])
    ajuste_helada = 0.15 if "helada" in problemas else 0.0

    cultivos_eval = [c for c in rot.cultivos if CULTIVOS[c].temporada != "barbecho"]
    secas, heladas, calores, deficits = [], [], [], []
    perdidas_media, perdidas_seco, caidas = [], [], []
    detalle_riesgo = []
    for cod in dict.fromkeys(cultivos_eval):
        rc = riesgos.get(cod) or {}
        c = CULTIVOS[cod]
        peso = 1.0 if c.ky > 0 else 0.5
        fila = {"cultivo": cod, "nombre": c.nombre}
        if rc.get("prob_seca") is not None:
            secas.append((rc["prob_seca"], peso))
            deficits.append(rc.get("deficit_medio") or 0)
            fila["prob_seca"] = rc["prob_seca"]
            fila["ventana_agua"] = rc.get("ventana_agua")
        if rc.get("perdida_anio_seco") is not None:
            perdidas_media.append(rc["perdida_media"])
            perdidas_seco.append(rc["perdida_anio_seco"])
            fila["perdida_media"] = rc["perdida_media"]
            fila["perdida_anio_seco"] = rc["perdida_anio_seco"]
            if rc.get("caida_anio_seco") is not None:
                caidas.append(rc["caida_anio_seco"])
                fila["caida_anio_seco"] = rc["caida_anio_seco"]
        if rc.get("prob_helada_agro") is not None:
            ph = min(1.0, rc["prob_helada_agro"] + ajuste_helada)
            heladas.append(ph)
            fila["prob_helada"] = round(ph, 3)
            fila["ventana_helada"] = rc.get("ventana_helada")
        if rc.get("prob_calor") is not None:
            calores.append(rc["prob_calor"])
            fila["prob_calor"] = rc["prob_calor"]
            fila["ventana_calor"] = rc.get("ventana_calor")
        detalle_riesgo.append(fila)
    seca = sum(p * w for p, w in secas) / sum(w for _, w in secas) if secas else 0.0
    helada = float(np.mean(heladas)) if heladas else 0.0
    calor = float(np.mean(calores)) if calores else 0.0

    # ingreso: por año; una perenne que ocupa invierno y verano cuenta una sola vez
    por_anio_ingreso = []
    for inv, ver in rot.anios:
        if inv == ver and CULTIVOS[inv].temporada == "perenne":
            por_anio_ingreso.append([inv])
        else:
            por_anio_ingreso.append([c for c in (inv, ver) if CULTIVOS[c].temporada != "barbecho"])
    cultivos_ingreso = [c for anio in por_anio_ingreso for c in anio]
    margenes = dict(ctx.get("margenes") or {})
    # si el productor dio márgenes pero falta alguno de esta rotación, se estima con el índice relativo
    # escalado a sus propios números: así todas las rotaciones se comparan en dólares y no en dos escalas
    estimados = []
    if margenes:
        escalas = sorted(float(margenes[c]) / CULTIVOS[c].ingreso_relativo for c in margenes
                         if c in CULTIVOS and CULTIVOS[c].ingreso_relativo >= 0.3 and float(margenes[c]) > 0)
        escala = escalas[len(escalas) // 2] if escalas else None
        for c in dict.fromkeys(cultivos_ingreso):
            if c not in margenes and CULTIVOS[c].ingreso_relativo > 0 and escala:
                margenes[c] = round(CULTIVOS[c].ingreso_relativo * escala)
                estimados.append(c)
    usa_margenes = bool(margenes) and all(c in margenes for c in cultivos_ingreso if CULTIVOS[c].ingreso_relativo > 0)
    if usa_margenes:
        ingreso_anual = sum(float(margenes.get(c, 0)) for c in cultivos_ingreso) / n
        ingreso_riesgo = sum(
            float(margenes.get(c, 0)) * (1 - 0.5 * ((riesgos.get(c) or {}).get("prob_seca") or 0))
            for c in cultivos_ingreso
        ) / n
        max_ref = max(float(v) for v in margenes.values()) * 1.6 if margenes else 1
        score_ingreso = _clip(100 * ingreso_riesgo / max_ref) if max_ref > 0 else 50
    else:
        rel = sum(CULTIVOS[c].ingreso_relativo for c in cultivos_ingreso) / n
        rel_riesgo = sum(
            CULTIVOS[c].ingreso_relativo * (1 - 0.5 * ((riesgos.get(c) or {}).get("prob_seca") or 0))
            for c in cultivos_ingreso
        ) / n
        ingreso_anual, ingreso_riesgo = None, None
        score_ingreso = _escala(rel_riesgo, INGRESO_REL_PEOR, INGRESO_REL_MEJOR)
        rel = round(rel, 2)

    # renta (kilos de soja por ha y año) y rinde de equilibrio por cultivo: los kilos que hay que
    # cosechar para pagar el costo y la parte de la renta que le toca (la mitad si comparte el año)
    detalle = ctx.get("detalle_margenes") or {}
    renta_kg = float(ctx.get("renta_kg") or 0)
    precio_soja = next((float(detalle[c]["precio"]) for c in ("soja", "soja2") if (detalle.get(c) or {}).get("precio")),
                       PRECIO_SOJA_REFERENCIA)
    renta_usd = renta_kg * precio_soja / 1000
    equilibrios = {}
    for anio in por_anio_ingreso:
        de_cosecha = [c for c in anio if CULTIVOS[c].ingreso_relativo > 0 and CULTIVOS[c].temporada != "perenne"]
        for c in de_cosecha:
            d = detalle.get(c) or {}
            if not (d.get("precio") and d.get("costo") is not None):
                continue
            parte = renta_usd / len(de_cosecha)
            kg = (float(d["costo"]) + parte) / float(d["precio"]) * 1000
            if kg > equilibrios.get(c, {}).get("kg_ha", 0):
                equilibrios[c] = {"cultivo": c, "nombre": CULTIVOS[c].nombre, "kg_ha": round(kg),
                                  "rinde_esperado": d.get("rinde")}
    ingreso_neto = (ingreso_anual - renta_usd) if (ingreso_anual is not None and renta_kg) else None

    forraje = sum(CULTIVOS[c].forraje for c in rot.cultivos) / (2 * n)
    distintos = len(set(cultivos_eval))
    por_anio = sum(1 for c in rot.cultivos if CULTIVOS[c].temporada in ("verano", "invierno")) / n
    simplicidad = _clip(100 - 14 * (distintos - 1) - 18 * max(0, por_anio - 1))
    familias = {
        "soja": "leg", "soja2": "leg", "pradera": "leg", "alfalfa": "leg", "maiz": "gram", "maiz2": "gram",
        "sorgo": "gram", "sorgo_forrajero": "gram", "trigo": "gram_inv", "cebada": "gram_inv",
        "verdeo": "gram_inv", "cobertura": "gram_inv", "colza": "cruc", "girasol": "comp",
        "campo_natural": "nat",
    }
    fams = {familias.get(c, c) for c in cultivos_eval}
    diversificacion = _clip(20 * len(fams) + 6 * distintos)

    # carbono: meses con raíces vivas + aporte de rastrojo + años de pastura
    vivos = float((_mensual(np.array([1.0 if x > 0.6 else 0.0 for x in cob_d]), n)).mean())
    aporte = sum(CULTIVOS[c].rastrojo for c in cultivos_eval) / n
    anios_pastura = sum(1 for inv, ver in rot.anios if CULTIVOS[inv].temporada == "perenne") / n
    indice_c = 0.45 * vivos + 0.25 * min(aporte / 1.4, 1) + 0.30 * anios_pastura
    tendencia_c = "sube" if indice_c >= 0.55 else "se mantiene" if indice_c >= 0.38 else "baja"

    ratio = a / t if t else 1
    score_erosion = _clip(100 - (ratio - 0.5) * 66.7)  # 0,5·T → 100; 2·T → 0
    score_suelo = 0.7 * score_erosion + 0.3 * _escala(indice_c, CARBONO_PEOR, CARBONO_MEJOR)
    score_agua = _escala(seca, SECA_PEOR, SECA_MEJOR)
    score_clima = _clip(100 * (1 - helada - calor))
    score_forraje = _clip(100 * forraje)
    puntajes = {
        "suelo": round(score_suelo), "agua": round(score_agua), "clima": round(score_clima),
        "ingreso": round(score_ingreso), "forraje": round(score_forraje),
        "simplicidad": round(simplicidad), "diversificacion": round(diversificacion),
    }

    # El Plan de Uso del MGAP se exige a los cultivos y a las pasturas sembradas con laboreo
    # (Res. 397/018), no al campo natural. Antes un lote que quedaba en campo natural salía «no pasa».
    exigible = not all(c == "campo_natural" for par in rot.anios for c in par)

    alertas = []
    if ratio > 1 and exigible:
        alertas.append(
            f"Erosión estimada {_n(a)} t/ha/año, por encima de la tolerancia del suelo ({_n(t, 0)}): "
            "con estos datos no cumpliría un Plan de Uso del MGAP."
        )
    elif ratio > 1:
        alertas.append(
            f"Erosión estimada {_n(a)} t/ha/año, algo más de lo que aguanta este suelo ({_n(t, 0)}). En campo natural "
            "el Plan de Uso no se exige, pero conviene ajustar la carga para que el campo no se pele."
        )
    analisis = ctx.get("analisis_suelo") or {}
    if "alfalfa" in rot.cultivos and analisis.get("ph") is not None and float(analisis["ph"]) < 6:
        alertas.append(f"La alfalfa pide pH 6 o más y el análisis dio {_n(float(analisis['ph']))}.")
    penalizacion = 1.0
    if "anegamiento" in problemas:
        sensibles = [CULTIVOS[c].nombre for c in set(cultivos_eval) if c in ("trigo", "cebada", "colza", "alfalfa")]
        if sensibles:
            # «Trigo sufre» / «Trigo y colza sufren»
            lista = sensibles[0] if len(sensibles) == 1 else ", ".join(sensibles[:-1]) + " y " + sensibles[-1]
            verbo = "sufre" if len(sensibles) == 1 else "sufren"
            alertas.append(f"La sección se anega: {lista} {verbo} con agua estancada en invierno.")
            penalizacion *= 0.85
    # lo demás que marca el productor (ajustes propios, a validar con un agrónomo): pesa sobre las
    # rotaciones que no atacan el problema y se explica en los riesgos
    if "compactacion" in problemas:
        if anios_pastura == 0:
            alertas.append("El productor marcó compactación: sin pradera ni alfalfa no hay raíces profundas que "
                           "la vayan aflojando; puede hacer falta descompactar.")
            penalizacion *= 0.95
        else:
            alertas.append("Para la compactación que marcó el productor: las raíces de la pastura ayudan a aflojar el "
                           "suelo, siempre que no se pastoree ni se entre con maquinaria con el suelo mojado.")
    if "malezas" in problemas and len(fams) <= 2 and anios_pastura == 0:  # la pastura ya corta el ciclo
        alertas.append("El productor marcó malezas resistentes: con tan pocas familias de cultivos se repiten los "
                       "mismos herbicidas, que es lo que las selecciona.")
        penalizacion *= 0.93
    if "erosion" in problemas and ratio > 0.7:
        # Decía «cerca de la tolerancia» también cuando la superaba (23,4 contra 2 en La Loma)
        if ratio > 1:
            alertas.append(f"El productor ve que la sección se lava: la estimación ({_n(a)} t/ha/año) puede quedarse "
                           f"corta, y esta rotación ya supera lo que aguanta el suelo ({_n(t, 0)}).")
        else:
            alertas.append(f"El productor ve que la sección se lava: la estimación ({_n(a)} t/ha/año) puede quedarse "
                           f"corta y esta rotación ya está cerca de la tolerancia ({_n(t, 0)}).")
        penalizacion *= 0.9
    if "cobertura" in rot.cultivos:
        alertas.append("En años secos, terminar la cobertura 30-45 días antes de sembrar el verano para no gastar el agua del perfil.")

    return {
        "id": rot.id,
        "nombre": rot.nombre,
        "descripcion": rot.descripcion,
        "tipo": rot.tipo,
        "anios": [list(p) for p in rot.anios],
        "erosion": {
            "a_t_ha": round(a, 2), "tolerancia_t": t, "ratio": round(ratio, 2), "cumple": ratio <= 1 or not exigible,
            "exigible": exigible,
            "r": round(r), "k": k, "ls": round(ls, 3), "c": round(c_anual, 4), "p": p_fac,
            "pendiente_pct": round(pend, 2),
            "largo_m": round(largo),
            "largo_origen": ctx.get("largo_origen") or "fijo",
            "aproximaciones": aprox_c,
        },
        "cobertura_mensual": [round(float(x), 3) for x in cob_m],
        "meses_descubierto": meses_descubierto,
        "ventana_peligro": peligro,
        "riesgo": {"seca": round(seca, 3), "helada": round(helada, 3), "calor": round(calor, 3),
                   "deficit_medio": round(float(np.mean(deficits)), 3) if deficits else None,
                   # rinde que se pierde por falta de agua (FAO-33), promedio de los cultivos de cosecha de la rotación
                   "perdida_media": round(float(np.mean(perdidas_media)), 3) if perdidas_media else None,
                   "perdida_anio_seco": round(float(np.mean(perdidas_seco)), 3) if perdidas_seco else None,
                   # cuánto menos rinde un año seco (1 de cada 5) que uno normal, promedio de sus cultivos de cosecha
                   "caida_anio_seco": round(float(np.mean(caidas)), 3) if caidas else None,
                   "por_cultivo": detalle_riesgo},
        "ingreso": {"usa_margenes": usa_margenes, "usd_ha_anio": round(ingreso_anual) if ingreso_anual else None,
                    "usd_ha_anio_con_riesgo": round(ingreso_riesgo) if ingreso_riesgo else None,
                    "indice_relativo": None if usa_margenes else rel,
                    "renta_kg": renta_kg or None, "renta_usd_ha": round(renta_usd) if renta_kg else None,
                    "precio_soja": precio_soja if renta_kg else None,
                    "usd_ha_anio_despues_de_renta": round(ingreso_neto) if ingreso_neto is not None else None,
                    "equilibrios": list(equilibrios.values()),
                    "margenes_estimados": estimados},
        "forraje": round(forraje, 2),
        "carbono": {"indice": round(indice_c, 2), "tendencia": tendencia_c, "meses_raices_vivas": round(vivos * 12, 1)},
        "puntajes": puntajes,
        "alertas": alertas,
        "penalizacion": penalizacion,
    }


# Escala por lote. En una suma ponderada cada peso vale lo que vale pasar
# de la peor a la mejor opción en ese criterio («peso por salto»). Con la escala de Uruguay, el forraje, la simplicidad y
# la diversificación siempre van de 0 a 100 entre las rotaciones de un lote, y el agua y el clima (que dependen del
# lugar) mucho menos: con agua 3 y forraje 3, el forraje movía el orden tres veces más. Para el total, cada criterio se
# mide entre la peor y la mejor opción del lote. El piso evita que una diferencia chica (dos opciones casi iguales en un
# criterio) se estire hasta 0-100: un rango menor que PISO_LOTE puntos de la escala de Uruguay cuenta como PISO_LOTE.
PISO_LOTE = 30.0


def escala_lote(evs: list[dict], piso: float = PISO_LOTE) -> dict[str, tuple[float, float]]:
    """{criterio: (lo peor del lote, rango usado)} con los puntajes de todas las opciones del lote."""
    esc = {}
    for d in DIMENSIONES:
        v = [e["puntajes"][d] for e in evs]
        esc[d] = (min(v), max(max(v) - min(v), piso))
    return esc


def puntajes_en_lote(ev: dict, escala: dict[str, tuple[float, float]] | None) -> dict[str, float]:
    if not escala:
        return dict(ev["puntajes"])
    return {d: _clip(100 * (ev["puntajes"][d] - escala[d][0]) / escala[d][1]) for d in DIMENSIONES}


def ponderar(ev: dict, prioridades: dict, escala: dict[str, tuple[float, float]] | None = None) -> float:
    """Promedio de los criterios pesado por las prioridades. Con `escala`, cada criterio medido dentro del lote."""
    pesos = {d: float(prioridades.get(d, 2)) for d in DIMENSIONES}
    total = sum(pesos.values()) or 1
    pj = puntajes_en_lote(ev, escala)
    s = sum(pj[d] * w for d, w in pesos.items()) / total
    # Sin el ×0,8 por pasarse de la tolerancia. La erosión ya está en el criterio suelo, y la tolerancia es
    # una condición: las que se pasan van después de las que cumplen (`plan.orden`), con el aviso. Contarla también
    # acá la metía tres veces (22-ponderacion.md).
    s *= ev.get("penalizacion", 1.0)  # lo que dijo el productor (ej. se anega) pesa sobre el puntaje
    return round(s, 1)


# --------------------------------------------------------------------------------------------
# Rotación actual a partir de lo que dijo el productor
# --------------------------------------------------------------------------------------------


def rotacion_desde_historial(historial: list[dict]) -> Rotacion | None:
    """historial: [{"anio": 2023, "invierno": "trigo", "verano": "soja2"}...] (más viejo primero)."""
    anios = []
    for h in sorted(historial or [], key=lambda x: x.get("anio", 0)):
        inv = h.get("invierno") or "barbecho"
        ver = h.get("verano") or "barbecho"
        if inv not in CULTIVOS:
            inv = "barbecho"
        if ver not in CULTIVOS:
            ver = "barbecho"
        if CULTIVOS[inv].temporada == "perenne" and ver == "barbecho":
            ver = inv
        anios.append((inv, ver))
    if not anios:
        return None
    # recortar repeticiones exactas de un ciclo (soja, soja, soja → soja)
    for largo in range(1, len(anios) + 1):
        patron = anios[:largo]
        if all(anios[i] == patron[i % largo] for i in range(len(anios))):
            anios = patron
            break
    texto = " → ".join(
        f"{CULTIVOS[i].nombre.split(' (')[0].lower()} / {CULTIVOS[v].nombre.split(' (')[0].lower()}" for i, v in anios
    )
    return Rotacion("actual", "Rotación actual", f"Lo que se hizo en los últimos años: {texto}.", tuple(anios),
                    "actual")


# --------------------------------------------------------------------------------------------
# Las 5 filas del desafío
# --------------------------------------------------------------------------------------------


def _n(x: float | None, d: int = 1) -> str:
    """Número con coma decimal, como se escribe en Uruguay."""
    if x is None:
        return "s/d"
    return f"{x:.{d}f}".replace(".", ",")


def _con_signo(x: float, d: int = 0) -> str:
    """+0,6 / −2 / 0, para los cambios de clima."""
    r = round(x, d)
    if r == 0:
        return _n(0.0, d)
    return ("+" if r > 0 else "−") + _n(abs(r), d)


def _pct(x: float | None) -> str:
    return "s/d" if x is None else f"{round(100 * x)} %"


def _de10(x: float | None) -> str:
    if x is None:
        return "s/d"
    if round(10 * x) == 0:
        return "menos de 1 de cada 10 años"
    return f"{round(10 * x)} de cada 10 años"


def explicar(ev: dict, ctx: dict, actual: dict | None) -> dict:
    er = ev["erosion"]
    suelo = ctx.get("suelo") or {}
    clima_info = ctx.get("clima_info") or {}
    por_que, beneficios, riesgos, huecos, evidencia = [], [], [], [], []

    if actual and actual["id"] != ev["id"]:
        d_a = actual["erosion"]["a_t_ha"] - er["a_t_ha"]
        if d_a > 0.5:
            por_que.append(f"Baja la erosión de {_n(actual['erosion']['a_t_ha'])} a {_n(er['a_t_ha'])} t/ha/año "
                           f"(tolerancia del suelo: {_n(er['tolerancia_t'], 0)}).")
        d_s = actual["riesgo"]["seca"] - ev["riesgo"]["seca"]
        if d_s > 0.05:
            por_que.append(f"Reparte el riesgo de seca: pasar la floración sin agua baja de "
                           f"{_de10(actual['riesgo']['seca'])} a {_de10(ev['riesgo']['seca'])}, en promedio.")
        d_m = len(actual["meses_descubierto"]) - len(ev["meses_descubierto"])
        if d_m > 0:
            por_que.append(f"El suelo queda descubierto {len(ev['meses_descubierto'])} meses al año en vez de "
                           f"{len(actual['meses_descubierto'])}.")
        if ev["forraje"] - actual["forraje"] > 0.15:
            por_que.append("Produce forraje para el ganado durante más meses del año.")
    elif actual and actual["id"] == ev["id"]:
        por_que.append("Es lo que se viene haciendo: la línea de base contra la que se comparan las demás.")
    if not por_que:
        mejor = max(ev["puntajes"], key=ev["puntajes"].get)
        por_que.append(f"Su punto fuerte es {NOMBRE_DIM[mejor].lower()} ({ev['puntajes'][mejor]}/100).")

    evidencia.append(
        f"Erosión con la ecuación del Plan de Uso: A = R {er['r']} × K {_n(er['k'], 3)} × LS {_n(er['ls'], 2)} × "
        f"C {_n(er['c'], 3)} × P {_n(er['p'])} = {_n(er['a_t_ha'])} t/ha/año."
    )
    if er.get("largo_m"):
        origen = {
            "productor": "el que cargaste",
            "srtm": "sacado del relieve de la NASA (SRTM) siguiendo el camino del agua en el lote",
        }.get(er.get("largo_origen"), "un valor típico, porque no se pudo sacar del relieve")
        evidencia.append(f"LS con largo de ladera de {er['largo_m']} m: {origen}.")
    aprox = er.get("aproximaciones") or []
    if aprox:
        nom_aprox = " y ".join(CULTIVOS[c].nombre.split(" (")[0].lower() for c in aprox if c in CULTIVOS)
        evidencia.append(
            f"Factor C con relaciones de pérdida de suelo de Erosión 6.0 (MGAP - UdelaR), con aproximación propia para {nom_aprox}."
        )
    else:
        evidencia.append(
            "Factor C con relaciones de pérdida de suelo de Erosión 6.0 (MGAP - UdelaR)."
        )
    fut = clima_info.get("futuro")
    if fut:
        # De dónde salen la seca, la helada y el calor (fuentes/cmip6.py)
        evidencia.append(
            f"Seca, helada y calor: los años reales {fut['periodo_real']} ajustados a lo que proyectan {fut['modelos']} "
            f"modelos de la NASA (NEX-GDDP-CMIP6, escenario medio) para {fut['futuro']}: {_con_signo(fut['temp_c'], 1)} °C y "
            f"{_con_signo(fut['lluvia_pct'])} % de lluvia (entre modelos, de {_con_signo(fut['lluvia_pct_rango'][0])} % a "
            f"{_con_signo(fut['lluvia_pct_rango'][1])} %)."
        )
    if ctx.get("r_fuente"):
        evidencia.append(ctx["r_fuente"])
    if suelo.get("grupo_coneat"):
        evidencia.append(
            f"Suelo (MGAP): grupo CONEAT {suelo['grupo_coneat']}, {suelo.get('suelo_dominante', '')}, "
            f"K {_n(suelo.get('factor_k'), 3)}, tolerancia {_n(suelo.get('tolerancia_t'), 0)} t/ha/año, pendiente "
            f"{_n(er['pendiente_pct'])} %."
        )
    elif suelo.get("pais") == "US":
        # Campos de EE. UU., con la carta de suelos SSURGO
        evidencia.append(
            f"Suelo (USDA-NRCS SSURGO): {suelo.get('unidad_cartografica') or suelo.get('suelo_dominante', '')}, "
            f"K {_n(suelo.get('factor_k_usda'), 2)} (USLE de EE. UU.), tolerancia T {_n(suelo.get('tolerancia_t_usda'), 0)} "
            f"t/acre/año ({_n(suelo.get('tolerancia_t'), 1)} t/ha), pendiente {_n(er['pendiente_pct'])} %, "
            f"grupo hidrológico {suelo.get('grupo_hidrologico') or '—'}."
        )
    elif suelo.get("mundial"):
        evidencia.append(
            f"Suelo (SoilGrids, mapa mundial de 250 m): {_n(suelo.get('arena'), 0)} % arena, {_n(suelo.get('limo'), 0)} % limo, "
            f"{_n(suelo.get('arcilla'), 0)} % arcilla y {_n(suelo.get('materia_organica'))} % de materia orgánica; K "
            f"{_n(suelo.get('factor_k'), 3)} (EPIC), tolerancia típica 7 t/ha/año, pendiente {_n(er['pendiente_pct'])} %."
        )
    if clima_info.get("meses_pico"):
        evidencia.append(
            f"Lluvia erosiva ({clima_info.get('fuente_lluvia') or 'NASA POWER'} {clima_info.get('periodo')}): se concentra en "
            f"{', '.join(clima_info['meses_pico'])}. Meses con el suelo descubierto en esta rotación: "
            f"{', '.join(ev['meses_descubierto']) or 'ninguno'}."
        )
    # La lluvia sale de GPM IMERG desde 2000; la evaporación (ET0), de NASA POWER
    fuente_agua = ("lluvia de GPM IMERG y evaporación de NASA POWER" if clima_info.get("fuente_lluvia") == "GPM IMERG"
                   else "NASA POWER")
    for fila in ev["riesgo"]["por_cultivo"]:
        if fila.get("prob_seca") is not None and CULTIVOS[fila["cultivo"]].ky > 0:
            evidencia.append(
                f"{fila['nombre']}: pasó su {fila['ventana_agua']} con menos de la mitad del agua que necesitaba "
                f"en {_de10(fila['prob_seca'])} ({fuente_agua}, balance FAO-56)."
            )
        # Se muestra contra el rinde con agua suficiente y no contra un año normal, porque con muchos años
        # secos el «normal» ya viene golpeado (en La Loma la soja continua parecía caer menos que una rotación con colza)
        if fila.get("perdida_anio_seco") is not None and fila["perdida_anio_seco"] >= 0.01:
            evidencia.append(
                f"{fila['nombre']}: en un año seco, de los que vienen 1 de cada 5, pierde {_pct(fila['perdida_anio_seco'])} "
                f"de lo que rendiría con agua suficiente (FAO-33 con el agua de toda la temporada, {fuente_agua})."
            )
    ndvi = ctx.get("ndvi") or {}
    if ndvi.get("descubierto_por_anio"):
        meses = [d["meses_descubierto"] for d in ndvi["descubierto_por_anio"]]
        periodo = f"{ndvi['descubierto_por_anio'][0]['anio']}-{ndvi['descubierto_por_anio'][-1]['anio']}"
        if max(meses) == 0:
            evidencia.append(f"Satélite (MODIS NDVI): en {periodo} la sección no tuvo meses con el suelo descubierto.")
        else:
            rango = f"entre {min(meses)} y {max(meses)}" if min(meses) != max(meses) else f"{max(meses)}"
            evidencia.append(f"Satélite (MODIS NDVI): en {periodo} la sección estuvo descubierta {rango} meses por año.")

    if ctx.get("punto"):
        from ..fuentes import gaez as gaez_mod
        evidencia.extend(gaez_mod.frases_rotacion(sum(ev["anios"], []), *ctx["punto"]))

    if er["cumple"] and er.get("ratio", 0) <= 1:
        beneficios.append(f"Cumple la tolerancia de erosión del suelo ({_n(er['a_t_ha'])} ≤ {_n(er['tolerancia_t'], 0)} t/ha/año).")
    elif er["cumple"]:
        beneficios.append("Es campo natural: el Plan de Uso no se exige (es para cultivos y pasturas sembradas).")
    if ev["carbono"]["tendencia"] == "sube":
        beneficios.append("Suma carbono al suelo: raíces vivas casi todo el año y mucho rastrojo o pastura.")
    elif ev["carbono"]["tendencia"] == "se mantiene":
        beneficios.append("Mantiene el carbono del suelo si se cuida el rastrojo.")
    if any(CULTIVOS[c].fija_n for c in ev["anios"][0] + sum(ev["anios"][1:], [])):
        beneficios.append("Incluye leguminosas que fijan nitrógeno.")
    if ev["forraje"] >= 0.4:
        beneficios.append(f"Aporta forraje ({_pct(ev['forraje'])} de las temporadas).")
    if ev["ingreso"]["usa_margenes"] and ev["ingreso"]["usd_ha_anio"]:
        beneficios.append(f"Margen esperado con tus números: {ev['ingreso']['usd_ha_anio']} USD/ha/año "
                          f"({ev['ingreso']['usd_ha_anio_con_riesgo']} descontando años de seca).")
    ing = ev["ingreso"]
    if ing.get("usd_ha_anio_despues_de_renta") is not None:
        beneficios.append(f"Después de pagar la renta ({_n(ing['renta_kg'], 0)} kg de soja ≈ {ing['renta_usd_ha']} USD/ha "
                          f"con soja a {_n(ing['precio_soja'], 0)} USD/t): {ing['usd_ha_anio_despues_de_renta']} USD/ha/año.")
    if ing.get("equilibrios"):
        partes = []
        for q in ing["equilibrios"]:
            t = f"{q['nombre'].lower()} {_n(q['kg_ha'], 0)} kg/ha"
            if q.get("rinde_esperado"):
                t += f" (esperás {_n(float(q['rinde_esperado']), 0)})"
                esp = float(q["rinde_esperado"])
                if esp < q["kg_ha"]:
                    riesgos.append(f"{q['nombre']}: con el rinde que esperás ({_n(esp, 0)} kg/ha) no llega al de "
                                   f"equilibrio ({_n(q['kg_ha'], 0)} kg/ha): pierde plata.")
                elif esp < q["kg_ha"] * 1.1:
                    riesgos.append(f"{q['nombre']}: el rinde que esperás ({_n(esp, 0)} kg/ha) queda a menos de 10 % "
                                   f"por encima del de equilibrio ({_n(q['kg_ha'], 0)} kg/ha).")
            partes.append(t)
        evidencia.append("Rinde de equilibrio (costo" + (" y renta" if ing.get("renta_kg") else "") + "): "
                         + "; ".join(partes) + ".")
    beneficios.extend(ev.get("beneficios_extra") or [])
    if ev["puntajes"]["diversificacion"] >= 60:
        beneficios.append("Diversifica: corta ciclos de malezas, plagas y enfermedades y reparte el riesgo de precio.")

    if ev["riesgo"]["seca"] >= 0.3:
        riesgos.append(f"Seca en floración en {_de10(ev['riesgo']['seca'])} en promedio para sus cultivos.")
    for fila in ev["riesgo"]["por_cultivo"]:
        if (fila.get("prob_helada") or 0) >= 0.2:
            riesgos.append(f"{fila['nombre']}: helada (≤ 2 °C a 2 m) en {fila['ventana_helada']} en {_de10(fila['prob_helada'])}.")
        if (fila.get("prob_calor") or 0) >= 0.3:
            riesgos.append(f"{fila['nombre']}: 3 o más días de calor extremo en {fila['ventana_calor']} en {_de10(fila['prob_calor'])}.")
    riesgos.extend(ev["alertas"])
    tend = (clima_info.get("tendencia") or {}).get("cultivos", {})
    for cod in dict.fromkeys(c for c in sum(ev["anios"], []) if c in tend):
        ps = tend[cod].get("prob_seca")
        if (
            ps
            and ps.get("antes") is not None
            and ps.get("ahora") is not None
            and ps["ahora"] > ps["antes"]
            and (ps.get("cambio_claro") if "cambio_claro" in ps else es_cambio_claro(ps["antes"], ps["ahora"]))
        ):
            riesgos.append(
                f"El clima se está corriendo: para {CULTIVOS[cod].nombre.lower()} la seca en floración pasó de "
                f"{_de10(ps['antes'])} ({clima_info['tendencia']['periodo_antes']}) a {_de10(ps['ahora'])} "
                f"({clima_info['tendencia']['periodo_ahora']})."
            )

    huecos.extend(ctx.get("huecos") or [])
    if ing.get("margenes_estimados"):
        huecos.append("Sin tu margen de " + ", ".join(CULTIVOS[c].nombre.lower() for c in ing["margenes_estimados"])
                      + ": lo estimé con el índice relativo, escalado a los márgenes que cargaste.")
    if not ev["ingreso"]["usa_margenes"]:
        huecos.append("Sin márgenes propios por cultivo: el ingreso es un índice relativo, no dólares.")
        if ing.get("renta_kg"):
            huecos.append(f"Pagás {_n(ing['renta_kg'], 0)} kg de soja de renta: con rinde, precio y costo de cada cultivo "
                          "se calcula cuánto queda después de pagarla y el rinde de equilibrio.")
    if aprox:
        nom_aprox = " y ".join(CULTIVOS[c].nombre.split(" (")[0].lower() for c in aprox if c in CULTIVOS)
        huecos.append(
            f"Aproximación propia para {nom_aprox}: no está en Erosión 6.0 y se usó Cereales de Invierno con rendimiento bajo."
            if len(aprox) == 1
            else f"Aproximación propia para {nom_aprox}: no están en Erosión 6.0 y se usó Cereales de Invierno con rendimiento bajo."
        )

    return {"por_que": por_que, "evidencia": evidencia, "beneficios": beneficios, "huecos": huecos, "riesgos": riesgos}
