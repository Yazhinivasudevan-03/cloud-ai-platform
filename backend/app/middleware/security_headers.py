"""Adds standard defensive HTTP response headers to every response.

This is a browser-facing hardening layer, distinct from the transport-level
concerns (TLS) a real deployment's reverse proxy/ingress is responsible for
(see kubernetes/base/ingress.yaml and docs/PHASE_10.md's HTTPS-readiness
notes) - these headers matter whether or not TLS is present.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        # Stops the browser from MIME-sniffing a response away from the
        # declared Content-Type (e.g. treating a JSON error body as HTML).
        response.headers["X-Content-Type-Options"] = "nosniff"
        # This API is never meant to be framed - blocks clickjacking-style
        # embedding of any of its responses (most relevant to /docs, /redoc).
        response.headers["X-Frame-Options"] = "DENY"
        # Don't leak the full request URL (which may contain query params)
        # to third-party origins linked from API-served pages.
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # This is a JSON API - no page here needs geolocation/camera/etc.
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=()"
        )
        return response
