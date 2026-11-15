"""Análisis completo de un campo y armado del plan por sección.

Flujo:
1. Clima de NASA POWER en el centro del campo (una celda de ~50 km alcanza para todo el campo).
2. Factor R oficial del MGAP (19 estaciones) y reparto mensual de la lluvia erosiva de NASA.
3. Por sección, en paralelo: suelo del MGAP en un punto interior, NDVI de MODIS, análisis de
   suelo propio si hay, agua útil → riesgos de cada cultivo con ese suelo.
4. Rotación actual (lo que contó el productor, o lo que vio el satélite) + candidatas, evaluadas
   y ordenadas por las prioridades del productor.
5. Plan: la mejor alternativa por sección, con las fases corridas entre secciones para que cada
   temporada el campo tenga cultivos repartidos (ingreso y trabajo más parejos).
"""

from __future__ import annotations

import contextvars
import datetime as dt
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterator

from shapely.geometry import shape

from ..fuentes import cdl, cmip6, hls_ndvi, mgap, modis, power, region, soilgrids, ssurgo
from . import descubierto, incertidumbre
from . import clima as clima_mod
from . import rotaciones as rot_mod
from . import suelo as suelo_mod
from .cultivos import CULTIVOS, HEMISFERIO

HORIZONTE_ANIOS = 5  # (antes 6)
CON_GANADO = {"verdeo_sorgo", "alfalfa_maiz", "campo_natural"}
PRIORIDADES_BASE = {"suelo": 3, "agua": 3, "clima": 2, "ingreso": 3, "forraje": 3, "simplicidad": 1,
                    "diversificacion": 1}


def _grupo(e: dict) -> str:
    if e["tipo"] == "actual":
        perennes = sum(1 for inv, _ in e["anios"] if CULTIVOS[inv].temporada == "perenne")
        return "ganadera" if perennes * 2 >= len(e["anios"]) else "agrícola"
    return "agrícola" if e["tipo"] == "agrícola" else "ganadera"


def _fmt_t_ha(v: float) -> str:
    r = round(v, 1)
    if r == int(r):
        return str(int(r))
    return f"{r:.1f}".replace(".", ",")


MINIMO_ALTERNATIVAS = 2  # con lo de hoy, al menos tres estrategias por lote, como pide la consigna


def _base(e: dict) -> str:
    """La misma rotación con y sin curvas de nivel cuenta como una sola."""
    return e["id"].removesuffix("_curvas")


def orden(e: dict) -> tuple[bool, float]:
    """Para ordenar las rotaciones de un lote: primero las que cumplen la tolerancia del suelo y, dentro de cada grupo,
    de mayor a menor puntaje. Antes las que se pasaban bajaban por un ×0,8 en el puntaje, y una que se pasaba
    con mucha ventaja en otro criterio podía quedar arriba de una que cumplía."""
    return (not e.get("erosion", {}).get("cumple", True), -e["puntaje_total"])


def elegir_recomendada(actual: dict | None, top: list[dict]) -> dict | None:
    """La recomendada del lote: la primera alternativa, salvo que lo que ya hace el productor cumpla la tolerancia y
    la alternativa no, o puntúe igual o mejor: entonces, seguir con lo de hoy. Antes, si ninguna
    alternativa cumplía, se recomendaba la que menos erosiona aunque lo de hoy sí cumpliera, con solo puntuar un poco
    más (la tolerancia es una condición, no un criterio más)."""
    if not top:
        return actual
    # lo de hoy con un cultivo que el productor ya no quiere se muestra para comparar, pero no se sugiere
    if actual and actual.get("erosion", {}).get("cumple", False) and not actual.get("tiene_excluidos"):
        if not top[0].get("erosion", {}).get("cumple", False) or actual["puntaje_total"] >= top[0]["puntaje_total"]:
            return actual
    return top[0]


SORTEOS_ACEPTABILIDAD = 2000


def aceptabilidad(opciones: list[dict], prioridades: dict, escala: dict | None, semilla: str = "",
                  n: int = SORTEOS_ACEPTABILIDAD) -> dict[str, int] | None:
    """En cuántos de cada 100 juegos de pesos parecidos a los del productor sale primera cada opción. Las prioridades de 0 a 5 dicen bien el orden, no los pesos exactos (la gente distingue la
    importancia de los criterios hasta un orden; Srivastava 1995, Kuller et al. 2026). Se sortean `n` juegos de pesos
    que respetan ese orden (los empates quedan empatados) y se cuenta cuál gana en cada uno: es el «índice de
    aceptabilidad» de SMAA (Lahdelma y Salminen). Con los ajustes por lo que contó el productor tal cual."""
    import zlib

    import numpy as np

    dims = [d for d in rot_mod.DIMENSIONES if float(prioridades.get(d, 2)) > 0]
    if len(opciones) < 2 or len(dims) < 2:
        return None
    pri = np.array([float(prioridades.get(d, 2)) for d in dims])
    pj = np.array([[rot_mod.puntajes_en_lote(e, escala)[d] for d in dims] for e in opciones])
    base = pj @ (pri / pri.sum())
    factor = np.array([e["puntaje_total"] / b if b > 0 else 1.0 for e, b in zip(opciones, base)])
    rng = np.random.default_rng(zlib.crc32(semilla.encode("utf-8")))
    # pesos al azar en el simplex, ordenados de mayor a menor y repartidos según el orden de las prioridades
    w = np.sort(rng.dirichlet(np.ones(len(dims)), size=n), axis=1)[:, ::-1]
    puesto = np.argsort(-pri, kind="stable")
    pesos = np.empty_like(w)
    pesos[:, puesto] = w
    for p in np.unique(pri):  # las prioridades empatadas reciben el mismo peso
        m = pri == p
        if m.sum() > 1:
            pesos[:, m] = pesos[:, m].mean(axis=1, keepdims=True)
    cuenta = np.bincount(np.argmax((pesos @ pj.T) * factor, axis=1), minlength=len(opciones))
    return {e["id"]: round(100 * int(c) / n) for e, c in zip(opciones, cuenta)}


def recomendar(actual: dict | None, top: list[dict], prioridades: dict, escala: dict | None,
               semilla: str = "") -> tuple[dict | None, dict[str, int] | None]:
    """La recomendada del lote y la aceptabilidad de cada opción. Primero las reglas de `elegir_recomendada`
    (tolerancia, lo que el productor no quiere); entre las opciones que podrían recomendarse (las que se muestran,
    cumplen la tolerancia y no tienen un cultivo excluido), gana la que sale primera más seguido con pesos parecidos a
    los del productor. Si empatan, queda la de `elegir_recomendada`."""
    base = elegir_recomendada(actual, top)
    compiten = [e for e in ([actual] if actual else []) + top
                if e.get("erosion", {}).get("cumple", False) and not e.get("tiene_excluidos")]
    if base not in compiten:
        return base, None
    ac = aceptabilidad(compiten, prioridades, escala, semilla)
    if not ac:
        return base, None
    mejor = max(compiten, key=lambda e: (ac[e["id"]], e is base, e["puntaje_total"]))
    return mejor, ac


def elegir_variadas(evs: list[dict], n: int = 3, minimo: int = MINIMO_ALTERNATIVAS) -> tuple[list[dict], str | None]:
    """Las alternativas de un lote: primero las que cumplen la tolerancia (ver `_elegir_que_cumplen`) y, si no
    llegan a `minimo`, se completa con las de mejor puntaje que no cumplen, primero del grupo (agrícola o con ganado)
    que falte. Esas llevan en la tarjeta «Supera tolerancia» y en sus riesgos que no pasarían el Plan de Uso.

    La consigna pide comparar al menos tres estrategias, incluida la actual, cada una con su porqué,
    evidencia, beneficios, huecos y riesgos. Mostrando solo las que cumplen, en el campo de ejemplo 3 de 6 lotes
    quedaban con lo de hoy y una sola alternativa. La erosión pasa a ser una condición que se avisa, no un filtro.
    """
    top, nota = _elegir_que_cumplen(evs, n)
    if len(top) >= minimo:
        return top, nota
    top = list(top)
    usadas = {_base(e) for e in top}
    resto = [e for e in sorted(evs, key=lambda e: -e["puntaje_total"]) if e not in top and _base(e) not in usadas]
    grupos = {_grupo(e) for e in top}
    for solo_grupo_nuevo in (True, False):
        for e in resto:
            if len(top) >= minimo:
                break
            if _base(e) in usadas or (solo_grupo_nuevo and _grupo(e) in grupos):
                continue
            top.append(e)
            usadas.add(_base(e))
            grupos.add(_grupo(e))
    return top, nota


