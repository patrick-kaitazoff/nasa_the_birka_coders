"""Humedad del suelo y evapotranspiración de GLDAS 2.1 (NASA Noah, 0,25°) desde 2000.

GLDAS (Global Land Data Assimilation System) combina observaciones meteorológicas y satelitales
dentro del modelo de superficie terrestre Noah de la NASA a escala global (resolución de 0,25°, ~25 km).
Provee datos continuos desde el año 2000 hasta el presente.

A diferencia de SMAP (que mide desde abril de 2015), GLDAS cubre las dos peores sequías
históricas recientes de Uruguay: la de 2008/2009 y la de 2022/2023.

Límites:
- Resolución de 0,25° (~25 km): no distingue lomas, bajos ni tipos de suelo del lote.
- Es un modelo de asimilación, no una medición directa en el predio.

Colección en Google Earth Engine: NASA/GLDAS/V021/NOAH/G025/T3H
Bandas:
- SoilMoi0_10cm_inst: contenido de agua en suelo 0-10 cm (kg/m² = mm)
- SoilMoi10_40cm_inst: contenido de agua en suelo 10-40 cm (kg/m² = mm)
- SoilMoi40_100cm_inst: contenido de agua en suelo 40-100 cm (kg/m² = mm)
- RootMoist_inst: contenido de agua en zona de raíces 0-100 cm (kg/m² = mm)
- Evap_tavg: tasa de evapotranspiración (kg/m²/s)
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import logging
import os
from typing import Any

import httpx
import numpy as np

from .. import cache
from . import modis_historia

logger = logging.getLogger(__name__)

COLECCION_GLDAS = "NASA/GLDAS/V021/NOAH/G025/T3H"
TIMEOUT_EE_S = 35.0
# Valor que devuelve Earth Engine en un mes sin imágenes (sin esto, un mes vacío hace fallar toda la consulta)
SIN_DATO = -9999

try:
    import ee
    HAY_EE = True
except ImportError:
    ee = None  # type: ignore[assignment]
    HAY_EE = False


def _primer_dia_mes_actual() -> dt.date:
    return dt.date.today().replace(day=1)


def _clave_cache(lat: float, lon: float, fecha_str: str) -> str:
    # Redondea a 0,25° (~25 km) para que campos en la misma celda compartan la caché
    c_lat = round(round(lat * 4) / 4, 3)
    c_lon = round(round(lon * 4) / 4, 3)
    txt = f"gldas:{c_lat}:{c_lon}:{fecha_str}"
    return hashlib.sha1(txt.encode("utf-8")).hexdigest()[:16]


def _asegurar_ee_inicializado(sa_info: dict | None = None) -> bool:
    global HAY_EE
    if not HAY_EE or ee is None:
        return False
    try:
        ee.data.get_cloud_projects()
        return True
    except Exception:
        pass
    if not sa_info:
        sa_info = modis_historia._cargar_sa_info()
    if not sa_info:
        return False
    try:
        creds = ee.ServiceAccountCredentials(sa_info["client_email"], key_data=json.dumps(sa_info))
        ee.Initialize(credentials=creds, project=sa_info.get("project_id"))
        return True
    except Exception as e:
        logger.debug(f"No se pudo inicializar ee con SA: {e}")
        return False


def _armar_con_cliente_ee(lat: float, lon: float, hoy_str: str, n_meses: int) -> dict:
    pt = ee.Geometry.Point([lon, lat])
    hoy = ee.Date(hoy_str)
    col = ee.ImageCollection(COLECCION_GLDAS).select([
        "SoilMoi0_10cm_inst",
        "SoilMoi10_40cm_inst",
        "SoilMoi40_100cm_inst",
        "RootMoist_inst",
        "Evap_tavg",
    ])
    meses = ee.List.sequence(0, n_meses - 1)

    def calc_mes(n):
        fin = hoy.advance(ee.Number(n).multiply(-1), "month")
        ini = fin.advance(-1, "month")
        sub = col.filterBounds(pt).filterDate(ini, fin)
        mean = sub.mean().reduceRegion(reducer=ee.Reducer.mean(), geometry=pt, scale=25000)
        return ee.Dictionary({
            "anio": ini.get("year"),
            "mes": ini.get("month"),
            "sm_0_10": mean.get("SoilMoi0_10cm_inst", SIN_DATO),
            "sm_10_40": mean.get("SoilMoi10_40cm_inst", SIN_DATO),
            "sm_40_100": mean.get("SoilMoi40_100cm_inst", SIN_DATO),
            "root_sm": mean.get("RootMoist_inst", SIN_DATO),
            "evap": mean.get("Evap_tavg", SIN_DATO),
        })

    resultado = ee.List(meses.map(calc_mes))
    return ee.serializer.encode(resultado, for_cloud_api=True)


# Plantilla base pre-serializada para entornos sin cliente ee (Vercel)
_PLANTILLA_GLDAS: dict[str, Any] = {
    'result': '0',
    'values': {
        '4': {'constantValue': 'month'},
        '3': {
            'functionInvocationValue': {
                'functionName': 'Date.advance',
                'arguments': {
                    'date': {
                        'functionInvocationValue': {
                            'functionName': 'Date',
                            'arguments': {'value': {'constantValue': '2026-11-15'}},
                        }
                    },
                    'delta': {
                        'functionInvocationValue': {
                            'functionName': 'Number.multiply',
                            'arguments': {
                                'left': {'argumentReference': '_MAPPING_VAR_1_0'},
                                'right': {'constantValue': -1},
                            },
                        }
                    },
                    'unit': {'valueReference': '4'},
                },
            }
        },
        '2': {
            'functionInvocationValue': {
                'functionName': 'Date.advance',
                'arguments': {
                    'date': {'valueReference': '3'},
                    'delta': {'constantValue': -1},
                    'unit': {'valueReference': '4'},
                },
            }
        },
        '6': {
            'functionInvocationValue': {
                'functionName': 'GeometryConstructors.Point',
                'arguments': {'coordinates': {'constantValue': [-56.15, -33.1]}},
            }
        },
        '8': {'constantValue': 'SoilMoi0_10cm_inst'},
        '9': {'constantValue': 'SoilMoi10_40cm_inst'},
        '10': {'constantValue': 'SoilMoi40_100cm_inst'},
        '11': {'constantValue': 'RootMoist_inst'},
        '12': {'constantValue': 'Evap_tavg'},
        '7': {
            'functionInvocationValue': {
                'functionName': 'Image.select',
                'arguments': {
                    'bandSelectors': {
                        'arrayValue': {
                            'values': [
                                {'valueReference': '8'},
                                {'valueReference': '9'},
                                {'valueReference': '10'},
                                {'valueReference': '11'},
                                {'valueReference': '12'},
                            ]
                        }
                    },
                    'input': {'argumentReference': '_MAPPING_VAR_0_0'},
                },
            }
        },
        '5': {
            'functionInvocationValue': {
                'functionName': 'Image.reduceRegion',
                'arguments': {
                    'geometry': {'valueReference': '6'},
                    'image': {
                        'functionInvocationValue': {
                            'functionName': 'reduce.mean',
                            'arguments': {
                                'collection': {
                                    'functionInvocationValue': {
                                        'functionName': 'Collection.filter',
                                        'arguments': {
                                            'collection': {
                                                'functionInvocationValue': {
                                                    'functionName': 'Collection.filter',
                                                    'arguments': {
                                                        'collection': {
                                                            'functionInvocationValue': {
                                                                'functionName': 'Collection.map',
                                                                'arguments': {
                                                                    'baseAlgorithm': {
                                                                        'functionDefinitionValue': {
                                                                            'argumentNames': ['_MAPPING_VAR_0_0'],
                                                                            'body': '7',
                                                                        }
                                                                    },
                                                                    'collection': {
                                                                        'functionInvocationValue': {
                                                                            'functionName': 'ImageCollection.load',
                                                                            'arguments': {
                                                                                'id': {'constantValue': COLECCION_GLDAS}
                                                                            },
                                                                        }
                                                                    },
                                                                },
                                                            }
                                                        },
                                                        'filter': {
                                                            'functionInvocationValue': {
                                                                'functionName': 'Filter.intersects',
                                                                'arguments': {
                                                                    'leftField': {'constantValue': '.all'},
                                                                    'rightValue': {
                                                                        'functionInvocationValue': {
                                                                            'functionName': 'Feature',
                                                                            'arguments': {'geometry': {'valueReference': '6'}},
                                                                        }
                                                                    },
                                                                },
                                                            }
                                                        },
                                                    },
                                                }
                                            },
                                            'filter': {
                                                'functionInvocationValue': {
                                                    'functionName': 'Filter.dateRangeContains',
                                                    'arguments': {
                                                        'leftValue': {
                                                            'functionInvocationValue': {
                                                                'functionName': 'DateRange',
                                                                'arguments': {
                                                                    'end': {'valueReference': '3'},
                                                                    'start': {'valueReference': '2'},
                                                                },
                                                            }
                                                        },
                                                        'rightField': {'constantValue': 'system:time_start'},
                                                    },
                                                }
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    },
                    'reducer': {'functionInvocationValue': {'functionName': 'Reducer.mean', 'arguments': {}}},
                    'scale': {'constantValue': 25000},
                },
            }
        },
        '1': {
            'dictionaryValue': {
                'values': {
                    'anio': {
                        'functionInvocationValue': {
                            'functionName': 'Date.get',
                            'arguments': {'date': {'valueReference': '2'}, 'unit': {'constantValue': 'year'}},
                        }
                    },
                    'evap': {
                        'functionInvocationValue': {
                            'functionName': 'Dictionary.get',
                            'arguments': {'dictionary': {'valueReference': '5'}, 'key': {'valueReference': '12'}},
                        }
                    },
                    'mes': {
                        'functionInvocationValue': {
                            'functionName': 'Date.get',
                            'arguments': {'date': {'valueReference': '2'}, 'unit': {'valueReference': '4'}},
                        }
                    },
                    'root_sm': {
                        'functionInvocationValue': {
                            'functionName': 'Dictionary.get',
                            'arguments': {'dictionary': {'valueReference': '5'}, 'key': {'valueReference': '11'}},
                        }
                    },
                    'sm_0_10': {
                        'functionInvocationValue': {
                            'functionName': 'Dictionary.get',
                            'arguments': {'dictionary': {'valueReference': '5'}, 'key': {'valueReference': '8'}},
                        }
                    },
                    'sm_10_40': {
                        'functionInvocationValue': {
                            'functionName': 'Dictionary.get',
                            'arguments': {'dictionary': {'valueReference': '5'}, 'key': {'valueReference': '9'}},
                        }
                    },
                    'sm_40_100': {
                        'functionInvocationValue': {
                            'functionName': 'Dictionary.get',
                            'arguments': {'dictionary': {'valueReference': '5'}, 'key': {'valueReference': '10'}},
                        }
                    },
                }
            }
        },
        '0': {
            'functionInvocationValue': {
                'functionName': 'List.map',
                'arguments': {
                    'baseAlgorithm': {
                        'functionDefinitionValue': {
                            'argumentNames': ['_MAPPING_VAR_1_0'],
                            'body': '1',
                        }
                    },
                    'dropNulls': {'constantValue': False},
                    'list': {
                        'functionInvocationValue': {
                            'functionName': 'List.sequence',
                            'arguments': {
                                'end': {'constantValue': 319},
                                'start': {'constantValue': 0},
                            },
                        }
                    },
                },
            }
        },
    },
}


def armar_expresion_gldas(lat: float, lon: float, hoy_str: str, n_meses: int, sa_info: dict | None = None) -> dict:
    if HAY_EE and _asegurar_ee_inicializado(sa_info):
        try:
            return _armar_con_cliente_ee(lat, lon, hoy_str, n_meses)
        except Exception as e:
            logger.debug(f"Falla ee.serializer en GLDAS ({e}); usando plantilla pre-serializada")

    expr = copy.deepcopy(_PLANTILLA_GLDAS)
    for campo in expr["values"]["1"]["dictionaryValue"]["values"].values():
        llamada = campo["functionInvocationValue"]
        if llamada["functionName"] == "Dictionary.get":
            llamada["arguments"]["defaultValue"] = {"constantValue": SIN_DATO}
    expr["values"]["3"]["functionInvocationValue"]["arguments"]["date"]["functionInvocationValue"]["arguments"]["value"]["constantValue"] = hoy_str
    expr["values"]["6"]["functionInvocationValue"]["arguments"]["coordinates"]["constantValue"] = [lon, lat]
    expr["values"]["0"]["functionInvocationValue"]["arguments"]["list"]["functionInvocationValue"]["arguments"]["end"]["constantValue"] = max(0, n_meses - 1)
    return expr


def _calcular_anomalias_mensuales(mensual: list[dict]) -> dict[str, float]:
    """Calcula la anomalía estandarizada ((v - media_mes) / desvio_mes) para la humedad de raíces."""
    por_mes: dict[int, list[float]] = {}
    validos = [m for m in mensual if m.get("root_sm") is not None]
    for m in validos:
        por_mes.setdefault(m["mes"], []).append(float(m["root_sm"]))

    stats = {
        mes: (float(np.mean(vals)), float(np.std(vals)) or 1.0)
        for mes, vals in por_mes.items()
        if vals
    }

    anomalias: dict[str, float] = {}
    for m in validos:
        mes_num = m["mes"]
        if mes_num in stats:
            media, std = stats[mes_num]
            clave = f"{m['anio']:04d}-{m['mes']:02d}"
            anomalias[clave] = round((float(m["root_sm"]) - media) / std, 2)
    return anomalias


def _coma(x: float) -> str:
    return f"{abs(x):.1f}".replace(".", ",")


def comparar_con_balance(
    gldas_anomalias: dict[str, float],
    app_anomalias: dict[str, float],
) -> dict:
    """Evalúa la coincidencia del balance de la app contra GLDAS, especialmente en 2008/09 y 2022/23."""
    comunes = sorted(k for k in gldas_anomalias if k in app_anomalias)
    if len(comunes) < 12:
        return {"correlacion": None, "meses_comunes": len(comunes), "acuerdo": "datos insuficientes"}

    g_vals = [gldas_anomalias[k] for k in comunes]
    a_vals = [app_anomalias[k] for k in comunes]
    r = float(np.corrcoef(g_vals, a_vals)[0, 1])

    # Evaluación específica en la seca de 2008/09 (oct 2008 a mar 2009)
    meses_08 = [f"2008-{m:02d}" for m in range(10, 13)] + [f"2009-{m:02d}" for m in range(1, 4)]
    g_08 = [gldas_anomalias[k] for k in meses_08 if k in gldas_anomalias]
    a_08 = [app_anomalias[k] for k in meses_08 if k in app_anomalias]

    # Evaluación específica en la seca de 2022/23 (oct 2022 a mar 2023)
    meses_22 = [f"2022-{m:02d}" for m in range(10, 13)] + [f"2023-{m:02d}" for m in range(1, 4)]
    g_22 = [gldas_anomalias[k] for k in meses_22 if k in gldas_anomalias]
    a_22 = [app_anomalias[k] for k in meses_22 if k in app_anomalias]

    min_08_g = min(g_08) if g_08 else None
    min_08_a = min(a_08) if a_08 else None
    min_22_g = min(g_22) if g_22 else None
    min_22_a = min(a_22) if a_22 else None

    coinciden_secas = (
        min_08_g is not None and min_08_g <= -1.2
        and min_08_a is not None and min_08_a <= -1.2
        and min_22_g is not None and min_22_g <= -1.2
        and min_22_a is not None and min_22_a <= -1.2
    )

    if coinciden_secas:
        frase_secas = (
            "En las secas de 2008/09 y 2022/23, el balance de la app y GLDAS marcaron las dos como muy secas "
            f"(en desvíos por debajo de lo normal, 2008/09: app {_coma(min_08_a)}, GLDAS {_coma(min_08_g)}; "
            f"2022/23: app {_coma(min_22_a)}, GLDAS {_coma(min_22_g)})."
        )
    elif r >= 0.65:
        frase_secas = "El balance de la app y GLDAS coinciden bien en la evolución de las sequías históricas."
    else:
        frase_secas = "GLDAS y el balance de la app muestran similitud general en los extremos secos."

    return {
        "correlacion": round(r, 2),
        "meses_comunes": len(comunes),
        "frase_secas": frase_secas,
        "coinciden_secas": coinciden_secas,
        "seca_2008": {"gldas_min": min_08_g, "app_min": min_08_a},
        "seca_2022": {"gldas_min": min_22_g, "app_min": min_22_a},
    }


def consultar_gldas(lat: float, lon: float, fecha_hasta: dt.date | None = None) -> dict:
    """Consulta la serie mensual histórica de GLDAS 2.1 (Noah 0,25°) desde enero de 2000.

    Devuelve {"ok": True, "mensual": [...], "anomalias": {...}, "fuente": "..."}.
    Si Earth Engine está desactivado o falla, devuelve ok: False con el motivo.
    """
    if os.environ.get("DESACTIVAR_EE") == "1":
        return {"ok": False, "motivo": "Earth Engine desactivado por configuración (DESACTIVAR_EE=1)"}

    if fecha_hasta is None:
        fecha_hasta = _primer_dia_mes_actual()
    hoy_str = fecha_hasta.isoformat()

    # Meses enteros desde enero de 2000 hasta el anterior a fecha_hasta
    n_meses = (fecha_hasta.year - 2000) * 12 + fecha_hasta.month - 1
    n_meses = max(12, min(n_meses, 360))

    clave = _clave_cache(lat, lon, hoy_str)
    guardado = cache.leer("gldas", clave, max_dias=90)
    if guardado:
        return {**guardado, "desde_cache": True}

    sa_info = modis_historia._cargar_sa_info()
    if not sa_info:
        return {"ok": False, "motivo": "Sin credenciales de Google Earth Engine (.secretos/)"}

    try:
        token = modis_historia._token_bearer_sa(sa_info)
        project_id = sa_info.get("project_id") or modis_historia.PROJECT_ID_EE
        expr = armar_expresion_gldas(lat, lon, hoy_str, n_meses, sa_info=sa_info)
        url = f"https://earthengine.googleapis.com/v1/projects/{project_id}/value:compute"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Goog-User-Project": project_id,
            "Content-Type": "application/json",
        }
        resp = httpx.post(url, json={"expression": expr}, headers=headers, timeout=TIMEOUT_EE_S)
        resp.raise_for_status()
        raw_items = resp.json().get("result", [])
    except Exception as e:
        logger.warning(f"Error consultando GLDAS en Earth Engine: {e}")
        return {"ok": False, "motivo": f"Falla en Earth Engine: {e}"}

    procesados = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        anio = item.get("anio")
        mes = item.get("mes")
        if anio is None or mes is None:
            continue
        r_sm, sm0, sm1, sm2, evap = (
            None if item.get(k) in (None, SIN_DATO) else item.get(k)
            for k in ("root_sm", "sm_0_10", "sm_10_40", "sm_40_100", "evap")
        )
        procesados.append({
            "anio": int(anio),
            "mes": int(mes),
            "root_sm": round(float(r_sm), 2) if r_sm is not None else None,
            "sm_0_10": round(float(sm0), 2) if sm0 is not None else None,
            "sm_10_40": round(float(sm1), 2) if sm1 is not None else None,
            "sm_40_100": round(float(sm2), 2) if sm2 is not None else None,
            "evap_mm_dia": round(float(evap) * 86400, 2) if evap is not None else None,
        })

    procesados.sort(key=lambda x: x["anio"] * 12 + x["mes"])
    anomalias = _calcular_anomalias_mensuales(procesados)
    for p in procesados:
        k = f"{p['anio']:04d}-{p['mes']:02d}"
        p["anomalia"] = anomalias.get(k)

    salida = {
        "ok": True,
        "mensual": procesados,
        "anomalias": anomalias,
        "fuente": "NASA GLDAS 2.1 (modelo Noah, 0,25°) vía Google Earth Engine",
        "limites": [
            "GLDAS es un modelo de asimilación (Noah, 0,25° ≈ 25 km) que combina satélites y meteorología; no es una medición directa en el lote.",
            "A diferencia de SMAP (que empezó en 2015), GLDAS cubre desde el 2000 y permite verificar las sequías de 2008/09 y 2022/23.",
        ],
    }

    cache.guardar("gldas", clave, salida)
    return salida
