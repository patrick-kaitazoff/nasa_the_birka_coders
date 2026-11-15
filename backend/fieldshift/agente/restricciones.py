"""Cultivos que el productor no quiere (o vuelve a querer), dichos con sus palabras.

«No quiero soja de ninguna manera», «sacá el maíz», «sin girasol», «nada de colza»: con eso se arma la lista de
`restricciones.cultivos_excluidos` y se vuelve a calcular. Lo usan el modo guiado (que no tiene IA y si no lo
detecta así no lo entiende) y el chat con IA, como pista para que el asesor no se lo saltee.
"""

from __future__ import annotations

import json
import re
import unicodedata

from ..analisis.cultivos import CULTIVOS

# nombre como lo dice la gente → códigos. Lo más específico va primero: «soja de segunda» antes que «soja».
_NOMBRES: list[tuple[str, tuple[str, ...]]] = [
    (r"soja de primera", ("soja",)),
    (r"soja de segunda|soja 2da|soja segunda", ("soja2",)),
    (r"soja", ("soja", "soja2")),
    (r"maiz de primera", ("maiz",)),
    (r"maiz de segunda|maiz 2do|maiz segunda", ("maiz2",)),
    (r"sorgo forrajero|sorgo de pastoreo", ("sorgo_forrajero",)),
    (r"sorgo granifero", ("sorgo",)),
    (r"maiz", ("maiz", "maiz2")),
    (r"sorgo", ("sorgo", "sorgo_forrajero")),
    (r"girasol", ("girasol",)),
    (r"trigo", ("trigo",)),
    (r"cebada", ("cebada",)),
    (r"colza|canola", ("colza",)),
    (r"alfalfa", ("alfalfa",)),
    (r"praderas?", ("pradera",)),
    (r"verdeos?", ("verdeo",)),
    (r"(?:cultivos? de )?coberturas?", ("cobertura",)),
    (r"campo natural", ("campo_natural",)),
    (r"barbechos?", ("barbecho",)),
    # en inglés
    (r"second[- ]crop soybeans?", ("soja2",)),
    (r"soybeans?|soy", ("soja", "soja2")),
    (r"corn|maize", ("maiz", "maiz2")),
    (r"sorghum", ("sorgo", "sorgo_forrajero")),
    (r"sunflowers?", ("girasol",)),
    (r"wheat", ("trigo",)),
    (r"barley", ("cebada",)),
    (r"rapeseed", ("colza",)),
    (r"pastures?", ("pradera",)),
    (r"cover crops?", ("cobertura",)),
    (r"fallow", ("barbecho",)),
]
_CULTIVO = "|".join(f"(?:{n})" for n, _ in _NOMBRES)

# lo que va antes del cultivo para decir que NO lo quiere
_NO = (
    r"(?:no (?:quiero|quisiera|me interesa|me gusta|voy a (?:hacer|sembrar|plantar)|hago|siembro|planto|pongo|"
    r"me sirve|me conviene|uso|uso mas)|"
    r"nunca(?: mas)?|ni loco (?:hago|siembro|planto)|sin|nada de|ni|sac(?:a|ar|ale|alo|ala|ame|ad)|quit(?:a|ar|ale|alo|ala)|elimin(?:a|ar)|exclu(?:i|ir|ye|yan)|"
    r"evit(?:a|ar)|descart(?:a|ar)|fuera|"
    r"(?:i )?(?:don'?t|do not) (?:want|grow|plant|like)(?: any)?(?: more)?|no more|without|remove|drop|exclude|avoid|take out)"
)
# lo que dice que SÍ lo vuelve a querer
_SI = (
    r"(?:(?:ahora )?si (?:quiero|puedo hacer|hago|me interesa)|volve(?:r)? a (?:poner|incluir|meter|agregar|sumar)|"
    r"agreg(?:a|ar|ale)|inclu(?:i|ir|ye)|pon(?:e|er|ele) (?:de nuevo )?|sum(?:a|ar|ale)|"
    r"put back|add back|bring back|i do want|include)"
)
_RELLENO = r"(?:\s+(?:hacer|sembrar|plantar|mas|nunca|tampoco|de nuevo|otra vez|el|la|los|las|lo|ninguna|ningun|cultivo|cultivos|de|the|any)\b)*"
# después del primer cultivo puede seguir una lista: «sin soja ni maíz», «nada de soja, maíz o girasol»
_LISTA = rf"(?:{_CULTIVO})(?:\s*(?:,|y|ni|o|ni tampoco|and|or|nor)\s+(?:el |la |los |las |the )?(?:{_CULTIVO}))*"


def _normal(texto: str) -> str:
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t)


