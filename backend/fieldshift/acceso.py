"""Contraseña para entrar a la app publicada.

La clave sale de la variable de entorno FIELDSHIFT_CLAVE (en Vercel, cargada como secreto; nunca en el repo).
- Con la variable: se pide la contraseña.
- Sin la variable: la app queda abierta, en la PC y en Vercel.

La app se publica sin contraseña. Hasta ese día, en Vercel sin la variable no entraba nadie
(cerrado ante un olvido); ahora lo abierto es lo buscado, así que sacar la variable abre la app. Para volver a
cerrarla alcanza con cargar FIELDSHIFT_CLAVE de nuevo y volver a publicar.

Se entra con un link `…/?clave=<clave>` o escribiéndola en la página que aparece. El navegador guarda una cookie
por un año con un resumen de la clave (no la clave), y la dirección se limpia para que la clave no quede a la vista.
Quedan afuera /api/salud (para ver si el servidor anda) y /api/puente/* (tiene su propia clave).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

COOKIE = "fs_acceso"
LIBRES = ("/api/salud", "/api/puente/")
UN_ANIO = 365 * 24 * 3600


def clave() -> str | None:
    """La clave configurada, o None si no hay (la app queda abierta)."""
    c = os.environ.get("FIELDSHIFT_CLAVE", "").strip()
    return c or None


def activa() -> bool:
    return clave() is not None


def _resumen(c: str) -> str:
    return hashlib.sha256(f"field-shift-acceso:{c}".encode()).hexdigest()


def _igual(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _pagina(error: bool) -> Response:
    aviso = (
        '<p class="error">Esa no es la contraseña. · That is not the password.</p>' if error else ""
    )
    cuerpo = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Seasons Ahead</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 16px; box-sizing: border-box;
    background: #2f3320; color: #f2f0e1; font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
  main {{ width: 100%; max-width: 380px; }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  p {{ margin: 0 0 18px; color: #d6d4c2; }}
  form {{ display: flex; gap: 8px; }}
  input {{ flex: 1; min-width: 0; padding: 10px 12px; border-radius: 8px; border: 1px solid #6b6f4f; background: #f2f0e1;
    color: #23261a; font: inherit; }}
  button {{ padding: 10px 16px; border-radius: 8px; border: 0; background: #ecf86e; color: #2f3320; font: inherit;
    font-weight: 650; cursor: pointer; }}
  .error {{ color: #ffb4a2; margin-top: 12px; }}
</style></head>
<body><main>
  <h1>Seasons Ahead</h1>
  <p>Por ahora es privado: escribí la contraseña para entrar.<br>Private for now: enter the password to continue.</p>
  <form method="get" action="">
    <input type="password" name="clave" autocomplete="current-password" aria-label="Contraseña / Password"
      placeholder="Contraseña / Password" autofocus required>
    <button type="submit">Entrar · Enter</button>
  </form>
  {aviso}
</main></body></html>"""
    return Response(
        cuerpo,
        status_code=401,
        media_type="text/html",
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"},
    )


async def controlar(request: Request, call_next):
    """Middleware HTTP: deja pasar con la cookie o con ?clave=… correcta; si no, la página de la contraseña."""
    c = clave()
    ruta = request.url.path
    if c is None or ruta.startswith(LIBRES):
        return await call_next(request)

    esperado = _resumen(c) if c else None
    cookie = request.cookies.get(COOKIE, "")
    if esperado and cookie and _igual(cookie, esperado):
        return await call_next(request)

    dada = request.query_params.get("clave")
    if dada is not None and esperado and _igual(_resumen(dada.strip()), esperado):
        resto = [(k, v) for k, v in request.query_params.multi_items() if k != "clave"]
        destino = ruta + ("?" + urlencode(resto) if resto else "")
        r = RedirectResponse(destino, status_code=303, headers={"Cache-Control": "no-store"})
        r.set_cookie(COOKIE, esperado, max_age=UN_ANIO, httponly=True, samesite="lax",
                     secure=request.url.scheme == "https")
        return r

    if ruta.startswith("/api/"):
        return JSONResponse({"detail": "Hace falta la contraseña."}, status_code=401,
                            headers={"Cache-Control": "no-store"})
    return _pagina(error=dada is not None)


def cache_publico() -> str:
    """Con contraseña, lo compilado se guarda solo en el navegador ("private"): si el CDN de Vercel lo guardara,
    se lo daría a cualquiera sin pasar por acá."""
    return "private" if activa() else "public"


__all__ = ["activa", "cache_publico", "clave", "controlar"]
