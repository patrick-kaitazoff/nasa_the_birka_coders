"""MODIS MOD13Q1 v061 (NDVI, 250 m, 16 días) serie histórica 2000 → hoy por sección.

Para qué sirve en la app: alimentar la pestaña «Historia» («Tu campo, temporada por temporada»),
mostrando qué vio la NASA desde el año 2000 en cada sección: cuándo hubo cultivo, cuándo
quedó descubierto y cómo respondió el verde a las secas históricas (en especial 2022-23).

Fuentes:
1. Google Earth Engine (colección MODIS/061/MOD13Q1, banda NDVI con escala 0.0001 y CRS nativo
   Sinusoidal), resolviendo en segundos para cualquier campo sin demoras ni colas.
2. Caché persistente / Runtime Cache (90 días) para evitar consultas redundantes.
3. NASA AppEEARS (archivado/legado para scripts como armar_historia_demo.py si hiciera falta;
   no está en el camino de ejecución de Historia).
"""

from __future__ import annotations

import base64
import csv
import datetime as dt
import hashlib
import io
import json
import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from .. import cache
from . import modis

logger = logging.getLogger(__name__)

PRODUCTO = "MOD13Q1.061"
COLECCION_EE = "MODIS/061/MOD13Q1"
BANDA_NDVI = "NDVI"
CAPA_LEGACY = "_250m_16_days_NDVI"
API_APPEEARS = "https://appeears.earthdatacloud.nasa.gov/api"
INICIO_HISTORIA = dt.date(2000, 2, 18)
COORD_DEMO_DURAZNO = (-33.1030, -56.1462)
PROJECT_ID_EE = "field-shift-514100"

FUENTE_EE = "NASA MODIS MOD13Q1 v061 vía Google Earth Engine"
FUENTE_EE_CACHE = "NASA MODIS MOD13Q1 v061 vía Google Earth Engine (caché)"

# Caché en memoria para el token Bearer de la cuenta de servicio de Earth Engine
_TOKEN_SA_CACHE: tuple[str, float] | None = None


def _clave(lat: float, lon: float) -> str:
    return f"{round(lat, 4)},{round(lon, 4)},historia_v2"


def _clave_campo(puntos_coords: list[tuple[str, float, float]]) -> str:
    cadena = ",".join(f"{pid}:{round(lat, 4)}:{round(lon, 4)}" for pid, lat, lon in sorted(puntos_coords))
    return hashlib.sha1(cadena.encode("utf-8")).hexdigest()[:16]


def es_campo_demo(lat: float, lon: float) -> bool:
    """Verifica si las coordenadas corresponden al campo de ejemplo en Durazno."""
    return abs(lat - COORD_DEMO_DURAZNO[0]) < 0.05 and abs(lon - COORD_DEMO_DURAZNO[1]) < 0.05


def _cargar_sa_info() -> dict | None:
    """Carga los datos de la cuenta de servicio de Google Cloud desde env o .secretos/."""
    # 1. Variable de entorno (nombre sugerido: EE_CUENTA_SERVICIO)
    val = os.environ.get("EE_CUENTA_SERVICIO")
    if val:
        v_strip = val.strip()
        if v_strip.startswith("{"):
            try:
                return json.loads(v_strip)
            except Exception as e:
                logger.warning(f"No se pudo parsear EE_CUENTA_SERVICIO como JSON: {e}")
        p = Path(v_strip)
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"No se pudo leer archivo de EE_CUENTA_SERVICIO {p}: {e}")

    # 2. Búsqueda local en carpetas .secretos/
    directorios_secretos = [
        Path(__file__).parents[4] / ".secretos",
        Path(__file__).parents[3] / ".secretos",
        Path.cwd() / ".secretos",
        Path.home() / "nasa" / ".secretos",
    ]
    for d in directorios_secretos:
        if not d.is_dir():
            continue
        # Buscar ee_cuenta_servicio.json o cualquier json de service account de field-shift
        candidatos = list(d.glob("*.json"))
        for c in candidatos:
            try:
                txt = c.read_text(encoding="utf-8")
                if "private_key" in txt and "client_email" in txt:
                    js = json.loads(txt)
                    if js.get("type") == "service_account":
                        return js
            except Exception:
                continue

    return None


