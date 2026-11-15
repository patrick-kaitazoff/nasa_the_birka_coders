"""Bucle del asesor con Gemini (API de Google): conversación + herramientas, emitiendo eventos para la app. La clave va en la variable
GEMINI_API_KEY (o GOOGLE_API_KEY); el modelo, en FIELDSHIFT_MODELO (por defecto `gemini-3.5-flash-lite`).

El historial de la API viaja entero desde el navegador y solo se le agregan mensajes al final. Cada mensaje
se guarda tal como lo devolvió Gemini (`Content` serializado, con sus `thought_signature`), porque Gemini 3
exige devolverle las firmas del razonamiento en cada llamada a herramienta. Un historial viejo con otro formato
(sin `parts`) se descarta: la ficha del campo viaja aparte en cada mensaje, así que no se pierde nada.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterator

from . import estado, herramientas
from .prompt import SISTEMA

# De gemini-3.8-flash a gemini-3.5-flash-lite. En producción 3.8 Flash daba
# 503 «high demand» en todas las pruebas, y en el nivel gratis deja
# ~20 consultas por día (capturas de desarrolladores; Google no lo publica) contra ~500 de Flash-Lite.
MODELO = os.environ.get("FIELDSHIFT_MODELO", "gemini-3.5-flash-lite")
MAX_VUELTAS = 12


def ia_disponible() -> bool:
    if os.environ.get("FIELDSHIFT_IA", "").lower() in ("0", "no", "false"):
        return False
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


# Tope de espera por llamada a Gemini. Sin tope, si Gemini no contestaba la burbuja del chat quedaba
# vacía con «Calculando…» para siempre. Es por pedido y entre trozos de la respuesta. De 90 s a 25 s: con el razonamiento bajo, una respuesta normal empieza en pocos segundos; si
# Gemini no contesta en 25, sigue el modo guiado (api._con_respaldo) en vez de dejar a la persona esperando.
TOPE_GEMINI_MS = 25_000


def _cliente():
    from google import genai
    from google.genai import types

    return genai.Client(http_options=types.HttpOptions(timeout=TOPE_GEMINI_MS))


IDIOMA_EN = (
    "The user is reading the app in English. Write every reply to them in plain English (no voseo), even "
    "though the field data and the tool results are in Spanish. Keep units and numbers as they come."
)


# Con un campo en EE. UU. la app muestra acres, t/ac, lb/ac, USD/ac y pulgadas, pero convierte solo lo
# que viene escrito como número + unidad abreviada (frontend, i18n/unidades.ts). «19,5 toneladas por hectárea» en
# palabras quedaba sin convertir al lado de cifras ya convertidas.
UNIDADES_US = (
    "The field is in the United States. All data and tool results are metric, and the app converts them on screen "
    "to U.S. units, but only when a number is written right before the abbreviated metric unit. So always write "
    "quantities as number + unit, exactly like this: 19.5 t/ha, 50 ha, 2600 kg/ha, 402 USD/ha, 574 mm. Never spell "
    "the unit out (no 'tonnes per hectare', 'hectares', 'millimeters') and never convert to acres, bushels or inches "
    "yourself. If the user gives numbers in acres, bushels per acre, dollars per bushel or dollars per acre, convert "
    "them to metric before saving them with a tool (1 acre = 0.4047 ha; corn 1 bu/ac = 62.8 kg/ha; soybean and "
    "wheat 1 bu/ac = 67.3 kg/ha; 1 USD/ac = 2.471 USD/ha)."
)


def _config(idioma: str, en_eeuu: bool = False):
    from google.genai import types

    sistema = SISTEMA + ("\n\n" + IDIOMA_EN if idioma == "en" else "") + ("\n\n" + UNIDADES_US if en_eeuu else "")
    funciones = [
        types.FunctionDeclaration(name=d["name"], description=d["description"], parameters_json_schema=d["input_schema"])
        for d in herramientas.DEFINICIONES
    ]
    return types.GenerateContentConfig(
        system_instruction=sistema,
        tools=[types.Tool(function_declarations=funciones)],
        # Razonamiento bajo (antes MEDIUM). Gemini piensa antes de escribir en CADA llamada, y un mensaje
        # que usa una herramienta son dos o tres llamadas: con MEDIUM una respuesta tardaba ~20 s (registros de Vercel)
        thinking_config=types.ThinkingConfig(thinking_level="LOW"),
        # el bucle de herramientas lo maneja esta función (emite eventos para la app en cada paso)
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=32000,
    )


def _en_eeuu(campo: dict) -> bool:
    from ..fuentes import region

    u = (campo or {}).get("ubicacion") or {}
    try:
        return u.get("lat") is not None and u.get("lon") is not None and region.pais(u["lat"], u["lon"]) == "US"
    except Exception:  # noqa: BLE001
        return False


def _a_dict(contenido: Any) -> dict:
    return contenido.model_dump(mode="json", exclude_none=True)


def historial_valido(historial: list[dict]) -> list[dict]:
    """Solo sirve un historial con el formato de Gemini; uno viejo se descarta entero."""
    if not historial or any(not isinstance(m, dict) or "parts" not in m for m in historial):
        return []
    return historial


def _juntar_partes(partes: list) -> list:
    """Une los pedacitos de texto del streaming. Nunca se une una parte que trae firma, razonamiento o una
    llamada a herramienta: Gemini pide devolverlas tal cual, en su lugar."""
    from google.genai import types

    out: list = []
    for p in partes:
        simple = p.text is not None and not p.thought and not p.thought_signature and not p.function_call
        if simple and out and out[-1].text is not None and not out[-1].thought and not out[-1].thought_signature \
                and not out[-1].function_call:
            out[-1] = types.Part(text=out[-1].text + p.text)
        else:
            out.append(p)
    return out


BLOQUEOS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


def conversar(campo: dict, historial: list[dict], texto: str, idioma: str = "es", pista: str | None = None) -> Iterator[dict]:
    """Emite eventos: texto, herramienta, tarjeta, campo_patch, progreso, analisis, plan,
    mensajes (los mensajes nuevos de la API para guardar), fin, error."""
    from google.genai import errors, types

    ctx = {"campo": campo}
    previos = [types.Content.model_validate(m) for m in historial_valido(historial)]
    nuevos: list = []
    contenido_usuario = f"<estado_campo>\n{estado.resumen_campo(campo)}\n</estado_campo>\n\n{texto}"
    if pista:  # lo que la app ya entendió del mensaje (tarjeta que contesta, cultivos que no quiere)
        contenido_usuario += f"\n\n<nota_de_la_app>\n{pista}\n</nota_de_la_app>"
    nuevos.append(types.Content(role="user", parts=[types.Part(text=contenido_usuario)]))
    cliente = _cliente()
    config = _config(idioma, _en_eeuu(campo))
    reintentos = 0
    completo = True

    for _ in range(MAX_VUELTAS):
        partes: list = []
        fin = None
        try:
            for trozo in cliente.models.generate_content_stream(model=MODELO, contents=previos + nuevos, config=config):
                cand = (trozo.candidates or [None])[0]
                if cand is None:
                    continue
                if cand.finish_reason:
                    fin = str(getattr(cand.finish_reason, "value", cand.finish_reason))
                for p in (cand.content.parts if cand.content and cand.content.parts else []):
                    partes.append(p)
                    if p.text and not p.thought:
                        yield {"tipo": "texto", "delta": p.text}
        except errors.ClientError as e:
            if e.code in (401, 403) or (e.code == 400 and "API key" in str(e)):
                yield {"tipo": "error", "mensaje": "La clave de la API de Gemini no es válida."}
            elif e.code == 429:
                yield {"tipo": "error", "mensaje": "La IA está saturada en este momento. Esperá un minuto y probá de nuevo."}
            else:
                yield {"tipo": "error", "mensaje": f"Error de la API de Gemini ({e.code})."}
            completo = False
            break
        except errors.ServerError as e:
            yield {"tipo": "error", "mensaje": f"La API de Gemini falló ({e.code}). Probá de nuevo en un rato."}
            completo = False
            break
        except errors.APIError as e:
            yield {"tipo": "error", "mensaje": f"Error de la API de Gemini ({e.code})."}
            completo = False
            break
        except OSError:
            yield {"tipo": "error", "mensaje": "No hay conexión con la API de Gemini."}
            completo = False
            break
        except Exception as e:  # noqa: BLE001
            # el tope de espera (httpx.TimeoutException y parientes): un aviso claro en vez del error interno
            if "Timeout" not in type(e).__name__:
                raise
            yield {"tipo": "error", "mensaje": "La IA tardó demasiado en contestar. Probá de nuevo en un momento."}
            completo = False
            break

        if fin in ("MALFORMED_FUNCTION_CALL", "MALFORMED_RESPONSE") and reintentos < 2:
            reintentos += 1
            continue  # la llamada a herramienta salió ilegible: se repite el turno sin guardarlo
        if fin in BLOQUEOS:
            yield {"tipo": "error", "mensaje": "La IA no pudo responder ese pedido."}
            completo = False
            break

        partes = _juntar_partes(partes)
        if not partes:
            break
        nuevos.append(types.Content(role="model", parts=partes))
        usos = [p.function_call for p in partes if p.function_call]
        if not usos:
            break

        respuestas = []
        for uso in usos:
            nombre, entrada = uso.name, dict(uso.args or {})
            yield {"tipo": "herramienta", "nombre": nombre, "estado": "inicio"}
            contenido, es_error = "Sin resultado.", True
            if fin == "MAX_TOKENS" and uso is usos[-1]:
                contenido = "La entrada llegó cortada; volvé a intentarlo más corto."
            else:
                for ev in herramientas.ejecutar(nombre, entrada, ctx):
                    if ev["tipo"] == "_resultado":
                        contenido, es_error = ev["contenido"], ev["es_error"]
                    else:
                        yield ev
            yield {"tipo": "herramienta", "nombre": nombre, "estado": "fin", "error": es_error}
            respuestas.append(types.Part(function_response=types.FunctionResponse(
                id=uso.id, name=nombre, response={"error": contenido} if es_error else {"resultado": contenido})))
        # todas las respuestas juntas, en un solo mensaje, como pide la API para llamadas en paralelo
        nuevos.append(types.Content(role="user", parts=respuestas))

    # si el turno se cortó por un error, no se guarda: el próximo pedido arranca limpio
    if completo:
        yield {"tipo": "mensajes", "nuevos": [_a_dict(c) for c in nuevos]}
    yield {"tipo": "fin"}


def extraer_con_ia(nombre: str, contenido: bytes, media_type: str) -> dict:
    """Lee un análisis de suelo en PDF escaneado o foto con Gemini, con salida JSON validada."""
    from google.genai import types

    num = {"type": ["number", "null"]}
    esquema = {
        "type": "object",
        "properties": {
            "filas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "nombre": {"type": ["string", "null"], "description": "potrero, lote o muestra"},
                        "ph": num, "materia_organica": num, "carbono_organico": num, "fosforo_bray": num,
                        "potasio": num, "arena": num, "limo": num, "arcilla": num,
                        "profundidad": {"type": ["string", "null"]},
                    },
                    "required": ["nombre", "ph", "materia_organica", "carbono_organico", "fosforo_bray", "potasio",
                                 "arena", "limo", "arcilla", "profundidad"],
                },
            },
            "laboratorio": {"type": ["string", "null"]},
            "fecha": {"type": ["string", "null"]},
        },
        "required": ["filas", "laboratorio", "fecha"],
    }
    r = _cliente().models.generate_content(
        model=MODELO,
        contents=[
            types.Part.from_bytes(data=contenido, mime_type=media_type),
            "Es un análisis de suelo de laboratorio. Extraé por cada muestra: pH en agua, materia orgánica (%), "
            "carbono orgánico (%), fósforo Bray I (ppm), potasio intercambiable (meq/100 g), arena, limo y arcilla "
            "(%). Si un valor no figura, null. No inventes valores.",
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=esquema,
            thinking_config=types.ThinkingConfig(thinking_level="LOW"),
        ),
    )
    if not r.text:
        raise ValueError("La IA no pudo leer el documento.")
    js = json.loads(r.text)
    for f in js["filas"]:
        if f.get("materia_organica") is None and f.get("carbono_organico") is not None:
            f["materia_organica"] = round(f["carbono_organico"] * 1.724, 2)
    js["filas"] = [{k: v for k, v in f.items() if v is not None} for f in js["filas"]]
    return {"tipo": "analisis_suelo", "metodo": f"leído con IA ({MODELO})", **js}
