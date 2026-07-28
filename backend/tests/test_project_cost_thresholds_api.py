"""Integration tests for the project monthly-budget/cost-threshold API
(Phase 21). Phase 24 added the same per-project ownership check every
other Project endpoint now enforces: only the project's own owner (or a
platform is_superuser) may read or write its cost thresholds - role
(viewer/operator/admin) then further gates read vs write for that owner.
"""
def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_project(client, token) -> int:
    response = client.post(
        "/api/v1/projects", json={"name": "cost-threshold-project"}, headers=_auth_header(token)
    )
    return response.json()["id"]


def test_get_cost_thresholds_returns_platform_defaults_when_never_configured(client, make_user_with_role):
    token = make_user_with_role("cost_threshold_viewer", "operator")
    project_id = _create_project(client, token)

    response = client.get(f"/api/v1/projects/{project_id}/cost-thresholds", headers=_auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["monthly_budget"] is None
    assert body["effective_cost_warning_threshold"] == 60.0
    assert body["effective_cost_critical_threshold"] == 80.0
    assert body["effective_cost_saturated_threshold"] == 90.0


def test_owner_can_read_but_not_update_cost_thresholds_without_operator_role(
    client, make_user_with_role, db_session
):
    from app.models.user import Role, User

    token = make_user_with_role("cost_threshold_op", "operator")
    project_id = _create_project(client, token)

    # Still the project's own owner - just stripped back down to the
    # default viewer role after creating it, so only WRITE access is
    # denied (role), not READ access (which ownership alone grants).
    user = db_session.query(User).filter(User.username == "cost_threshold_op").one()
    operator_role = db_session.query(Role).filter(Role.name == "operator").one()
    user.roles.remove(operator_role)
    db_session.commit()

    get_response = client.get(
        f"/api/v1/projects/{project_id}/cost-thresholds", headers=_auth_header(token)
    )
    assert get_response.status_code == 200

    put_response = client.put(
        f"/api/v1/projects/{project_id}/cost-thresholds",
        json={"monthly_budget": 1000.0},
        headers=_auth_header(token),
    )
    assert put_response.status_code == 403


def test_cost_thresholds_are_forbidden_for_a_non_owner(client, make_user_with_role):
    owner_token = make_user_with_role("cost_threshold_owner", "operator")
    other_token = make_user_with_role("cost_threshold_other", "admin")
    project_id = _create_project(client, owner_token)

    get_response = client.get(
        f"/api/v1/projects/{project_id}/cost-thresholds", headers=_auth_header(other_token)
    )
    assert get_response.status_code == 403
    assert get_response.json()["error"]["code"] == "NOT_YOUR_PROJECT"

    put_response = client.put(
        f"/api/v1/projects/{project_id}/cost-thresholds",
        json={"monthly_budget": 1000.0},
        headers=_auth_header(other_token),
    )
    assert put_response.status_code == 403
    assert put_response.json()["error"]["code"] == "NOT_YOUR_PROJECT"


def test_update_cost_thresholds_persists_budget_and_override(client, make_user_with_role):
    token = make_user_with_role("cost_threshold_op_b", "operator")
    project_id = _create_project(client, token)

    response = client.put(
        f"/api/v1/projects/{project_id}/cost-thresholds",
        json={"monthly_budget": 5000.0, "cost_warning_threshold": 40.0},
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["monthly_budget"] == 5000.0
    assert body["cost_warning_threshold"] == 40.0
    assert body["effective_cost_warning_threshold"] == 40.0
    assert body["effective_cost_critical_threshold"] == 80.0  # untouched - platform default


def test_update_cost_thresholds_rejects_non_ascending_tiers(client, make_user_with_role):
    token = make_user_with_role("cost_threshold_op_c", "operator")
    project_id = _create_project(client, token)

    response = client.put(
        f"/api/v1/projects/{project_id}/cost-thresholds",
        json={"cost_warning_threshold": 95.0},  # above the default critical (80)
        headers=_auth_header(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_THRESHOLD_ORDERING"


def test_cost_thresholds_for_nonexistent_project_returns_404(client, make_user_with_role):
    token = make_user_with_role("cost_threshold_op_d", "operator")
    response = client.get("/api/v1/projects/999999/cost-thresholds", headers=_auth_header(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"
