import pytest
import jwt
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta
from main import app
from config.database import get_db
from utils.security import get_password_hash, verify_password, create_access_token

BASE = "/api/auth"

# HELPER: crea un mock de conexión a la BD y lo inyecta en FastAPI
# Usa app.dependency_overrides para reemplazar get_db completamente
def override_db(mock_conn):
    """Retorna una función generadora que FastAPI acepta como dependencia"""
    async def _get_db_override():
        yield mock_conn
    return _get_db_override

def make_mock_db():
    db = AsyncMock()
    db.fetchrow = AsyncMock()
    db.execute  = AsyncMock()
    return db

# 1. FUNCIONAL — Login con credenciales válidas
@pytest.mark.asyncio
async def test_login_credenciales_validas():
    password_real = "password123"
    hashed        = get_password_hash(password_real)

    mock_db = make_mock_db()
    mock_db.fetchrow.side_effect = [
        None,   # tabla users: no existe
        {       # tabla students: sí existe
            "id": 1,
            "dni": "12345678",
            "first_name": "Juan",
            "last_name": "Perez",
            "password_hash": hashed
        }
    ]

    app.dependency_overrides[get_db] = override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"{BASE}/login", json={
                "dni": "12345678",
                "password": password_real
            })
    finally:
        app.dependency_overrides.clear()

    print("Login válido:", response.json())
    assert response.status_code == 200
    assert "token" in response.json()


# 2. VALIDACIÓN — Rechaza credenciales incorrectas
@pytest.mark.asyncio
async def test_login_credenciales_incorrectas():
    hashed = get_password_hash("password_correcta")

    mock_db = make_mock_db()
    mock_db.fetchrow.side_effect = [
        None,
        {
            "id": 1,
            "dni": "12345678",
            "first_name": "Juan",
            "last_name": "Perez",
            "password_hash": hashed
        }
    ]

    app.dependency_overrides[get_db] = override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"{BASE}/login", json={
                "dni": "12345678",
                "password": "contraseña_incorrecta"
            })
    finally:
        app.dependency_overrides.clear()

    print("Login inválido:", response.json())
    assert response.status_code == 401


# 3. SEGURIDAD — Contraseña almacenada encriptada
def test_contrasena_encriptada():
    password = "miPassword123"
    hashed   = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("otraContraseña", hashed) is False


# 4. SEGURIDAD — Token JWT generado correctamente 
def test_token_jwt_generado_correctamente():
    data  = {"sub": "99", "role": "student"}
    token = create_access_token(data)

    assert token is not None
    assert isinstance(token, str)

    SECRET  = os.getenv("SECRET_KEY", "your-secret-key-here")
    decoded = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert decoded["sub"]  == "99"
    assert decoded["role"] == "student"


# 5. CONTROL DE ACCESO 
@pytest.mark.asyncio
async def test_ruta_protegida_sin_token():
    mock_db = make_mock_db()
    mock_db.fetchrow.return_value = None

    app.dependency_overrides[get_db] = override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/students/", follow_redirects=True)
    finally:
        app.dependency_overrides.clear()

    print("Sin token:", response.status_code)
    assert response.status_code in [401, 403]

# 6. VALIDACIÓN DE DATOS 
@pytest.mark.asyncio
async def test_registro_campos_vacios():
    mock_db = make_mock_db()

    app.dependency_overrides[get_db] = override_db(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"{BASE}/register", json={})
    finally:
        app.dependency_overrides.clear()

    print("Campos vacíos:", response.status_code, response.json())
    assert response.status_code == 422


# 7. INTEGRACIÓN — No registra DNI duplicado
@pytest.mark.asyncio
async def test_registro_dni_duplicado():
    mock_db = make_mock_db()
    mock_db.fetchrow.return_value = {"id": 5}

    app.dependency_overrides[get_db] = override_db(mock_db)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:

            response = await client.post(
                f"{BASE}/register",
                json={
                    "dni": "111111e1",
                    "password": "Test1234",
                    "first_name": "Juan",
                    "last_name": "Perez",
                    "phone": "999999999",
                    "parent_name": "Papa",
                    "parent_phone": "988888888"
                }
            )
    finally:
        app.dependency_overrides.clear()

    data = response.json()

    assert response.status_code == 400
    assert data["detail"] == \
        "DNI registrado previamente, por favor ingrese otro"

# 8. MANEJO DE ERRORES — Mensaje adecuado cuando el DNI no existe
@pytest.mark.asyncio
async def test_mensaje_error_login_fallido():
    mock_db = make_mock_db()
    mock_db.fetchrow.side_effect = [None, None]

    app.dependency_overrides[get_db] = override_db(mock_db)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:

            response = await client.post(
                f"{BASE}/login",
                json={
                    "dni": "00000000",
                    "password": "cualquiera"
                }
            )
    finally:
        app.dependency_overrides.clear()

    data = response.json()

    assert response.status_code == 401

    assert data["detail"] == \
        "No se encontró este DNI. Verifica el número o regístrate primero."
  
# 9. AUTORIZACIÓN — El token generado contiene role=student
from utils.security import create_access_token


@pytest.mark.asyncio
async def test_estudiante_no_puede_acceder_panel_admin():

    token = create_access_token({
        "id": 1,
        "role": "student"
    })

    mock_db = make_mock_db()

    mock_db.fetchrow.side_effect = [
        {
            "id": 1,
            "dni": "12345678"
        }
    ]

    app.dependency_overrides[get_db] = override_db(mock_db)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:

            response = await client.get(
                "/api/admin/dashboard",
                headers={
                    "Authorization": f"Bearer {token}"
                }
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403

    assert response.json()["detail"] == \
        "Not enough permissions"

# 10. EXPIRACIÓN DEL TOKEN — Token expirado es rechazado
def test_token_expirado_es_rechazado():
    @pytest.mark.asyncio
    async def test_token_expirado_es_rechazado():

        token_expirado = create_access_token(
            {
                "id": 1,
                "role": "student"
            },
            expires_delta=timedelta(hours=-1)
        )

        mock_db = make_mock_db()

        app.dependency_overrides[get_db] = override_db(mock_db)

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:

                response = await client.get(
                    "/api/admin/dashboard",
                    headers={
                        "Authorization": f"Bearer {token_expirado}"
                    }
                )

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 401

        assert response.json()["detail"] == \
            "Invalid authentication credentials"