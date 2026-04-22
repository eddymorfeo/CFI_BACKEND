from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.errors import AppException


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exception: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exception.status_code,
            content=exception.to_response(),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_: Request, exception: HTTPException) -> JSONResponse:
        detail = exception.detail
        message = detail if isinstance(detail, str) else "Ocurrió un error en la solicitud."

        return JSONResponse(
            status_code=exception.status_code,
            content={
                "success": False,
                "error_code": "HTTP_ERROR",
                "message": message,
                "detail": detail,
                "context": {},
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(_: Request, exception: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Ocurrió un error interno del servidor.",
                "detail": str(exception),
                "context": {},
            },
        )