def _elegir_que_cumplen(evs: list[dict], n: int = 3) -> tuple[list[dict], str | None]:
    """Elige como tarjetas solo opciones que cumplen la tolerancia.

    Si ambos grupos (agrícola y con ganado) tienen opciones que cumplen, elige la mejor de cada uno
    y completa hasta n con las siguientes que también cumplan.
    Si el 'otro tipo' no tiene ninguna que cumpla, no muestra tarjeta de ese tipo y devuelve una
    nota corta con los números reales del caso.
    Si ninguna alternativa cumple la tolerancia, devuelve la que menos erosiona y una nota clara.
    """
    if not evs:
        return [], None

    cumplen = [e for e in evs if e.get("erosion", {}).get("cumple")]

    # Caso: ninguna alternativa cumple la tolerancia
    if not cumplen:
        menos_erosiona = min(evs, key=lambda e: (e["erosion"]["a_t_ha"], -e["puntaje_total"]))
        a = menos_erosiona["erosion"]["a_t_ha"]
        t = menos_erosiona["erosion"]["tolerancia_t"]
        nom_rot = menos_erosiona["nombre"][:1].lower() + menos_erosiona["nombre"][1:]
        # Sin «te mostramos la que menos erosiona», que no cuadraba cuando había más tarjetas
        nota = (
            f"Ninguna opción queda dentro de lo que aguanta el suelo en este lote ({_fmt_t_ha(t)} t/ha/año). "
            f"La que menos lo erosiona es {nom_rot}: {_fmt_t_ha(a)} t/ha/año"
        )
        return [menos_erosiona], nota

    # Caso: al menos una cumple
    mejor = cumplen[0]
    g_mejor = _grupo(mejor)
    g_otro = "agrícola" if g_mejor == "ganadera" else "ganadera"

    cumplen_otro = [e for e in cumplen if _grupo(e) == g_otro]
    if cumplen_otro:
        elegidas = [mejor, cumplen_otro[0]]
        for e in cumplen:
            if len(elegidas) >= n:
                break
            if e not in elegidas:
                elegidas.append(e)
        return sorted(elegidas, key=lambda e: -e["puntaje_total"]), None

    # El otro tipo no tiene ninguna que cumpla
    evs_otro = [e for e in evs if _grupo(e) == g_otro]
    nota = None
    if evs_otro:
        mejor_otro = evs_otro[0]
        a = mejor_otro["erosion"]["a_t_ha"]
        t = mejor_otro["erosion"]["tolerancia_t"]
        nom_rot = mejor_otro["nombre"][:1].lower() + mejor_otro["nombre"][1:]
        if g_otro == "agrícola":
            nota = (
                f"Con solo cultivos, ninguna rotación cumple lo que aguanta el suelo en este lote: "
                f"la mejor ({nom_rot}) perdería {_fmt_t_ha(a)} t/ha/año y el suelo aguanta {_fmt_t_ha(t)}"
            )
        else:
            nota = (
                f"Con pasturas o ganado, ninguna rotación cumple lo que aguanta el suelo en este lote: "
                f"la mejor ({nom_rot}) perdería {_fmt_t_ha(a)} t/ha/año y el suelo aguanta {_fmt_t_ha(t)}"
            )

    top = cumplen[:n]
    return top, nota


def area_ha(geojson: dict) -> float:
    g = shape(geojson)
    lat0 = g.centroid.y
    kx = 111320 * math.cos(math.radians(lat0))
    ky = 110540

    def proyectar(coords):
        return [(x * kx, y * ky) for x, y, *_ in coords]

    from shapely.geometry import MultiPolygon, Polygon

    def pol(p):
        return Polygon(proyectar(p.exterior.coords), [proyectar(i.coords) for i in p.interiors])

    if g.geom_type == "Polygon":
        return pol(g).area / 1e4
    if g.geom_type == "MultiPolygon":
        return MultiPolygon([pol(p) for p in g.geoms]).area / 1e4
    return 0.0


def punto_interior(geojson: dict) -> tuple[float, float]:
    p = shape(geojson).representative_point()
    return p.y, p.x


def temporada_actual(hoy: dt.date | None = None, hemisferio: str = "sur") -> tuple[str, int]:
    """La próxima decisión. Sur: de julio a diciembre se decide el verano de este año; de enero a junio, el invierno.
    Norte: de enero a junio, el verano de este año (maíz y soja se siembran en abril-mayo); de julio a
    septiembre, el invierno que se siembra en octubre; de octubre en adelante ese invierno ya está sembrado y se
    decide el verano del año que viene."""
    hoy = hoy or dt.date.today()
    if hemisferio == "norte":
        if hoy.month <= 6:
            return "verano", hoy.year
        if hoy.month <= 9:
            return "invierno", hoy.year
        return "verano", hoy.year + 1
    if hoy.month >= 7:
        return "verano", hoy.year
    return "invierno", hoy.year


def etiquetas_temporadas(n_anios: int, hoy: dt.date | None = None, hemisferio: str = "sur") -> list[dict]:
    """Sur: el verano cruza el año («Verano 2026/27») y el invierno no. Norte: al revés («Verano 2027»,
    «Invierno 2027/28»). En los dos, cada invierno arranca un año nuevo de la rotación."""
    tipo, y = temporada_actual(hoy, hemisferio)
    norte = hemisferio == "norte"
    out = []
    for i in range(n_anios * 2):
        if tipo == "verano":
            etiqueta = f"Verano {y}" if norte else f"Verano {y}/{str(y + 1)[2:]}"
            out.append({"tipo": "verano", "anio": y, "etiqueta": etiqueta})
            tipo = "invierno"
            if not norte:
                y += 1
        else:
            etiqueta = f"Invierno {y}/{str(y + 1)[2:]}" if norte else f"Invierno {y}"
            out.append({"tipo": "invierno", "anio": y, "etiqueta": etiqueta})
            tipo = "verano"
            if norte:
                y += 1
    return out


def siembras_pastura(rot: rot_mod.Rotacion, fase: int, temporadas: list[dict]) -> tuple[list[str | None], str | None]:
    """En qué temporadas del plan se siembra (o se renueva) la pastura, y la próxima vez aunque caiga después del
    plan.
    Mismo criterio que la cobertura del factor C: se siembra el primer año de pastura después de cultivos, y la
    pradera permanente se renueva en su primer año. Se siembra en otoño: se marca en el invierno de ese año."""
    n = len(rot.anios)
    sembrar: dict[int, str] = {}
    for i, (inv, ver) in enumerate(rot.anios):
        if inv != ver or CULTIVOS[inv].temporada != "perenne" or inv == "campo_natural":
            continue
        prev = rot.anios[(i - 1) % n]
        prev_pastura = prev[0] == prev[1] and CULTIVOS[prev[0]].temporada == "perenne"
        if not prev_pastura:
            sembrar[i] = "siembra"
        elif rot.id.startswith("pradera_permanente") and i == 0:
            sembrar[i] = "renovación"
    marcas: list[str | None] = [None] * len(temporadas)
    if not sembrar:
        return marcas, None
    anio = fase
    for idx, t in enumerate(temporadas):
        if t["tipo"] == "invierno":
            if idx > 0:
                anio += 1
            marcas[idx] = sembrar.get(anio % n)
    texto = lambda que, anio_: f"{'se renueva' if que == 'renovación' else 'se siembra'} en el otoño de {anio_}"  # noqa: E731
    primera = next((i for i, m in enumerate(marcas) if m), None)
    if primera is not None:
        return marcas, texto(marcas[primera], temporadas[primera]["anio"])
    # no cae dentro del plan: la próxima, contando inviernos después del último
    ultimo = temporadas[-1]["anio"] if temporadas else 0
    for extra in range(1, n + 1):
        que = sembrar.get((anio + extra) % n)
        if que:
            return marcas, texto(que, ultimo + extra)
    return marcas, None


def secuencia(rot: rot_mod.Rotacion, fase: int, temporadas: list[dict]) -> list[str]:
    """Cultivo de cada temporada. Cada invierno arranca un año nuevo de la rotación (salvo que el
    plan empiece en invierno); el verano siguiente es la segunda mitad de ese mismo año."""
    n = len(rot.anios)
    out, anio = [], fase
    for idx, t in enumerate(temporadas):
        if t["tipo"] == "invierno":
            if idx > 0:
                anio += 1
            out.append(rot.anios[anio % n][0])
        else:
            out.append(rot.anios[anio % n][1])
    return out


