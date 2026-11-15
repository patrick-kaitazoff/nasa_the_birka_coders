"""Pruebas del diagnóstico de ECOSTRESS del campo de ejemplo (sin red)."""

from fieldshift.fuentes import ecostress


def test_cargar_diagnostico_ecostress():
    diag = ecostress.cargar_diagnostico_ecostress()
    assert diag["fuente"] == "NASA ECOSTRESS (ISS)"
    dc = diag["diagnostico_campo"]
    assert dc["pasadas_con_dato_valido"] + dc["pasadas_con_nube_o_corte"] == dc["pasadas_totales_orbita"]
    # Comprobado contra Earth Engine (L2T_LSTE V2 sobre el polígono del ejemplo)
    f = next(f for f in diag["fechas_clave_ejemplo"] if f["fecha"] == "2023-01-10")
    assert (f["temperatura_min_c"], f["temperatura_max_c"], f["temperatura_media_c"]) == (34.1, 46.7, 41.4)
    assert round(f["temperatura_max_c"] - f["temperatura_min_c"], 1) == f["rango_intralote_c"]
