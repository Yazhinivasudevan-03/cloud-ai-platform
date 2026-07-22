"""SQLAlchemy engine/session management and the FastAPI `get_db` dependency."""
from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings

settings = get_settings()

engine = create_engine(
    settings.sqlalchemy_database_uri,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and guarantees it is
    closed after the request, even if an exception is raised.

    Also stashes the session on `request.state.db_session` - `AuditLogMiddleware`
    reuses this same session/connection for its own write rather than opening
    a second one, since a separate connection auditing a row this same
    request just created (e.g. a brand-new user) would otherwise have to
    wait for a lock that specific row's own (already-committed-by-here)
    transaction held only moments earlier - harmless in production where
    that commit already happened, but see docs/PHASE_18.md for why a second
    connection matters more than it sounds in this project's own test
    harness, where a test's transaction is deliberately never committed.
    """
    db = SessionLocal()
    request.state.db_session = db
    try:
        yield db
    finally:
        db.close()
