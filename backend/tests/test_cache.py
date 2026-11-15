"""Pruebas de la memoria compartida (Runtime Cache de Vercel) y límites de tamaño."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

from fieldshift import cache


def test_espacios_compartidos_incluyen_clima_mgap_y_verdor():
    """Verifica que el clima (POWER), el suelo/catastro (MGAP) y el verdor (MODIS/HLS) estén en COMPARTIDOS."""
    # Clima
    assert "power" in cache.COMPARTIDOS, "NASA POWER debe ser compartido entre instancias de Vercel"
    # MGAP
    assert "mgap_padron" in cache.COMPARTIDOS
    assert "mgap_suelo" in cache.COMPARTIDOS
    assert "mgap_suelos_area" in cache.COMPARTIDOS
    assert "mgap_r" in cache.COMPARTIDOS
    assert "mgap_departamentos" in cache.COMPARTIDOS
    # Verdor
    assert "modis_ndvi" in cache.COMPARTIDOS
    assert "modis_historia" in cache.COMPARTIDOS
    assert "modis_historia_tarea" in cache.COMPARTIDOS
    assert "hls_fechas" in cache.COMPARTIDOS
    assert "partes_hls" in cache.COMPARTIDOS
    # Otros esenciales
    assert "smap" in cache.COMPARTIDOS
    assert "analisis" in cache.COMPARTIDOS


def test_tamano_35_anios_power_entra_en_limite_vercel():
    """Comprueba que una respuesta real de 35 años de NASA POWER (~720 KB) cabe holgadamente en el límite de 2 MB de Vercel."""
    # Buscar una muestra real guardada en la caché local
    muestras_power = list(Path("app/backend/cache/power").glob("*.json"))
    if not muestras_power:
        return

    tamano_bytes = muestras_power[0].stat().st_size
    # El límite de Data Cache / Runtime Cache en Vercel es 2 MB (2.097.152 bytes)
    LIMITE_VERCEL_BYTES = 2 * 1024 * 1024
    assert tamano_bytes < LIMITE_VERCEL_BYTES, f"POWER pesa {tamano_bytes} bytes, excede el límite de Vercel"
    # Verificar que además tiene margen amplio (pesa menos de 1 MB)
    assert tamano_bytes < 1024 * 1024, f"POWER pesa {tamano_bytes} bytes, debería pesar ~720 KB"


def test_cache_compartida_lectura_y_escritura(tmp_path, monkeypatch):
    """Simula una segunda instancia de Vercel sin archivo local en /tmp que recupera los datos desde RuntimeCache."""
    # Carpeta temporal aislada simulando la instancia B de Vercel
    monkeypatch.setattr(cache, "CARPETA", tmp_path / "tmp_instancia_b")

    almacen_vercel = {}

    class MockRuntimeCache:
        def get(self, key):
            return almacen_vercel.get(key)

        def set(self, key, value, options=None):
            almacen_vercel[key] = value

    mock_rc = MockRuntimeCache()
    monkeypatch.setattr(cache, "_compartida", lambda: mock_rc)

    # 1. Simular que la instancia A guardó el clima en la memoria compartida
    clave_clima = "-33.10,-56.15,diario"
    datos_clima = {"lat": -33.10, "lon": -56.15, "dias": 13000, "temp": [25.0] * 100}
    cache.guardar("power", clave_clima, datos_clima)

    assert f"power:{cache._ruta('power', clave_clima).stem}" in almacen_vercel

    # 2. Borrar el archivo local para emular que estamos en la instancia B (disco /tmp vacío)
    ruta_local = cache._ruta("power", clave_clima)
    if ruta_local.exists():
        ruta_local.unlink()

    # 3. La instancia B debe leer exitosamente desde la memoria compartida de Vercel
    recuperado = cache.leer("power", clave_clima)
    assert recuperado is not None
    assert recuperado["dias"] == 13000
    assert recuperado["lat"] == -33.10

    # 4. Y además haber populado el /tmp local de la instancia B para que la siguiente lectura sea inmediata
    assert ruta_local.exists()
