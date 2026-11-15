"""Modo guiado: la misma entrevista y el mismo análisis, sin IA.

Sirve cuando no hay clave de la API de Gemini (demo sin conexión, costo cero) y como red de
seguridad. Sigue un guion fijo: mira qué falta en la ficha del campo y pide eso con la misma
tarjeta que usaría el asesor con IA. Al final corre el análisis y resume los números.
"""

from __future__ import annotations

import re
import time

from typing import Iterator

from ..analisis import plan as plan_mod
from ..analisis.clima import es_cambio_claro
from ..analisis import rotaciones as rot_mod
from ..analisis.cultivos import CULTIVOS
from . import estado, restricciones

PASOS = [
    ("dibujar_campo",
     "Hola. Para empezar, ubiquemos el campo: elegí la forma que te quede más cómoda.",
     lambda c: bool(c.get("contorno"))),
    ("secciones",
     "Ahora dividilo en los lotes que manejás por separado (o potreros, si tenés ganado). El plan se arma lote por lote.",
     lambda c: bool(c.get("secciones"))),
    ("datos_sistema",
     "Contame cómo trabajás el campo: qué hacés, si tenés ganado y si es propio o arrendado.",
     lambda c: bool(c.get("sistema"))),
    ("historial_seccion",
     "¿Qué sembraste en cada lote estos últimos años? Es la base contra la que comparo; si no te acordás, miro lo que vio el satélite.",
     lambda c: any(s.get("historial") for s in c.get("secciones") or [])),
    ("problemas",
     "Tu experiencia vale más que cualquier satélite: contame dónde se anega, hiela o se lava, y qué te anduvo bien.",
     lambda c: bool(c.get("experiencia")) or any(s.get("problemas") for s in c.get("secciones") or [])),
    ("subir_analisis_suelo",
     "¿Tenés un análisis de suelo? Subilo (CSV, Excel, PDF o foto) y afino cuánta agua guarda y qué opciones convienen.",
     lambda c: bool(c.get("analisis_suelo_general")) or any(s.get("analisis_suelo") for s in c.get("secciones") or [])),
    ("prioridades",
     "Casi terminamos: ¿qué te importa más? Ordená tus prioridades y contame tus planes.",
     lambda c: bool((c.get("objetivos") or {}).get("prioridades"))),
    ("margenes",
     "Opcional: si sabés tus márgenes por cultivo (USD por hectárea), cargalos y comparo en dólares.",
     lambda c: bool(c.get("margenes"))),
]


def siguiente_paso(campo: dict) -> tuple[str, str] | None:
    omitidos = set(campo.get("pasos_omitidos") or [])
    for tipo, texto, hecho in PASOS:
        if tipo in omitidos:
            continue
        if not hecho(campo):
            return tipo, texto
    return None


def _de10(x):
    """Probabilidad como "N de cada 10 años": se entiende mejor que un porcentaje (13-mostrar-los-datos.md)."""
    n = round(10 * x)
    return "ningún año de cada 10" if n == 0 else f"{n} de cada 10 años"


def _n(x, d=1):
    return f"{x:.{d}f}".replace(".", ",")


TOLERANCIA = "tolerancia (lo máximo que ese suelo puede perder por año sin degradarse)"


