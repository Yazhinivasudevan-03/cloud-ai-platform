"""Rate limiting configuration (slowapi/limits), applied per-route via decorators.

The login endpoint uses this to mitigate brute-force credential guessing;
additional routes can opt in with `@limiter.limit(...)` as needed.
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi import FastAPI

limiter = Limiter(key_func=get_remote_address)


def register_rate_limiter(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
