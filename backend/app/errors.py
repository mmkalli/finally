"""One error shape for every API error: {"error": "<message>", "code": "<CODE>"} (PLAN.md §8)."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.market import MarketDataError

# PLAN.md §8 error table: code -> HTTP status
ERROR_STATUS: dict[str, int] = {
    "INVALID_TICKER": 400,
    "UNKNOWN_TICKER": 400,
    "INVALID_QUANTITY": 400,
    "INSUFFICIENT_CASH": 400,
    "INSUFFICIENT_SHARES": 400,
    "NO_PRICE": 400,
    "NOT_FOUND": 404,
    "INVALID_REQUEST": 400,  # malformed request body (not in the PLAN table; keeps the shape uniform)
}


class AppError(Exception):
    """Raise anywhere in a request to return {"error": message, "code": code} with the code's status."""

    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status if status is not None else ERROR_STATUS.get(code, 400)

    def to_dict(self) -> dict:
        """The error shape, also used for failed chat actions ({"error", "code"} merged into the action)."""
        return {"error": self.message, "code": self.code}


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message, "code": code}, status_code=status)


async def _app_error(request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.code, exc.message, exc.status)


async def _market_error(request: Request, exc: MarketDataError) -> JSONResponse:
    return error_response(exc.code, str(exc), exc.http_status)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    message = f"{where}: {first.get('msg', 'invalid value')}" if where else first.get("msg", "Invalid request")
    return error_response("INVALID_REQUEST", message, 400)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "NOT_FOUND" if exc.status_code == 404 else f"HTTP_{exc.status_code}"
    return JSONResponse(
        {"error": str(exc.detail), "code": code}, status_code=exc.status_code, headers=getattr(exc, "headers", None)
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(MarketDataError, _market_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
