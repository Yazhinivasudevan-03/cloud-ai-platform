"""Integration tests for the cross-deployment (global) alert and optimization
recommendation listings added in Phase 7 to power dashboard-level frontend views."""
from datetime import datetime

from app.models.alert import Alert
from app.models.optimization_recommendation import OptimizationRecommendation


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_deployment(client, token: str, name: str) -> dict:
    project = client.post(
        "/api/v1/projects", json={"name": f"Global Listing Demo {name}"}, headers=_auth_header(token)
    ).json()
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": f"{name}-service"},
        headers=_auth_header(token),
    ).json()
    deployment = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": f"{name}-deploy"},
        headers=_auth_header(token),
    ).json()
    return deployment


def test_global_alerts_listing_spans_multiple_deployments(client, make_user_with_role, db_session):
    operator_token = make_user_with_role("operator_user", "operator")
    deployment_a = _create_deployment(client, operator_token, "alpha")
    deployment_b = _create_deployment(client, operator_token, "beta")

    db_session.add_all(
        [
            Alert(
                deployment_id=deployment_a["id"],
                alert_type="cpu_elevated",
                severity="warning",
                message="a",
                status="active",
                triggered_at=datetime(2026, 7, 15, 10, 0, 0),
            ),
            Alert(
                deployment_id=deployment_b["id"],
                alert_type="cpu_high",
                severity="critical",
                message="b",
                status="active",
                triggered_at=datetime(2026, 7, 15, 11, 0, 0),
            ),
        ]
    )
    db_session.commit()

    # The deployments' own owner sees both (Phase 24: global listing is
    # scoped to the current user's own alerts, not every deployment's).
    response = client.get("/api/v1/alerts", headers=_auth_header(operator_token))
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 2

    filtered = client.get(
        "/api/v1/alerts", params={"deployment_id": deployment_a["id"]}, headers=_auth_header(operator_token)
    )
    assert filtered.status_code == 200
    assert filtered.json()["meta"]["total"] == 1
    assert filtered.json()["items"][0]["deployment_id"] == deployment_a["id"]

    # A different, non-owning user sees none of them.
    other_token = make_user_with_role("other_viewer_user")
    isolated = client.get("/api/v1/alerts", headers=_auth_header(other_token))
    assert isolated.status_code == 200
    assert isolated.json()["meta"]["total"] == 0


def test_global_alerts_listing_404s_on_bad_deployment_filter(client, make_user_with_role):
    token = make_user_with_role("viewer_user")
    response = client.get(
        "/api/v1/alerts", params={"deployment_id": 999999}, headers=_auth_header(token)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEPLOYMENT_NOT_FOUND"


def test_global_optimization_recommendations_listing_spans_multiple_deployments(
    client, make_user_with_role, db_session
):
    operator_token = make_user_with_role("operator_user", "operator")
    deployment_a = _create_deployment(client, operator_token, "gamma")
    deployment_b = _create_deployment(client, operator_token, "delta")

    db_session.add_all(
        [
            OptimizationRecommendation(
                deployment_id=deployment_a["id"],
                recommendation_type="increase_pods",
                description="a",
                status="pending",
            ),
            OptimizationRecommendation(
                deployment_id=deployment_b["id"],
                recommendation_type="reduce_cpu",
                description="b",
                status="applied",
            ),
        ]
    )
    db_session.commit()

    # The deployments' own owner sees both (Phase 24: global listing is
    # scoped to the current user's own deployments, not every deployment).
    response = client.get("/api/v1/optimization-recommendations", headers=_auth_header(operator_token))
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 2

    filtered = client.get(
        "/api/v1/optimization-recommendations",
        params={"status": "pending"},
        headers=_auth_header(operator_token),
    )
    assert filtered.status_code == 200
    assert filtered.json()["meta"]["total"] == 1
    assert filtered.json()["items"][0]["recommendation_type"] == "increase_pods"

    # A different, non-owning user sees none of them.
    other_token = make_user_with_role("other_viewer_user")
    isolated = client.get("/api/v1/optimization-recommendations", headers=_auth_header(other_token))
    assert isolated.status_code == 200
    assert isolated.json()["meta"]["total"] == 0