def _codigos(trozo: str) -> list[str]:
    """Los cultivos nombrados en `trozo`, en orden y sin repetir."""
    vistos: list[str] = []
    resto = trozo
    while resto:
        m = re.search(_CULTIVO, resto)
        if not m:
            break
        palabra = m.group(0)
        for patron, cods in _NOMBRES:
            if re.fullmatch(patron, palabra):
                for c in cods:
                    if c in CULTIVOS and c not in vistos:
                        vistos.append(c)
                break
        resto = resto[m.end():]
    return vistos


def _buscar(texto: str, verbo: str) -> list[str]:
    t = _normal(texto)
    out: list[str] = []
    for m in re.finditer(rf"\b{verbo}{_RELLENO}\s+({_LISTA})", t):
        for c in _codigos(m.group(1)):
            if c not in out:
                out.append(c)
    return out


def detectar(texto: str) -> dict[str, list[str]]:
    """{"excluir": [...], "incluir": [...]} con los códigos que el texto pide sacar o volver a poner."""
    incluir = _buscar(texto, _SI)
    excluir = [c for c in _buscar(texto, _NO) if c not in incluir]
    return {"excluir": excluir, "incluir": incluir}


def aplicar(campo: dict, cambios: dict[str, list[str]]) -> list[str] | None:
    """La lista nueva de excluidos, o None si no cambia nada."""
    antes = list((campo.get("restricciones") or {}).get("cultivos_excluidos") or [])
    nueva = [c for c in antes if c not in cambios.get("incluir", [])]
    for c in cambios.get("excluir", []):
        if c not in nueva:
            nueva.append(c)
    return None if nueva == antes else nueva


# cuando van los dos, se dice como lo dice la gente: «la soja», no «soja de primera y soja de segunda»
_JUNTOS = [(("soja", "soja2"), "soja"), (("maiz", "maiz2"), "maíz"), (("sorgo", "sorgo_forrajero"), "sorgo")]


def nombres(codigos: list[str]) -> str:
    """«soja y girasol», «soja de segunda»."""
    resto = [c for c in codigos if c in CULTIVOS]
    ns = []
    for par, nombre in _JUNTOS:
        if all(c in resto for c in par):
            ns.append(nombre)
            resto = [c for c in resto if c not in par]
    ns += [CULTIVOS[c].nombre.split(" (")[0].lower() for c in resto]
    if len(ns) <= 1:
        return "".join(ns)
    return ", ".join(ns[:-1]) + " y " + ns[-1]


TARJETA_NOMBRE = {
    "datos_sistema": "cómo trabaja el campo", "historial_seccion": "qué sembró en cada sección",
    "problemas": "su experiencia y los problemas del campo", "subir_analisis_suelo": "el análisis de suelo",
    "subir_estacion": "los datos de su estación o pluviómetro", "subir_historial": "el historial de cultivos",
    "prioridades": "sus prioridades y planes", "margenes": "sus márgenes por cultivo",
}


def pista(campo: dict, texto: str, paso: str | None) -> str | None:
    """Para el asesor con IA: lo que la app ya entendió del mensaje, para que no se le pase."""
    lineas = []
    if paso:
        lineas.append(
            f"El productor contestó con sus palabras la tarjeta «{TARJETA_NOMBRE.get(paso, paso)}» ({paso}), en vez del "
            "formulario. Sacá del texto todos los datos que puedas y guardalos con actualizar_campo. Si con eso el paso "
            f"queda respondido (aunque sea en parte), no vuelvas a pedir la tarjeta {paso}: agregalo a pasos_omitidos si "
            "no alcanza para un dato concreto, decí en una línea qué anotaste y seguí con lo siguiente. Si falta algo "
            "imprescindible, preguntá solo eso, en palabras.")
    pedido = detectar(texto)
    nueva = aplicar(campo, pedido) if (pedido["excluir"] or pedido["incluir"]) else None
    if nueva is not None:
        partes = []
        if pedido["excluir"]:
            partes.append(f"no quiere {nombres(pedido['excluir'])} (códigos {', '.join(pedido['excluir'])})")
        if pedido["incluir"]:
            partes.append(f"vuelve a aceptar {nombres(pedido['incluir'])} (códigos {', '.join(pedido['incluir'])})")
        lineas.append(
            "Parece que " + " y ".join(partes) + ". Si es eso, guardá con actualizar_campo "
            f"restricciones.cultivos_excluidos = {json.dumps(nueva)} (la lista completa). Si ya hay análisis, volvé a correr "
            "analizar_campo y contá qué cambió en cada sección con cambios_respecto_al_analisis_anterior; si en alguna "
            "sección había elegido una opción con esos cultivos, aplicá con proponer_plan la sugerida nueva. Si lo dijo en "
            "otro sentido (por ejemplo, preguntando), no cambies nada y contestá.")
    return "\n".join(lineas) or None