def resumen_texto(res: dict, campo: dict | None = None) -> str:
    campo = campo or {}
    cl = res["clima"]
    t = cl["tendencia"]
    plan = res["plan"]
    lineas = [
        f"Listo. Analicé {len(res['secciones'])} secciones con 35 años de clima diario de la NASA ({cl['periodo']}), "
        f"{'el suelo del mapa mundial SoilGrids' if any((x.get('suelo') or {}).get('mundial') for x in res['secciones']) else 'el suelo del MGAP'} "
        "y lo que vio el satélite MODIS desde 2022.",
    ]
    # el ejemplo de clima, con un cultivo que esté en el plan (el que más superficie ocupa)
    area: dict[str, float] = {}
    for a in plan["secciones"]:
        for c in a["cultivos"]:
            area[c] = area.get(c, 0) + a["area_ha"]
    # Buscamos si algún cultivo del plan tiene un cambio claro en seca (diferencia >= 0.2)
    cultivo_cambio_claro = None
    for c in sorted(area, key=lambda c: -area[c]):
        ps = (t["cultivos"].get(c) or {}).get("prob_seca")
        if ps and ps.get("antes") is not None and ps.get("ahora") is not None:
            es_claro = ps.get("cambio_claro") if "cambio_claro" in ps else es_cambio_claro(ps["antes"], ps["ahora"])
            if es_claro:
                cultivo_cambio_claro = (c, ps)
                break

    calor = (f"Los días de más de 35 °C en verano pasaron de {_n(t['dias_calor_verano']['antes'])} a "
             f"{_n(t['dias_calor_verano']['ahora'])} por año.")
    if cultivo_cambio_claro:
        c, ps = cultivo_cambio_claro
        lineas.append(
            f"El clima de tu zona se está corriendo: en {nombre_cultivo(c).lower()}, la floración llegó con menos de la "
            f"mitad del agua que necesita {_de10(ps['antes'])} entre {t['periodo_antes']}, y {_de10(ps['ahora'])} entre "
            f"{t['periodo_ahora']}. " + calor
        )
    else:
        ll = t.get("lluvia_anual") or {}
        lineas.append(f"El clima de tu zona se está corriendo: la lluvia del año pasó de {_n(ll.get('antes'), 0)} a "
                      f"{_n(ll.get('ahora'), 0)} mm entre {t['periodo_antes']} y {t['periodo_ahora']}. " + calor)
    lineas.append(
        f"Con la ecuación del Plan de Uso, la erosión media del campo con lo que hacés hoy es "
        f"{_n(plan['erosion_media_actual'])} t/ha/año; si tomás la sugerida en cada sección, "
        f"{_n(plan.get('erosion_media_sugerida', plan['erosion_media_plan']))}."
    )
    sistema = campo.get("sistema") or {}
    pct = (campo.get("objetivos") or {}).get("pct_agricola")
    equilibrio = plan.get("equilibrio") or {}
    if sistema.get("tipo") == "mixto" and pct is not None and equilibrio.get("nota"):
        lineas.append(equilibrio["nota"])
    elif sistema.get("tipo") == "mixto" and pct is not None:
        lineas.append(f"Como el campo es mixto, las sugerencias reparten las secciones para que quede más o menos "
                      f"{_n(pct, 0)} % agrícola, como marcaste en cómo trabajás el campo; por eso alguna sección puede ir "
                      "a cultivos aunque otra opción dé menos erosión. Si querés otro reparto, cambialo ahí.")
    tol = [TOLERANCIA]  # se explica la primera vez que aparece

    def tolerancia() -> str:
        return tol.pop() if tol else "tolerancia"

    for s in res["secciones"]:
        a = s["actual"]
        asig = next((x for x in plan["secciones"] if x["seccion_id"] == s["id"]), None)
        rid = (asig.get("sugerida_id") or asig["rotacion_id"]) if asig else s["recomendada_id"]
        rec = next((e for e in ([a] if a else []) + s["alternativas"] if e and e["id"] == rid), None)
        if not rec:
            continue
        cab = f"{s['nombre']} ({_n(s['area_ha'], 0)} ha)"
        er = rec["erosion"]
        if rid == "actual":
            lineas.append(f"{cab}: seguí con lo que venís haciendo; ya cumple la {tolerancia()} del suelo "
                          f"(erosión {_n(er['a_t_ha'])} t/ha/año, tolerancia {_n(er['tolerancia_t'], 0)})."
                          if er["cumple"] and er.get("ratio", 0) <= 1 else
                          f"{cab}: seguí con el campo natural; ahí el Plan de Uso no se exige (erosión "
                          f"{_n(er['a_t_ha'])} t/ha/año)."
                          if er["cumple"] else
                          f"{cab}: seguí con lo actual, aunque la erosión ({_n(er['a_t_ha'])}) supera la {tolerancia()} "
                          f"({_n(er['tolerancia_t'], 0)}).")
            continue
        txt = f"{cab}: con tus prioridades, la opción que mejor sale es {rec['nombre'][0].lower() + rec['nombre'][1:]}"
        if a:
            txt += (f" en vez de lo actual (erosión {_n(a['erosion']['a_t_ha'])} → {_n(er['a_t_ha'])} "
                    f"t/ha/año; {tolerancia()}: {_n(er['tolerancia_t'], 0)})")
        lineas.append(txt + ".")
    lineas.append(
        "El plan arranca en la opción sugerida de cada sección. Tocá una sección para ver las alternativas, cada una con el porqué, la "
        "evidencia, los beneficios, lo que falta saber y los riesgos, y elegí vos qué probar. Es un apoyo para "
        "decidir: revisalo con tu agrónomo."
    )
    return "\n\n".join(lineas)


