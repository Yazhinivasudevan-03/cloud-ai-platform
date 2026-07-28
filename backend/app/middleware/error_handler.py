"""Global exception handlers producing a consistent JSON error envelope."""
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.utils.exceptions import AppException
from app.utils.logger import get_logger

logger = get_logger("http.validation")


def _humanize_validation_errors(errors: list[dict]) -> str:
    """Turns Pydantic's structured error list into a real, specific
    message - e.g. "mobile_number must be in E.164 format, e.g.
    +14155552671" or "Missing required field: country" - instead of the
    generic, unhelpful "Request validation failed" this replaces. Multiple
    simultaneous errors are joined so nothing is silently dropped."""
    messages: list[str] = []
    for error in errors:
        loc = [part for part in error.get("loc", []) if part != "body"]
        field = ".".join(str(part) for part in loc) if loc else None

        if error.get("type") == "missing" and field:
            messages.append(f"Missing required field: {field}")
            continue

        # Pydantic v2 prefixes every field_validator/model_validator-raised
        # ValueError with "Value error, " - strip that boilerplate so only
        # the real, specific message (written by this project's own
        # validators, e.g. "password and confirm_password must match") is
        # shown, whether or not the error is tied to a single field.
        raw_msg = error.get("msg", "")
        messages.append(raw_msg.removeprefix("Value error, "))

    return "; ".join(messages) if messages else "Request validation failed"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # exc.errors() may embed raw exception objects (e.g. a ValueError raised
        # inside a field_validator) in its "ctx" field, which json.dumps cannot
        # serialize directly - jsonable_encoder converts them to strings first.
        errors = jsonable_encoder(exc.errors())
        message = _humanize_validation_errors(errors)

        # Prints the exact validation failure to the terminal (JSON-formatted,
        # see app/utils/logger.py) - `extra` surfaces the full per-field error
        # list as its own log field, not just the summarized message string,
        # so the real cause is always visible server-side even if a client
        # only shows a generic banner.
        logger.warning(
            "Request validation failed for %s %s: %s",
            request.method,
            request.url.path,
            message,
            extra={"validation_errors": errors},
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": message,
                    "details": errors,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}},
        )
