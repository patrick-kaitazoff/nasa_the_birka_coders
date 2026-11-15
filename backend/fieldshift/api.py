"""API web de Seasons Ahead (FastAPI). Sirve también el frontend compilado si existe.

Correr: uvicorn fieldshift.api:app --reload --port 8000 (desde app/backend)
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import mimetypes
import os
import re
import unicodedata
import queue
import threading
import traceback
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agente import chat as chat_mod
from .agente import estado, guiado, puente, restricciones
from .analisis import clima as clima_mod
from .analisis import plan as plan_mod
from .analisis.cultivos import APORTES, catalogo_publico
from .analisis.rotaciones import ROTACIONES
from .fuentes import buscar as buscar_mod
from .fuentes import hls, mgap, power, region, smap, ssurgo
from . import acceso, archivos

app = FastAPI(title="Seasons Ahead — Asesor de campo", version="0.1.0")


def _preparar_gemini() -> None:
    """La librería de Gemini (google-genai) es grande y en Vercel se compila desde el código en cada arranque en frío
    (los SyntaxWarning de google/genai/types.py en los registros): uno o dos segundos que pagaba el primer mensaje del
    chat. Se importa en segundo plano apenas arranca el servidor, mientras se atiende lo que sea."""
    try:
        import google.genai  # noqa: F401
        from google.genai import types  # noqa: F401
    except Exception:  # noqa: BLE001
        pass


if chat_mod.ia_disponible():
    threading.Thread(target=_preparar_gemini, name="preparar-gemini", daemon=True).start()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# contraseña para entrar a lo publicado (ver acceso.py); en la PC no pide nada
app.middleware("http")(acceso.controlar)


def _sse(eventos: Iterator[dict]) -> StreamingResponse:
    """Corre el generador en un hilo y manda cada evento como Server-Sent Event."""
    q: queue.Queue = queue.Queue()
    FIN = object()

    def trabajar():
        try:
            for ev in eventos:
                q.put(ev)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()  # el detalle va a la consola del servidor; a la persona, un mensaje en castellano
            q.put({"tipo": "error", "mensaje": f"Error interno: {e}"})
            q.put({"tipo": "fin"})
        finally:
            q.put(FIN)

    # con una copia del contexto del pedido: en Vercel la Runtime Cache (puente remoto) vive en contextvars y un
    # hilo nuevo no los hereda
    threading.Thread(target=contextvars.copy_context().run, args=(trabajar,), daemon=True).start()

    def emitir():
        while True:
            try:
                ev = q.get(timeout=15)
            except queue.Empty:
                yield ": sigo acá\n\n"  # mantiene viva la conexión durante análisis largos
                continue
            if ev is FIN:
                break
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(emitir(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/salud")
def salud(puente_pedido: bool = Query(False, alias="puente")):
    if puente.activo(puente_pedido):
        return {"ok": True, "ia": True, "modelo": "puente de prueba"}
    # Si el servidor tiene con qué pedir la lluvia de GPM IMERG (sin salir a internet ni mostrar nada)
    lluvia_imerg = bool(os.environ.get("EARTHDATA_TOKEN") or (os.environ.get("EARTHDATA_USER") and os.environ.get("EARTHDATA_PASS")))
    return {"ok": True, "ia": chat_mod.ia_disponible(), "modelo": chat_mod.MODELO if chat_mod.ia_disponible() else None,
            "lluvia_imerg": lluvia_imerg}


@app.get("/api/pais")
def pais_visitante(x_vercel_ip_country: str | None = Header(None)):
    """País de quien visita, sacado de la IP. Vercel lo pone en la cabecera x-vercel-ip-country sin costo ni
    llamada afuera; en la PC no viene y se devuelve null (la pantalla se queda con lo que adivinó por la zona horaria).
    No se guarda en ningún lado ni se cachea en la CDN: depende de quién pide."""
    p = (x_vercel_ip_country or "").strip().upper()[:2]
    return Response(json.dumps({"pais": p or None}), media_type="application/json",
                    headers={"Cache-Control": "private, no-store"})


@app.get("/api/catalogo")
def catalogo():
    return {
        "cultivos": catalogo_publico(),
        "aportes": APORTES,
        "rotaciones": [{"id": r.id, "nombre": r.nombre, "descripcion": r.descripcion, "tipo": r.tipo,
                        "anios": [list(p) for p in r.anios]} for r in ROTACIONES.values()],
        "departamentos": mgap.DEPARTAMENTOS,
    }


@app.get("/api/departamentos")
def departamentos():
    """Límites de los 19 departamentos (MGAP-DGRN simplificados a 0,004° con coverage_simplify).
    Copia guardada en el repo (scripts/actualizar_departamentos.py la renueva) para servir en < 10 ms."""
    return FileResponse(Path(__file__).parent / "datos" / "departamentos_uy.json", media_type="application/json",
                        headers=_un_dia())


class Punto(BaseModel):
    lat: float
    lon: float


@app.get("/api/estados-us")
def estados_us():
    """Límites de los 48 estados contiguos de EE. UU. y DC (Census TIGERweb 1:20M, simplificados). Copia en el repo
    (scripts/actualizar_estados_us.py la renueva)."""
    return FileResponse(Path(__file__).parent / "datos" / "estados_us.json", media_type="application/json",
                        headers=_un_dia())


@app.get("/api/condados-us/{fips}")
def condados_us(fips: str):
    """Condados de un estado de EE. UU. (Census TIGERweb 1:5M), por el FIPS de dos cifras del estado (Iowa = 19)."""
    ruta = Path(__file__).parent / "datos" / "condados_us" / f"{fips}.json"
    if not (len(fips) == 2 and fips.isdigit() and ruta.is_file()):
        raise HTTPException(404, "No tengo ese estado (solo los 48 contiguos y DC).")
    return FileResponse(ruta, media_type="application/json",
                        headers=_un_dia())


@app.post("/api/lote-cdl")
def lote_cdl(p: Punto):
    """El lote que contiene el punto según el Cropland Data Layer (EE. UU.): el par del padrón del MGAP."""
    from .fuentes import cdl

    if region.pais(p.lat, p.lon) != "US":
        raise HTTPException(400, "El lote por Cropland Data Layer es solo para EE. UU.")
    r = cdl.lote_en_punto(p.lat, p.lon)
    if not r.get("ok"):
        raise HTTPException(404, r.get("error", "No encontré un lote ahí."))
    return r


@app.get("/api/padron")
def padron(departamento: str, numero: int):
    try:
        r = mgap.padron(departamento, numero)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"El servidor del MGAP no respondió: {e}") from e
    if not r.get("ok"):
        raise HTTPException(404, r.get("error", "No encontrado"))
    return r


@app.get("/api/buscar")
def buscar(q: str = Query("", max_length=120)):
    """Buscador del paso 1: un pueblo, un paraje, una calle o «ruta 5 km 200», con su departamento
    (IDE Uruguay, mojones del MTOP y, si no hay nada, OpenStreetMap). Ver fuentes/buscar.py."""
    return {"resultados": buscar_mod.buscar(q)}


@app.get("/api/lugares")
def lugares():
    """Ciudades, villas, pueblos, caseríos y parajes de Uruguay (OpenStreetMap), para poner nombres en el mapa.
    Copia guardada en el repo (scripts/actualizar_lugares.py la renueva): la demo no depende de Overpass."""
    return FileResponse(Path(__file__).parent / "datos" / "lugares_uy.json", media_type="application/json",
                        headers=_un_dia())


@app.get("/api/lugares-us")
def lugares_us():
    """Ciudades y pueblos de los 48 estados contiguos de EE. UU. (GeoNames, CC BY 4.0), de más a menos habitantes.
    Copia guardada en el repo (scripts/actualizar_lugares_us.py la renueva)."""
    return FileResponse(Path(__file__).parent / "datos" / "lugares_us.json", media_type="application/json",
                        headers=_un_dia())


@app.get("/api/rutas")
def rutas():
    """Rutas nacionales de Uruguay (OpenStreetMap) con puntos para poner su número, para guiarse sobre la foto
    satelital. Copia guardada en el repo (scripts/actualizar_rutas.py la renueva)."""
    return FileResponse(Path(__file__).parent / "datos" / "rutas_uy.json", media_type="application/json",
                        headers=_un_dia())


@app.get("/api/mar")
def mar():
    """El mar frente a Uruguay (línea de costa de OpenStreetMap): el mapa lo pinta parejo de cerca, donde la foto
    de Esri trae el agua en cuadrados. Copia guardada en el repo (scripts/actualizar_mar.py la renueva)."""
    return FileResponse(Path(__file__).parent / "datos" / "mar_uy.json", media_type="application/json",
                        headers=_un_dia())


def _slug_depto(nombre: str) -> str:
    n = unicodedata.normalize("NFKD", nombre).encode("ASCII", "ignore").decode("utf-8")
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


@app.get("/api/caminos/{departamento}")
def caminos(departamento: str):
    """Caminos departamentales y vecinales de un departamento (OpenStreetMap),
    guardados por departamento para descargarse solo cuando la persona elige o se acerca a ese departamento.
    Copia guardada en datos/caminos/{slug}.json (scripts/actualizar_caminos.py la renueva)."""
    slug = _slug_depto(departamento)
    archivo = Path(__file__).parent / "datos" / "caminos" / f"{slug}.json"
    if not archivo.exists():
        raise HTTPException(404, f"No hay caminos guardados para el departamento '{departamento}'")
    return FileResponse(archivo, media_type="application/json",
                        headers=_un_dia())


@app.get("/api/hls")
def hls_fechas(oeste: float, sur: float, este: float, norte: float):
    """Días con imagen limpia de HLS (30 m) sobre el campo, para el fondo "NASA" del mapa."""
    try:
        return hls.fechas_limpias((oeste, sur, este, norte))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"No respondió el catálogo de la NASA (CMR): {e}") from e


@app.post("/api/suelo")
def suelo(p: Punto):
    # En EE. UU., la carta de suelos SSURGO del USDA-NRCS
    if region.pais(p.lat, p.lon) == "US":
        return ssurgo.suelo_punto(p.lat, p.lon)
    return mgap.suelo_punto(p.lat, p.lon)


class Area(BaseModel):
    geometria: dict


@app.post("/api/suelos-area")
def suelos_area(a: Area):
    """Grupos de suelo CONEAT dentro de un contorno dibujado (para ver si una sección mezcla suelos). En EE. UU., las unidades de SSURGO, con su nombre en el lugar del grupo CONEAT."""
    try:
        from shapely.geometry import shape as _shape

        g = _shape(a.geometria)
        if region.pais(g.centroid.y, g.centroid.x) == "US":
            partes = ssurgo.secciones_por_suelo(a.geometria, minimo_pct=0)
            total = sum(_shape(x["geometria"]).area for x in partes) or 1
            return {"fuente": "USDA-NRCS SSURGO (Soil Data Access)",
                    "partes": [{"grupo_coneat": x["muname"], "fraccion": round(_shape(x["geometria"]).area / total, 3),
                                "geometria": x["geometria"]} for x in partes]}
        return mgap.suelos_en_area(a.geometria)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"No respondió el servidor del MGAP: {e}") from e


class CampoPrecalentar(BaseModel):
    campo: dict


@app.post("/api/precalentar")
def precalentar(p: CampoPrecalentar):
    """Baja de antemano el clima, el suelo y el verdor de cada sección mientras sigue la entrevista, para que el
    análisis final no espere (ver plan.precalentar). El frontend lo llama sin esperar la respuesta."""
    return plan_mod.precalentar(p.campo)


@app.post("/api/proponer-partes")
def proponer_partes(a: Area):
    """Borrador de las partes del campo según cómo cambia el verde en la imagen de la NASA (HLS, 30 m)."""
    from .analisis import partes as partes_mod
    try:
        return partes_mod.proponer(a.geometria)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(502, f"No pude leer la imagen de la NASA: {e}") from e


@app.post("/api/clima")
def clima(p: Punto):
    pw = power.bajar_diario(p.lat, p.lon)
    return clima_mod.analizar(pw)


class PedidoEscenario(BaseModel):
    lat: float
    lon: float
    agua_util_mm: float = 120.0
    lluvia_pct: float = 0.0
    temp_c: float = 0.0
    cultivos: list[str] | None = None


@app.post("/api/escenario")
def escenario(p: PedidoEscenario):
    try:
        pw = power.bajar_diario(p.lat, p.lon)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(502, f"No pude bajar el clima de la NASA: {e}") from e
    return clima_mod.escenario(pw, p.agua_util_mm, p.lluvia_pct, p.temp_c, p.cultivos)


@app.get("/api/smap")
def humedad_smap(lat: float, lon: float, agua_util_mm: float = 120.0):
    """Humedad de raíces de SMAP L4, GLDAS 2.1 y su comparación con el balance de la app. No espera: si AppEEARS
    todavía no terminó, devuelve "pendiente" y el frontend vuelve a preguntar."""
    from .analisis import humedad
    from .fuentes import gldas as gldas_mod

    r = smap.estado(lat, lon)
    if r["estado"] != "listo":
        return r
    try:
        serie = clima_mod.serie_diaria(power.bajar_diario(lat, lon))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return {"estado": "error", "motivo": f"Tengo SMAP pero no pude bajar el clima de la NASA: {e}"}
    try:
        g = gldas_mod.consultar_gldas(lat, lon)
    except Exception:  # noqa: BLE001
        g = None
    return {"estado": "listo", "fuente": r["fuente"], **humedad.comparar(r["serie"], serie, agua_util_mm, gldas=g)}


@app.get("/api/ecostress")
def ecostress_diagnostico():
    """Diagnóstico de pasadas y heterogeneidad térmica intra-lote a 70 m de ECOSTRESS."""
    from .fuentes import ecostress as ecostress_mod

    return ecostress_mod.cargar_diagnostico_ecostress()


@app.get("/api/gaez")
def gaez_aptitud(lat: float, lon: float):
    """Aptitud de cada cultivo de secano según FAO GAEZ v4 en la celda (~9 km) del punto. Vacío fuera de Uruguay."""
    from .fuentes import gaez as gaez_mod

    return {"fuente": "FAO/IIASA GAEZ v4 (secano, insumo alto, clima 2011-2040 según 5 modelos con RCP 4.5; también 1981-2010)",
            "cultivos": gaez_mod.aptitud_punto(lat, lon)}


class PedidoRelieve(BaseModel):
    contorno: dict[str, Any]
    secciones: list[dict[str, Any]]
    r: float
    p: float = 1.0
    largo_m: float | None = None  # sin largo del productor, sale del relieve (camino del agua en SRTM)


@app.post("/api/relieve")
def relieve_campo(p: PedidoRelieve):
    """Relieve de SRTM, pendiente y erosión por cuadrado de 30 m (actual y con el plan), para Datos y el 3D."""
    from .analisis import relieve

    try:
        return relieve.analizar(p.contorno, p.secciones, p.r, p.p, p.largo_m)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(502, f"No pude armar el relieve de la NASA (SRTM): {e}") from e


class PedidoRangos(BaseModel):
    erosiones: list[dict[str, Any]]
    r_alternativas: list[float | None] = []


@app.post("/api/rango-erosion")
def rangos_erosion(p: PedidoRangos):
    """Rango de la erosión (Monte Carlo) de varias rotaciones, para análisis guardados antes de que se
    calculara (el campo de ejemplo)."""
    from .analisis import incertidumbre

    return {"rangos": [incertidumbre.rango_erosion(e, p.r_alternativas) for e in p.erosiones],
            "supuestos": incertidumbre.SUPUESTOS}


class SerieNdvi(BaseModel):
    mensual: list[dict[str, Any]]


@app.post("/api/descubierto")
def metodos_descubierto(p: SerieNdvi):
    """Los dos métodos de suelo descubierto sobre una serie mensual de NDVI (para análisis guardados antes
    de que existiera la comparación, como el campo de ejemplo)."""
    from .analisis import descubierto

    return descubierto.comparar(p.mensual)


class PedidoHistoria(BaseModel):
    campo: dict[str, Any]
    seccion_id: str | None = None
    correcciones: dict[str, str] | None = None
    # cultivos del plan por sección, temporada por temporada: {id: [["invierno", "trigo"], ["verano", "soja2"], …]}
    ciclos_plan: dict[str, list[list[str]]] | None = None


@app.post("/api/historia")
def historia_campo(p: PedidoHistoria):
    """Historia temporal 2000 → hoy: satélite MODIS, clima de NASA POWER y rotación propuesta."""
    from .analisis import historia as historia_mod

    try:
        return historia_mod.analizar_historia(p.campo, p.seccion_id, p.correcciones, p.ciclos_plan)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(502, f"No pude calcular la historia del campo: {e}") from e



@app.post("/api/archivo")
async def archivo(
    archivo: UploadFile = File(...),
    tipo_esperado: str | None = Form(None),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
):
    contenido = await archivo.read()
    if len(contenido) > 25 * 1024 * 1024:
        raise HTTPException(413, "El archivo pesa más de 25 MB.")
    nombre = archivo.filename or "archivo"
    pw = None
    if lat is not None and lon is not None:
        try:
            pw = power.bajar_diario(lat, lon)
        except Exception:  # noqa: BLE001
            pw = None
    try:
        r = archivos.procesar(nombre, contenido, pw, tipo_esperado)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"No pude leer el archivo: {e}") from e
    if r.get("tipo") == "necesita_ia":
        if chat_mod.ia_disponible():
            media = archivo.content_type or mimetypes.guess_type(nombre)[0] or "application/pdf"
            try:
                return chat_mod.extraer_con_ia(nombre, contenido, media)
            except Exception as e:  # noqa: BLE001
                r["motivo"] += f" La IA tampoco pudo: {e}"
        r["sugerencia"] = "Cargá los valores a mano en el formulario."
    return r


class PedidoAnalisis(BaseModel):
    campo: dict[str, Any]


@app.post("/api/analizar")
def analizar(p: PedidoAnalisis):
    campo = p.campo

    def eventos():
        for ev in plan_mod.analizar_campo_pasos(campo):
            if ev["tipo"] == "progreso":
                yield ev
            else:
                estado.guardar_analisis(campo.get("id", "campo"), ev["resultado"])
                yield {"tipo": "analisis", "resultado": ev["resultado"]}
        yield {"tipo": "fin"}

    return _sse(eventos())


class PedidoPlan(BaseModel):
    campo: dict[str, Any]
    eleccion: dict[str, str] | None = None
    # si el servidor no tiene el análisis guardado (otra máquina, campo de ejemplo), lo manda la app
    secciones: list[dict[str, Any]] | None = None
    temporadas: list[dict[str, Any]] | None = None


@app.post("/api/plan")
def rearmar_plan(p: PedidoPlan):
    res = estado.analisis_de(p.campo.get("id", "campo"))
    if not res and p.secciones and p.temporadas:
        res = {"secciones": p.secciones, "plan": {"temporadas": p.temporadas}}
    if not res:
        raise HTTPException(409, "Todavía no hay análisis de este campo.")
    campo = {**p.campo, "rotacion_elegida": {**(p.campo.get("rotacion_elegida") or {}), **(p.eleccion or {})}}
    plan = plan_mod.armar_plan(res["secciones"], res["plan"]["temporadas"], campo)
    res["plan"] = plan
    estado.guardar_analisis(p.campo.get("id", "campo"), res)
    return plan


class PedidoChat(BaseModel):
    campo: dict[str, Any]
    historial: list[dict[str, Any]] = []
    texto: str
    modo: str | None = None  # "ia" | "guiado"
    idioma: str = "es"  # "es" | "en": en inglés la IA contesta en inglés (el resto se traduce en la pantalla)
    puente: bool = False  # el chat se abrió con ?puente=1
    # el último análisis que tiene el navegador: el servidor lo puede no tener (campo de ejemplo, otra instancia de
    # Vercel, se reinició) y el asesor lo necesita para contestar «¿por qué?» sin volver a calcular todo
    analisis: dict[str, Any] | None = None
    # la tarjeta que la persona contestó con sus palabras en vez del formulario
    paso: str | None = None
    # el navegador ya tiene resultados (sin IA no se manda el análisis entero): «no quiero soja» recalcula en vez de
    # volver a la entrevista
    con_analisis: bool = False
    # el mensaje lo armó la app, no lo escribió la persona: «Listo, dibujé el contorno…», una tarjeta terminada u
    # omitida, «analizar de nuevo» al cambiar el campo. Eso lo resuelve siempre el modo guiado, sin la IA
    accion: bool = False


@app.post("/api/chat")
def chat(p: PedidoChat):
    if puente.activo(p.puente) and p.modo != "guiado":
        return _sse(puente.conversar(p.campo, p.texto))
    usar_ia = chat_mod.ia_disponible() and p.modo != "guiado"
    # el saludo del principio, con el campo vacío, es siempre el mismo: sale al instante del modo guiado, sin esperar
    # a la IA. La IA entra desde la
    # primera respuesta de la persona.
    # La IA
    # se llama solo para lo que la persona escribe. Los pasos de la entrevista que avanzan con las tarjetas y el mapa,
    # los mensajes internos («__inicio») y «analizar de nuevo» van por el modo guiado, que da lo mismo sin esperar.
    if usar_ia and (p.accion or (p.texto or "").startswith("__") or _es_reanalizar(p.texto)):
        usar_ia = False
    if p.analisis and p.analisis.get("secciones") and not estado.analisis_de(p.campo.get("id", "campo")):
        estado.guardar_analisis(p.campo.get("id", "campo"), p.analisis)
    if usar_ia:
        ia = chat_mod.conversar(p.campo, p.historial, p.texto, p.idioma, restricciones.pista(p.campo, p.texto, p.paso))
        return _sse(_con_respaldo(ia, p.campo, lambda campo: guiado.conversar(campo, p.texto, p.paso, p.con_analisis)))
    return _sse(guiado.conversar(p.campo, p.texto, p.paso, p.con_analisis))


def _es_reanalizar(texto: str | None) -> bool:
    return (texto or "").strip().lower().rstrip(".!") in ("analizar de nuevo", "analyze again", "analyse again")


# lo que ya mostró la IA en la pantalla: si falla después de esto, el error se muestra (no se puede deshacer)
_VISIBLES = {"texto", "tarjeta", "analisis", "plan"}


def _con_respaldo(ia, campo, guiado_eventos):
    """Si la IA falla antes de mostrar nada (saturada, sin conexión, tardó demasiado), contesta el modo guiado en vez
    de mostrar «La API de Gemini falló». Lo que la IA ya guardó en la ficha queda, y el guiado sigue desde la ficha con eso."""
    mostro = False
    while True:
        try:
            ev = next(ia)
        except StopIteration:
            return
        except Exception:  # noqa: BLE001
            if mostro:
                raise
            traceback.print_exc()
            ev = {"tipo": "error"}
        if ev.get("tipo") == "error" and not mostro:
            ia.close()
            yield {"tipo": "texto", "delta": "La IA no está respondiendo ahora; sigo sin ella.\n\n"}
            yield from guiado_eventos(campo)
            return
        if ev.get("tipo") == "campo_patch":
            campo = estado.fusionar(campo, ev.get("cambios") or {})
        if ev.get("tipo") in _VISIBLES:
            mostro = True
        yield ev


# ------------------------------------------------------------------ puente remoto (solo pruebas)
def _clave_puente(x_puente_clave: str | None) -> None:
    if not puente.clave():
        raise HTTPException(404, "Not Found")
    if not puente.clave_valida(x_puente_clave):
        raise HTTPException(401, "Clave del puente incorrecta")


@app.get("/api/puente/pendientes")
def puente_pendientes(esperar: float = 0, x_puente_clave: str | None = Header(None)):
    _clave_puente(x_puente_clave)
    return puente.esperar_pendientes(min(max(esperar, 0), 50))


@app.get("/api/puente/entrada/{mid}")
def puente_entrada(mid: str, x_puente_clave: str | None = Header(None)):
    _clave_puente(x_puente_clave)
    datos = puente.almacen().entrada(mid)
    if datos is None:
        raise HTTPException(404, "No hay un mensaje con ese id (o ya venció)")
    return datos


@app.post("/api/puente/salida/{mid}")
def puente_salida(mid: str, eventos: list[dict[str, Any]], x_puente_clave: str | None = Header(None)):
    _clave_puente(x_puente_clave)
    puente.almacen().agregar(mid, eventos)
    return {"ok": True}


# ------------------------------------------------------------------ frontend compilado
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


# Python 3.12 no conoce .webp: la foto del trigo de la portada salía como «application/octet-stream»
mimetypes.add_type("image/webp", ".webp")


def _guardar_en_la_red(cabeceras: Any, segundos: int) -> None:
    """Le pide a la red de Vercel (el CDN) que guarde la respuesta y la entregue sin despertar a la función de Python.

    Vercel solo guarda lo que sale de una función si se lo piden con `s-maxage` o con esta cabecera; `max-age` es para
    el navegador. Medido: todo lo compilado salía con `X-Vercel-Cache: MISS`, cada archivo esperaba 0,2 a
    0,8 s a la función (que está en Virginia y atiende de a uno) y el texto de la portada aparecía recién a los ~1,7 s.
    La cabecera es solo para Vercel, que la saca antes de contestar: el navegador sigue viendo el `Cache-Control` de
    siempre. Lo guardado es de cada subida: una subida nueva arranca con la red vacía. Con contraseña no se guarda nada
    (la red se lo daría a cualquiera sin pasar por acá)."""
    if not acceso.activa():
        cabeceras["Vercel-CDN-Cache-Control"] = f"max-age={segundos}"


def _un_dia() -> dict[str, str]:
    """Los mapas fijos (departamentos, rutas, costa): un día en el navegador y en la red de Vercel."""
    cabeceras = {"Cache-Control": f"{acceso.cache_publico()}, max-age=86400"}
    _guardar_en_la_red(cabeceras, 86400)
    return cabeceras


class _Inmutables(StaticFiles):
    """/assets lleva el hash del contenido en el nombre: navegador y CDN de Vercel lo guardan un año sin preguntar.
    Así el JS de 1,6 MB no despierta la función de Python en cada visita."""

    def file_response(self, *args: Any, **kwargs: Any):
        r = super().file_response(*args, **kwargs)
        r.headers["Cache-Control"] = f"{acceso.cache_publico()}, max-age=31536000, immutable"
        _guardar_en_la_red(r.headers, 31536000)
        return r


class _Ejemplos(StaticFiles):
    """Los campos de ejemplo: el navegador pregunta siempre si cambiaron y, si llegan a la función, la red los guarda."""

    def file_response(self, *args: Any, **kwargs: Any):
        r = super().file_response(*args, **kwargs)
        r.headers["Cache-Control"] = "private, no-cache" if acceso.activa() else "no-cache"
        _guardar_en_la_red(r.headers, 86400)
        return r


def _archivo_dist(f: Path, if_none_match: str | None) -> Response:
    """index.html y los demás archivos de dist con un ETag sacado del CONTENIDO.

    El ETag de FileResponse sale de fecha + tamaño, y en Vercel todos los archivos tienen la misma fecha
    e index.html pesa siempre lo mismo: cada subida nueva tenía el mismo ETag, el navegador recibía 304, se quedaba
    con el index.html viejo y pedía JS de una versión borrada (404 → página en blanco)."""
    datos = f.read_bytes()
    etag = '"' + hashlib.md5(datos).hexdigest() + '"'
    cabeceras = {"ETag": etag, "Cache-Control": "private, no-cache" if acceso.activa() else "no-cache"}
    # el navegador pregunta siempre (no-cache) y le contesta la red de Vercel, no la función
    _guardar_en_la_red(cabeceras, 86400)
    if if_none_match and etag in if_none_match:
        return Response(status_code=304, headers=cabeceras)
    tipo = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    return Response(datos, media_type=tipo, headers=cabeceras)


if DIST.exists():
    # En Vercel estas dos carpetas salen de su red como archivos estáticos y no pasan por la función (pyproject.toml,
    # `[tool.vercel.fastapi.static] cdn = true`; el año de caché de /assets lo pone ahí vercel.json). En la PC las sirve
    # la app, como siempre.
    app.mount("/assets", _Inmutables(directory=DIST / "assets"), name="assets")
    if (DIST / "ejemplos").is_dir():  # los campos de ejemplo ya calculados: lo que baja «Ver un campo de ejemplo»
        app.mount("/ejemplos", _Ejemplos(directory=DIST / "ejemplos"), name="ejemplos")

    @app.get("/{ruta:path}")
    def spa(ruta: str, if_none_match: str | None = Header(None)):
        # La portada B
        # queda en el repo pero /b lleva a la A. Redirección temporal (302), por si se quiere volver.
        if ruta.strip("/") in ("b", "b.html"):
            return RedirectResponse("/", status_code=302)
        f = DIST / ruta
        if ruta and f.is_file():
            return _archivo_dist(f, if_none_match)
        pagina = DIST / f"{ruta.strip('/')}.html"  # /app → app.html (la herramienta); «/» es la portada
        if ruta.strip("/") and pagina.is_file() and pagina.parent == DIST:
            return _archivo_dist(pagina, if_none_match)
        return _archivo_dist(DIST / "index.html", if_none_match)
