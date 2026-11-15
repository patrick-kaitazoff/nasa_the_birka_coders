"""Lectura de los archivos que sube el productor.

- Análisis de suelo: CSV, Excel o PDF de laboratorio. Se buscan pH, materia orgánica (o carbono
  orgánico), fósforo Bray I, potasio, arena, limo, arcilla y el nombre del potrero/lote.
- Estación meteorológica: CSV o Excel con fecha y lluvia/temperaturas (diario, horario o cada 10
  minutos, como exportan Davis WeatherLink o Pessl FieldClimate). Se pasa a diario y se compara
  con NASA POWER en los días en común.
- Historial de cultivos: CSV con año, potrero, cultivo de invierno y de verano.

Las imágenes y los PDF escaneados necesitan la IA; sin ella se pide
cargar los valores a mano.
"""

from __future__ import annotations

import io
import re
import unicodedata

import numpy as np
import pandas as pd

from .analisis import clima as clima_mod


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9%]+", " ", s).strip()


def leer_tabla(nombre: str, contenido: bytes) -> pd.DataFrame:
    ext = nombre.lower().rsplit(".", 1)[-1]
    if ext in ("xlsx", "xlsm", "xls"):
        return pd.read_excel(io.BytesIO(contenido))
    texto = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = contenido.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    texto = texto or contenido.decode("utf-8", "ignore")
    muestra = texto[:5000]
    sep = max([";", ",", "\t", "|"], key=lambda c: muestra.count(c))
    lineas = texto.splitlines()
    # saltear líneas de encabezado de la estación hasta la fila con más separadores
    conteos = [l.count(sep) for l in lineas[:40]]
    maximo = max(conteos) if conteos else 0
    inicio = next((i for i, c in enumerate(conteos) if c == maximo and c > 0), 0)
    decimal = "," if sep == ";" else "."
    return pd.read_csv(io.StringIO("\n".join(lineas[inicio:])), sep=sep, decimal=decimal,
                       engine="python", on_bad_lines="skip")


# --------------------------------------------------------------------------------------------
# Qué es el archivo
# --------------------------------------------------------------------------------------------

CLAVES_SUELO = {
    "ph": ["ph", "ph agua", "ph h2o", "ph en agua"],
    "materia_organica": ["materia organica", "mo", "m o", "mo %", "m o %", "materia organica %"],
    "carbono_organico": ["carbono organico", "co", "c org", "c o", "carbono", "corg", "c organico"],
    "fosforo_bray": ["p bray", "bray", "fosforo", "p bray i", "p ppm", "fosforo bray", "p", "p bray 1"],
    "potasio": ["k", "potasio", "k meq", "k intercambiable", "k meq 100g", "potasio intercambiable"],
    "arena": ["arena", "arena %", "sand"],
    "limo": ["limo", "limo %", "silt"],
    "arcilla": ["arcilla", "arcilla %", "clay"],
    "nombre": ["muestra", "potrero", "lote", "chacra", "seccion", "identificacion", "id", "campo", "padron"],
    "profundidad": ["profundidad", "prof", "horizonte"],
}
CLAVES_ESTACION = {
    "fecha": ["fecha", "date", "fecha hora", "datetime", "timestamp", "dia", "time", "fecha y hora"],
    "hora": ["hora", "hour"],
    "lluvia": ["lluvia", "precipitacion", "rain", "precip", "pp", "lluvia mm", "rain mm", "precipitation"],
    "tmax": ["tmax", "temp max", "temperatura maxima", "max temp", "t max", "hi temp", "high temp", "maxima"],
    "tmin": ["tmin", "temp min", "temperatura minima", "min temp", "t min", "low temp", "minima"],
    "tmed": ["temp", "temperatura", "temp out", "t aire", "air temp", "temperature", "tmed", "temp media"],
}


def _columna(df: pd.DataFrame, opciones: list[str]) -> str | None:
    cols = {c: _norm(c) for c in df.columns}
    for o in opciones:  # coincidencia exacta primero
        for c, n in cols.items():
            if n == o:
                return c
    for o in opciones:
        if len(o) < 3:
            continue
        for c, n in cols.items():
            if n.startswith(o) or f" {o}" in f" {n}":
                return c
    return None