# ----------------------------------------------------------------- respuestas con sus palabras
# Con IA, el asesor saca los datos del texto. Sin IA, acá se
# saca lo que se puede con palabras clave; el texto queda siempre en la ficha (notas_productor) y el paso se da por
# respondido, así la entrevista sigue y no vuelve a pedir lo mismo.

def _sin_tildes(t: str) -> str:
    return restricciones._normal(t)


PRIORIDAD_PALABRAS = {
    "ingreso": r"plata|ingreso|ganancia|rentab|margen|dolar|negocio|ganar",
    "suelo": r"suelo|erosi|lavad|degrad|materia organica",
    "agua": r"agua|seca|sequia|humedad",
    "clima": r"clima|calor|helada|lluvia",
    "forraje": r"forraje|pasto|ganado|vacas|comida para",
    "simplicidad": r"simple|sencill|facil|menos trabajo|poco trabajo",
    "diversificacion": r"diversific|riesgo|no poner todo|variedad",
}

PROBLEMA_PALABRAS = {
    "anegamiento": r"anega|encharca|inunda|agua parada|se llena de agua",
    "helada": r"hiela|helada",
    "erosion": r"se lava|erosi|carcava|zanj",
    "suelo_superficial": r"superficial|piedra|roca|poco suelo|suelo playo",
    "malezas": r"maleza|yuyo|gramilla|sorgo de alepo|rama negra",
    "compactacion": r"compact|piso de arado",
    "sequia": r"se seca|seca rapido|sequia",
}