def ajuste_tenencia(e: dict, rot, sistema: dict, vende_forraje: bool) -> None:
    """Campo arrendado: el arrendatario paga renta todos los años y lo que la pastura le da al suelo
    queda para el dueño. Con contrato corto, las rotaciones con años de pastura le sirven menos.
    Ajuste propio, a validar: hasta −30 % con 5 años o menos de contrato, −15 % con más (la mitad si
    el forraje se vende)."""
    if sistema.get("tenencia") != "arrendado":
        return
    perennes = sum(1 for inv, _ in rot.anios if CULTIVOS[inv].temporada == "perenne")
    if not perennes:
        return
    frac = perennes / len(rot.anios)
    anios = sistema.get("anios_contrato")
    peso = 0.3 if (anios is None or float(anios) <= 5) else 0.15
    if vende_forraje:
        peso /= 2
    e["puntaje_total"] = round(e["puntaje_total"] * (1 - peso * frac), 1)
    plazo = f"Con {int(anios)} años de contrato" if anios else "En campo arrendado"
    e["alertas"].append(
        f"{plazo}, {perennes} de cada {len(rot.anios)} años serían pastura: se paga la renta igual y la mejora "
        "del suelo queda para el dueño" + (" (el forraje vendido compensa una parte)." if vende_forraje else ".")
    )


def _aplica_a_seccion(texto: str | None, seccion: str | None, secciones: list[str]) -> bool:
    """Si el productor nombró lotes («la soja continua en La Loma»), lo que cuenta vale solo para esos lotes."""
    from ..archivos import _norm

    if not texto or not seccion:
        return True
    n = f" {_norm(texto)} "
    nombrados = [x for x in secciones if x and f" {_norm(x)} " in n]
    return not nombrados or seccion in nombrados


def _repite_todos_los_anios(rot, cultivos: set[str]) -> bool:
    """La rotación tiene alguno de esos cultivos todos los años (soja continua, maíz sobre maíz)."""
    return bool(rot.anios) and all(inv in cultivos or ver in cultivos for inv, ver in rot.anios)


def ajuste_experiencia(e: dict, rot, experiencia: dict, seccion: str | None = None,
                       secciones: list[str] | None = None) -> None:
    """Lo que el productor contó que le anduvo o le falló: −10 % a las rotaciones con un cultivo que le
    falló, +5 % a las que tienen uno que le anduvo (ajuste propio). Su experiencia vale como dato.

    Si nombra lotes, vale solo para esos lotes; y si lo que falló es repetir el cultivo («soja continua»,
    «monocultivo»), solo marca las rotaciones que lo repiten todos los años. Antes «la soja continua en La Loma» le
    ponía «incluye soja de segunda, que contaste que te falló» a una rotación con soja un año de cada dos en otro lote."""
    from ..archivos import _norm, cultivos_en_texto

    secciones = secciones or []
    cultivos = set(rot.cultivos)
    t_fallo, t_funciono = experiencia.get("que_fallo"), experiencia.get("que_funciono")
    fallo_set = cultivos_en_texto(t_fallo) if _aplica_a_seccion(t_fallo, seccion, secciones) else set()
    if fallo_set and re.search(r" (continu[oa]s?|monocultivo|sobre (soja|maiz|trigo))\b", f" {_norm(t_fallo)} "):
        fallo_set = fallo_set if _repite_todos_los_anios(rot, fallo_set) else set()
    funciono_set = cultivos_en_texto(t_funciono) if _aplica_a_seccion(t_funciono, seccion, secciones) else set()
    fallo = sorted(cultivos & fallo_set)
    funciono = sorted(cultivos & funciono_set - set(fallo))
    nombres = lambda cs: ", ".join(CULTIVOS[c].nombre.split(" (")[0].split(" / ")[0].lower() for c in cs)  # noqa: E731
    if fallo:
        e["puntaje_total"] = round(e["puntaje_total"] * 0.9, 1)
        e["alertas"].append(f"Incluye {nombres(fallo)}, que contaste que te falló: conviene revisar por qué antes de "
                            "repetirlo (¿la chacra, el año, el manejo?).")
    if funciono:
        e["puntaje_total"] = round(min(100.0, e["puntaje_total"] * 1.05), 1)
        e.setdefault("beneficios_extra", []).append(f"Incluye {nombres(funciono)}, que contaste que te anduvo bien.")


def ajuste_riesgo_comercial(e: dict, sistema: dict) -> None:
    """Seguro de seca y venta a futuro: no cambian el puntaje, cambian cómo se lee el riesgo de seca."""
    seca = (e.get("riesgo") or {}).get("seca") or 0
    if seca < 0.3:
        return
    de10 = round(seca * 10)
    if sistema.get("seguro_seca") is False:
        e["alertas"].append(f"Sin seguro de seca: en {de10} de cada 10 años sus cultivos llegan a la floración con falta "
                            "de agua, y un año así se puede llevar el margen de varios.")
    elif sistema.get("seguro_seca"):
        e.setdefault("beneficios_extra", []).append(
            f"Tenés seguro de seca: cubre parte de los {de10} de cada 10 años con falta de agua en floración.")
    if sistema.get("vende_futuro"):
        e["alertas"].append("Vendés a futuro: en un año seco esta rotación puede no llegar a los kilos comprometidos y "
                            "habría que pagar la diferencia. Muchos productores ponen tope a lo que venden antes de cosechar.")


def dentro_de_uruguay(lat: float, lon: float) -> bool:
    """Rectángulo aproximado de Uruguay: alcanza para elegir textos y fuentes, no para límites legales."""
    return -35.1 <= lat <= -30.0 and -58.6 <= lon <= -53.0


def _huecos_seccion(sec: dict, suelo: dict, ndvi: dict, analisis: dict | None, area: float,
                    agua: float, ajustes_agua: list[str], cdl_sec: dict | None = None) -> list[str]:
    h = []
    if not analisis and suelo.get("agua_util_mm"):
        txt = (f"Sin análisis de suelo de esta sección: el agua útil sale de la carta de suelos SSURGO "
               f"({suelo['agua_util_mm']:.0f} mm hasta 80 cm), no de una muestra del campo")
        h.append(txt + (f", {' y '.join(ajustes_agua)}: queda en {agua:.0f} mm." if ajustes_agua else "."))
    elif not analisis:
        txt = f"Sin análisis de suelo de esta sección: el agua útil parte de un valor típico ({suelo_mod.AGUA_UTIL_POR_DEFECTO:.0f} mm)"
        h.append(txt + (f", {' y '.join(ajustes_agua)}: queda en {agua:.0f} mm." if ajustes_agua else "."))
    elif ajustes_agua:
        h.append(f"El agua útil del análisis se {' y '.join(ajustes_agua)}: queda en {agua:.0f} mm.")
    if suelo.get("mundial"):
        h.append(f"Suelo del mapa mundial SoilGrids (250 m): el factor K sale de la textura y el carbono; la tolerancia "
                 f"es un valor típico (7 t/ha/año) porque no hay una oficial para este lugar.")
    elif not suelo.get("ok"):
        # En EE. UU. el suelo es de SSURGO; en otros países, de SoilGrids
        quien = {"UY": "No respondió el servidor del MGAP", "US": "SSURGO no devolvió suelo para este punto"}.get(
            region.pais(*punto_interior(sec["geometria"])), "No hay carta de suelos de este lugar")
        h.append(f"{quien}: K, tolerancia y pendiente son valores típicos.")
    if area < 10:
        h.append(f"Sección de {area:.1f} ha: el píxel de MODIS (6,25 ha) mezcla bordes y vecinos.")
    if not ndvi.get("serie"):
        h.append("Sin serie de NDVI: no se pudo contrastar la rotación actual con el satélite.")
    if not sec.get("historial"):
        if (cdl_sec or {}).get("historial"):
            h.append("El productor no contó qué hizo en esta sección: la rotación actual sale del Cropland Data Layer "
                     "del USDA, que no ve los cultivos de cobertura (el invierno figura como barbecho).")
        else:
            h.append("El productor no contó qué hizo en esta sección: la rotación actual se infirió del satélite.")
    return h


def _actual_desde_ndvi(ndvi: dict) -> rot_mod.Rotacion | None:
    temps = ndvi.get("temporadas") or []
    if not temps:
        return None
    inv = [t for t in temps if t["temporada"].startswith("invierno")]
    ver = [t for t in temps if t["temporada"].startswith("verano")]
    perm = sum("permanente" in t["uso_detectado"] for t in temps) / len(temps)
    if perm >= 0.7:
        return rot_mod.Rotacion("actual", "Rotación actual (vista por satélite)",
                                "El satélite muestra cobertura todo el año: pastura o campo natural.",
                                (("campo_natural", "campo_natural"),), "actual")
    inv_ok = sum(t["ndvi_max"] >= modis.UMBRAL_CULTIVO for t in inv) / max(len(inv), 1)
    ver_ok = sum(t["ndvi_max"] >= modis.UMBRAL_CULTIVO for t in ver) / max(len(ver), 1)
    i = "trigo" if inv_ok >= 0.5 else "barbecho"
    v = ("soja2" if i == "trigo" else "soja") if ver_ok >= 0.5 else "barbecho"
    return rot_mod.Rotacion("actual", "Rotación actual (vista por satélite)",
                            f"Inferida del NDVI: invierno con cultivo {round(inv_ok * 10)} de cada 10 años, "
                            f"verano con cultivo {round(ver_ok * 10)} de cada 10.", ((i, v),), "actual")


