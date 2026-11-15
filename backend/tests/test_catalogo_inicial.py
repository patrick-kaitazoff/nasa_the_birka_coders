"""El catálogo que viene dentro del frontend tiene que ser el mismo que da /api/catalogo.
Si falla: correr scripts/exportar_catalogo.py y commitear frontend/src/catalogo_inicial.json."""

import json
from pathlib import Path

from fieldshift.api import catalogo

ARCHIVO = Path(__file__).resolve().parents[2] / "frontend" / "src" / "catalogo_inicial.json"


def test_catalogo_del_frontend_igual_al_del_servidor():
    assert json.loads(ARCHIVO.read_text(encoding="utf-8")) == json.loads(json.dumps(catalogo(), ensure_ascii=False))
