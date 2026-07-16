"""One-time seed script for load testing: creates an admin user (promoted via
a direct DB write, the same bootstrap technique backend/tests/conftest.py
uses) plus a handful of projects/microservices/deployments/pods/resource_usage
rows, so the read-heavy endpoints locustfile.py exercises return realistic,
non-empty data instead of measuring the trivial cost of an empty list.

Run once, before the Locust run, against the same backend the load test will
target:
    docker compose run --rm -v "${PWD}/tests/load:/mnt/load" \\
        --entrypoint python backend /mnt/load/seed_data.py
"""
import os
import sys

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, "/app")  # backend/app is importable inside the backend container
from app.config.settings import get_settings  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.user import UserCreate  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.utils.exceptions import ConflictError  # noqa: E402

BASE_URL = os.getenv("LOAD_TEST_BASE_URL", "http://backend:8000")
ADMIN_USERNAME = "loadtest_admin"
ADMIN_PASSWORD = "Sup3rSecret1"

PROJECT_COUNT = 5
DEPLOYMENTS_PER_PROJECT = 2
PODS_PER_DEPLOYMENT = 3
RESOURCE_USAGE_ROWS_PER_DEPLOYMENT = 24  # a day of hourly samples

# A pool of pre-registered viewer accounts for locustfile.py to log in as -
# registering a fresh account per simulated user would immediately trip
# RATE_LIMIT_REGISTER (see docs/PHASE_10.md), and wouldn't be realistic
# anyway: real dashboard load is mostly existing users logging in and
# browsing, not a flood of brand-new signups.
VIEWER_POOL_SIZE = 20
VIEWER_PASSWORD = "Sup3rSecret1"


def _promote_to_admin(username: str) -> None:
    settings = get_settings()
    engine = create_engine(settings.sqlalchemy_database_uri)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:  # type: Session
        admin_role = session.query(Role).filter(Role.name == "admin").one()
        user = session.query(User).filter(User.username == username).one()
        if admin_role not in user.roles:
            user.roles.append(admin_role)
            session.commit()


def main() -> None:
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "username": ADMIN_USERNAME,
            "email": f"{ADMIN_USERNAME}@example.com",
            "password": ADMIN_PASSWORD,
        },
    )
    if register_response.status_code not in (201, 409):
        raise RuntimeError(f"Unexpected register response: {register_response.text}")

    _promote_to_admin(ADMIN_USERNAME)

    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    login_response.raise_for_status()
    token = login_response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    for p in range(PROJECT_COUNT):
        project_resp = client.post(
            "/api/v1/projects",
            json={"name": f"load-test-project-{p}", "description": "Seeded for load testing"},
        )
        if project_resp.status_code == 409:
            continue
        project_resp.raise_for_status()
        project_id = project_resp.json()["id"]

        microservice_resp = client.post(
            f"/api/v1/projects/{project_id}/microservices",
            json={
                "name": f"load-test-service-{p}",
                "language": "python",
                "repository_url": "https://example.com/repo.git",
            },
        )
        microservice_resp.raise_for_status()
        microservice_id = microservice_resp.json()["id"]

        for d in range(DEPLOYMENTS_PER_PROJECT):
            deployment_resp = client.post(
                f"/api/v1/microservices/{microservice_id}/deployments",
                json={
                    "name": f"load-test-deploy-{p}-{d}",
                    "namespace": f"load-test-ns-{p}-{d}",
                    "replicas": 2,
                    "memory_limit_mb": 512,
                },
            )
            deployment_resp.raise_for_status()
            deployment_id = deployment_resp.json()["id"]

            for pod in range(PODS_PER_DEPLOYMENT):
                client.post(
                    f"/api/v1/deployments/{deployment_id}/pods",
                    json={
                        "pod_name": f"load-test-pod-{p}-{d}-{pod}",
                        "status": "running",
                    },
                ).raise_for_status()

            for row in range(RESOURCE_USAGE_ROWS_PER_DEPLOYMENT):
                client.post(
                    f"/api/v1/deployments/{deployment_id}/resource-usage",
                    json={
                        "cpu_usage_percent": 40.0 + (row % 10),
                        "memory_usage_mb": 256.0 + (row % 20) * 5,
                        "disk_usage_mb": 1024.0,
                        "network_in_kbps": 500.0,
                        "network_out_kbps": 300.0,
                        "recorded_at": f"2026-07-{10 + (row // 24):02d}T{row % 24:02d}:00:00",
                    },
                ).raise_for_status()

    # Created directly through AuthService (bypassing the HTTP endpoint) -
    # bulk-seeding 20 accounts through the rate-limited /auth/register
    # endpoint would trip RATE_LIMIT_REGISTER itself. AuthService has no
    # HTTP-layer concerns, so this is the exact same registration logic the
    # endpoint calls, just invoked directly - not a reimplementation that
    # could drift from it.
    settings = get_settings()
    engine = create_engine(settings.sqlalchemy_database_uri)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        auth_service = AuthService(session)
        for v in range(VIEWER_POOL_SIZE):
            username = f"loadtest_viewer_{v}"
            try:
                auth_service.register(
                    UserCreate(
                        username=username,
                        email=f"{username}@example.com",
                        password=VIEWER_PASSWORD,
                    )
                )
                session.commit()
            except ConflictError:
                session.rollback()

    print(
        f"Seed complete: {PROJECT_COUNT} projects, admin user '{ADMIN_USERNAME}', "
        f"{VIEWER_POOL_SIZE} viewer accounts ready."
    )


if __name__ == "__main__":
    main()
