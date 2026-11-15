"""Dos métodos para decidir, mes a mes, si una sección estuvo con el suelo descubierto (NDVI de MODIS).

El desafío pide comparar enfoques estadísticos o de IA para encontrar patrones. Acá se comparan dos
formas de pasar de "qué tan verde se vio" a "estuvo descubierto o no":

1. **Corte fijo (regla agronómica)**: NDVI < 0,30 = suelo desnudo o rastrojo seco. Es el umbral de uso
   común para MODIS y el mismo para todo el país. Su debilidad: el NDVI del suelo desnudo cambia con el
   color del suelo, la humedad y el rastrojo, así que un mismo número no significa lo mismo en todas las
   chacras.
2. **Corte automático por sección (método de Otsu)**: sin entrenar con nada, toma la serie de NDVI de esa
   sección y busca el número que mejor la separa en dos grupos ("bajo" y "alto"), el que maximiza la
   diferencia entre los grupos (Otsu 1979; es lo mismo que agrupar en dos con k-medias en una dimensión).
   Se adapta a cada suelo, pero solo tiene sentido si la sección pasó por los dos estados: en una pastura
   que estuvo verde siempre, "separar en dos" inventa una diferencia que no existe.

Lo que se muestra: el corte de cada método, cuántos meses por año da descubierto cada uno, en qué
porcentaje de los meses coinciden y el kappa de Cohen (coincidencia descontando la que daría el azar).
Donde no coinciden es la "zona gris" que conviene mirar en el campo.
"""

from __future__ import annotations

import numpy as np

UMBRAL_FIJO = 0.30
SEPARACION_MINIMA = 0.15  # diferencia de promedios entre los dos grupos para que Otsu tenga sentido
TECHO_GRUPO_BAJO = 0.40  # el grupo "bajo" tiene que parecer suelo: si su promedio pasa esto, es pasto en su época seca


def corte_otsu(valores: list[float]) -> tuple[float, float, float]:
    """Corte que maximiza la varianza entre los dos grupos. Devuelve (corte, separación, promedio del grupo bajo)."""
    x = np.sort(np.asarray(valores, dtype=float))
    n = len(x)
    if n < 4:
        return float("nan"), 0.0, float("nan")
    mejor, corte, sep, bajo = -1.0, float(x[n // 2]), 0.0, float(x[0])
    acum = np.cumsum(x)
    total = acum[-1]
    for i in range(1, n):
        if x[i] == x[i - 1]:
            continue
        w0, w1 = i / n, (n - i) / n
        m0, m1 = acum[i - 1] / i, (total - acum[i - 1]) / (n - i)
        var = w0 * w1 * (m0 - m1) ** 2
        if var > mejor:
            mejor, corte, sep, bajo = var, float((x[i - 1] + x[i]) / 2), float(m1 - m0), float(m0)
    return corte, sep, bajo


def _kappa(a: np.ndarray, b: np.ndarray) -> float | None:
    po = float(np.mean(a == b))
    pa, pb = float(np.mean(a)), float(np.mean(b))
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe >= 1 else round((po - pe) / (1 - pe), 2)


def comparar(mensual: list[dict]) -> dict:
    """mensual: [{"anio", "mes", "ndvi"}]. Usa solo los años con 10 meses o más (igual que la app)."""
    por_anio: dict[int, list[dict]] = {}
    for m in mensual or []:
        por_anio.setdefault(int(m["anio"]), []).append(m)
    filas = [m for y, ms in sorted(por_anio.items()) if len(ms) >= 10 for m in sorted(ms, key=lambda r: r["mes"])]
    if len(filas) < 12:
        return {"ok": False, "motivo": "Hace falta al menos un año de NDVI para comparar los métodos."}
    ndvi = np.array([f["ndvi"] for f in filas])
    anios = sorted({f["anio"] for f in filas})
    corte, sep, bajo = corte_otsu(ndvi.tolist())
    separa = sep >= SEPARACION_MINIMA
    otsu_aplica = separa and bajo <= TECHO_GRUPO_BAJO
    fijo = ndvi < UMBRAL_FIJO
    auto = ndvi < corte if otsu_aplica else np.zeros_like(fijo)

    def por_anio_medio(mask: np.ndarray) -> float:
        return round(float(mask.sum()) / len(anios), 1)

    distintos = [{"anio": f["anio"], "mes": f["mes"], "ndvi": f["ndvi"], "fijo": bool(a), "auto": bool(b)}
                 for f, a, b in zip(filas, fijo, auto) if a != b]
    coincidencia = round(100 * float(np.mean(fijo == auto)))
    kappa = _kappa(fijo, auto) if otsu_aplica else None

    if not separa:
        lectura = ("La sección no pasó por dos estados claros (casi siempre verde o casi siempre pelada): el corte "
                   "automático no tiene qué separar y vale el corte fijo.")
    elif not otsu_aplica:
        bajo_txt = f"{bajo:.2f}".replace(".", ",")
        lectura = (f"Los meses más bajos de esta sección siguen siendo vegetación (NDVI promedio {bajo_txt}): el corte "
                   "automático separaría la época verde de la época seca del pasto, no suelo cubierto de descubierto. "
                   "Los dos métodos coinciden en que no hubo suelo desnudo.")
    elif coincidencia >= 90:
        lectura = "Los dos métodos coinciden casi siempre: la lectura del satélite es firme."
    elif corte > UMBRAL_FIJO:
        lectura = ("El corte automático queda más alto que el fijo: en esta sección hay meses de cobertura rala "
                   "(rastrojo, cultivo recién nacido o maleza) que el corte fijo cuenta como cubiertos. Conviene "
                   "mirar en el campo esos meses.")
    else:
        lectura = ("El corte automático queda más bajo que el fijo: el suelo de esta sección se ve más verde "
                   "que el promedio aun pelado (o el rastrojo queda verde), y el corte fijo puede exagerar los meses "
                   "descubiertos.")
    return {
        "ok": True,
        "anios": len(anios),
        "meses": len(filas),
        "metodos": [
            {"id": "fijo", "nombre": "Corte fijo (regla agronómica)", "corte": UMBRAL_FIJO,
             "meses_por_anio": por_anio_medio(fijo)},
            {"id": "otsu", "nombre": "Corte automático por sección (Otsu)", "corte": round(corte, 3) if otsu_aplica else None,
             "meses_por_anio": por_anio_medio(auto) if otsu_aplica else None, "aplica": otsu_aplica,
             "separacion": round(sep, 3), "promedio_grupo_bajo": round(bajo, 3)},
        ],
        "coincidencia_pct": coincidencia if otsu_aplica else None,
        "kappa": kappa,
        "distintos": distintos[-12:],
        "lectura": lectura,
    }
