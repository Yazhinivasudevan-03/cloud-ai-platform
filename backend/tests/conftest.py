"""Pytest fixtures: an isolated test database and a FastAPI TestClient wired to it.

Tests run against a real MySQL schema (not SQLite) so behaviour matches
production exactly. Each test runs inside a transaction that is rolled back
afterwards, giving full isolation without recreating tables per test.
"""
import os

# Force the test database names even if already set in the environment (e.g.
# when running inside the backend container), so tests never touch the
# development schemas - both the main application database and the separate
# login-credentials database (see docs/PHASE_13.md) get their own test schema.
os.environ["MYSQL_DATABASE"] = "cloud_ai_platform_test"
os.environ["AUTH_MYSQL_DATABASE"] = "cloud_ai_auth_test"
# Tracing itself is unit-tested directly against a throwaway app/engine in
# test_observability.py - disabled here so every one of this suite's many
# HTTP requests doesn't also print a ConsoleSpanExporter span to stdout.
os.environ["OTEL_ENABLED"] = "false"
# Auto-apply is unit-tested explicitly, per test, via monkeypatch - forced
# off here so a developer's own local .env (e.g. enabled for a live demo
# against the real dev stack) can never leak into `docker compose run`'s
# inherited service environment and make this suite's default-off
# assertions fail non-deterministically depending on host state. This is
# a real bug this project's own test suite caught, not a hypothetical one.
os.environ["OPTIMIZATION_AUTO_APPLY_ENABLED"] = "false"

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.database.base import Base
from app.database.session import get_db
import app.models  # noqa: F401 registers all models
from app.main import app
from app.middleware.rate_limiter import limiter
from app.models.user import Role, User

settings = get_settings()

engine = create_engine(settings.sqlalchemy_database_uri, pool_pre_ping=True)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Mirrors backend/alembic/versions/59b011f59240_seed_default_roles.py: the test
# schema is built via metadata.create_all (not Alembic), so that data-only
# migration never runs here - these roles are seeded directly instead.
_SEED_ROLES = [
    ("viewer", "Read-only access to dashboards and reports"),
    ("operator", "Can create and update platform resources"),
    ("admin", "Full administrative access, including user and role management"),
]


@pytest.fixture(scope="session", autouse=True)
def _create_test_schema():
    Base.metadata.create_all(bind=engine)
    with TestSessionLocal() as session:
        for name, description in _SEED_ROLES:
            session.add(Role(name=name, description=description))
        session.commit()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Each test gets a fresh rate-limit budget so login-heavy tests don't
    trip the login endpoint's brute-force protection against each other."""
    limiter.reset()
    yield


@pytest.fixture()
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session: Session = TestSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    def _override_get_db(request: Request):
        # Stash the same shared test session AuditLogMiddleware reuses, so
        # its writes land in the same never-committed test transaction as
        # everything else in the test, rather than a second connection
        # deadlocking against locks that transaction is still holding - see
        # app/database/session.py's get_db() for the equivalent production
        # behavior.
        request.state.db_session = db_session
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


DEFAULT_TEST_PASSWORD = "Sup3rSecret1"


@pytest.fixture()
def make_user_with_role(client: TestClient, db_session: Session):
    """Factory fixture: register a user via the real API, then optionally
    grant it an extra role by writing directly to the DB. Granting roles
    through the API itself requires an existing admin, so bootstrapping the
    very first admin/operator in a test has to reach around the API once;
    every other permission check in these tests still goes through HTTP.
    Returns a valid access token for the new user.
    """

    def _make(username: str, role_name: str | None = None) -> str:
        client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": DEFAULT_TEST_PASSWORD,
            },
        )
        if role_name:
            role = db_session.query(Role).filter(Role.name == role_name).one()
            user = db_session.query(User).filter(User.username == username).one()
            user.roles.append(role)
            db_session.commit()

        response = client.post(
            "/api/v1/auth/login",
            data={"username": username, "password": DEFAULT_TEST_PASSWORD},
        )
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    return _make
