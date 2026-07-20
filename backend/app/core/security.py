import base64
import hashlib

from cryptography.fernet import Fernet
from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def _fernet_key(raw: str) -> bytes:
    value = raw.encode("utf-8")
    try:
        decoded = base64.urlsafe_b64decode(value)
        if len(decoded) == 32:
            return value
    except Exception:
        pass
    digest = hashlib.sha256(value).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(secret: str) -> str:
    return Fernet(_fernet_key(get_settings().encryption_key)).encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(secret: str) -> str:
    return Fernet(_fernet_key(get_settings().encryption_key)).decrypt(secret.encode("utf-8")).decode("utf-8")


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.admin_token == "change-me":
        return
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный токен администратора")
