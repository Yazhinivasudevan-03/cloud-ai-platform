"""Integration tests for Metric and ResourceUsage ingestion/query endpoints."""


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_deployment(client, token: str) -> dict:
    project = client.post(
        "/api/v1/projects", json={"name": "Payments Platform"}, headers=_auth_header(token)
    ).json()
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "billing-service"},
        headers=_auth_header(token),
    ).json()
    deployment = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy"},
        headers=_auth_header(token),
    ).json()
    return deployment


def _create_pod(client, token: str, deployment_id: int) -> dict:
    return client.post(
        f"/api/v1/deployments/{deployment_id}/pods",
        json={"pod_name": "pod-a"},
        headers=_auth_header(token),
    ).json()


def test_ingest_metric_requires_existing_deployment(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    response = client.post(
        "/api/v1/deployments/999999/metrics",
        json={"metric_type": "cpu_usage", "value": 42.5, "unit": "percent",
              "recorded_at": "2026-07-15T12:00:00"},
        headers=_auth_header(token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEPLOYMENT_NOT_FOUND"


def test_ingest_metric_forbidden_for_viewer(client, make_user_with_role):
    operator_token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, operator_token)

    viewer_token = make_user_with_role("viewer_user")
    response = client.post(
        f"/api/v1/deployments/{deployment['id']}/metrics",
        json={"metric_type": "cpu_usage", "value": 42.5, "unit": "percent",
              "recorded_at": "2026-07-15T12:00:00"},
        headers=_auth_header(viewer_token),
    )
    assert response.status_code == 403


def test_ingest_and_list_metrics_with_type_and_time_filter(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, token)

    client.post(
        f"/api/v1/deployments/{deployment['id']}/metrics",
        json={"metric_type": "cpu_usage", "value": 40.0, "unit": "percent",
              "recorded_at": "2026-07-15T10:00:00"},
        headers=_auth_header(token),
    )
    client.post(
        f"/api/v1/deployments/{deployment['id']}/metrics",
        json={"metric_type": "memory_usage", "value": 512.0, "unit": "MB",
              "recorded_at": "2026-07-15T11:00:00"},
        headers=_auth_header(token),
    )

    response = client.get(
        f"/api/v1/deployments/{deployment['id']}/metrics",
        params={"metric_type": "cpu_usage"},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["metric_type"] == "cpu_usage"

    time_filtered = client.get(
        f"/api/v1/deployments/{deployment['id']}/metrics",
        params={"since": "2026-07-15T10:30:00"},
        headers=_auth_header(token),
    )
    assert time_filtered.json()["meta"]["total"] == 1
    assert time_filtered.json()["items"][0]["metric_type"] == "memory_usage"


def test_ingest_metric_with_pod_id(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, token)
    pod = _create_pod(client, token, deployment["id"])

    response = client.post(
        f"/api/v1/deployments/{deployment['id']}/metrics",
        json={"metric_type": "cpu_usage", "value": 40.0, "unit": "percent",
              "recorded_at": "2026-07-15T10:00:00", "pod_id": pod["id"]},
        headers=_auth_header(token),
    )
    assert response.status_code == 201
    assert response.json()["pod_id"] == pod["id"]


def test_ingest_metric_rejects_pod_from_different_deployment(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    deployment_a = _create_deployment(client, token)
    pod_a = _create_pod(client, token, deployment_a["id"])

    # A second, unrelated deployment.
    microservice = client.post(
        f"/api/v1/projects/{client.post('/api/v1/projects', json={'name': 'Other Project'}, headers=_auth_header(token)).json()['id']}/microservices",
        json={"name": "other-service"},
        headers=_auth_header(token),
    ).json()
    deployment_b = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "other-deploy"},
        headers=_auth_header(token),
    ).json()

    response = client.post(
        f"/api/v1/deployments/{deployment_b['id']}/metrics",
        json={"metric_type": "cpu_usage", "value": 40.0, "unit": "percent",
              "recorded_at": "2026-07-15T10:00:00", "pod_id": pod_a["id"]},
        headers=_auth_header(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "POD_DEPLOYMENT_MISMATCH"


def test_ingest_and_list_resource_usage(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, token)

    created = client.post(
        f"/api/v1/deployments/{deployment['id']}/resource-usage",
        json={
            "cpu_usage_percent": 55.5,
            "memory_usage_mb": 1024.0,
            "disk_usage_mb": 2048.0,
            "network_in_kbps": 100.0,
            "network_out_kbps": 50.0,
            "recorded_at": "2026-07-15T12:00:00",
        },
        headers=_auth_header(token),
    )
    assert created.status_code == 201
    assert created.json()["cpu_usage_percent"] == 55.5

    listed = client.get(
        f"/api/v1/deployments/{deployment['id']}/resource-usage", headers=_auth_header(token)
    )
    assert listed.status_code == 200
    assert listed.json()["meta"]["total"] == 1


def test_ingest_resource_usage_rejects_negative_values(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, token)

    response = client.post(
        f"/api/v1/deployments/{deployment['id']}/resource-usage",
        json={
            "cpu_usage_percent": -5.0,
            "memory_usage_mb": 1024.0,
            "disk_usage_mb": 2048.0,
            "network_in_kbps": 100.0,
            "network_out_kbps": 50.0,
            "recorded_at": "2026-07-15T12:00:00",
        },
        headers=_auth_header(token),
    )
    assert response.status_code == 422