def _con_contexto(fn, *args):
    """Corre fn en otro hilo con una copia del contexto del pedido: en Vercel la caché compartida (Runtime Cache)
    vive en contextvars, y un hilo sin la copia cae a la caché en memoria sin avisar (no ve lo ya bajado)."""
    return contextvars.copy_context().run(fn, *args)


def precalentar(campo: dict) -> dict:
    """Baja de antemano lo que el análisis final va a pedir:
    el clima de NASA POWER, el factor R y, por cada sección, el suelo del MGAP y el verdor MODIS (~17 s por
    sección sin caché, que era casi todo el tiempo del análisis). Se llama cuando se confirman las secciones; cuando
    termina la entrevista, el análisis encuentra todo guardado y tarda ~1 s. Los errores se ignoran: el análisis
    vuelve a intentar."""
    t0 = time.perf_counter()
    contorno = campo.get("contorno")
    secciones = campo.get("secciones") or ([{"geometria": contorno}] if contorno else [])
    if not secciones:
        return {"ok": False, "segundos": 0}
    lat, lon = punto_interior(contorno or secciones[0]["geometria"])
    pais = region.pais(lat, lon)
    tareas = [(power.bajar_diario, lat, lon)] + ([(mgap.factor_r, lat, lon)] if pais == "UY" else [])
    for sec in secciones:
        la, lo = punto_interior(sec["geometria"])
        tareas.append((modis.ndvi_punto, la, lo))
        if pais == "UY":
            tareas.append((mgap.suelo_seccion, sec["geometria"], la, lo))
        elif pais == "US":  # Suelo de SSURGO y cultivos de cada año del CDL
            tareas += [(ssurgo.suelo_seccion, sec["geometria"], la, lo), (cdl.por_anio, sec["geometria"])]

    def una(t):
        fn, *args = t
        try:
            fn(*args)
            return True
        except Exception:  # noqa: BLE001
            return False

    with ThreadPoolExecutor(max_workers=min(16, len(tareas))) as ex:
        bien = sum(ex.map(lambda t: _con_contexto(una, t), tareas))
    return {"ok": True, "tareas": len(tareas), "bien": bien, "segundos": round(time.perf_counter() - t0, 1)}


def analizar_campo(campo: dict, progreso: Callable[[str, float], None] | None = None) -> dict:
    eventos = list(analizar_campo_pasos(campo))
    for e in eventos:
        if e["tipo"] == "progreso" and progreso:
            progreso(e["mensaje"], e["avance"])
    return eventos[-1]["resultado"]


