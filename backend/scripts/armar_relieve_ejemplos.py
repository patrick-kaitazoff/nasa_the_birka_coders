"""Deja calculado el relieve 3D de cada campo de ejemplo en frontend/public/ejemplos/relieve_<id>.json.

Al abrir un ejemplo, lo primero que se ve es el Plan con el relieve 3D. Ese relieve se le pedía al servidor
(/api/relieve), que tarda 2 a 3 s en la PC y más en Vercel si la función estaba dormida: mientras tanto el 3D decía
«Buscando el relieve de la NASA». Con este archivo el navegador lo baja junto con el ejemplo y el 3D sale enseguida. La erosión de lo que elige la persona se sigue calculando en el navegador, igual que antes.

El pedido se arma igual que `pedidoRelieve` de frontend/src/relieve/useRelieve.ts. Hay que volver a correrlo cada vez
que se regenera un ejemplo (armar_demo.py, armar_demo_eeuu.py, armar_terrenos.py): el archivo lleva una «huella» (los
lotes y el factor R) y, si no coincide con el ejemplo, la app lo descarta y le pide el relieve al servidor.

    cd app/backend && .venv/Scripts/python scripts/armar_relieve_ejemplos.py

También baja la foto satelital de Esri que va encima del relieve (foto_<id>.jpg), la misma dirección que arma
`urlFotoEsri` en useRelieve.ts. La app se la pedía a Esri al abrir el 3D y Esri la arma a pedido: tardaba varios
segundos y mientras tanto el terreno de afuera del campo quedaba verdoso. Para bajar solo las fotos, sin
recalcular el relieve:

    cd app/backend && .venv/Scripts/python scripts/armar_relieve_ejemplos.py --solo-fotos
"""

from __future__ import annotations

import json
import math
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from fieldshift.analisis import relieve  # noqa: E402

EJEMPLOS = RAIZ.parent / "frontend" / "public" / "ejemplos"
FICHAS = {
    "uy": "campo_demo.fieldshift.json",
    "us": "campo_demo_eeuu.fieldshift.json",
    "pucon": "terreno_pucon.fieldshift.json",
    "mosela": "terreno_mosela.fieldshift.json",
    "lunarejo": "terreno_lunarejo.fieldshift.json",
}


def pedido(ficha: dict) -> dict:
    campo, analisis = ficha["campo"], ficha["analisis"]
    por_id = {s["id"]: s for s in analisis["secciones"]}
    p = 1
    secciones = []
    for sc in campo["secciones"]:
        s = por_id.get(sc["id"])
        if not s:
            continue
        actual = s.get("actual") or {}
        erosion = actual.get("erosion") or {}
        if erosion.get("p"):
            p = erosion["p"]
        suelo = s.get("suelo") or {}
        secciones.append({"id": s["id"], "nombre": s["nombre"], "geometria": sc["geometria"],
                          "k": suelo.get("factor_k"), "t": suelo.get("tolerancia_t"), "c_actual": erosion.get("c")})
    return {"contorno": campo["contorno"], "secciones": secciones, "r": analisis["factor_r"]["usado"], "p": p,
            "largo_m": campo.get("largo_pendiente_m") or None}


def bajar_foto(res: dict, clave: str) -> None:
    """La foto de Esri del recuadro del relieve, con el mismo tamaño que pide urlFotoEsri (useRelieve.ts)."""
    b, g = res["bordes"], res["grilla"]
    ancho_m = (b["este"] - b["oeste"]) * 111320 * math.cos(math.radians((b["norte"] + b["sur"]) / 2))
    alto_m = (b["norte"] - b["sur"]) * 110540
    lado = max(256, min(2048, int(max(ancho_m, alto_m) / 0.5 + 0.5)))
    asp = g["cols"] / g["filas"]
    w = int((lado if asp >= 1 else lado * asp) + 0.5)
    h = int((lado / asp if asp >= 1 else lado) + 0.5)
    url = ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
           f"?bbox={b['oeste']},{b['sur']},{b['este']},{b['norte']}&bboxSR=4326&imageSR=4326&size={w},{h}&format=jpg&f=image")
    pedido_http = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(pedido_http, timeout=120) as r:
        datos = r.read()
    if datos[:2] != bytes([0xFF, 0xD8]):
        raise RuntimeError(f"Esri no devolvió una foto para {clave}: {datos[:120]!r}")
    salida = EJEMPLOS / f"foto_{clave}.jpg"
    salida.write_bytes(datos)
    print(f"{salida.name}: {len(datos) // 1024} KB, {w} x {h}")


def main() -> None:
    if "--solo-fotos" in sys.argv:
        for clave in FICHAS:
            res = json.loads((EJEMPLOS / f"relieve_{clave}.json").read_text(encoding="utf-8"))["relieve"]
            bajar_foto(res, clave)
        return
    for clave, archivo in FICHAS.items():
        ficha = json.loads((EJEMPLOS / archivo).read_text(encoding="utf-8"))
        ped = pedido(ficha)
        res = relieve.analizar(ped["contorno"], ped["secciones"], ped["r"], ped["p"], ped["largo_m"])
        salida = EJEMPLOS / f"relieve_{clave}.json"
        huella = {"secciones": [s["id"] for s in ped["secciones"]], "r": ped["r"]}
        salida.write_text(json.dumps({"huella": huella, "relieve": res}, ensure_ascii=False, separators=(",", ":")),
                          encoding="utf-8")
        print(f"{salida.name}: {salida.stat().st_size // 1024} KB, {len(ped['secciones'])} lotes")
        bajar_foto(res, clave)


if __name__ == "__main__":
    main()
