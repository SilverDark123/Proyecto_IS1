from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import time

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Error: clave secreta sin valor por defecto ---
# Antes: SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-here")
# Si la variable de entorno no existe, la aplicación falla al iniciar
# en lugar de usar una clave insegura conocida públicamente.
SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET no está definido en las variables de entorno. "
        "Defina una clave segura (ej. con `openssl rand -hex 32`) antes de iniciar el servidor."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 24 * 60  # 24 horas


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# Error: control de intentos fallidos de login ---
# Esta es una implementación EN MEMORIA, suficiente para el
# alcance académico del proyecto (no requiere tabla nueva en la BD ni Redis).
# Limitación a documentar en el informe: si el servidor se reinicia, el
# contador se reinicia también; y si corren varias instancias del backend,
# cada una tendría su propio contador. Para producción real se recomendaría
# Redis o una tabla en BD.

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutos

_failed_attempts: dict[str, dict] = {}
# estructura: { "dni_o_username": {"count": int, "locked_until": float|None} }


def is_locked_out(identifier: str) -> tuple[bool, int]:
    """Devuelve (esta_bloqueado, segundos_restantes)."""
    record = _failed_attempts.get(identifier)
    if not record or not record.get("locked_until"):
        return False, 0

    remaining = record["locked_until"] - time.time()
    if remaining <= 0:
        # el bloqueo ya expiró, se limpia
        _failed_attempts.pop(identifier, None)
        return False, 0

    return True, int(remaining)


def register_failed_attempt(identifier: str) -> None:
    record = _failed_attempts.setdefault(identifier, {"count": 0, "locked_until": None})
    record["count"] += 1
    if record["count"] >= MAX_FAILED_ATTEMPTS:
        record["locked_until"] = time.time() + LOCKOUT_SECONDS


def reset_attempts(identifier: str) -> None:
    _failed_attempts.pop(identifier, None)