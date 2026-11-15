"""Modo puente, solo para pruebas: el asesor es una persona que contesta desde afuera.

Sirve para probar la conversación libre sin clave de la API de Gemini. Hay dos formas:

- **Local** (`FIELDSHIFT_PUENTE=<carpeta>`): cada mensaje del productor queda en <carpeta>/entrada/<id>.json y
  la app espera los eventos que se van agregando en <carpeta>/salida/<id>.jsonl hasta uno {"tipo": "fin"}.
  Vale para todos los chats de ese servidor.
- **Remoto** (la app en Vercel, `FIELDSHIFT_PUENTE_CLAVE=<clave>`): los mensajes y los eventos viajan por la
  Runtime Cache de Vercel (compartida entre las instancias de la región) y se leen y contestan por
  /api/puente/…, con la clave en el encabezado X-Puente-Clave. Solo lo usan los chats abiertos con
  `?puente=1`; el resto de la gente sigue en el modo guiado.

Para contestar, desde app/backend (con --remoto <url> para la app en internet; la clave sale de
FIELDSHIFT_PUENTE_CLAVE o de .secretos/puente.env):
    python -m fieldshift.agente.puente [--remoto URL] esperar [segundos] (muestra los mensajes sin contestar)
    python -m fieldshift.agente.puente [--remoto URL] <id> texto - (el texto entra por stdin)
    python -m fieldshift.agente.puente [--remoto URL] <id> tarjeta <tipo> [mensaje]
    python -m fieldshift.agente.puente [--remoto URL] <id> herramienta <nombre> '<json>'
    python -m fieldshift.agente.puente [--remoto URL] <id> fin
Las herramientas son las mismas del asesor con IA (herramientas.py) y corren donde corre el comando: los
números salen de ahí.
"""

from __future__ import annotations

import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterator

ESPERA_MAX = 15 * 60  # segundos, en local
# En Vercel cada pedido muere a los 300 s (vercel.json): se corta un poco antes para poder avisar.
ESPERA_MAX_REMOTO = 280
TTL = 2 * 3600  # lo del puente remoto se borra solo a las 2 h


def carpeta() -> Path | None:
    c = os.environ.get("FIELDSHIFT_PUENTE")
    return Path(c) if c else None


def clave() -> str | None:
    return os.environ.get("FIELDSHIFT_PUENTE_CLAVE") or None


def activo(pedido: bool = False) -> bool:
    """El puente local vale para todo el servidor; el remoto, solo para los chats que lo piden (?puente=1)."""
    if carpeta() is not None:
        return True
    return bool(pedido and clave())


def clave_valida(dada: str | None) -> bool:
    c = clave()
    return bool(c and dada and hmac.compare_digest(c.encode(), dada.encode()))


# ------------------------------------------------------------------ dónde se guarda
class _Carpeta:
    """El puente de siempre: archivos en una carpeta del servidor."""

    def __init__(self, base: Path):
        self.base = base
        (base / "entrada").mkdir(parents=True, exist_ok=True)
        (base / "salida").mkdir(parents=True, exist_ok=True)

    def _salida(self, mid: str) -> Path:
        return self.base / "salida" / f"{mid}.jsonl"

    def crear(self, mid: str, datos: dict) -> None:
        self._salida(mid).touch()
        (self.base / "entrada" / f"{mid}.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")

    def entrada(self, mid: str) -> dict | None:
        f = self.base / "entrada" / f"{mid}.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def eventos_desde(self, mid: str, n: int) -> list[dict]:
        lineas = [l for l in self._salida(mid).read_text(encoding="utf-8").splitlines() if l.strip()]
        return [json.loads(l) for l in lineas[n:]]

    def agregar(self, mid: str, eventos: list[dict]) -> None:
        with self._salida(mid).open("a", encoding="utf-8") as f:
            for ev in eventos:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def pendientes(self) -> list[dict]:
        sal = []
        for f in sorted((self.base / "entrada").glob("*.json")):
            mid = f.stem
            evs = self.eventos_desde(mid, 0) if self._salida(mid).exists() else []
            if not any(e.get("tipo") == "fin" for e in evs):
                sal.append({"id": mid, "texto": json.loads(f.read_text(encoding="utf-8")).get("texto", "")})
        return sal