def _desde_texto(campo: dict, paso: str, texto: str) -> tuple[dict, str]:
    """Lo que se pudo sacar del texto para la ficha (cambios para fusionar) y una frase que lo dice."""
    t = _sin_tildes(texto)
    notas = list(campo.get("notas_productor") or []) + [{"paso": paso, "texto": texto.strip()}]
    cambios: dict = {"notas_productor": notas}
    dicho = ""
    if paso == "datos_sistema":
        agri = bool(re.search(r"agricol|agricultura|siembr|cultiv|soja|trigo|maiz|cosech", t))
        gana = bool(re.search(r"ganad|vaca|novill|ternero|tambo|leche|oveja|cria|engorde|invernada|cabezas", t))
        tipo = "mixto" if agri and gana else "ganadero" if gana else "agricola" if agri else None
        if tipo:
            sistema = {**(campo.get("sistema") or {}), "tipo": tipo, "ganado": tipo != "agricola"}
            if re.search(r"arrend|alquil|renta", t):
                sistema["tenencia"] = "arrendado"
            elif re.search(r"propi|mio|nuestro|de la familia", t):
                sistema["tenencia"] = "propio"
            if re.search(r"vend\w* (?:el |de )?(?:forraje|fardo|silo|pasto)|fardos|pastoreo a terceros", t):
                sistema["vende_forraje"] = True
            if re.search(r"\briego\b|\brieg[oa]", t) and not re.search(r"sin riego|no riego", t):
                sistema["riego"] = True
            cabezas = re.search(r"(\d[\d.]*)\s*(?:cabezas|vacas|animales|novillos)", t)
            if cabezas and tipo != "agricola":
                sistema["cabezas"] = int(cabezas.group(1).replace(".", ""))
            cambios["sistema"] = sistema
            pct = {"agricola": 100, "ganadero": 0}.get(tipo)
            m = re.search(r"(\d{1,3})\s*%\s*(?:agricol|de agricultura|cultiv)", t)
            if tipo == "mixto":
                pct = int(m.group(1)) if m else 50
            cambios["objetivos"] = {**(campo.get("objetivos") or {}), "pct_agricola": pct}
            dicho = {"agricola": "Anoté que es un campo agrícola.", "ganadero": "Anoté que es un campo ganadero.",
                     "mixto": f"Anoté que es un campo mixto, más o menos {pct} % agrícola."}[tipo]
            dicho += {"arrendado": " Es arrendado.", "propio": " Es propio."}.get(sistema.get("tenencia"), "")
    elif paso == "problemas":
        exp = {**(campo.get("experiencia") or {}), "texto": texto.strip()}
        cambios["experiencia"] = exp
        encontrados = [k for k, pat in PROBLEMA_PALABRAS.items() if re.search(pat, t)]
        secs = campo.get("secciones") or []
        nombradas = [s for s in secs if s.get("nombre") and _sin_tildes(s["nombre"]) in t]
        destino = nombradas or (secs if len(secs) == 1 else [])
        if encontrados and destino:
            cambios["secciones"] = [{"id": s["id"], "problemas": sorted(set((s.get("problemas") or []) + encontrados))} for s in destino]
            dicho = (f"Anoté tu experiencia y lo marqué en {', '.join(s.get('nombre') or 'la sección' for s in destino)}: "
                     f"{', '.join(PROBLEMAS_NOMBRE[p] for p in encontrados)}.")
        else:
            dicho = "Anoté tu experiencia."
    elif paso == "prioridades":
        pr = {"ingreso": 3, "suelo": 3, "agua": 3, "clima": 2, "forraje": 3 if (campo.get("sistema") or {}).get("ganado") else 0,
              "simplicidad": 1, "diversificacion": 1}
        subidas = [k for k, pat in PRIORIDAD_PALABRAS.items() if re.search(pat, t)]
        for k in subidas:
            pr[k] = 5
        cambios["objetivos"] = {**(campo.get("objetivos") or {}), **(cambios.get("objetivos") or {}), "prioridades": pr,
                                "largo_plazo": texto.strip()}
        dicho = (f"Le di más peso a lo que nombraste: {', '.join(PRIORIDAD_NOMBRE[k] for k in subidas)}." if subidas
                 else "Dejé las prioridades parejas; podés ajustarlas después en el plan.")
    elif paso == "margenes":
        margenes: dict[str, float] = {}
        for patron, cods in restricciones._NOMBRES:
            for m in re.finditer(rf"\b(?:{patron})\b[^\d]{{0,25}}?(\d+(?:[.,]\d+)?)", t):
                cod = cods[0]
                if cod not in margenes:
                    margenes[cod] = float(m.group(1).replace(",", "."))
        if margenes:
            cambios["margenes"] = {**(campo.get("margenes") or {}), **margenes}
            dicho = "Anoté los márgenes: " + ", ".join(f"{nombre_cultivo(c).lower()} {_n(v, 0)} USD/ha" for c, v in margenes.items()) + "."
    elif paso == "subir_analisis_suelo":
        valores: dict[str, float] = {}
        for clave, patron in SUELO_PALABRAS.items():
            m = re.search(rf"(?:{patron})\D{{0,12}}?(\d+(?:[.,]\d+)?)", t)
            if m:
                valores[clave] = float(m.group(1).replace(",", "."))
        if valores:
            cambios["analisis_suelo_general"] = {**(campo.get("analisis_suelo_general") or {}), **valores, "nombre": "Dicho en el chat"}
            dicho = "Anoté el análisis de suelo: " + ", ".join(f"{SUELO_NOMBRE[k]} {_n(v, 0 if v == int(v) else 1)}" for k, v in valores.items()) + "."
    # lo que no se pudo pasar a un dato concreto queda como nota y el paso se da por respondido
    if not dicho or paso in ("historial_seccion", "subir_estacion", "subir_historial"):
        dicho = dicho or ("Lo anoté en la ficha. Sin la IA no puedo pasarlo a números, así que para este paso uso lo que "
                          "vio el satélite y los datos de la NASA y del MGAP. Si querés que cuente en el cálculo, completá "
                          "el formulario o pasá a la conversación libre.")
        cambios["pasos_omitidos"] = sorted(set((campo.get("pasos_omitidos") or []) + [paso]))
    return cambios, dicho


