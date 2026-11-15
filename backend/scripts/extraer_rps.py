"""Extrae las tablas del programa Erosión 6.0 del MGAP (archivos .ERD) necesarias para Field Shift.

Genera app/backend/fieldshift/datos/rps_erosion6.json con las relaciones de pérdida de suelo (RPS),
el efecto residual de pasturas (ERP), los factores C precalculados y los valores publicados para colza.

Fuente de los .ERD:
  Programa Erosión 6.0 USLE-RUSLE (Facultad de Agronomía, UdelaR / MGAP-DGRN)
  https://www.gub.uy/ministerio-ganaderia-agricultura-pesca/politicas-y-gestion/programa-erosion-60-usle-rusle
  Descargado de https://descargas.mgap.gub.uy/DGRN/CONEAT/Erosion%20para%20Windows.rar

Uso:
  python app/backend/scripts/extraer_rps.py [<carpeta_con_datos_erd>]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Agregar scripts al path para importar leer_erosion6
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import leer_erosion6  # noqa: E402

RAIZ_BACKEND = SCRIPTS_DIR.parent
SALIDA_JSON = RAIZ_BACKEND / "fieldshift" / "datos" / "rps_erosion6.json"


def redondear(x: float, dec: int = 4) -> float:
    return round(float(x), dec)


def main():
    if len(sys.argv) > 1:
        data_dir = Path(sys.argv[1])
    else:
        temp_dir = Path(os.environ.get("TEMP", "/tmp")) / "erosion6" / "Erosion para Windows" / "DATA"
        if temp_dir.exists():
            data_dir = temp_dir
        else:
            raise FileNotFoundError(f"No se encontró la carpeta con los .ERD en {temp_dir}. Pasa la ruta como argumento.")

    print(f"Leyendo tablas .ERD desde {data_dir}...")
    rps_raw = leer_erosion6.leer(str(data_dir / "RPS.ERD"))
    erp_raw = leer_erosion6.leer(str(data_dir / "ERP.ERD"))
    factores_c_raw = leer_erosion6.leer(str(data_dir / "FACTORESC.ERD"))

    # 1. ERP (Efecto Residual de Pasturas)
    # mIdCultivo == 11 (Pastura), mIdRendimiento == 23 (MEDIO: 4.5 a 6.75 Mg/ha/año MS)
    # Por cultivo post-pastura (1 y 2) y por período (0 a 4)
    erp_por_cultivo: dict[str, dict[str, float]] = {}
    for r in erp_raw:
        if r["mIdCultivo"] == 11 and r["mIdRendimiento"] == 23:
            pos = str(r["mCantCultLuegoPast"])
            p = str(r["midPeriodo"])
            if pos not in erp_por_cultivo:
                erp_por_cultivo[pos] = {}
            erp_por_cultivo[pos][p] = redondear(r["mERP"], 3)

    # 2. Factores C precalculados
    # Campo natural: 0.02
    campo_natural_c = 0.02
    for fc in factores_c_raw:
        if "Campo Natural" in fc.get("nDescripcion", ""):
            campo_natural_c = redondear(fc.get("nFactorC", 0.02), 4)

    # 3. RPS para Siembra Directa (el manejo por defecto y recomendado)
    # Cultivo 1: Cereales de Invierno (Manejo 25: Siembra directa, Rendimiento 1: TODOS)
    # Cultivo 2: Sorgo o Maíz (Manejo 25: Siembra directa)
    # Cultivo 3: Soja (Manejo 27: Siembra Directa)
    # Cultivo 7: Girasol (Manejo 27: Siembra Directa)
    # Cultivo 11: Pastura Establecida o Consociada (Manejo 31: NO APLICA, Rendimiento 23: MEDIO)
    # Cultivo 12: Pastura no Consociada (Manejo 25: Siembra directa, Rendimiento 1: TODOS)

    # Cereales de invierno (Manejo 25)
    cereales = [r for r in rps_raw if r["mIdCultivo"] == 1 and r["mIdManejo"] == 25]
    cereales_rps = {"pasos_residuo": sorted(set(r["mPorcSueloCubResidLuegoSiembra"] for r in cereales)),
                    "p1": {}, "p2": {}, "p3": {}, "p4": {}}
    for r in cereales:
        res = str(r["mPorcSueloCubResidLuegoSiembra"])
        p = f"p{r['mIdPeriodo']}"
        cereales_rps[p][res] = redondear(r["mRps"], 4)

    # Soja (Manejo 27)
    soja = [r for r in rps_raw if r["mIdCultivo"] == 3 and r["mIdManejo"] == 27]
    soja_resids = sorted(set(r["mPorcSueloCubResidLuegoSiembra"] for r in soja))
    soja_rps = {
        "pasos_residuo_siembra": soja_resids,
        "p1": {}, "p2": {}, "p3": {},
        "pasos_rastrojo_p4": [20, 30, 40, 50, 60, 70, 80, 90],
        "p4": {},
    }
    for r in soja:
        res = str(r["mPorcSueloCubResidLuegoSiembra"])
        p = r["mIdPeriodo"]
        if p in ("1", "2"):
            soja_rps[f"p{p}"][res] = redondear(r["mRps"], 4)
        elif p == "3":
            # Si hay varias coberturas aéreas, tomamos 90 % (cobertura típica en floración/llenado) o la única
            a3 = r.get("mPorcSueloCubParteAerea3", 0)
            if a3 == 90 or a3 == 0 or res not in soja_rps["p3"]:
                soja_rps["p3"][res] = redondear(r["mRps"], 4)
        elif p == "4":
            # Período 4 está tabulado por % de suelo cubierto por el rastrojo dejado (aerea4)
            a4 = r.get("mPorcSueloCubParteAerea4", 0)
            if a4 > 0 and str(a4) not in soja_rps["p4"]:
                soja_rps["p4"][str(a4)] = redondear(r["mRps"], 4)

    # Maíz o Sorgo (Manejo 25)
    maiz = [r for r in rps_raw if r["mIdCultivo"] == 2 and r["mIdManejo"] == 25]
    maiz_resids = sorted(set(r["mPorcSueloCubResidLuegoSiembra"] for r in maiz))
    maiz_rps = {
        "pasos_residuo_siembra": maiz_resids,
        "p1": {}, "p2": {}, "p3": {},
        "pasos_rastrojo_p4": [20, 30, 40, 50, 60, 70, 80, 90],
        "p4": {},
    }
    for r in maiz:
        res = str(r["mPorcSueloCubResidLuegoSiembra"])
        p = r["mIdPeriodo"]
        if p in ("1", "2"):
            maiz_rps[f"p{p}"][res] = redondear(r["mRps"], 4)
        elif p == "3":
            a3 = r.get("mPorcSueloCubParteAerea3", 0)
            if a3 == 90 or a3 == 0 or res not in maiz_rps["p3"]:
                maiz_rps["p3"][res] = redondear(r["mRps"], 4)
        elif p == "4":
            a4 = r.get("mPorcSueloCubParteAerea4", 0)
            if a4 > 0 and str(a4) not in maiz_rps["p4"]:
                maiz_rps["p4"][str(a4)] = redondear(r["mRps"], 4)

    # Girasol (Manejo 27)
    girasol = [r for r in rps_raw if r["mIdCultivo"] == 7 and r["mIdManejo"] == 27]
    girasol_resids = sorted(set(r["mPorcSueloCubResidLuegoSiembra"] for r in girasol))
    girasol_rps = {"pasos_residuo": girasol_resids, "p1": {}, "p2": {}, "p3": {}, "p4": {}}
    for r in girasol:
        res = str(r["mPorcSueloCubResidLuegoSiembra"])
        p = r["mIdPeriodo"]
        if p in ("1", "2", "4"):
            girasol_rps[f"p{p}"][res] = redondear(r["mRps"], 4)
        elif p == "3":
            a3 = r.get("mPorcSueloCubParteAerea3", 0)
            if a3 == 90 or a3 == 96 or res not in girasol_rps["p3"]:
                girasol_rps["p3"][res] = redondear(r["mRps"], 4)

    # Pastura no Consociada (Cultivo 12, Manejo 25 - año de siembra)
    pastura_nc = [r for r in rps_raw if r["mIdCultivo"] == 12 and r["mIdManejo"] == 25]
    pastura_nc_resids = sorted(set(r["mPorcSueloCubResidLuegoSiembra"] for r in pastura_nc))
    pastura_nc_rps = {"pasos_residuo": pastura_nc_resids, "p1": {}, "p2": {}, "p3": {}, "p4": {}}
    for r in pastura_nc:
        res = str(r["mPorcSueloCubResidLuegoSiembra"])
        p = f"p{r['mIdPeriodo']}"
        pastura_nc_rps[p][res] = redondear(r["mRps"], 4)

    # Pastura Establecida o Consociada (Cultivo 11, Manejo 31, Rendimiento 23 MEDIO)
    pastura_cons = [r for r in rps_raw if r["mIdCultivo"] == 11 and r["mIdManejo"] == 31 and r["mIdRendimiento"] == 23]
    pastura_cons_rps = redondear(pastura_cons[0]["mRps"], 4) if pastura_cons else 0.03

    # 4. Colza (datos científicos locales de Agrociencia Uruguay v23 n2, 2019)
    colza_rps = {
        "fuente": "Agrociencia Uruguay v23 n2 (2019), pág. 124-135",
        "url": "http://www.scielo.edu.uy/pdf/agro/v23n2/2301-1548-agro-23-02-124.pdf",
        "periodos": {"p1": 0.142, "p2": 0.079, "p3": 0.032, "p4": 0.040},
    }

    datos = {
        "encabezado": {
            "fuente": "Programa Erosión 6.0 USLE-RUSLE (Facultad de Agronomía, UdelaR / MGAP)",
            "url": "https://www.gub.uy/ministerio-ganaderia-agricultura-pesca/politicas-y-gestion/programa-erosion-60-usle-rusle",
            "fecha_descarga": "2026-11-15",
            "script_generador": "app/backend/scripts/extraer_rps.py",
            "descripcion": (
                "Tablas derivadas de relaciones de pérdida de suelo (RPS), efecto residual de pasturas (ERP) "
                "y factores C precalculados de Erosión 6.0 para siembra directa, complementadas con datos de "
                "colza de Agrociencia Uruguay v23 n2."
            ),
        },
        "rps": {
            "cereales_invierno": cereales_rps,
            "soja": soja_rps,
            "sorgo_o_maiz": maiz_rps,
            "girasol": girasol_rps,
            "pastura_no_consociada": pastura_nc_rps,
            "pastura_establecida": pastura_cons_rps,
            "colza": colza_rps,
        },
        "erp": erp_por_cultivo,
        "precalculados": {
            "campo_natural": campo_natural_c,
        },
    }

    SALIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA_JSON, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    print(f"Archivo guardado exitosamente en {SALIDA_JSON} ({SALIDA_JSON.stat().st_size} bytes).")


if __name__ == "__main__":
    main()