def _token_bearer_sa(sa_info: dict) -> str:
    """Genera o reutiliza un token OAuth2 Bearer para la cuenta de servicio."""
    global _TOKEN_SA_CACHE
    now = time.time()
    if _TOKEN_SA_CACHE and _TOKEN_SA_CACHE[1] > now + 300:
        return _TOKEN_SA_CACHE[0]

    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": sa_info["client_email"],
        "sub": sa_info["client_email"],
        "aud": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/earthengine",
        "iat": int(now),
        "exp": int(now) + 3600,
    }

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    seg1 = b64url(json.dumps(header).encode("utf-8"))
    seg2 = b64url(json.dumps(payload).encode("utf-8"))
    msg = f"{seg1}.{seg2}".encode("ascii")

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    private_key = serialization.load_pem_private_key(
        sa_info["private_key"].encode("utf-8"),
        password=None,
    )
    sig = private_key.sign(msg, padding.PKCS1v15(), hashes.SHA256())
    jwt_assertion = f"{seg1}.{seg2}.{b64url(sig)}"

    r = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt_assertion,
        },
        timeout=30,
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    _TOKEN_SA_CACHE = (token, now + 3300)
    return token


def _armar_expresion_getregion(lon: float, lat: float, start: str, end: str) -> dict:
    """Construye el grafo de expresión serializado para ImageCollection.getRegion."""
    return {
        "result": "0",
        "values": {
            "3": {"constantValue": [BANDA_NDVI]},
            "2": {
                "functionInvocationValue": {
                    "functionName": "Image.select",
                    "arguments": {
                        "bandSelectors": {"valueReference": "3"},
                        "input": {"argumentReference": "_MAPPING_VAR_0_0"},
                    },
                }
            },
            "1": {
                "functionInvocationValue": {
                    "functionName": "Collection.map",
                    "arguments": {
                        "baseAlgorithm": {
                            "functionDefinitionValue": {
                                "argumentNames": ["_MAPPING_VAR_0_0"],
                                "body": "2",
                            }
                        },
                        "collection": {
                            "functionInvocationValue": {
                                "functionName": "Collection.filter",
                                "arguments": {
                                    "collection": {
                                        "functionInvocationValue": {
                                            "functionName": "ImageCollection.load",
                                            "arguments": {"id": {"constantValue": COLECCION_EE}},
                                        }
                                    },
                                    "filter": {
                                        "functionInvocationValue": {
                                            "functionName": "Filter.dateRangeContains",
                                            "arguments": {
                                                "leftValue": {
                                                    "functionInvocationValue": {
                                                        "functionName": "DateRange",
                                                        "arguments": {
                                                            "end": {"constantValue": end},
                                                            "start": {"constantValue": start},
                                                        },
                                                    }
                                                },
                                                "rightField": {"constantValue": "system:time_start"},
                                            },
                                        }
                                    },
                                },
                            }
                        },
                    },
                }
            },
            "0": {
                "functionInvocationValue": {
                    "functionName": "ImageCollection.getRegion",
                    "arguments": {
                        "collection": {"valueReference": "1"},
                        "crs": {
                            "functionInvocationValue": {
                                "functionName": "Image.projection",
                                "arguments": {
                                    "image": {
                                        "functionInvocationValue": {
                                            "functionName": "Image.select",
                                            "arguments": {
                                                "bandSelectors": {"valueReference": "3"},
                                                "input": {
                                                    "functionInvocationValue": {
                                                        "functionName": "Collection.first",
                                                        "arguments": {"collection": {"valueReference": "1"}},
                                                    }
                                                },
                                            },
                                        }
                                    }
                                },
                            }
                        },
                        "geometry": {
                            "functionInvocationValue": {
                                "functionName": "GeometryConstructors.Point",
                                "arguments": {"coordinates": {"constantValue": [lon, lat]}},
                            }
                        },
                    },
                }
            },
        },
    }


