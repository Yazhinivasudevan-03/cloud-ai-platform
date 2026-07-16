"""Load test for the Cloud AI Platform backend API.

Run tests/load/seed_data.py first (creates 20 viewer accounts + 5 projects
with deployments/pods/resource-usage), then run this against the same
backend, e.g.:

    docker run --rm --network cloud-ai-platform_cloud-ai-network \\
        -v "$(pwd)/tests/load:/mnt/locust" -p 8089:8089 \\
        locustio/locust -f /mnt/locust/locustfile.py --host http://backend:8000

Simulates realistic dashboard traffic: mostly read-heavy browsing (the
platform's actual usage pattern - operators/viewers checking on monitored
infrastructure) with a much smaller share of write operations (alert/
optimization evaluation - the same on-demand endpoints APScheduler calls
automatically every few minutes in production).
"""
import random
import time

from locust import HttpUser, between, task

LOGIN_RETRY_ATTEMPTS = 5
LOGIN_RETRY_BACKOFF_SECONDS = 3


def _login_or_stop(user: HttpUser, username: str, password: str) -> bool:
    """Log in, retrying on RATE_LIMIT_LOGIN's 429 (see docs/PHASE_10.md - all
    simulated users share this test runner's single IP, so even a
    conservative ramp-up can occasionally still land two logins in the same
    rate-limit window). Returns False (and stops the user) if login never
    succeeds - the correct behavior is for that simulated user to give up
    cleanly, not to silently run every subsequent request unauthenticated,
    which is exactly the bug an earlier version of this file had: it assumed
    `response.json()["access_token"]` always existed and never checked the
    login response's status code first.
    """
    for attempt in range(LOGIN_RETRY_ATTEMPTS):
        response = user.client.post(
            "/api/v1/auth/login",
            data={"username": username, "password": password},
            name="/api/v1/auth/login",
        )
        if response.status_code == 200:
            token = response.json()["access_token"]
            user.client.headers["Authorization"] = f"Bearer {token}"
            return True
        if response.status_code != 429:
            break  # a real failure (bad credentials etc.) - retrying won't help
        time.sleep(LOGIN_RETRY_BACKOFF_SECONDS)

    user.environment.runner.stats.log_error(
        "POST", "/api/v1/auth/login", f"gave up after {LOGIN_RETRY_ATTEMPTS} attempts"
    )
    user.stop()
    return False

VIEWER_POOL_SIZE = 20
VIEWER_PASSWORD = "Sup3rSecret1"
ADMIN_USERNAME = "loadtest_admin"
ADMIN_PASSWORD = "Sup3rSecret1"


class DashboardViewerUser(HttpUser):
    """The dominant traffic pattern: an already-registered viewer logging in
    and browsing dashboards - list projects, drill into one, check its
    deployments/pods/alerts/predictions. No writes (viewers can't write)."""

    wait_time = between(1, 3)
    weight = 9

    def on_start(self) -> None:
        self.project_ids: list[int] = []
        self.deployment_ids: list[int] = []
        username = f"loadtest_viewer_{random.randint(0, VIEWER_POOL_SIZE - 1)}"
        _login_or_stop(self, username, VIEWER_PASSWORD)

    @task(5)
    def list_projects(self) -> None:
        response = self.client.get("/api/v1/projects", name="/api/v1/projects")
        if response.ok:
            self.project_ids = [p["id"] for p in response.json().get("items", [])]

    @task(3)
    def view_project_detail(self) -> None:
        if not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        self.client.get(f"/api/v1/projects/{project_id}", name="/api/v1/projects/[id]")
        response = self.client.get(
            f"/api/v1/projects/{project_id}/microservices",
            name="/api/v1/projects/[id]/microservices",
        )
        if response.ok:
            items = response.json().get("items", [])
            for microservice in items:
                deployments_resp = self.client.get(
                    f"/api/v1/microservices/{microservice['id']}/deployments",
                    name="/api/v1/microservices/[id]/deployments",
                )
                if deployments_resp.ok:
                    self.deployment_ids.extend(
                        d["id"] for d in deployments_resp.json().get("items", [])
                    )

    @task(4)
    def view_deployment_detail(self) -> None:
        if not self.deployment_ids:
            return
        deployment_id = random.choice(self.deployment_ids)
        self.client.get(
            f"/api/v1/deployments/{deployment_id}/pods", name="/api/v1/deployments/[id]/pods"
        )
        self.client.get(
            f"/api/v1/deployments/{deployment_id}/resource-usage",
            name="/api/v1/deployments/[id]/resource-usage",
        )
        self.client.get(
            f"/api/v1/deployments/{deployment_id}/predictions",
            name="/api/v1/deployments/[id]/predictions",
        )

    @task(2)
    def view_alerts(self) -> None:
        self.client.get("/api/v1/alerts", name="/api/v1/alerts")

    @task(2)
    def view_optimization_recommendations(self) -> None:
        self.client.get(
            "/api/v1/optimization-recommendations", name="/api/v1/optimization-recommendations"
        )

    @task(1)
    def view_notifications(self) -> None:
        self.client.get("/api/v1/notifications", name="/api/v1/notifications")

    @task(1)
    def view_own_profile(self) -> None:
        self.client.get("/api/v1/auth/me", name="/api/v1/auth/me")


class OperatorUser(HttpUser):
    """A much smaller share of traffic: an operator triggering the same
    on-demand alert/optimization evaluation endpoints APScheduler already
    calls automatically every few minutes in production (Phase 5/6) - here
    exercised under concurrent load instead of on a timer."""

    wait_time = between(5, 10)
    weight = 1

    def on_start(self) -> None:
        _login_or_stop(self, ADMIN_USERNAME, ADMIN_PASSWORD)

    @task(1)
    def evaluate_alerts(self) -> None:
        self.client.post("/api/v1/alerts/evaluate", name="/api/v1/alerts/evaluate")

    @task(1)
    def evaluate_optimizations(self) -> None:
        self.client.post("/api/v1/optimization/evaluate", name="/api/v1/optimization/evaluate")