class _Cache:
    """Puente remoto: Runtime Cache de Vercel. Cada evento va en su propia clave y un contador dice cuántos hay,
    así la app, que pregunta cada segundo, lee un número chico y no la lista entera (se cobra por cada 8 KB)."""

    def __init__(self):
        from vercel.functions import RuntimeCache

        # strict en Vercel: si la caché no está, mejor un error que una caché en memoria que no ve la otra instancia
        self.c = RuntimeCache(namespace="fieldshift-puente", strict=bool(os.environ.get("VERCEL")))

    def _set(self, k: str, v: Any) -> None:
        self.c.set(k, v, {"ttl": TTL})

    def crear(self, mid: str, datos: dict) -> None:
        self._set(f"entrada:{mid}", datos)
        self._set(f"n:{mid}", 0)
        pend = self.c.get("pendientes") or []
        pend.append({"id": mid, "texto": datos.get("texto", ""), "hora": time.time()})
        self._set("pendientes", pend[-50:])

    def entrada(self, mid: str) -> dict | None:
        return self.c.get(f"entrada:{mid}")

    def eventos_desde(self, mid: str, n: int) -> list[dict]:
        total = self.c.get(f"n:{mid}") or 0
        return [e for e in (self.c.get(f"ev:{mid}:{i}") for i in range(n, total)) if e is not None]

    def agregar(self, mid: str, eventos: list[dict]) -> None:
        total = self.c.get(f"n:{mid}") or 0
        for i, ev in enumerate(eventos):
            self._set(f"ev:{mid}:{total + i}", ev)
        self._set(f"n:{mid}", total + len(eventos))
        if any(e.get("tipo") == "fin" for e in eventos):
            self.quitar(mid)

    def quitar(self, mid: str) -> None:
        pend = self.c.get("pendientes") or []
        self._set("pendientes", [p for p in pend if p["id"] != mid])

    def pendientes(self) -> list[dict]:
        hace = time.time() - ESPERA_MAX_REMOTO - 60  # los que la app ya dejó de esperar no se muestran
        return [p for p in (self.c.get("pendientes") or []) if p.get("hora", 0) > hace]


_almacen_remoto: _Cache | None = None


def almacen() -> _Carpeta | _Cache:
    global _almacen_remoto
    base = carpeta()
    if base is not None:
        return _Carpeta(base)
    if _almacen_remoto is None:
        _almacen_remoto = _Cache()
    return _almacen_remoto