def analizar_campo_pasos(campo: dict) -> Iterator[dict]:
    """Generador: va emitiendo {"tipo": "progreso"...} y al final {"tipo": "resultado"...}."""

    def prog(msg, av):
        return {"tipo": "progreso", "mensaje": msg, "avance": av}

    t_inicio_total = time.perf_counter()
    tiempos_secciones: dict[str, dict[str, float]] = {}

    contorno = campo.get("contorno")
    secciones = campo.get("secciones") or []
    if not contorno and not secciones:
        raise ValueError("Falta el contorno del campo.")
    if not secciones:
        secciones = [{"id": "s1", "nombre": "Campo entero", "geometria": contorno}]
    ref = contorno or secciones[0]["geometria"]
    lat, lon = punto_interior(ref)
    total_sec = len(secciones)
    # El suelo y el factor R oficial dependen del país (Uruguay: MGAP; EE. UU.: SSURGO)
    pais = region.pais(lat, lon)
    # Calendario de siembra y año agrícola del hemisferio del campo (cultivos.CULTIVOS lo lee). El
    # generador corre entero en un mismo hilo y contexto (api._sse), así que alcanza con fijarlo acá.
    hemisferio = region.hemisferio(lat)
    HEMISFERIO.set(hemisferio)

    def _bajar_power():
        t0 = time.perf_counter()
        pw = power.bajar_diario(lat, lon)
        return pw, time.perf_counter() - t0

    def _bajar_r():
        t0 = time.perf_counter()
        if pais != "UY":
            # las 19 estaciones del MGAP son de Uruguay: interpolarlas para otro país daba un R sin sentido
            return None, time.perf_counter() - t0
        try:
            r = mgap.factor_r(lat, lon)
        except Exception:  # noqa: BLE001
            r = None
        return r, time.perf_counter() - t0

    def _bajar_ladera():
        # Largo de ladera y pendiente de cada lote con el relieve de SRTM (cualquier país); si no se
        # puede, la erosión sigue con los 100 m típicos
        t0 = time.perf_counter()
        try:
            from . import relieve as relieve_mod
            lad = relieve_mod.ladera_por_seccion(ref, secciones)
        except Exception:  # noqa: BLE001
            lad = {}
        return lad, time.perf_counter() - t0

    def consultar_seccion(sec: dict) -> tuple[dict, dict, dict, float, float, float, dict | None]:
        la, lo = punto_interior(sec["geometria"])
        res: dict[str, tuple[dict, float]] = {}

        def _get_s():
            t0 = time.perf_counter()
            try:
                if pais == "US":
                    # el suelo del lote entero, no el de un punto
                    s = ssurgo.suelo_seccion(sec["geometria"], la, lo)
                elif pais == "UY":
                    s = mgap.suelo_seccion(sec["geometria"], la, lo)
                else:
                    s = {"ok": False, "errores": ["No hay carta de suelos de este país en la app."]}
            except Exception as e:  # noqa: BLE001 — el MGAP se cae seguido; seguimos con valores típicos
                s = {"ok": False, "errores": [str(e)]}
            if not s.get("ok"):
                # fuera de Uruguay (o con el MGAP caído): el mapa mundial de suelos de ISRIC
                try:
                    g = soilgrids.suelo_punto(la, lo)
                except Exception as e:  # noqa: BLE001
                    g = {"ok": False, "errores": [str(e)]}
                if g.get("ok"):
                    s = g
            res["s"] = (s, time.perf_counter() - t0)

        def _get_n():
            t0 = time.perf_counter()
            try:
                n = modis.ndvi_punto(la, lo)
            except Exception as e:  # noqa: BLE001
                n = {"serie": [], "error": str(e)}
            res["n"] = (n, time.perf_counter() - t0)

        def _get_h():
            t0 = time.perf_counter()
            try:
                h = hls_ndvi.consultar_hls_seccion(sec["geometria"])
            except Exception as e:  # noqa: BLE001
                h = {"ok": False, "error": str(e)}
            res["h"] = (h, time.perf_counter() - t0)

        def _get_c():
            # En EE. UU., qué cultivo hubo cada año en la sección (Cropland Data Layer del USDA)
            try:
                d = cdl.por_anio(sec["geometria"])
                res["c"] = {**d, "historial": cdl.historial(sec["geometria"]) if d.get("ok") else []}
            except Exception as e:  # noqa: BLE001
                res["c"] = {"ok": False, "error": str(e), "anios": [], "historial": []}

        hilos = [threading.Thread(target=_con_contexto, args=(f,)) for f in
                 (_get_s, _get_n, _get_h) + ((_get_c,) if pais == "US" else ())]
        for th in hilos:
            th.start()
        for th in hilos:
            th.join()

        s, t_s = res["s"]
        n, t_n = res["n"]
        h, t_h = res.get("h", ({"ok": False, "error": "No ejecutado"}, 0.0))
        if h.get("ok") and n.get("mensual"):
            coinc = hls_ndvi._calcular_coincidencia(h.get("mensual") or [], n.get("mensual"))
            h.update(coinc)
        return s, n, h, t_s, t_n, t_h, res.get("c")

    t0_sec_bloque = time.perf_counter()

    with ThreadPoolExecutor(max_workers=min(32, max(4, 2 + total_sec))) as ex:
        # Disparamos todas las consultas I/O en paralelo al mismo tiempo (t=0):
        # 1. Clima de 35 años de NASA POWER
        # 2. Factor R oficial del MGAP
        # 3. Suelo MGAP y verdor satelital MODIS para cada sección (con sus hilos propios)
        fut_power = ex.submit(_con_contexto, _bajar_power)
        fut_r = ex.submit(_con_contexto, _bajar_r)
        fut_ladera = ex.submit(_con_contexto, _bajar_ladera)
        futuros_sec = {ex.submit(_con_contexto, consultar_seccion, sec): (i, sec) for i, sec in enumerate(secciones)}

        yield prog("Bajando 35 años de clima de NASA POWER y la lluvia de satélite GPM IMERG…", 0.05)
        pw, t_power = fut_power.result()
        serie = clima_mod.preparar(pw)
        # Los riesgos de cada cultivo con los años reales ajustados al clima que proyectan los modelos de
        # la NASA para 2026-2035 (NEX-GDDP-CMIP6, escenario medio); fuera de Uruguay, los años reales tal cual
        cambio = cmip6.cambio(lat, lon)
        serie_riesgo = clima_mod.con_cambio_mensual(serie, cambio) if cambio else serie

        analisis_general = campo.get("analisis_suelo_general")
        agua_general, _ = suelo_mod.agua_util(analisis_general)
        yield prog("Calculando evapotranspiración, balance de agua, heladas y calor por cultivo…", 0.15)
        t0_clima = time.perf_counter()
        clima = clima_mod.analizar(pw, agua_general, cambio=cambio)
        ero = clima["erosividad"]
        t_clima = time.perf_counter() - t0_clima

        yield prog("Consultando el factor R oficial del MGAP…" if pais == "UY"
                   else "Estimando la lluvia erosiva (factor R) con la lluvia diaria de satélite…", 0.22)
        r_of, t_mgap_r = fut_r.result()
        laderas, _t_ladera = fut_ladera.result()
        r_nasa = ero["r_anual"] / 10  # mismas unidades que el MGAP
        r_medido = campo.get("factor_r_medido") if (campo.get("factor_r_medido") or {}).get("r") else None
        if r_of:
            r_usado = r_of["r"]
            cerca = r_of["estaciones"][0]
            r_fuente = (
                f"Factor R {r_usado} del MGAP (estación {cerca['nombre'].title()} a {cerca['km']} km, interpolado). "
                f"Con la lluvia diaria de {serie.fuente_lluvia} se estima {r_nasa:.0f}: "
                f"{'coinciden' if abs(r_nasa / r_usado - 1) < 0.15 else 'difieren'} "
                f"({(r_nasa / r_usado - 1) * 100:+.0f} %)."
            )
        elif r_medido:
            # Un R medido con
            # lluvia de pluviógrafo, cargado junto con el campo. Hoy solo lo traen los terrenos de ejemplo de fuera
            # de Uruguay (scripts/armar_terrenos.py, mapa GloREDa): la fórmula de abajo está ajustada con estaciones
            # de EE. UU. y en climas de lluvia mansa (Alemania, sur de Chile) da varias veces más que lo medido.
            r_usado = float(r_medido["r"])
            r_fuente = (f"Factor R {r_usado:.0f} medido ({r_medido.get('fuente') or 'dato cargado con el campo'}). "
                        f"Con solo la lluvia anual de {serie.fuente_lluvia} la fórmula de Renard y Freimund daría {r_nasa:.0f}.")
        else:
            r_usado = r_nasa
            por_que = "el MGAP no respondió" if pais == "UY" else "el factor R oficial del MGAP es solo de Uruguay"
            r_fuente = f"Factor R {r_usado:.0f} estimado con la lluvia diaria de {serie.fuente_lluvia} ({por_que})."

        riesgos_por_agua: dict[int, dict] = {round(agua_general / 10) * 10: clima["riesgos_cultivo"]}

        def riesgos_para(agua: float) -> dict:
            clave = round(agua / 10) * 10
            if clave not in riesgos_por_agua:
                rr = {}
                for cod, c in CULTIVOS.items():
                    if c.temporada == "barbecho":
                        continue
                    x = clima_mod.riesgos_cultivo(serie_riesgo, c, clave)
                    x.pop("por_anio", None)
                    rr[cod] = x
                riesgos_por_agua[clave] = rr
            return riesgos_por_agua[clave]

        prioridades = {**PRIORIDADES_BASE, **((campo.get("objetivos") or {}).get("prioridades") or {})}
        en_uruguay = dentro_de_uruguay(lat, lon)
        excluidos = set((campo.get("restricciones") or {}).get("cultivos_excluidos") or [])
        sistema = campo.get("sistema") or {}
        hay_ganado = bool(sistema.get("ganado")) or sistema.get("tipo") in ("ganadero", "mixto")
        vende_forraje = bool(sistema.get("vende_forraje"))
        if not hay_ganado and "forraje" not in ((campo.get("objetivos") or {}).get("prioridades") or {}):
            prioridades["forraje"] = 0
        margenes = campo.get("margenes") or {}
        temporadas = etiquetas_temporadas(HORIZONTE_ANIOS, hemisferio=hemisferio)

        nombres_secciones = [x.get("nombre") for x in campo.get("secciones") or [] if x.get("nombre")]

        def evaluar_una_seccion(sec: dict, suelo: dict, ndvi: dict, hls: dict | None = None,
                                cdl_sec: dict | None = None) -> tuple[dict, dict | None]:
            area = area_ha(sec["geometria"])
            analisis = sec.get("analisis_suelo") or analisis_general
            agua, agua_origen = suelo_mod.agua_util(analisis)
            if not analisis and suelo.get("ok") and suelo.get("agua_util_mm"):
                # En EE. UU. la carta de suelos (SSURGO) da el agua disponible de cada horizonte
                agua = float(suelo["agua_util_mm"])
                agua_origen = f"carta de suelos SSURGO ({suelo.get('suelo_dominante')}, hasta 80 cm)"
            problemas = list(sec.get("problemas") or [])
            estacion = campo.get("estacion") or {}
            # una estación de referencia lejana no dice si el campo es más helador
            if ((estacion.get("comparacion") or {}).get("campo_mas_helador") and not estacion.get("referencia")
                    and "helada" not in problemas):
                problemas.append("helada")  # la estación del productor registró más heladas que NASA POWER
            ajustes_agua = []
            if "suelo_superficial" in problemas:
                agua *= 0.7
                ajustes_agua.append("bajado 30 % porque el productor marcó suelo superficial")
            if "sequia" in problemas:
                agua *= 0.8
                ajustes_agua.append("bajado 20 % porque el productor dice que se seca rápido")
            if ajustes_agua:
                agua_origen = f"{agua_origen}; {', '.join(ajustes_agua)} → {agua:.0f} mm"
            ctx = {
                "suelo": suelo if suelo.get("ok") else {},
                "r_factor": r_usado,
                "r_fuente": r_fuente,
                "reparto_erosivo": ero["reparto_mensual"],
                "riesgos": riesgos_para(agua),
                "problemas": problemas,
                "margenes": margenes,
                "detalle_margenes": campo.get("detalle_margenes") or {},
                "renta_kg": sistema.get("renta_kg") if sistema.get("tenencia") == "arrendado" else None,
                **_largo_de(sec, campo, laderas.get(sec.get("id")) or {}),
                "practica_p": rot_mod.p_curvas((suelo or {}).get("pendiente_pct")) if sec.get("curvas_de_nivel") or campo.get("curvas_de_nivel") else 1.0,
                "ndvi": ndvi,
                "analisis_suelo": analisis,
                "clima_info": {"meses_pico": ero["meses_pico"], "periodo": clima["periodo"],
                               "tendencia": clima["tendencia"], "fuente_lluvia": clima.get("fuente_lluvia"),
                               "futuro": clima.get("clima_futuro")},
                "huecos": _huecos_seccion(sec, suelo, ndvi, analisis, area, agua, ajustes_agua, cdl_sec),
                "punto": (lat, lon),  # para GAEZ (celda de ~9 km: alcanza el centro del campo)
            }
            actual_rot = rot_mod.rotacion_desde_historial(sec.get("historial") or [])
            if not actual_rot and (cdl_sec or {}).get("historial"):
                # EE. UU., lo que muestra el Cropland Data Layer de los últimos años
                actual_rot = rot_mod.rotacion_desde_historial(cdl_sec["historial"])
                anios_cdl = [x["anio"] for x in cdl_sec["historial"]]
                actual_rot = rot_mod.Rotacion(
                    actual_rot.id, "Rotación actual (Cropland Data Layer del USDA)",
                    actual_rot.descripcion.replace("Lo que se hizo en los últimos años",
                                                   f"Lo que muestra el CDL de {anios_cdl[0]} a {anios_cdl[-1]}"),
                    actual_rot.anios, actual_rot.tipo)
            actual_rot = actual_rot or _actual_desde_ndvi(ndvi)
            candidatas = []
            for r in rot_mod.ROTACIONES.values():
                if excluidos & set(r.cultivos):
                    continue
                if r.id in rot_mod.SOLO_FUERA_DE_URUGUAY and en_uruguay:
                    continue
                if r.id in CON_GANADO and not hay_ganado and (r.id == "campo_natural" or not vende_forraje):
                    continue  # el campo natural solo se aprovecha con animales
                if r.id == "alfalfa_maiz" and ("anegamiento" in problemas or (analisis and analisis.get("ph") and float(analisis["ph"]) < 5.8)):
                    continue
                candidatas.append(r)
            # (escala por lote): primero se evalúan todas las opciones del lote y después se pondera, porque
            # cada criterio se mide entre la peor y la mejor de ellas (`rotaciones.escala_lote`)
            evs = []
            actual_ev = None
            rot_de: dict[int, object] = {}  # id(ev) → rotación, para los ajustes
            sin_ganado: set[int] = set()  # opciones con pastura en un campo sin ganado propio (×0,9)
            if actual_rot:
                actual_ev = rot_mod.evaluar(actual_rot, ctx)
                actual_ev["es_actual"] = True
                rot_de[id(actual_ev)] = actual_rot
                # Si lo de hoy tiene un cultivo que el productor ya no quiere, se sigue mostrando para
                # comparar, pero no puede salir como sugerida
                no_quiere = [c for c in actual_rot.cultivos if c in excluidos]
                if no_quiere:
                    actual_ev["tiene_excluidos"] = True
                    actual_ev["alertas"].append(
                        f"Tiene {_lista_cultivos(no_quiere)}, que marcaste que no querés: se muestra para comparar, no se sugiere.")
            for r in candidatas:
                if actual_rot and r.anios == actual_rot.anios:
                    continue
                e = rot_mod.evaluar(r, ctx)
                rot_de[id(e)] = r
                if not hay_ganado and r.tipo != "agrícola" and e["forraje"] > 0.3:
                    if vende_forraje:
                        e["alertas"].append("El forraje se vende: el ingreso depende de tener comprador para los fardos o el pastoreo.")
                    else:
                        e["alertas"].append("Necesita ganado propio o arrendar el pastoreo para aprovechar la pastura.")
                        sin_ganado.add(id(e))
                evs.append(e)
                # Si una rotación con cultivos se pasa de lo que aguanta el suelo pero sembrando en
                # curvas de nivel entra, se ofrece también así (antes solo contaba si el productor ya las hacía, y
                # en suelos con pendiente siempre ganaba la pradera sola)
                pend_sec = (ctx["suelo"] or {}).get("pendiente_pct")
                if (ctx["practica_p"] == 1.0 and not e["erosion"]["cumple"] and r.tipo != "ganadera"
                        and pend_sec is not None and 1 <= pend_sec <= 20):
                    e2 = rot_mod.evaluar(r, {**ctx, "practica_p": rot_mod.p_curvas(pend_sec)})
                    if e2["erosion"]["cumple"]:
                        e2["id"] = f"{r.id}_curvas"
                        e2["nombre"] = f"{r.nombre}, en curvas de nivel"
                        e2["descripcion"] = (f"{r.descripcion} Sembrando en curvas de nivel (o con terrazas) el agua "
                                             "corre más despacio y arrastra menos suelo.")
                        e2["practica"] = "curvas"
                        e2["alertas"].append("Hay que sembrar siguiendo las curvas de nivel (o armar terrazas): más "
                                             "trabajo de máquina, pero la erosión baja a la mitad o menos.")
                        e2["puntajes"]["simplicidad"] = max(0, e2["puntajes"]["simplicidad"] - 15)
                        rot_de[id(e2)] = r
                        evs.append(e2)
            todas_lote = ([actual_ev] if actual_ev else []) + evs
            escala = rot_mod.escala_lote(todas_lote) if todas_lote else None
            for e in todas_lote:
                r = rot_de[id(e)]
                e["puntaje_total"] = rot_mod.ponderar(e, prioridades, escala)
                if id(e) in sin_ganado:
                    e["puntaje_total"] = round(e["puntaje_total"] * 0.9, 1)
                ajuste_tenencia(e, r, sistema, vende_forraje)
                ajuste_riesgo_comercial(e, sistema)
                ajuste_experiencia(e, r, campo.get("experiencia") or {}, sec.get("nombre"), nombres_secciones)
            evs.sort(key=orden)
            top, nota_tol = elegir_variadas(evs, 3)
            comparadas = ([actual_ev] if actual_ev else []) + top
            for e in comparadas:
                e["explicacion"] = rot_mod.explicar(e, ctx, actual_ev)
                e["erosion"]["rango"] = incertidumbre.rango_erosion(
                    e["erosion"], [] if r_medido and not r_of else [r_of["r"] if r_of else None, r_nasa])
            recomendada, acept = recomendar(actual_ev, top, prioridades, escala, str(sec.get("id") or sec.get("nombre")))
            res_sec = {
                "id": sec.get("id"),
                "nombre": sec.get("nombre"),
                "area_ha": round(area, 1),
                "punto": punto_interior(sec["geometria"]),
                "suelo": suelo,
                "ndvi": {**{k: ndvi.get(k) for k in ("fuente", "mensual", "temporadas", "descubierto_por_anio", "umbrales", "error")},
                         "metodos": descubierto.comparar(ndvi.get("mensual") or []),
                         "hls": hls if (hls and hls.get("ok")) else (hls or {})},
                "agua_util_mm": round(agua),
                "agua_util_origen": agua_origen,
                "cdl": ({k: cdl_sec.get(k) for k in ("ok", "fuente", "anios", "error")} if cdl_sec else None),
                "analisis_suelo": suelo_mod.interpretar(analisis),
                "problemas": problemas,
                "actual": actual_ev,
                "alternativas": top,
                "nota_tolerancia": nota_tol,
                # También la seca, para la tabla de todas las rotaciones de Comparar (antes mostraba
                # solo la erosión y parecía que era lo único que contaba)
                "todas": [{"id": e["id"], "nombre": e["nombre"], "puntaje_total": e["puntaje_total"],
                           "puntajes": e["puntajes"], "erosion": e["erosion"],
                           "riesgo": {"seca": e["riesgo"]["seca"]}} for e in evs],
                "recomendada_id": recomendada["id"] if recomendada else None,
                # en cuántos de cada 100 juegos de pesos parecidos sale primera cada opción que podía recomendarse
                "aceptabilidad": acept,
                "escala_lote": {d: [round(a, 1), round(a + r, 1)] for d, (a, r) in escala.items()} if escala else None,
            }
            return res_sec, recomendada

        msg_suelo = {"UY": "grupo CONEAT y factor K de suelo en MGAP", "US": "suelo y factor K en SSURGO (USDA)"}.get(
            pais, "verdor de satélite")
        yield prog(f"Consultando {msg_suelo} ({total_sec} secciones)…", 0.30)
        resultados_sec: list[dict | None] = [None] * total_sec
        completadas = 0

        for fut in as_completed(futuros_sec):
            i, sec = futuros_sec[fut]
            suelo, ndvi, hls, t_s, t_n, t_h, cdl_sec = fut.result()
            t0_ev = time.perf_counter()
            res_sec, rec = evaluar_una_seccion(sec, suelo, ndvi, hls, cdl_sec)
            t_rot = time.perf_counter() - t0_ev
            resultados_sec[i] = res_sec
            sec_id = str(sec.get("id") or i + 1)
            tiempos_secciones[sec_id] = {
                "suelo": t_s,
                "ndvi": t_n,
                "hls": t_h,
                "rotaciones": t_rot,
            }
            completadas += 1
            avance = 0.35 + (completadas / total_sec) * 0.50

            nom_sec = sec.get("nombre") or f"Sección {sec_id}"
            if suelo.get("ok") and suelo.get("grupo_coneat"):
                k_val = suelo.get("factor_k")
                k_str = f", K {k_val}" if k_val is not None else ""
                suelo_txt = f"suelo CONEAT {suelo['grupo_coneat']}{k_str}"
            elif suelo.get("ok") and suelo.get("pais") == "US":
                k_val = suelo.get("factor_k")
                suelo_txt = f"suelo {suelo.get('suelo_dominante')} (SSURGO){f', K {k_val}' if k_val is not None else ''}"
            elif suelo.get("ok") and suelo.get("factor_k") is not None:
                suelo_txt = f"suelo K {suelo['factor_k']}"
            else:
                suelo_txt = "suelo típico"

            temps = ndvi.get("temporadas") or []
            max_ndvi = max((t.get("ndvi_max") or 0 for t in temps), default=0)
            if max_ndvi > 0:
                sat_txt = f"NDVI máx {max_ndvi:.2f}"
            elif ndvi.get("serie"):
                max_s = max((p.get("ndvi") or 0 for p in ndvi["serie"]), default=0)
                sat_txt = f"NDVI máx {max_s:.2f}" if max_s > 0 else "satélite consultado"
            else:
                sat_txt = "satélite consultado"

            if rec:
                rec_txt = f"recomendada «{rec['nombre']}» ({round(rec['puntaje_total'])} pts)"
            else:
                rec_txt = "evaluación completa"

            msg = f"{nom_sec}: {suelo_txt}, {sat_txt} → {rec_txt}"
            yield prog(msg, round(avance, 2))

        t_secciones_total = time.perf_counter() - t0_sec_bloque

    yield prog("Evaluando balance hídrico, riesgo de heladas y erosión USLE…", 0.88)
    yield prog("Optimizando rotaciones para cumplir la tolerancia del suelo y tus prioridades…", 0.94)
    yield prog("Armando el plan por sección y temporada…", 0.98)
    t0_plan = time.perf_counter()
    plan = armar_plan([r for r in resultados_sec if r is not None], temporadas, campo)
    t_plan = time.perf_counter() - t0_plan
    t_total = time.perf_counter() - t_inicio_total

    print(
        f"[CRONÓMETRO ANÁLISIS] Total: {t_total:.2f} s | NASA POWER: {t_power:.2f} s | "
        f"Clima: {t_clima:.2f} s | MGAP Factor R: {t_mgap_r:.2f} s | "
        f"Secciones ({total_sec}): {t_secciones_total:.2f} s | Plan: {t_plan:.2f} s",
        flush=True,
    )
    for s_id, t_inf in tiempos_secciones.items():
        t_s_tot = t_inf["suelo"] + t_inf["ndvi"] + t_inf.get("hls", 0.0) + t_inf["rotaciones"]
        print(
            f"  - Sección {s_id}: Total {t_s_tot:.2f} s (Suelo MGAP: {t_inf['suelo']:.2f} s | "
            f"MODIS NDVI: {t_inf['ndvi']:.2f} s | HLS 30m: {t_inf.get('hls', 0.0):.2f} s | Rotaciones: {t_inf['rotaciones']:.2f} s)",
            flush=True,
        )

    fuentes_lista = [
        *([{"nombre": "NASA GPM IMERG V07 (diario, 0,1°) vía Giovanni (GES DISC)", "url": "https://gpm.nasa.gov/data/imerg",
             "uso": "lluvia desde junio de 2000: balance de agua, seca, erosividad"}] if serie.fuente_lluvia == "GPM IMERG" else []),
        {"nombre": "NASA POWER (diario, AG)", "url": "https://power.larc.nasa.gov",
         "uso": ("temperatura, radiación, humedad y viento (ET0), helada, calor; lluvia antes de 2000"
                 if serie.fuente_lluvia == "GPM IMERG" else "clima, ET0, balance de agua, helada, calor, erosividad")},
        {"nombre": "NASA MODIS MOD13Q1 v061 vía ORNL DAAC", "url": "https://modis.ornl.gov/rst/api/v1/", "uso": "cobertura del suelo por sección (NDVI)"},
    ]
    if r_medido and not r_of:
        fuentes_lista.append({
            "nombre": "GloREDa 1.2 (JRC, Comisión Europea): lluvia erosiva medida en 3939 estaciones, mapa de ~1 km",
            "url": "https://doi.org/10.5281/zenodo.8036998",
            "uso": "factor R de la ecuación de erosión",
        })
    if any((s.get("ndvi") or {}).get("hls", {}).get("ok") for s in resultados_sec if s):
        fuentes_lista.append({
            "nombre": "NASA HLS v002 (Landsat 8-9 + Sentinel-2, 30 m) vía Google Earth Engine",
            "url": "https://hls.gsfc.nasa.gov/",
            "uso": "verdor y NDVI mensual por polígono a escala de chacra",
        })
    fuentes_lista.extend([
        {"nombre": "NASA GLDAS 2.1 Noah (0,25°) vía Google Earth Engine", "url": "https://ldas.gsfc.nasa.gov/gldas", "uso": "humedad de suelo por capas y contraste en secas históricas (2000-hoy)"},
        {"nombre": "NASA ECOSTRESS (ISS, 70 m) vía LP DAAC / Earth Engine", "url": "https://ecostress.jpl.nasa.gov/", "uso": "temperatura adentro del potrero a 70 m en días puntuales (por ahora, solo en el campo de ejemplo)"},
        {"nombre": "FAO/IIASA GAEZ v4 (res05, ~9 km)", "url": "https://gaez.fao.org/", "uso": "aptitud de cada cultivo de secano en la zona del campo (celda de ~9 km), con el clima de 2011-2040 (5 modelos), en las tarjetas de las rotaciones"},
        {"nombre": "MGAP-DGRN (CONEAT, factor K, tolerancia, pendiente, factor R, padrones)", "url": "https://dgrn.mgap.gub.uy/arcgis/rest/services", "uso": "suelo y ecuación de erosión del Plan de Uso"},
        {"nombre": "INUMET, estaciones por hora (datos abiertos)", "url": "https://catalogodatos.gub.uy/dataset/inumet-observaciones-meteorologicas-temperatura-del-aire-en-el-uruguay", "uso": "corrección de la temperatura de NASA POWER, mes a mes con 7 estaciones"},
        {"nombre": "NASA NEX-GDDP-CMIP6 (30 modelos, 25 km) vía Google Earth Engine", "url": "https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6", "uso": "cambio de temperatura y lluvia proyectado para 2026-2035 en la celda del campo"},
        {"nombre": "FAO-56 (Allen et al. 1998)", "url": "https://www.fao.org/3/x0490e/x0490e00.htm", "uso": "ET0 y coeficientes de cultivo"},
    ])

    yield {
        "tipo": "resultado",
        "resultado": {
            "generado": dt.datetime.now().isoformat(timespec="seconds"),
            "centro": {"lat": lat, "lon": lon},
            "cronometro_s": {
                "total": round(t_total, 2),
                "nasa_power": round(t_power, 2),
                "clima": round(t_clima, 2),
                "mgap_factor_r": round(t_mgap_r, 2),
                "secciones_total": round(t_secciones_total, 2),
                "armado_plan": round(t_plan, 2),
                "detalle_secciones": {
                    s_id: {
                        "suelo": round(t_inf["suelo"], 2),
                        "ndvi": round(t_inf["ndvi"], 2),
                        "hls": round(t_inf.get("hls", 0.0), 2),
                        "rotaciones": round(t_inf["rotaciones"], 2),
                        "total": round(t_inf["suelo"] + t_inf["ndvi"] + t_inf.get("hls", 0.0) + t_inf["rotaciones"], 2),
                    }
                    for s_id, t_inf in tiempos_secciones.items()
                },
            },
            "clima": clima,
            "factor_r": {"usado": r_usado, "mgap": r_of, "nasa": round(r_nasa), "fuente": r_fuente,
                         "medido": r_medido if not r_of else None},
            "secciones": resultados_sec,
            "plan": plan,
            "prioridades": prioridades,
            "fuentes": fuentes_lista,
        },
    }