def clasificar(df: pd.DataFrame) -> str:
    suelo = sum(_columna(df, CLAVES_SUELO[k]) is not None for k in ("ph", "materia_organica", "carbono_organico", "fosforo_bray", "potasio", "arcilla"))
    est = sum(_columna(df, CLAVES_ESTACION[k]) is not None for k in ("lluvia", "tmax", "tmin", "tmed"))
    tiene_fecha = _columna(df, CLAVES_ESTACION["fecha"]) is not None
    norm_cols = " ".join(_norm(c) for c in df.columns)
    if ("invierno" in norm_cols or "verano" in norm_cols or "cultivo" in norm_cols) and ("ano" in norm_cols or "anio" in norm_cols or "zafra" in norm_cols):
        return "historial"
    if suelo >= 2 and suelo >= est:
        return "analisis_suelo"
    if tiene_fecha and est >= 1:
        return "estacion"
    return "desconocido"


# --------------------------------------------------------------------------------------------
# Análisis de suelo
# --------------------------------------------------------------------------------------------


def _num(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    s = str(v).strip().replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group()) if m else None


def suelo_desde_tabla(df: pd.DataFrame) -> list[dict]:
    cols = {k: _columna(df, v) for k, v in CLAVES_SUELO.items()}
    filas = []
    for _, fila in df.iterrows():
        d = {}
        for k, c in cols.items():
            if c is None:
                continue
            d[k] = str(fila[c]).strip() if k in ("nombre", "profundidad") else _num(fila[c])
        if d.get("materia_organica") is None and d.get("carbono_organico") is not None:
            d["materia_organica"] = round(d["carbono_organico"] * 1.724, 2)
        if d.get("potasio") and d["potasio"] > 5:  # vino en ppm
            d["potasio"] = round(d["potasio"] / 391, 2)
        if any(d.get(k) is not None for k in ("ph", "materia_organica", "fosforo_bray", "potasio")):
            filas.append({k: v for k, v in d.items() if v not in (None, "nan")})
    return filas


PATRONES_PDF = {
    "ph": r"\bpH\s*(?:\(?\s*(?:H2O|agua)\s*\)?)?\s*[:=]?\s*(\d+[.,]\d+)",
    "materia_organica": r"(?:materia\s+org[aá]nica|M\.?\s?O\.?)\s*(?:\(?%\)?)?\s*[:=]?\s*(\d+[.,]?\d*)",
    "carbono_organico": r"(?:carbono\s+org[aá]nico|C\.?\s?O\.?|C\s?org)\s*(?:\(?%\)?)?\s*[:=]?\s*(\d+[.,]?\d*)",
    "fosforo_bray": r"(?:P\s*\(?\s*Bray\s*(?:I|1)?\s*\)?|f[oó]sforo(?:\s+Bray)?)\s*(?:\(?\s*(?:ppm|mg/kg|µg/g)\s*\)?)?\s*[:=]?\s*(\d+[.,]?\d*)",
    "potasio": r"(?:\bK\b|potasio)\s*(?:intercambiable)?\s*(?:\(?\s*meq\s*/\s*100\s*g\s*\)?)?\s*[:=]?\s*(\d+[.,]\d+)",
    "arena": r"arena\s*(?:\(?%\)?)?\s*[:=]?\s*(\d+[.,]?\d*)",
    "limo": r"limo\s*(?:\(?%\)?)?\s*[:=]?\s*(\d+[.,]?\d*)",
    "arcilla": r"arcilla\s*(?:\(?%\)?)?\s*[:=]?\s*(\d+[.,]?\d*)",
}


def texto_pdf(contenido: bytes) -> str:
    from pypdf import PdfReader

    lector = PdfReader(io.BytesIO(contenido))
    return "\n".join((p.extract_text() or "") for p in lector.pages[:20])


def suelo_desde_texto(texto: str) -> dict:
    d = {}
    for k, pat in PATRONES_PDF.items():
        m = re.search(pat, texto, flags=re.IGNORECASE)
        if m:
            d[k] = _num(m.group(1))
    if d.get("materia_organica") is None and d.get("carbono_organico") is not None:
        d["materia_organica"] = round(d["carbono_organico"] * 1.724, 2)
    if d.get("ph") is not None and not (3 <= d["ph"] <= 10):
        d.pop("ph")
    return d


