#!/usr/bin/env bash
# Compila el frontend y levanta todo en http://localhost:8000 (el backend sirve la app).
# Uso: bash iniciar.sh (desde la raíz del proyecto)
set -e
AQUI="$(cd "$(dirname "$0")" && pwd)"
cd "$AQUI/frontend"
[ -d node_modules ] || npm install
npm run build
cd "$AQUI/backend"
if [ ! -d .venv ]; then
  python -m venv .venv
  if [ -f .venv/Scripts/pip ]; then .venv/Scripts/pip install -r requirements.txt; else .venv/bin/pip install -r requirements.txt; fi
fi
PY=.venv/Scripts/python; [ -f "$PY" ] || PY=.venv/bin/python
# cuenta de Earthdata para SMAP (EARTHDATA_USER y EARTHDATA_PASS), si está: .secretos/ nunca se sube
SECRETOS="$AQUI/.secretos/earthdata.env"
if [ -f "$SECRETOS" ]; then
  # se lee línea por línea y el valor se toma tal cual: con "source", una contraseña con ) ^ $ o el fin de
  # línea de Windows que deja el Bloc de notas rompía el archivo
  while IFS= read -r linea || [ -n "$linea" ]; do
    linea="${linea%$'\r'}"; linea="${linea#export }"
    clave="${linea%%=*}"; valor="${linea#*=}"
    # si la escribieron entre comillas, se sacan
    case "$valor" in \'*\'|\"*\") valor="${valor:1:${#valor}-2}" ;; esac
    case "$clave" in EARTHDATA_USER|EARTHDATA_PASS) export "$clave=$valor" ;; esac
  done < "$SECRETOS"
  [ -n "$EARTHDATA_PASS" ] && echo "SMAP: cuenta de Earthdata cargada ($EARTHDATA_USER)" || echo "SMAP: falta la contraseña en .secretos/earthdata.env"
fi
echo "Seasons Ahead en http://localhost:8000 (Ctrl+C para cortar)"
PYTHONIOENCODING=utf-8 "$PY" -m uvicorn fieldshift.api:app --port 8000
