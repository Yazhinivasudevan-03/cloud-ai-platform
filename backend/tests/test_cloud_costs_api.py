"""Integration tests for the CloudCost ingestion/query/forecast REST API."""


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_project(client, token: str) -> dict:
    return client.post(
        "/api/v1/projects", json={"name": "Cloud Costs API Demo"}, headers=_auth_header(token)
    ).json()


def test_ingest_cloud_cost_requires_existing_project(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    response = client.post(
        "/api/v1/projects/999999/cloud-costs",
        json={
            "provider": "aws",
            "service_name": "EC2",
            "cost_amount": 500,
            "billing_period_start": "2026-06-01",
            "billing_period_end": "2026-06-30",
        },
        headers=_auth_header(token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_ingest_cloud_cost_forbidden_for_viewer(client, make_user_with_role):
    operator_token = make_user_with_role("operator_user", "operator")
    project = _create_project(client, operator_token)

    viewer_token = make_user_with_role("viewer_user")
    response = client.post(
        f"/api/v1/projects/{project['id']}/cloud-costs",
        json={
            "provider": "aws",
            "service_name": "EC2",
            "cost_amount": 500,
            "billing_period_start": "2026-06-01",
            "billing_period_end": "2026-06-30",
        },
        headers=_auth_header(viewer_token),
    )
    assert response.status_code == 403


def test_ingest_rejects_end_before_start(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    project = _create_project(client, token)

    response = client.post(
        f"/api/v1/projects/{project['id']}/cloud-costs",
        json={
            "provider": "aws",
            "service_name": "EC2",
            "cost_amount": 500,
            "billing_period_start": "2026-06-30",
            "billing_period_end": "2026-06-01",
        },
        headers=_auth_header(token),
    )
    assert response.status_code == 422


def test_ingest_and_list_cloud_costs(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    project = _create_project(client, token)

    created = client.post(
        f"/api/v1/projects/{project['id']}/cloud-costs",
        json={
            "provider": "aws",
            "service_name": "EC2",
            "cost_amount": 500.50,
            "billing_period_start": "2026-06-01",
            "billing_period_end": "2026-06-30",
        },
        headers=_auth_header(token),
    )
    assert created.status_code == 201
    assert created.json()["cost_amount"] == 500.50

    listed = client.get(f"/api/v1/projects/{project['id']}/cloud-costs", headers=_auth_header(token))
    assert listed.status_code == 200
    assert listed.json()["meta"]["total"] == 1


def test_forecast_returns_404_without_history(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    project = _create_project(client, token)

    response = client.get(f"/api/v1/projects/{project['id']}/cost-forecast", headers=_auth_header(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NO_COST_HISTORY"


def test_forecast_naive_with_single_month(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    project = _create_project(client, token)
    client.post(
        f"/api/v1/projects/{project['id']}/cloud-costs",
        json={
            "provider": "aws",
            "service_name": "EC2",
            "cost_amount": 1000,
            "billing_period_start": "2026-06-01",
            "billing_period_end": "2026-06-30",
        },
        headers=_auth_header(token),
    )

    response = client.get(f"/api/v1/projects/{project['id']}/cost-forecast", headers=_auth_header(token))
    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "naive_last_period"
    assert body["predicted_next_month_cost"] == 1000.0


def test_forecast_linear_regression_with_trend(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    project = _create_project(client, token)
    for month, amount in [("04", 1000), ("05", 1200), ("06", 1400)]:
        client.post(
            f"/api/v1/projects/{project['id']}/cloud-costs",
            json={
                "provider": "aws",
                "service_name": "EC2",
                "cost_amount": amount,
                "billing_period_start": f"2026-{month}-01",
                "billing_period_end": f"2026-{month}-28",
            },
            headers=_auth_header(token),
        )

    response = client.get(f"/api/v1/projects/{project['id']}/cost-forecast", headers=_auth_header(token))
    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "linear_regression"
    assert body["predicted_next_month_cost"] == 1600.0