# --------------------------------------------------------------------------------------------
# Estación meteorológica
# --------------------------------------------------------------------------------------------


def estacion_desde_tabla(df: pd.DataFrame) -> pd.DataFrame:
    c_fecha = _columna(df, CLAVES_ESTACION["fecha"])
    c_hora = _columna(df, CLAVES_ESTACION["hora"])
    if c_fecha is None:
        raise ValueError("No encontré una columna de fecha.")
    texto_fecha = df[c_fecha].astype(str)
    if c_hora and c_hora != c_fecha:
        texto_fecha = texto_fecha + " " + df[c_hora].astype(str)
    fechas = pd.to_datetime(texto_fecha, dayfirst=True, errors="coerce")
    if fechas.isna().mean() > 0.5:
        fechas = pd.to_datetime(texto_fecha, dayfirst=False, errors="coerce")
    datos = pd.DataFrame({"fecha": fechas})
    for k in ("lluvia", "tmax", "tmin", "tmed"):
        c = _columna(df, CLAVES_ESTACION[k])
        if c is not None:
            datos[k] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce")
    datos = datos.dropna(subset=["fecha"])
    datos["dia"] = datos["fecha"].dt.normalize()
    por_dia = datos.groupby("dia")
    salida = pd.DataFrame(index=por_dia.size().index)
    registros_dia = por_dia.size().median()
    if "lluvia" in datos:
        salida["lluvia"] = por_dia["lluvia"].sum(min_count=1)
    if "tmax" in datos:
        salida["tmax"] = por_dia["tmax"].max()
    elif "tmed" in datos and registros_dia > 1:
        salida["tmax"] = por_dia["tmed"].max()
    if "tmin" in datos:
        salida["tmin"] = por_dia["tmin"].min()
    elif "tmed" in datos and registros_dia > 1:
        salida["tmin"] = por_dia["tmed"].min()
    salida.attrs["registros_por_dia"] = float(registros_dia)
    return salida


def comparar_con_power(est: pd.DataFrame, power: dict) -> dict:
    """Días en común entre la estación y NASA POWER: sesgo de lluvia y temperaturas, heladas. Contra POWER tal cual
    (sin la corrección con INUMET), porque los textos dicen «NASA POWER»."""
    serie = clima_mod.preparar(power, corregir_temperatura=False)
    pw = pd.DataFrame(
        {"lluvia": serie.lluvia, "tmax": serie.tmax, "tmin": serie.tmin},
        index=pd.to_datetime([f.isoformat() for f in serie.fechas]),
    )
    comun = est.add_suffix("_est").join(pw.add_suffix("_nasa"), how="inner")
    out: dict = {
        "dias_estacion": int(len(est)),
        "dias_en_comun": int(len(comun)),
        "desde": est.index.min().date().isoformat() if len(est) else None,
        "hasta": est.index.max().date().isoformat() if len(est) else None,
        "registros_por_dia": est.attrs.get("registros_por_dia"),
    }
    if len(comun) < 20:
        out["conclusion"] = ("Hay menos de 20 días en común con NASA POWER (que tiene ~5 días de atraso): "
                             "no alcanza para comparar.")
        return out
    concl = []
    if "lluvia_est" in comun:
        c = comun.dropna(subset=["lluvia_est"])
        le, ln = float(c["lluvia_est"].sum()), float(c["lluvia_nasa"].sum())
        mens = c.resample("MS")[["lluvia_est", "lluvia_nasa"]].sum()
        corr = float(mens.corr().iloc[0, 1]) if len(mens) >= 3 else None
        out["lluvia"] = {"estacion_mm": round(le), "nasa_mm": round(ln),
                         "diferencia_pct": round((le / ln - 1) * 100) if ln > 0 else None,
                         "correlacion_mensual": round(corr, 2) if corr is not None and not np.isnan(corr) else None}
        if ln > 0:
            dif = (le / ln - 1) * 100
            if abs(dif) < 3:
                concl.append(f"Tu estación y {serie.fuente_lluvia} midieron prácticamente la misma lluvia en {len(c)} días "
                             f"({le:.0f} y {ln:.0f} mm).")
            else:
                concl.append(f"Tu estación midió {abs(dif):.0f} % {'más' if dif > 0 else 'menos'} lluvia que {serie.fuente_lluvia} "
                             f"en los mismos {len(c)} días ({le:.0f} contra {ln:.0f} mm).")
    for k, nombre in (("tmin", "mínimas"), ("tmax", "máximas")):
        if f"{k}_est" in comun:
            c = comun.dropna(subset=[f"{k}_est"])
            if len(c):
                sesgo = float((c[f"{k}_est"] - c[f"{k}_nasa"]).mean())
                out[k] = {"sesgo_c": round(sesgo, 1)}
                if abs(sesgo) >= 0.5:
                    concl.append(f"Las {nombre} de tu campo son {abs(sesgo):.1f}".replace(".", ",") + f" °C más {'altas' if sesgo > 0 else 'bajas'} que las de NASA POWER.")
    if "tmin_est" in comun:
        c = comun.dropna(subset=["tmin_est"])
        he, hn = int((c["tmin_est"] <= 0).sum()), int((c["tmin_nasa"] <= 0).sum())
        out["heladas"] = {"estacion": he, "nasa": hn}
        if he > hn:
            concl.append(f"Tu estación registró {he} heladas contra {hn} de NASA POWER: el campo es más helador que el promedio "
                         "de la zona (unos 50 km). El análisis suma ese riesgo a los cultivos sensibles.")
            out["campo_mas_helador"] = True
    out["conclusion"] = " ".join(concl) or "Tu estación y NASA POWER coinciden razonablemente."
    return out