# ------------------------------------------------------------------ lado de la app
def conversar(campo: dict, texto: str) -> Iterator[dict]:
    from . import guiado

    if (texto or "").startswith("__inicio"):
        yield from guiado.conversar(campo, texto)  # el saludo inicial no hace esperar a nadie
        return
    a = almacen()
    remoto = isinstance(a, _Cache)
    mid = time.strftime("%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"
    a.crear(mid, {"id": mid, "texto": texto, "campo": campo})

    leidas, inicio = 0, time.time()
    espera = ESPERA_MAX_REMOTO if remoto else ESPERA_MAX
    while time.time() - inicio < espera:
        for ev in a.eventos_desde(mid, leidas):
            leidas += 1
            yield ev
            if ev.get("tipo") == "fin":
                return
        time.sleep(1.0 if remoto else 0.4)
    if remoto:
        a.quitar(mid)
        yield {"tipo": "error", "mensaje": "La respuesta tardó más de lo que permite el servidor. Volvé a mandar el mensaje."}
    else:
        yield {"tipo": "error", "mensaje": "Nadie contestó del otro lado del puente."}
    yield {"tipo": "fin"}


def esperar_pendientes(segundos: float) -> list[dict]:
    """Para /api/puente/pendientes: espera hasta `segundos` a que haya algún mensaje sin contestar."""
    a = almacen()
    fin = time.time() + segundos
    while True:
        pend = a.pendientes()
        if pend or time.time() >= fin:
            return pend
        time.sleep(1.0)


# ------------------------------------------------------------------ lado de quien contesta (terminal)
class _Remoto:
    """Habla con la app en internet por /api/puente/…; la entrada se copia a la PC para correr las herramientas."""

    def __init__(self, url: str):
        import httpx

        c = clave() or _clave_de_secretos()
        if not c:
            raise SystemExit("Falta la clave del puente: FIELDSHIFT_PUENTE_CLAVE o .secretos/puente.env")
        self.url = url.rstrip("/")
        self.http = httpx.Client(headers={"X-Puente-Clave": c}, timeout=60)
        from .. import cache

        self.local = cache.CARPETA / "puente_remoto"
        self.local.mkdir(parents=True, exist_ok=True)

    def pendientes(self, segundos: float) -> list[dict]:
        r = self.http.get(f"{self.url}/api/puente/pendientes", params={"esperar": segundos}, timeout=segundos + 30)
        r.raise_for_status()
        return r.json()

    def entrada(self, mid: str) -> dict:
        f = self.local / f"{mid}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        r = self.http.get(f"{self.url}/api/puente/entrada/{mid}")
        r.raise_for_status()
        f.write_text(r.text, encoding="utf-8")
        return r.json()

    def guardar_entrada(self, mid: str, datos: dict) -> None:
        (self.local / f"{mid}.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")

    def agregar(self, mid: str, eventos: list[dict]) -> None:
        self.http.post(f"{self.url}/api/puente/salida/{mid}", json=eventos).raise_for_status()


def _clave_de_secretos() -> str | None:
    f = Path(__file__).resolve().parents[4] / ".secretos" / "puente.env"
    if not f.exists():
        return None
    for linea in f.read_text(encoding="utf-8").splitlines():
        linea = linea.strip().removeprefix("export ")
        if linea.startswith("FIELDSHIFT_PUENTE_CLAVE="):
            return linea.split("=", 1)[1].strip().strip("'\"")
    return None


def _main(argv: list[str]) -> None:
    from . import herramientas

    remoto = None
    if argv[:1] == ["--remoto"]:
        remoto = _Remoto(argv[1])
        argv = argv[2:]

    if argv[:1] == ["esperar"]:
        segundos = float(argv[1]) if len(argv) > 1 else 25
        if remoto:
            pend = remoto.pendientes(segundos)
        else:
            fin = time.time() + segundos
            while not (pend := almacen().pendientes()) and time.time() < fin:
                time.sleep(1)
        for p in pend:
            print(json.dumps({"id": p["id"], "texto": p["texto"]}, ensure_ascii=False))
        return

    mid, accion, *resto = argv
    if remoto:
        datos = remoto.entrada(mid)
        emitir_lista = lambda evs: remoto.agregar(mid, evs)  # noqa: E731
        guardar = lambda d: remoto.guardar_entrada(mid, d)  # noqa: E731
    else:
        a = almacen()
        datos = a.entrada(mid)
        if datos is None:
            raise SystemExit(f"No hay un mensaje {mid}")
        emitir_lista = lambda evs: a.agregar(mid, evs)  # noqa: E731
        f = a.base / "entrada" / f"{mid}.json"  # type: ignore[union-attr]
        guardar = lambda d: f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")  # noqa: E731

    if accion == "texto":
        t = sys.stdin.read() if resto[:1] == ["-"] else " ".join(resto)
        emitir_lista([{"tipo": "texto", "delta": t.rstrip("\n")}])
    elif accion == "tarjeta":
        emitir_lista([{"tipo": "tarjeta", "tarjeta": resto[0], "mensaje": " ".join(resto[1:]) or None}])
    elif accion == "herramienta":
        nombre = resto[0]
        entrada_h = json.loads(resto[1]) if len(resto) > 1 else {}
        ctx = {"campo": datos["campo"]}
        evs: list[dict] = [{"tipo": "herramienta", "nombre": nombre, "estado": "inicio"}]
        emitir_lista(evs)
        contenido, es_error = "Sin resultado.", True
        lote: list[dict] = []
        for ev in herramientas.ejecutar(nombre, entrada_h, ctx):
            if ev["tipo"] == "_resultado":
                contenido, es_error = ev["contenido"], ev["es_error"]
            elif remoto:
                lote.append(ev)  # en remoto, de a un pedido por evento sería lento: se mandan juntos
                if ev["tipo"] == "progreso":
                    emitir_lista(lote)
                    lote = []
            else:
                emitir_lista([ev])
        lote.append({"tipo": "herramienta", "nombre": nombre, "estado": "fin", "error": es_error})
        emitir_lista(lote)
        datos["campo"] = ctx["campo"]  # la próxima herramienta del mismo turno ve los cambios
        guardar(datos)
        print(("ERROR: " if es_error else "") + contenido)
    elif accion == "fin":
        emitir_lista([{"tipo": "fin"}])
    else:
        raise SystemExit(f"Acción desconocida: {accion}")


if __name__ == "__main__":
    _main(sys.argv[1:])
