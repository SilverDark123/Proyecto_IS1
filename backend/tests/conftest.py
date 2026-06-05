import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config.database as db_module

@pytest.fixture(autouse=True)
async def reset_db_pool():
    """Resetea el pool antes de cada test para que use el loop correcto"""
    # Cierra el pool anterior si existe
    await db_module.close_db_pool()
    # Crea un pool nuevo en el loop actual del test
    await db_module.get_db_pool()
    yield
    # Cierra al finalizar el test
    await db_module.close_db_pool()