def _procesar_filas_getregion(filas: list[list[Any]]) -> list[dict]:
    """Procesa la tabla retornada por getRegion (vía REST o ee local).

    Filtra valores de relleno (-3000), escala (0.0001), restringe a rango biofísico
    válido (-0.20 a 1.0) y aplica filtro de nubes (modis._sacar_nubes).
    """
    if not filas or len(filas) <= 1:
        return []

    header = [str(c).lower() for c in filas[0]]
    idx_id = header.index("id") if "id" in header else 0
    idx_time = header.index("time") if "time" in header else 3
    idx_ndvi = header.index("ndvi") if "ndvi" in header else 4

    puntos = []
    for f in filas[1:]:
        raw_val = f[idx_ndvi]
        if raw_val is None:
            continue
        try:
            val = float(raw_val)
        except (ValueError, TypeError):
            continue

        if val <= -2500 or val > 15000:
            continue

        if abs(val) > 1.0:
            val = val * 0.0001

        if not (-0.20 <= val <= 1.0):
            continue

        raw_id = str(f[idx_id])
        if len(raw_id) >= 10 and raw_id[4] == "_" and raw_id[7] == "_":
            fecha = raw_id[:10].replace("_", "-")
        else:
            t_ms = f[idx_time]
            try:
                fecha = dt.datetime.fromtimestamp(t_ms / 1000, tz=dt.timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                continue

        puntos.append({"fecha": fecha, "ndvi": round(val, 3)})

    puntos.sort(key=lambda p: p["fecha"])
    return modis._sacar_nubes(puntos)


def _consultar_punto_ee(lon: float, lat: float, hasta: dt.date | None = None) -> list[dict]:
    """Consulta la serie de NDVI de Earth Engine para un punto dado.

    Prueba primero con la cuenta de servicio y la API REST directa (Camino b).
    Si no hay cuenta de servicio configurada, intenta usar la sesión local de ee (Camino PC).
    Si no hay credenciales disponibles o DESACTIVAR_EE=1, devuelve lista vacía.
    """
    if os.environ.get("DESACTIVAR_EE") == "1":
        return []

    hasta_str = (hasta or dt.date.today()).strftime("%Y-%m-%d")
    inicio_str = INICIO_HISTORIA.strftime("%Y-%m-%d")

    # 1. Camino b: Cuenta de servicio vía API REST con httpx
    sa_info = _cargar_sa_info()
    if sa_info:
        try:
            token = _token_bearer_sa(sa_info)
            project_id = sa_info.get("project_id") or PROJECT_ID_EE
            expr = _armar_expresion_getregion(lon, lat, inicio_str, hasta_str)
            url = f"https://earthengine.googleapis.com/v1/projects/{project_id}/value:compute"
            headers = {
                "Authorization": f"Bearer {token}",
                "X-Goog-User-Project": project_id,
                "Content-Type": "application/json",
            }
            r = httpx.post(url, json={"expression": expr}, headers=headers, timeout=45)
            r.raise_for_status()
            filas = r.json().get("result", [])
            return _procesar_filas_getregion(filas)
        except Exception as e:
            logger.warning(f"Fallo en consulta EE REST con cuenta de servicio: {e}")

    # 2. Camino local: Sesión de ee inicializada en la PC
    try:
        import ee

        try:
            ee.Initialize(project=PROJECT_ID_EE)
        except Exception:
            pass
        col = ee.ImageCollection(COLECCION_EE).filterDate(inicio_str, hasta_str).select(BANDA_NDVI)
        native_proj = col.first().select(BANDA_NDVI).projection()
        pt = ee.Geometry.Point([lon, lat])
        filas = col.getRegion(pt, crs=native_proj).getInfo()
        return _procesar_filas_getregion(filas)
    except Exception as e:
        logger.warning(f"Fallo en consulta EE con cliente Python: {e}")

    return []


def estado_campo(puntos_coords: list[tuple[str, float, float]], tarea_fijada: str | None = None) -> dict:
    """Verifica y obtiene la serie histórica MODIS para todas las secciones de un campo.

    Orden de resolución:
    1. Caché persistente (90 días). Si todas las secciones están guardadas, contesta al instante.
    2. Google Earth Engine (resolución en 1 a 3 segundos en paralelo).
    3. Si Earth Engine no está disponible o falla, devuelve estado 'solo_clima' sin bloquear
       ni preguntar cada 15 segundos. No se pide nada a AppEEARS.
    """
    if not puntos_coords:
        return {"estado": "listo", "secciones": {}, "fuente": FUENTE_EE}

    # 1. Comprobar si todas las secciones ya tienen su serie en caché
    secciones_listas: dict[str, dict[str, Any]] = {}
    faltantes: list[tuple[str, float, float]] = []

    for sec_id, lat, lon in puntos_coords:
        c = _clave(lat, lon)
        guardado = cache.leer("modis_historia", c, max_dias=90)
        if guardado and guardado.get("serie"):
            secciones_listas[sec_id] = guardado
        else:
            faltantes.append((sec_id, lat, lon))

    if not faltantes:
        return {
            "estado": "listo",
            "secciones": secciones_listas,
            "fuente": FUENTE_EE_CACHE,
        }

    # 2. Descargar las secciones faltantes desde Earth Engine en paralelo
    def _tarea_seccion(item: tuple[str, float, float]) -> tuple[str, float, float, list[dict]]:
        sid, lat, lon = item
        pts = _consultar_punto_ee(lon, lat)
        return sid, lat, lon, pts

    max_hilos = min(6, len(faltantes))
    try:
        with ThreadPoolExecutor(max_workers=max_hilos) as ex:
            resultados = list(ex.map(_tarea_seccion, faltantes))
    except Exception as e:
        logger.warning(f"Error al paralelizar consulta EE: {e}")
        resultados = []

    fallo_alguna = False
    for sid, lat, lon, serie in resultados:
        if not serie:
            fallo_alguna = True
            continue
        inter = interpretar_historia(serie, "sur" if lat < 0 else "norte")
        res_sec = {
            "fuente": FUENTE_EE,
            "lat": lat,
            "lon": lon,
            "serie": serie,
            "estado": "listo",
            **inter,
        }
        cache.guardar("modis_historia", _clave(lat, lon), res_sec)
        secciones_listas[sid] = res_sec

    if len(secciones_listas) == len(puntos_coords):
        return {
            "estado": "listo",
            "secciones": secciones_listas,
            "fuente": FUENTE_EE,
        }

    # Si no se pudo obtener el satélite para todas las secciones, Historia sigue con el clima
    return {
        "estado": "solo_clima",
        "secciones": secciones_listas,
        "motivo": "Por ahora solo tenemos los datos del clima de la zona (NASA POWER).",
    }


def interpretar_historia(puntos: list[dict], hemisferio: str = "sur") -> dict:
    """Interpreta la serie histórica de NDVI por temporada desde 2000 hasta el presente.

    Calcula la fenología de cada temporada, la mediana histórica por tipo (invierno / verano)
    y la anomalía porcentual respecto a la mediana del propio campo.
    """
    if not puntos:
        return {"temporadas": [], "mensual": [], "medianas": {}, "descubierto_por_anio": []}

    puntos = modis._sacar_nubes(sorted(puntos, key=lambda p: p["fecha"]))
    por_mes: dict[tuple[int, int], list[float]] = {}
    for p in puntos:
        try:
            y, m = int(p["fecha"][:4]), int(p["fecha"][5:7])
            por_mes.setdefault((y, m), []).append(float(p["ndvi"]))
        except (ValueError, KeyError):
            continue

    mensual = {k: float(sum(v) / len(v)) for k, v in por_mes.items()}
    anios = sorted({k[0] for k in mensual})

    # Detección de suelo descubierto por año
    descubierto = []
    for y in anios:
        meses = [m for m in range(1, 13) if (y, m) in mensual]
        if len(meses) >= 8:
            bajos = [m for m in meses if mensual[(y, m)] < modis.UMBRAL_DESCUBIERTO]
            descubierto.append({"anio": y, "meses_descubierto": len(bajos), "meses": bajos})

    # Armado de temporadas agrícolas desde 2000
    temporadas_crudas = []
    norte = hemisferio == "norte"
    for y in anios:
        if norte:
            # Hemisferio norte, verano de junio a septiembre e invierno en otoño + primavera (en pleno
            # invierno el trigo está en reposo o bajo la nieve). Ver modis.interpretar.
            ver = [mensual[(y, m)] for m in (6, 7, 8, 9) if (y, m) in mensual]
            inv = [mensual[k] for k in ((y, 11), (y + 1, 3), (y + 1, 4)) if k in mensual]
            for tipo, vals, nombre in (("verano", ver, f"verano {y}"), ("invierno", inv, f"invierno {y}/{str(y + 1)[2:]}")):
                if len(vals) >= 3:
                    info = modis._temporada(nombre, vals)
                    info["tipo"] = tipo
                    info["anio_agricola"] = y
                    info["ndvi_integrado"] = round(float(np.mean(vals)), 3)
                    temporadas_crudas.append(info)
            continue
        # Invierno del año y (meses 6 a 10)
        inv = [mensual[(y, m)] for m in (6, 7, 8, 9, 10) if (y, m) in mensual]
        if len(inv) >= 3:
            info_inv = modis._temporada(f"invierno {y}", inv)
            info_inv["tipo"] = "invierno"
            info_inv["anio_agricola"] = y
            info_inv["ndvi_integrado"] = round(float(np.mean(inv)), 3)
            temporadas_crudas.append(info_inv)

        # Verano del año y / y+1 (diciembre de y, enero-marzo de y+1)
        ver = [mensual[k] for k in ((y, 12), (y + 1, 1), (y + 1, 2), (y + 1, 3)) if k in mensual]
        if len(ver) >= 3:
            info_ver = modis._temporada(f"verano {y}/{str(y + 1)[2:]}", ver)
            info_ver["tipo"] = "verano"
            info_ver["anio_agricola"] = y
            info_ver["ndvi_integrado"] = round(float(np.mean(ver)), 3)
            temporadas_crudas.append(info_ver)

    # Cálculo de medianas históricas por tipo de temporada para esta sección
    max_inv = [t["ndvi_max"] for t in temporadas_crudas if t["tipo"] == "invierno"]
    max_ver = [t["ndvi_max"] for t in temporadas_crudas if t["tipo"] == "verano"]

    mediana_inv = round(float(np.median(max_inv)), 3) if max_inv else 0.70
    mediana_ver = round(float(np.median(max_ver)), 3) if max_ver else 0.80

    temporadas = []
    for t in temporadas_crudas:
        mediana = mediana_inv if t["tipo"] == "invierno" else mediana_ver
        anomalia = round(((t["ndvi_max"] / mediana) - 1.0) * 100.0, 1) if mediana > 0 else 0.0
        # Estrés severo detectado por satélite: verdor >= 15 % por debajo de la mediana histórica
        estres_satelite = anomalia <= -15.0
        t_final = {
            **t,
            "mediana_historica": mediana,
            "anomalia_ndvi_pct": anomalia,
            "estres_satelite": estres_satelite,
        }
        temporadas.append(t_final)

    return {
        "mensual": [{"anio": k[0], "mes": k[1], "ndvi": round(v, 3)} for k, v in sorted(mensual.items())],
        "temporadas": temporadas,
        "descubierto_por_anio": descubierto,
        "medianas": {"invierno": mediana_inv, "verano": mediana_ver},
        "total_temporadas": len(temporadas),
    }


def ndvi_historia_punto(lat: float, lon: float, seccion_id: str | None = None) -> dict:
    """Obtiene la serie histórica de NDVI (2000 a hoy) para una coordenada dada desde la caché."""
    clave = _clave(lat, lon)
    guardado = cache.leer("modis_historia", clave, max_dias=90)
    if guardado and guardado.get("serie"):
        return guardado

    return {
        "fuente": None,
        "lat": lat,
        "lon": lon,
        "serie": [],
        "estado": "sin_datos",
        "mensaje": "Sin datos de satélite todavía",
        **interpretar_historia([]),
    }


# ==============================================================================
# FUNCIONES LEGADAS DE NASA APPEEARS (Archivadas para scripts de datos locales)
# ==============================================================================


def _credenciales() -> tuple[str, str] | None:
    """Credenciales de Earthdata para descargas masivas legadas de AppEEARS."""
    u, p = os.environ.get("EARTHDATA_USER"), os.environ.get("EARTHDATA_PASS")
    if not (u and p):
        for r in [
            Path(__file__).parents[4] / ".secretos" / "earthdata.env",
            Path(__file__).parents[3] / ".secretos" / "earthdata.env",
            Path.cwd() / ".secretos" / "earthdata.env",
        ]:
            if r.is_file():
                try:
                    for linea in r.read_text(encoding="utf-8").splitlines():
                        linea = linea.strip()
                        if linea.startswith("export "):
                            linea = linea[7:]
                        if "=" in linea and not linea.startswith("#"):
                            k, v = linea.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k == "EARTHDATA_USER" and not u:
                                u = v
                            elif k == "EARTHDATA_PASS" and not p:
                                p = v
                except Exception:
                    pass
    return (u, p) if u and p else None


def _token(cred: tuple[str, str]) -> str:
    guardado = cache.leer("appeears", "token", max_dias=1.5)
    if guardado:
        return guardado
    r = httpx.post(f"{API_APPEEARS}/login", auth=cred, timeout=60)
    r.raise_for_status()
    token = r.json()["token"]
    cache.guardar("appeears", "token", token)
    return token


def _pedido_campo(puntos_coords: list[tuple[str, float, float]], hasta: dt.date) -> dict:
    fmt = "%m-%d-%Y"
    return {
        "task_type": "point",
        "task_name": f"fieldshift_modis_{_clave_campo(puntos_coords)}",
        "params": {
            "dates": [{"startDate": INICIO_HISTORIA.strftime(fmt), "endDate": hasta.strftime(fmt)}],
            "layers": [{"product": PRODUCTO, "layer": CAPA_LEGACY}],
            "coordinates": [
                {"id": pid, "latitude": round(lat, 4), "longitude": round(lon, 4)}
                for pid, lat, lon in puntos_coords
            ],
        },
    }


def leer_csv_modis(texto: str) -> dict[str, list[dict]]:
    """CSV de puntos de AppEEARS → {seccion_id: [{"fecha": YYYY-MM-DD, "ndvi": float}]}.

    Identifica las columnas de ID, Date y la capa de NDVI.
    Filtra valores de relleno (-3000), normaliza escala (0.0001) y descarta fuera de rango.
    """
    filas = list(csv.DictReader(io.StringIO(texto)))
    if not filas:
        return {}

    cols = list(filas[0].keys())
    c_id = next((c for c in cols if c.strip().lower() in ("id", "point_id")), cols[0])
    c_fecha = next((c for c in cols if c.strip().lower() == "date"), None)
    c_ndvi = next((c for c in cols if c.endswith("_250m_16_days_NDVI") or "ndvi" in c.lower()), None)

    if not c_fecha or not c_ndvi:
        raise ValueError(f"El CSV de AppEEARS no tiene las columnas requeridas (Date, NDVI): {cols}")

    puntos_por_id: dict[str, list[dict]] = defaultdict(list)

    for f in filas:
        sec_id = (f.get(c_id) or "campo").strip()
        raw_fecha = (f.get(c_fecha) or "").strip()
        fecha = raw_fecha[:10]
        if len(fecha) != 10:
            continue

        raw_val = f.get(c_ndvi)
        if raw_val is None or raw_val.strip() == "":
            continue

        try:
            val = float(raw_val)
        except ValueError:
            continue

        if val <= -2500 or val > 15000:
            continue

        if abs(val) > 1.0:
            val = val * 0.0001

        if -0.20 <= val <= 1.0:
            puntos_por_id[sec_id].append({"fecha": fecha, "ndvi": round(val, 3)})

    salida: dict[str, list[dict]] = {}
    for sid, lista in puntos_por_id.items():
        lista.sort(key=lambda p: p["fecha"])
        salida[sid] = modis._sacar_nubes(lista)

    return salida


def _bajar_resultado(token: str, tarea: str) -> dict[str, list[dict]]:
    h = {"Authorization": f"Bearer {token}"}
    r = httpx.get(f"{API_APPEEARS}/bundle/{tarea}", headers=h, timeout=60)
    r.raise_for_status()
    csvs = [a for a in r.json().get("files", []) if a.get("file_name", "").lower().endswith(".csv")]
    csvs.sort(key=lambda a: "MOD13Q1" not in a.get("file_name", ""))
    for a in csvs:
        r = httpx.get(f"{API_APPEEARS}/bundle/{tarea}/{a['file_id']}", headers=h, timeout=180, follow_redirects=True)
        r.raise_for_status()
        try:
            series_dict = leer_csv_modis(r.text)
            if series_dict:
                return series_dict
        except ValueError:
            continue
    raise ValueError("La tarea de AppEEARS terminó sin un CSV de MOD13Q1 que se pueda interpretar.")


def esperar_campo(
    puntos_coords: list[tuple[str, float, float]],
    tarea_fijada: str | None = None,
    cada_s: int = 15,
    max_min: int = 90,
) -> dict:
    """Función de espera legada para tareas históricas en AppEEARS."""
    fin = time.time() + max_min * 60
    while True:
        r = estado_campo(puntos_coords, tarea_fijada=tarea_fijada)
        if r.get("estado") != "pendiente" or time.time() > fin:
            return r
        time.sleep(cada_s)
