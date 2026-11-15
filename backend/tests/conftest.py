"""Las pruebas no salen a internet: la lluvia de GPM IMERG (que se pide a Giovanni) queda apagada en todas, salvo en
las que la prueban y ponen su propia serie."""

import pytest

from fieldshift.fuentes import imerg
from fieldshift.fuentes import relieve as fuente_relieve


@pytest.fixture(autouse=True)
def _sin_imerg(monkeypatch):
    def apagado(lat, lon):
        raise RuntimeError("IMERG apagado en las pruebas")

    monkeypatch.setattr(imerg, "serie", apagado)


@pytest.fixture(autouse=True)
def _sin_suelos_por_area(monkeypatch):
    """El suelo de cada lote se busca en el grupo CONEAT o la unidad de SSURGO que ocupa más superficie:
    en las pruebas esa consulta por área queda apagada y el suelo sale del punto, como antes."""
    from fieldshift.fuentes import mgap, ssurgo

    def apagado(*a, **k):
        raise RuntimeError("suelos por área apagado en las pruebas")

    monkeypatch.setattr(mgap, "suelos_en_area", apagado)
    monkeypatch.setattr(ssurgo, "secciones_por_suelo", apagado)


@pytest.fixture(autouse=True)
def _sin_srtm(monkeypatch):
    """El largo de ladera del análisis sale de SRTM: en las pruebas no se baja; la erosión sigue con 100 m,
    salvo en las que prueban el relieve y ponen su propia elevación."""
    def apagado(*a, **k):
        raise RuntimeError("SRTM apagado en las pruebas")

    monkeypatch.setattr(fuente_relieve, "mosaico", apagado)


@pytest.fixture(autouse=True)
def _sin_earth_engine(monkeypatch):
    """Earth Engine (historia de MODIS y NDVI de HLS) queda apagado en las pruebas: con la cuenta de servicio
    en la PC, alguna prueba se conectaba de verdad. Las que prueban HLS simulan la respuesta y lo vuelven a prender."""
    monkeypatch.setenv("DESACTIVAR_EE", "1")