# cultivos de cosecha: un año de la rotación cuenta como agrícola si tiene alguno (igual que la pantalla del Plan)
GRANOS = {"soja", "soja2", "maiz", "maiz2", "sorgo", "girasol", "trigo", "cebada", "colza"}


def fraccion_agricola(e: dict) -> float:
    """Parte de los años de la rotación con algún cultivo de cosecha (0 a 1). Alfalfa 3 años → maíz → trigo / soja 2ª
    es 2 de 5: antes contaba entera como ganadera y en un campo mixto la sugerida no tenía opción con agricultura."""
    anios = e.get("anios")
    if not anios:
        return 1.0 if e.get("tipo") == "agrícola" else 0.0
    return sum(1 for inv, ver in anios if inv in GRANOS or ver in GRANOS) / len(anios)


def _equilibrio(secciones: list[dict], campo: dict) -> tuple[dict[str, str], dict | None]:
    """Si el productor quiere un campo mixto, reparte la superficie entre agricultura y ganadería para las sugeridas.

    Meta: `objetivos.pct_agricola` (0-100); si no la dio y el sistema es mixto, 50 %. En cada sección compiten la
    mejor opción con agricultura que cumple lo que aguanta el suelo y la mejor sin agricultura; quedan con
    agricultura las secciones donde pierde menos puntos, contando la parte agrícola de cada rotación, hasta la meta.
    Devuelve también cuánto agrícola queda con las sugeridas y, si no se llega a la meta, por qué.
    """
    objetivos = campo.get("objetivos") or {}
    meta = objetivos.get("pct_agricola")
    tipo = (campo.get("sistema") or {}).get("tipo")
    if meta is None and tipo == "mixto":
        meta = 50
    # solo para campos mixtos: en uno agrícola (la tarjeta guarda 100 %) o ganadero (0 %) cada sección
    # se queda con su mejor opción; si no, una rotación actual con pradera se tomaba por "ganadera"
    if meta is None or (tipo and tipo != "mixto") or not 0 < float(meta) < 100:
        return {}, None
    meta = float(meta)
    total = sum(s["area_ha"] for s in secciones) or 1
    opciones = []
    for s in secciones:
        # la rotación actual también compite: si ya anda bien y cumple la tolerancia, puede quedarse
        actual_ok = s["actual"] and s["actual"].get("erosion", {}).get("cumple", True) and not s["actual"].get("tiene_excluidos")
        evs = sorted([e for e in ([s["actual"]] if actual_ok else []) + s["alternativas"] if e],
                     key=lambda e: -e["puntaje_total"])
        agr = next((e for e in evs if fraccion_agricola(e) > 0 and e["erosion"].get("ratio", 0) <= 1.0), None)
        # También la ganadera tiene que cumplir; ahora las alternativas pueden traer opciones que no
        # cumplen (para mostrar al menos tres estrategias) y una de esas no puede salir como sugerida
        gan = next((e for e in evs if fraccion_agricola(e) == 0 and e["erosion"].get("ratio", 0) <= 1.0), None)
        if agr and gan:
            opciones.append((agr["puntaje_total"] - gan["puntaje_total"], s, agr, gan))
    opciones.sort(key=lambda x: -x[0])
    asignado, area_agr = {}, 0.0
    for delta, s, agr, gan in opciones:
        suma = fraccion_agricola(agr) * s["area_ha"]
        if 100 * (area_agr + suma / 2) / total <= meta:
            asignado[s["id"]] = agr["id"]
            area_agr += suma
        else:
            asignado[s["id"]] = gan["id"]
    # las secciones que no entraron en el reparto aportan lo de su recomendada
    for s in secciones:
        if s["id"] in asignado:
            continue
        rec = next((e for e in ([s["actual"]] if s["actual"] else []) + s["alternativas"]
                    if e and e["id"] == s.get("recomendada_id")), None)
        if rec:
            area_agr += fraccion_agricola(rec) * s["area_ha"]
    pct = 100 * area_agr / total
    nota = None
    if pct < meta - 10:
        nota = (f"Con lo que aguanta el suelo de cada lote, las sugeridas llegan a {pct:.0f} % agrícola y no al "
                f"{meta:.0f} % que marcaste: más agricultura se pasaría de la tolerancia en algún lote.")
    return asignado, {"meta": round(meta), "pct_sugerido": round(pct), "nota": nota}


