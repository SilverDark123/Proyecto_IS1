import pytest
import jwt
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from main import app

BASE = "/api/auth"

# Estudiante creado con create_students.py
DNI_VALIDO      = "35127489"
PASSWORD_VALIDO = "123456"

# ─────────────────────────────────────────────────────────────────
# 1. Verificar que el frontend envíe credenciales y reciba respuesta
# Prueba la comunicación real frontend → backend → BD
# ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_integracion_login_respuesta_completa():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"{BASE}/login", json={
            "dni": DNI_VALIDO,
            "password": PASSWORD_VALIDO
        })

    print("\nRespuesta login:", response.json())
    assert response.status_code == 200
    data = response.json()
    # Verifica que la respuesta tenga token y datos del usuario
    assert "token" in data
    assert "user" in data
    assert data["user"]["role"] == "student"


# ─────────────────────────────────────────────────────────────────
# 2. Comprobar que el backend consulte la BD y valide el usuario
# Si el usuario existe en la BD el login debe ser exitoso
# ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_integracion_backend_consulta_bd():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"{BASE}/login", json={
            "dni": DNI_VALIDO,
            "password": PASSWORD_VALIDO
        })

    print("\nConsulta BD:", response.json())
    assert response.status_code == 200
    # Si llegó aquí es que la BD respondió correctamente
    assert "token" in response.json()


# ─────────────────────────────────────────────────────────────────
# 3. Validar que al iniciar sesión se genere un token JWT válido
# Decodifica el token real y verifica su contenido
# ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_integracion_token_jwt_valido():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"{BASE}/login", json={
            "dni": DNI_VALIDO,
            "password": PASSWORD_VALIDO
        })

    assert response.status_code == 200
    token  = response.json()["token"]
    SECRET = os.getenv("SECRET_KEY", "your-secret-key-here")

    # Decodificar el token real generado por el sistema
    decoded = jwt.decode(token, SECRET, algorithms=["HS256"])
    print("\nToken decodificado:", decoded)

    assert "id"   in decoded
    assert "role" in decoded
    assert decoded["role"] == "student"


# ─────────────────────────────────────────────────────────────────
# 4. Confirmar que el registro inserte datos en la BD
# Usa un DNI que no exista para registrar un nuevo estudiante
# ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_integracion_registro_inserta_en_bd():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"{BASE}/register", json={
            "dni": "11223344",
            "password": "Test1234",
            "first_name": "Test",
            "last_name": "Integración",
            "phone": "999888777",
            "parent_name": "Padre Test",
            "parent_phone": "988777666"
        })

    print("\nRegistro nuevo:", response.status_code, response.json())
    # 201 = creado exitosamente, 400 = ya existía de una corrida anterior
    assert response.status_code in [201, 400]
    if response.status_code == 201:
        assert "token" in response.json()


# ─────────────────────────────────────────────────────────────────
# 5. Verificar que un DNI duplicado sea rechazado
# Intenta registrar dos veces el mismo DNI
# ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_integracion_dni_duplicado_rechazado():
    payload = {
        "dni": "55667788",
        "password": "Test1234",
        "first_name": "Duplicado",
        "last_name": "Test",
        "phone": "999111222",
        "parent_name": "Padre",
        "parent_phone": "988111222"
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Primer registro
        r1 = await client.post(f"{BASE}/register", json=payload)
        print("\nPrimer registro:", r1.status_code)
        # Segundo intento con mismo DNI
        r2 = await client.post(f"{BASE}/register", json=payload)
        print("Segundo registro (duplicado):", r2.status_code, r2.json())

    # El segundo debe ser rechazado con 400
    assert r2.status_code == 400
    assert "detail" in r2.json()


# ─────────────────────────────────────────────────────────────────
# 6. Comprobar que rutas protegidas rechacen sin token o token inválido
# ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_integracion_rutas_protegidas_sin_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Sin token
        r1 = await client.get("/api/students/", follow_redirects=True)
        print("\nSin token:", r1.status_code)

        # Con token inválido
        r2 = await client.get("/api/students/",
            headers={"Authorization": "Bearer token_falso_invalido"},
            follow_redirects=True
        )
        print("Token inválido:", r2.status_code)

    assert r1.status_code in [401, 403]
    assert r2.status_code in [401, 403]


# ─────────────────────────────────────────────────────────────────
# 7. Validar que el sistema identifique el rol y devuelva datos correctos
# Un estudiante debe recibir role=student en la respuesta
# ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_integracion_rol_identificado_correctamente():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"{BASE}/login", json={
            "dni": DNI_VALIDO,
            "password": PASSWORD_VALIDO
        })

    assert response.status_code == 200
    data = response.json()
    print("\nRol del usuario:", data["user"]["role"])
    assert data["user"]["role"] == "student"
    assert "dni" in data["user"]


# ─────────────────────────────────────────────────────────────────
# 8. Verificar que los mensajes de error del backend sean claros
# Con credenciales incorrectas el mensaje debe ser legible
# ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_integracion_mensajes_error_claros():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # DNI no existe
        r1 = await client.post(f"{BASE}/login", json={
            "dni": "00000000",
            "password": "cualquiera"
        })
        # Contraseña incorrecta
        r2 = await client.post(f"{BASE}/login", json={
            "dni": DNI_VALIDO,
            "password": "contraseña_incorrecta"
        })

    print("\nMensaje DNI no existe:", r1.json())
    print("Mensaje contraseña incorrecta:", r2.json())

    assert r1.status_code == 401
    assert "detail" in r1.json()
    assert len(r1.json()["detail"]) > 0

    assert r2.status_code == 401
    assert "detail" in r2.json()
    assert len(r2.json()["detail"]) > 0