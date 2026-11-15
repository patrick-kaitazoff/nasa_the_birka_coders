"""
Fuente de datos ECOSTRESS (NASA / ISS, 70 m).

ECOSTRESS (ECOsystem Spaceborne Thermal Radiometer Experiment on Space Station)
mide la temperatura de superficie terrestre (LST), evapotranspiración (ET) y
estrés evaporativo (ESI) a 70 m de resolución espacial.

Por qué se usa:
Es la única fuente satelital de la lista oficial de la NASA capaz de resolver
la heterogeneidad térmica y el estrés hídrico adentro del potrero (a 70 m).

Límites analizados:
1. Órbita de la ISS: no es heliosincrónica (precesa), por lo que la hora local
   de pasada varía continuamente y muchas observaciones ocurren de noche o madrugada.
2. Nubosidad en Uruguay: en los últimos 2 años (2024-2026), de 181 pasadas orbitales
   sobre el campo de ejemplo (-33.1, -56.15), solo 52 tuvieron datos útiles libres
   de nubes (28,7%). El 71% restante quedó tapado por nubosidad o fuera de cuadro.
3. Cobertura de productos:
   - Los productos históricos ALEXI / dis-ALEXI solo cubren Estados Unidos (CONUS).
   - El índice de estrés PT-JPL global (ECO_L4T_ESI, 70 m) cubre Uruguay pero no
     está en el catálogo nativo de Earth Engine.
   - En Earth Engine se accede a LST a 70 m (NASA/ECOSTRESS/L2T_LSTE/V2).
4. Conclusión operativa:
   No sirve para un monitoreo continuo día a día, pero es insustituible para
   evaluar heterogeneidad y estrés intra-lote en fechas puntuales de seca u olas de calor
   (ej. 12,6 °C de diferencia entre bajos y lomas en la seca de enero 2023).
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

_DIR_DATOS = Path(__file__).resolve().parent.parent / "datos"
_ARCHIVO_DEMO = _DIR_DATOS / "ecostress_demo.json"


def cargar_diagnostico_ecostress() -> Dict[str, Any]:
    """
    Carga el diagnóstico de pasadas y fechas clave de ECOSTRESS precalculado
    para el campo de ejemplo de Uruguay.
    """
    if _ARCHIVO_DEMO.exists():
        try:
            with open(_ARCHIVO_DEMO, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "fuente": "NASA ECOSTRESS (ISS)",
        "resolucion_espacial": "70 metros",
        "conclusion": (
            "ECOSTRESS a 70 m ve la heterogeneidad térmica dentro del potrero, "
            "pero debido a la órbita de la ISS y la nubosidad (solo 28% de pasadas limpias), "
            "sirve para fechas clave de diagnóstico y no para seguimiento diario continuo."
        ),
        "fechas_clave_ejemplo": [],
    }
