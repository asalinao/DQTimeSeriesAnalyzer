from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings


router = APIRouter()


class LoginPayload(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(payload: LoginPayload) -> dict:
    settings = get_settings()
    if payload.username != settings.admin_username or payload.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    return {"access_token": settings.admin_token, "token_type": "admin"}
