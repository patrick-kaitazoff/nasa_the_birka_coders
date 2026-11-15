"""Copia el catálogo (cultivos con color, ícono y tramas; rotaciones; departamentos) dentro del frontend, en
frontend/src/catalogo_inicial.json, para que el plano y las leyendas se dibujen con colores apenas abre la app sin
esperar a /api/catalogo.

La app igual lo pide al servidor y se queda con esa versión. tests/test_catalogo_inicial.py avisa si quedaron
distintos. Correr desde app/backend: .venv/Scripts/python scripts/exportar_catalogo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from fieldshift.api import catalogo  # noqa: E402

SALIDA = RAIZ.parent / "frontend" / "src" / "catalogo_inicial.json"


def main():
    SALIDA.write_text(json.dumps(catalogo(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(SALIDA, round(SALIDA.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