def _equilibrar(secciones: list[dict], campo: dict) -> dict[str, str]:
    return _equilibrio(secciones, campo)[0]


def _lista_cultivos(codigos: list[str]) -> str:
    """«soja de primera y soja de segunda»."""
    ns = list(dict.fromkeys(CULTIVOS[c].nombre.split(" (")[0].lower() for c in codigos if c in CULTIVOS))
    return ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " y " + ns[-1]


def _evaluacion(sec: dict, rid: str | None) -> dict | None:
    return next((e for e in ([sec["actual"]] if sec["actual"] else []) + sec["alternativas"] if e and e["id"] == rid), None)


def _largo_de(sec: dict, campo: dict, ladera: dict) -> dict:
    """El largo de ladera del lote: el que cargó el productor, si no el del relieve (SRTM), si no 100 m."""
    propio = sec.get("largo_pendiente_m") or campo.get("largo_pendiente_m")
    if propio:
        largo, origen = propio, "productor"
    elif ladera.get("largo_m"):
        largo, origen = ladera["largo_m"], "srtm"
    else:
        largo, origen = 100, "fijo"
    return {"largo_pendiente_m": largo, "largo_origen": origen, "pendiente_srtm": ladera.get("pendiente_media")}


def armar_plan(secciones: list[dict], temporadas: list[dict], campo: dict) -> dict:
    """Arma el plan temporada por temporada con la rotación que eligió el productor en cada sección. Arrancaba en lo de hoy; una sección sin elección arranca en la sugerida (equilibrio agrícola-ganadero si
    corresponde, o la mejor según sus prioridades). La sugerida va también en `sugerida_id`, y lo de hoy se elige
    con «actual»: el productor sigue decidiendo lote por lote.
    """
    reparto, equilibrio = _equilibrio(secciones, campo)
    sugeridas = {**{s["id"]: s["recomendada_id"] for s in secciones}, **reparto}
    elegidas = campo.get("rotacion_elegida") or {}
    asignadas = []
    ocupacion: list[dict[str, float]] = [dict() for _ in temporadas]
    for sec in sorted(secciones, key=lambda s: -s["area_ha"]):
        sug = sugeridas.get(sec["id"]) or sec["recomendada_id"]
        rid = elegidas.get(sec["id"]) or sug
        ev = _evaluacion(sec, rid)
        if ev is None:
            ev = next((e for e in sec["alternativas"]), sec["actual"])
        if ev is None:
            continue
        rot = rot_mod.Rotacion(ev["id"], ev["nombre"], ev["descripcion"], tuple(tuple(p) for p in ev["anios"]), ev["tipo"])
        ultimo_verano = None
        if sec["actual"]:
            ultimo_verano = sec["actual"]["anios"][-1][1]
        mejor, mejor_costo = 0, None
        for fase in range(len(rot.anios)):
            sec_cult = secuencia(rot, fase, temporadas)
            costo = sum((ocupacion[i].get(c, 0) + sec["area_ha"]) ** 2 - ocupacion[i].get(c, 0) ** 2
                        for i, c in enumerate(sec_cult))
            if ultimo_verano and sec_cult and sec_cult[0] == ultimo_verano and ultimo_verano in ("soja", "soja2"):
                costo *= 1.5
            if mejor_costo is None or costo < mejor_costo:
                mejor, mejor_costo = fase, costo
        cultivos_sec = secuencia(rot, mejor, temporadas)
        for i, c in enumerate(cultivos_sec):
            ocupacion[i][c] = ocupacion[i].get(c, 0) + sec["area_ha"]
        nombre_rot = "Seguir como hasta ahora" if rot.id == "actual" else rot.nombre
        siembras, proxima = siembras_pastura(rot, mejor, temporadas)
        ev_sug = _evaluacion(sec, sug)
        asignadas.append({"seccion_id": sec["id"], "seccion": sec["nombre"], "area_ha": sec["area_ha"],
                          "rotacion_id": rot.id, "rotacion": nombre_rot, "fase": mejor,
                          "cultivos": cultivos_sec, "siembras": siembras, "proxima_siembra": proxima,
                          "sugerida_id": ev_sug["id"] if ev_sug else None,
                          "sugerida": ("Seguir como hasta ahora" if ev_sug["id"] == "actual" else ev_sug["nombre"]) if ev_sug else None,
                          "elegida": sec["id"] in elegidas})

    total = sum(s["area_ha"] for s in secciones) or 1
    resumen = []
    for i, t in enumerate(temporadas):
        oc = ocupacion[i]
        cubierto = sum(a for c, a in oc.items() if c != "barbecho")
        forr = sum(a * CULTIVOS[c].forraje for c, a in oc.items())
        resumen.append({
            **t,
            "area_por_cultivo": {c: round(a, 1) for c, a in sorted(oc.items(), key=lambda x: -x[1])},
            "pct_cubierto": round(100 * cubierto / total),
            "ha_forraje": round(forr, 1),
        })
    erosion_media = sum(
        next((e["erosion"]["a_t_ha"] for e in ([s["actual"]] if s["actual"] else []) + s["alternativas"]
              if e and e["id"] == a["rotacion_id"]), 0) * a["area_ha"]
        for s in secciones for a in asignadas if a["seccion_id"] == s["id"]
    ) / total
    erosion_actual = sum((s["actual"]["erosion"]["a_t_ha"] if s["actual"] else 0) * s["area_ha"] for s in secciones) / total
    erosion_sugerida = sum(
        ((_evaluacion(s, a["sugerida_id"]) or {}).get("erosion", {}).get("a_t_ha", 0)) * a["area_ha"]
        for s in secciones for a in asignadas if a["seccion_id"] == s["id"]
    ) / total
    return {
        "temporadas": temporadas,
        "secciones": asignadas,
        "resumen_temporadas": resumen,
        "erosion_media_plan": round(erosion_media, 2),
        "erosion_media_actual": round(erosion_actual, 2),
        "erosion_media_sugerida": round(erosion_sugerida, 2),
        "equilibrio": equilibrio,
    }