SUELO_PALABRAS = {
    "ph": r"\bph",
    "materia_organica": r"materia organica|\bm\.? ?o\.?\b",
    "fosforo_bray": r"fosforo|\bp bray|\bbray",
    "potasio": r"potasio|\bk\b",
    "arena": r"arena",
    "limo": r"limo",
    "arcilla": r"arcilla",
    "agua_util_mm": r"agua util",
}
SUELO_NOMBRE = {"ph": "pH", "materia_organica": "materia orgánica", "fosforo_bray": "fósforo", "potasio": "potasio",
                "arena": "arena", "limo": "limo", "arcilla": "arcilla", "agua_util_mm": "agua útil"}
PROBLEMAS_NOMBRE = {"anegamiento": "se anega", "helada": "hiela", "erosion": "se lava", "suelo_superficial": "suelo superficial",
                    "malezas": "malezas", "compactacion": "compactación", "sequia": "se seca rápido"}
PRIORIDAD_NOMBRE = {"ingreso": "el ingreso", "suelo": "cuidar el suelo", "agua": "el agua", "clima": "el clima",
                    "forraje": "el forraje", "simplicidad": "que sea simple", "diversificacion": "diversificar"}


def _cultivos_rot(rid: str, plan_previo: dict | None, sid: str) -> set[str]:
    if rid in rot_mod.ROTACIONES:
        return set(rot_mod.ROTACIONES[rid].cultivos)
    sec = next((x for x in (plan_previo or {}).get("secciones") or [] if x.get("seccion_id") == sid), None)
    return set((sec or {}).get("cultivos") or [])


def _nombre_rot(res: dict, sid: str, rid: str | None) -> str | None:
    sec = next((x for x in res.get("secciones") or [] if x.get("id") == sid), None)
    if not sec or not rid:
        return None
    e = next((x for x in ([sec.get("actual")] if sec.get("actual") else []) + (sec.get("alternativas") or []) if x and x.get("id") == rid), None)
    if not e:
        return None
    return "lo que hacés hoy" if rid == "actual" else e.get("nombre")


def _analizar(campo: dict) -> Iterator[dict]:
    """Corre el análisis y emite sus eventos; el último es {"tipo": "_resultado"...} o un error."""
    yield {"tipo": "herramienta", "nombre": "analizar_campo", "estado": "inicio"}
    resultado = None
    try:
        for ev in plan_mod.analizar_campo_pasos(campo):
            if ev["tipo"] == "progreso":
                yield ev
            else:
                resultado = ev["resultado"]
    except Exception as e:  # noqa: BLE001
        yield {"tipo": "herramienta", "nombre": "analizar_campo", "estado": "fin", "error": True}
        yield {"tipo": "error", "mensaje": f"No pude terminar el análisis: {e}"}
        return
    estado.guardar_analisis(campo.get("id", "campo"), resultado)
    yield {"tipo": "herramienta", "nombre": "analizar_campo", "estado": "fin", "error": False}
    yield {"tipo": "analisis", "resultado": resultado}
    yield {"tipo": "plan", "plan": resultado["plan"]}
    yield {"tipo": "_resultado", "resultado": resultado}


