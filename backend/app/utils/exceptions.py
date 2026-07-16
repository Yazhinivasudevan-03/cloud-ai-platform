"""Application-level exception hierarchy.

Raising one of these anywhere in a service/controller lets the global
exception handlers (see `app.middleware.error_handler`) translate it into a
consistent JSON error envelope with the correct HTTP status code, instead of
leaking a raw 500 traceback to the client.
"""


class AppException(Exception):
    """Base class for all application exceptions."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(AppException):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppException):
    status_code = 409
    code = "CONFLICT"


class UnauthorizedError(AppException):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppException):
    status_code = 403
    code = "FORBIDDEN"


class ValidationAppError(AppException):
    status_code = 422
    code = "VALIDATION_ERROR"
