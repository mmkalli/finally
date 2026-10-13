# backend/app/errors.py
"""One error shape for every API failure: {"error": message, "code": code} (PLAN.md §8)."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.market import MarketDataError


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message, "code": code}, status_code=status)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.code, exc.message, exc.status)

    @app.exception_handler(MarketDataError)
    async def _market_error(_: Request, exc: MarketDataError) -> JSONResponse:
        return error_response(exc.code, str(exc), exc.http_status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        field = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = f"Invalid request: {field} {first.get('msg', '')}".strip() if field else "Invalid request body"
        return error_response("INVALID_REQUEST", message, 422)