# --------------------------------------------------------------------------------------------
# Historial
# --------------------------------------------------------------------------------------------

SINONIMOS_CULTIVO = {
    "soja": "soja", "soja 1": "soja", "soja primera": "soja", "soja de primera": "soja", "soja 2": "soja2",
    "soja segunda": "soja2", "soja de segunda": "soja2", "maiz": "maiz", "maiz 1": "maiz", "maiz 2": "maiz2",
    "maiz segunda": "maiz2", "maiz de segunda": "maiz2", "maiz primera": "maiz", "maiz de primera": "maiz", "sorgo": "sorgo", "girasol": "girasol", "trigo": "trigo", "cebada": "cebada",
    "colza": "colza", "canola": "colza", "avena": "cobertura", "avena negra": "cobertura", "raigras": "verdeo",
    "cobertura": "cobertura", "cultivo de cobertura": "cobertura", "verdeo": "verdeo", "pradera": "pradera",
    "pastura": "pradera", "alfalfa": "alfalfa", "campo natural": "campo_natural", "natural": "campo_natural",
    "barbecho": "barbecho", "nada": "barbecho", "descanso": "barbecho", "sorgo forrajero": "sorgo_forrajero",
}


def cultivo_desde_texto(t: str | None) -> str | None:
    if not t:
        return None
    n = _norm(t)
    if n in SINONIMOS_CULTIVO:
        return SINONIMOS_CULTIVO[n]
    for k in sorted(SINONIMOS_CULTIVO, key=len, reverse=True):
        if k in n:
            return SINONIMOS_CULTIVO[k]
    return None


FORRAJERAS = {"pradera", "alfalfa", "verdeo", "sorgo_forrajero"}
GENERICOS = {"soja": {"soja", "soja2"}, "maiz": {"maiz", "maiz2"}}