def _con_exclusiones(campo: dict, cambios: dict[str, list[str]], nueva: list[str], con_analisis: bool = False) -> Iterator[dict]:
    """Guarda los cultivos que no quiere y, si ya se puede analizar, recalcula y cuenta qué cambió por sección."""
    sacados = [c for c in cambios["excluir"] if c not in ((campo.get("restricciones") or {}).get("cultivos_excluidos") or [])]
    vueltos = [c for c in cambios["incluir"] if c in ((campo.get("restricciones") or {}).get("cultivos_excluidos") or [])]
    previo = estado.analisis_de(campo.get("id", "campo"))
    plan_previo = (previo or {}).get("plan")
    # una sección donde había elegido una opción con ese cultivo vuelve a la sugerida
    elegida = dict(campo.get("rotacion_elegida") or {})
    soltadas = [sid for sid, rid in elegida.items() if set(nueva) & _cultivos_rot(rid, plan_previo, sid)]
    for sid in soltadas:
        elegida.pop(sid)
    nuevo = {**campo, "restricciones": {**(campo.get("restricciones") or {}), "cultivos_excluidos": nueva}, "rotacion_elegida": elegida}
    yield {"tipo": "campo_patch", "cambios": {"restricciones": nuevo["restricciones"]}}
    if sacados and vueltos:
        frase = f"Saqué {restricciones.nombres(sacados)} de las opciones y volví a poner {restricciones.nombres(vueltos)}."
    elif sacados:
        frase = f"Saqué {restricciones.nombres(sacados)} de las opciones."
    elif vueltos:
        frase = f"Volví a poner {restricciones.nombres(vueltos)} en las opciones."
    else:
        frase = "Ya lo tenía en cuenta."
    # con resultados a la vista se recalcula aunque falte algún paso de la entrevista (el ejemplo no tiene análisis
    # de suelo, por ejemplo); sin resultados, se anota y la entrevista sigue
    if not nuevo.get("contorno") or (siguiente_paso(nuevo) and not (previo or con_analisis)):
        yield {"tipo": "texto", "delta": f"{frase} Lo tengo en cuenta cuando analice el campo.\n\n"}
        return
    resultado = None
    for ev in _analizar(nuevo):
        if ev["tipo"] == "_resultado":
            resultado = ev["resultado"]
        else:
            yield ev
    if resultado is None:
        return
    plan = resultado["plan"]
    if soltadas:
        yield {"tipo": "campo_patch", "cambios": {"rotacion_elegida": {
            x["seccion_id"]: x.get("sugerida_id") or x["rotacion_id"] for x in plan["secciones"] if x["seccion_id"] in soltadas}}}
    lineas = [f"{frase} Volví a calcular con el clima de la NASA y el suelo del MGAP. Lo sugerido por sección:"]
    for x in plan["secciones"]:
        sid = x["seccion_id"]
        ahora = _nombre_rot(resultado, sid, x.get("sugerida_id") or x["rotacion_id"])
        antes_x = next((y for y in (plan_previo or {}).get("secciones") or [] if y.get("seccion_id") == sid), None)
        antes = _nombre_rot(previo, sid, (antes_x or {}).get("sugerida_id") or (antes_x or {}).get("rotacion_id")) if previo and antes_x else None
        nom = next((s.get("nombre") for s in resultado["secciones"] if s["id"] == sid), sid)
        if ahora and antes and antes != ahora:
            lineas.append(f"- **{nom}**: antes {antes}; ahora {ahora}.")
        elif ahora:
            lineas.append(f"- **{nom}**: {ahora}{' (no cambia)' if antes else ''}.")
    if sacados:
        lineas.append(f"\nSi querés volver a tenerla en cuenta, escribí «volvé a poner {restricciones.nombres(sacados)}».")
    yield {"tipo": "texto", "delta": "\n".join(lineas)}
    yield {"tipo": "fin"}
    yield {"tipo": "_listo"}


