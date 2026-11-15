"""Punto de entrada para Vercel: expone la app de FastAPI que vive en backend/fieldshift/api.py.

En local se sigue levantando con `bash app/iniciar.sh` (uvicorn desde app/backend); este archivo solo lo usa
Vercel, que busca un `app` en main.py. El frontend se compila antes de subir (frontend/dist) y lo sirve la
misma app.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from fieldshift.api import app  # noqa: E402,F401
