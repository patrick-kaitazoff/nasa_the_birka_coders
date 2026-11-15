"""Guarda en el repo una serie de SMAP L4 bajada a mano de AppEEARS, para no esperar a la NASA.

AppEEARS tarda horas con SMAP. Con esto, el CSV de
un pedido ya terminado queda en fieldshift/datos/smap/<clave>.json y la app lo usa sin pedir nada
(fuentes/smap.py → guardado).

Uso desde app/backend (el CSV es el *-SPL4SMGP-008-results.csv del zip que da AppEEARS):
    .venv/Scripts/python scripts/guardar_smap.py <results.csv> [<id del pedido>]

Si el CSV trae varios puntos (columna ID), guarda uno por punto. La clave sale de la latitud y longitud de
cada punto redondeadas a 2 decimales, igual que en la app.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fieldshift.fuentes import smap  # noqa: E402


def guardar(csv_path: Path, pedido: str | None = None) -> list[Path]:
    texto = csv_path.read_text(encoding="utf-8")
    por_punto: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for fila in csv.DictReader(io.StringIO(texto)):
        por_punto[(fila.get("ID", ""), fila["Latitude"], fila["Longitude"])].append(fila)
    smap.DIR_GUARDADOS.mkdir(parents=True, exist_ok=True)
    escritos = []
    for (pid, lat, lon), filas in por_punto.items():
        salida = io.StringIO()
        w = csv.DictWriter(salida, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
        serie = smap.leer_csv(salida.getvalue())
        if not serie:
            print(f"  {pid}: sin datos válidos, no se guarda")
            continue
        la, lo = float(lat), float(lon)
        destino = smap.DIR_GUARDADOS / f"{smap._clave(la, lo)}.json"
        datos = {
            "fuente": f"NASA SMAP L4 ({smap.PRODUCTO}) vía AppEEARS",
            "pedido_appeears": pedido,
            "punto": {"id": pid, "lat": la, "lon": lo},
            "desde": serie[0]["fecha"],
            "hasta": serie[-1]["fecha"],
            "bajado": dt.date.today().isoformat(),
            "serie": serie,
        }
        destino.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        escritos.append(destino)
        print(f"  {pid} ({la}, {lo}) → {destino.name}: {len(serie)} días, {serie[0]['fecha']} a {serie[-1]['fecha']}, "
              f"{destino.stat().st_size // 1024} KB")
    return escritos


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    guardar(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None)