def conversar(campo: dict, texto: str, paso: str | None = None, con_analisis: bool = False) -> Iterator[dict]:
    t = (texto or "").strip().lower()
    quiere_analizar = any(p in t for p in ("analiz", "de nuevo", "recalcul", "otra vez", "actualiz"))
    # contestó una tarjeta con sus palabras: se guarda lo que se entiende y la entrevista sigue
    respondio_tarjeta = bool(paso and texto and not texto.startswith("__"))
    if respondio_tarjeta:
        cambios, dicho = _desde_texto(campo, paso, texto)
        campo = estado.fusionar(campo, cambios)
        yield {"tipo": "campo_patch", "cambios": cambios}
        yield {"tipo": "texto", "delta": dicho + "\n\n"}
    # «no quiero soja», «sacá el maíz», «volvé a poner el trigo»: se guarda y, con todo cargado, se recalcula
    pedido = restricciones.detectar(texto or "")
    nueva = restricciones.aplicar(campo, pedido) if (pedido["excluir"] or pedido["incluir"]) else None
    if nueva is not None:
        termino = False
        for ev in _con_exclusiones(campo, pedido, nueva, con_analisis):
            if ev["tipo"] == "_listo":
                termino = True
            else:
                yield ev
        if termino:
            return
        campo = {**campo, "restricciones": {**(campo.get("restricciones") or {}), "cultivos_excluidos": nueva}}
    paso = siguiente_paso(campo)
    # La estación o el pluviómetro propio no es un paso de la entrevista: si la persona dice que mide, se le abre la tarjeta.
    if re.search(r"estaci[oó]n|pluvi[oó]metro|mido la lluvia|registro de lluvia", t) and not campo.get("estacion"):
        yield {"tipo": "texto", "delta": "Dale: subí los datos y los pongo al lado de lo que midió la NASA."}
        yield {"tipo": "tarjeta", "tarjeta": "subir_estacion", "mensaje": None}
        yield {"tipo": "fin"}
        return
    # el saludo y qué vamos a hacer ya están en la presentación de arriba del chat (frontend, Presentacion.tsx)
    if paso and not quiere_analizar:
        tipo, txt = paso
        # Transición con animación thinking-orbs para que se aprecie el análisis de la información ingresada
        # y el productor tenga tiempo de leer la respuesta antes de que se despliegue la siguiente tarjeta
        if texto and texto != "__inicio":
            yield {"tipo": "progreso", "mensaje": "Analizando la información del campo…", "avance": None}
            time.sleep(0.58)  # 10 % menos (en otra compu se sentía largo)
        yield {"tipo": "texto", "delta": txt}
        if texto and texto != "__inicio":
            time.sleep(0.32)
        yield {"tipo": "tarjeta", "tarjeta": tipo, "mensaje": None}
        yield {"tipo": "fin"}
        return
    if not campo.get("contorno") and not campo.get("secciones"):
        yield {"tipo": "texto", "delta": "Primero necesito el contorno del campo."}
        yield {"tipo": "tarjeta", "tarjeta": "dibujar_campo", "mensaje": None}
        yield {"tipo": "fin"}
        return
    ya = estado.analisis_de(campo.get("id", "campo")) or con_analisis
    if ya and not quiere_analizar and respondio_tarjeta:
        yield {"tipo": "texto", "delta": "Para que lo tenga en cuenta en los números, escribí «analizar de nuevo»."}
        yield {"tipo": "fin"}
        return
    if ya and not quiere_analizar and not t.startswith("__"):
        yield {"tipo": "texto", "delta": (
            "En el modo guiado no puedo contestar preguntas libres. Sí puedo sacar un cultivo de las opciones y volver a "
            "calcular: escribí, por ejemplo, «no quiero soja». También podés cambiar la rotación de cada sección en el "
            "plan, mover las prioridades o escribir «analizar de nuevo» después de cambiar datos. Con la IA activada "
            "te explico cualquier número.")}
        yield {"tipo": "fin"}
        return
    resultado = None
    for ev in _analizar(campo):
        if ev["tipo"] == "_resultado":
            resultado = ev["resultado"]
        else:
            yield ev
    if resultado is None:
        yield {"tipo": "fin"}
        return
    yield {"tipo": "texto", "delta": resumen_texto(resultado, campo)}
    yield {"tipo": "fin"}


def nombre_cultivo(cod: str) -> str:
    return CULTIVOS[cod].nombre if cod in CULTIVOS else cod
