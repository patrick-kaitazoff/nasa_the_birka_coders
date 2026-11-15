"""Pruebas de la aptitud de FAO GAEZ v4 (grilla de Uruguay guardada, sin red)."""

from fieldshift.fuentes import gaez


def test_grilla_cubre_uruguay():
    datos = gaez.cargar_datos_gaez()
    g = datos["grilla"]
    assert (g["ancho"], g["alto"]) == (66, 60)
    for capas in (datos["cultivos"], datos["cultivos_1981_2010"]):
        for capa in capas.values():
            assert len(capa["clase"]) == len(capa["indice"]) == 66 * 60
    # La app usa 2011-2040 (promedio de 5 modelos, RCP 4.5) y guarda 1981-2010 para comparar
    assert "2011-2040" in datos["periodo"] and "1981-2010" in datos["periodo_antes"]


def test_campo_de_ejemplo():
    # 1981-2010 comprobado a mano contra el servicio de la FAO (identify de sxHr_soy y sxHr_srg); el
    # promedio de 5 modelos de 2011-2040 coincide con el ENSEMBLE de GAEZ en los 6 cultivos que lo tienen
    apt = gaez.aptitud_punto(-33.1, -56.15)
    assert apt["soja"] == {"clase": 2, "aptitud": "alta", "indice": 70,
                           "clase_antes": 3, "aptitud_antes": "buena", "indice_antes": 66}
    assert apt["sorgo"] == {"clase": 4, "aptitud": "media", "indice": 49,
                            "clase_antes": 4, "aptitud_antes": "media", "indice_antes": 51}


def test_cada_campo_usa_su_celda():
    # Soriano (litoral) da distinto que Durazno: antes todos los campos recibían los datos de Durazno
    assert gaez.aptitud_punto(-33.3, -58.0)["soja"]["clase"] == 1
    assert gaez.aptitud_punto(-33.1, -56.15)["soja"]["clase"] == 2


def test_fuera_de_uruguay_no_dice_nada():
    assert gaez.aptitud_punto(40.0, -95.0) == {}
    assert gaez.frases_rotacion(["soja", "trigo"], 40.0, -95.0) == []


def test_frase_rotacion():
    frases = gaez.frases_rotacion(["trigo", "soja2", "sorgo", "trigo", "cobertura", "maiz"], -33.1, -56.15)
    base = "FAO GAEZ v4 en la zona (secano, clima 2011-2040 según 5 modelos, celda de ~9 km): "
    assert frases == [base + "aptitud alta (índice 70-76 de 100) para Trigo y Soja.",
                      base + "aptitud buena (índice 69 de 100) para Maíz.",
                      base + "aptitud media (índice 49 de 100) para Sorgo.",
                      "Con el clima de 1981-2010, GAEZ daba aptitud buena para Trigo y Soja."]
    # pradera, verdeos y campo natural no tienen equivalente en GAEZ
    assert gaez.frases_rotacion(["pradera", "campo_natural"], -33.1, -56.15) == []
