"""Interpretación del análisis de suelo que sube el productor.

- Agua útil (mm) desde la textura: valores típicos por clase textural (mm de agua útil por metro
  de suelo), aproximados de tablas de uso común (USDA / FAO-56 tabla 19). A validar con INIA.
- Umbrales de pH, materia orgánica, fósforo (Bray I) y potasio: referencias aproximadas de uso
  común en Uruguay, a confirmar con un agrónomo. Se muestran como "referencia", no como
  recomendación de fertilización.
"""

from __future__ import annotations

AGUA_UTIL_MM_POR_M = {
    "arenoso": 70,
    "arenoso franco": 90,
    "franco arenoso": 120,
    "franco": 160,
    "franco limoso": 190,
    "franco arcillo arenoso": 140,
    "franco arcilloso": 170,
    "franco arcillo limoso": 175,
    "arcillo arenoso": 130,
    "arcillo limoso": 160,
    "arcilloso": 150,
}
PROFUNDIDAD_RAICES_M = 0.8
AGUA_UTIL_POR_DEFECTO = 120.0


def clase_textural(arena: float, limo: float, arcilla: float) -> str:
    """Triángulo textural USDA, simplificado a las 11 clases de la tabla."""
    s = arena + limo + arcilla
    if s <= 0:
        return "franco"
    arena, limo, arcilla = (100 * x / s for x in (arena, limo, arcilla))
    if arcilla >= 40:
        if limo >= 40:
            return "arcillo limoso"
        if arena >= 45:
            return "arcillo arenoso"
        return "arcilloso"
    if arcilla >= 27:
        if arena <= 20:
            return "franco arcillo limoso"
        if arena >= 45:
            return "franco arcillo arenoso"
        return "franco arcilloso"
    if arcilla >= 20 and arena >= 45:
        return "franco arcillo arenoso"
    if arena >= 85:
        return "arenoso"
    if arena >= 70:
        return "arenoso franco"
    if arena >= 52:
        return "franco arenoso"
    if limo >= 50:
        return "franco limoso"
    return "franco"


def agua_util(analisis: dict | None) -> tuple[float, str]:
    """Agua útil de la zona de raíces (mm) y de dónde salió."""
    if not analisis:
        return AGUA_UTIL_POR_DEFECTO, "valor típico (120 mm) porque no hay análisis de suelo"
    if analisis.get("agua_util_mm"):
        return float(analisis["agua_util_mm"]), "dato del productor"
    clase = analisis.get("textura")
    a, l, c = (analisis.get(k) for k in ("arena", "limo", "arcilla"))
    if None not in (a, l, c):
        clase = clase_textural(float(a), float(l), float(c))
    if clase and clase.lower() in AGUA_UTIL_MM_POR_M:
        mm = AGUA_UTIL_MM_POR_M[clase.lower()] * PROFUNDIDAD_RAICES_M
        mo = analisis.get("materia_organica")
        if mo:
            mm *= 1 + min(max(float(mo) - 2.5, 0), 3) * 0.03  # +3 % por cada punto de MO sobre 2,5
        return round(mm), f"textura {clase} del análisis ({PROFUNDIDAD_RAICES_M} m de raíces)"
    return AGUA_UTIL_POR_DEFECTO, "valor típico (120 mm): el análisis no trae textura"


def interpretar(analisis: dict | None) -> dict:
    if not analisis:
        return {"hay_analisis": False, "notas": [], "alertas": []}
    notas, alertas = [], []
    ph = analisis.get("ph")
    if ph is not None:
        ph = float(ph)
        if ph < 5.5:
            alertas.append(f"pH {ph:.1f}: suelo ácido. La alfalfa y el trébol rinden mal; evaluar encalado.")
        elif ph < 6.0:
            notas.append(f"pH {ph:.1f}: algo ácido; la alfalfa pide 6 o más.")
        else:
            notas.append(f"pH {ph:.1f}: sin limitaciones para los cultivos de la zona.")
    mo = analisis.get("materia_organica")
    if mo is not None:
        mo = float(mo)
        if mo < 2.5:
            alertas.append(f"Materia orgánica {mo:.1f} %: baja. Prioriza rotaciones con pasturas o mucho rastrojo.")
        elif mo < 3.5:
            notas.append(f"Materia orgánica {mo:.1f} %: media; la agricultura continua la va a bajar.")
        else:
            notas.append(f"Materia orgánica {mo:.1f} %: buena.")
    p = analisis.get("fosforo_bray")
    if p is not None:
        p = float(p)
        if p < 12:
            alertas.append(f"Fósforo Bray I {p:.0f} ppm: bajo para soja y trigo (referencia ~12-16 ppm).")
        else:
            notas.append(f"Fósforo Bray I {p:.0f} ppm: suficiente para la mayoría de los cultivos.")
    k = analisis.get("potasio")
    if k is not None:
        k = float(k)
        if k < 0.3:
            alertas.append(f"Potasio {k:.2f} meq/100 g: bajo (referencia ~0,3-0,35 para soja).")
        else:
            notas.append(f"Potasio {k:.2f} meq/100 g: adecuado.")
    mm, origen = agua_util(analisis)
    notas.append(f"Agua útil estimada: {mm:.0f} mm ({origen}).")
    return {"hay_analisis": True, "notas": notas, "alertas": alertas, "agua_util_mm": mm,
            "ph": analisis.get("ph"), "materia_organica": analisis.get("materia_organica")}
