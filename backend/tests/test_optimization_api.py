"""Integration tests for the OptimizationRecommendation REST API."""
from app.models.optimization_recommendation import OptimizationRecommendation


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_deployment(client, token: str) -> dict:
    project = client.post(
        "/api/v1/projects", json={"name": "Optimization API Demo"}, headers=_auth_header(token)
    ).json()
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "opt-api-service"},
        headers=_auth_header(token),
    ).json()
    deployment = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "opt-api-deploy", "memory_limit_mb": 1000},
        headers=_auth_header(token),
    ).json()
    return deployment


def test_deployment_accepts_memory_limit_mb(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, token)
    assert deployment["memory_limit_mb"] == 1000.0


def test_evaluate_optimizations_forbidden_for_viewer(client, make_user_with_role):
    token = make_user_with_role("viewer_user")
    response = client.post("/api/v1/optimization/evaluate", headers=_auth_header(token))
    assert response.status_code == 403


def test_evaluate_optimizations_returns_summary_for_operator(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    response = client.post("/api/v1/optimization/evaluate", headers=_auth_header(token))
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "deployments_evaluated",
        "recommendations_created",
        "recommendations_dismissed",
    }


def test_list_recommendations_requires_existing_deployment(client, make_user_with_role):
    token = make_user_with_role("viewer_user")
    response = client.get(
        "/api/v1/deployments/999999/optimization-recommendations", headers=_auth_header(token)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEPLOYMENT_NOT_FOUND"


def test_list_and_get_and_apply_recommendation(client, make_user_with_role, db_session):
    operator_token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, operator_token)

    recommendation = OptimizationRecommendation(
        deployment_id=deployment["id"],
        recommendation_type="increase_pods",
        description="test recommendation",
        estimated_savings=None,
        status="pending",
    )
    db_session.add(recommendation)
    db_session.commit()
    db_session.refresh(recommendation)

    viewer_token = make_user_with_role("viewer_user")
    list_response = client.get(
        f"/api/v1/deployments/{deployment['id']}/optimization-recommendations",
        params={"status": "pending"},
        headers=_auth_header(viewer_token),
    )
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1

    get_response = client.get(
        f"/api/v1/optimization-recommendations/{recommendation.id}",
        headers=_auth_header(viewer_token),
    )
    assert get_response.status_code == 200
    assert get_response.json()["recommendation_type"] == "increase_pods"

    forbidden_apply = client.patch(
        f"/api/v1/optimization-recommendations/{recommendation.id}",
        json={"status": "applied"},
        headers=_auth_header(viewer_token),
    )
    assert forbidden_apply.status_code == 403

    apply_response = client.patch(
        f"/api/v1/optimization-recommendations/{recommendation.id}",
        json={"status": "applied"},
        headers=_auth_header(operator_token),
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "applied"


def test_cannot_action_already_actioned_recommendation(client, make_user_with_role, db_session):
    operator_token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, operator_token)

    recommendation = OptimizationRecommendation(
        deployment_id=deployment["id"],
        recommendation_type="reduce_cpu",
        description="test",
        status="dismissed",
    )
    db_session.add(recommendation)
    db_session.commit()
    db_session.refresh(recommendation)

    response = client.patch(
        f"/api/v1/optimization-recommendations/{recommendation.id}",
        json={"status": "applied"},
        headers=_auth_header(operator_token),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_RECOMMENDATION_TRANSITION"


def test_get_recommendation_not_found(client, make_user_with_role):
    token = make_user_with_role("viewer_user")
    response = client.get(
        "/api/v1/optimization-recommendations/999999", headers=_auth_header(token)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OPTIMIZATION_RECOMMENDATION_NOT_FOUND"