def cultivos_en_texto(t: str | None) -> set[str]:
    """Todos los cultivos que nombra un texto libre ("maíz y soja", "me falló el forraje").
    "Soja" o "maíz" sin más incluyen las dos épocas; "forraje" o "pasturas", las forrajeras."""
    if not t:
        return set()
    n = f" {_norm(t)} "
    out: set[str] = set()
    if any(w in n for w in (" forraje", " pastura", " verdeos", " praderas")):
        out |= FORRAJERAS
    for k in sorted(SINONIMOS_CULTIVO, key=len, reverse=True):
        if k in ("nada", "natural", "descanso"):
            continue
        i = n.find(f" {k}")
        def entera(j: int) -> bool:  # palabra entera, admitiendo el plural ("sojas", "maices" no)
            resto = n[j + 1 + len(k): j + 3 + len(k)]
            return not resto[:1].isalpha() or (resto[:1] == "s" and not resto[1:2].isalpha())
        while i >= 0 and not entera(i):
            i = n.find(f" {k}", i + 1)
        if i < 0:
            continue
        cod = SINONIMOS_CULTIVO[k]
        out |= GENERICOS.get(k, {cod}) if k in GENERICOS else {cod}
        n = n[:i] + " " * (len(k) + 1) + n[i + 1 + len(k):]  # que "soja" no vuelva a contar en "soja de segunda"
    return out


def historial_desde_tabla(df: pd.DataFrame) -> list[dict]:
    c_anio = _columna(df, ["ano", "anio", "zafra", "year", "campana"])
    c_sec = _columna(df, CLAVES_SUELO["nombre"])
    c_inv = _columna(df, ["invierno", "cultivo invierno", "winter"])
    c_ver = _columna(df, ["verano", "cultivo verano", "summer"])
    out = []
    for _, f in df.iterrows():
        anio = _num(f[c_anio]) if c_anio else None
        out.append({
            "seccion": str(f[c_sec]).strip() if c_sec else None,
            "anio": int(anio) if anio else None,
            "invierno": cultivo_desde_texto(f[c_inv]) if c_inv else None,
            "verano": cultivo_desde_texto(f[c_ver]) if c_ver else None,
        })
    return [h for h in out if h["anio"]]


# --------------------------------------------------------------------------------------------
# Entrada única
# --------------------------------------------------------------------------------------------


def procesar(nombre: str, contenido: bytes, power: dict | None = None, tipo_esperado: str | None = None) -> dict:
    ext = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    if ext == "pdf":
        texto = texto_pdf(contenido)
        valores = suelo_desde_texto(texto)
        if len([k for k in valores if k in ("ph", "materia_organica", "fosforo_bray", "potasio")]) >= 2:
            return {"tipo": "analisis_suelo", "filas": [valores], "metodo": "texto del PDF",
                    "texto_extraido": texto[:3000]}
        return {"tipo": "necesita_ia", "motivo": "No pude leer los valores del PDF (puede estar escaneado).",
                "texto_extraido": texto[:3000]}
    if ext in ("png", "jpg", "jpeg", "webp", "gif", "heic"):
        return {"tipo": "necesita_ia", "motivo": "Es una imagen: hay que leerla con IA o cargar los valores a mano."}
    if ext not in ("csv", "txt", "xlsx", "xls", "xlsm", "tsv"):
        return {"tipo": "desconocido", "motivo": f"No sé leer archivos .{ext} todavía."}
    df = leer_tabla(nombre, contenido)
    tipo = tipo_esperado if tipo_esperado in ("analisis_suelo", "estacion", "historial") else clasificar(df)
    if tipo == "analisis_suelo":
        filas = suelo_desde_tabla(df)
        return {"tipo": tipo, "filas": filas, "columnas": [str(c) for c in df.columns]}
    if tipo == "estacion":
        est = estacion_desde_tabla(df)
        res: dict = {"tipo": tipo, "dias": int(len(est)),
                     "desde": est.index.min().date().isoformat() if len(est) else None,
                     "hasta": est.index.max().date().isoformat() if len(est) else None,
                     "variables": [c for c in est.columns]}
        if power is not None and len(est):
            res["comparacion"] = comparar_con_power(est, power)
        mensual = est.resample("MS").agg({c: ("sum" if c == "lluvia" else "mean") for c in est.columns})
        res["mensual"] = [
            {"mes": i.strftime("%Y-%m"), **{c: (None if pd.isna(v) else round(float(v), 1)) for c, v in fila.items()}}
            for i, fila in mensual.tail(36).iterrows()
        ]
        return res
    if tipo == "historial":
        return {"tipo": tipo, "filas": historial_desde_tabla(df)}
    return {"tipo": "desconocido", "columnas": [str(c) for c in df.columns],
            "motivo": "No reconocí las columnas como análisis de suelo, estación o historial."}
