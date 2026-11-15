"""Herramientas que el asesor usa para conectar la conversación con los datos.

Cada herramienta devuelve (resultado_para_el_modelo, eventos_para_la_app). Los números siempre
salen de acá; el modelo los explica pero no los inventa.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from ..analisis import plan as plan_mod
from ..analisis.cultivos import CULTIVOS
from ..analisis.rotaciones import DIMENSIONES, ROTACIONES
from . import estado

TARJETAS = {
    "dibujar_campo": "Mapa para ubicar el campo: padrón, archivo (KML/KMZ/GeoJSON/shapefile), dibujo o coordenadas.",
    "secciones": "Dividir el campo en secciones (potreros/chacras) dibujando o en franjas, o usar los suelos del padrón.",
    "datos_sistema": "Tipo de producción, ganado, si vende forraje, maquinaria, riego, tenencia (propio/arrendado y años).",
    "historial_seccion": "Tabla para cargar qué se hizo en cada sección los últimos años (invierno y verano).",
    "problemas": "Marcar por sección: se anega, hiela, se erosiona, suelo superficial, malezas, compactación; y texto libre.",
    "subir_analisis_suelo": "Subir el análisis de suelo (CSV, Excel, PDF o foto) o cargarlo a mano.",
    "subir_estacion": "Subir datos de la estación meteorológica propia (CSV o Excel).",
    "subir_historial": "Subir un archivo con el historial de cultivos por potrero.",
    "prioridades": "Deslizadores de prioridades (ingreso, suelo, agua, clima, forraje, simplicidad, diversificación) y planes a corto y largo plazo.",
    "margenes": "Márgenes propios por cultivo en USD/ha (opcional).",
}

DEFINICIONES: list[dict[str, Any]] = [
    {
        "name": "actualizar_campo",
        "description": (
            "Guarda en la ficha del campo lo que el productor contó en el chat. Usala cada vez que diga algo útil: "
            "nombre, sistema (tipo: agricola|ganadero|mixto, ganado: bool, cabezas, vende_forraje: bool, riego, maquinaria, tenencia: "
            "propio|arrendado, anios_contrato, renta_kg: kilos de soja por ha y año, seguro_seca: bool, vende_futuro: bool), experiencia (anios, texto, que_funciono, que_fallo), objetivos "
            "(corto_plazo, largo_plazo, pct_agricola 0-100, prioridades: {suelo, agua, clima, ingreso, forraje, "
            "simplicidad, diversificacion} de 0 a 5), restricciones (cultivos_excluidos: códigos, plan_uso_mgap: bool), "
            "margenes ({codigo_cultivo: USD/ha}, sin renta), detalle_margenes ({codigo_cultivo: {rinde: kg/ha, "
            "precio: USD/t, costo: USD/ha sin renta}}; con eso se calcula el rinde de equilibrio). Para una sección, pasá secciones=[{id, historial: [{anio, invierno, "
            "verano}], problemas: [anegamiento|helada|erosion|suelo_superficial|malezas|compactacion|sequia], notas}]. "
            "Códigos de cultivo válidos: " + ", ".join(CULTIVOS) + "."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campo": {"type": "object", "description": "Cambios al nivel del campo (mezcla profunda)."},
                "secciones": {"type": "array", "items": {"type": "object"}, "description": "Cambios por sección, con su id."},
            },
        },
    },
    {
        "name": "pedir_al_productor",
        "description": (
            "Muestra en el chat una tarjeta para que el productor cargue algo que se hace mejor con un formulario, "
            "un mapa o un archivo. Después de usarla, terminá tu turno con una frase corta y esperá. Tipos: "
            + "; ".join(f"{k}: {v}" for k, v in TARJETAS.items())
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": list(TARJETAS)},
                "mensaje": {"type": "string", "description": "Una línea que explica para qué sirve ese dato."},
            },
            "required": ["tipo"],
        },
    },
    {
        "name": "analizar_campo",
        "description": (
            "Corre el análisis completo con los datos de la ficha: clima de NASA POWER (1991-hoy) con la lluvia de "
            "GPM IMERG desde 2000, factor R del MGAP, "
            "suelo del MGAP y cobertura MODIS por sección, y evalúa la rotación actual contra alternativas con la "
            "ecuación de erosión del Plan de Uso, riesgo de seca, helada y calor, ingreso, forraje y carbono. Tarda "
            "de 10 a 60 segundos. Devuelve los números y las 5 filas (por qué, evidencia, beneficios, huecos, riesgos) "
            "por opción. Usala cuando ya tengas el contorno del campo y lo más importante de la entrevista; se puede "
            "volver a correr si cambian los datos."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "consultar_analisis",
        "description": (
            "Devuelve el detalle del último análisis de UNA sección, para justificar una decisión o contestar «¿por qué "
            "esta y no otra?»: todas las rotaciones evaluadas ordenadas por puntaje (con el puntaje de cada criterio, la "
            "erosión y si cumple la tolerancia), cómo pesaron las prioridades del productor, cuál se recomendó y con qué "
            "regla, y, si pasás rotacion_id, el detalle completo de esa opción (por qué, evidencia, beneficios, huecos y "
            "riesgos cuando estaba entre las comparadas). No recalcula nada: usa el último analizar_campo. Usala antes de "
            "justificar con números que no tengas a mano."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seccion_id": {"type": "string", "description": "id (o nombre) de la sección."},
                "rotacion_id": {"type": "string", "description": "Opcional: id de una rotación, o 'actual', para ver su detalle."},
            },
            "required": ["seccion_id"],
        },
    },
    {
        "name": "proponer_plan",
        "description": (
            "Arma el plan visual por sección y temporada (mapa del campo pintado con qué sembrar en cada sección). "
            "Cada sección arranca en la sugerida (sugerida_id), que le tenés que explicar con su porqué; el productor "
            "decide y puede volver a lo de hoy con 'actual'. Pasá eleccion={id_seccion: "
            "id_rotacion} solo con lo que el productor eligió. Ids de rotación: " + ", ".join(ROTACIONES) + ", o 'actual'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "eleccion": {"type": "object", "description": "{id_seccion: id_rotacion}"},
                "comentario": {"type": "string", "description": "Por qué este plan, en una o dos frases."},
            },
        },
    },
]


def ejecutar(nombre: str, entrada: dict, ctx: dict) -> Iterator[dict]:
    """Ejecuta una herramienta. Emite eventos para la app y, al final,
    {"tipo": "_resultado", "contenido": str, "es_error": bool}. `ctx` tiene "campo" y se modifica."""
    if not isinstance(entrada, dict):
        yield {"tipo": "_resultado", "contenido": "Entrada inválida: se esperaba un objeto.", "es_error": True}
        return
    campo = ctx["campo"]

    if nombre == "actualizar_campo":
        cambios = dict(entrada.get("campo") or {})
        if entrada.get("secciones"):
            cambios["secciones"] = entrada["secciones"]
        if not cambios:
            yield {"tipo": "_resultado", "contenido": "No había cambios.", "es_error": True}
            return
        ctx["campo"] = estado.fusionar(campo, cambios)
        yield {"tipo": "campo_patch", "cambios": cambios}
        yield {"tipo": "_resultado", "contenido": "Guardado en la ficha del campo.", "es_error": False}
        return

    if nombre == "pedir_al_productor":
        tipo = entrada.get("tipo")
        if tipo not in TARJETAS:
            yield {"tipo": "_resultado", "contenido": f"Tipo de tarjeta desconocido: {tipo}", "es_error": True}
            return
        yield {"tipo": "tarjeta", "tarjeta": tipo, "mensaje": entrada.get("mensaje")}
        yield {"tipo": "_resultado", "contenido": "Tarjeta mostrada. Terminá el turno y esperá la respuesta del productor.",
               "es_error": False}
        return

    if nombre == "analizar_campo":
        if not campo.get("contorno") and not campo.get("secciones"):
            yield {"tipo": "_resultado", "contenido": "Todavía no hay contorno del campo: pedí la tarjeta dibujar_campo.",
                   "es_error": True}
            return
        anterior = estado.analisis_de(campo.get("id", "campo"))
        resultado = None
        try:
            for ev in plan_mod.analizar_campo_pasos(campo):
                if ev["tipo"] == "progreso":
                    yield ev
                else:
                    resultado = ev["resultado"]
        except Exception as e:  # noqa: BLE001
            yield {"tipo": "_resultado", "contenido": f"El análisis falló: {e}", "es_error": True}
            return
        estado.guardar_analisis(campo.get("id", "campo"), resultado)
        yield {"tipo": "analisis", "resultado": resultado}
        yield {"tipo": "plan", "plan": resultado["plan"]}
        resumen = estado.resumen_analisis(resultado)
        if anterior:
            resumen["cambios_respecto_al_analisis_anterior"] = cambios_entre(anterior, resultado)
        yield {"tipo": "_resultado", "contenido": json.dumps(resumen, ensure_ascii=False), "es_error": False}
        return

    if nombre == "consultar_analisis":
        res = estado.analisis_de(campo.get("id", "campo"))
        if not res:
            yield {"tipo": "_resultado", "contenido": "Todavía no hay análisis: corré analizar_campo.", "es_error": True}
            return
        detalle = detalle_seccion(res, campo, str(entrada.get("seccion_id") or ""), entrada.get("rotacion_id"))
        if detalle is None:
            ids = ", ".join(f"{s['id']} ({s['nombre']})" for s in res["secciones"])
            yield {"tipo": "_resultado", "contenido": f"No encontré esa sección. Las del análisis: {ids}.", "es_error": True}
            return
        yield {"tipo": "_resultado", "contenido": json.dumps(detalle, ensure_ascii=False), "es_error": False}
        return

    if nombre == "proponer_plan":
        res = estado.analisis_de(campo.get("id", "campo"))
        if not res:
            yield {"tipo": "_resultado", "contenido": "Primero hay que correr analizar_campo.", "es_error": True}
            return
        eleccion = entrada.get("eleccion") or {}
        campo2 = {**campo, "rotacion_elegida": {**(campo.get("rotacion_elegida") or {}), **eleccion}}
        plan = plan_mod.armar_plan(res["secciones"], res["plan"]["temporadas"], campo2)
        res["plan"] = plan
        estado.guardar_analisis(campo.get("id", "campo"), res)
        if eleccion:
            ctx["campo"] = campo2
            yield {"tipo": "campo_patch", "cambios": {"rotacion_elegida": campo2["rotacion_elegida"]}}
        yield {"tipo": "plan", "plan": plan, "comentario": entrada.get("comentario")}
        yield {"tipo": "_resultado", "contenido": json.dumps({
            "erosion_media_actual": plan["erosion_media_actual"], "erosion_media_plan": plan["erosion_media_plan"],
            "erosion_media_si_toma_las_sugeridas": plan.get("erosion_media_sugerida"),
            "asignacion": [{"seccion": a["seccion"], "rotacion": a["rotacion"], "eligio_el_productor": a.get("elegida"),
                            "sugerida": a.get("sugerida"), "cultivos": a["cultivos"][:6]} for a in plan["secciones"]],
            "temporadas": [t["etiqueta"] for t in plan["temporadas"][:6]],
        }, ensure_ascii=False), "es_error": False}
        return

    yield {"tipo": "_resultado", "contenido": f"Herramienta desconocida: {nombre}", "es_error": True}


REGLA_RECOMENDACION = (
    "Puntaje = promedio de los criterios pesado por las prioridades del productor (0 a 5; sin dato, 2). Las barras de "
    "cada criterio van de 0 a 100 entre lo peor y lo mejor que se ve en Uruguay; para el total, cada criterio se mide "
    "entre la peor y la mejor opción de ese lote (así una prioridad 3 pesa lo mismo en agua que en forraje, aunque las "
    "rotaciones de un lote se diferencien poco en agua). Lo que contó el productor (se anega, le falló, "
    "tenencia corta) baja el puntaje. La tolerancia de erosión es una condición: las rotaciones que la superan van "
    "después de las que cumplen, aunque puntúen más. Se muestran las 3 mejores alternativas variadas. Entre las que se "
    "muestran y cumplen la tolerancia (y lo de hoy, si cumple y no tiene un cultivo que el productor ya no quiere), se "
    "recomienda la que sale primera más seguido en 2000 juegos de pesos parecidos a los del productor, en el mismo orden "
    "de prioridades («aceptabilidad»): las prioridades de 0 a 5 dicen bien el orden, no los números exactos. Casi siempre "
    "es la de más puntaje; si no, la tarjeta lo explica. Si ninguna alternativa cumple y lo de hoy sí, seguir con lo de hoy."
)


def _buscar_seccion(res: dict, clave: str) -> dict | None:
    c = clave.strip().lower()
    for s in res["secciones"]:
        if str(s["id"]).lower() == c or str(s.get("nombre") or "").lower() == c:
            return s
    return None


def _opcion_completa(e: dict) -> dict:
    er = e["erosion"]
    return {
        "id": e["id"], "nombre": e["nombre"], "es_actual": bool(e.get("es_actual")),
        "puntaje_total": e["puntaje_total"], "puntajes": e["puntajes"],
        "erosion_t_ha": er.get("a_t_ha"), "tolerancia": er.get("tolerancia_t"), "cumple": er.get("cumple"),
        "erosion_rango": er.get("rango"), "meses_descubierto": e.get("meses_descubierto"),
        "riesgo": e.get("riesgo"), "carbono": e.get("carbono"), "ingreso": e.get("ingreso"),
        "alertas": e.get("alertas"), "explicacion": e.get("explicacion"),
    }


def detalle_seccion(res: dict, campo: dict, seccion: str, rotacion_id: str | None) -> dict | None:
    """Todo lo que hace falta para justificar la decisión de una sección (sin recalcular)."""
    s = _buscar_seccion(res, seccion)
    if s is None:
        return None
    prios = ((campo.get("objetivos") or {}).get("prioridades") or {})
    elegida = (campo.get("rotacion_elegida") or {}).get(s["id"])
    actual_id = s["actual"]["id"] if s.get("actual") else None
    ranking = []
    for i, e in enumerate(s.get("todas") or [], 1):
        er = e["erosion"]
        ranking.append({
            "puesto": i, "id": e["id"], "nombre": e["nombre"], "puntaje_total": e["puntaje_total"],
            "puntajes": e["puntajes"], "erosion_t_ha": er.get("a_t_ha"), "cumple_tolerancia": er.get("cumple"),
        })
    out: dict = {
        "seccion": {"id": s["id"], "nombre": s["nombre"], "area_ha": s["area_ha"], "problemas": s.get("problemas")},
        "prioridades_usadas": {d: float(prios.get(d, 2)) for d in DIMENSIONES},
        "regla": REGLA_RECOMENDACION,
        "recomendada_id": s.get("recomendada_id"),
        "elegida_por_el_productor": elegida,
        "actual": _opcion_completa(s["actual"]) if s.get("actual") else None,
        "comparadas": [e["id"] for e in s.get("alternativas") or []],
        "ranking_todas": ranking,
        "nota_tolerancia": s.get("nota_tolerancia"),
    }
    if rotacion_id:
        rid = "actual" if rotacion_id == "actual" else rotacion_id
        candidatas = ([s["actual"]] if s.get("actual") else []) + list(s.get("alternativas") or [])
        e = next((x for x in candidatas if x["id"] == rid or (rid == "actual" and x.get("es_actual"))), None)
        if e is not None:
            out["detalle"] = _opcion_completa(e)
        else:
            fila = next((x for x in ranking if x["id"] == rid), None)
            out["detalle"] = ({**fila, "nota": "No estaba entre las opciones comparadas en detalle; hay puntajes y "
                               "erosión, no las cinco filas."} if fila else
                              {"nota": f"La rotación «{rotacion_id}» no se evaluó en esta sección."})
    if actual_id is None:
        out["nota_actual"] = "No hay rotación actual cargada ni deducida para esta sección."
    return out


def cambios_entre(antes: dict, despues: dict) -> dict:
    """Qué cambió entre dos análisis del mismo campo, para que el asesor lo cuente («antes salía X, ahora Y»)."""
    previo = {s["id"]: s for s in antes.get("secciones") or []}
    secs = []
    for s in despues["secciones"]:
        p = previo.get(s["id"])
        if p is None:
            secs.append({"seccion": s["nombre"], "cambio": "sección nueva"})
            continue
        nombre = lambda sec, rid: next((e["nombre"] for e in sec.get("todas") or [] if e["id"] == rid),  # noqa: E731
                                       "rotación actual" if rid and sec.get("actual") and sec["actual"]["id"] == rid else rid)
        punt = lambda sec, rid: next((e["puntaje_total"] for e in sec.get("todas") or [] if e["id"] == rid), None)  # noqa: E731
        ra, rd = p.get("recomendada_id"), s.get("recomendada_id")
        secs.append({
            "seccion": s["nombre"],
            "recomendada_antes": nombre(p, ra), "recomendada_ahora": nombre(s, rd),
            "cambio_la_recomendacion": ra != rd,
            "puntaje_de_la_anterior_antes_y_ahora": [punt(p, ra), punt(s, ra)],
        })
    pa, pd = antes.get("plan") or {}, despues.get("plan") or {}
    return {
        "secciones": secs,
        "erosion_media_del_plan_antes_y_ahora": [pa.get("erosion_media_plan"), pd.get("erosion_media_plan")],
    }
