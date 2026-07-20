import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import init_db


def error_response(code: str, message: str, status_code: int, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}, "request_id": str(uuid.uuid4())}},
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="DQ Time Series Service", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_request: Request, exc: StarletteHTTPException):
        return error_response("HTTP_ERROR", str(exc.detail), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exc: RequestValidationError):
        return error_response("VALIDATION_ERROR", "Некорректные данные запроса", 422, {"errors": exc.errors()})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception):
        return error_response("INTERNAL_ERROR", "Внутренняя ошибка сервиса", 500, {"reason": str(exc)})

    return app


app = create_app()
