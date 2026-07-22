"""Writes a real AuditLog row for every mutating request (POST/PUT/PATCH/
DELETE) - the audit trail the AuditLog model was originally built for but
never actually populated (see docs/PHASE_18.md). Logs regardless of the
response status: a denied/failed mutation attempt (403, 404, 422) is
genuinely audit-worthy too, arguably more so than a routine success.

Read-only requests (GET/HEAD/OPTIONS) are never logged - an audit trail
records who changed what, not who looked at what, and logging every GET
would drown the real signal in traffic noise.

Reuses the same session `Depends(get_db)` already stashed on
`request.state.db_session` for this request (see
`app/database/session.py`) rather than opening a second, independent
connection - a second connection auditing a row this same request just
wrote (e.g. a brand-new user during registration) would otherwise be
checking a foreign key against a row whose owning transaction it has no
special knowledge has already committed, which is a real, if narrow, race
in general and is *guaranteed* to deadlock in this project's own test
harness, where a test's transaction is deliberately held open (never
committed) for the whole test. Falls back to a fresh session only if
nothing stashed one (no endpoint currently exists that mutates data
without depending on `get_db`, but this keeps the middleware correct if
one ever did).
"""
import re

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.database.session import SessionLocal
from app.models.audit_log import AuditLog
from app.utils.logger import get_logger

logger = get_logger("audit")

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Matches /api/v1/{entity_type}[/{entity_id}][/...] - e.g. /api/v1/projects/42
# captures entity_type="projects", entity_id=42. A create (POST with no ID
# in the path yet) or a nested/action path (e.g.
# /deployments/9/sync-cloud-metrics) still captures the top-level entity_type;
# entity_id is left null when the path has no numeric segment there.
_ENTITY_FROM_PATH = re.compile(r"^/api/v1/([a-zA-Z\-]+)(?:/(\d+))?")


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if request.method in _MUTATING_METHODS:
            self._record(request, response)

        return response

    def _record(self, request: Request, response: Response) -> None:
        user = getattr(request.state, "current_user", None)
        match = _ENTITY_FROM_PATH.match(request.url.path)
        entity_type = match.group(1) if match else "unknown"
        entity_id = int(match.group(2)) if match and match.group(2) else None

        db = getattr(request.state, "db_session", None)
        owns_session = db is None
        if db is None:
            db = SessionLocal()
        try:
            db.add(
                AuditLog(
                    user_id=user.id if user else None,
                    action=f"{request.method} {request.url.path}",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    details=f"status={response.status_code}",
                    ip_address=request.client.host if request.client else None,
                )
            )
            db.commit()
        except Exception:
            # An audit-logging failure must never take down the actual
            # request it's trying to record - log and move on.
            logger.exception("Failed to write audit log entry")
            db.rollback()
        finally:
            if owns_session:
                db.close()
